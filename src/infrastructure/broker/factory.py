from src.infrastructure.broker.base import BrokerAdapter
from src.infrastructure.broker.paper import PaperBroker


def build_broker(name: str) -> BrokerAdapter:
    name = (name or "PAPER").upper()
    if name == "PAPER":
        return PaperBroker()
    if name == "ALPACA":
        # Lazy import so the SDK is only required when actually used.
        from src.infrastructure.broker.alpaca import AlpacaBroker
        return AlpacaBroker()
    raise ValueError(f"Unknown broker: {name}")
