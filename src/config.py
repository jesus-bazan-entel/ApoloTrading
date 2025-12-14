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

config = Config()
