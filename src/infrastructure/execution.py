import logging
import uuid
from typing import Dict
from src.infrastructure.event_bus import EventBus, Event, EventType

logger = logging.getLogger("ExecutionEngine")

class ExecutionEngine:
    """
    Handles Order Execution.
    Modes:
    - PAPER: Simulates fills locally.
    - LIVE: Connects to Broker API (TODO).
    """
    def __init__(self, event_bus: EventBus, mode: str = "PAPER"):
        self.bus = event_bus
        self.mode = mode
        self.active_orders: Dict[str, dict] = {}
        
        self.bus.subscribe(EventType.ORDER_REQUEST, self.on_order_request)

    def on_order_request(self, event: Event):
        order_req = event.data
        logger.info(f"Received Order Request: {order_req}")
        
        if self.mode == "PAPER":
            self._execute_paper(order_req)
        else:
            self._execute_live(order_req)

    def _execute_paper(self, order_req: dict):
        # Simulate Order Placement
        order_id = str(uuid.uuid4())
        logger.info(f"PAPER TRADING: Placing order {order_id} for {order_req['symbol']}")
        
        # Simulate Immediate Fill for now (In real paper trading, we'd wait for price match)
        fill_event = Event(EventType.ORDER_FILL, {
            "order_id": order_id,
            "signal_id": order_req.get('signal_id'),
            "symbol": order_req['symbol'],
            "filled_quantity": order_req['quantity'],
            "fill_price": order_req['price'], # Filled at limit
            "commission": 1.05 * order_req['quantity'], # Mock commission
            "timestamp": event.timestamp if 'event' in locals() else None
        })
        self.bus.publish(fill_event)

    def _execute_live(self, order_req: dict):
        raise NotImplementedError("Live Trading adapters (IBKR/Alpaca) not yet implemented.")
