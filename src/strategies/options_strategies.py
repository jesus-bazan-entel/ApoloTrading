from collections import defaultdict, deque
from datetime import datetime
from typing import Deque, Dict, List, Optional
from src.infrastructure.event_bus import EventBus, Event, EventType

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
    """Shared mechanics for Long Call / Long Put: track price history per
    symbol and emit a directional signal when momentum confirms the bias and
    implied volatility is not too rich (cheaper premium = better risk/reward
    on a long single-leg)."""

    OPTION_TYPE: str = "CALL"   # overridden by subclasses
    BIAS_DIRECTION: int = 1     # +1 bullish (call), -1 bearish (put)
    OTM_PCT: float = 0.02       # how far OTM to buy (2% by default)
    PREMIUM_PCT: float = 0.012  # rough premium estimate as % of spot
    MAX_IV_RANK: float = 50.0   # skip when IV is too rich

    HISTORY_LEN: int = 10
    FAST_MA: int = 3
    SLOW_MA: int = 8
    COOLDOWN_TICKS: int = 5     # avoid stacking signals on every tick

    def __init__(self, name: str, event_bus: EventBus):
        super().__init__(name, event_bus)
        self._history: Dict[str, Deque[float]] = defaultdict(
            lambda: deque(maxlen=self.HISTORY_LEN)
        )
        self._cooldown: Dict[str, int] = defaultdict(int)
        self.bus.subscribe(EventType.MARKET_DATA, self.on_market_data)

    def _momentum_confirms(self, prices: Deque[float]) -> bool:
        if len(prices) < self.SLOW_MA:
            return False
        fast = sum(list(prices)[-self.FAST_MA:]) / self.FAST_MA
        slow = sum(list(prices)[-self.SLOW_MA:]) / self.SLOW_MA
        # Bullish: fast > slow. Bearish: fast < slow.
        return (fast - slow) * self.BIAS_DIRECTION > 0

    def evaluate(self, data: dict) -> Optional[dict]:
        symbol = data.get('symbol')
        price = data.get('price')
        if not symbol or price is None:
            return None

        history = self._history[symbol]
        history.append(price)

        if self._cooldown[symbol] > 0:
            self._cooldown[symbol] -= 1
            return None

        # Filter 1: IV must not be too rich
        iv_rank = data.get('iv_rank', 0)
        if iv_rank > self.MAX_IV_RANK:
            return None

        # Filter 2: directional momentum must confirm
        if not self._momentum_confirms(history):
            return None

        # Strike selection: slightly OTM in the direction of the bias
        strike = price * (1 + self.OTM_PCT * self.BIAS_DIRECTION)
        # Premium estimate (very rough; real data would use the chain)
        premium = round(price * self.PREMIUM_PCT, 2)
        # Max risk on a long option = premium paid * 100 (per contract)
        risk_per_unit = round(premium * 100, 2)

        self._cooldown[symbol] = self.COOLDOWN_TICKS

        return {
            "strategy": "LONG_CALL" if self.OPTION_TYPE == "CALL" else "LONG_PUT",
            "symbol": symbol,
            "side": "BUY",  # debit trade: we are paying the premium
            "legs": [
                {"side": "BUY", "type": self.OPTION_TYPE, "strike": round(strike, 2)}
            ],
            "limit_price": premium,
            "risk_per_unit": risk_per_unit,
        }

    def on_market_data(self, event: Event):
        signal = self.evaluate(event.data)
        if signal:
            self.bus.publish(Event(EventType.SIGNAL, signal))


class LongCallStrategy(_DirectionalDebitStrategy):
    """Long Call (debit):
    - Thesis: Bullish.
    - Setup: BUY ~2% OTM call when fast MA > slow MA and IV rank is moderate.
    - Risk: limited to premium paid; profit theoretically unlimited.
    - Exit (handled elsewhere): +50-100% on premium, -50% stop, or DTE.
    """
    OPTION_TYPE = "CALL"
    BIAS_DIRECTION = 1

    def __init__(self, event_bus: EventBus):
        super().__init__("LongCall", event_bus)


class LongPutStrategy(_DirectionalDebitStrategy):
    """Long Put (debit):
    - Thesis: Bearish.
    - Setup: BUY ~2% OTM put when fast MA < slow MA and IV rank is moderate.
    - Risk: limited to premium paid.
    """
    OPTION_TYPE = "PUT"
    BIAS_DIRECTION = -1

    def __init__(self, event_bus: EventBus):
        super().__init__("LongPut", event_bus)


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
