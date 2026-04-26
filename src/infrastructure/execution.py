import logging
from typing import Optional

from src.config import config
from src.infrastructure.broker import BrokerAdapter, OrderRequest, build_broker
from src.infrastructure.event_bus import Event, EventBus, EventType

logger = logging.getLogger("ExecutionEngine")


class ExecutionEngine:
    """Routes ORDER_REQUEST events through a BrokerAdapter and publishes the
    resulting ORDER_FILL. The broker is selected via config.BROKER (PAPER /
    ALPACA). Pass a broker explicitly to override (used by tests/backtests)."""

    def __init__(self, event_bus: EventBus, broker: Optional[BrokerAdapter] = None):
        self.bus = event_bus
        self.broker = broker or build_broker(config.BROKER)
        logger.info(f"ExecutionEngine using broker={self.broker.name}")
        self.bus.subscribe(EventType.ORDER_REQUEST, self.on_order_request)

    def on_order_request(self, event: Event):
        order_req = event.data
        logger.info(f"Order request: {order_req}")

        order = OrderRequest(
            symbol=order_req["symbol"],
            side=order_req["side"],
            quantity=int(order_req["quantity"]),
            limit_price=float(order_req["price"]),
            legs=order_req.get("legs") or [],
            strategy=order_req.get("strategy"),
            closing_trade_id=order_req.get("closing_trade_id"),
            exit_reason=order_req.get("exit_reason"),
        )

        result = self.broker.place_order(order)
        if not result.accepted:
            logger.error(f"Broker rejected order: {result.error}")
            self.bus.publish(Event(EventType.ERROR, {
                "origin": "ExecutionEngine",
                "message": result.error,
                "order": order_req,
            }))
            return

        self.bus.publish(Event(EventType.ORDER_FILL, {
            "order_id": result.order_id,
            "signal_id": order_req.get("signal_id"),
            "symbol": order.symbol,
            "strategy": order.strategy,
            "side": order.side,
            "legs": order.legs,
            "filled_quantity": result.filled_quantity,
            "fill_price": result.fill_price,
            "commission": result.commission,
            "closing_trade_id": order.closing_trade_id,
            "exit_reason": order.exit_reason,
            "timestamp": None,
        }))
