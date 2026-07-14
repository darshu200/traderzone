"""TradeSignal strategy engine. Implements BOS + Order Block + Retest logic on
15-min structure, 5-min entry trigger, with volume, VWAP, time window and hard
filters as specified in the problem statement."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, time as dtime
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from constants import (
    ENTRY_WINDOWS, BTST_WINDOW, VOLUME_MULTIPLIER, ATR_PERIOD,
    ATR_BUFFER_MIN, ATR_BUFFER_MAX, MIN_RR, MIN_RR_FLOOR, IST,
    LONDON_TZ, NY_TZ,
    LONDON_OPEN_LOCAL, LONDON_CLOSE_LOCAL,
    NY_OPEN_LOCAL, NY_CLOSE_LOCAL,
    LONDON_OPEN_WINDOW_HOURS, FRIDAY_CLOSE_BUFFER_MIN,
)

logger = logging.getLogger(__name__)


# ------------------------- Indicators ------------------------- #

def atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    high = df["High"]; low = df["Low"]; close = df["Close"]
    tr = pd.concat([
        (high - low).abs(),
        (high - close.shift(1)).abs(),
        (low - close.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period, min_periods=period).mean()


def vwap_intraday(df5: pd.DataFrame) -> pd.Series:
    """Session-anchored VWAP based on 5-min candles. Resets each trading date.
    If total volume in a group is 0 (typical for forex on yfinance), fall back
    to a session-anchored time-weighted average price (TWAP)."""
    if df5.empty:
        return pd.Series(dtype=float)
    tp = (df5["High"] + df5["Low"] + df5["Close"]) / 3.0
    vol = df5["Volume"].fillna(0)
    date_key = df5.index.date
    total_vol = vol.groupby(date_key).transform("sum")
    if (total_vol == 0).all():
        # No volume data — use TWAP (rolling cumulative mean per session).
        return tp.groupby(date_key).expanding().mean().reset_index(level=0, drop=True)
    grp_tpv = (tp * vol).groupby(date_key).cumsum()
    grp_v = vol.groupby(date_key).cumsum().replace(0, np.nan)
    result = grp_tpv / grp_v
    # For any NaN segments (volume-zero sessions), fall back to TWAP
    twap = tp.groupby(date_key).expanding().mean().reset_index(level=0, drop=True)
    return result.fillna(twap)


# ------------------------- Swings & Structure ------------------------- #

def find_swings(df: pd.DataFrame, left: int, right: int) -> Tuple[List[int], List[int]]:
    """Return (swing_high_idx, swing_low_idx) as positional integer indexes."""
    highs = df["High"].values
    lows = df["Low"].values
    sh, sl = [], []
    n = len(df)
    for i in range(left, n - right):
        if highs[i] == max(highs[i - left : i + right + 1]) and \
           highs[i] > max(highs[i - left : i]) and highs[i] > max(highs[i + 1 : i + right + 1]):
            sh.append(i)
        if lows[i] == min(lows[i - left : i + right + 1]) and \
           lows[i] < min(lows[i - left : i]) and lows[i] < min(lows[i + 1 : i + right + 1]):
            sl.append(i)
    return sh, sl


# ------------------------- Data classes ------------------------- #

@dataclass
class Setup:
    direction: str            # 'LONG' or 'SHORT'
    setup_type: str           # 'BOS-OB-Retest' or 'Liquidity-Sweep'
    bos_idx15: int
    swing_price: float
    ob_high: float
    ob_low: float
    atr15: float


@dataclass
class SignalResult:
    instrument: str
    direction: str
    setup_type: str
    entry: float
    stoploss: float
    target: float
    rr: float
    timestamp: str            # ISO IST
    call_type: str            # 'INTRADAY' or 'BTST'
    trade_date: str           # YYYY-MM-DD (IST)
    ob_high: float
    ob_low: float
    swing_price: float
    asset_class: str = "EQUITY"   # 'EQUITY' or 'FOREX'
    rr_tier: str = ""             # e.g. '1:1', '1:2', '1:3', '1:5' — the actual RR achieved, labeled honestly
    structural_start_ts: str = "" # timestamp of the BOS/sweep candle that started this setup —
                                   # lets us separate "strategy needed this long to confirm"
                                   # from "the system was slow to notice an already-ready signal"
    notes: str = ""


# ------------------------- Detection helpers ------------------------- #

def _in_window(t: dtime, window: Tuple[Tuple[int, int], Tuple[int, int]]) -> bool:
    (h1, m1), (h2, m2) = window
    return (dtime(h1, m1) <= t <= dtime(h2, m2))


def _is_intraday_time(t: dtime) -> bool:
    return any(_in_window(t, w) for w in ENTRY_WINDOWS)


def _is_btst_time(t: dtime) -> bool:
    return _in_window(t, BTST_WINDOW)


# ---------------------------------------------------------------------------
# Forex session helpers — timezone-aware. All accept a tz-aware datetime and
# make decisions from the local time in London / New York, so DST transitions
# are handled correctly (mid-March, early-November).
# ---------------------------------------------------------------------------

def _ensure_tzaware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=IST)
    return dt


def _london_session_open(dt: datetime) -> bool:
    """True if `dt` falls in the London session (08:00–17:00 Europe/London)."""
    lo = _ensure_tzaware(dt).astimezone(LONDON_TZ)
    open_t = dtime(*LONDON_OPEN_LOCAL)
    close_t = dtime(*LONDON_CLOSE_LOCAL)
    return open_t <= lo.time() < close_t


def _ny_session_open(dt: datetime) -> bool:
    """True if `dt` falls in the NY session (08:00–17:00 America/New_York)."""
    n = _ensure_tzaware(dt).astimezone(NY_TZ)
    open_t = dtime(*NY_OPEN_LOCAL)
    close_t = dtime(*NY_CLOSE_LOCAL)
    return open_t <= n.time() < close_t


def _is_forex_primary_time(dt: datetime) -> bool:
    """Primary entry window = London/NY overlap (intersection of both sessions)."""
    return _london_session_open(dt) and _ny_session_open(dt)


def _is_forex_secondary_time(dt: datetime) -> bool:
    """Secondary entry window = first N hours of London open."""
    lo = _ensure_tzaware(dt).astimezone(LONDON_TZ)
    open_h, open_m = LONDON_OPEN_LOCAL
    win_start = lo.replace(hour=open_h, minute=open_m, second=0, microsecond=0)
    win_end = win_start + timedelta(hours=LONDON_OPEN_WINDOW_HOURS)
    return win_start <= lo < win_end


def _is_forex_friday_cutoff(dt: datetime) -> bool:
    """True if `dt` is inside the FRIDAY_CLOSE_BUFFER_MIN minutes BEFORE the
    Friday 17:00 America/New_York close (global forex week close)."""
    ny = _ensure_tzaware(dt).astimezone(NY_TZ)
    if ny.weekday() != 4:  # 4 = Friday
        return False
    ny_close_h, ny_close_m = NY_CLOSE_LOCAL
    close = ny.replace(hour=ny_close_h, minute=ny_close_m, second=0, microsecond=0)
    delta_min = (close - ny).total_seconds() / 60.0
    return 0 <= delta_min <= FRIDAY_CLOSE_BUFFER_MIN


def _is_forex_market_open(dt: datetime) -> bool:
    """Forex market: opens Sunday 17:00 America/New_York, closes Friday 17:00
    America/New_York. Closed all day Saturday."""
    ny = _ensure_tzaware(dt).astimezone(NY_TZ)
    wd = ny.weekday()  # Mon=0..Sun=6
    t = ny.time()
    open_t = dtime(*NY_OPEN_LOCAL)
    close_t = dtime(*NY_CLOSE_LOCAL)
    if wd == 5:              # Saturday: closed all day
        return False
    if wd == 6:              # Sunday: open after 17:00 local
        return t >= close_t
    if wd == 4:              # Friday: open until 17:00 local
        return t < close_t
    _ = open_t               # keep for future use
    return True              # Mon-Thu: open 24h


def _daily_bias(df_daily: pd.DataFrame) -> str:
    """Return 'UP', 'DOWN', or 'NEUTRAL' based on 20/50 EMA on daily."""
    if df_daily is None or len(df_daily) < 55:
        return "NEUTRAL"
    ema20 = df_daily["Close"].ewm(span=20, adjust=False).mean()
    ema50 = df_daily["Close"].ewm(span=50, adjust=False).mean()
    last_c = df_daily["Close"].iloc[-1]
    if last_c > ema20.iloc[-1] > ema50.iloc[-1]:
        return "UP"
    if last_c < ema20.iloc[-1] < ema50.iloc[-1]:
        return "DOWN"
    return "NEUTRAL"


def find_latest_setup(df15: pd.DataFrame, asset_class: str = "EQUITY",
                       instrument_type: str = "stock") -> Optional[Setup]:
    """Look at the most recent 15-min candle. If it caused a BOS with volume filter,
    return a Setup describing the order block. Otherwise return None.

    For FOREX and INDEX instruments, yfinance reports zero/unreliable volume
    (indices have no real traded volume, same as forex pairs), so the volume
    filter is replaced with a range-based impulse filter: the BOS candle's
    true range must be >= 1.2 * ATR14. Only individual stocks use the real
    volume filter.
    """
    if df15 is None or len(df15) < 30:
        return None
    df15 = df15.copy()
    df15["vol_sma20"] = df15["Volume"].rolling(20, min_periods=20).mean()
    df15["atr14"] = atr(df15, ATR_PERIOD)

    sh, sl = find_swings(df15, left=3, right=3)
    last_i = len(df15) - 1
    last = df15.iloc[last_i]
    last_close = float(last["Close"])
    atr15 = float(last["atr14"] or 0)
    if atr15 <= 0:
        return None

    # ---- Impulse filter: volume for individual stocks, range for forex/index ----
    use_range_filter = (asset_class == "FOREX") or (instrument_type == "index")
    if use_range_filter:
        last_range = float(last["High"]) - float(last["Low"])
        if last_range < 1.2 * atr15:
            return None
    else:
        last_vol = float(last["Volume"] or 0)
        vol_sma = float(last["vol_sma20"] or 0)
        if vol_sma <= 0 or last_vol < VOLUME_MULTIPLIER * vol_sma:
            return None

    # Most recent swing high BEFORE last candle
    recent_sh = [i for i in sh if i < last_i]
    recent_sl = [i for i in sl if i < last_i]

    # Bullish BOS
    if recent_sh:
        sh_idx = recent_sh[-1]
        swing_price = float(df15["High"].iloc[sh_idx])
        if last_close > swing_price:
            # OB = last opposite-colored (red) candle before the impulsive move
            # Search between sh_idx and last_i for last red candle
            ob_i = None
            for i in range(last_i - 1, sh_idx - 1, -1):
                o = df15["Open"].iloc[i]; c = df15["Close"].iloc[i]
                if c < o:
                    ob_i = i; break
            if ob_i is None:
                return None
            return Setup(
                direction="LONG", setup_type="BOS-OB-Retest",
                bos_idx15=last_i, swing_price=swing_price,
                ob_high=float(df15["High"].iloc[ob_i]),
                ob_low=float(df15["Low"].iloc[ob_i]),
                atr15=atr15,
            )

    # Bearish BOS
    if recent_sl:
        sl_idx = recent_sl[-1]
        swing_price = float(df15["Low"].iloc[sl_idx])
        if last_close < swing_price:
            ob_i = None
            for i in range(last_i - 1, sl_idx - 1, -1):
                o = df15["Open"].iloc[i]; c = df15["Close"].iloc[i]
                if c > o:
                    ob_i = i; break
            if ob_i is None:
                return None
            return Setup(
                direction="SHORT", setup_type="BOS-OB-Retest",
                bos_idx15=last_i, swing_price=swing_price,
                ob_high=float(df15["High"].iloc[ob_i]),
                ob_low=float(df15["Low"].iloc[ob_i]),
                atr15=atr15,
            )
    return None


def _find_equal_level_pool(levels: List[float], price: float,
                            tol_pct: float = 0.0015) -> Optional[float]:
    """Given recent swing levels, return the midpoint of any two within
    tol_pct of each other — an 'equal highs/lows' liquidity pool. None if
    no such cluster exists."""
    for i in range(len(levels)):
        for j in range(i + 1, len(levels)):
            if price > 0 and abs(levels[i] - levels[j]) <= tol_pct * price:
                return (levels[i] + levels[j]) / 2
    return None


def find_liquidity_sweep_setup(df15: pd.DataFrame, df5: pd.DataFrame,
                                asset_class: str = "EQUITY",
                                instrument_type: str = "stock") -> Optional[Setup]:
    """Setup B from the rulebook (never implemented until now): price sweeps
    an obvious liquidity pool (equal highs/lows, previous day's high/low, or
    today's opening range), reclaims it within a few candles, then confirms
    a Change of Character (CHoCH) in the reversal direction. The sweep
    candle becomes a micro order block; entry/SL/target reuse the exact
    same retest + VWAP + rejection-candle + RR logic as Setup A.

    Only uses data up to the current point in time (df15/df5 should already
    be trimmed to "now" by the caller) — no look-ahead.
    """
    if df15 is None or len(df15) < 20 or df5 is None or len(df5) < 20:
        return None

    price = float(df15["Close"].iloc[-1])
    atr_series = atr(df15, ATR_PERIOD)
    atr15 = float(atr_series.iloc[-1] or 0)
    if atr15 <= 0:
        return None

    # ---- 1. Build liquidity pool candidates ----
    sh_idx, sl_idx = find_swings(df15, left=3, right=3)
    highs = [float(df15["High"].iloc[i]) for i in sh_idx[-6:]] if sh_idx else []
    lows = [float(df15["Low"].iloc[i]) for i in sl_idx[-6:]] if sl_idx else []

    pools: List[Tuple[float, str]] = []  # (level, 'HIGH' or 'LOW')
    eq_high = _find_equal_level_pool(highs, price)
    if eq_high:
        pools.append((eq_high, "HIGH"))
    eq_low = _find_equal_level_pool(lows, price)
    if eq_low:
        pools.append((eq_low, "LOW"))

    day_keys = df15.index.normalize()
    today = day_keys[-1]
    prev_mask = day_keys < today
    if prev_mask.any():
        prev_day = day_keys[prev_mask][-1]
        prev_df = df15[day_keys == prev_day]
        if not prev_df.empty:
            pools.append((float(prev_df["High"].max()), "HIGH"))
            pools.append((float(prev_df["Low"].min()), "LOW"))

    today_df = df15[day_keys == today]
    if len(today_df) >= 3:
        opening = today_df.iloc[:3]
        pools.append((float(opening["High"].max()), "HIGH"))
        pools.append((float(opening["Low"].min()), "LOW"))

    if not pools:
        return None

    # ---- 2. Sweep + reclaim on recent 5-min candles ----
    recent5 = df5.iloc[-12:].copy()  # last ~60 min
    recent5["vol_sma20"] = df5["Volume"].rolling(20, min_periods=20).mean().reindex(recent5.index)
    recent5["atr5"] = atr(df5, ATR_PERIOD).reindex(recent5.index)
    use_range_filter = (asset_class == "FOREX") or (instrument_type == "index")

    for level, kind in pools:
        for i in range(len(recent5) - 3):
            c = recent5.iloc[i]
            h, l = float(c["High"]), float(c["Low"])
            swept = (h > level) if kind == "HIGH" else (l < level)
            if not swept:
                continue

            atr5v = float(c.get("atr5") or 0)
            if atr5v <= 0:
                continue
            if use_range_filter:
                if (h - l) < 1.1 * atr5v:
                    continue
            else:
                vsma = float(c.get("vol_sma20") or 0)
                if vsma <= 0 or float(c["Volume"] or 0) < 1.2 * vsma:
                    continue

            reclaim_idx = None
            for j in range(i, min(i + 4, len(recent5))):
                cc = recent5.iloc[j]
                closed_back = (float(cc["Close"]) < level) if kind == "HIGH" else (float(cc["Close"]) > level)
                if closed_back:
                    reclaim_idx = j
                    break
            if reclaim_idx is None:
                continue

            # ---- 3. CHoCH confirmation after the reclaim ----
            direction = "LONG" if kind == "LOW" else "SHORT"
            micro_sh, micro_sl = find_swings(recent5.iloc[: reclaim_idx + 1], left=1, right=1)
            confirm_window = recent5.iloc[reclaim_idx: reclaim_idx + 5]
            choch = False
            if direction == "LONG" and micro_sh:
                ref_high = float(recent5["High"].iloc[micro_sh[-1]])
                choch = bool((confirm_window["Close"] > ref_high).any())
            elif direction == "SHORT" and micro_sl:
                ref_low = float(recent5["Low"].iloc[micro_sl[-1]])
                choch = bool((confirm_window["Close"] < ref_low).any())
            if not choch:
                continue

            # ---- 4. Micro order block = the sweep candle itself ----
            return Setup(
                direction=direction, setup_type="Liquidity-Sweep",
                bos_idx15=len(df15) - 1, swing_price=level,
                ob_high=h, ob_low=l, atr15=atr15,
            )
    return None


def check_retest_and_trigger(
    df5: pd.DataFrame,
    setup: Setup,
    at_time: Optional[pd.Timestamp] = None,
) -> Optional[Tuple[float, pd.Timestamp]]:
    """On 5-min candles, check if there is a bullish/bearish rejection candle
    inside the OB (retest) AND price on the right side of intraday VWAP.
    Returns (entry_price, entry_ts) or None."""
    if df5 is None or len(df5) < 20:
        return None
    df5 = df5.copy()
    df5["vwap"] = vwap_intraday(df5)

    # Restrict window: last 10 candles (~50 min on 5-min candles). Widened
    # from 5 (~25 min) after diagnostics showed most retest failures were
    # "price never got back to the OB in time," not a rejection-shape or
    # VWAP-side failure — institutional retests often take longer than 25 min.
    lookback = 10
    if at_time is not None:
        df5 = df5.loc[df5.index <= at_time]
        if len(df5) < lookback + 1:
            return None
    candidates = df5.iloc[-lookback:]

    for ts, c in candidates.iterrows():
        o, h, l, cl = float(c["Open"]), float(c["High"]), float(c["Low"]), float(c["Close"])
        v = float(c.get("vwap", np.nan))
        rng = h - l
        if rng <= 0:
            continue
        # Must touch OB range
        if setup.direction == "LONG":
            if not (l <= setup.ob_high and h >= setup.ob_low):
                continue
            # bullish rejection: close in top half of its range
            if (cl - l) / rng < 0.5:
                continue
            # bullish candle
            if cl <= o:
                continue
            # above VWAP
            if not (np.isfinite(v) and cl > v):
                continue
            return cl, ts
        else:
            if not (l <= setup.ob_high and h >= setup.ob_low):
                continue
            # bearish rejection: close in bottom half
            if (h - cl) / rng < 0.5:
                continue
            if cl >= o:
                continue
            if not (np.isfinite(v) and cl < v):
                continue
            return cl, ts
    return None


# ------------------------- Public API ------------------------- #

def _rr_tier_label(rr: float) -> str:
    """Label a signal by its actual reward-to-risk, e.g. 2.3 -> '1:2',
    3.9 -> '1:4'. Never below 1:1 since MIN_RR_FLOOR already rejects those."""
    return f"1:{max(1, round(rr))}"


def build_signal_from_setup(
    instrument: str,
    setup: Setup,
    entry: float,
    entry_ts: pd.Timestamp,
    df15: pd.DataFrame,
    call_type: str,
    pip_decimals: int = 2,
    asset_class: str = "EQUITY",
) -> Optional[SignalResult]:
    """Given a detected setup + confirmed entry, compute SL/target/RR and check
    minimum reward-to-risk. Returns None if RR < MIN_RR_FLOOR (1:1). Signals
    from 1:1 up are accepted and tagged with their real rr_tier label."""
    try:
        structural_start_ts = df15.index[setup.bos_idx15].isoformat()
    except Exception:
        structural_start_ts = ""
    buffer = (ATR_BUFFER_MIN + ATR_BUFFER_MAX) / 2 * setup.atr15
    if setup.direction == "LONG":
        stoploss = setup.ob_low - buffer
        risk = entry - stoploss
        min_risk = 10 ** (-pip_decimals)  # 1 pip/tick — guards against risk
        if risk <= min_risk:             # rounding to zero downstream
            return None
        # target = next liquidity pool above (last known swing high or extended)
        sh, _ = find_swings(df15, 3, 3)
        target_price = None
        recent_high = df15["High"].max()
        if sh:
            future_sh_prices = [float(df15["High"].iloc[i]) for i in sh
                                if float(df15["High"].iloc[i]) > entry]
            if future_sh_prices:
                target_price = min(future_sh_prices)
        if target_price is None:
            target_price = recent_high
        # If no valid target beyond entry, extrapolate 3R
        if target_price <= entry:
            target_price = entry + 3 * risk
        rr = (target_price - entry) / risk
        if rr < MIN_RR_FLOOR - 1e-9:
            return None
        return SignalResult(
            instrument=instrument, direction="LONG", setup_type=setup.setup_type,
            entry=round(entry, pip_decimals), stoploss=round(stoploss, pip_decimals),
            target=round(target_price, pip_decimals), rr=round(rr, 2),
            timestamp=entry_ts.astimezone(IST).isoformat(),
            call_type=call_type,
            trade_date=entry_ts.astimezone(IST).date().isoformat(),
            ob_high=round(setup.ob_high, pip_decimals),
            ob_low=round(setup.ob_low, pip_decimals),
            swing_price=round(setup.swing_price, pip_decimals),
            asset_class=asset_class,
            rr_tier=_rr_tier_label(rr),
            structural_start_ts=structural_start_ts,
        )
    else:
        stoploss = setup.ob_high + buffer
        risk = stoploss - entry
        min_risk = 10 ** (-pip_decimals)
        if risk <= min_risk:
            return None
        _, sl_list = find_swings(df15, 3, 3)
        target_price = None
        if sl_list:
            future_sl_prices = [float(df15["Low"].iloc[i]) for i in sl_list
                                if float(df15["Low"].iloc[i]) < entry]
            if future_sl_prices:
                target_price = max(future_sl_prices)
        if target_price is None:
            target_price = df15["Low"].min()
        if target_price >= entry:
            target_price = entry - 3 * risk
        rr = (entry - target_price) / risk
        if rr < MIN_RR_FLOOR - 1e-9:
            return None
        return SignalResult(
            instrument=instrument, direction="SHORT", setup_type=setup.setup_type,
            entry=round(entry, pip_decimals), stoploss=round(stoploss, pip_decimals),
            target=round(target_price, pip_decimals), rr=round(rr, 2),
            timestamp=entry_ts.astimezone(IST).isoformat(),
            call_type=call_type,
            trade_date=entry_ts.astimezone(IST).date().isoformat(),
            ob_high=round(setup.ob_high, pip_decimals),
            ob_low=round(setup.ob_low, pip_decimals),
            swing_price=round(setup.swing_price, pip_decimals),
            asset_class=asset_class,
            rr_tier=_rr_tier_label(rr),
            structural_start_ts=structural_start_ts,
        )


def scan_live_signal(
    instrument: str,
    df15: pd.DataFrame,
    df5: pd.DataFrame,
    now_ist: datetime,
    signals_today_count: int,
    daily_df: Optional[pd.DataFrame] = None,
    nifty_dir: Optional[str] = None,
    banknifty_dir: Optional[str] = None,
    is_expiry_close: bool = False,
    asset_class: str = "EQUITY",
    instrument_type: str = "stock",
    pip_decimals: int = 2,
) -> Optional[SignalResult]:
    """Try to detect a valid signal for a single instrument at the current
    moment. Applies all hard filters."""
    if df15 is None or df5 is None:
        return None
    if signals_today_count >= 2:
        return None

    setup = find_latest_setup(df15, asset_class=asset_class, instrument_type=instrument_type)
    if setup is not None and setup.setup_type == "BOS-OB-Retest" and daily_df is not None:
        # Trend filter: only take the breakout-continuation setup when the
        # daily-timeframe trend agrees with it. BOS-OB-Retest is a
        # continuation strategy — taking it against the larger trend is a
        # well-known way breakout systems get faked out in ranging markets.
        bias = _daily_bias(daily_df)
        if (setup.direction == "LONG" and bias != "UP") or \
           (setup.direction == "SHORT" and bias != "DOWN"):
            setup = None  # falls through to liquidity-sweep check below
    if setup is None:
        setup = find_liquidity_sweep_setup(df15, df5, asset_class=asset_class,
                                            instrument_type=instrument_type)
    if setup is None:
        return None
    if asset_class == "FOREX":
        # Skip 30-min pre-Friday-close window
        if _is_forex_friday_cutoff(now_ist):
            return None
        primary = _is_forex_primary_time(now_ist)
        secondary = _is_forex_secondary_time(now_ist)
        if not (primary or secondary):
            return None
        call_type = "FX-OVERLAP" if primary else "FX-LONDON-OPEN"
    else:
        if is_expiry_close:
            return None
        t = now_ist.time()
        if t < dtime(9, 30) or t > dtime(15, 15):
            return None
        # Conflicting index bias check (equities only)
        if nifty_dir and banknifty_dir and nifty_dir != "NEUTRAL" and banknifty_dir != "NEUTRAL":
            if nifty_dir != banknifty_dir:
                return None
        intraday_ok = _is_intraday_time(t)
        btst_ok = _is_btst_time(t)
        if not (intraday_ok or btst_ok):
            return None
        call_type = "INTRADAY"
        if btst_ok and daily_df is not None:
            bias = _daily_bias(daily_df)
            if (setup.direction == "LONG" and bias == "UP") or \
               (setup.direction == "SHORT" and bias == "DOWN"):
                call_type = "BTST"

    entry_pack = check_retest_and_trigger(df5, setup)
    if entry_pack is None:
        return None
    entry, entry_ts = entry_pack
    signal = build_signal_from_setup(
        instrument, setup, entry, entry_ts, df15, call_type,
        pip_decimals=pip_decimals, asset_class=asset_class,
    )
    return signal


def signal_to_dict(s: SignalResult) -> dict:
    return asdict(s)
