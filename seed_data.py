import random
from datetime import datetime, timedelta
from src.infrastructure.database.models import db, Trade, AccountState, RiskState, TradeStatus, StrategyType

def seed():
    session = db.get_session()
    
    # Clear existing
    session.query(Trade).delete()
    session.query(AccountState).delete()
    
    print("Seeding Database with 30 days of Prop Firm history...")
    
    current_equity = 100000.0
    start_date = datetime.now() - timedelta(days=30)
    
    session.add(AccountState(
        timestamp=start_date,
        equity=current_equity,
        balance=current_equity,
        risk_state=RiskState.NORMAL,
        drawdown_pct=0.0,
        daily_trades_count=0
    ))
    
    strategies = [StrategyType.BULL_PUT_SPREAD, StrategyType.IRON_CONDOR, StrategyType.BEAR_CALL_SPREAD]
    symbols = ["SPY", "QQQ", "IWM", "AAPL", "MSFT"]
    
    for day in range(1, 31):
        # 1-3 trades per day
        current_date = start_date + timedelta(days=day)
        daily_trades = random.randint(0, 3)
        
        for _ in range(daily_trades):
            # Trade details
            strat = random.choice(strategies)
            sym = random.choice(symbols)
            credit = random.uniform(0.50, 3.00)
            
            # Result (Win rate ~70%)
            is_win = random.random() < 0.70
            pnl = credit * 100 if is_win else -credit * 2 * 100 # 1:2 Risk Reward hit
            
            current_equity += pnl
            
            t = Trade(
                strategy_type=strat,
                symbol=sym,
                entry_time=current_date + timedelta(hours=random.randint(9, 15)),
                status=TradeStatus.CLOSED,
                entry_credit=credit,
                pnl=pnl,
                max_risk=credit*2*100,
                exit_debit=0.0 if is_win else credit*3
            )
            session.add(t)
            
        # End of day state
        hwm = 100000.0
        dd = (hwm - current_equity) / hwm if current_equity < hwm else 0.0
        
        state_enum = RiskState.NORMAL
        if dd > 0.04: state_enum = RiskState.DEFENSIVE
        if dd > 0.08: state_enum = RiskState.HALT
        
        acc = AccountState(
            timestamp=current_date.replace(hour=16, minute=0),
            equity=current_equity,
            balance=current_equity,
            risk_state=state_enum,
            drawdown_pct=dd,
            daily_trades_count=daily_trades
        )
        session.add(acc)
    
    session.commit()
    print(f"Seeding Complete. Final Equity: ${current_equity:,.2f}")

if __name__ == "__main__":
    seed()
