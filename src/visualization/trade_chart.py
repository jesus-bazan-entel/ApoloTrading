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

from src.strategies.indicators import ema as _ema


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
    overlays: Optional[dict] = None,   # SPY playbook: trendline, support
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

    # EMA overlays (8/21/50) for the playbook context. We compute them from
    # the same closes the strategy used so the chart matches the decision.
    closes = list(df["Close"].values)
    ema8 = _ema(closes, 8) if len(closes) >= 8 else None
    ema21 = _ema(closes, 21) if len(closes) >= 21 else None
    ema50 = _ema(closes, 50) if len(closes) >= 50 else None
    addplots = []
    if ema8:
        addplots.append(mpf.make_addplot(ema8, color="#f1c40f", width=1.0))
    if ema21:
        addplots.append(mpf.make_addplot(ema21, color="#9b59b6", width=1.0))
    if ema50:
        addplots.append(mpf.make_addplot(ema50, color="#34495e", width=1.4))

    # mplfinance horizontal lines: strike + entry spot, and optional support
    # for M4 (Trazado Base).
    hl_levels = [entry_spot, strike]
    hl_colors = ["#3498db", accent]
    hl_styles = ["--", "-"]
    hl_widths = [1.0, 1.5]
    support_level = (overlays or {}).get("support") if overlays else None
    if support_level:
        hl_levels.append(support_level)
        hl_colors.append("#7f8c8d")
        hl_styles.append("-.")
        hl_widths.append(1.2)
    hlines = dict(
        hlines=hl_levels,
        colors=hl_colors,
        linestyle=hl_styles,
        linewidths=hl_widths,
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

    plot_kwargs = dict(
        type="candle",
        style=style,
        title=title,
        ylabel="Spot price",
        hlines=hlines,
        figsize=(11, 5.5),
        returnfig=True,
        warn_too_much_data=10000,
    )
    if addplots:
        plot_kwargs["addplot"] = addplots
    fig, axes = mpf.plot(df, **plot_kwargs)

    ax = axes[0]
    # Shade the pattern window in the bias colour. axvspan uses positional
    # x coordinates, matching mplfinance's internal x-axis.
    ax.axvspan(pattern_start_x - 0.5, pattern_end_x + 0.5,
               alpha=0.15, color=accent, zorder=0)

    # Descending / ascending trendline from the playbook (M4 step 3, RCB).
    trendline = (overlays or {}).get("trendline") if overlays else None
    if trendline:
        slope = trendline.get("slope", 0.0)
        intercept = trendline.get("intercept", 0.0)
        lookback = int(trendline.get("lookback", 15))
        # The fit is in lookback-local coords; map back to global x indices.
        start_x_global = max(n - lookback, 0)
        xs_local = list(range(0, lookback))
        xs_global = [start_x_global + x for x in xs_local]
        ys = [slope * x + intercept for x in xs_local]
        ax.plot(xs_global, ys, color="#2c3e50", linewidth=1.2,
                linestyle="--", label="Trazado Base")

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

    # Legend for price levels + EMAs.
    ax.plot([], [], color="#3498db", linestyle="--", label=f"Entry spot ${entry_spot:.2f}")
    ax.plot([], [], color=accent, linestyle="-", label=f"Option strike ${strike:.2f}")
    if support_level:
        ax.plot([], [], color="#7f8c8d", linestyle="-.",
                label=f"Soporte ${support_level:.2f}")
    if ema8:
        ax.plot([], [], color="#f1c40f", label="EMA 8")
    if ema21:
        ax.plot([], [], color="#9b59b6", label="EMA 21")
    if ema50:
        ax.plot([], [], color="#34495e", label="EMA 50")
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
