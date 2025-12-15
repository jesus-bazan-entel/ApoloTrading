from datetime import datetime, date
from typing import Optional
from sqlalchemy.orm import Session
from src.infrastructure.event_bus import EventBus, Event, EventType
from src.infrastructure.database.models import Trade, AccountState, RiskState, TradeStatus

class RiskManager:
    """
    The Gatekeeper.
    Subscribes to SIGNAL events.
    Checks system health, drawdown, and correlation.
    Publishes ORDER_REQUEST if safe.
    """
    def __init__(self, event_bus: EventBus, db_session: Session):
        self.bus = event_bus
        self.db = db_session
        
        # Risk Limits (hardcoded defaults, should be from User Config)
        self.max_drawdown_limit = 0.08 # 8% Hard Stop
        self.daily_max_loss_pct = 0.02 # 2% Daily Max Loss
        self.weekly_max_loss_pct = 0.05 # 5% Weekly Max Loss
        self.max_consecutive_losses = 3
        
        self.daily_max_trades = 3
        
        # Subscribe to signals
        self.bus.subscribe(EventType.SIGNAL, self.on_signal)

    def _get_current_risk_state(self) -> AccountState:
        # Get latest state from DB
        state = self.db.query(AccountState).order_by(AccountState.timestamp.desc()).first()
        if not state:
            # Initial State
            return AccountState(
                equity=100000.0, 
                balance=100000.0, 
                risk_state=RiskState.NORMAL, 
                drawdown_pct=0.0,
                daily_pnl=0.0,
                weekly_pnl=0.0,
                consecutive_losses=0
            )
        return state

    def _calculate_position_size(self, signal_data: dict, state: AccountState) -> float:
        """
        Dynamic Position Sizing:
        NORMAL: 2% Risk
        DEFENSIVE: 1% Risk
        HALT: 0%
        """
        if state.risk_state == RiskState.HALT:
            return 0.0
        
        risk_pct = 0.02 if state.risk_state == RiskState.NORMAL else 0.01
        capital_at_risk = state.equity * risk_pct
        
        # Estimation: For Credit Spreads, Max Risk = width - credit
        risk_per_contract = signal_data.get('risk_per_unit', 100.0) 
        
        if risk_per_contract <= 0: return 0.0
        
        quantity = int(capital_at_risk / risk_per_contract)
        return quantity

    def on_signal(self, event: Event):
        signal = event.data
        state = self._get_current_risk_state()

        # 1. Check Global Kill Switch (Drawdown)
        if state.drawdown_pct > self.max_drawdown_limit:
            print(f"RISK REJECT: Max Drawdown breached ({state.drawdown_pct:.2%})")
            return

        # 2. Check Daily Loss Limit (PMD)
        if state.daily_pnl < -(state.equity * self.daily_max_loss_pct):
            print(f"RISK REJECT: Daily Max Loss breached ({state.daily_pnl})")
            return

        # 3. Check Weekly Loss Limit (PMS)
        if state.weekly_pnl < -(state.equity * self.weekly_max_loss_pct):
            print(f"RISK REJECT: Weekly Max Loss breached ({state.weekly_pnl})")
            return

        # 4. Check Consecutive Losses
        if state.consecutive_losses >= self.max_consecutive_losses:
            print(f"RISK REJECT: Max Consecutive Losses reached ({state.consecutive_losses})")
            return

        # 5. Daily Limits (Trades count)
        daily_count = state.daily_trades_count if state.daily_trades_count is not None else 0
        if daily_count >= self.daily_max_trades:
            print("RISK REJECT: Daily trade limit reached")
            return

        # 6. Position Sizing
        quantity = self._calculate_position_size(signal, state)
        if quantity <= 0:
            print(f"RISK REJECT: Calculated quantity is 0 (Risk State: {state.risk_state})")
            return

        # 7. Publish Order Request
        order_event = Event(EventType.ORDER_REQUEST, {
            "signal_id": signal.get('id'),
            "symbol": signal.get('symbol'),
            "strategy": signal.get('strategy'),
            "side": signal.get('side'),
            "quantity": quantity,
            "order_type": "LIMIT", # Options limit orders
            "price": signal.get('limit_price'),
            "legs": signal.get('legs') # Pass complex legs info
        })
        print(f"RISK APPROVED: {quantity} cons for {signal.get('symbol')}")
        self.bus.publish(order_event)

    def update_account_state(self, current_equity: float, pnl_change: float = 0.0):
        """
        Called after trades allow updating DD and State.
        Now requires pnl_change to update daily/weekly PnL.
        """
        latest = self._get_current_risk_state()
        
        # Calculate Drawdown
        hwm = 100000.0 # Placeholder
        dd = (hwm - current_equity) / hwm
        
        new_state = RiskState.NORMAL
        if dd > 0.04: new_state = RiskState.DEFENSIVE
        if dd > 0.08: new_state = RiskState.HALT
        
        # Update Counters
        daily_pnl = latest.daily_pnl + pnl_change
        weekly_pnl = latest.weekly_pnl + pnl_change
        
        con_losses = latest.consecutive_losses
        if pnl_change < 0:
            con_losses += 1
        elif pnl_change > 0:
            con_losses = 0 # Reset on win
        
        # Needs logic to reset daily/weekly PnL (omitted for brevity, assume manual reset or cron)
        
        new_record = AccountState(
            equity=current_equity,
            balance=current_equity, 
            risk_state=new_state,
            drawdown_pct=dd,
            daily_trades_count=latest.daily_trades_count,
            daily_pnl=daily_pnl,
            weekly_pnl=weekly_pnl,
            consecutive_losses=con_losses
        )
        self.db.add(new_record)
        self.db.commit()
