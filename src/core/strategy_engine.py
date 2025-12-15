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
    STRATEGIES = [StrategyType.BULL_PUT_SPREAD, StrategyType.BEAR_CALL_SPREAD, StrategyType.CASH_SECURED_PUT, StrategyType.IRON_CONDOR]
    
    def __init__(self, session: Session):
        self.session = session

    def analyze_market(self):
        """
        Simulates scanning the market for opportunities fitting PRD criteria.
        Criteria:
        - Delta 20-40
        - Expiration 30-45 days
        - IV Rank > 50 (High Vol)
        """
        symbol = random.choice(self.APPROVED_SYMBOLS)
        strategy = random.choice(self.STRATEGIES)
        
        # Simulate pricing & Greeks
        base_price = random.uniform(100, 500)
        
        # PRD: Focus on 30-45 DTE
        dte = random.randint(30, 45)
        
        # PRD: Delta 20-40 (OTM)
        # Simulating OTM by strike distance
        strike_distance = random.uniform(0.03, 0.08) # 3-8% OTM
        
        if strategy == StrategyType.CASH_SECURED_PUT:
             max_risk = base_price * 100 # Cash Secured
             entry_credit = base_price * random.uniform(0.01, 0.03) # 1-3% premium
        else:
             # Spreads
             width = 5.0 
             max_risk = (width * 100) * 0.8 # Risk is width - credit roughly
             entry_credit = width * 100 * 0.2 # 20% of width
        
        return {
            "symbol": symbol,
            "strategy": strategy,
            "entry_credit": round(entry_credit, 2),
            "max_risk": round(max_risk, 2),
            "prob_profit": random.randint(65, 85),
            "dte": dte,
            "delta_proxy": random.uniform(0.20, 0.40)
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
        PRD: Buy to Close if premium drops to 20% of original (80% profit).
        """
        trade = self.session.query(Trade).get(trade_id)
        if trade and trade.status == TradeStatus.OPEN:
            # Simulate exit based on Theta Decay logic
            # Scenario A: Profit Target Hit (BTC @ 20%)
            is_profit_target = random.random() < 0.60 
            
            if is_profit_target:
               exit_price = trade.entry_credit * 0.20 # Compulsory exit at 20%
            else:
               # Scenario B: Stop Loss or Expiration Challenge
               # Random outcome for other cases
               is_winner = random.random() < 0.50
               if is_winner:
                   exit_price = trade.entry_credit * random.uniform(0.25, 0.60)
               else:
                   exit_price = trade.entry_credit * random.uniform(1.2, 1.8) # Loss
            
            pnl = trade.entry_credit - exit_price - trade.commission
            
            trade.exit_time = datetime.utcnow()
            trade.exit_debit = round(exit_price, 2)
            trade.pnl = round(pnl, 2)
            trade.status = TradeStatus.CLOSED
            
            self.session.commit()
            return trade
        return None
