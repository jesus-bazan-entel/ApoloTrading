"""Real-time(ish) market data feed.

Polls yfinance for spot price (and once per N polls for IV rank) and
publishes events on the bus:

- MARKET_DATA: every poll cycle. Used by ExitManager to monitor open
  positions intraday (stop-loss / profit-target on the next 15 minutes
  rather than waiting for the close).
- DAILY_BAR: once per calendar day per symbol, on the first poll of a
  new trading day. Carries the full prior-day OHLC and a 30-bar history
  so candlestick-pattern strategies can run.
"""
import logging
import time
from datetime import date
from typing import Dict, List, Optional

from src.infrastructure.event_bus import Event, EventBus, EventType
from src.infrastructure.market_data.client import MarketDataClient

logger = logging.getLogger("LiveDataFeed")


class LiveDataFeed:
    def __init__(
        self,
        event_bus: EventBus,
        symbols: List[str],
        poll_seconds: float = 900.0,   # 15 min default for intraday exits
        iv_refresh_every: int = 20,
        client: Optional[MarketDataClient] = None,
    ):
        self.bus = event_bus
        self.symbols = symbols
        self.poll_seconds = poll_seconds
        self.iv_refresh_every = iv_refresh_every
        self.client = client or MarketDataClient()

        self._iv_cache: Dict[str, float] = {}
        self._last_daily_bar: Dict[str, date] = {}
        self._tick_count = 0
        self._stop = False

    def stop(self):
        self._stop = True

    # ------------------------------------------------------------------
    def _fetch_daily_history(self, symbol: str, bars: int = 80) -> List[dict]:
        """Pull the last `bars` daily OHLC+Volume rows from yfinance.
        Default 80 bars so EMA50 and MACD have enough warmup."""
        try:
            import yfinance as yf
            hist = yf.Ticker(symbol).history(period=f"{bars + 10}d", interval="1d")
            if hist is None or hist.empty:
                return []
            hist = hist.tail(bars)
            return [
                {
                    "timestamp": idx.to_pydatetime(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": float(row.get("Volume") or 0.0),
                }
                for idx, row in hist.iterrows()
            ]
        except Exception as e:
            logger.warning(f"Could not fetch daily history for {symbol}: {e}")
            return []

    # ------------------------------------------------------------------
    def run(self, max_ticks: Optional[int] = None):
        """Block and stream. Set max_ticks for finite runs (e.g. tests)."""
        logger.info(f"LiveDataFeed starting for {self.symbols} "
                    f"every {self.poll_seconds}s")
        while not self._stop:
            self._tick_count += 1
            today = date.today()
            for sym in self.symbols:
                price = self.client.get_current_price(sym)
                if price <= 0:
                    logger.warning(f"Skipping {sym}: no price available")
                    continue

                if (sym not in self._iv_cache
                        or self._tick_count % self.iv_refresh_every == 1):
                    self._iv_cache[sym] = self.client.get_iv_rank(sym)

                payload = {
                    "symbol": sym,
                    "price": price,
                    "iv_rank": self._iv_cache[sym],
                }

                # Always publish the intraday tick for the ExitManager.
                self.bus.publish(Event(EventType.MARKET_DATA, payload))

                # On the first poll of a new trading day, re-fetch daily
                # OHLC and emit a DAILY_BAR. The 30-bar history is enough
                # context for our 3-bar-max patterns.
                if self._last_daily_bar.get(sym) != today:
                    self._last_daily_bar[sym] = today
                    history = self._fetch_daily_history(sym, bars=80)
                    if history:
                        last = history[-1]
                        daily_payload = {
                            **payload,
                            "open": last["open"],
                            "high": last["high"],
                            "low": last["low"],
                            "close": last["close"],
                            "volume": last.get("volume", 0.0),
                            "ohlc_history": history,
                        }
                        self.bus.publish(Event(EventType.DAILY_BAR, daily_payload))

            if max_ticks is not None and self._tick_count >= max_ticks:
                break
            time.sleep(self.poll_seconds)
        logger.info("LiveDataFeed stopped")
