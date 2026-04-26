"""Annotated candlestick chart per trade (didactic visual analysis).

Renders the OHLC bars that led to the entry, highlights the bars that
formed the recognized pattern, and overlays:
- the strike (BUY level for the option)
- the entry spot price
- a one-line caption with the pattern name and what it means

Saves a PNG to `charts/trade_<id>.png` and returns the path.
"""
import os
from datetime import datetime, timedelta
from typing import List, Optional

import matplotlib

matplotlib.use("Agg")  # non-interactive backend; safe in headless runs

import matplotlib.pyplot as plt
import mplfinance as mpf
import pandas as pd


def _bars_to_df(history: List[dict]) -> pd.DataFrame:
    rows = []
    for h in history:
        ts = h.get("timestamp")
        if isinstance(ts, str):
            try:
                ts = datetime.fromisoformat(ts)
            except ValueError:
                ts = None
        if ts is None:
            ts = datetime.utcnow()
        rows.append({
            "Date": pd.Timestamp(ts),
            "Open": h["open"],
            "High": h["high"],
            "Low": h["low"],
            "Close": h["close"],
        })
    df = pd.DataFrame(rows).set_index("Date").sort_index()
    # mplfinance is unhappy with duplicate timestamps; nudge ties by ms.
    if not df.index.is_unique:
        df.index = pd.to_datetime(df.index) + pd.to_timedelta(
            range(len(df)), unit="ms")
    return df


def generate_trade_chart(
    trade_id: int,
    symbol: str,
    strategy: str,                # "LONG_CALL" or "LONG_PUT"
    pattern_name: str,
    pattern_bars_back: int,
    rationale: str,
    ohlc_history: List[dict],
    entry_spot: float,
    strike: float,
    expiration: Optional[str] = None,
    output_dir: str = "charts",
) -> Optional[str]:
    if not ohlc_history or len(ohlc_history) < 3:
        return None

    df = _bars_to_df(ohlc_history)
    if df.empty:
        return None

    # mplfinance uses a positional x-axis (0, 1, 2, ...), not datetime, so
    # all overlay annotations must be in the same space.
    n = len(df)
    pattern_start_x = max(n - pattern_bars_back, 0)
    pattern_end_x = n - 1

    bias_up = strategy == "LONG_CALL"
    accent = "#2ecc71" if bias_up else "#e74c3c"

    # mplfinance horizontal lines: strike + entry spot.
    hlines = dict(
        hlines=[entry_spot, strike],
        colors=["#3498db", accent],
        linestyle=["--", "-"],
        linewidths=[1.0, 1.5],
    )

    title = (f"{strategy.replace('_', ' ')} {symbol}  |  "
             f"{pattern_name}  |  entry ${entry_spot:.2f}  "
             f"strike ${strike:.2f}")

    style = mpf.make_mpf_style(
        base_mpf_style="charles",
        rc={"font.size": 9, "axes.titlesize": 10},
    )

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"trade_{trade_id:04d}.png")

    fig, axes = mpf.plot(
        df,
        type="candle",
        style=style,
        title=title,
        ylabel="Spot price",
        hlines=hlines,
        figsize=(11, 5.5),
        returnfig=True,
        warn_too_much_data=10000,
    )

    ax = axes[0]
    # Shade the pattern window in the bias colour. axvspan uses positional
    # x coordinates, matching mplfinance's internal x-axis.
    ax.axvspan(pattern_start_x - 0.5, pattern_end_x + 0.5,
               alpha=0.15, color=accent, zorder=0)

    # Arrow pointing at the latest bar with the pattern label.
    last_bar = df.iloc[-1]
    price_range = max(df["High"].max() - df["Low"].min(), 1e-6)
    if bias_up:
        arrow_y = last_bar["Low"]
        text_y = arrow_y - price_range * 0.12
    else:
        arrow_y = last_bar["High"]
        text_y = arrow_y + price_range * 0.12
    ax.annotate(
        pattern_name,
        xy=(pattern_end_x, arrow_y),
        xytext=(pattern_end_x, text_y),
        ha="center",
        fontsize=9,
        fontweight="bold",
        color=accent,
        arrowprops=dict(arrowstyle="->", color=accent, lw=1.5),
    )

    # Legend for the price levels.
    ax.plot([], [], color="#3498db", linestyle="--", label=f"Entry spot ${entry_spot:.2f}")
    ax.plot([], [], color=accent, linestyle="-", label=f"Option strike ${strike:.2f}")
    ax.legend(loc="upper left", fontsize=8, framealpha=0.85)

    # Didactic caption below the chart.
    caption = rationale
    if expiration:
        caption += f"  -  Expiracion: {expiration}"
    fig.text(0.5, 0.02, caption, ha="center", va="bottom",
             fontsize=8, wrap=True, color="#444")
    fig.subplots_adjust(bottom=0.18)

    fig.savefig(out_path, dpi=110, bbox_inches="tight")
    plt.close(fig)
    return out_path
