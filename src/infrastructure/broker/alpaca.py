"""Alpaca options broker adapter.

Skeleton: imports `alpaca-py` lazily so the rest of the system runs even
when the SDK is not installed. Reads ALPACA_API_KEY / ALPACA_API_SECRET /
ALPACA_PAPER (true/false) from the environment.

The OCC option symbol is built from the underlying + expiration + strike
+ option type (call/put). Alpaca expects something like
`XLF260116C00046000` (root + YYMMDD + C/P + strike*1000 padded to 8).

NOTE: Alpaca options trading is paper-only for many accounts and requires
explicit approval. This adapter is intentionally minimal — verify routing
in their paper sandbox before flipping BROKER=ALPACA on a real account.
"""
import logging
import os
import uuid
from datetime import datetime
from typing import Optional

from src.infrastructure.broker.base import BrokerAdapter, FillResult, OrderRequest

logger = logging.getLogger("AlpacaBroker")


def _occ_symbol(underlying: str, expiration: str, strike: float, option_type: str) -> str:
    exp = datetime.strptime(expiration, "%Y-%m-%d")
    code = "C" if option_type.upper().startswith("C") else "P"
    strike_int = int(round(strike * 1000))
    return f"{underlying.upper()}{exp.strftime('%y%m%d')}{code}{strike_int:08d}"


class AlpacaBroker(BrokerAdapter):
    name = "alpaca"

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        paper: Optional[bool] = None,
    ):
        self.api_key = api_key or os.getenv("ALPACA_API_KEY")
        self.api_secret = api_secret or os.getenv("ALPACA_API_SECRET")
        env_paper = os.getenv("ALPACA_PAPER", "true").lower() != "false"
        self.paper = env_paper if paper is None else paper

        if not self.api_key or not self.api_secret:
            raise RuntimeError(
                "AlpacaBroker requires ALPACA_API_KEY and ALPACA_API_SECRET")

        try:
            from alpaca.trading.client import TradingClient
        except ImportError as e:
            raise RuntimeError(
                "alpaca-py not installed. Run: pip install alpaca-py") from e

        self._client = TradingClient(self.api_key, self.api_secret, paper=self.paper)
        logger.info(f"AlpacaBroker ready (paper={self.paper})")

    def place_order(self, order: OrderRequest) -> FillResult:
        from alpaca.trading.requests import LimitOrderRequest
        from alpaca.trading.enums import OrderSide, TimeInForce

        # Single-leg debit only for now. Multi-leg combos require Alpaca's
        # OptionLegRequest list, not implemented in this skeleton.
        if not order.legs or len(order.legs) != 1:
            return FillResult(order_id="", fill_price=0.0, filled_quantity=0,
                              accepted=False,
                              error="AlpacaBroker only handles single-leg orders")

        leg = order.legs[0]
        try:
            occ = _occ_symbol(
                order.symbol,
                leg["expiration"],
                float(leg["strike"]),
                leg["type"],
            )
        except Exception as e:
            return FillResult(order_id="", fill_price=0.0, filled_quantity=0,
                              accepted=False,
                              error=f"Bad option symbol: {e}")

        side = OrderSide.BUY if order.side.upper() == "BUY" else OrderSide.SELL

        req = LimitOrderRequest(
            symbol=occ,
            qty=order.quantity,
            side=side,
            time_in_force=TimeInForce.DAY,
            limit_price=order.limit_price,
        )

        try:
            placed = self._client.submit_order(req)
        except Exception as e:
            logger.error(f"Alpaca submit_order failed: {e}")
            return FillResult(order_id="", fill_price=0.0, filled_quantity=0,
                              accepted=False, error=str(e))

        # Alpaca options fills are async; we report the request as accepted
        # at the limit price and let the rest of the system reconcile when
        # the trade activity stream emits the actual fill. Wire that stream
        # up before going live.
        return FillResult(
            order_id=str(getattr(placed, "id", uuid.uuid4())),
            fill_price=order.limit_price,
            filled_quantity=order.quantity,
            commission=0.0,
            accepted=True,
        )
