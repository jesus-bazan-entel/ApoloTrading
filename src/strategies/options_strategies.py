from datetime import datetime
from typing import List, Optional
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
