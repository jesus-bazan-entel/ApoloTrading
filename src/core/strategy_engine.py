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
    STRATEGIES = [StrategyType.CASH_SECURED_PUT, StrategyType.BEAR_CALL_SPREAD, StrategyType.BULL_PUT_SPREAD, StrategyType.IRON_CONDOR]
    
    def __init__(self, session: Session):
        self.session = session
        # Initialize Real Data Access
        from src.infrastructure.market_data.client import MarketDataClient
        self.market_data = MarketDataClient()

    def analyze_market(self):
        """
        Scans the market using REAL DATA via MarketDataClient.
        Falls back to simulation only if data fetch fails.
        """
        symbol = random.choice(self.APPROVED_SYMBOLS)
        strategy = random.choice(self.STRATEGIES)
        
        # 1. Fetch Real Data
        print(f"AI Scanning {symbol} for {strategy}...")
        current_price = self.market_data.get_current_price(symbol)
        chain_data = self.market_data.get_option_chain(symbol)
        
        if not chain_data or current_price == 0:
            print("Real data unavailable, falling back to basic simulation.")
            return self._analyze_market_simulation(symbol, strategy) # Helper for fallback
            
        # 2. Strategy Logic with Real Data
        expiration = chain_data['expiration']
        options_df = None
        is_call = False
        
        # Define Target Strikes based on Strategy
        target_strike = 0
        limit_price = 0
        risk = 0
        
        if strategy == StrategyType.CASH_SECURED_PUT or strategy == StrategyType.BULL_PUT_SPREAD:
            # Look for OTM Puts (Strike < Price) -> Delta ~0.30 approx 4-5% OTM for volatile, 2-3% for stable
            target_strike_price = current_price * 0.96 # 4% OTM
            options_df = chain_data['puts']
            is_call = False
            
        elif strategy == StrategyType.BEAR_CALL_SPREAD:
            # Look for OTM Calls (Strike > Price)
            target_strike_price = current_price * 1.04 # 4% OTM
            options_df = chain_data['calls']
            is_call = True
            
        else:
            # Iron Condor -> Complex, let's simplify to Put side for MVP or fallback
            return self._analyze_market_simulation(symbol, strategy)

        # 3. Find specific contract
        # Sort by strike to find closest to target
        options_df['diff'] = abs(options_df['strike'] - target_strike_price)
        options_df = options_df.sort_values('diff')
        
        if options_df.empty:
             return self._analyze_market_simulation(symbol, strategy)
             
        selected_option = options_df.iloc[0] # The closest one
        
        # 4. Pricing
        # Use 'lastPrice' or midpoint of 'bid'/'ask'
        price = selected_option.get('lastPrice', 0)
        strike = selected_option['strike']
        
        # Calculate Risk/Return based on Strategy
        entry_credit = price * 100 # Premium received
        
        if strategy == StrategyType.CASH_SECURED_PUT:
            max_risk = strike * 100 # Full collateral
        elif strategy == StrategyType.BEAR_CALL_SPREAD or strategy == StrategyType.BULL_PUT_SPREAD:
            # Mocking the protection leg (buying next strike)
            # Assuming spread width of $5
            width = 5.0
            protection_price = price * 0.3 # Rough estimate of buying cheaper option
            net_credit = (price - protection_price) * 100
            entry_credit = net_credit
            max_risk = (width * 100) - net_credit
        else:
            max_risk = 0
            
        return {
            "symbol": symbol,
            "strategy": strategy,
            "entry_credit": round(entry_credit, 2),
            "max_risk": round(max_risk, 2),
            "prob_profit": random.randint(65, 85),
            "dte": (datetime.strptime(expiration, "%Y-%m-%d") - datetime.now()).days,
            "delta_proxy": 0.30, 
            "real_data": True,
            "strike_details": f"Strike {strike} @ {expiration}",
            "legs_data": [{
                "symbol": symbol,
                "option_symbol": f"{symbol}_{expiration}_{strike}_{'C' if is_call else 'P'}",
                "side": "SELL",
                "strike": strike,
                "expiration": datetime.strptime(expiration, "%Y-%m-%d"),
                "option_type": "CALL" if is_call else "PUT",
                "entry_price": price
            }]
        }

    def _analyze_market_simulation(self, symbol, strategy):
        # ... (Old Code logic moved here) ...
        # Simulate pricing & Greeks
        base_price = random.uniform(100, 500)
        dte = random.randint(30, 45)
        
        # Mock Expiration
        mock_exp = datetime.now() + timedelta(days=dte)
        
        if strategy == StrategyType.CASH_SECURED_PUT:
             max_risk = base_price * 100 
             entry_credit = base_price * random.uniform(0.01, 0.03)
             strike = base_price * 0.95
             is_call = False
        else:
             width = 5.0 
             max_risk = (width * 100) * 0.8 
             entry_credit = width * 100 * 0.2 
             strike = base_price * 1.05
             is_call = True
        
        return {
            "symbol": symbol,
            "strategy": strategy,
            "entry_credit": round(entry_credit, 2),
            "max_risk": round(max_risk, 2),
            "prob_profit": random.randint(65, 85),
            "dte": dte,
            "delta_proxy": random.uniform(0.20, 0.40),
            "strike_details": f"Sim {strike:.2f}",
            "legs_data": [{
                "symbol": symbol,
                "option_symbol": f"SIM_{symbol}_{strike:.0f}",
                "side": "SELL",
                "strike": strike,
                "expiration": mock_exp,
                "option_type": "CALL" if is_call else "PUT",
                "entry_price": entry_credit / 100
            }]
        }

    def execute_ai_trade(self, trade_proposal):
        """
        Commits the trade to the database (Global Execution).
        Now saves LEGS.
        """
        from src.infrastructure.database.models import Leg # Import locally to avoid circulars
        
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
        self.session.flush() # ID generation
        
        # Save Legs
        if "legs_data" in trade_proposal:
            for leg_data in trade_proposal["legs_data"]:
                new_leg = Leg(
                    trade_id=new_trade.id,
                    option_symbol=leg_data.get("option_symbol"),
                    side=leg_data.get("side"),
                    strike=leg_data.get("strike"),
                    expiration=leg_data.get("expiration"),
                    option_type=leg_data.get("option_type"),
                    entry_price=leg_data.get("entry_price"),
                    exit_price=0.0
                )
                self.session.add(new_leg)
        
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
