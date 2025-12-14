from datetime import datetime
from typing import List, Optional
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Enum, ForeignKey, JSON, Boolean
from sqlalchemy.orm import declarative_base, relationship, sessionmaker, Session
import enum

Base = declarative_base()

class TradeStatus(str, enum.Enum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"

class RiskState(str, enum.Enum):
    NORMAL = "NORMAL"
    DEFENSIVE = "DEFENSIVE"
    HALT = "HALT"

class StrategyType(str, enum.Enum):
    BULL_PUT_SPREAD = "BULL_PUT_SPREAD"
    BEAR_CALL_SPREAD = "BEAR_CALL_SPREAD"
    IRON_CONDOR = "IRON_CONDOR"

class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="USER") # ADMIN or USER
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Configuration (JSON) to store custom risk params, capital, etc.
    config = Column(JSON, default={}) 

class Trade(Base):
    __tablename__ = 'trades'

    id = Column(Integer, primary_key=True, autoincrement=True)
    # user_id removed - Trades are GLOBAL
    
    strategy_type = Column(Enum(StrategyType), nullable=False)
    symbol = Column(String, nullable=False)
    entry_time = Column(DateTime, default=datetime.utcnow)
    exit_time = Column(DateTime, nullable=True)
    status = Column(Enum(TradeStatus), default=TradeStatus.OPEN)
    
    # Financials
    entry_credit = Column(Float, nullable=False) # Total credit received
    exit_debit = Column(Float, default=0.0)      # Total debit paid to close
    pnl = Column(Float, default=0.0)             # Realized PnL
    commission = Column(Float, default=0.0)
    
    # Risk
    max_risk = Column(Float, nullable=False)     # Max loss potential
    
    legs = relationship("Leg", back_populates="trade", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Trade id={self.id} {self.strategy_type} {self.symbol} status={self.status}>"

class Leg(Base):
    __tablename__ = 'legs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_id = Column(Integer, ForeignKey('trades.id'), nullable=False)
    
    option_symbol = Column(String, nullable=False) # e.g., SPY_240620_P_450
    side = Column(String, nullable=False) # BUY or SELL
    strike = Column(Float, nullable=False)
    expiration = Column(DateTime, nullable=False)
    option_type = Column(String, nullable=False) # PUT or CALL
    
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)

    trade = relationship("Trade", back_populates="legs")

class AccountState(Base):
    __tablename__ = 'account_state'

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey('users.id'), nullable=True)
    
    timestamp = Column(DateTime, default=datetime.utcnow)
    equity = Column(Float, nullable=False)
    balance = Column(Float, nullable=False)
    risk_state = Column(Enum(RiskState), default=RiskState.NORMAL)
    drawdown_pct = Column(Float, default=0.0)
    daily_trades_count = Column(Integer, default=0)


# Global DB Instance
# We will initialize this after defining the class properly
# db = Database()

from dotenv import load_dotenv
import os

load_dotenv()

class Database:
    def __init__(self):
        self.db_url = os.getenv("DATABASE_URL", "sqlite:///apolo_trading.db")
        
        # SQLAlchemy requires 'postgresql://', but some providers (like Heroku/Supabase) 
        # might give 'postgres://'. We fix it here.
        if self.db_url.startswith("postgres://"):
            self.db_url = self.db_url.replace("postgres://", "postgresql://", 1)
            
        print(f"Connecting to database: {self.db_url.split('@')[-1] if '@' in self.db_url else 'local sqlite'}")
        
        self.engine = create_engine(self.db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def get_session(self) -> Session:
        return self.SessionLocal()

db = Database()
