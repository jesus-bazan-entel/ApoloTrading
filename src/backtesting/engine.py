"""Historical backtest engine.

Pulls daily OHLC from yfinance, computes a rolling-realized-vol IV proxy,
and replays the bars through the live event bus so the actual production
modules (RiskManager, PortfolioManager, ExitManager, ExecutionEngine) run
unmodified. Options are priced via Black-Scholes against a synthesized
chain (`BacktestMarketDataClient`).

Returns a result dict with the equity curve and trade-level stats.
"""
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional

import pandas as pd
import yfinance as yf
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.backtesting.market_data import BacktestMarketDataClient
from src.config import config
from src.infrastructure.broker.paper import PaperBroker
from src.infrastructure.database.models import (
    AccountState, Base, RiskState, Trade, TradeStatus,
)
from src.infrastructure.event_bus import Event, EventBus, EventType
from src.infrastructure.execution import ExecutionEngine

logger = logging.getLogger("BacktestEngine")


@dataclass
class BacktestResult:
    symbol: str
    start: datetime
    end: datetime
    initial_equity: float
    final_equity: float
    total_pnl: float
    trade_count: int
    wins: int
    losses: int
    win_rate: float
    avg_win: float
    avg_loss: float
    max_drawdown: float
    equity_curve: List[float] = field(default_factory=list)


class BacktestEngine:
    def __init__(
        self,
        symbol: str,
        start: str,                # "YYYY-MM-DD"
        end: str,
        strategy_classes: List[type],
        initial_equity: Optional[float] = None,
        db_path: str = "sqlite:///backtest.db",
    ):
        self.symbol = symbol
        self.start = start
        self.end = end
        self.strategy_classes = strategy_classes
        self.initial_equity = initial_equity or config.INITIAL_EQUITY
        self.db_path = db_path

        self.bus = EventBus()
        self.bt_client = BacktestMarketDataClient()

        # Each backtest gets its own SQLite file — keeps the production DB
        # clean and lets us drop-and-recreate between runs deterministically.
        self.engine = create_engine(self.db_path, echo=False)
        Base.metadata.drop_all(self.engine)
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    # ------------------------------------------------------------------
    def _wire_modules(self):
        from src.domain.exit_manager import ExitManager
        from src.domain.portfolio import PortfolioManager
        from src.risk.manager import RiskManager

        # Override INITIAL_EQUITY for this run via a sentinel AccountState.
        self.session.add(AccountState(
            timestamp=datetime.utcnow(),
            equity=self.initial_equity,
            balance=self.initial_equity,
            risk_state=RiskState.NORMAL,
            drawdown_pct=0.0,
            daily_trades_count=0,
        ))
        self.session.commit()

        RiskManager(self.bus, self.session)
        PortfolioManager(
            self.bus, self.session,
            time_provider=lambda: self.bt_client.now,
        )
        ExitManager(
            self.bus,
            market_data_client=self.bt_client,
            time_provider=lambda: self.bt_client.now,
        )
        ExecutionEngine(self.bus, broker=PaperBroker())
        for cls in self.strategy_classes:
            cls(self.bus, market_data_client=self.bt_client)

    # ------------------------------------------------------------------
    def _load_history(self) -> pd.DataFrame:
        df = yf.download(self.symbol, start=self.start, end=self.end,
                         progress=False, auto_adjust=True)
        if df.empty:
            raise RuntimeError(f"No history for {self.symbol} in window")
        # Normalize a flat single-index Close column even when yfinance returns
        # MultiIndex columns for multi-ticker downloads.
        if isinstance(df.columns, pd.MultiIndex):
            df = df.xs(self.symbol, axis=1, level=1)
        df = df[["Close"]].dropna()
        df["ret"] = df["Close"].pct_change()
        df["vol_20"] = df["ret"].rolling(20).std() * math.sqrt(252)
        # 252-day rolling IV-rank proxy
        rolling = df["vol_20"]
        df["iv_rank"] = ((rolling - rolling.rolling(252, min_periods=20).min())
                         / (rolling.rolling(252, min_periods=20).max()
                            - rolling.rolling(252, min_periods=20).min())
                         * 100.0).clip(0, 100)
        return df.dropna(subset=["vol_20"])

    # ------------------------------------------------------------------
    def run(self) -> BacktestResult:
        self._wire_modules()
        df = self._load_history()
        logger.info(f"Backtest {self.symbol} {self.start}->{self.end} "
                    f"bars={len(df)}")

        equity_curve = []
        for ts, row in df.iterrows():
            spot = float(row["Close"])
            sigma = float(row["vol_20"])
            ivr = float(row["iv_rank"]) if not math.isnan(row["iv_rank"]) else 50.0
            self.bt_client.update(self.symbol, ts.to_pydatetime(), spot, sigma)

            payload = {
                "symbol": self.symbol,
                "price": spot,
                "iv_rank": ivr,
                "timestamp": ts.to_pydatetime(),
            }
            # ExitManager reacts to MARKET_DATA first so any close on this
            # bar is realized before strategies evaluate new entries.
            self.bus.publish(Event(EventType.MARKET_DATA, payload))
            self.bus.publish(Event(EventType.DAILY_BAR, payload))

            latest = (self.session.query(AccountState)
                      .order_by(AccountState.id.desc()).first())
            equity_curve.append(latest.equity if latest else self.initial_equity)

        return self._summarize(df, equity_curve)

    # ------------------------------------------------------------------
    def _summarize(self, df, equity_curve) -> BacktestResult:
        trades = (self.session.query(Trade)
                  .filter(Trade.status == TradeStatus.CLOSED).all())
        pnls = [float(t.pnl or 0.0) for t in trades]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p <= 0]

        peak = equity_curve[0] if equity_curve else self.initial_equity
        max_dd = 0.0
        for eq in equity_curve:
            peak = max(peak, eq)
            dd = (peak - eq) / peak if peak > 0 else 0.0
            max_dd = max(max_dd, dd)

        final = equity_curve[-1] if equity_curve else self.initial_equity
        return BacktestResult(
            symbol=self.symbol,
            start=df.index[0].to_pydatetime() if not df.empty else datetime.utcnow(),
            end=df.index[-1].to_pydatetime() if not df.empty else datetime.utcnow(),
            initial_equity=self.initial_equity,
            final_equity=final,
            total_pnl=sum(pnls),
            trade_count=len(trades),
            wins=len(wins),
            losses=len(losses),
            win_rate=(len(wins) / len(trades)) if trades else 0.0,
            avg_win=(sum(wins) / len(wins)) if wins else 0.0,
            avg_loss=(sum(losses) / len(losses)) if losses else 0.0,
            max_drawdown=max_dd,
            equity_curve=equity_curve,
        )
