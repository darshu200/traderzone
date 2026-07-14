"""
Instrumented replay of the exact backtest loop for one instrument, with a
counter at every filter stage, so we can see WHERE candidates get rejected
instead of just the final zero.

Run from the backend folder with your venv active:
    python debug_nifty_funnel.py
Edit INSTRUMENT / START / END below to try other instruments or ranges.
"""
from datetime import datetime, timedelta
import pandas as pd

from constants import INSTRUMENTS, MAX_SIGNALS_PER_INSTRUMENT_PER_DAY
from data_source import fetch_candles_range
from strategy import (
    find_latest_setup, check_retest_and_trigger, build_signal_from_setup,
    _is_forex_friday_cutoff,
)
from backtest import _is_intraday_or_btst, _forex_window

INSTRUMENT = "NIFTY"
START = "2026-05-07"
END = "2026-07-05"

meta = INSTRUMENTS[INSTRUMENT]
asset_class = meta.get("asset_class", "EQUITY")
instrument_type = meta.get("type", "stock")
pip_decimals = meta.get("pip_decimals", 2)

df15 = fetch_candles_range(INSTRUMENT, "15m", START, END)
df5 = fetch_candles_range(INSTRUMENT, "5m", START, END)
print(f"df15 shape: {None if df15 is None else df15.shape}")
print(f"df5  shape: {None if df5 is None else df5.shape}")

counts = {
    "total_candles": 0,
    "daily_cap_skipped": 0,
    "session_window_failed": 0,
    "setup_none_bos": 0,
    "df5_scan_empty": 0,
    "retest_trigger_failed": 0,
    "signal_build_failed": 0,
    "final_signals": 0,
}
counts_per_day = {}

for i in range(30, len(df15)):
    window15 = df15.iloc[: i + 1]
    ts15 = window15.index[-1]
    day_key = ts15.date().isoformat()
    counts["total_candles"] += 1

    if counts_per_day.get(day_key, 0) >= MAX_SIGNALS_PER_INSTRUMENT_PER_DAY:
        counts["daily_cap_skipped"] += 1
        continue

    if asset_class == "FOREX":
        if _is_forex_friday_cutoff(ts15.to_pydatetime()):
            counts["session_window_failed"] += 1
            continue
        call_type = _forex_window(ts15)
        if call_type is None:
            counts["session_window_failed"] += 1
            continue
    else:
        if ts15.weekday() == 3 and ts15.time() >= pd.Timestamp("14:00").time():
            counts["session_window_failed"] += 1
            continue
        call_type = _is_intraday_or_btst(ts15)
        if call_type is None:
            counts["session_window_failed"] += 1
            continue

    setup = find_latest_setup(window15, asset_class=asset_class, instrument_type=instrument_type)
    if setup is None:
        counts["setup_none_bos"] += 1
        continue

    end_scan = ts15 + timedelta(minutes=60)
    df5_scan = df5.loc[(df5.index >= ts15) & (df5.index <= end_scan)]
    if df5_scan.empty:
        counts["df5_scan_empty"] += 1
        continue

    day_start = ts15.replace(hour=9 if asset_class == "EQUITY" else 0,
                             minute=15 if asset_class == "EQUITY" else 0,
                             second=0, microsecond=0)
    df5_day = df5.loc[(df5.index >= day_start) & (df5.index <= end_scan)]
    entry_pack = check_retest_and_trigger(df5_day, setup)
    if entry_pack is None:
        counts["retest_trigger_failed"] += 1
        continue

    entry, entry_ts = entry_pack
    sig = build_signal_from_setup(
        INSTRUMENT, setup, entry, entry_ts, window15, call_type,
        pip_decimals=pip_decimals, asset_class=asset_class,
    )
    if sig is None:
        counts["signal_build_failed"] += 1
        continue

    counts["final_signals"] += 1
    counts_per_day[day_key] = counts_per_day.get(day_key, 0) + 1

print("\n--- FUNNEL RESULTS ---")
for k, v in counts.items():
    print(f"{k:25s}: {v}")