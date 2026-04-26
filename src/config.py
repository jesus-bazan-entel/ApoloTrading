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

    # Runtime mode. SIMULATION = synthetic tick loop (default; deterministic).
    # LIVE_DATA = poll yfinance for real prices/IV and publish to bus.
    # BACKTEST = run BacktestEngine over historical data.
    MODE = os.getenv("MODE", "SIMULATION").upper()

    # LIVE_DATA settings
    LIVE_SYMBOLS = [s.strip() for s in os.getenv("LIVE_SYMBOLS", "XLF,SOFI,F").split(",") if s.strip()]
    LIVE_POLL_SECONDS = float(os.getenv("LIVE_POLL_SECONDS", "30"))
    LIVE_MAX_TICKS = int(os.getenv("LIVE_MAX_TICKS", "0"))  # 0 = run forever

    # Broker selection (PAPER, ALPACA). Live broker is opt-in.
    BROKER = os.getenv("BROKER", "PAPER").upper()

    # Exit rules for long debit trades
    PROFIT_TARGET_PCT = float(os.getenv("PROFIT_TARGET_PCT", "1.0"))   # +100% on premium
    STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.5"))           # -50% on premium
    DTE_EXIT_DAYS = int(os.getenv("DTE_EXIT_DAYS", "7"))               # close if DTE < 7

config = Config()
