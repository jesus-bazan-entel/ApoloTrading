"""Broker adapter interface.

The ExecutionEngine routes orders through a BrokerAdapter so swapping
between PAPER (synthetic immediate fill) and ALPACA (real options API) is
purely a config flip.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class OrderRequest:
    symbol: str           # underlying (e.g. "XLF")
    side: str             # "BUY" or "SELL"
    quantity: int         # contracts
    limit_price: float    # premium, dollars per share (so per contract * 100)
    legs: List[dict]      # [{type: CALL/PUT, strike, expiration, side}]
    strategy: Optional[str] = None
    closing_trade_id: Optional[int] = None
    exit_reason: Optional[str] = None
    extra: dict = field(default_factory=dict)


@dataclass
class FillResult:
    order_id: str
    fill_price: float
    filled_quantity: int
    commission: float = 0.0
    accepted: bool = True
    error: Optional[str] = None


class BrokerAdapter(ABC):
    """Sync adapter. Live brokers should still respond quickly enough that
    ExecutionEngine can publish ORDER_FILL on the same call; if a broker is
    truly async, wrap it and poll order status before returning."""

    name: str = "base"

    @abstractmethod
    def place_order(self, order: OrderRequest) -> FillResult:
        ...
