"""Candlestick pattern detection.

Pure-functional pattern recognizers operating on a sequence of OHLC bars
ordered oldest -> newest. Each detector returns a `Pattern` (or None) for
the pattern that ENDS at the most recent bar; older bars are context.

Why patterns: for the LongCall/LongPut strategy we want each trade to be
backed by a textbook candlestick reading. Patterns are stronger in daily
timeframes than the raw MA cross we used initially, and they give the
trader something to read on the chart.

Reference for thresholds: Bulkowski, "Encyclopedia of Candlestick Charts".
The percentages below are conservative defaults chosen so the same
detector flags ~1-3 setups per symbol per month on liquid US equities.
"""
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence


@dataclass
class Bar:
    open: float
    high: float
    low: float
    close: float

    @property
    def body(self) -> float:
        return abs(self.close - self.open)

    @property
    def total_range(self) -> float:
        return self.high - self.low

    @property
    def is_bull(self) -> bool:
        return self.close > self.open

    @property
    def is_bear(self) -> bool:
        return self.close < self.open

    @property
    def upper_shadow(self) -> float:
        return self.high - max(self.open, self.close)

    @property
    def lower_shadow(self) -> float:
        return min(self.open, self.close) - self.low

    @property
    def midpoint(self) -> float:
        return (self.open + self.close) / 2


@dataclass
class Pattern:
    name: str          # human-readable
    bias: str          # "BULLISH" or "BEARISH"
    bars_back: int     # how many bars the pattern spans (1, 2, or 3)
    strength: int      # 1..3 (3 = strongest)
    description: str   # didactic text shown in trade rationale and chart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _avg_body(bars: Sequence[Bar], n: int = 10) -> float:
    if not bars:
        return 0.0
    last_n = bars[-n:] if len(bars) >= n else bars
    bodies = [b.body for b in last_n if b.body > 0]
    return sum(bodies) / len(bodies) if bodies else 0.0


def _trend_slope(bars: Sequence[Bar], window: int, end_offset: int) -> float:
    """Slope of closes over `window` bars ending `end_offset` bars before the
    last bar. end_offset=N excludes the last N bars from the regression — set
    it to the size of the candidate pattern so the trend is measured BEFORE
    the reversal candles, which is the textbook definition.
    """
    end = len(bars) - end_offset
    if end < window:
        return 0.0
    segment = bars[end - window:end]
    if not segment:
        return 0.0
    return segment[-1].close - segment[0].close


def _is_uptrend(bars: Sequence[Bar], window: int = 5, end_offset: int = 1) -> bool:
    return _trend_slope(bars, window, end_offset) > 0


def _is_downtrend(bars: Sequence[Bar], window: int = 5, end_offset: int = 1) -> bool:
    return _trend_slope(bars, window, end_offset) < 0


# ---------------------------------------------------------------------------
# Bullish patterns
# ---------------------------------------------------------------------------
def bullish_engulfing(bars: Sequence[Bar]) -> Optional[Pattern]:
    if len(bars) < 2:
        return None
    prev, curr = bars[-2], bars[-1]
    if not (prev.is_bear and curr.is_bull):
        return None
    if curr.body < prev.body:
        return None
    if curr.open > prev.close or curr.close < prev.open:
        return None
    if not _is_downtrend(bars, window=5, end_offset=2):
        return None
    return Pattern(
        name="Bullish Engulfing",
        bias="BULLISH",
        bars_back=2,
        strength=3,
        description=(
            "Una vela alcista cuyo cuerpo envuelve completamente al cuerpo "
            "bajista anterior, despues de un tramo bajista. Senala "
            "agotamiento vendedor y posible giro alcista."
        ),
    )


def hammer(bars: Sequence[Bar]) -> Optional[Pattern]:
    if len(bars) < 6:
        return None
    b = bars[-1]
    if b.body == 0 or b.total_range == 0:
        return None
    # Long lower shadow >= 2x body, small upper shadow <= body, body in upper third.
    if b.lower_shadow < 2 * b.body:
        return None
    if b.upper_shadow > b.body:
        return None
    if min(b.open, b.close) < b.low + 0.6 * b.total_range:
        return None
    if not _is_downtrend(bars, window=5, end_offset=1):
        return None
    return Pattern(
        name="Hammer",
        bias="BULLISH",
        bars_back=1,
        strength=2,
        description=(
            "Vela con sombra inferior larga (>=2x el cuerpo) y cuerpo "
            "pequeno en la parte superior, tras una caida. Los compradores "
            "rechazaron precios mas bajos -> posible piso."
        ),
    )


def piercing_line(bars: Sequence[Bar]) -> Optional[Pattern]:
    if len(bars) < 2:
        return None
    prev, curr = bars[-2], bars[-1]
    if not (prev.is_bear and curr.is_bull):
        return None
    if curr.open >= prev.low:
        return None
    if curr.close < prev.midpoint or curr.close >= prev.open:
        return None
    if not _is_downtrend(bars, window=5, end_offset=2):
        return None
    return Pattern(
        name="Piercing Line",
        bias="BULLISH",
        bars_back=2,
        strength=2,
        description=(
            "La vela actual abre por debajo del minimo previo y cierra "
            "encima del punto medio del cuerpo bajista anterior. Los "
            "compradores recuperaron mas de la mitad del terreno perdido."
        ),
    )


def morning_star(bars: Sequence[Bar]) -> Optional[Pattern]:
    if len(bars) < 3:
        return None
    a, b, c = bars[-3], bars[-2], bars[-1]
    avg = _avg_body(bars[:-1], n=10) or 1e-9
    if not (a.is_bear and a.body > avg):
        return None
    if b.body > 0.5 * a.body:
        return None
    if not (c.is_bull and c.close > a.midpoint):
        return None
    return Pattern(
        name="Morning Star",
        bias="BULLISH",
        bars_back=3,
        strength=3,
        description=(
            "Patron de tres velas: roja larga, indecision (cuerpo pequeno), "
            "verde larga que cierra dentro del cuerpo de la primera. Es uno "
            "de los giros alcistas mas fiables del repertorio clasico."
        ),
    )


# ---------------------------------------------------------------------------
# Bearish patterns
# ---------------------------------------------------------------------------
def bearish_engulfing(bars: Sequence[Bar]) -> Optional[Pattern]:
    if len(bars) < 2:
        return None
    prev, curr = bars[-2], bars[-1]
    if not (prev.is_bull and curr.is_bear):
        return None
    if curr.body < prev.body:
        return None
    if curr.open < prev.close or curr.close > prev.open:
        return None
    if not _is_uptrend(bars, window=5, end_offset=2):
        return None
    return Pattern(
        name="Bearish Engulfing",
        bias="BEARISH",
        bars_back=2,
        strength=3,
        description=(
            "Una vela bajista cuyo cuerpo envuelve completamente al cuerpo "
            "alcista previo tras un tramo alcista. Senala agotamiento "
            "comprador y posible giro bajista."
        ),
    )


def shooting_star(bars: Sequence[Bar]) -> Optional[Pattern]:
    if len(bars) < 6:
        return None
    b = bars[-1]
    if b.body == 0 or b.total_range == 0:
        return None
    if b.upper_shadow < 2 * b.body:
        return None
    if b.lower_shadow > b.body:
        return None
    if max(b.open, b.close) > b.high - 0.4 * b.total_range:
        # body should sit in lower third of range
        return None
    if not _is_uptrend(bars, window=5, end_offset=1):
        return None
    return Pattern(
        name="Shooting Star",
        bias="BEARISH",
        bars_back=1,
        strength=2,
        description=(
            "Vela con sombra superior larga y cuerpo pequeno en la parte "
            "baja, tras un avance. Los vendedores rechazaron precios mas "
            "altos -> posible techo."
        ),
    )


def dark_cloud_cover(bars: Sequence[Bar]) -> Optional[Pattern]:
    if len(bars) < 2:
        return None
    prev, curr = bars[-2], bars[-1]
    if not (prev.is_bull and curr.is_bear):
        return None
    if curr.open <= prev.high:
        return None
    if curr.close > prev.midpoint or curr.close <= prev.open:
        return None
    if not _is_uptrend(bars, window=5, end_offset=2):
        return None
    return Pattern(
        name="Dark Cloud Cover",
        bias="BEARISH",
        bars_back=2,
        strength=2,
        description=(
            "La vela actual abre por encima del maximo previo y cierra "
            "debajo del punto medio del cuerpo alcista anterior. Espejo "
            "bajista de la Piercing Line."
        ),
    )


def evening_star(bars: Sequence[Bar]) -> Optional[Pattern]:
    if len(bars) < 3:
        return None
    a, b, c = bars[-3], bars[-2], bars[-1]
    avg = _avg_body(bars[:-1], n=10) or 1e-9
    if not (a.is_bull and a.body > avg):
        return None
    if b.body > 0.5 * a.body:
        return None
    if not (c.is_bear and c.close < a.midpoint):
        return None
    return Pattern(
        name="Evening Star",
        bias="BEARISH",
        bars_back=3,
        strength=3,
        description=(
            "Patron de tres velas: verde larga, indecision, roja larga que "
            "cierra dentro del cuerpo de la primera. Espejo bajista de la "
            "Morning Star, muy fiable historicamente."
        ),
    )


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------
BULLISH_DETECTORS: List[Callable[[Sequence[Bar]], Optional[Pattern]]] = [
    morning_star,
    bullish_engulfing,
    piercing_line,
    hammer,
]
BEARISH_DETECTORS: List[Callable[[Sequence[Bar]], Optional[Pattern]]] = [
    evening_star,
    bearish_engulfing,
    dark_cloud_cover,
    shooting_star,
]


def detect_first(bars: Sequence[Bar], bias: str) -> Optional[Pattern]:
    """Return the strongest pattern ending at the latest bar matching bias.
    Detectors are listed strongest-first; the first match wins."""
    detectors = BULLISH_DETECTORS if bias == "BULLISH" else BEARISH_DETECTORS
    for fn in detectors:
        result = fn(bars)
        if result is not None:
            return result
    return None
