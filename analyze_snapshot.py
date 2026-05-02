"""Analiza un snapshot OHLCV (formato MCP TradingView) contra el playbook.

Util para validar end-to-end: pegamos las velas que devuelve data_get_ohlcv,
corremos los indicadores + detectores M4/RCB, y reportamos el estado.
"""
import json
import sys

from src.strategies.candlestick import Bar
from src.strategies.indicators import (
    descending_highs_line, ema, horizontal_support,
    is_zona_barata, is_zona_cara, line_value_at, macd, volume_step_down,
)


def analyze(bars_json_path: str):
    with open(bars_json_path) as f:
        bars_data = json.load(f)

    bars = [Bar(open=b["open"], high=b["high"], low=b["low"], close=b["close"])
            for b in bars_data]
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    lows = [b.low for b in bars]
    volumes = [b.get("volume", 0) for b in bars_data]

    e8 = ema(closes, 8)
    e21 = ema(closes, 21)
    e50 = ema(closes, 50)
    _m_line, _signal, hist = macd(closes)

    last = bars[-1]
    n = len(bars)

    # --- M4 condiciones ---
    m4_canal = last.close < e50[-1] and e8[-1] < e21[-1]
    m4_zona_cara = any(
        is_zona_cara(closes[: -k] if k > 0 else closes,
                     e21[: -k] if k > 0 else e21, threshold_pct=0.006)
        for k in (0, 1, 2)
    )
    m4_line = descending_highs_line(highs, lookback=15)
    m4_support = horizontal_support(lows, lookback=12, tolerance_pct=0.005)
    m4_breakdown = (last.is_bear and m4_support is not None
                    and last.close <= m4_support * 1.001)

    # --- RCB condiciones ---
    rcb_line = descending_highs_line(highs, lookback=15)
    rcb_zona_barata = any(
        is_zona_barata(closes[: -k] if k > 0 else closes,
                       e21[: -k] if k > 0 else e21, threshold_pct=0.006)
        for k in (1, 2, 3)
    )
    rcb_break = False
    if rcb_line is not None and last.is_bull:
        slope, intercept = rcb_line
        line_today = line_value_at(slope, intercept, 14)
        rcb_break = last.close > line_today

    print("=" * 60)
    print(f"  Bars: {n}  |  Last close: {last.close:.2f}")
    print("=" * 60)
    print(f"  EMA8  : {e8[-1]:.2f}")
    print(f"  EMA21 : {e21[-1]:.2f}")
    print(f"  EMA50 : {e50[-1]:.2f}")
    print(f"  MACD hist : {hist[-1]:+.3f}  (prev {hist[-2]:+.3f})")
    print(f"  Vol step-down (last 5) : {volume_step_down(volumes, 5)}")
    print()
    print(f"  --- M4 (PUT) ---")
    print(f"  1) Canal bajista (close<EMA50 y EMA8<EMA21): "
          f"{'OK' if m4_canal else 'NO'}")
    print(f"  2) Zona Cara reciente: {'OK' if m4_zona_cara else 'NO'}")
    print(f"  3) Triangulo descendente: line={m4_line is not None} "
          f"support={m4_support is not None}")
    print(f"  4) Vela roja rompe soporte: {'OK' if m4_breakdown else 'NO'}")
    m4_fires = m4_canal and m4_zona_cara and m4_line and m4_support and m4_breakdown
    print(f"  >>> M4 FIRE: {bool(m4_fires)}")
    print()
    print(f"  --- RCB (CALL) ---")
    print(f"  1) Linea descendente previa: {'OK' if rcb_line else 'NO'}")
    print(f"  2) Zona Barata reciente: {'OK' if rcb_zona_barata else 'NO'}")
    print(f"  3) Vela verde rompe linea: {'OK' if rcb_break else 'NO'}")
    print(f"  4) MACD subiendo o positivo: "
          f"{'OK' if (hist[-1] > hist[-2] or hist[-1] > 0) else 'NO'}")
    rcb_fires = bool(rcb_line) and rcb_zona_barata and rcb_break
    print(f"  >>> RCB FIRE: {rcb_fires}")
    print("=" * 60)


if __name__ == "__main__":
    analyze(sys.argv[1] if len(sys.argv) > 1 else "spy_snapshot.json")
