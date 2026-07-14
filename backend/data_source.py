"""Data source utilities. Uses NSE India unofficial JSON for live quotes with
fallback to yfinance for both historical and live data. All calls are cached
in-memory for a short TTL to avoid rate limits."""
from __future__ import annotations

import logging
import math
import os
import tempfile
import time
from typing import Optional

import pandas as pd
import requests
import yfinance as yf

from constants import INSTRUMENTS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# yfinance hardening: Yahoo's "Invalid Crumb" 401 is a widespread, current
# issue tied to their anti-scraping cookie/token check, not specific to this
# app. curl_cffi impersonates a real browser's TLS fingerprint, which yfinance
# officially recommends as the workaround. We build one shared session and
# reuse it everywhere yfinance is called.
# ---------------------------------------------------------------------------
_yf_session = None


def _get_yf_session():
    """Return a curl_cffi session impersonating Chrome, for yfinance calls.
    Falls back to yfinance's default session if curl_cffi is unavailable."""
    global _yf_session
    if _yf_session is not None:
        return _yf_session
    try:
        from curl_cffi import requests as cffi_requests
        _yf_session = cffi_requests.Session(impersonate="chrome")
    except Exception as e:
        logger.warning(f"curl_cffi session unavailable, falling back to default: {e}")
        _yf_session = None
    return _yf_session


def _yf_download_with_retry(*, max_attempts: int = 3, backoff_base: float = 1.5, **kwargs):
    """Wrapper around yf.download with the curl_cffi session and retry-with-
    backoff, since the crumb/401 error can be intermittent even after the
    session fix."""
    session = _get_yf_session()
    if session is not None:
        kwargs["session"] = session
    last_exc = None
    for attempt in range(1, max_attempts + 1):
        try:
            df = yf.download(**kwargs)
            if df is not None and not df.empty:
                return df
            last_exc = None
        except Exception as e:
            last_exc = e
            logger.warning(f"yfinance download attempt {attempt}/{max_attempts} "
                           f"failed for {kwargs.get('tickers')}: {e}")
        if attempt < max_attempts:
            time.sleep(backoff_base * attempt)
    if last_exc:
        logger.warning(f"yfinance download exhausted retries: {last_exc}")
    return None


# Fix TzCache: default AppData location can fail on Windows if the folder
# already exists in a bad state; point it at a writable temp dir instead.
try:
    _tz_cache_dir = os.path.join(tempfile.gettempdir(), "tradesignal_yf_tzcache")
    os.makedirs(_tz_cache_dir, exist_ok=True)
    yf.set_tz_cache_location(_tz_cache_dir)
except Exception as e:
    logger.warning(f"Could not set yfinance tz cache location: {e}")

# Simple in-memory TTL cache: {key: (expires_ts, value)}
_cache: dict = {}


def _cache_get(key: str):
    v = _cache.get(key)
    if not v:
        return None
    if time.time() > v[0]:
        _cache.pop(key, None)
        return None
    return v[1]


def _cache_set(key: str, value, ttl: int):
    _cache[key] = (time.time() + ttl, value)

_NSE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.nseindia.com/",
}

_nse_session: Optional[requests.Session] = None
_nse_last_seed = 0.0
_nse_disabled_until = 0.0  # unix ts; set when NSE blocks us


def _get_nse_session() -> Optional[requests.Session]:
    global _nse_session, _nse_last_seed, _nse_disabled_until
    now = time.time()
    if now < _nse_disabled_until:
        return None
    if _nse_session is None or (now - _nse_last_seed) > 600:
        s = requests.Session()
        s.headers.update(_NSE_HEADERS)
        try:
            s.get("https://www.nseindia.com/", timeout=5)
            s.get("https://www.nseindia.com/get-quotes/equity?symbol=RELIANCE", timeout=5)
            _nse_session = s
            _nse_last_seed = now
        except Exception as e:
            logger.warning(f"NSE session seed failed: {e}")
            _nse_disabled_until = now + 45  # short lockout — recover fast from
            return None                     # transient blips instead of a 5-min blackout
    return _nse_session


def _finite(*vals: float) -> bool:
    """True only if every value is a real, finite number. Guards quote
    fetchers against NaN/Infinity slipping into a response — a value like
    that reaching Starlette's JSONResponse.render() raises 'Out of range
    float values are not JSON compliant' and 500s the ENTIRE endpoint, not
    just the one bad row."""
    return all(isinstance(v, (int, float)) and math.isfinite(v) for v in vals)


def fetch_nse_quote(symbol: str) -> Optional[dict]:
    """Fetch live quote from NSE India. Returns None on failure."""
    global _nse_disabled_until
    meta = INSTRUMENTS.get(symbol)
    if not meta:
        return None
    # Skip NSE for non-equity assets (forex/commodity)
    if meta.get("asset_class") != "EQUITY" or not meta.get("nse"):
        return None
    session = _get_nse_session()
    if session is None:
        return None
    try:
        if meta["type"] == "index":
            url = "https://www.nseindia.com/api/allIndices"
            r = session.get(url, timeout=6)
            if r.status_code != 200:
                _nse_disabled_until = time.time() + 300
                return None
            data = r.json()
            for row in data.get("data", []):
                if row.get("index") == meta["nse"]:
                    ltp = float(row.get("last", 0))
                    change = float(row.get("variation", 0))
                    pct = float(row.get("percentChange", 0))
                    if not _finite(ltp, change, pct):
                        logger.warning(f"NSE index quote for {symbol} had a non-finite "
                                       f"value (ltp={ltp}, change={change}, pct={pct}), discarding")
                        return None
                    return {"ltp": ltp, "change": change, "pct": pct, "source": "nse"}
        else:
            url = f"https://www.nseindia.com/api/quote-equity?symbol={meta['nse']}"
            r = session.get(url, timeout=6)
            if r.status_code != 200:
                _nse_disabled_until = time.time() + 300
                return None
            data = r.json()
            price_info = data.get("priceInfo", {})
            ltp = float(price_info.get("lastPrice", 0))
            change = float(price_info.get("change", 0))
            pct = float(price_info.get("pChange", 0))
            if not _finite(ltp, change, pct):
                logger.warning(f"NSE equity quote for {symbol} had a non-finite "
                               f"value (ltp={ltp}, change={change}, pct={pct}), discarding")
                return None
            return {"ltp": ltp, "change": change, "pct": pct, "source": "nse"}
    except Exception as e:
        logger.warning(f"NSE quote failed for {symbol}: {e}")
        _nse_disabled_until = time.time() + 300
        return None
    return None


def fetch_yf_quote(symbol: str) -> Optional[dict]:
    """Live quote from yfinance (used as fallback)."""
    meta = INSTRUMENTS.get(symbol)
    if not meta:
        return None
    try:
        df = _yf_download_with_retry(
            tickers=meta["yf"], period="2d", interval="1m",
            progress=False, auto_adjust=False, threads=False,
        )
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        last = float(df["Close"].iloc[-1])
        # Prev day close via daily
        d = _yf_download_with_retry(tickers=meta["yf"], period="5d", interval="1d",
                        progress=False, auto_adjust=False, threads=False)
        if d is None or d.empty:
            d = df
        if isinstance(d.columns, pd.MultiIndex):
            d.columns = d.columns.get_level_values(0)
        prev = float(d["Close"].iloc[-2]) if len(d) >= 2 else last
        change = last - prev
        pct = (change / prev * 100.0) if prev else 0.0
        if not _finite(last, change, pct):
            logger.warning(f"yfinance quote for {symbol} had a non-finite value "
                           f"(last={last}, change={change}, pct={pct}), discarding")
            return None
        return {"ltp": last, "change": change, "pct": pct, "source": "yfinance"}
    except Exception as e:
        logger.warning(f"yfinance quote failed for {symbol}: {e}")
        return None


def get_live_quote(symbol: str) -> Optional[dict]:
    cache_key = f"quote:{symbol}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    q = fetch_nse_quote(symbol)
    if q is None:
        q = fetch_yf_quote(symbol)
    if q is not None:
        _cache_set(cache_key, q, ttl=45)
    return q


# ---------------------------------------------------------------------------
# Option chain sentiment (NIFTY / BANKNIFTY only). NSE's free endpoint only
# returns a LIVE snapshot — there is no free historical time series for this,
# so it cannot be backtested, only used for live/forward signal context.
# ---------------------------------------------------------------------------
_OPTION_CHAIN_SYMBOLS = {"NIFTY": "NIFTY", "BANKNIFTY": "BANKNIFTY"}


def get_option_chain_sentiment(symbol: str) -> Optional[dict]:
    """Fetch live NSE option chain for NIFTY/BANKNIFTY and compute PCR,
    OI-based bias, and Max Pain strike. Returns None on failure or if the
    symbol isn't NIFTY/BANKNIFTY. Live-only — no historical backtest support."""
    nse_symbol = _OPTION_CHAIN_SYMBOLS.get(symbol)
    if not nse_symbol:
        return None
    cache_key = f"optionchain:{symbol}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    session = _get_nse_session()
    if session is None:
        logger.warning(f"Option chain [{symbol}]: no NSE session available")
        return None
    try:
        url = f"https://www.nseindia.com/api/option-chain-indices?symbol={nse_symbol}"
        r = session.get(url, timeout=8)
        if r.status_code != 200:
            logger.warning(f"Option chain [{symbol}]: NSE returned HTTP {r.status_code}")
            return None
        payload = r.json()
        records = payload.get("records", {})
        underlying = float(records.get("underlyingValue", 0))
        expiry_dates = records.get("expiryDates", [])
        if not expiry_dates or underlying <= 0:
            logger.warning(f"Option chain [{symbol}]: no expiry_dates or underlying<=0 "
                           f"(underlying={underlying}, expiry_dates={bool(expiry_dates)})")
            return None
        nearest_expiry = expiry_dates[0]
        rows = [row for row in records.get("data", [])
                if row.get("expiryDate") == nearest_expiry]
        if not rows:
            logger.warning(f"Option chain [{symbol}]: no rows for nearest expiry {nearest_expiry}")
            return None

        total_ce_oi = 0.0
        total_pe_oi = 0.0
        total_ce_vol = 0.0
        total_pe_vol = 0.0
        strikes: dict[float, dict] = {}
        for row in rows:
            strike = float(row.get("strikePrice", 0))
            ce = row.get("CE") or {}
            pe = row.get("PE") or {}
            ce_oi = float(ce.get("openInterest", 0) or 0)
            pe_oi = float(pe.get("openInterest", 0) or 0)
            total_ce_oi += ce_oi
            total_pe_oi += pe_oi
            total_ce_vol += float(ce.get("totalTradedVolume", 0) or 0)
            total_pe_vol += float(pe.get("totalTradedVolume", 0) or 0)
            strikes[strike] = {"ce_oi": ce_oi, "pe_oi": pe_oi}

        if total_ce_oi <= 0 and total_pe_oi <= 0:
            logger.warning(f"Option chain [{symbol}]: zero OI on both sides, "
                           f"{len(rows)} rows parsed for expiry {nearest_expiry}")
            return None
        pcr = round(total_pe_oi / total_ce_oi, 3) if total_ce_oi > 0 else None

        # Max Pain: strike minimizing total intrinsic payout to option buyers
        # at expiry, across all candidate settlement strikes.
        candidate_strikes = sorted(strikes.keys())
        max_pain_strike = None
        min_payout = None
        for k in candidate_strikes:
            payout = 0.0
            for s, oi in strikes.items():
                if k > s:
                    payout += oi["ce_oi"] * (k - s)
                if s > k:
                    payout += oi["pe_oi"] * (s - k)
            if min_payout is None or payout < min_payout:
                min_payout = payout
                max_pain_strike = k

        # Simple OI-based bias: more put OI written (relative to calls) is
        # typically read as support/bullish positioning, and vice versa.
        # This is a sentiment heuristic, not a precise directional signal.
        if pcr is None:
            oi_bias = "NEUTRAL"
        elif pcr > 1.2:
            oi_bias = "BULLISH"
        elif pcr < 0.8:
            oi_bias = "BEARISH"
        else:
            oi_bias = "NEUTRAL"

        result = {
            "symbol": symbol,
            "underlying": underlying,
            "expiry": nearest_expiry,
            "pcr": pcr,
            "oi_bias": oi_bias,
            "max_pain": max_pain_strike,
            "total_ce_oi": int(total_ce_oi),
            "total_pe_oi": int(total_pe_oi),
            "total_ce_volume": int(total_ce_vol),
            "total_pe_volume": int(total_pe_vol),
            "source": "nse",
            "note": "Live snapshot only — not available for historical backtesting.",
        }
        _cache_set(cache_key, result, ttl=60)
        return result
    except Exception as e:
        logger.warning(f"Option chain fetch failed for {symbol}: {e}")
        return None


def fetch_candles(symbol: str, interval: str, period: str = "5d") -> Optional[pd.DataFrame]:
    """Fetch OHLCV from yfinance with 60s cache.
    interval: '5m', '15m', '1d'
    Returns DataFrame with columns Open, High, Low, Close, Volume and datetime index in IST.
    """
    cache_key = f"candles:{symbol}:{interval}:{period}"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    meta = INSTRUMENTS.get(symbol)
    if not meta:
        return None
    try:
        df = _yf_download_with_retry(
            tickers=meta["yf"], period=period, interval=interval,
            progress=False, auto_adjust=False, threads=False,
        )
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert("Asia/Kolkata")
        out = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        _cache_set(cache_key, out, ttl=60)
        return out
    except Exception as e:
        logger.warning(f"fetch_candles failed for {symbol} {interval}: {e}")
        return None


def fetch_candles_range(symbol: str, interval: str, start: str, end: str) -> Optional[pd.DataFrame]:
    """Fetch OHLCV between explicit dates (YYYY-MM-DD)."""
    meta = INSTRUMENTS.get(symbol)
    if not meta:
        return None
    try:
        df = _yf_download_with_retry(
            tickers=meta["yf"], start=start, end=end, interval=interval,
            progress=False, auto_adjust=False, threads=False,
        )
        if df is None or df.empty:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        df.index = df.index.tz_convert("Asia/Kolkata")
        return df[["Open", "High", "Low", "Close", "Volume"]].copy()
    except Exception as e:
        logger.warning(f"fetch_candles_range failed: {e}")
        return None
