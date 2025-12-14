import math
from dataclasses import dataclass
from datetime import datetime
import numpy as np
from scipy.stats import norm

@dataclass
class OptionGreeks:
    delta: float
    gamma: float
    theta: float
    vega: float
    rho: float
    theoretical_price: float
    iv: float

class OptionPricingModel:
    """
    Professional implementation of Black-Scholes-Merton for European options.
    (Note: American options proxied via BSM often sufficient for short-term DTE, 
    but for strict precision Bjerksund-Stensland is preferred. Using BSM for speed in MVP).
    """

    @staticmethod
    def calculate_greeks(
        S: float, # Spot Price
        K: float, # Strike Price
        T: float, # Time to Expiration (in years)
        r: float, # Risk-free rate
        sigma: float, # Implied Volatility
        option_type: str = "call" # "call" or "put"
    ) -> OptionGreeks:
        """
        Calculate Greeks and Theoretical Price.
        """
        if T <= 0:
            return OptionGreeks(0, 0, 0, 0, 0, max(0, S-K) if option_type=="call" else max(0, K-S), sigma)

        d1 = (math.log(S / K) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        if option_type == "call":
            delta = norm.cdf(d1)
            theta = (- (S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T)) 
                     - r * K * math.exp(-r * T) * norm.cdf(d2))
            price = S * norm.cdf(d1) - K * math.exp(-r * T) * norm.cdf(d2)
            rho = K * T * math.exp(-r * T) * norm.cdf(d2)
        else:
            delta = norm.cdf(d1) - 1
            theta = (- (S * norm.pdf(d1) * sigma) / (2 * math.sqrt(T)) 
                     + r * K * math.exp(-r * T) * norm.cdf(-d2))
            price = K * math.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)
            rho = -K * T * math.exp(-r * T) * norm.cdf(-d2)

        gamma = norm.pdf(d1) / (S * sigma * math.sqrt(T))
        vega = S * norm.pdf(d1) * math.sqrt(T)

        # Annualize Theta usually preferred in days
        theta_daily = theta / 365.0
        vega_pct = vega / 100.0 # Standard convention

        return OptionGreeks(
            delta=delta,
            gamma=gamma,
            theta=theta_daily,
            vega=vega_pct,
            rho=rho,
            theoretical_price=price,
            iv=sigma
        )
