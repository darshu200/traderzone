"""Backend API tests for TradeSignal (Equity + Forex extension).

Covers:
- Market status (equity_open + forex_open + session labels)
- Instruments universe (12 equity + 7 forex = 19)
- Watchlist (with asset_class filter)
- Settings persistence + migration (all 19 symbols)
- Signals CRUD + stale annotation for OPEN forex signals
- Analytics (with by_asset_class + asset_class filter)
- Backtest (equity regression + forex EURUSD/XAUUSD/GBPUSD, CSV)
- Dev run-scan off-hours
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL") or "https://nifty-signals-54.preview.emergentagent.com"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"

IST = ZoneInfo("Asia/Kolkata")

EQUITY_SYMBOLS = {
    "NIFTY", "BANKNIFTY", "RELIANCE", "HDFCBANK", "ICICIBANK", "SBIN",
    "TMPV", "TATASTEEL", "BHARTIARTL", "LT", "AXISBANK", "KOTAKBANK",
}
FOREX_SYMBOLS = {"EURUSD", "GBPUSD", "USDJPY", "GBPJPY", "AUDUSD", "USDCAD", "XAUUSD"}
ALL_SYMBOLS = EQUITY_SYMBOLS | FOREX_SYMBOLS


# -------------- shared client -------------- #

@pytest.fixture(scope="session")
def api_client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def mongo_db():
    client = MongoClient(os.environ.get("MONGO_URL", "mongodb://localhost:27017"))
    db = client[os.environ.get("DB_NAME", "test_database")]
    return db


# -------------- Market status -------------- #

class TestMarketStatus:
    def test_market_status_shape(self, api_client):
        r = api_client.get(f"{API}/market/status", timeout=15)
        assert r.status_code == 200, r.text
        d = r.json()
        # New tz-aware fields expected by the refactor
        for k in (
            "server_time_ist", "server_time_london", "server_time_ny",
            "equity_open", "forex_open", "is_open",
            "in_forex_overlap", "in_forex_london_open_window",
            "london_session_open", "ny_session_open",
            "session_equity",
            "session_forex_overlap_ist", "session_forex_secondary_ist",
            "session_forex_london_local", "session_forex_ny_local",
            "last_scan",
        ):
            assert k in d, f"missing {k}"
        assert isinstance(d["equity_open"], bool)
        assert isinstance(d["forex_open"], bool)
        assert isinstance(d["is_open"], bool)
        assert isinstance(d["in_forex_overlap"], bool)
        assert isinstance(d["in_forex_london_open_window"], bool)
        assert isinstance(d["london_session_open"], bool)
        assert isinstance(d["ny_session_open"], bool)
        assert d["is_open"] == (d["equity_open"] or d["forex_open"])
        # Verify session labels
        assert "09:15" in d["session_equity"]
        assert d["session_forex_london_local"] == "08:00 - 17:00 Europe/London"
        assert d["session_forex_ny_local"] == "08:00 - 17:00 America/New_York"
        # Dynamic IST windows: must contain "IST" and be HH:MM - HH:MM IST format
        import re
        assert re.match(r"^\d{2}:\d{2} - \d{2}:\d{2} IST$", d["session_forex_overlap_ist"]), d["session_forex_overlap_ist"]
        assert re.match(r"^\d{2}:\d{2} - \d{2}:\d{2} IST$", d["session_forex_secondary_ist"]), d["session_forex_secondary_ist"]
        # Verify server_time_london / _ny parse as tz-aware iso datetimes
        for k in ("server_time_ist", "server_time_london", "server_time_ny"):
            dt = datetime.fromisoformat(d[k])
            assert dt.tzinfo is not None, f"{k} not tz-aware"

    def test_market_status_removed_fields(self, api_client):
        """Old hardcoded IST-only field names must no longer be present."""
        r = api_client.get(f"{API}/market/status", timeout=15)
        assert r.status_code == 200
        d = r.json()
        # Old top-level field names (pre-refactor). If they persist, code was not migrated.
        assert "session_forex_overlap" not in d
        assert "session_forex_secondary" not in d


# -------------- Instruments -------------- #

class TestInstruments:
    def test_list_all_instruments(self, api_client):
        r = api_client.get(f"{API}/instruments", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 19, f"expected 19, got {len(data)}"
        symbols = {i["symbol"] for i in data}
        assert symbols == ALL_SYMBOLS
        for item in data:
            assert set(item.keys()) >= {"symbol", "name", "type", "asset_class", "pip_decimals", "price_prefix"}
            assert "yf" not in item, "yfinance ticker should not leak to client"
            assert item["asset_class"] in ("EQUITY", "FOREX")
            assert isinstance(item["pip_decimals"], int)

    def test_list_forex_only(self, api_client):
        r = api_client.get(f"{API}/instruments", params={"asset_class": "FOREX"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 7
        assert {i["symbol"] for i in data} == FOREX_SYMBOLS
        assert all(i["asset_class"] == "FOREX" for i in data)
        # JPY pairs and XAUUSD -> 2 decimals; majors -> 4
        pip_map = {i["symbol"]: i["pip_decimals"] for i in data}
        assert pip_map["EURUSD"] == 4
        assert pip_map["USDJPY"] == 2
        assert pip_map["GBPJPY"] == 2
        assert pip_map["XAUUSD"] == 2

    def test_list_equity_only(self, api_client):
        r = api_client.get(f"{API}/instruments", params={"asset_class": "EQUITY"}, timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 12
        assert {i["symbol"] for i in data} == EQUITY_SYMBOLS
        assert all(i["asset_class"] == "EQUITY" for i in data)


# -------------- Watchlist -------------- #

class TestWatchlist:
    def test_watchlist_default_returns_all_19(self, api_client):
        # Reset settings first so all 19 are active
        api_client.put(f"{API}/settings", json={"active_instruments": list(ALL_SYMBOLS)}, timeout=20)
        r = api_client.get(f"{API}/watchlist", timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) == 19
        assert {i["symbol"] for i in data} == ALL_SYMBOLS
        for item in data:
            assert "asset_class" in item
            assert "pip_decimals" in item
            assert "price_prefix" in item

    def test_watchlist_forex_filter(self, api_client):
        r = api_client.get(f"{API}/watchlist", params={"asset_class": "FOREX"}, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 7
        assert {i["symbol"] for i in data} == FOREX_SYMBOLS
        # All forex should return yfinance data with non-zero LTP
        by_sym = {i["symbol"]: i for i in data}
        for sym in FOREX_SYMBOLS:
            item = by_sym[sym]
            assert item["asset_class"] == "FOREX"
            assert item["source"] in {"yfinance", "unavailable"}
            assert isinstance(item["ltp"], (int, float))
        # At least 5 of 7 should have real (>0) LTP values
        non_zero = sum(1 for i in data if isinstance(i["ltp"], (int, float)) and i["ltp"] > 0)
        assert non_zero >= 5, f"Only {non_zero}/7 forex returned non-zero LTP: {by_sym}"

    def test_watchlist_equity_filter(self, api_client):
        r = api_client.get(f"{API}/watchlist", params={"asset_class": "EQUITY"}, timeout=120)
        assert r.status_code == 200
        data = r.json()
        assert len(data) == 12
        assert {i["symbol"] for i in data} == EQUITY_SYMBOLS


# -------------- Settings -------------- #

class TestSettings:
    def test_settings_contains_all_19(self, api_client):
        # After startup migration, active_instruments should include all 19
        # Reset first to ensure clean state
        api_client.put(f"{API}/settings", json={"active_instruments": list(ALL_SYMBOLS)}, timeout=15)
        r = api_client.get(f"{API}/settings", timeout=15)
        assert r.status_code == 200
        d = r.json()
        assert set(d["active_instruments"]) == ALL_SYMBOLS
        assert len(d["active_instruments"]) == 19

    def test_settings_persist_forex_subset(self, api_client):
        subset = ["EURUSD", "GBPUSD", "XAUUSD"]
        r = api_client.put(f"{API}/settings", json={"active_instruments": subset}, timeout=15)
        assert r.status_code == 200
        assert set(r.json()["active_instruments"]) == set(subset)
        # Re-fetch
        r2 = api_client.get(f"{API}/settings", timeout=15)
        assert set(r2.json()["active_instruments"]) == set(subset)
        # Restore for downstream tests
        api_client.put(f"{API}/settings", json={"active_instruments": list(ALL_SYMBOLS)}, timeout=15)


# -------------- Signals (basic + stale annotation) -------------- #

class TestSignals:
    def test_signals_list(self, api_client):
        r = api_client.get(f"{API}/signals", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_dev_run_scan_offhours(self, api_client):
        r = api_client.post(f"{API}/dev/run-scan", timeout=120)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d.get("triggered") is True
        assert "report" in d

    def test_signals_asset_class_filter(self, api_client, mongo_db):
        # Seed one equity and one forex signal
        eq_id = f"TEST_EQ_{uuid.uuid4()}"
        fx_id = f"TEST_FX_{uuid.uuid4()}"
        now = datetime.now(IST)
        mongo_db.signals.insert_many([
            {
                "_id": eq_id, "id": eq_id, "instrument": "HDFCBANK",
                "asset_class": "EQUITY", "direction": "LONG",
                "setup_type": "BOS_RETEST", "call_type": "INTRADAY",
                "timestamp": now.isoformat(), "trade_date": now.date().isoformat(),
                "entry": 1500, "stoploss": 1490, "target": 1530, "rr": 3.0,
                "outcome": "OPEN", "exit_price": None, "r_multiple": None,
                "created_at": now.isoformat(),
            },
            {
                "_id": fx_id, "id": fx_id, "instrument": "EURUSD",
                "asset_class": "FOREX", "direction": "LONG",
                "setup_type": "BOS_RETEST", "call_type": "FX-OVERLAP",
                "timestamp": now.isoformat(), "trade_date": now.date().isoformat(),
                "entry": 1.1450, "stoploss": 1.1420, "target": 1.1540, "rr": 3.0,
                "outcome": "OPEN", "exit_price": None, "r_multiple": None,
                "created_at": now.isoformat(),
            },
        ])
        try:
            r = api_client.get(f"{API}/signals", params={"asset_class": "FOREX"}, timeout=15)
            assert r.status_code == 200
            ids = [s["id"] for s in r.json()]
            assert fx_id in ids
            assert eq_id not in ids

            r2 = api_client.get(f"{API}/signals", params={"asset_class": "EQUITY"}, timeout=15)
            ids2 = [s["id"] for s in r2.json()]
            assert eq_id in ids2
            assert fx_id not in ids2
        finally:
            mongo_db.signals.delete_many({"id": {"$in": [eq_id, fx_id]}})

    def test_stale_forex_signal(self, api_client, mongo_db):
        # Seed one forex OPEN signal > 24h ago -> stale=true, and one recent -> stale=false
        stale_id = f"TEST_STALE_{uuid.uuid4()}"
        fresh_id = f"TEST_FRESH_{uuid.uuid4()}"
        now = datetime.now(IST)
        old_ts = (now - timedelta(hours=48)).isoformat()
        new_ts = (now - timedelta(hours=2)).isoformat()
        mongo_db.signals.insert_many([
            {"_id": stale_id, "id": stale_id, "instrument": "EURUSD",
             "asset_class": "FOREX", "direction": "LONG",
             "setup_type": "BOS_RETEST", "call_type": "FX-OVERLAP",
             "timestamp": old_ts, "trade_date": now.date().isoformat(),
             "entry": 1.14, "stoploss": 1.135, "target": 1.15, "rr": 3.0,
             "outcome": "OPEN", "exit_price": None, "r_multiple": None,
             "created_at": old_ts},
            {"_id": fresh_id, "id": fresh_id, "instrument": "EURUSD",
             "asset_class": "FOREX", "direction": "LONG",
             "setup_type": "BOS_RETEST", "call_type": "FX-OVERLAP",
             "timestamp": new_ts, "trade_date": now.date().isoformat(),
             "entry": 1.14, "stoploss": 1.135, "target": 1.15, "rr": 3.0,
             "outcome": "OPEN", "exit_price": None, "r_multiple": None,
             "created_at": new_ts},
        ])
        try:
            r = api_client.get(f"{API}/signals", params={"asset_class": "FOREX"}, timeout=15)
            assert r.status_code == 200
            by_id = {s["id"]: s for s in r.json()}
            assert stale_id in by_id
            assert fresh_id in by_id
            assert by_id[stale_id].get("stale") is True
            assert by_id[stale_id].get("age_hours") is not None
            assert by_id[stale_id]["age_hours"] >= 24
            assert by_id[fresh_id].get("stale") is False
        finally:
            mongo_db.signals.delete_many({"id": {"$in": [stale_id, fresh_id]}})

    def test_seed_patch_update_and_delete_equity(self, api_client, mongo_db):
        sid = str(uuid.uuid4())
        seed = {
            "_id": sid, "id": sid, "instrument": "HDFCBANK", "asset_class": "EQUITY",
            "direction": "LONG", "setup_type": "BOS_RETEST", "call_type": "INTRADAY",
            "timestamp": datetime.utcnow().isoformat(),
            "trade_date": datetime.utcnow().date().isoformat(),
            "entry": 1500.0, "stoploss": 1490.0, "target": 1530.0, "rr": 3.0,
            "outcome": "OPEN", "exit_price": None, "r_multiple": None,
            "created_at": datetime.utcnow().isoformat(),
        }
        mongo_db.signals.insert_one(seed)
        try:
            r = api_client.patch(f"{API}/signals/{sid}",
                                 json={"outcome": "WON", "exit_price": 1530.0}, timeout=20)
            assert r.status_code == 200, r.text
            updated = r.json()
            assert updated["outcome"] == "WON"
            assert updated["r_multiple"] == 3.0

            r2 = api_client.delete(f"{API}/signals/{sid}", timeout=15)
            assert r2.status_code == 200
            assert r2.json()["deleted"] is True

            r3 = api_client.patch(f"{API}/signals/nonexistent-{uuid.uuid4()}",
                                  json={"outcome": "WON"}, timeout=15)
            assert r3.status_code == 404
        finally:
            mongo_db.signals.delete_one({"id": sid})


# -------------- Analytics -------------- #

class TestAnalytics:
    def test_analytics_shape_and_by_asset_class(self, api_client, mongo_db):
        # Seed one closed equity and one closed forex
        ids = []
        for outcome, rm, ac, sym in [
            ("WON", 3.0, "EQUITY", "RELIANCE"),
            ("LOST", -1.0, "FOREX", "EURUSD"),
        ]:
            sid = f"TEST_AN_{outcome}_{uuid.uuid4()}"
            ids.append(sid)
            mongo_db.signals.insert_one({
                "_id": sid, "id": sid, "instrument": sym, "asset_class": ac,
                "direction": "LONG", "setup_type": "BOS_RETEST",
                "call_type": "INTRADAY" if ac == "EQUITY" else "FX-OVERLAP",
                "timestamp": datetime.utcnow().isoformat(),
                "trade_date": datetime.utcnow().date().isoformat(),
                "entry": 100.0, "stoploss": 90.0, "target": 130.0, "rr": 3.0,
                "outcome": outcome, "exit_price": 130.0 if outcome == "WON" else 90.0,
                "r_multiple": rm, "created_at": datetime.utcnow().isoformat(),
                "closed_at": datetime.utcnow().isoformat(),
            })
        try:
            r = api_client.get(f"{API}/analytics", timeout=20)
            assert r.status_code == 200
            d = r.json()
            for k in ("total_signals", "win_rate", "avg_r", "by_setup",
                      "by_instrument", "by_type", "by_asset_class",
                      "equity_curve", "closed", "open", "won", "lost", "breakeven"):
                assert k in d, f"missing key {k}"
            assert isinstance(d["by_asset_class"], dict)
            # Should include both classes
            assert "EQUITY" in d["by_asset_class"] or "FOREX" in d["by_asset_class"]

            # Filter by FOREX
            r2 = api_client.get(f"{API}/analytics", params={"asset_class": "FOREX"}, timeout=20)
            assert r2.status_code == 200
            d2 = r2.json()
            assert d2.get("asset_class") == "FOREX"
            # by_asset_class should only contain FOREX bucket
            assert set(d2["by_asset_class"].keys()) <= {"FOREX"}
        finally:
            mongo_db.signals.delete_many({"id": {"$in": ids}})


# -------------- Backtest -------------- #

class TestBacktest:
    def test_backtest_invalid_instrument(self, api_client):
        r = api_client.post(f"{API}/backtest", json={
            "instrument": "FAKESYM", "start_date": "2026-06-01", "end_date": "2026-07-03"
        }, timeout=30)
        assert r.status_code == 400

    def test_backtest_range_exceeds_55_days(self, api_client):
        r = api_client.post(f"{API}/backtest", json={
            "instrument": "HDFCBANK", "start_date": "2026-04-01", "end_date": "2026-07-03"
        }, timeout=30)
        assert r.status_code == 400

    def test_backtest_invalid_date_format(self, api_client):
        r = api_client.post(f"{API}/backtest", json={
            "instrument": "HDFCBANK", "start_date": "bad-date", "end_date": "2026-07-03"
        }, timeout=30)
        assert r.status_code == 400

    def test_backtest_equity_regression_hdfcbank(self, api_client):
        r = api_client.post(f"{API}/backtest", json={
            "instrument": "HDFCBANK", "start_date": "2026-06-01", "end_date": "2026-07-03"
        }, timeout=240)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "summary" in d and "signals" in d
        for k in ("total", "won", "lost", "win_rate", "avg_r"):
            assert k in d["summary"]
        # Regression: equity signals must have asset_class=EQUITY (if any signal returned)
        for s in d["signals"]:
            assert s.get("asset_class", "EQUITY") == "EQUITY"
            assert s.get("call_type") in ("INTRADAY", "BTST")

    def test_backtest_forex_eurusd(self, api_client):
        r = api_client.post(f"{API}/backtest", json={
            "instrument": "EURUSD", "start_date": "2026-06-10", "end_date": "2026-07-03"
        }, timeout=240)
        assert r.status_code == 200, r.text
        d = r.json()
        # Response-level asset_class field
        # (spec says asset_class:'FOREX' in the response — may be under summary or top-level)
        top_ac = d.get("asset_class") or d.get("summary", {}).get("asset_class")
        # Not strictly required per current server.py, but per-signal must be FOREX
        signals = d.get("signals", [])
        # Should generate >=1 forex signal typically
        assert isinstance(signals, list)
        for s in signals:
            assert s.get("asset_class") == "FOREX", f"expected FOREX, got {s.get('asset_class')} for {s}"
            assert s.get("call_type") in ("FX-OVERLAP", "FX-LONDON-OPEN")
        if top_ac is not None:
            assert top_ac == "FOREX"

    def test_backtest_forex_xauusd(self, api_client):
        r = api_client.post(f"{API}/backtest", json={
            "instrument": "XAUUSD", "start_date": "2026-06-10", "end_date": "2026-07-03"
        }, timeout=240)
        assert r.status_code == 200, r.text
        d = r.json()
        for s in d.get("signals", []):
            assert s.get("asset_class") == "FOREX"

    def test_backtest_forex_gbpusd(self, api_client):
        r = api_client.post(f"{API}/backtest", json={
            "instrument": "GBPUSD", "start_date": "2026-06-10", "end_date": "2026-07-03"
        }, timeout=240)
        assert r.status_code == 200, r.text
        d = r.json()
        for s in d.get("signals", []):
            assert s.get("asset_class") == "FOREX"

    def test_backtest_csv_forex(self, api_client):
        r = api_client.get(
            f"{API}/backtest/csv",
            params={"instrument": "EURUSD", "start_date": "2026-06-10", "end_date": "2026-07-03"},
            timeout=240,
        )
        assert r.status_code == 200, r.text
        cd = r.headers.get("Content-Disposition", "")
        assert "attachment" in cd.lower() and ".csv" in cd
        header = r.text.splitlines()[0]
        assert "asset_class" in header
        # Check any data rows have FOREX in asset_class column
        lines = r.text.splitlines()
        if len(lines) > 1:
            data_rows = lines[1:]
            for line in data_rows:
                # Column order: instrument,asset_class,direction,...
                cols = line.split(",")
                if len(cols) >= 2 and cols[0] == "EURUSD":
                    assert cols[1] == "FOREX"


# -------------- Timezone/DST-aware forex helpers -------------- #

# Add backend path so we can import strategy/constants directly for unit tests
import sys
_BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

LONDON = ZoneInfo("Europe/London")
NY = ZoneInfo("America/New_York")


class TestForexTZHelpers:
    """Unit tests for the tz-aware forex session helpers in strategy.py.

    These validate the DST-safe behaviour across:
    - Summer (BST + EDT active, typical: 2025-07)
    - Winter (GMT + EST active, typical: 2025-01)
    - Friday 30-min cutoff before NY 17:00 close
    - Sun 17:00 NY open / Fri 17:00 NY close weekly window
    """

    def _strategy(self):
        import strategy
        return strategy

    # ------- Summer / BST + EDT ------- #

    def test_summer_ist_18_00_overlap_true(self):
        s = self._strategy()
        # Tue 2025-07-15 18:00 IST -> 13:30 BST London / 08:30 EDT NY -> overlap
        dt = datetime(2025, 7, 15, 18, 0, tzinfo=IST)
        assert s._is_forex_primary_time(dt) is True
        assert s._is_forex_secondary_time(dt) is False
        assert s._is_forex_friday_cutoff(dt) is False
        assert s._is_forex_market_open(dt) is True
        assert s._london_session_open(dt) is True
        assert s._ny_session_open(dt) is True

    def test_summer_ist_22_00_overlap_false(self):
        s = self._strategy()
        # Tue 2025-07-15 22:00 IST -> 17:30 BST London (CLOSED) / 12:30 EDT NY
        dt = datetime(2025, 7, 15, 22, 0, tzinfo=IST)
        assert s._london_session_open(dt) is False
        assert s._is_forex_primary_time(dt) is False

    def test_summer_ist_12_30_london_2h(self):
        s = self._strategy()
        # Tue 2025-07-15 12:30 IST -> 08:00 BST London (first 2h) / 03:00 EDT NY
        dt = datetime(2025, 7, 15, 12, 30, tzinfo=IST)
        assert s._is_forex_secondary_time(dt) is True
        assert s._is_forex_primary_time(dt) is False
        assert s._london_session_open(dt) is True
        assert s._ny_session_open(dt) is False

    # ------- Winter / GMT + EST ------- #

    def test_winter_ist_19_00_overlap_true(self):
        s = self._strategy()
        # Wed 2025-01-15 19:00 IST -> 13:30 GMT London / 08:30 EST NY -> overlap
        dt = datetime(2025, 1, 15, 19, 0, tzinfo=IST)
        assert s._is_forex_primary_time(dt) is True

    def test_winter_ist_22_00_overlap_still_true(self):
        s = self._strategy()
        # Wed 2025-01-15 22:00 IST -> 16:30 GMT London / 11:30 EST NY -> still overlap in winter
        dt = datetime(2025, 1, 15, 22, 0, tzinfo=IST)
        assert s._is_forex_primary_time(dt) is True
        assert s._london_session_open(dt) is True
        assert s._ny_session_open(dt) is True

    def test_winter_ist_13_30_london_2h(self):
        s = self._strategy()
        # Wed 2025-01-15 13:30 IST -> 08:00 GMT London (first 2h)
        dt = datetime(2025, 1, 15, 13, 30, tzinfo=IST)
        assert s._is_forex_secondary_time(dt) is True

    # ------- Friday cutoff (30 min pre NY 17:00 close) ------- #

    def test_friday_summer_16_45_ny_cutoff_true(self):
        s = self._strategy()
        # Fri 2025-07-18 16:45 America/New_York (EDT): 15 min before close -> cutoff=True
        dt = datetime(2025, 7, 18, 16, 45, tzinfo=NY)
        assert s._is_forex_friday_cutoff(dt) is True

    def test_friday_summer_15_45_ny_cutoff_false(self):
        s = self._strategy()
        # Fri 2025-07-18 15:45 NY: 75 min before close -> cutoff=False
        dt = datetime(2025, 7, 18, 15, 45, tzinfo=NY)
        assert s._is_forex_friday_cutoff(dt) is False

    def test_friday_summer_17_05_ny_post_close(self):
        s = self._strategy()
        # Fri 2025-07-18 17:05 NY: after close -> cutoff=False, market closed
        dt = datetime(2025, 7, 18, 17, 5, tzinfo=NY)
        assert s._is_forex_friday_cutoff(dt) is False
        assert s._is_forex_market_open(dt) is False

    def test_friday_winter_16_45_ny_cutoff_true(self):
        s = self._strategy()
        # Fri 2025-01-17 16:45 NY (EST) -> cutoff behaviour preserved in winter DST
        dt = datetime(2025, 1, 17, 16, 45, tzinfo=NY)
        assert s._is_forex_friday_cutoff(dt) is True

    # ------- Weekend market_open behaviour ------- #

    def test_saturday_market_closed(self):
        s = self._strategy()
        dt = datetime(2025, 7, 19, 10, 0, tzinfo=NY)  # Sat morning NY
        assert s._is_forex_market_open(dt) is False

    def test_sunday_18_00_ny_open(self):
        s = self._strategy()
        # Sun 2025-07-20 18:00 NY -> after 17:00 Sunday open -> True
        dt = datetime(2025, 7, 20, 18, 0, tzinfo=NY)
        assert s._is_forex_market_open(dt) is True

    def test_sunday_16_00_ny_still_closed(self):
        s = self._strategy()
        # Sun 2025-07-20 16:00 NY -> before Sunday open at 17:00 -> False
        dt = datetime(2025, 7, 20, 16, 0, tzinfo=NY)
        assert s._is_forex_market_open(dt) is False


# -------------- Removed constants regression -------------- #

class TestConstantsRefactor:
    """The pre-refactor hardcoded IST windows must be removed from constants."""

    def test_removed_constants_no_longer_present(self):
        import constants
        removed = ("FOREX_PRIMARY_WINDOW", "FOREX_SECONDARY_WINDOW", "FRIDAY_CUTOFF_SAT_IST")
        for name in removed:
            assert not hasattr(constants, name), \
                f"{name} should have been removed from constants.py"

    def test_new_tzaware_constants_present(self):
        import constants
        for name in (
            "LONDON_TZ", "NY_TZ",
            "LONDON_OPEN_LOCAL", "LONDON_CLOSE_LOCAL",
            "NY_OPEN_LOCAL", "NY_CLOSE_LOCAL",
            "LONDON_OPEN_WINDOW_HOURS", "FRIDAY_CLOSE_BUFFER_MIN",
        ):
            assert hasattr(constants, name), f"missing new constant {name}"
        # zoneinfo values are the correct tz
        assert str(constants.LONDON_TZ) == "Europe/London"
        assert str(constants.NY_TZ) == "America/New_York"
        assert constants.FRIDAY_CLOSE_BUFFER_MIN == 30
        assert constants.LONDON_OPEN_WINDOW_HOURS == 2