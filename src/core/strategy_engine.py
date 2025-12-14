import random
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from src.infrastructure.database.models import Trade, StrategyType, TradeStatus, RiskState

class StrategyEngine:
    """
    Simulates the AI Trader logic:
    1. Scans markets (random generation for prototype)
    2. Valuates risk
    3. Executes trades
    """
    
    APPROVED_SYMBOLS = ["SPY", "QQQ", "IWM", "MSFT", "AAPL", "NVDA", "AMD", "TSLA"]
    STRATEGIES = [StrategyType.BULL_PUT_SPREAD, StrategyType.BEAR_CALL_SPREAD, StrategyType.IRON_CONDOR]
    
    def __init__(self, session: Session):
        self.session = session

    def analyze_market(self):
        """
        Simulates scanning the market for opportunities.
        Returns a potential trade object (uncommitted).
        """
        symbol = random.choice(self.APPROVED_SYMBOLS)
        strategy = random.choice(self.STRATEGIES)
        
        # Simulate pricing logic
        base_price = random.uniform(100, 500)
        max_risk = base_price * 100 * 0.05 # 5% risk width approx
        entry_credit = max_risk * random.uniform(0.15, 0.40) # 15-40% RoR
        
        return {
            "symbol": symbol,
            "strategy": strategy,
            "entry_credit": round(entry_credit, 2),
            "max_risk": round(max_risk, 2),
            "prob_profit": random.randint(65, 85)
        }

    def execute_ai_trade(self, trade_proposal):
        """
        Commits the trade to the database (Global Execution).
        """
        new_trade = Trade(
            strategy_type=trade_proposal["strategy"],
            symbol=trade_proposal["symbol"],
            entry_time=datetime.utcnow(),
            status=TradeStatus.OPEN,
            entry_credit=trade_proposal["entry_credit"],
            max_risk=trade_proposal["max_risk"],
            exit_debit=0.0,
            pnl=0.0,
            commission=1.50 # estimate
        )
        
        self.session.add(new_trade)
        self.session.commit()
        return new_trade

    def close_trade(self, trade_id):
        """
        Simulates closing a trade.
        """
        trade = self.session.query(Trade).get(trade_id)
        if trade and trade.status == TradeStatus.OPEN:
            # Simulate exit pricing
            # Randomness: 70% chance of profit
            is_winner = random.random() < 0.70
            
            if is_winner:
               # Winner: bought back for 10-50% of credit
               exit_price = trade.entry_credit * random.uniform(0.10, 0.50)
            else:
               # Loser: bought back for 120-200% of credit (loss)
               exit_price = trade.entry_credit * random.uniform(1.2, 2.0)
            
            pnl = trade.entry_credit - exit_price - trade.commission
            
            trade.exit_time = datetime.utcnow()
            trade.exit_debit = round(exit_price, 2)
            trade.pnl = round(pnl, 2)
            trade.status = TradeStatus.CLOSED
            
            self.session.commit()
            return trade
        return None
