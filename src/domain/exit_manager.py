"""Exit manager for long debit option trades.

Tracks open positions in memory (populated from ORDER_FILL events) and on
each MARKET_DATA tick re-prices the open contracts to decide whether to
close. Three exit rules, all configurable via env vars:

- profit target: current premium >= entry * (1 + PROFIT_TARGET_PCT)
- stop loss:     current premium <= entry * (1 - STOP_LOSS_PCT)
- DTE exit:      days to expiration <= DTE_EXIT_DAYS

When triggered, publishes ORDER_REQUEST(side=SELL, closing_trade_id=...)
which the ExecutionEngine fills like any other order. PortfolioManager
then realizes PnL on the close fill.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Dict, Optional

from src.config import config
from src.infrastructure.event_bus import Event, EventBus, EventType
from src.infrastructure.market_data.client import MarketDataClient, bs_price

logger = logging.getLogger("ExitManager")


@dataclass
class OpenPosition:
    trade_id: int
    symbol: str
    strategy: str
    option_type: str   # CALL or PUT
    strike: float
    expiration: Optional[datetime]
    entry_price: float
    quantity: int
    iv_at_entry: Optional[float]
    bracket_pct: Optional[float] = None  # per-trade override (SPY playbook = 0.10)


class ExitManager:
    def __init__(
        self,
        event_bus: EventBus,
        market_data_client: Optional[MarketDataClient] = None,
        risk_free_rate: float = 0.05,
        time_provider: Optional[Callable[[], datetime]] = None,
    ):
        self.bus = event_bus
        self.market_data = market_data_client
        self.r = risk_free_rate
        # time_provider lets the backtest inject simulated time. In live mode
        # it defaults to the real wall clock.
        self._now = time_provider or datetime.now
        self.positions: Dict[int, OpenPosition] = {}

        self.bus.subscribe(EventType.ORDER_FILL, self.on_fill)
        self.bus.subscribe(EventType.MARKET_DATA, self.on_market_data)

    # ------------------------------------------------------------------
    # Position tracking
    # ------------------------------------------------------------------
    def on_fill(self, event: Event):
        data = event.data
        trade_id = data.get("trade_id")
        if trade_id is None:
            return

        # Close fill: drop the position from the tracker.
        if data.get("closing_trade_id") is not None:
            self.positions.pop(data["closing_trade_id"], None)
            return

        legs = data.get("legs") or []
        if not legs:
            return
        leg = legs[0]  # single-leg debit trades

        exp = leg.get("expiration")
        if isinstance(exp, str):
            try:
                exp = datetime.strptime(exp, "%Y-%m-%d")
            except ValueError:
                exp = None

        self.positions[trade_id] = OpenPosition(
            trade_id=trade_id,
            symbol=data["symbol"],
            strategy=data.get("strategy") or "LONG_CALL",
            option_type=leg.get("type", "CALL"),
            strike=float(leg.get("strike", 0.0)),
            expiration=exp if isinstance(exp, datetime) else None,
            entry_price=float(data.get("fill_price", 0.0)),
            quantity=int(data.get("filled_quantity") or data.get("quantity") or 1),
            iv_at_entry=leg.get("iv"),
            bracket_pct=data.get("bracket_pct"),
        )
        logger.info(f"Tracking position trade_id={trade_id} {self.positions[trade_id]}")

    # ------------------------------------------------------------------
    # Exit evaluation
    # ------------------------------------------------------------------
    def on_market_data(self, event: Event):
        data = event.data
        symbol = data.get("symbol")
        spot = data.get("price")
        if not symbol or spot is None or not self.positions:
            return

        for trade_id, pos in list(self.positions.items()):
            if pos.symbol != symbol:
                continue
            current = self._current_premium(pos, spot)
            if current is None:
                continue
            reason = self._exit_reason(pos, current)
            if reason:
                self._submit_close(pos, current, reason)

    def _current_premium(self, pos: OpenPosition, spot: float) -> Optional[float]:
        # 1. Live chain lookup (most accurate)
        if self.market_data is not None and pos.expiration is not None:
            exp_str = pos.expiration.strftime("%Y-%m-%d")
            opt_type = "call" if pos.option_type == "CALL" else "put"
            price = self.market_data.get_option_price(
                pos.symbol, exp_str, pos.strike, opt_type)
            if price is not None and price > 0:
                return price

        # 2. Black-Scholes fallback using stored IV
        if pos.iv_at_entry and pos.expiration is not None:
            T = max((pos.expiration - self._now()).days, 0) / 365.0
            opt_type = "call" if pos.option_type == "CALL" else "put"
            return round(
                bs_price(spot, pos.strike, T, self.r, pos.iv_at_entry, opt_type),
                2,
            )

        # 3. Last resort: linear-ish proxy using spot move (very rough — used
        # only in pure simulation where no IV/expiration is set).
        intrinsic_now = (max(spot - pos.strike, 0.0) if pos.option_type == "CALL"
                         else max(pos.strike - spot, 0.0))
        # Assume entry was almost all extrinsic; decay it slightly.
        return round(max(intrinsic_now, pos.entry_price * 0.9), 2)

    def _exit_reason(self, pos: OpenPosition, current: float) -> Optional[str]:
        # Per-trade bracket overrides the global profit/stop pcts when set.
        if pos.bracket_pct is not None:
            target_pct = stop_pct = pos.bracket_pct
        else:
            target_pct = config.PROFIT_TARGET_PCT
            stop_pct = config.STOP_LOSS_PCT
        if current >= pos.entry_price * (1 + target_pct):
            return "PROFIT_TARGET"
        if current <= pos.entry_price * (1 - stop_pct):
            return "STOP_LOSS"
        if pos.expiration is not None:
            dte = (pos.expiration - self._now()).days
            if dte <= config.DTE_EXIT_DAYS:
                return "DTE"
        return None

    def _submit_close(self, pos: OpenPosition, current: float, reason: str):
        logger.info(f"EXIT {reason}: closing trade_id={pos.trade_id} {pos.symbol} "
                    f"entry={pos.entry_price} now={current}")
        # Drop optimistically; if the fill never arrives, on_fill (close) is a
        # no-op and a duplicate close request will be filtered next tick by
        # the missing trade_id.
        self.positions.pop(pos.trade_id, None)

        self.bus.publish(Event(EventType.ORDER_REQUEST, {
            "symbol": pos.symbol,
            "strategy": pos.strategy,
            "side": "SELL",
            "quantity": pos.quantity,
            "order_type": "LIMIT",
            "price": current,
            "legs": [{
                "side": "SELL",
                "type": pos.option_type,
                "strike": pos.strike,
                "expiration": (pos.expiration.strftime("%Y-%m-%d")
                               if pos.expiration else None),
            }],
            "closing_trade_id": pos.trade_id,
            "exit_reason": reason,
        }))
