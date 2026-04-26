"""SPY Tactical Playbook strategies.

Implements the Alta Prioridad setups:
- M4  : Modelo de 4 Pasos (PUT)  — bear regime + Zona Cara + descending
        triangle + breakdown candle.
- RCB : Ruptura de Canal Bajista (CALL) — descending channel breakout
        with MACD turning bullish.

Differences vs the legacy LongCall/LongPut strategies:
- Underlying is SPY (single-symbol focus, can be widened via SPY_SYMBOLS).
- Strike: ATM (target delta ~0.50).
- Expiration: short (1-7 DTE) — the playbook recommends ~2 days.
- Exit bracket: +/- 10% of the fill price (carried in the signal as
  `bracket_pct`; ExitManager honours it instead of its global defaults).
"""
from collections import defaultdict
from typing import Dict, List, Optional

from src.infrastructure.event_bus import Event, EventBus, EventType
from src.strategies.candlestick import Bar
from src.strategies.indicators import (
    descending_highs_line,
    ema,
    horizontal_support,
    is_zona_barata,
    is_zona_cara,
    line_value_at,
    macd,
    volume_step_down,
)
from src.strategies.options_strategies import Strategy


class _SPYPlaybookStrategy(Strategy):
    """Shared mechanics for the playbook strategies.

    Each subclass decides whether the latest DAILY_BAR meets its setup.
    When it does, this base class builds the signal with ATM strike,
    short DTE, and a bracket_pct so the ExitManager applies the +/- 10%
    rule the playbook prescribes.
    """

    # Overridden by subclasses
    OPTION_TYPE: str = "CALL"
    BIAS: str = "BULLISH"
    SETUP_NAME: str = ""           # e.g. "M4", "RCB"
    SETUP_DESCRIPTION: str = ""

    # Strike & expiration (playbook defaults)
    TARGET_DELTA: float = 0.50     # ATM
    MIN_DTE: int = 1
    MAX_DTE: int = 7

    # Heuristic fallback when no chain available
    OTM_PCT: float = 0.0           # ATM = no offset
    PREMIUM_PCT: float = 0.018     # short-DTE ATM is ~1.5-2% of spot

    # Filters
    MAX_IV_RANK: float = 70.0      # short DTE tolerates higher IV
    SYMBOLS = ("SPY",)             # default focus

    # Bracket exit per playbook
    BRACKET_PCT: float = 0.10

    # Indicator periods
    EMA_FAST: int = 8
    EMA_SLOW: int = 21
    EMA_TREND: int = 50

    # Cooldown between signals on the same symbol
    COOLDOWN_BARS: int = 3

    def __init__(self, name: str, event_bus: EventBus,
                 market_data_client=None, symbols: Optional[List[str]] = None):
        super().__init__(name, event_bus)
        self.symbols = tuple(symbols) if symbols else self.SYMBOLS
        self._cooldown: Dict[str, int] = defaultdict(int)
        self.market_data = market_data_client
        self.bus.subscribe(EventType.DAILY_BAR, self.on_market_data)

    # ------------------------------------------------------------------
    # Setup detection — overridden by subclasses
    # ------------------------------------------------------------------
    def _detect_setup(self, bars: List[Bar], volumes: List[float],
                      ema8: List[float], ema21: List[float], ema50: List[float],
                      macd_hist: List[float]) -> Optional[dict]:
        """Return a dict with rationale + extra fields if the setup fires,
        None otherwise. Subclasses implement."""
        raise NotImplementedError

    # ------------------------------------------------------------------
    @staticmethod
    def _bars_from_history(history: List[dict]) -> List[Bar]:
        return [Bar(open=h["open"], high=h["high"],
                    low=h["low"], close=h["close"]) for h in history]

    @staticmethod
    def _volumes_from_history(history: List[dict]) -> List[float]:
        return [float(h.get("volume") or 0.0) for h in history]

    # ------------------------------------------------------------------
    def _build_signal_from_chain(self, symbol: str) -> Optional[dict]:
        if self.market_data is None:
            return None
        opt_type = "call" if self.OPTION_TYPE == "CALL" else "put"
        contract = self.market_data.find_option_by_delta(
            symbol,
            option_type=opt_type,
            target_delta=self.TARGET_DELTA,
            min_dte=self.MIN_DTE,
            max_dte=self.MAX_DTE,
        )
        if not contract:
            return None
        return {
            "strike": contract["strike"],
            "premium": contract["premium"],
            "expiration": contract["expiration"],
            "delta": contract["delta"],
            "dte": contract["dte"],
            "iv": contract["iv"],
            "source": "chain",
        }

    def _build_signal_heuristic(self, symbol: str, price: float) -> dict:
        # ATM: strike == spot rounded to nearest dollar (or half dollar for SPY)
        strike = round(price * 2) / 2 if price >= 50 else round(price, 2)
        # Short-DTE ATM premium estimate
        premium = round(price * self.PREMIUM_PCT, 2)
        return {
            "strike": strike,
            "premium": premium,
            "expiration": None,
            "delta": None,
            "dte": None,
            "iv": None,
            "source": "heuristic",
        }

    # ------------------------------------------------------------------
    def evaluate(self, data: dict) -> Optional[dict]:
        symbol = data.get("symbol")
        if symbol not in self.symbols:
            return None
        history = data.get("ohlc_history") or []
        price = data.get("price")
        if not symbol or price is None or len(history) < self.EMA_TREND + 5:
            return None

        if self._cooldown[symbol] > 0:
            self._cooldown[symbol] -= 1
            return None

        iv_rank = data.get("iv_rank", 0)
        if iv_rank > self.MAX_IV_RANK:
            return None

        bars = self._bars_from_history(history)
        volumes = self._volumes_from_history(history)
        closes = [b.close for b in bars]

        ema8 = ema(closes, self.EMA_FAST)
        ema21 = ema(closes, self.EMA_SLOW)
        ema50 = ema(closes, self.EMA_TREND)
        _macd_line, _signal_line, hist = macd(closes)

        setup = self._detect_setup(bars, volumes, ema8, ema21, ema50, hist)
        if setup is None:
            return None

        contract = (self._build_signal_from_chain(symbol)
                    or self._build_signal_heuristic(symbol, price))

        risk_per_unit = round(contract["premium"] * 100, 2)
        self._cooldown[symbol] = self.COOLDOWN_BARS

        rationale = setup.get("rationale", self.SETUP_DESCRIPTION)

        return {
            "strategy": "LONG_CALL" if self.OPTION_TYPE == "CALL" else "LONG_PUT",
            "symbol": symbol,
            "side": "BUY",
            "legs": [{
                "side": "BUY",
                "type": self.OPTION_TYPE,
                "strike": contract["strike"],
                "expiration": contract["expiration"],
                "iv": contract["iv"],
                "delta": contract["delta"],
            }],
            "limit_price": contract["premium"],
            "risk_per_unit": risk_per_unit,
            "dte": contract["dte"],
            "source": contract["source"],
            "pattern_name": self.SETUP_NAME,
            "pattern_strength": setup.get("strength", 3),
            "pattern_bars_back": setup.get("bars_back", 5),
            "rationale": rationale,
            "ohlc_history": list(history),
            "spot_at_entry": price,
            # Playbook bracket: +/-10% of premium, picked up by ExitManager.
            "bracket_pct": self.BRACKET_PCT,
            # Optional overlays for the chart annotation.
            "overlays": setup.get("overlays"),
        }

    def on_market_data(self, event: Event):
        signal = self.evaluate(event.data)
        if signal:
            self.bus.publish(Event(EventType.SIGNAL, signal))


# =============================================================================
# M4 — Modelo de 4 Pasos (PUT)
# =============================================================================
class M4Strategy(_SPYPlaybookStrategy):
    """M4 — Modelo de 4 Pasos (PUT).

    1. Canal Bajista: close < EMA50 AND EMA8 < EMA21.
    2. Zona Cara: price has rallied back to (or just above) EMA21 from below.
    3. Trazado Base: a descending-highs trendline + a horizontal support
       cluster (the descending triangle).
    4. Ruptura del Piso: today's bar is RED and closes BELOW the support.

    Confirmations: MACD histogram negative or rolling lower; volume on the
    counter-trend rally was decreasing ("bajada en gradas").
    """

    OPTION_TYPE = "PUT"
    BIAS = "BEARISH"
    SETUP_NAME = "M4 Modelo de 4 Pasos"
    SETUP_DESCRIPTION = (
        "Canal bajista (precio bajo EMA50, EMA8<EMA21), retroceso a Zona "
        "Cara, triangulo descendente formado y vela roja rompe el soporte. "
        "MACD bajista y volumen del rally decreciente confirman."
    )

    def __init__(self, event_bus, market_data_client=None, symbols=None):
        super().__init__("M4", event_bus, market_data_client, symbols)

    def _detect_setup(self, bars, volumes, ema8, ema21, ema50, macd_hist):
        if len(bars) < 30:
            return None

        last = bars[-1]
        # Step 1: Canal Bajista
        if not (last.close < ema50[-1] and ema8[-1] < ema21[-1]):
            return None

        closes = [b.close for b in bars]
        highs = [b.high for b in bars]
        lows = [b.low for b in bars]

        # Step 2: Zona Cara — price recently retraced toward EMA21 from below.
        # Look at the previous 1-3 bars (the rally), not necessarily today.
        zona_cara_recent = any(
            is_zona_cara(closes[: -k] if k > 0 else closes,
                         ema21[: -k] if k > 0 else ema21,
                         threshold_pct=0.006)
            for k in (0, 1, 2)
        )
        if not zona_cara_recent:
            return None

        # Step 3: Descending triangle = descending highs + horizontal support.
        line = descending_highs_line(highs, lookback=15)
        support = horizontal_support(lows, lookback=12, tolerance_pct=0.005)
        if line is None or support is None:
            return None
        slope, intercept = line

        # Step 4: today's bar must be red AND close below support.
        if not last.is_bear:
            return None
        if last.close > support * 1.001:  # tiny buffer for noise
            return None

        # Confirmations
        macd_bearish = macd_hist[-1] < 0 or (
            len(macd_hist) >= 2 and macd_hist[-1] < macd_hist[-2])
        rally_volume_fading = volume_step_down(volumes, n=5, min_drops=3)

        rationale = (
            f"M4 disparado: canal bajista activo, ultima orbita en Zona Cara "
            f"sobre EMA21, triangulo descendente con soporte ~{support:.2f}, "
            f"vela roja de hoy cerro en {last.close:.2f} "
            f"(rompiendo el piso). "
            f"MACD {'bajista' if macd_bearish else 'plano'}, "
            f"volumen del rally {'decreciente' if rally_volume_fading else 'mixto'}."
        )

        return {
            "rationale": rationale,
            "bars_back": 1,
            "strength": 3 if macd_bearish and rally_volume_fading else 2,
            "overlays": {
                "trendline": {
                    "kind": "descending",
                    "slope": slope,
                    "intercept": intercept,
                    "lookback": 15,
                },
                "support": support,
            },
        }


# =============================================================================
# RCB — Ruptura de Canal Bajista (CALL)
# =============================================================================
class RCBStrategy(_SPYPlaybookStrategy):
    """RCB — Ruptura de Canal Bajista (CALL).

    1. Prior Canal Bajista: there is a descending highs line over the
       lookback (the channel that we are about to break).
    2. Zona Barata: price had pulled back to / under EMA21 in the past
       few bars (short-term oversold).
    3. Ruptura: today's bar is GREEN and closes ABOVE the descending
       trendline value at "today" (breakout).
    4. Confirmation: MACD histogram crossing up (was negative, now >= 0
       OR rising for 2 bars).
    """

    OPTION_TYPE = "CALL"
    BIAS = "BULLISH"
    SETUP_NAME = "RCB Ruptura de Canal Bajista"
    SETUP_DESCRIPTION = (
        "Canal bajista previo definido por linea de maximos descendentes. "
        "Vela verde de hoy cierra por encima de la linea, despues de un "
        "retroceso al EMA21 (Zona Barata). MACD cruzando al alza confirma."
    )

    def __init__(self, event_bus, market_data_client=None, symbols=None):
        super().__init__("RCB", event_bus, market_data_client, symbols)

    def _detect_setup(self, bars, volumes, ema8, ema21, ema50, macd_hist):
        if len(bars) < 25:
            return None

        last = bars[-1]
        if not last.is_bull:
            return None

        highs = [b.high for b in bars]
        closes = [b.close for b in bars]

        # Step 1+2: descending channel that was respected recently
        line = descending_highs_line(highs, lookback=15)
        if line is None:
            return None
        slope, intercept = line

        # Position 14 within the lookback == today's bar (lookback=15, idx 0..14)
        line_today = line_value_at(slope, intercept, 14)

        # Zona Barata in the prior few bars (price had pulled back to EMA21)
        zona_barata_recent = any(
            is_zona_barata(closes[: -k] if k > 0 else closes,
                           ema21[: -k] if k > 0 else ema21,
                           threshold_pct=0.006)
            for k in (1, 2, 3)
        )
        if not zona_barata_recent:
            return None

        # Step 3: breakout above the descending line
        if last.close <= line_today:
            return None

        # Step 4: MACD turning bullish
        macd_turning_up = (macd_hist[-1] > macd_hist[-2]
                           if len(macd_hist) >= 2 else False)
        macd_now_positive = macd_hist[-1] > 0
        if not (macd_turning_up or macd_now_positive):
            return None

        rationale = (
            f"RCB disparado: vela verde rompe al alza la linea descendente "
            f"(valor en hoy ~{line_today:.2f}), tras retroceso reciente a "
            f"EMA21 (Zona Barata). MACD "
            f"{'positivo' if macd_now_positive else 'subiendo'}."
        )

        return {
            "rationale": rationale,
            "bars_back": 1,
            "strength": 3 if (macd_now_positive and macd_turning_up) else 2,
            "overlays": {
                "trendline": {
                    "kind": "descending",
                    "slope": slope,
                    "intercept": intercept,
                    "lookback": 15,
                },
            },
        }
