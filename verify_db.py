import os
from sqlalchemy import create_engine, text

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "apolo_trading.db")
DB_URL = f"sqlite:///{DB_PATH}"

print(f"Checking DB at: {DB_PATH}")

if not os.path.exists(DB_PATH):
    print("❌ DB File does not exist!")
else:
    print(f"DB File exists. Size: {os.path.getsize(DB_PATH)} bytes")
    try:
        engine = create_engine(DB_URL)
        with engine.connect() as conn:
            result_trades = conn.execute(text("SELECT count(*) FROM trades"))
            count_trades = result_trades.scalar()
            
            result_acc = conn.execute(text("SELECT count(*) FROM account_state"))
            count_acc = result_acc.scalar()
            
            print(f"Trades Count: {count_trades}")
            print(f"Account States Count: {count_acc}")
            
            if count_acc > 0:
                print("Last Account State:")
                last = conn.execute(text("SELECT * FROM account_state ORDER BY id DESC LIMIT 1")).fetchone()
                print(last)
    except Exception as e:
        print(f"Error reading DB: {e}")
