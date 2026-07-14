"""Backtest module: replay 15-min + 5-min candles across a date range and
generate historical signals using the same strategy logic."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import List, Optional

import pandas as pd

from constants import (
    IST, ENTRY_WINDOWS, BTST_WINDOW, MAX_SIGNALS_PER_INSTRUMENT_PER_DAY,
    INSTRUMENTS,
)
from data_source import fetch_candles_range
from strategy import (
    find_latest_setup, check_retest_and_trigger, build_signal_from_setup,
    find_liquidity_sweep_setup, _daily_bias,
    signal_to_dict, SignalResult,
    _is_forex_friday_cutoff, _is_forex_primary_time, _is_forex_secondary_time,
)

logger = logging.getLogger(__name__)


def _is_intraday_or_btst(ts: pd.Timestamp):
    t = ts.time()
    for (h1, m1), (h2, m2) in ENTRY_WINDOWS:
        if pd.Timestamp(f"{h1:02d}:{m1:02d}").time() <= t <= pd.Timestamp(f"{h2:02d}:{m2:02d}").time():
            return "INTRADAY"
    b1, b2 = BTST_WINDOW
    if pd.Timestamp(f"{b1[0]:02d}:{b1[1]:02d}").time() <= t <= pd.Timestamp(f"{b2[0]:02d}:{b2[1]:02d}").time():
        return "BTST"
    return None


def _forex_window(ts: pd.Timestamp):
    """Return 'FX-OVERLAP' or 'FX-LONDON-OPEN' or None for a forex candle.
    Uses tz-aware London/NY session boundaries (DST safe)."""
    dt = ts.to_pydatetime()
    if _is_forex_primary_time(dt):
        return "FX-OVERLAP"
    if _is_forex_secondary_time(dt):
        return "FX-LONDON-OPEN"
    return None


def simulate_outcome(sig: SignalResult, df5_future: pd.DataFrame) -> dict:
    """Given the 5-min candles AFTER the entry time, determine if SL or target
    hit first. Returns dict with outcome / r_multiple / exit_price."""
    if df5_future is None or df5_future.empty:
        return {"outcome": "OPEN", "r_multiple": 0.0, "exit_price": None}
    if sig.direction == "LONG":
        risk = sig.entry - sig.stoploss
        if risk <= 0:
            return {"outcome": "OPEN", "r_multiple": 0.0, "exit_price": None,
                    "notes": "invalid signal: non-positive risk"}
        for ts, c in df5_future.iterrows():
            if c["Low"] <= sig.stoploss:
                return {"outcome": "LOST", "r_multiple": -1.0, "exit_price": sig.stoploss,
                        "exit_time": ts.isoformat()}
            if c["High"] >= sig.target:
                return {"outcome": "WON", "r_multiple": round((sig.target - sig.entry) / risk, 2),
                        "exit_price": sig.target, "exit_time": ts.isoformat()}
    else:
        risk = sig.stoploss - sig.entry
        if risk <= 0:
            return {"outcome": "OPEN", "r_multiple": 0.0, "exit_price": None,
                    "notes": "invalid signal: non-positive risk"}
        for ts, c in df5_future.iterrows():
            if c["High"] >= sig.stoploss:
                return {"outcome": "LOST", "r_multiple": -1.0, "exit_price": sig.stoploss,
                        "exit_time": ts.isoformat()}
            if c["Low"] <= sig.target:
                return {"outcome": "WON", "r_multiple": round((sig.entry - sig.target) / risk, 2),
                        "exit_price": sig.target, "exit_time": ts.isoformat()}
    return {"outcome": "OPEN", "r_multiple": 0.0, "exit_price": None}


def run_backtest(instrument: str, start_date: str, end_date: str) -> dict:
    """Run strategy across [start_date, end_date] (YYYY-MM-DD) using 15m and 5m
    candles from yfinance. Returns dict with signals and summary stats."""
    meta = INSTRUMENTS.get(instrument, {})
    asset_class = meta.get("asset_class", "EQUITY")
    instrument_type = meta.get("type", "stock")
    pip_decimals = meta.get("pip_decimals", 2)

    df15 = fetch_candles_range(instrument, "15m", start_date, end_date)
    df5 = fetch_candles_range(instrument, "5m", start_date, end_date)
    daily_end = (datetime.fromisoformat(end_date) + timedelta(days=1)).date().isoformat()
    daily_start = (datetime.fromisoformat(start_date) - timedelta(days=120)).date().isoformat()
    df_daily = fetch_candles_range(instrument, "1d", daily_start, daily_end)
    if df15 is None or df5 is None or df15.empty or df5.empty:
        return {"instrument": instrument, "asset_class": asset_class,
                "start": start_date, "end": end_date,
                "signals": [], "summary": {"total": 0, "won": 0, "lost": 0, "open": 0,
                                            "win_rate": 0, "avg_r": 0}}

    signals: List[dict] = []
    counts_per_day: dict[str, int] = {}

    # iterate each 15m candle in chronological order
    for i in range(30, len(df15)):
        window15 = df15.iloc[: i + 1]
        ts15 = window15.index[-1]
        day_key = ts15.date().isoformat()
        if counts_per_day.get(day_key, 0) >= MAX_SIGNALS_PER_INSTRUMENT_PER_DAY:
            continue

        # ---- session-window filter per asset class ----
        if asset_class == "FOREX":
            if _is_forex_friday_cutoff(ts15.to_pydatetime()):
                continue
            call_type = _forex_window(ts15)
            if call_type is None:
                continue
        else:
            # Skip Thursday within 90 min of 15:30 (option expiry proxy)
            if ts15.weekday() == 3 and ts15.time() >= pd.Timestamp("14:00").time():
                continue
            call_type = _is_intraday_or_btst(ts15)
            if call_type is None:
                continue

        setup = find_latest_setup(window15, asset_class=asset_class, instrument_type=instrument_type)
        if setup is not None and setup.setup_type == "BOS-OB-Retest" and df_daily is not None:
            # Trend filter: only take breakout-continuation trades aligned
            # with the daily trend. Uses only daily candles already closed
            # before ts15 — no look-ahead into the current/future day.
            daily_so_far = df_daily[df_daily.index.normalize() < ts15.normalize()]
            bias = _daily_bias(daily_so_far)
            if (setup.direction == "LONG" and bias != "UP") or \
               (setup.direction == "SHORT" and bias != "DOWN"):
                setup = None
        if setup is None:
            df5_so_far = df5.loc[df5.index <= ts15]
            setup = find_liquidity_sweep_setup(window15, df5_so_far, asset_class=asset_class,
                                                instrument_type=instrument_type)
        if setup is None:
            continue

        # Check corresponding 5m window (up to 60 min after the 15m close —
        # widened from 30 min; live signals get re-checked every scheduler
        # cycle with no hard cutoff, so this gives the backtest closer parity)
        end_scan = ts15 + timedelta(minutes=60)
        df5_scan = df5.loc[(df5.index >= ts15) & (df5.index <= end_scan)]
        if df5_scan.empty:
            continue
        # For retest we want the vwap-anchored full-day 5m up to end_scan
        day_start = ts15.replace(hour=9 if asset_class == "EQUITY" else 0,
                                 minute=15 if asset_class == "EQUITY" else 0,
                                 second=0, microsecond=0)
        df5_day = df5.loc[(df5.index >= day_start) & (df5.index <= end_scan)]
        entry_pack = check_retest_and_trigger(df5_day, setup)
        if entry_pack is None:
            continue
        entry, entry_ts = entry_pack
        sig = build_signal_from_setup(
            instrument, setup, entry, entry_ts, window15, call_type,
            pip_decimals=pip_decimals, asset_class=asset_class,
        )
        if sig is None:
            continue

        # simulate outcome
        df5_future = df5.loc[df5.index > entry_ts]
        outcome = simulate_outcome(sig, df5_future)
        sig_d = signal_to_dict(sig)
        sig_d.update(outcome)
        signals.append(sig_d)
        counts_per_day[day_key] = counts_per_day.get(day_key, 0) + 1

    won = sum(1 for s in signals if s.get("outcome") == "WON")
    lost = sum(1 for s in signals if s.get("outcome") == "LOST")
    op = sum(1 for s in signals if s.get("outcome") == "OPEN")
    total = len(signals)
    win_rate = round((won / total * 100), 2) if total else 0.0
    r_vals = [s.get("r_multiple", 0.0) for s in signals if s.get("outcome") in ("WON", "LOST")]
    avg_r = round(sum(r_vals) / len(r_vals), 2) if r_vals else 0.0

    return {
        "instrument": instrument, "asset_class": asset_class,
        "start": start_date, "end": end_date,
        "signals": signals,
        "summary": {"total": total, "won": won, "lost": lost, "open": op,
                    "win_rate": win_rate, "avg_r": avg_r},
    }