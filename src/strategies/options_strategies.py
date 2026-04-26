from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Optional

from src.infrastructure.event_bus import Event, EventBus, EventType
from src.strategies.candlestick import Bar, Pattern, detect_first

class Strategy:
    def __init__(self, name: str, event_bus: EventBus):
        self.name = name
        self.bus = event_bus

    def on_market_data(self, event: Event):
        raise NotImplementedError

class BullPutSpreadStrategy(Strategy):
    """
    Bull Put Spread:
    - Thesis: Neutral to Bullish.
    - Setup: Sell Put (Strike A), Buy Put (Strike B). A > B.
    - Rules: IV Rank > 30, Delta Short ~0.30, PoP > 70%.
    """
    def __init__(self, event_bus: EventBus):
        super().__init__("BullPutSpread", event_bus)
        self.bus.subscribe(EventType.MARKET_DATA, self.on_market_data)

    def evaluate(self, data: dict) -> Optional[dict]:
        # Placeholder for complex Option Chain Analysis
        # In a real system, 'data' would contain the full chain.
        
        current_price = data.get('price')
        iv_rank = data.get('iv_rank', 0) # Assumed pre-calculated or passed
        
        if iv_rank < 30:
            return None
            
        # Mock finding strikes
        short_put_strike = current_price * 0.95 # ~30 Delta proxy
        long_put_strike = current_price * 0.90
        
        credit = 1.50 # Mock credit
        width = short_put_strike - long_put_strike
        max_risk = width - credit
        
        # Return Signal Data structure
        return {
            "strategy": "BULL_PUT_SPREAD",
            "symbol": data.get('symbol'),
            "side": "SELL", # We are selling the spread (receiving credit)
            "legs": [
                {"side": "SELL", "type": "PUT", "strike": short_put_strike},
                {"side": "BUY",  "type": "PUT", "strike": long_put_strike}
            ],
            "limit_price": credit,
            "risk_per_unit": max_risk * 100 # Multiplier
        }

    def on_market_data(self, event: Event):
        signal = self.evaluate(event.data)
        if signal:
            self.bus.publish(Event(EventType.SIGNAL, signal))

class IronCondorStrategy(Strategy):
    """
    Iron Condor:
    - Thesis: Neutral.
    - Setup: Bull Put Spread + Bear Call Spread.
    - Rules: Low Trend (ADX < 20), High IV.
    """
    def __init__(self, event_bus: EventBus):
        super().__init__("IronCondor", event_bus)
        self.bus.subscribe(EventType.MARKET_DATA, self.on_market_data)

    def on_market_data(self, event: Event):
        data = event.data
        adx = data.get('adx', 25) # Mock indicator
        
        if adx > 20: 
            return # Market is trending, avoid Condor
        
        # Signal Generation similar to Bull Put but with 4 legs
        signal = {
            "strategy": "IRON_CONDOR",
            "symbol": data.get('symbol'),
            "side": "SELL",
            "risk_per_unit": 200.0, # Placeholder
            "limit_price": 3.00
        }
        self.bus.publish(Event(EventType.SIGNAL, signal))

class CashSecuredPutStrategy(Strategy):
    """
    Cash Secured Put (CSP):
    - Objective: Income Generation / Acquisition.
    - Setup: Sell OTM Put.
    - Risk: Defined (Strike Price * 100).
    - Criteria: Delta 20-40, IV Rank > 20.
    """
    def __init__(self, event_bus: EventBus):
        super().__init__("CashSecuredPut", event_bus)
        self.bus.subscribe(EventType.MARKET_DATA, self.on_market_data)

    def evaluate(self, data: dict) -> Optional[dict]:
        current_price = data.get('price')
        iv_rank = data.get('iv_rank', 0)
        
        # PRD: Prioritize high IV
        if iv_rank < 20: 
            return None
            
        # Target Delta 0.30 (approx 5% OTM for this mock)
        strike_price = current_price * 0.95
        
        # Premium estimation (mock)
        premium = current_price * 0.015
        
        # Collateral Requirement: Full Strike Value
        collateral = strike_price * 100
        
        return {
            "strategy": "CASH_SECURED_PUT",
            "symbol": data.get('symbol'),
            "side": "SELL",
            "legs": [
                {"side": "SELL", "type": "PUT", "strike": strike_price}
            ],
            "limit_price": round(premium, 2),
            "risk_per_unit": round(collateral, 2)
        }

    def on_market_data(self, event: Event):
        signal = self.evaluate(event.data)
        if signal:
            self.bus.publish(Event(EventType.SIGNAL, signal))


class _DirectionalDebitStrategy(Strategy):
    """Shared mechanics for Long Call / Long Put.

    Each entry is justified by a confirmed candlestick pattern in the
    direction of the strategy's bias (bullish patterns for calls, bearish
    for puts). We pull the OHLC history from the DAILY_BAR payload, run
    it through the candlestick detectors, and only emit a signal when a
    pattern fires AND IV rank is moderate.

    The signal carries the pattern name, a didactic description, and the
    bar window so the chart generator can later annotate the trade.
    """

    OPTION_TYPE: str = "CALL"   # overridden by subclasses
    BIAS: str = "BULLISH"       # "BULLISH" or "BEARISH"
    OTM_PCT: float = 0.02       # how far OTM (heuristic fallback)
    PREMIUM_PCT: float = 0.012  # rough premium estimate as % of spot (fallback)
    MAX_IV_RANK: float = 50.0   # skip when IV is too rich
    TARGET_DELTA: float = 0.35  # ~30-40 delta for long options
    MIN_DTE: int = 30
    MAX_DTE: int = 45
    MIN_PATTERN_STRENGTH: int = 2

    COOLDOWN_BARS: int = 3      # avoid stacking signals on consecutive bars

    def __init__(self, name: str, event_bus: EventBus,
                 market_data_client=None):
        super().__init__(name, event_bus)
        self._cooldown: Dict[str, int] = defaultdict(int)
        self.market_data = market_data_client  # optional: real chain lookups
        # Long Call/Put are multi-day theses. Only consider entries on the
        # daily bar; intraday MARKET_DATA ticks are handled by ExitManager.
        self.bus.subscribe(EventType.DAILY_BAR, self.on_market_data)

    @staticmethod
    def _bars_from_history(history: List[dict]) -> List[Bar]:
        return [Bar(open=h["open"], high=h["high"],
                    low=h["low"], close=h["close"]) for h in history]

    def _detect_pattern(self, history: List[dict]) -> Optional[Pattern]:
        bars = self._bars_from_history(history)
        if len(bars) < 6:
            return None
        pattern = detect_first(bars, self.BIAS)
        if pattern is None:
            return None
        if pattern.strength < self.MIN_PATTERN_STRENGTH:
            return None
        return pattern

    def _build_signal_from_chain(self, symbol: str) -> Optional[dict]:
        """Try to pick a real contract by delta. None if data not available."""
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
        """Fallback when the option chain is unavailable (offline/sim)."""
        bias_sign = 1 if self.BIAS == "BULLISH" else -1
        strike = price * (1 + self.OTM_PCT * bias_sign)
        premium = round(price * self.PREMIUM_PCT, 2)
        return {
            "strike": round(strike, 2),
            "premium": premium,
            "expiration": None,
            "delta": None,
            "dte": None,
            "iv": None,
            "source": "heuristic",
        }

    def evaluate(self, data: dict) -> Optional[dict]:
        symbol = data.get('symbol')
        price = data.get('price')
        history = data.get('ohlc_history') or []
        if not symbol or price is None or not history:
            return None

        if self._cooldown[symbol] > 0:
            self._cooldown[symbol] -= 1
            return None

        iv_rank = data.get('iv_rank', 0)
        if iv_rank > self.MAX_IV_RANK:
            return None

        pattern = self._detect_pattern(history)
        if pattern is None:
            return None

        contract = (self._build_signal_from_chain(symbol)
                    or self._build_signal_heuristic(symbol, price))

        # Max risk on a long option = premium paid * 100 (per contract)
        risk_per_unit = round(contract["premium"] * 100, 2)

        self._cooldown[symbol] = self.COOLDOWN_BARS

        rationale = (
            f"{pattern.name} ({pattern.bias.lower()}, fuerza {pattern.strength}/3) "
            f"detectado en {symbol}. {pattern.description}"
        )

        return {
            "strategy": "LONG_CALL" if self.OPTION_TYPE == "CALL" else "LONG_PUT",
            "symbol": symbol,
            "side": "BUY",  # debit trade: we are paying the premium
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
            # Candlestick rationale: forwarded all the way through the bus so
            # PortfolioManager can persist it and the chart generator can
            # annotate the entry.
            "pattern_name": pattern.name,
            "pattern_strength": pattern.strength,
            "pattern_bars_back": pattern.bars_back,
            "rationale": rationale,
            "ohlc_history": list(history),
            "spot_at_entry": price,
        }

    def on_market_data(self, event: Event):
        signal = self.evaluate(event.data)
        if signal:
            self.bus.publish(Event(EventType.SIGNAL, signal))


class LongCallStrategy(_DirectionalDebitStrategy):
    """Long Call (debit):
    - Thesis: Bullish.
    - Setup: BUY ~30-40 delta call when a bullish candlestick pattern
      (Morning Star, Bullish Engulfing, Piercing Line, Hammer) prints on
      the daily and IV rank is moderate.
    - Risk: limited to premium paid; profit theoretically unlimited.
    - Exit (handled by ExitManager): +100% on premium, -50% stop, or DTE < 7.
    """
    OPTION_TYPE = "CALL"
    BIAS = "BULLISH"

    def __init__(self, event_bus: EventBus, market_data_client=None):
        super().__init__("LongCall", event_bus, market_data_client)


class LongPutStrategy(_DirectionalDebitStrategy):
    """Long Put (debit):
    - Thesis: Bearish.
    - Setup: BUY ~30-40 delta put when a bearish candlestick pattern
      (Evening Star, Bearish Engulfing, Dark Cloud Cover, Shooting Star)
      prints on the daily and IV rank is moderate.
    - Risk: limited to premium paid.
    """
    OPTION_TYPE = "PUT"
    BIAS = "BEARISH"

    def __init__(self, event_bus: EventBus, market_data_client=None):
        super().__init__("LongPut", event_bus, market_data_client)


class BearCallSpreadStrategy(Strategy):
    """
    Bear Call Spread (Credit Spread):
    - Objective: Income from neutral/bearish view.
    - Setup: Sell Call A, Buy Call B (A < B).
    - Risk: Limited to Width - Credit.
    """
    def __init__(self, event_bus: EventBus):
        super().__init__("BearCallSpread", event_bus)
        self.bus.subscribe(EventType.MARKET_DATA, self.on_market_data)

    def evaluate(self, data: dict) -> Optional[dict]:
        current_price = data.get('price')
        iv_rank = data.get('iv_rank', 0)
        
        if iv_rank < 20: return None
        
        # Short Call at ~30 Delta (approx 105% of price)
        short_call_strike = current_price * 1.05
        # Long Call protection (Spread width ~$5 or 1%)
        long_call_strike = short_call_strike + 5.0
        
        credit = 1.20 # Mock
        width = long_call_strike - short_call_strike
        max_risk = width - credit
        
        return {
            "strategy": "BEAR_CALL_SPREAD",
            "symbol": data.get('symbol'),
            "side": "SELL",
            "legs": [
                {"side": "SELL", "type": "CALL", "strike": short_call_strike},
                {"side": "BUY",  "type": "CALL", "strike": long_call_strike}
            ],
            "limit_price": credit,
            "risk_per_unit": max_risk * 100
        }

    def on_market_data(self, event: Event):
        signal = self.evaluate(event.data)
        if signal:
            self.bus.publish(Event(EventType.SIGNAL, signal))
