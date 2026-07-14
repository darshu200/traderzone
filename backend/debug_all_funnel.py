"""
Runs the exact same funnel logic as run_backtest, across EVERY instrument
(all equity + forex + indices) at once, using the maximum available ~60-day
yfinance intraday window. Prints a per-instrument breakdown plus totals.

Run from the backend folder with your venv active:
    python debug_all_funnel.py
"""
from datetime import datetime, timedelta
import pandas as pd

from constants import INSTRUMENTS, ALL_SYMBOLS, MAX_SIGNALS_PER_INSTRUMENT_PER_DAY
from data_source import fetch_candles_range
from strategy import (
    find_latest_setup, check_retest_and_trigger, build_signal_from_setup,
    _is_forex_friday_cutoff,
)
from backtest import _is_intraday_or_btst, _forex_window

# Stay safely inside yfinance's ~60-day intraday history limit.
END_DT = datetime.now()
START_DT = END_DT - timedelta(days=58)
START = START_DT.strftime("%Y-%m-%d")
END = END_DT.strftime("%Y-%m-%d")

print(f"Window: {START} -> {END}\n")


def run_funnel(instrument: str) -> dict:
    meta = INSTRUMENTS[instrument]
    asset_class = meta.get("asset_class", "EQUITY")
    instrument_type = meta.get("type", "stock")
    pip_decimals = meta.get("pip_decimals", 2)

    counts = {
        "instrument": instrument, "asset_class": asset_class,
        "total_candles": 0, "session_window_failed": 0, "setup_none_bos": 0,
        "df5_scan_empty": 0, "retest_trigger_failed": 0,
        "signal_build_failed": 0, "final_signals": 0, "error": None,
    }

    df15 = fetch_candles_range(instrument, "15m", START, END)
    df5 = fetch_candles_range(instrument, "5m", START, END)
    if df15 is None or df5 is None or df15.empty or df5.empty:
        counts["error"] = "no data returned"
        return counts

    counts_per_day = {}
    for i in range(30, len(df15)):
        window15 = df15.iloc[: i + 1]
        ts15 = window15.index[-1]
        day_key = ts15.date().isoformat()
        counts["total_candles"] += 1

        if counts_per_day.get(day_key, 0) >= MAX_SIGNALS_PER_INSTRUMENT_PER_DAY:
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
            instrument, setup, entry, entry_ts, window15, call_type,
            pip_decimals=pip_decimals, asset_class=asset_class,
        )
        if sig is None:
            counts["signal_build_failed"] += 1
            continue

        counts["final_signals"] += 1
        counts_per_day[day_key] = counts_per_day.get(day_key, 0) + 1

    return counts


results = []
for sym in ALL_SYMBOLS:
    print(f"Running {sym} ...")
    results.append(run_funnel(sym))

col_order = ["instrument", "asset_class", "total_candles", "session_window_failed",
             "setup_none_bos", "df5_scan_empty", "retest_trigger_failed",
             "signal_build_failed", "final_signals"]

print("\n" + "=" * 130)
header = f"{'Instrument':<12}{'Class':<8}{'Candles':>9}{'SessFail':>10}{'NoBOS':>8}{'5mEmpty':>9}{'RetestFail':>12}{'BuildFail':>11}{'FINAL':>8}"
print(header)
print("-" * 130)

totals = {k: 0 for k in col_order[2:]}
errors = []
for r in results:
    if r["error"]:
        errors.append(f"{r['instrument']}: {r['error']}")
        continue
    print(f"{r['instrument']:<12}{r['asset_class']:<8}{r['total_candles']:>9}"
          f"{r['session_window_failed']:>10}{r['setup_none_bos']:>8}"
          f"{r['df5_scan_empty']:>9}{r['retest_trigger_failed']:>12}"
          f"{r['signal_build_failed']:>11}{r['final_signals']:>8}")
    for k in totals:
        totals[k] += r[k]

print("-" * 130)
print(f"{'TOTAL':<12}{'':<8}{totals['total_candles']:>9}"
      f"{totals['session_window_failed']:>10}{totals['setup_none_bos']:>8}"
      f"{totals['df5_scan_empty']:>9}{totals['retest_trigger_failed']:>12}"
      f"{totals['signal_build_failed']:>11}{totals['final_signals']:>8}")
print("=" * 130)

if errors:
    print("\nInstruments with no data returned:")
    for e in errors:
        print(f"  - {e}")

print(f"\nGRAND TOTAL final_signals across ALL instruments: {totals['final_signals']}")
print("(This is the real number that matters — not any single instrument alone.)")
