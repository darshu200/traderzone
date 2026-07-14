"""Candle archiving. yfinance only allows ~60 days of 15m/5m intraday history,
which caps how far back we can ever backtest using it directly. This module
fetches recent candles daily and upserts them into MongoDB, so over time we
build our own historical dataset that isn't limited by yfinance's window.

Safe to run multiple times per day — upserts on (instrument, interval, ts)
dedupe automatically.
"""
import logging

from constants import ALL_SYMBOLS
from data_source import fetch_candles

logger = logging.getLogger(__name__)

# Fetch a 5-day lookback each run (not just "today") so a missed day (app not
# running, machine off) still gets backfilled automatically on the next run,
# within yfinance's own short-interval limits.
ARCHIVE_INTERVALS = (("15m", "5d"), ("5m", "5d"))


async def archive_recent_candles(db) -> dict:
    """Fetch recent 15m/5m candles for every instrument and upsert into the
    `candle_archive` collection. Returns a summary dict for logging/API use."""
    summary = {"instruments_ok": 0, "rows_upserted": 0, "errors": []}

    for sym in ALL_SYMBOLS:
        for interval, period in ARCHIVE_INTERVALS:
            try:
                df = fetch_candles(sym, interval=interval, period=period)
                if df is None or df.empty:
                    continue
                for ts, row in df.iterrows():
                    vol = row.get("Volume", 0)
                    doc = {
                        "instrument": sym,
                        "interval": interval,
                        "ts": ts.isoformat(),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": float(vol) if vol == vol else 0.0,  # NaN check
                    }
                    await db.candle_archive.update_one(
                        {"instrument": sym, "interval": interval, "ts": doc["ts"]},
                        {"$set": doc},
                        upsert=True,
                    )
                    summary["rows_upserted"] += 1
                summary["instruments_ok"] += 1
            except Exception as e:
                logger.warning(f"Archive failed for {sym} {interval}: {e}")
                summary["errors"].append(f"{sym}:{interval}: {e}")

    logger.info(
        f"Candle archive run complete: {summary['instruments_ok']} instrument/"
        f"interval pairs ok, {summary['rows_upserted']} rows upserted, "
        f"{len(summary['errors'])} errors."
    )
    return summary


async def ensure_archive_indexes(db):
    """Call once at startup — cheap no-op if the index already exists."""
    await db.candle_archive.create_index(
        [("instrument", 1), ("interval", 1), ("ts", 1)], unique=True
    )
