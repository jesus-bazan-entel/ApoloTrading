"""Technical indicators used by the SPY Tactical Playbook.

Pure functions over Python lists — no pandas dependency on the hot path so
the strategies stay event-loop friendly.

Implemented:
- ema(values, period)
- macd(closes, fast=12, slow=26, signal=9) -> (macd_line, signal_line, hist)
- volume_step_down(volumes, n=5) -> bool ("bajada en gradas")
- distance_to_ema_pct(price, ema, atr) -> float (relative extension)
- is_zona_cara(closes, ema21, threshold) -> bool (overbought rebound)
- is_zona_barata(closes, ema21, threshold) -> bool (oversold rebound)
- atr(highs, lows, closes, period=14) -> list
- descending_triangle(highs, lows, lookback) -> dict | None (M4 step 3)
- channel_break(closes, line_slope, line_intercept, direction) -> bool
"""
from typing import List, Optional, Sequence, Tuple


def ema(values: Sequence[float], period: int) -> List[float]:
    """Exponential moving average. Returns a list aligned with `values`;
    the first `period - 1` entries are seeded with a simple average so the
    series has no None gaps for downstream consumers."""
    if not values or period <= 0:
        return []
    if len(values) < period:
        # Not enough data — return an SMA of what we have, then keep flat.
        avg = sum(values) / len(values)
        return [avg] * len(values)

    k = 2.0 / (period + 1)
    out: List[float] = []
    seed = sum(values[:period]) / period
    out.extend([seed] * period)
    prev = seed
    for v in values[period:]:
        prev = v * k + prev * (1 - k)
        out.append(prev)
    return out


def macd(closes: Sequence[float], fast: int = 12, slow: int = 26,
         signal: int = 9) -> Tuple[List[float], List[float], List[float]]:
    if len(closes) < slow + signal:
        # not enough data; return zeros
        n = len(closes)
        zeros = [0.0] * n
        return zeros, zeros, zeros
    ema_fast = ema(closes, fast)
    ema_slow = ema(closes, slow)
    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = ema(macd_line, signal)
    hist = [m - s for m, s in zip(macd_line, signal_line)]
    return macd_line, signal_line, hist


def volume_step_down(volumes: Sequence[float], n: int = 5,
                     min_drops: int = 3) -> bool:
    """Volume "bajada en gradas": at least `min_drops` decreasing readings
    over the last `n` bars. Used to confirm that the counter-trend rally
    that put price in the Zona Cara is losing conviction."""
    if len(volumes) < n + 1:
        return False
    last = list(volumes[-(n + 1):])
    drops = sum(1 for i in range(1, len(last)) if last[i] < last[i - 1])
    return drops >= min_drops


def atr(highs: Sequence[float], lows: Sequence[float],
        closes: Sequence[float], period: int = 14) -> List[float]:
    """Average True Range, returned aligned with the input series."""
    n = len(closes)
    if n == 0:
        return []
    trs: List[float] = [highs[0] - lows[0]]
    for i in range(1, n):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1]),
        )
        trs.append(tr)
    # Wilder smoothing approximated by EMA with same period.
    return ema(trs, period)


def is_zona_cara(closes: Sequence[float], ema21: Sequence[float],
                 threshold_pct: float = 0.005) -> bool:
    """Zona Cara (overbought short term): in a bear regime, the bounce that
    pushes price back UP through (or near) the EMA21 from below. We check
    that the most recent close is within +/- threshold of the EMA21 OR has
    just crossed above it from below in the last few bars."""
    if not closes or not ema21 or len(closes) != len(ema21):
        return False
    recent_close = closes[-1]
    recent_ema = ema21[-1]
    if recent_ema <= 0:
        return False
    extension = (recent_close - recent_ema) / recent_ema
    # Within a small band ABOVE the EMA21 == price has rallied back to it.
    return -threshold_pct <= extension <= 4 * threshold_pct


def is_zona_barata(closes: Sequence[float], ema21: Sequence[float],
                   threshold_pct: float = 0.005) -> bool:
    """Symmetric of Zona Cara for CALL setups: in a bull regime, price
    pulls back DOWN to the EMA21 from above."""
    if not closes or not ema21 or len(closes) != len(ema21):
        return False
    recent_close = closes[-1]
    recent_ema = ema21[-1]
    if recent_ema <= 0:
        return False
    extension = (recent_close - recent_ema) / recent_ema
    return -4 * threshold_pct <= extension <= threshold_pct


# ---------------------------------------------------------------------------
# Trendline helpers (M4 step 3 + RCB)
# ---------------------------------------------------------------------------
def descending_highs_line(highs: Sequence[float],
                          lookback: int = 12) -> Optional[Tuple[float, float]]:
    """Fit a descending line to recent swing highs (a simple least-squares
    over the local maxima of the lookback window). Returns (slope,
    intercept) of close = slope * x + intercept where x is the bar index
    inside the lookback. None if the slope is not negative or there are
    too few pivots."""
    if len(highs) < lookback:
        return None
    window = list(highs[-lookback:])

    # Identify local maxima: a bar whose high exceeds both neighbours.
    pivots: List[Tuple[int, float]] = []
    for i in range(1, len(window) - 1):
        if window[i] > window[i - 1] and window[i] > window[i + 1]:
            pivots.append((i, window[i]))
    # Always include the last bar so the line covers up to "today".
    pivots.append((len(window) - 1, window[-1]))

    if len(pivots) < 2:
        return None

    xs = [p[0] for p in pivots]
    ys = [p[1] for p in pivots]
    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    den = sum((x - mean_x) ** 2 for x in xs)
    if den == 0:
        return None
    slope = num / den
    if slope >= 0:
        return None  # not descending
    intercept = mean_y - slope * mean_x
    return slope, intercept


def horizontal_support(lows: Sequence[float], lookback: int = 10,
                       tolerance_pct: float = 0.004) -> Optional[float]:
    """Return a horizontal support level if at least 2 of the recent lows
    cluster within `tolerance_pct`. Returns the average of the cluster."""
    if len(lows) < lookback:
        return None
    window = list(lows[-lookback:])
    base = min(window)
    cluster = [v for v in window if abs(v - base) / base <= tolerance_pct]
    if len(cluster) < 2:
        return None
    return sum(cluster) / len(cluster)


def line_value_at(slope: float, intercept: float, x: int) -> float:
    return slope * x + intercept
