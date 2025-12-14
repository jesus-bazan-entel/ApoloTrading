import logging
from collections import defaultdict
from enum import Enum
from typing import List, Callable, Any, Dict
from datetime import datetime

# Configure professional logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("apolo_system.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("EventBus")

class EventType(Enum):
    MARKET_DATA = "MARKET_DATA"
    SIGNAL = "SIGNAL"
    ORDER_REQUEST = "ORDER_REQUEST"
    ORDER_FILL = "ORDER_FILL"
    RISK_CHECK = "RISK_CHECK"
    SYSTEM_STATUS = "SYSTEM_STATUS"
    ERROR = "ERROR"

class Event:
    """Base Event class for the Event-Driven Architecture."""
    def __init__(self, event_type: EventType, data: Dict[str, Any]):
        self.type = event_type
        self.data = data
        self.timestamp = datetime.now()

    def __repr__(self):
        return f"<Event type={self.type.name} timestamp={self.timestamp}>"

class EventBus:
    """
    Central Nervous System of the Application.
    Uses a simple Publisher/Subscriber pattern.
    """
    def __init__(self):
        self._subscribers: Dict[EventType, List[Callable]] = defaultdict(list)
        self._event_queue: List[Event] = []

    def subscribe(self, event_type: EventType, handler: Callable[[Event], None]):
        """Register a handler for a specific event type."""
        self._subscribers[event_type].append(handler)
        logger.info(f"Subscribed {handler.__name__} to {event_type.name}")

    def publish(self, event: Event):
        """
        Publish an event to all subscribers. 
        In a synchronous engine, this executes immediately.
        """
        logger.debug(f"Publishing event: {event}")
        if event.type in self._subscribers:
            for handler in self._subscribers[event.type]:
                try:
                    handler(event)
                except Exception as e:
                    logger.critical(f"Error acting on event {event.type} in handler {handler.__name__}: {e}", exc_info=True)
                    # Publish Error event to system
                    error_event = Event(EventType.ERROR, {"message": str(e), "origin": handler.__name__})
                    # Avoid infinite loops if error handler fails
                    if event.type != EventType.ERROR:
                        self.publish(error_event)

    def reset(self):
        self._subscribers.clear()
        self._event_queue.clear()
