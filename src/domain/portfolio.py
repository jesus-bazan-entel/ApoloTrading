from datetime import datetime
from typing import Callable, Optional

from sqlalchemy.orm import Session

from src.config import config
from src.infrastructure.database.models import (
    AccountState, Leg, RiskState, StrategyType, Trade, TradeStatus,
)
from src.infrastructure.event_bus import Event, EventBus, EventType


class PortfolioManager:
    """
    Handles state persistence.

    On ORDER_FILL:
      - Opening fill (BUY for debit strategies): create Trade + Leg(s),
        decrement cash by premium paid + commission.
      - Closing fill (SELL with closing_trade_id): mark Trade CLOSED,
        compute realized PnL = (exit - entry) * 100 * qty - commissions,
        increment cash by premium received - commission.

    AccountState is appended after every fill so the dashboard / risk manager
    always sees the latest equity, drawdown, and counters. Daily and weekly
    counters reset automatically when the calendar day / ISO week rolls over,
    using time_provider() (defaults to wall clock; the backtest injects the
    simulated bar timestamp).
    """

    def __init__(self, event_bus: EventBus, db_session: Session,
                 time_provider: Optional[Callable[[], datetime]] = None):
        self.bus = event_bus
        self.db = db_session
        self._now = time_provider or datetime.utcnow
        self.bus.subscribe(EventType.ORDER_FILL, self.on_fill)

    @staticmethod
    def _resolve_strategy(strategy_str) -> StrategyType:
        if isinstance(strategy_str, StrategyType):
            return strategy_str
        try:
            return StrategyType(strategy_str)
        except (ValueError, TypeError):
            return StrategyType.LONG_CALL

    @staticmethod
    def _parse_expiration(value) -> Optional[datetime]:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            try:
                return datetime.strptime(value, "%Y-%m-%d")
            except ValueError:
                return None
        return None

    # ------------------------------------------------------------------
    def on_fill(self, event: Event):
        data = event.data
        side = (data.get("side") or "BUY").upper()
        qty = int(data.get("filled_quantity") or data.get("quantity") or 1)
        fill_price = float(data.get("fill_price", 0.0))
        commission = float(data.get("commission", 0.0))
        closing_trade_id = data.get("closing_trade_id")

        if closing_trade_id is not None:
            self._handle_close(data, qty, fill_price, commission, closing_trade_id)
        else:
            self._handle_open(data, side, qty, fill_price, commission)

    # ------------------------------------------------------------------
    def _handle_open(self, data: dict, side: str, qty: int,
                     fill_price: float, commission: float):
        strategy_enum = self._resolve_strategy(data.get("strategy"))
        is_debit = side == "BUY"
        symbol = data["symbol"]

        max_risk = (fill_price * 100 * qty) if is_debit else (qty * 100)

        pattern_name = data.get("pattern_name")
        rationale = data.get("rationale")

        trade = Trade(
            strategy_type=strategy_enum,
            symbol=symbol,
            entry_time=data.get("timestamp") or self._now(),
            status=TradeStatus.OPEN,
            entry_credit=fill_price,
            max_risk=max_risk,
            commission=commission,
            entry_pattern=pattern_name,
            entry_rationale=rationale,
        )
        self.db.add(trade)
        self.db.flush()  # need trade.id for legs and the fill annotation

        legs = data.get("legs") or []
        for leg in legs:
            self.db.add(Leg(
                trade_id=trade.id,
                option_symbol=self._compose_option_symbol(symbol, leg),
                side=leg.get("side", side),
                strike=float(leg.get("strike", 0.0)),
                expiration=self._parse_expiration(leg.get("expiration")) or self._now(),
                option_type=leg.get("type", "CALL"),
                entry_price=fill_price,
                exit_price=None,
            ))

        # Generate the didactic candlestick chart for this trade. We try, but
        # never let chart errors block trade persistence.
        if pattern_name and data.get("ohlc_history") and legs:
            try:
                from src.visualization.trade_chart import generate_trade_chart
                first_leg = legs[0]
                path = generate_trade_chart(
                    trade_id=trade.id,
                    symbol=symbol,
                    strategy=strategy_enum.value,
                    pattern_name=pattern_name,
                    pattern_bars_back=int(data.get("pattern_bars_back") or 1),
                    rationale=rationale or "",
                    ohlc_history=data["ohlc_history"],
                    entry_spot=float(data.get("spot_at_entry") or 0.0),
                    strike=float(first_leg.get("strike", 0.0)),
                    expiration=first_leg.get("expiration"),
                    overlays=data.get("overlays"),
                )
                if path:
                    trade.chart_path = path
            except Exception as e:
                print(f"PORTFOLIO: chart generation failed for trade {trade.id}: {e}")

        self.db.commit()

        # Annotate the in-flight event so ExitManager and downstream listeners
        # can see the persisted trade_id.
        data["trade_id"] = trade.id

        cash_delta = (-(fill_price * 100 * qty) if is_debit
                      else (fill_price * 100 * qty)) - commission

        pattern_tag = f" [{pattern_name}]" if pattern_name else ""
        print(f"PORTFOLIO: OPEN {side} {qty}x {symbol} "
              f"@ {fill_price} ({strategy_enum.value}){pattern_tag} "
              f"trade_id={trade.id}")

        self._append_account_state(cash_delta=cash_delta, opened_trade=True)

    # ------------------------------------------------------------------
    def _handle_close(self, data: dict, qty: int, fill_price: float,
                      commission: float, closing_trade_id: int):
        trade = self.db.query(Trade).get(closing_trade_id)
        if trade is None:
            print(f"PORTFOLIO: WARN close fill for unknown trade_id={closing_trade_id}")
            return
        if trade.status == TradeStatus.CLOSED:
            return

        # Realized PnL for a long debit trade closed by SELL:
        #   gross = (exit - entry) * 100 * qty
        #   net   = gross - entry_commission - exit_commission
        gross = (fill_price - float(trade.entry_credit)) * 100 * qty
        pnl = gross - float(trade.commission or 0.0) - commission

        trade.exit_time = self._now()
        trade.exit_debit = fill_price
        trade.pnl = round(pnl, 2)
        trade.status = TradeStatus.CLOSED
        trade.commission = float(trade.commission or 0.0) + commission

        for leg in trade.legs:
            leg.exit_price = fill_price

        self.db.commit()
        data["trade_id"] = trade.id

        cash_delta = (fill_price * 100 * qty) - commission

        reason = data.get("exit_reason", "MANUAL")
        print(f"PORTFOLIO: CLOSE {trade.symbol} trade_id={trade.id} "
              f"pnl={trade.pnl} reason={reason}")

        self._append_account_state(cash_delta=cash_delta,
                                   pnl_realized=trade.pnl)

    # ------------------------------------------------------------------
    def _append_account_state(self, cash_delta: float = 0.0,
                              opened_trade: bool = False,
                              pnl_realized: float = 0.0):
        last_state = (self.db.query(AccountState)
                      .order_by(AccountState.id.desc()).first())
        current_equity = last_state.equity if last_state else config.INITIAL_EQUITY

        new_equity = current_equity + (pnl_realized if pnl_realized else 0.0)

        hwm = max(config.INITIAL_EQUITY, current_equity, new_equity)
        dd = (hwm - new_equity) / hwm if new_equity < hwm else 0.0

        risk_state = RiskState.NORMAL
        if dd > 0.04:
            risk_state = RiskState.DEFENSIVE
        if dd > 0.08:
            risk_state = RiskState.HALT

        now = self._now()
        same_day = bool(last_state and last_state.timestamp.date() == now.date())
        same_week = bool(
            last_state
            and last_state.timestamp.isocalendar()[:2] == now.isocalendar()[:2]
        )

        prev_count = (last_state.daily_trades_count or 0) if same_day else 0
        prev_daily = (last_state.daily_pnl or 0.0) if same_day else 0.0
        prev_weekly = (last_state.weekly_pnl or 0.0) if same_week else 0.0
        prev_streak = (last_state.consecutive_losses or 0) if last_state else 0

        if pnl_realized > 0:
            streak = 0
        elif pnl_realized < 0:
            streak = prev_streak + 1
        else:
            streak = prev_streak

        self.db.add(AccountState(
            timestamp=now,
            equity=new_equity,
            balance=new_equity + cash_delta,
            risk_state=risk_state,
            drawdown_pct=dd,
            daily_trades_count=prev_count + (1 if opened_trade else 0),
            daily_pnl=prev_daily + pnl_realized,
            weekly_pnl=prev_weekly + pnl_realized,
            consecutive_losses=streak,
        ))
        self.db.commit()

    # ------------------------------------------------------------------
    @staticmethod
    def _compose_option_symbol(symbol: str, leg: dict) -> str:
        exp = leg.get("expiration") or "OPEN"
        strike = leg.get("strike", 0)
        opt = leg.get("type", "C")[0]
        return f"{symbol}_{exp}_{strike}_{opt}"
