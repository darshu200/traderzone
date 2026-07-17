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
                            "notes": f"BTST max hold ({BTST_MAX_HOLD_DAYS}d) reached — force-closed",
                        }},
                    )
                    logger.info(f"BTST max-hold closed {sym} {doc['direction']}: {outcome} @ {last_close}")
        except Exception as e:
            logger.warning(f"Auto-close check failed for {sym}: {e}")


@app.on_event("startup")
async def _on_startup():
    doc = await db.settings.find_one({"_id": "singleton"})
    if not doc:
        await db.settings.insert_one({"_id": "singleton", "active_instruments": list(ALL_SYMBOLS)})
    else:
        # Migration: ensure any newly-added instruments are enabled by default
        existing = set(doc.get("active_instruments", []))
        missing = [s for s in ALL_SYMBOLS if s not in existing]
        if missing:
            merged = list(existing) + missing
            await db.settings.update_one({"_id": "singleton"},
                                         {"$set": {"active_instruments": merged}})
    # Weekday broad scan: equity 9:15-15:30 IST + all DST-shifted forex windows
    # (London 08:00 IST-equivalents range 12:30-13:30; overlap ends up to 22:30 IST in winter DST).
    scheduler.add_job(
        run_signal_scan,
        CronTrigger(day_of_week="mon-fri", hour="9-23", minute="*/2", timezone=IST),
        id="weekday_scan", replace_existing=True,
    )
    # Saturday early morning: NY session tail after Friday close (up to ~04:00 IST in winter DST)
    scheduler.add_job(
        run_signal_scan,
        CronTrigger(day_of_week="sat", hour="0-4", minute="*/2", timezone=IST),
        id="sat_forex_tail", replace_existing=True,
    )
    # Sunday-open covers: forex reopens Sun 17:00 America/New_York which is
    # Mon 02:30 IST (summer/EDT) or Mon 03:30 IST (winter/EST). Only NY session
    # is open then (no London), so live signals still won't fire — but keeping
    # a scheduler tick alive here lets stale-flag / cache-warm logic run.
    scheduler.add_job(
        run_signal_scan,
        CronTrigger(day_of_week="sun,mon", hour="2-8", minute="*/2", timezone=IST),
        id="sun_open_tail", replace_existing=True,
    )
    # Auto-close: checks every OPEN signal against real price action and
    # closes it the moment SL/target is actually touched, instead of
    # relying on manual end-of-day closing.
    scheduler.add_job(
        _auto_close_open_signals,
        CronTrigger(day_of_week="mon-fri", hour="9-23", minute="*/2", timezone=IST),
        id="auto_close_weekday", replace_existing=True,
    )
    scheduler.add_job(
        _auto_close_open_signals,
        CronTrigger(day_of_week="sat", hour="0-4", minute="*/2", timezone=IST),
        id="auto_close_sat", replace_existing=True,
    )
    scheduler.add_job(
        _auto_close_open_signals,
        CronTrigger(day_of_week="sun,mon", hour="2-8", minute="*/2", timezone=IST),
        id="auto_close_sun", replace_existing=True,
    )
    await ensure_archive_indexes(db)
    # Defense-in-depth: even if application-level dedup logic ever has a gap,
    # the database itself refuses an exact duplicate (same instrument,
    # direction, day, and entry timestamp = the same underlying setup).
    try:
        await db.signals.create_index(
            [("instrument", 1), ("direction", 1), ("trade_date", 1), ("timestamp", 1)],
            unique=True, name="uniq_signal_setup",
        )
    except Exception as e:
        logger.warning(f"Could not create unique signals index (may already exist "
                       f"with duplicates from before this fix): {e}")
    # Daily candle archive: run once after both equity and forex sessions are
    # done for the day, so we build our own historical dataset beyond
    # yfinance's ~60-day intraday history limit. 23:55 IST covers equity
    # close (15:30) and the latest forex overlap end (~22:30 in winter DST).
    scheduler.add_job(
        _run_daily_archive_job,
        CronTrigger(hour=23, minute=55, timezone=IST),
        id="daily_candle_archive", replace_existing=True,
    )
    scheduler.start()
    logger.info("Scheduler started (equity + forex windows, IST).")


@app.on_event("shutdown")
async def _on_shutdown():
    try:
        scheduler.shutdown(wait=False)
    except Exception:
        pass
    client.close()


# --------------------------- API Endpoints --------------------------- #

@api.get("/")
async def root():
    return {"app": "TradeSignal", "status": "ok"}


@api.get("/health")
async def health():
    """Dedicated keepalive endpoint for external pingers (cron-job.org,
    UptimeRobot, etc). Deliberately does nothing except return instantly —
    no DB call, no yfinance/NSE call, no business logic — so pinging it
    every few minutes is free of side effects and never breaks even if
    /market/status's response shape changes later. Purpose: stop Render's
    free-tier web service from spinning down after 15 min of no inbound
    traffic, which would otherwise kill the in-process APScheduler cron."""
    return {"status": "alive", "server_time_utc": datetime.now(timezone.utc).isoformat()}


@api.get("/market/status")
async def market_status():
    now = _now_ist()
    # Compute the current-day forex session boundaries in IST for display.
    # We use the *native* London/NY session hours as truth and convert them
    # to IST here so the UI shows the actual DST-adjusted times.
    now_london = now.astimezone(LONDON_TZ)
    london_open = now_london.replace(hour=8, minute=0, second=0, microsecond=0)
    london_close = now_london.replace(hour=17, minute=0, second=0, microsecond=0)
    london_2h_end = london_open + timedelta(hours=2)
    now_ny = now.astimezone(NY_TZ)
    ny_open = now_ny.replace(hour=8, minute=0, second=0, microsecond=0)
    ny_close = now_ny.replace(hour=17, minute=0, second=0, microsecond=0)
    # Overlap = intersection of the two sessions on this calendar date
    overlap_start_utc = max(london_open.astimezone(IST), ny_open.astimezone(IST))
    overlap_end_utc = min(london_close.astimezone(IST), ny_close.astimezone(IST))

    def _fmt(dt):
        return dt.astimezone(IST).strftime("%H:%M")

    return {
        "server_time_ist": now.isoformat(),
        "server_time_london": now_london.isoformat(),
        "server_time_ny": now_ny.isoformat(),
        "equity_open": _is_equity_market_open(now),
        "forex_open": _is_forex_market_open(now),
        "is_open": _is_equity_market_open(now) or _is_forex_market_open(now),
        "in_forex_overlap": _is_forex_primary_time(now),
        "in_forex_london_open_window": _is_forex_secondary_time(now),
        "london_session_open": _london_session_open(now),
        "ny_session_open": _ny_session_open(now),
        "session_equity": "09:15 - 15:30 IST",
        # Dynamic IST windows, derived from London/NY local time (DST-safe):
        "session_forex_overlap_ist": f"{_fmt(overlap_start_utc)} - {_fmt(overlap_end_utc)} IST",
        "session_forex_secondary_ist": f"{_fmt(london_open)} - {_fmt(london_2h_end)} IST",
        "session_forex_london_local": "08:00 - 17:00 Europe/London",
        "session_forex_ny_local": "08:00 - 17:00 America/New_York",
        "last_scan": _last_scan_report,
    }


@api.get("/instruments")
async def list_instruments(asset_class: Optional[str] = None):
    items = [
        {"symbol": s, **{k: v for k, v in m.items() if k != "yf"}}
        for s, m in INSTRUMENTS.items()
    ]
    if asset_class in ("EQUITY", "FOREX"):
        items = [i for i in items if i["asset_class"] == asset_class]
    return items


@api.get("/watchlist")
async def watchlist(asset_class: Optional[str] = None):
    """Reads the cache populated by run_signal_scan's tick (via
    _refresh_watchlist_cache) — a plain Mongo lookup, no live NSE/yfinance
    calls in the request path. Data is at most ~2 min old, which is already
    the system's own update cadence everywhere else, so this adds no real
    staleness — it just stops re-fetching 74 symbols live on every page
    view/refresh, which is what was causing multi-minute dashboard loads."""
    active = await _get_active_symbols(asset_class=asset_class)
    if not active:
        return []
    cur = db.watchlist_cache.find({"_id": {"$in": active}}, {"_id": 0})
    rows = await cur.to_list(len(active))
    by_symbol = {r["symbol"]: r for r in rows}
    # Preserve active-list order; symbols not yet cached (e.g. right after a
    # fresh deploy, before the first scan tick has run) are simply omitted
    # rather than blocking the response — they'll appear within ~2 min.
    return [by_symbol[s] for s in active if s in by_symbol]


@api.get("/signals")
async def get_signals(
    limit: int = Query(default=200, le=500),
    date: Optional[str] = None,
    instrument: Optional[str] = None,
    asset_class: Optional[str] = None,
):
    q = {}
    if date: q["trade_date"] = date
    if instrument: q["instrument"] = instrument
    if asset_class in ("EQUITY", "FOREX"): q["asset_class"] = asset_class
    cur = db.signals.find(q, {"_id": 0}).sort("timestamp", -1).limit(limit)
    rows = await cur.to_list(limit)
    return [_annotate_stale(r) for r in rows]


@api.get("/signals/today")
async def get_today_signals(asset_class: Optional[str] = None):
    today = _now_ist().date().isoformat()
    # Today's signals, PLUS any still-open BTST signal from a previous day —
    # those are active positions meant to be evaluated for exit today, not
    # just shown on their entry day and then dropped from view.
    q = {"$or": [
        {"trade_date": today},
        {"call_type": "BTST", "outcome": "OPEN"},
    ]}
    if asset_class in ("EQUITY", "FOREX"):
        q = {"$and": [q, {"asset_class": asset_class}]}
    cur = db.signals.find(q, {"_id": 0}).sort("timestamp", -1)
    rows = await cur.to_list(500)
    return [_annotate_stale(r) for r in rows]


@api.patch("/signals/{sid}")
async def update_signal(sid: str, upd: TradeUpdateModel):
    doc = await db.signals.find_one({"id": sid})
    if not doc:
        raise HTTPException(404, "Signal not found")
    r_mult = None
    if upd.exit_price is not None and doc.get("entry") is not None and doc.get("stoploss") is not None:
        entry = float(doc["entry"]); sl = float(doc["stoploss"])
        risk = abs(entry - sl)
        if risk > 0:
            if doc["direction"] == "LONG":
                r_mult = round((float(upd.exit_price) - entry) / risk, 2)
            else:
                r_mult = round((entry - float(upd.exit_price)) / risk, 2)
    if upd.outcome == "BREAKEVEN":
        r_mult = 0.0
    # Guard against outcome/exit_price contradicting each other (this is
    # exactly how a manual entry produced outcome="WON" with an exit price
    # sitting at the stoploss before this check existed).
    if r_mult is not None and upd.outcome in ("WON", "LOST"):
        if upd.outcome == "WON" and r_mult < -0.05:
            raise HTTPException(400, f"outcome='WON' but computed r_multiple={r_mult} "
                                     f"(exit price implies a loss) — check exit_price")
        if upd.outcome == "LOST" and r_mult > 0.05:
            raise HTTPException(400, f"outcome='LOST' but computed r_multiple={r_mult} "
                                     f"(exit price implies a win) — check exit_price")
    await db.signals.update_one(
        {"id": sid},
        {"$set": {"outcome": upd.outcome, "exit_price": upd.exit_price,
                  "r_multiple": r_mult, "notes": upd.notes,
                  "closed_at": _now_ist().isoformat()}},
    )
    doc = await db.signals.find_one({"id": sid}, {"_id": 0})
    return _annotate_stale(doc)


@api.delete("/signals/{sid}")
async def delete_signal(sid: str):
    res = await db.signals.delete_one({"id": sid})
    if res.deleted_count == 0:
        raise HTTPException(404, "Signal not found")
    return {"deleted": True}


@api.get("/analytics")
async def analytics(asset_class: Optional[str] = None, forward_test_only: bool = False):
    q = {}
    if asset_class in ("EQUITY", "FOREX"): q["asset_class"] = asset_class
    if forward_test_only:
        settings_doc = await db.settings.find_one({"_id": "singleton"})
        fts = (settings_doc or {}).get("forward_test_start")
        if fts:
            q["timestamp"] = {"$gte": fts}
    cur = db.signals.find(q, {"_id": 0})
    signals = await cur.to_list(5000)

    won = [s for s in signals if s.get("outcome") == "WON"]
    lost = [s for s in signals if s.get("outcome") == "LOST"]
    be = [s for s in signals if s.get("outcome") == "BREAKEVEN"]
    closed = won + lost + be
    total = len(signals)
    win_rate = round(len(won) / len(closed) * 100, 2) if closed else 0.0
    r_vals = [s.get("r_multiple") or 0 for s in closed]
    avg_r = round(sum(r_vals) / len(r_vals), 2) if r_vals else 0.0

    by_setup: dict = {}
    for s in signals:
        k = s.get("setup_type", "unknown")
        by_setup[k] = by_setup.get(k, 0) + 1

    by_instrument: dict = {}
    for s in signals:
        k = s.get("instrument", "unknown")
        d = by_instrument.setdefault(k, {"total": 0, "won": 0, "lost": 0, "r": 0.0})
        d["total"] += 1
        if s.get("outcome") == "WON": d["won"] += 1
        if s.get("outcome") == "LOST": d["lost"] += 1
        if s.get("r_multiple") is not None:
            d["r"] += float(s["r_multiple"] or 0)

    # By call type — include both equity + forex labels
    by_type: dict = {}
    for s in signals:
        k = s.get("call_type", "INTRADAY")
        d = by_type.setdefault(k, {"total": 0, "won": 0, "lost": 0, "r": 0.0})
        d["total"] += 1
        if s.get("outcome") == "WON": d["won"] += 1
        if s.get("outcome") == "LOST": d["lost"] += 1
        if s.get("r_multiple") is not None:
            d["r"] += float(s["r_multiple"] or 0)

    # By asset class
    by_asset: dict = {}
    for s in signals:
        k = s.get("asset_class", "EQUITY")
        d = by_asset.setdefault(k, {"total": 0, "won": 0, "lost": 0, "r": 0.0})
        d["total"] += 1
        if s.get("outcome") == "WON": d["won"] += 1
        if s.get("outcome") == "LOST": d["lost"] += 1
        if s.get("r_multiple") is not None:
            d["r"] += float(s["r_multiple"] or 0)

    closed_sorted = sorted(closed, key=lambda x: x.get("closed_at") or x.get("timestamp") or "")
    equity = []
    cum = 0.0
    for s in closed_sorted:
        r = float(s.get("r_multiple") or 0)
        cum += r
        equity.append({
            "t": s.get("closed_at") or s.get("timestamp"),
            "cum_r": round(cum, 2),
            "instrument": s.get("instrument"),
            "asset_class": s.get("asset_class", "EQUITY"),
        })

    return {
        "asset_class": asset_class or "ALL",
        "total_signals": total,
        "closed": len(closed), "open": total - len(closed),
        "won": len(won), "lost": len(lost), "breakeven": len(be),
        "win_rate": win_rate, "avg_r": avg_r,
        "by_setup": by_setup, "by_instrument": by_instrument, "by_type": by_type,
        "by_asset_class": by_asset,
        "equity_curve": equity,
    }


@api.get("/settings")
async def get_settings():
    doc = await db.settings.find_one({"_id": "singleton"})
    if not doc:
        return {"active_instruments": list(ALL_SYMBOLS), "forward_test_start": None}
    return {"active_instruments": doc.get("active_instruments", list(ALL_SYMBOLS)),
            "forward_test_start": doc.get("forward_test_start")}


@api.post("/settings/mark-forward-test-start")
async def mark_forward_test_start():
    """Mark 'now' as the clean forward-test start point. Signals generated
    before this timestamp were produced during strategy tuning/iteration and
    shouldn't be counted as an honest track record — only what's generated
    from this point forward is a genuine, untouched paper-trading test."""
    now_iso = _now_ist().isoformat()
    await db.settings.update_one(
        {"_id": "singleton"}, {"$set": {"forward_test_start": now_iso}}, upsert=True,
    )
    return {"forward_test_start": now_iso}


@api.put("/settings")
async def update_settings(s: SettingsModel):
    filtered = [x for x in s.active_instruments if x in INSTRUMENTS]
    await db.settings.update_one(
        {"_id": "singleton"},
        {"$set": {"active_instruments": filtered}},
        upsert=True,
    )
    return {"active_instruments": filtered}


@api.post("/backtest")
async def backtest_route(req: BacktestRequest):
    if req.instrument not in INSTRUMENTS:
        raise HTTPException(400, "Unknown instrument")
    try:
        s = datetime.fromisoformat(req.start_date).date()
        e = datetime.fromisoformat(req.end_date).date()
    except Exception:
        raise HTTPException(400, "Invalid date format, use YYYY-MM-DD")
    if e < s:
        raise HTTPException(400, "end_date must be >= start_date")
    span = (e - s).days
    if span > 55:
        raise HTTPException(400, "Backtest window exceeds 55 days (yfinance intraday limit)")

    result = run_backtest(req.instrument, req.start_date, req.end_date)
    await db.backtests.insert_one({
        "_id": str(uuid.uuid4()),
        "instrument": req.instrument,
        "asset_class": INSTRUMENTS[req.instrument]["asset_class"],
        "start": req.start_date, "end": req.end_date,
        "summary": result["summary"], "count": len(result["signals"]),
        "created_at": _now_ist().isoformat(),
    })
    return result


@api.get("/backtest/csv")
async def backtest_csv(instrument: str, start_date: str, end_date: str):
    if instrument not in INSTRUMENTS:
        raise HTTPException(400, "Unknown instrument")
    try:
        s = datetime.fromisoformat(start_date).date()
        e = datetime.fromisoformat(end_date).date()
    except Exception:
        raise HTTPException(400, "Invalid date format")
    if (e - s).days > 55:
        raise HTTPException(400, "Backtest window exceeds 55 days")
    result = run_backtest(instrument, start_date, end_date)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "instrument", "asset_class", "direction", "setup_type", "call_type",
        "timestamp", "entry", "stoploss", "target", "rr",
        "outcome", "exit_price", "r_multiple",
    ])
    for s in result["signals"]:
        writer.writerow([
            s.get("instrument"), s.get("asset_class"), s.get("direction"),
            s.get("setup_type"), s.get("call_type"),
            s.get("timestamp"), s.get("entry"), s.get("stoploss"), s.get("target"), s.get("rr"),
            s.get("outcome"), s.get("exit_price"), s.get("r_multiple"),
        ])
    buf.seek(0)
    fname = f"backtest_{instrument}_{start_date}_{end_date}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@api.post("/dev/dedupe-signals")
async def dedupe_signals():
    """One-time cleanup: remove exact-duplicate signals (same instrument,
    direction, trade_date, and entry timestamp) that were inserted before
    the dedup-logic fix, so the new unique index can be created. Keeps the
    earliest-created copy of each duplicate group."""
    pipeline = [
        {"$group": {
            "_id": {"instrument": "$instrument", "direction": "$direction",
                     "trade_date": "$trade_date", "timestamp": "$timestamp"},
            "ids": {"$push": "$_id"}, "count": {"$sum": 1},
        }},
        {"$match": {"count": {"$gt": 1}}},
    ]
    removed = 0
    groups = []
    async for g in db.signals.aggregate(pipeline):
        ids = g["ids"]
        to_remove = ids[1:]  # keep the first, remove the rest
        if to_remove:
            result = await db.signals.delete_many({"_id": {"$in": to_remove}})
            removed += result.deleted_count
            groups.append({"key": g["_id"], "removed": result.deleted_count})
    return {"duplicate_groups_found": len(groups), "total_removed": removed, "groups": groups}


@api.get("/signals/rejected")
async def get_rejected_signals(date: Optional[str] = None, asset_class: Optional[str] = None):
    """Signals that were detected but rejected for being too stale to act
    on (MAX_SIGNAL_STALENESS_MIN). Shows how much opportunity is being
    missed to confirmation-chain delay + data lag, so it's an informed
    decision rather than a guess."""
    q = {"trade_date": date or _now_ist().date().isoformat()}
    if asset_class in ("EQUITY", "FOREX"):
        q["asset_class"] = asset_class
    cur = db.rejected_signals.find(q, {"_id": 0}).sort("detected_at", -1)
    rows = await cur.to_list(500)
    return {
        "count": len(rows),
        "by_setup_type": {
            st: sum(1 for r in rows if r.get("setup_type") == st)
            for st in ("BOS-OB-Retest", "Liquidity-Sweep")
        },
        "avg_staleness_min": round(sum(r["staleness_min"] for r in rows) / len(rows), 1) if rows else 0,
        "rows": rows,
    }


@api.post("/dev/run-scan")
async def dev_run_scan():
    """Trigger a manual scan (useful for testing / off-hours)."""
    await run_signal_scan()
    return {"triggered": True, "report": _last_scan_report}


@api.post("/dev/run-archive")
async def dev_run_archive():
    """Trigger a manual candle-archive run right now (normally runs once
    daily at 23:55 IST). Useful to test immediately or backfill on demand."""
    summary = await archive_recent_candles(db)
    return {"triggered": True, "summary": summary}


@api.get("/dev/archive-status")
async def dev_archive_status():
    """Quick counts of what's in the candle_archive collection so far."""
    total = await db.candle_archive.count_documents({})
    pipeline = [
        {"$group": {"_id": {"instrument": "$instrument", "interval": "$interval"},
                     "count": {"$sum": 1},
                     "min_ts": {"$min": "$ts"}, "max_ts": {"$max": "$ts"}}},
        {"$sort": {"_id.instrument": 1, "_id.interval": 1}},
    ]
    breakdown = [
        {"instrument": r["_id"]["instrument"], "interval": r["_id"]["interval"],
         "count": r["count"], "from": r["min_ts"], "to": r["max_ts"]}
        async for r in db.candle_archive.aggregate(pipeline)
    ]
    return {"total_rows": total, "breakdown": breakdown}


app.include_router(api)
app.include_router(create_capital_router(db, _now_ist), prefix="/api")
app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)
