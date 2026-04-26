import time

from src.config import config
from src.infrastructure.database.models import db
from src.infrastructure.event_bus import Event, EventBus, EventType
from src.infrastructure.execution import ExecutionEngine
from src.risk.manager import RiskManager
from src.strategies.options_strategies import LongCallStrategy, LongPutStrategy


def _run_simulation(bus: EventBus):
    """Synthetic tick loop. Used for offline development / smoke tests.

    Builds plausible OHLC bars by simulating intra-bar high/low spread,
    so candlestick-pattern strategies have something to recognize. Bar 16
    on each symbol is a deliberately engineered Bullish/Bearish Engulfing
    so the demo always fires at least one pattern entry.
    """
    from datetime import datetime, timedelta
    symbols = ["XLF", "SOFI", "F"]
    prices = {"XLF": 45.0, "SOFI": 12.0, "F": 11.0}
    drift = {"XLF": 1, "SOFI": -1, "F": 1}  # +1 up, -1 down for engulfing forge
    history = {sym: [] for sym in symbols}
    base_date = datetime.now() - timedelta(days=20)

    for i in range(20):
        print(f"\n--- Tick {i} ---")
        for sym in symbols:
            noise = (time.time() % 1) - 0.5
            d = drift[sym]
            prev_close = prices[sym]

            if i == 15:
                # Trend continuation candle (small body in trend direction)
                # so tick 16 can engulf it as a textbook reversal.
                close = prev_close + d * 0.10
                open_ = prev_close - d * 0.02
            elif i == 16:
                # Reversal engulfing: gap further in trend direction on open,
                # then close past prior bar's open in the opposite direction.
                last = history[sym][-1]
                open_ = last["close"] + d * 0.05
                close = last["open"] - d * 0.40
            else:
                close = prev_close + d * 0.05 + noise * 0.02
                open_ = prev_close + noise * 0.01

            high = max(open_, close) + abs(noise) * 0.05 + 0.02
            low = min(open_, close) - abs(noise) * 0.05 - 0.02
            prices[sym] = close

            bar = {
                "timestamp": base_date + timedelta(days=i),
                "open": open_, "high": high, "low": low, "close": close,
            }
            history[sym].append(bar)
            history[sym] = history[sym][-30:]

            payload = {
                "symbol": sym,
                "price": close,
                "iv_rank": 25 + (i % 10),
                "open": open_, "high": high, "low": low, "close": close,
                "ohlc_history": list(history[sym]),
            }
            bus.publish(Event(EventType.MARKET_DATA, payload))
            bus.publish(Event(EventType.DAILY_BAR, payload))
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
