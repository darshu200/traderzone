"""
Deeper diagnostic: for every BOS setup found, show EXACTLY why the retest
stage rejected it (never touched the OB zone / touched but wrong rejection
shape / touched with right shape but wrong side of VWAP), instead of just
counting "failed". This tells us which single condition is the real
bottleneck before we touch anything.

Run from the backend folder with your venv active:
    python debug_retest_reasons.py
"""
from datetime import timedelta
import numpy as np
import pandas as pd

from constants import INSTRUMENTS, MAX_SIGNALS_PER_INSTRUMENT_PER_DAY
from data_source import fetch_candles_range
from strategy import find_latest_setup, vwap_intraday
from backtest import _is_intraday_or_btst

INSTRUMENT = "NIFTY"
START = "2026-05-07"
END = "2026-07-05"

meta = INSTRUMENTS[INSTRUMENT]
asset_class = meta.get("asset_class", "EQUITY")
instrument_type = meta.get("type", "stock")

df15 = fetch_candles_range(INSTRUMENT, "15m", START, END)
df5 = fetch_candles_range(INSTRUMENT, "5m", START, END)
print(f"df15 shape: {None if df15 is None else df15.shape}")
print(f"df5  shape: {None if df5 is None else df5.shape}")

reasons = {
    "never_touched_ob": 0,
    "touched_wrong_shape": 0,
    "touched_right_shape_wrong_vwap_side": 0,
    "passed_all": 0,
}
counts_per_day = {}

for i in range(30, len(df15)):
    window15 = df15.iloc[: i + 1]
    ts15 = window15.index[-1]
    day_key = ts15.date().isoformat()
    if counts_per_day.get(day_key, 0) >= MAX_SIGNALS_PER_INSTRUMENT_PER_DAY:
        continue
    if ts15.weekday() == 3 and ts15.time() >= pd.Timestamp("14:00").time():
        continue
    call_type = _is_intraday_or_btst(ts15)
    if call_type is None:
        continue

    setup = find_latest_setup(window15, asset_class=asset_class, instrument_type=instrument_type)
    if setup is None:
        continue

    end_scan = ts15 + timedelta(minutes=30)
    day_start = ts15.replace(hour=9, minute=15, second=0, microsecond=0)
    df5_day = df5.loc[(df5.index >= day_start) & (df5.index <= end_scan)].copy()
    if df5_day.empty or len(df5_day) < 20:
        continue
    df5_day["vwap"] = vwap_intraday(df5_day)
    candidates = df5_day.iloc[-5:]

    touched_any = False
    right_shape_any = False
    passed = False
    for ts, c in candidates.iterrows():
        o, h, l, cl = float(c["Open"]), float(c["High"]), float(c["Low"]), float(c["Close"])
        v = float(c.get("vwap", np.nan))
        rng = h - l
        if rng <= 0:
            continue
        touches = (l <= setup.ob_high and h >= setup.ob_low)
        if not touches:
            continue
        touched_any = True
        if setup.direction == "LONG":
            shape_ok = ((cl - l) / rng >= 0.5) and (cl > o)
        else:
            shape_ok = ((h - cl) / rng >= 0.5) and (cl < o)
        if not shape_ok:
            continue
        right_shape_any = True
        vwap_ok = (np.isfinite(v) and ((cl > v) if setup.direction == "LONG" else (cl < v)))
        if vwap_ok:
            passed = True
            break

    counts_per_day[day_key] = counts_per_day.get(day_key, 0) + (1 if passed else 0)
    if passed:
        reasons["passed_all"] += 1
    elif right_shape_any:
        reasons["touched_right_shape_wrong_vwap_side"] += 1
    elif touched_any:
        reasons["touched_wrong_shape"] += 1
    else:
        reasons["never_touched_ob"] += 1

print("\n--- RETEST FAILURE BREAKDOWN (among candles with a valid BOS setup) ---")
for k, v in reasons.items():
    print(f"{k:38s}: {v}")
