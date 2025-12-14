import pandas as pd
from typing import List, Dict, Optional
from datetime import datetime, timedelta
from src.infrastructure.event_bus import EventBus, Event, EventType
from src.infrastructure.database.models import Trade, Leg

class BacktestDataFeed:
    """
    Simulates a live data feed by iterating over historical data 
    and publishing MARKET_DATA events.
    """
    def __init__(self, event_bus: EventBus, data: pd.DataFrame):
        self.bus = event_bus
        self.data = data # Expected Index: Datetime, Columns: OHLCV + Option chains potentially
        self.current_index = 0

    def stream_next(self) -> bool:
        if self.current_index >= len(self.data):
            return False
        
        row = self.data.iloc[self.current_index]
        timestamp = self.data.index[self.current_index]
        
        # Publish Market Data Event
        event = Event(EventType.MARKET_DATA, {
            "timestamp": timestamp,
            "symbol": "SPY", # Simplified for MVP
            "price": row['Close'], # Use close for simplified tick
            # In real system, we'd pass the full Option Chain snapshot here
        })
        self.bus.publish(event)
        
        self.current_index += 1
        return True

class ExecutionSimulator:
    """
    Simulates the Exchange. Listens for ORDER_REQUEST, 
    applies Slippage/latency, and publishes ORDER_FILL.
    """
    def __init__(self, event_bus: EventBus, slippage_pct=0.01):
        self.bus = event_bus
        self.slippage = slippage_pct
        self.bus.subscribe(EventType.ORDER_REQUEST, self.handle_order_request)

    def handle_order_request(self, event: Event):
        order_data = event.data
        # Simulate fill logic
        mid_price = order_data.get("price", 100.0) # Placeholder
        
        # Apply slippage
        fill_price = mid_price * (1 + self.slippage) if order_data['side'] == 'BUY' else mid_price * (1 - self.slippage)
        
        fill_event = Event(EventType.ORDER_FILL, {
            "order_id": order_data.get("order_id"),
            "symbol": order_data['symbol'],
            "fill_price": fill_price,
            "quantity": order_data['quantity'],
            "timestamp": event.timestamp + timedelta(milliseconds=200) # Latency
        })
        self.bus.publish(fill_event)

class BacktestEngine:
    def __init__(self, event_bus: EventBus, start_date: datetime, end_date: datetime):
        self.bus = event_bus
        self.start_date = start_date
        self.end_date = end_date
        self.feed = None
        self.execution = ExecutionSimulator(event_bus)

    def load_data(self):
        # TODO: Load real CSV/Parquet data here
        # Creating dummy data for structural validation
        dates = pd.date_range(start=self.start_date, end=self.end_date, freq='1min')
        df = pd.DataFrame(index=dates, data={'Close': [450.0 + i*0.01 for i in range(len(dates))]})
        self.feed = BacktestDataFeed(self.bus, df)

    def run(self):
        """Main Backtest Loop"""
        print("Starting Backtest...")
        self.load_data()
        
        while self.feed.stream_next():
            pass # The event bus handles the reaction logic
            
        print("Backtest Complete.")
