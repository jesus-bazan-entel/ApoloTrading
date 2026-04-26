import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

class Config:
    # Default to local SQLite if no Cloud URL provided
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///apolo_trading.db")

    # Supabase/Postgres requires specific driver prefix in SQLAlchemy
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

    # Trading account starting equity (USD). Long Call/Put strategy is viable
    # from ~$1,000-$2,000. Override with env var INITIAL_EQUITY.
    INITIAL_EQUITY = float(os.getenv("INITIAL_EQUITY", "2000"))

    # Risk per trade as a fraction of equity in NORMAL state
    RISK_PCT_NORMAL = float(os.getenv("RISK_PCT_NORMAL", "0.02"))
    RISK_PCT_DEFENSIVE = float(os.getenv("RISK_PCT_DEFENSIVE", "0.01"))

    # Hard cap: maximum % of equity a single contract may risk, even if the
    # 2% sizing rule rounds to 0 contracts (lets small accounts open 1 lot).
    SINGLE_TRADE_HARD_CAP_PCT = float(os.getenv("SINGLE_TRADE_HARD_CAP_PCT", "0.10"))

config = Config()
