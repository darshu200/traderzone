"""TradeSignal FastAPI backend — Equity + Forex."""
from __future__ import annotations

import io
import csv
import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta, time as dtime, timezone
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from constants import (
    INSTRUMENTS, ALL_SYMBOLS, EQUITY_SYMBOLS, FOREX_SYMBOLS, IST,
    LONDON_TZ, NY_TZ, FOREX_MAX_HOLD_HOURS, MAX_SIGNAL_STALENESS_MIN,
    BTST_MAX_HOLD_DAYS,
)
from data_source import get_live_quote, fetch_candles
from candle_archive import archive_recent_candles, ensure_archive_indexes
from backtest import simulate_outcome
from types import SimpleNamespace
from capital import compute_real_rr_at_detection, check_already_invalid
from capital_routes import create_capital_router
from strategy import (
    scan_live_signal, signal_to_dict, _daily_bias, _is_forex_market_open,
    _is_forex_primary_time, _is_forex_secondary_time,
    _london_session_open, _ny_session_open, _is_forex_friday_cutoff,
)
from backtest import run_backtest

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger("tradesignal")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="TradeSignal API")
api = APIRouter(prefix="/api")

# --------------------------- Pydantic Models --------------------------- #

class SettingsModel(BaseModel):
    active_instruments: List[str] = Field(default_factory=lambda: list(ALL_SYMBOLS))


class TradeUpdateModel(BaseModel):
    outcome: str  # 'WON' | 'LOST' | 'BREAKEVEN'
    exit_price: Optional[float] = None
    notes: Optional[str] = None


class BacktestRequest(BaseModel):
    instrument: str
    start_date: str  # YYYY-MM-DD
    end_date: str    # YYYY-MM-DD


# --------------------------- Helpers --------------------------- #

def _now_ist() -> datetime:
    return datetime.now(IST)


def _is_equity_market_open(now: Optional[datetime] = None) -> bool:
    now = now or _now_ist()
    if now.weekday() >= 5:
        return False
    t = now.time()
    return dtime(9, 15) <= t <= dtime(15, 30)


async def _get_active_symbols(asset_class: Optional[str] = None) -> List[str]:
    doc = await db.settings.find_one({"_id": "singleton"})
    active = (doc or {}).get("active_instruments", ALL_SYMBOLS)
    active = [s for s in active if s in INSTRUMENTS]
    if asset_class in ("EQUITY", "FOREX"):
        active = [s for s in active if INSTRUMENTS[s]["asset_class"] == asset_class]
    return active


def _annotate_stale(doc: dict) -> dict:
    """Attach a `stale` boolean if OPEN forex signal is older than max hold."""
    if doc.get("outcome") in (None, "OPEN") and doc.get("asset_class") == "FOREX":
        try:
            ts = datetime.fromisoformat(doc.get("timestamp"))
            age_h = (_now_ist() - ts).total_seconds() / 3600.0
            doc["stale"] = age_h > FOREX_MAX_HOLD_HOURS
            doc["age_hours"] = round(age_h, 1)
        except Exception:
            doc["stale"] = False
    else:
        doc["stale"] = False
    return doc


# --------------------------- Scheduler / Signal loop --------------------------- #

_last_scan_report: dict = {"last_run": None, "last_generated": 0, "errors": []}


def _is_expiry_close(now: datetime) -> bool:
    """Within 90 minutes of weekly Nifty option expiry (Thursday 3:30 pm)."""
    if now.weekday() != 3:
        return False
    expiry_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    return (expiry_close - now).total_seconds() <= 90 * 60 and now < expiry_close


def _quick_bias(sym: str) -> str:
    df = fetch_candles(sym, "15m", period="2d")
    if df is None or df.empty:
        return "NEUTRAL"
    ema20 = df["Close"].ewm(span=20, adjust=False).mean()
    ema50 = df["Close"].ewm(span=50, adjust=False).mean()
    last = df["Close"].iloc[-1]
    if last > ema20.iloc[-1] > ema50.iloc[-1]:
        return "UP"
    if last < ema20.iloc[-1] < ema50.iloc[-1]:
        return "DOWN"
    return "NEUTRAL"


_SCAN_CONCURRENCY = asyncio.Semaphore(8)  # bounded — avoids hammering NSE/yfinance


async def _scan_one_symbol(sym, meta, now, nifty_dir, bnifty_dir, expiry_close,
                            today_key, equity_open, forex_open):
    ac = meta["asset_class"]
    if ac == "EQUITY" and not equity_open:
        return False
    if ac == "FOREX" and not forex_open:
        return False
    async with _SCAN_CONCURRENCY:
        try:
            existing = await db.signals.count_documents({"instrument": sym, "trade_date": today_key})
            if existing >= 2:
                return False
            # Blocking yfinance/NSE calls moved off the event loop, and run
            # concurrently (bounded) across instruments instead of one by one.
            df15, df5, df_d = await asyncio.gather(
                asyncio.to_thread(fetch_candles, sym, "15m", period="5d"),
                asyncio.to_thread(fetch_candles, sym, "5m", period="5d"),
                asyncio.to_thread(fetch_candles, sym, "1d", period="120d"),
            )
            sig = scan_live_signal(
                sym, df15, df5, now,
                signals_today_count=existing,
                daily_df=df_d,
                nifty_dir=nifty_dir, banknifty_dir=bnifty_dir,
                is_expiry_close=expiry_close,
                asset_class=ac, instrument_type=meta.get("type", "stock"),
                pip_decimals=meta.get("pip_decimals", 2),
            )
            if sig is None:
                return False
            sig_d = signal_to_dict(sig)

            # Real-money context: capture the price at the moment of
            # detection (from the already-fetched df5, no extra network
            # call needed) — NOT the strategy's theoretical entry, which
            # can be stale by the time a human could actually act on it.
            try:
                dashboard_price = float(df5["Close"].iloc[-1])
                sig_d["dashboard_price"] = dashboard_price
                sig_d["real_rr_at_detection"] = compute_real_rr_at_detection(
                    dashboard_price, sig_d["stoploss"], sig_d["target"], sig_d["direction"])
                sig_d["already_invalid_at_detection"] = check_already_invalid(
                    dashboard_price, sig_d["stoploss"], sig_d["target"], sig_d["direction"])
            except Exception as e:
                logger.warning(f"Could not compute dashboard_price for {sym}: {e}")
                sig_d["dashboard_price"] = None
                sig_d["real_rr_at_detection"] = None
                sig_d["already_invalid_at_detection"] = None

            # Staleness check: if this signal's own entry timestamp is
            # already older than MAX_SIGNAL_STALENESS_MIN by the time its
            # confirmation chain finishes resolving, it's no longer
            # actionable — reject it rather than show a "fresh-looking"
            # card for a trade that's likely already near target or stopped.
            staleness_min = None
            confirm_span_min = None
            try:
                entry_dt = datetime.fromisoformat(sig_d["timestamp"])
                staleness_min = (now - entry_dt).total_seconds() / 60
                struct_ts = sig_d.get("structural_start_ts")
                if struct_ts:
                    struct_dt = datetime.fromisoformat(struct_ts)
                    confirm_span_min = (entry_dt - struct_dt).total_seconds() / 60
                    logger.info(
                        f"Signal timing [{sym}]: pattern started {struct_ts} -> "
                        f"entry confirmed {sig_d['timestamp']} "
                        f"(confirmation took {confirm_span_min:.1f} min) -> "
                        f"detected at {now.isoformat()} "
                        f"(operational lag {staleness_min:.1f} min)"
                    )
            except Exception:
                pass
            if staleness_min is not None and staleness_min > MAX_SIGNAL_STALENESS_MIN:
                logger.warning(f"Signal REJECTED (stale): {sym} entry_ts={sig_d['timestamp']} "
                               f"was {staleness_min:.1f} min old at detection time {now.isoformat()}")
                try:
                    await db.rejected_signals.insert_one({
                        "instrument": sym, "asset_class": ac,
                        "direction": sig_d.get("direction"),
                        "setup_type": sig_d.get("setup_type"),
                        "would_be_entry": sig_d.get("entry"),
                        "would_be_stoploss": sig_d.get("stoploss"),
                        "would_be_target": sig_d.get("target"),
                        "rr_tier": sig_d.get("rr_tier"),
                        "structural_start_ts": sig_d.get("structural_start_ts"),
                        "entry_ts": sig_d.get("timestamp"),
                        "staleness_min": round(staleness_min, 1),
                        "confirm_span_min": round(confirm_span_min, 1) if confirm_span_min is not None else None,
                        "detected_at": now.isoformat(),
                        "trade_date": today_key,
                        "reason": "stale",
                    })
                except Exception as e:
                    logger.warning(f"Could not persist rejected signal for {sym}: {e}")
                return False

            # Real dedup check: has THIS EXACT underlying setup (same entry
            # timestamp) already been inserted? Previously this checked "is
            # the last signal <30 min old by wall clock", which let the same
            # setup re-insert once >30 min of wall-clock time passed, even
            # though the setup itself (same entry_ts) hadn't changed.
            exact_dup = await db.signals.find_one({
                "instrument": sym, "direction": sig.direction,
                "trade_date": today_key, "timestamp": sig_d["timestamp"],
            })
            if exact_dup:
                return False
            sid = str(uuid.uuid4())
            sig_d["_id"] = sid
            sig_d["id"] = sid
            sig_d["outcome"] = "OPEN"
            sig_d["exit_price"] = None
            sig_d["r_multiple"] = None
            sig_d["created_at"] = now.isoformat()
            sig_d["detected_delay_min"] = round(staleness_min, 1) if staleness_min is not None else None
            try:
                await db.signals.insert_one(sig_d)
            except DuplicateKeyError:
                logger.info(f"Duplicate signal caught at DB level for {sym}, skipped")
                return False
            logger.info(f"Signal: {sym} [{ac}] {sig.direction} @ {sig.entry}")
            return True
        except Exception as e:
            logger.exception(f"Signal scan failed for {sym}: {e}")
            _last_scan_report["errors"].append(f"{sym}: {e}")
            return False


async def _refresh_watchlist_cache(active: List[str]):
    """Computes the same per-symbol row /api/watchlist used to compute live,
    on every single frontend request (get_live_quote + fetch_candles + the
    approaching-setup check), but does it here — once per cron tick — and
    upserts the result into db.watchlist_cache. /api/watchlist then just
    reads this collection, so opening/refreshing the dashboard is a plain
    Mongo read instead of 74 live NSE/yfinance calls in the request path.
    That live-on-every-request pattern was the actual cause of the 2-5 min
    dashboard load — not backend sleep, not network — it was re-doing (on
    every page view) almost the same fetch work the 2-min cron already
    does, but serially blocking the HTTP response until all of it finished.
    """
    from strategy import find_swings, atr as _atr

    def _row(sym: str) -> dict:
        meta = INSTRUMENTS[sym]
        q = get_live_quote(sym) or {"ltp": 0, "change": 0, "pct": 0, "source": "unavailable"}
        approaching = False
        try:
            df15 = fetch_candles(sym, "15m", period="3d")
            if df15 is not None and len(df15) >= 30:
                sh, sl = find_swings(df15, 3, 3)
                a = _atr(df15).iloc[-1]
                last_c = df15["Close"].iloc[-1]
                if sh:
                    lvl = df15["High"].iloc[sh[-1]]
                    if abs(lvl - last_c) <= 0.5 * a:
                        approaching = True
                if not approaching and sl:
                    lvl = df15["Low"].iloc[sl[-1]]
                    if abs(lvl - last_c) <= 0.5 * a:
                        approaching = True
        except Exception:
            pass
        return {
            "_id": sym, "symbol": sym, "name": meta["name"], "type": meta["type"],
            "asset_class": meta["asset_class"],
            "pip_decimals": meta.get("pip_decimals", 2),
            "price_prefix": meta.get("price_prefix", ""),
            "ltp": q.get("ltp"), "change": q.get("change"), "pct": q.get("pct"),
            "source": q.get("source"), "approaching_setup": approaching,
            "cached_at": _now_ist().isoformat(),
        }

    async def _row_bounded(s):
        async with _SCAN_CONCURRENCY:
            return await asyncio.to_thread(_row, s)

    rows = await asyncio.gather(*[_row_bounded(s) for s in active], return_exceptions=True)
    for r in rows:
        if isinstance(r, Exception):
            logger.warning(f"watchlist cache refresh failed for one symbol: {r}")
            continue
        try:
            await db.watchlist_cache.replace_one({"_id": r["_id"]}, r, upsert=True)
        except Exception as e:
            logger.warning(f"watchlist cache upsert failed for {r.get('symbol')}: {e}")


async def run_signal_scan():
    """Scheduler tick — evaluate all active symbols CONCURRENTLY (bounded),
    so a large instrument universe doesn't cause the scan to run longer than
    the scheduler's own tick interval. Each symbol's own filter (equity vs
    forex time-window) decides whether a signal is produced."""
    now = _now_ist()
    _last_scan_report["last_run"] = now.isoformat()
    _last_scan_report["errors"] = []
    equity_open = _is_equity_market_open(now)
    forex_open = _is_forex_market_open(now)
    if not (equity_open or forex_open):
        return

    active = await _get_active_symbols()
    nifty_dir = _quick_bias("NIFTY") if equity_open else "NEUTRAL"
    bnifty_dir = _quick_bias("BANKNIFTY") if equity_open else "NEUTRAL"
    expiry_close = _is_expiry_close(now)
    today_key = now.date().isoformat()

    results = await asyncio.gather(*[
        _scan_one_symbol(sym, INSTRUMENTS[sym], now, nifty_dir, bnifty_dir,
                          expiry_close, today_key, equity_open, forex_open)
        for sym in active
    ])
    _last_scan_report["last_generated"] = sum(1 for r in results if r)

    # Piggyback the watchlist cache refresh on this same tick — no extra
    # scheduler job, no extra 2-minute cadence, just reuses this run's
    # window so /api/watchlist stops doing live fetches on every page load.
    try:
        await _refresh_watchlist_cache(active)
    except Exception as e:
        logger.warning(f"watchlist cache refresh failed: {e}")


scheduler = AsyncIOScheduler(timezone=str(IST))


async def _run_daily_archive_job():
    await archive_recent_candles(db)


async def _auto_close_open_signals():
    """Check every OPEN signal against real 5-min price action since its
    entry, and close it the MOMENT price actually touches SL or target —
    using the exact same simulate_outcome logic the backtest already
    trusts. This replaces relying on manual end-of-day closing, which was
    producing outcome/r_multiple labels that didn't agree with each other
    (e.g. outcome='WON' with an exit price sitting at the stoploss)."""
    now = _now_ist()
    open_sigs = await db.signals.find({"outcome": "OPEN"}).to_list(500)
    for doc in open_sigs:
        sym = doc.get("instrument")
        meta = INSTRUMENTS.get(sym)
        if not meta:
            continue
        try:
            entry_ts = datetime.fromisoformat(doc["timestamp"])
            df5 = await asyncio.to_thread(fetch_candles, sym, "5m", period="10d")
            if df5 is None or df5.empty:
                continue
            df5_future = df5.loc[df5.index > entry_ts]
            if df5_future.empty:
                continue
            sig_like = SimpleNamespace(
                direction=doc["direction"], entry=doc["entry"],
                stoploss=doc["stoploss"], target=doc["target"],
            )
            result = simulate_outcome(sig_like, df5_future)
            if result["outcome"] in ("WON", "LOST"):
                await db.signals.update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "outcome": result["outcome"], "exit_price": result["exit_price"],
                        "r_multiple": result["r_multiple"], "closed_at": now.isoformat(),
                        "auto_closed": True,
                    }},
                )
                logger.info(f"Auto-closed {sym} {doc['direction']}: {result['outcome']} "
                           f"@ {result['exit_price']} (R={result['r_multiple']})")
                continue

            # End-of-day forced square-off for INTRADAY calls that hit
            # neither SL nor target during the session, at 15:25 IST — the
            # live price at that moment, matching when your broker actually
            # auto-squares-off intraday positions. BTST calls are allowed
            # to stay open past today.
            ac = meta.get("asset_class", "EQUITY")
            is_eod = (ac == "EQUITY" and now.time() >= dtime(15, 25)) or \
                     (ac == "FOREX" and _is_forex_friday_cutoff(now))
            if doc.get("call_type") == "INTRADAY" and is_eod:
                last_close = float(df5_future["Close"].iloc[-1])
                risk = abs(doc["entry"] - doc["stoploss"])
                if risk > 0:
                    r_mult = round((last_close - doc["entry"]) / risk, 2) if doc["direction"] == "LONG" \
                        else round((doc["entry"] - last_close) / risk, 2)
                else:
                    r_mult = 0.0
                outcome = "WON" if r_mult > 0.05 else ("LOST" if r_mult < -0.05 else "BREAKEVEN")
                await db.signals.update_one(
                    {"id": doc["id"]},
                    {"$set": {
                        "outcome": outcome, "exit_price": last_close, "r_multiple": r_mult,
                        "closed_at": now.isoformat(), "auto_closed": True,
                        "notes": "EOD square-off — neither SL nor target hit during session",
                    }},
                )
                logger.info(f"EOD square-off {sym} {doc['direction']}: {outcome} @ {last_close}")
                continue

            # BTST max-hold: if neither SL nor target hit within
            # BTST_MAX_HOLD_DAYS trading days, force-close rather than
            # leaving the position open indefinitely.
            if doc.get("call_type") == "BTST":
                trade_date = datetime.fromisoformat(doc["trade_date"]).date()
                days_held = (now.date() - trade_date).days
                if days_held >= BTST_MAX_HOLD_DAYS:
                    last_close = float(df5_future["Close"].iloc[-1])
                    risk = abs(doc["entry"] - doc["stoploss"])
                    if risk > 0:
                       
