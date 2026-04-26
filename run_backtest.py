"""Quick backtest runner.

Usage:
    python run_backtest.py [SYMBOL] [START] [END]

Defaults to SPY over the last full year (the SPY Tactical Playbook is
designed for that ticker). Override STRATEGY_SET to switch which
strategies are loaded:
    STRATEGY_SET=PATTERNS python run_backtest.py XLF 2024-01-01 2024-12-31
    STRATEGY_SET=PLAYBOOK python run_backtest.py SPY 2024-01-01 2024-12-31  (default)
    STRATEGY_SET=ALL      python run_backtest.py SPY 2024-01-01 2024-12-31
"""
import sys
from datetime import datetime, timedelta

from src.backtesting.engine import BacktestEngine
from src.config import config
from src.strategies.options_strategies import LongCallStrategy, LongPutStrategy
from src.strategies.spy_playbook import M4Strategy, RCBStrategy


def _strategy_classes():
    classes = []
    if config.STRATEGY_SET in ("PATTERNS", "ALL"):
        classes += [LongCallStrategy, LongPutStrategy]
    if config.STRATEGY_SET in ("PLAYBOOK", "ALL"):
        classes += [M4Strategy, RCBStrategy]
    if not classes:
        raise SystemExit(f"Unknown STRATEGY_SET={config.STRATEGY_SET}")
    return classes


def main():
    symbol = sys.argv[1] if len(sys.argv) > 1 else "SPY"
    end = sys.argv[3] if len(sys.argv) > 3 else datetime.utcnow().strftime("%Y-%m-%d")
    start = (sys.argv[2] if len(sys.argv) > 2
             else (datetime.utcnow() - timedelta(days=365)).strftime("%Y-%m-%d"))

    engine = BacktestEngine(
        symbol=symbol,
        start=start,
        end=end,
        strategy_classes=_strategy_classes(),
    )
    res = engine.run()

    print()
    print("=" * 60)
    print(f"  Backtest {res.symbol}  {res.start.date()} -> {res.end.date()}")
    print(f"  Strategy set : {config.STRATEGY_SET}")
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
