"""Quick backtest runner.

Usage:
    python run_backtest.py [SYMBOL] [START] [END]

Defaults to XLF over the last full year of trading. Equity, win rate, and
drawdown are printed; the per-trade detail lives in backtest.db.
"""
import sys
from datetime import datetime, timedelta

from src.backtesting.engine import BacktestEngine
from src.strategies.options_strategies import LongCallStrategy, LongPutStrategy


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "XLF"
    end = sys.argv[3] if len(sys.argv) > 3 else datetime.utcnow().strftime("%Y-%m-%d")
    start = (sys.argv[2] if len(sys.argv) > 2
             else (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d"))

    engine = BacktestEngine(
        symbol=symbol,
        start=start,
        end=end,
        strategy_classes=[LongCallStrategy, LongPutStrategy],
    )
    res = engine.run()

    print()
    print("=" * 60)
    print(f"  Backtest {res.symbol}  {res.start.date()} -> {res.end.date()}")
    print("=" * 60)
    print(f"  Initial equity : ${res.initial_equity:,.2f}")
    print(f"  Final equity   : ${res.final_equity:,.2f}")
    print(f"  Total PnL      : ${res.total_pnl:,.2f}  "
          f"({(res.total_pnl / res.initial_equity * 100):.2f}%)")
    print(f"  Trades closed  : {res.trade_count}  "
          f"(W={res.wins}  L={res.losses}  WinRate={res.win_rate:.1%})")
    print(f"  Avg win / loss : ${res.avg_win:.2f} / ${res.avg_loss:.2f}")
    print(f"  Max drawdown   : {res.max_drawdown:.2%}")
    print("=" * 60)


if __name__ == "__main__":
    main()
