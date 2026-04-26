import time
from src.config import config
from src.infrastructure.event_bus import EventBus, Event, EventType
from src.infrastructure.database.models import db
from src.risk.manager import RiskManager
from src.strategies.options_strategies import LongCallStrategy, LongPutStrategy
from src.infrastructure.execution import ExecutionEngine


def main():
    print("Initializing Apolo Trading System (TradeMind AI)...")
    print(f"Starting equity: ${config.INITIAL_EQUITY:,.2f} | "
          f"Risk/trade NORMAL: {config.RISK_PCT_NORMAL:.1%} | "
          f"DEFENSIVE: {config.RISK_PCT_DEFENSIVE:.1%}")

    # 1. Infrastructure
    bus = EventBus()
    db_session = db.get_session()

    # 2. Modules
    risk_manager = RiskManager(bus, db_session)
    from src.domain.portfolio import PortfolioManager
    portfolio_manager = PortfolioManager(bus, db_session)

    execution = ExecutionEngine(bus, mode="PAPER")

    # 3. Strategies: simple debit trades (long calls / long puts)
    long_call = LongCallStrategy(bus)
    long_put = LongPutStrategy(bus)

    print("System Online. Streaming simulated market data...")

    # 4. Simulation Loop. Cheap, liquid underlyings whose option premiums fit
    # a small account ($2k starting equity). Each symbol drifts in one
    # direction so the momentum filter has something to confirm: XLF/F up
    # (calls), SOFI down (puts).
    try:
        symbols = ["XLF", "SOFI", "F"]
        prices = {"XLF": 45.0, "SOFI": 12.0, "F": 11.0}
        drift = {"XLF": 1, "SOFI": -1, "F": 1}  # +1 up, -1 down

        for i in range(20):
            print(f"\n--- Tick {i} ---")
            for sym in symbols:
                noise = (time.time() % 1) - 0.5
                prices[sym] += drift[sym] * 0.05 + noise * 0.02

                event = Event(EventType.MARKET_DATA, {
                    "symbol": sym,
                    "price": prices[sym],
                    # Long options prefer modest IV (cheaper premium)
                    "iv_rank": 25 + (i % 10),
                    "adx": 22,
                })
                bus.publish(event)

            time.sleep(0.2)

    except KeyboardInterrupt:
        print("Shutdown requested.")

    print("Simulation Complete.")


if __name__ == "__main__":
    main()
