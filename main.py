import time
import threading
from src.infrastructure.event_bus import EventBus, Event, EventType
from src.infrastructure.database.models import db
from src.risk.manager import RiskManager
from src.strategies.options_strategies import BullPutSpreadStrategy, IronCondorStrategy
from src.infrastructure.execution import ExecutionEngine
from src.infrastructure.database.models import AccountState, RiskState

def main():
    print("Initializing Apolo Trading System (TradeMind AI)...")
    
    # 1. Infrastructure
    bus = EventBus()
    db_session = db.get_session()
    
    # 2. Modules
    risk_manager = RiskManager(bus, db_session)
    # Initialize Portfolio Manager to handle persistence
    from src.domain.portfolio import PortfolioManager
    portfolio_manager = PortfolioManager(bus, db_session)
    
    execution = ExecutionEngine(bus, mode="PAPER")
    
    # 3. Strategies
    bull_put = BullPutSpreadStrategy(bus)
    iron_condor = IronCondorStrategy(bus)
    
    print("System Online. Waiting for Market Data...")
    
    # 4. Simulation Loop (Replace with Real Data Feed in Live)
    # Simulating a market day
    try:
        symbols = ["SPY", "QQQ", "IWM"]
        prices = {"SPY": 450.0, "QQQ": 380.0, "IWM": 190.0}
        
        # Generate enough ticks to populate charts
        for i in range(20):
            print(f"\n--- Tick {i} ---")
            for sym in symbols:
                # Fluctuate price slightly
                prices[sym] += (0.5 - (time.time() % 1)) 
                
                event = Event(EventType.MARKET_DATA, {
                    "symbol": sym,
                    "price": prices[sym],
                    "iv_rank": 35 + i, # Simulating increasing IV to trigger entries
                    "adx": 15 # Low ADX for Condor
                })
                bus.publish(event)
            
            # Shorter sleep for faster data gen
            time.sleep(0.2)
            
    except KeyboardInterrupt:
        print("Shutdown requested.")
    
    print("Simulation Complete.")

if __name__ == "__main__":
    main()
