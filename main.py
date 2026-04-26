import time

from src.config import config
from src.infrastructure.database.models import db
from src.infrastructure.event_bus import Event, EventBus, EventType
from src.infrastructure.execution import ExecutionEngine
from src.risk.manager import RiskManager
from src.strategies.options_strategies import LongCallStrategy, LongPutStrategy


def _run_simulation(bus: EventBus):
    """Synthetic tick loop. Used for offline development / smoke tests."""
    symbols = ["XLF", "SOFI", "F"]
    prices = {"XLF": 45.0, "SOFI": 12.0, "F": 11.0}
    drift = {"XLF": 1, "SOFI": -1, "F": 1}  # +1 up, -1 down

    for i in range(20):
        print(f"\n--- Tick {i} ---")
        for sym in symbols:
            noise = (time.time() % 1) - 0.5
            prices[sym] += drift[sym] * 0.05 + noise * 0.02
            bus.publish(Event(EventType.MARKET_DATA, {
                "symbol": sym,
                "price": prices[sym],
                "iv_rank": 25 + (i % 10),
                "adx": 22,
            }))
        time.sleep(0.2)


def _run_live_data(bus: EventBus):
    """Poll yfinance for real prices and IV rank, publish to the bus."""
    from src.infrastructure.market_data.feed import LiveDataFeed
    feed = LiveDataFeed(
        bus,
        symbols=config.LIVE_SYMBOLS,
        poll_seconds=config.LIVE_POLL_SECONDS,
    )
    try:
        feed.run(max_ticks=config.LIVE_MAX_TICKS or None)
    except KeyboardInterrupt:
        feed.stop()


def main():
    print("Initializing Apolo Trading System (TradeMind AI)...")
    print(f"Mode: {config.MODE} | Broker: {config.BROKER} | "
          f"Equity: ${config.INITIAL_EQUITY:,.2f} | "
          f"Risk/trade NORMAL: {config.RISK_PCT_NORMAL:.1%}")

    bus = EventBus()
    db_session = db.get_session()

    risk_manager = RiskManager(bus, db_session)
    from src.domain.exit_manager import ExitManager
    from src.domain.portfolio import PortfolioManager
    from src.infrastructure.market_data.client import MarketDataClient

    portfolio_manager = PortfolioManager(bus, db_session)

    market_data_client = MarketDataClient() if config.MODE == "LIVE_DATA" else None
    exit_manager = ExitManager(bus, market_data_client=market_data_client)

    execution = ExecutionEngine(bus)

    long_call = LongCallStrategy(bus, market_data_client=market_data_client)
    long_put = LongPutStrategy(bus, market_data_client=market_data_client)

    print("System Online.")
    try:
        if config.MODE == "LIVE_DATA":
            _run_live_data(bus)
        else:
            _run_simulation(bus)
    except KeyboardInterrupt:
        print("Shutdown requested.")

    print("Run Complete.")


if __name__ == "__main__":
    main()
