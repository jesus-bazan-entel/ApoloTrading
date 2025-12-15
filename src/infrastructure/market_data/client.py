import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
import random

class MarketDataClient:
    """
    Acts as the bridge to real market data.
    Currently uses yfinance (Yahoo Finance) as the provider.
    """
    
    def get_current_price(self, symbol: str) -> float:
        """Fetches real-time(ish) price for the symbol."""
        try:
            ticker = yf.Ticker(symbol)
            # 'fast_info' is often faster than history for last price
            price = ticker.fast_info.last_price
            if price:
                return float(price)
            
            # Fallback
            hist = ticker.history(period="1d")
            if not hist.empty:
                return float(hist["Close"].iloc[-1])
            return 0.0
        except Exception as e:
            print(f"Error fetching price for {symbol}: {e}")
            return 0.0

    def get_option_chain(self, symbol: str, min_dte: int = 30, max_dte: int = 45):
        """
        Fetches the option chain for a specific expiration window.
        Returns a DataFrame with Calls and Puts suitable for the PRD.
        """
        try:
            ticker = yf.Ticker(symbol)
            expirations = ticker.options
            
            if not expirations:
                return None
            
            # Find expirations within DTE window (e.g., 30-45 days)
            target_date = None
            today = datetime.now()
            
            valid_dates = []
            for date_str in expirations:
                # Format usually YYYY-MM-DD
                exp_date = datetime.strptime(date_str, "%Y-%m-%d")
                days_to_exp = (exp_date - today).days
                
                if min_dte <= days_to_exp <= max_dte:
                    valid_dates.append(date_str)
            
            if not valid_dates:
                # Fallback: Just get the next available one if none in window (for testing)
                # or return None to be strict. Let's return the first one > min_dte
                future_dates = [d for d in expirations if (datetime.strptime(d, "%Y-%m-%d") - today).days > min_dte]
                if future_dates:
                    target_date = future_dates[0]
                else:
                    target_date = expirations[0] if expirations else None
            else:
                target_date = valid_dates[0] # Pick the first valid one (closest to 30 days usually)
                
            if not target_date:
                return None
                
            # Fetch Chain
            chain = ticker.option_chain(target_date)
            return {
                "expiration": target_date,
                "calls": chain.calls,
                "puts": chain.puts,
                "underlying_price": self.get_current_price(symbol) # Refresh price
            }
            
        except Exception as e:
            print(f"Error fetching options for {symbol}: {e}")
            return None
