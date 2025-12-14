from datetime import datetime
from sqlalchemy.orm import Session
from src.infrastructure.event_bus import EventBus, Event, EventType
from src.infrastructure.database.models import Trade, Leg, AccountState, TradeStatus, RiskState

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

    def on_fill(self, event: Event):
        data = event.data
        print(f"PORTFOLIO: Processing Fill for {data['symbol']}")
        
        # 1. Create Trade Record
        # Simplified: Assuming 1 order = 1 trade for MVP. 
        # In reality, multiple fills make one trade.
        
        # Determine strategy type (passed from signal usually, simplified here)
        strategy_map = {
            "SPY": "BULL_PUT_SPREAD", # Mock inference
            "QQQ": "IRON_CONDOR",
            "IWM": "BEAR_CALL_SPREAD"
        }
        
        new_trade = Trade(
            strategy_type=strategy_map.get(data['symbol'], "BULL_PUT_SPREAD"),
            symbol=data['symbol'],
            entry_time=data['timestamp'] or datetime.utcnow(),
            status=TradeStatus.OPEN,
            entry_credit=data['fill_price'], # Assuming credit receive
            max_risk=data['quantity'] * 100, # Placeholder risk calc
            commission=data.get('commission', 0.0)
        )
        self.db.add(new_trade)
        self.db.commit() # Commit to get ID
        
        # 2. Update Account State
        # Get last state
        last_state = self.db.query(AccountState).order_by(AccountState.timestamp.desc()).first()
        current_equity = last_state.equity if last_state else 100000.0
        
        # Mock PnL impact (since it's a credit, cash goes up, but equity stays same until price moves)
        # For visualization, let's simulate a small immediate random PnL fluctuation
        import random
        pnl_change = random.uniform(-50, 150) 
        
        new_equity = current_equity + pnl_change
        
        # Drawdown Calc
        # (Simplified, need HWM tracking in DB or memory)
        hwm = 100000.0 # simplified
        dd = (hwm - new_equity) / hwm if new_equity < hwm else 0.0
        
        risk_state = RiskState.NORMAL
        if dd > 0.04: risk_state = RiskState.DEFENSIVE
        if dd > 0.08: risk_state = RiskState.HALT

        new_state = AccountState(
            timestamp=datetime.utcnow(),
            equity=new_equity,
            balance=new_equity, # Simplified
            risk_state=risk_state,
            drawdown_pct=dd,
            daily_trades_count=(last_state.daily_trades_count + 1) if last_state else 1
        )
        self.db.add(new_state)
        self.db.commit()
