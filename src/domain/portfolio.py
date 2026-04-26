import random
from datetime import datetime
from sqlalchemy.orm import Session
from src.config import config
from src.infrastructure.event_bus import EventBus, Event, EventType
from src.infrastructure.database.models import (
    Trade, Leg, AccountState, TradeStatus, RiskState, StrategyType,
)

class PortfolioManager:
    """
    Handles state persistence.
    Listens to ORDER_FILL to save Trades.
    Updates Account Equity.
    """
    def __init__(self, event_bus: EventBus, db_session: Session):
        self.bus = event_bus
        self.db = db_session
        self.bus.subscribe(EventType.ORDER_FILL, self.on_fill)

    @staticmethod
    def _resolve_strategy(strategy_str) -> StrategyType:
        if isinstance(strategy_str, StrategyType):
            return strategy_str
        try:
            return StrategyType(strategy_str)
        except (ValueError, TypeError):
            return StrategyType.LONG_CALL

    def on_fill(self, event: Event):
        data = event.data
        side = (data.get('side') or 'BUY').upper()
        is_debit = side == 'BUY'
        qty = data.get('filled_quantity') or data.get('quantity') or 1
        fill_price = data.get('fill_price', 0.0)
        commission = data.get('commission', 0.0)

        strategy_enum = self._resolve_strategy(data.get('strategy'))

        print(f"PORTFOLIO: Fill {side} {qty}x {data['symbol']} @ {fill_price} "
              f"({strategy_enum.value})")

        # 1. Trade record. For long options, max_risk = premium paid * 100 * qty.
        if is_debit:
            max_risk = fill_price * 100 * qty
        else:
            max_risk = qty * 100  # placeholder for credit strategies

        new_trade = Trade(
            strategy_type=strategy_enum,
            symbol=data['symbol'],
            entry_time=data.get('timestamp') or datetime.utcnow(),
            status=TradeStatus.OPEN,
            entry_credit=fill_price,
            max_risk=max_risk,
            commission=commission,
        )
        self.db.add(new_trade)
        self.db.commit()

        # 2. Update Account State.
        last_state = (self.db.query(AccountState)
                      .order_by(AccountState.timestamp.desc()).first())
        current_equity = last_state.equity if last_state else config.INITIAL_EQUITY

        # Simulated mark-to-market move on entry (placeholder until real
        # closing prices are wired in). For debit trades, we bias the random
        # range a bit positively when the directional bet is right and
        # negatively when it isn't; we don't know that here, so keep it
        # symmetric scaled to the position's notional risk.
        notional = max(max_risk, 1.0)
        pnl_change = random.uniform(-0.3, 0.5) * notional

        new_equity = current_equity + pnl_change

        hwm = max(config.INITIAL_EQUITY, current_equity)
        dd = (hwm - new_equity) / hwm if new_equity < hwm else 0.0

        risk_state = RiskState.NORMAL
        if dd > 0.04:
            risk_state = RiskState.DEFENSIVE
        if dd > 0.08:
            risk_state = RiskState.HALT

        new_state = AccountState(
            timestamp=datetime.utcnow(),
            equity=new_equity,
            balance=new_equity,
            risk_state=risk_state,
            drawdown_pct=dd,
            daily_trades_count=((last_state.daily_trades_count or 0) + 1)
                                if last_state else 1,
        )
        self.db.add(new_state)
        self.db.commit()
