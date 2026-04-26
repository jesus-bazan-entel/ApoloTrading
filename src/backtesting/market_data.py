"""Synthetic option market data for backtests.

yfinance does not expose historical option chains, so for offline
backtesting we synthesize them via Black-Scholes:
- IV = trailing realized vol (annualized).
- Delta-targeted strike via grid search over a +/-20% band.
- Premium re-priced each bar using current spot, time to expiration, and
  the latest IV.

The BacktestEngine drives this client by calling `update(symbol, date,
spot, iv)` on every bar, so the strategy and the ExitManager always see
the current simulated state.
"""
from datetime import datetime, timedelta
from typing import Dict, Optional

from src.infrastructure.market_data.client import bs_delta, bs_price


class BacktestMarketDataClient:
    def __init__(self, dte_target: int = 35, risk_free_rate: float = 0.05):
        self.dte_target = dte_target
        self.r = risk_free_rate
        self._spot: Dict[str, float] = {}
        self._iv: Dict[str, float] = {}
        self._date: datetime = datetime.utcnow()

    # ------------------------------------------------------------------
    def update(self, symbol: str, current_date: datetime,
               spot: float, iv: float):
        self._spot[symbol] = spot
        self._iv[symbol] = max(iv, 0.05)  # floor at 5% to avoid degenerate BS
        self._date = current_date

    @property
    def now(self) -> datetime:
        return self._date

    # ------------------------------------------------------------------
    def find_option_by_delta(
        self,
        symbol: str,
        option_type: str,        # "call" or "put"
        target_delta: float = 0.35,
        min_dte: int = 30,
        max_dte: int = 45,
        risk_free_rate: float = 0.05,
    ) -> Optional[dict]:
        if symbol not in self._spot:
            return None
        spot = self._spot[symbol]
        sigma = self._iv[symbol]
        dte = max(min_dte, min(self.dte_target, max_dte))
        T = dte / 365.0
        expiration = (self._date + timedelta(days=dte)).strftime("%Y-%m-%d")

        target = abs(target_delta)
        best = None
        best_diff = float("inf")
        # Scan strikes in 1% increments around spot (-20% .. +20%)
        for pct in range(-20, 21):
            K = round(spot * (1 + pct / 100.0), 2)
            d = bs_delta(spot, K, T, self.r, sigma, option_type)
            diff = abs(abs(d) - target)
            if diff < best_diff:
                premium = bs_price(spot, K, T, self.r, sigma, option_type)
                if premium <= 0:
                    continue
                best = {
                    "strike": K,
                    "premium": round(premium, 2),
                    "expiration": expiration,
                    "iv": sigma,
                    "delta": d,
                    "dte": dte,
                    "spot": spot,
                }
                best_diff = diff
        return best

    # ------------------------------------------------------------------
    def get_option_price(
        self,
        symbol: str,
        expiration: str,
        strike: float,
        option_type: str,
    ) -> Optional[float]:
        if symbol not in self._spot:
            return None
        spot = self._spot[symbol]
        sigma = self._iv[symbol]
        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d")
        except (TypeError, ValueError):
            return None
        T = max((exp_date - self._date).days, 0) / 365.0
        return round(bs_price(spot, strike, T, self.r, sigma, option_type), 2)
