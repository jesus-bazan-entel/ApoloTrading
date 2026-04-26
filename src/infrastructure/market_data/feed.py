"""Real-time(ish) market data feed.

Polls yfinance for spot price (and once per N polls for IV rank), then
publishes MARKET_DATA events on the bus. Designed to drop in where the
simulated tick loop lived in main.py.
"""
import logging
import time
from typing import Dict, List, Optional

from src.infrastructure.event_bus import Event, EventBus, EventType
from src.infrastructure.market_data.client import MarketDataClient

logger = logging.getLogger("LiveDataFeed")


class LiveDataFeed:
    def __init__(
        self,
        event_bus: EventBus,
        symbols: List[str],
        poll_seconds: float = 30.0,
        iv_refresh_every: int = 20,
        client: Optional[MarketDataClient] = None,
    ):
        self.bus = event_bus
        self.symbols = symbols
        self.poll_seconds = poll_seconds
        self.iv_refresh_every = iv_refresh_every
        self.client = client or MarketDataClient()

        self._iv_cache: Dict[str, float] = {}
        self._tick_count = 0
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self, max_ticks: Optional[int] = None):
        """Block and stream. Set max_ticks for finite runs (e.g. tests)."""
        logger.info(f"LiveDataFeed starting for {self.symbols} "
                    f"every {self.poll_seconds}s")
        while not self._stop:
            self._tick_count += 1
            for sym in self.symbols:
                price = self.client.get_current_price(sym)
                if price <= 0:
                    logger.warning(f"Skipping {sym}: no price available")
                    continue

                if (sym not in self._iv_cache
                        or self._tick_count % self.iv_refresh_every == 1):
                    self._iv_cache[sym] = self.client.get_iv_rank(sym)

                self.bus.publish(Event(EventType.MARKET_DATA, {
                    "symbol": sym,
                    "price": price,
                    "iv_rank": self._iv_cache[sym],
                }))

            if max_ticks is not None and self._tick_count >= max_ticks:
                break
            time.sleep(self.poll_seconds)
        logger.info("LiveDataFeed stopped")
