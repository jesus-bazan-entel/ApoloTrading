import math
import time
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd
import yfinance as yf
from scipy.stats import norm

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

    def find_option_by_delta(
        self,
        symbol: str,
        option_type: str,        # "call" or "put"
        target_delta: float = 0.35,
        min_dte: int = 30,
        max_dte: int = 45,
        risk_free_rate: float = 0.05,
    ) -> Optional[dict]:
        """
        Walk the live option chain and pick the contract whose delta is
        closest to target_delta. For puts, we compare absolute delta values.
        Returns a dict with strike, premium (mid of bid/ask if available,
        else lastPrice), expiration, iv, delta, dte. None on failure.
        """
        try:
            chain = self.get_option_chain(symbol, min_dte=min_dte, max_dte=max_dte)
            if not chain:
                return None

            spot = float(chain["underlying_price"]) or self.get_current_price(symbol)
            if spot <= 0:
                return None

            df = (chain["calls"] if option_type == "call" else chain["puts"]).copy()
            if df is None or df.empty:
                return None

            exp_date = datetime.strptime(chain["expiration"], "%Y-%m-%d")
            dte = max((exp_date - datetime.now()).days, 1)
            T = dte / 365.0

            target = abs(target_delta)
            best = None
            best_diff = float("inf")

            for _, row in df.iterrows():
                strike = float(row["strike"])
                iv = float(row.get("impliedVolatility") or 0.0)
                if iv <= 0:
                    continue
                d = bs_delta(spot, strike, T, risk_free_rate, iv, option_type)
                diff = abs(abs(d) - target)
                if diff < best_diff:
                    bid = float(row.get("bid") or 0.0)
                    ask = float(row.get("ask") or 0.0)
                    last = float(row.get("lastPrice") or 0.0)
                    if bid > 0 and ask > 0:
                        premium = (bid + ask) / 2
                    else:
                        premium = last
                    if premium <= 0:
                        continue
                    best = {
                        "strike": strike,
                        "premium": round(premium, 2),
                        "expiration": chain["expiration"],
                        "iv": iv,
                        "delta": d,
                        "dte": dte,
                        "spot": spot,
                    }
                    best_diff = diff

            return best
        except Exception as e:
            print(f"Error selecting option for {symbol}: {e}")
            return None

    def get_option_price(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        option_type: str,  # "call" or "put"
    ) -> Optional[float]:
        """Look up a specific option's current mid price from the live chain."""
        try:
            ticker = yf.Ticker(symbol)
            chain = ticker.option_chain(expiration)
            df = chain.calls if option_type == "call" else chain.puts
            row = df[df["strike"] == strike]
            if row.empty:
                # tolerate floating-point strike mismatch
                df = df.copy()
                df["_d"] = (df["strike"] - strike).abs()
                row = df.sort_values("_d").head(1)
                if row.empty or row["_d"].iloc[0] > 0.01:
                    return None
            r = row.iloc[0]
            bid = float(r.get("bid") or 0.0)
            ask = float(r.get("ask") or 0.0)
            last = float(r.get("lastPrice") or 0.0)
            if bid > 0 and ask > 0:
                return round((bid + ask) / 2, 2)
            return round(last, 2) if last > 0 else None
        except Exception as e:
            print(f"Error fetching option price {symbol} {expiration} {strike}{option_type}: {e}")
            return None

    def get_iv_rank(self, symbol: str, lookback_days: int = 365) -> float:
        """
        Approximate IV Rank in [0, 100]. We proxy IV with realized volatility
        of daily returns (yfinance does not expose historical implied vol for
        free tickers), then rank today's value within the lookback window.
        Returns 50.0 if data is insufficient (neutral assumption).
        """
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period=f"{lookback_days}d", interval="1d")
            if len(hist) < 30:
                return 50.0
            returns = hist["Close"].pct_change().dropna()
            # Rolling 20-day annualized realized vol as IV proxy
            rolling = returns.rolling(window=20).std() * math.sqrt(252) * 100
            rolling = rolling.dropna()
            if rolling.empty:
                return 50.0
            current = float(rolling.iloc[-1])
            lo, hi = float(rolling.min()), float(rolling.max())
            if hi <= lo:
                return 50.0
            return max(0.0, min(100.0, (current - lo) / (hi - lo) * 100.0))
        except Exception as e:
            print(f"Error computing IV rank for {symbol}: {e}")
            return 50.0


def bs_delta(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str = "call") -> float:
    """Black-Scholes delta. T in years, sigma in decimal (e.g. 0.25)."""
    if T <= 0 or sigma <= 0 or S <= 0 or K <= 0:
        return 0.0
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    if option_type == "call":
        return float(norm.cdf(d1))
    return float(norm.cdf(d1) - 1.0)


def bs_price(S: float, K: float, T: float, r: float, sigma: float,
             option_type: str = "call") -> float:
    """Black-Scholes theoretical price. Returns intrinsic value at T<=0."""
    if S <= 0 or K <= 0:
        return 0.0
    if T <= 0 or sigma <= 0:
        if option_type == "call":
            return max(0.0, S - K)
        return max(0.0, K - S)
    d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    if option_type == "call":
        return float(S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2))
    return float(K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1))
