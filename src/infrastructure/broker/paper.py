"""Paper broker: fills every order immediately at the limit price.

Mirrors the previous inline behavior of ExecutionEngine._execute_paper so
that PAPER mode keeps working after the adapter refactor.
"""
import uuid

from src.infrastructure.broker.base import BrokerAdapter, FillResult, OrderRequest


class PaperBroker(BrokerAdapter):
    name = "paper"

    def __init__(self, commission_per_contract: float = 1.05):
        self.commission_per_contract = commission_per_contract

    def place_order(self, order: OrderRequest) -> FillResult:
        return FillResult(
            order_id=str(uuid.uuid4()),
            fill_price=order.limit_price,
            filled_quantity=order.quantity,
            commission=self.commission_per_contract * order.quantity,
        )
