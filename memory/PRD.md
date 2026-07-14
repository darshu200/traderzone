# TradeSignal — Product Requirements

## Original Problem Statement
Web app called "TradeSignal" — an Indian NSE stock market technical analysis
signal dashboard for Nifty 50, Bank Nifty, and a fixed watchlist of 10 liquid
large-caps. Personal/internal testing only, not public trading advice.

## Stack
- React 19 + Tailwind (dark trading-terminal theme, IBM Plex Mono + Chivo)
- FastAPI + AsyncIOMotor + MongoDB
- APScheduler for 2-min market-hours signal scan (IST)
- yfinance for historical OHLCV, NSE India unofficial JSON for live quotes with
  yfinance fallback

## Personas
- Solo retail trader tracking signals for personal paper-trading

## Core Requirements (static)
- Instrument universe: NIFTY, BANKNIFTY + 10 large-caps
- 15m structure, 5m entry, daily bias for BTST
- Strategy: swing detection → BOS (with vol ≥ 1.5x SMA20) → order block →
  5m rejection retest inside OB → above/below VWAP → 1:3 RR minimum
- Entry windows: 09:30–11:15 and 13:30–14:45 IST; BTST uses 13:30–14:45 window
- Hard filters: NIFTY/BANKNIFTY conflict, ≥2 signals/instrument/day, first/last
  15 min of session, 90 min pre-Thursday close
- Dashboard: Live signals, Watchlist, Trade Log (mark WON/LOST/BE), Performance
  Analytics (win rate, avg R, equity curve, breakdowns), Backtest with CSV,
  Settings for active instruments
- Paper-trading only; no broker integration

## Implemented (2026-07-04)
- Backend (`/app/backend`):
  - `constants.py`, `data_source.py`, `strategy.py`, `backtest.py`, `server.py`
  - Endpoints: `/api/market/status`, `/api/instruments`, `/api/watchlist`,
    `/api/signals` (GET/PATCH/DELETE), `/api/signals/today`, `/api/analytics`,
    `/api/settings` (GET/PUT), `/api/backtest` (POST + `/csv`), `/api/dev/run-scan`
  - APScheduler cron: Mon–Fri, hour 9–15, minute */2, IST
- Frontend (`/app/frontend`):
  - Pages: LiveSignals, TradeLog, Analytics, Backtest, Settings
  - Components: Sidebar, TopBar, SignalCard, WatchlistCard, CloseTradeDialog
  - Dark terminal theme with IBM Plex Mono for prices; Recharts for equity curve
- Tested: 14/14 backend + 30/30 frontend checks (see /app/test_reports/iteration_1.json)

## Iteration 3 (2026-07-04) — DST-Safe Forex Sessions
- Rewrote forex session logic to be timezone-aware:
  - Source of truth: `Europe/London` 08:00–17:00 and `America/New_York` 08:00–17:00
  - Primary entry = intersection (overlap). Secondary = first 2h of London open.
  - Friday close cutoff = 30 min before Friday 17:00 America/New_York (works in both EDT and EST)
  - Forex market open = Sun 17:00 NY → Fri 17:00 NY, closed all Saturday
- Removed hardcoded IST tuples (`FOREX_PRIMARY_WINDOW`, `FOREX_SECONDARY_WINDOW`, `FRIDAY_CUTOFF_SAT_IST`)
- `/api/market/status` now returns dynamic session strings (`session_forex_overlap_ist`, `session_forex_secondary_ist`) plus native tz timestamps (`server_time_london`, `server_time_ny`) and separate `london_session_open` / `ny_session_open` booleans
- Frontend Live Signals empty-state and Settings notes read the DST-adjusted times directly from the API
- Scheduler widened: `mon-fri 9-23 IST`, `sat 0-4 IST`, `sun-mon 2-8 IST` — covers all DST-shifted forex windows including Sunday-open tail
- Tested: 39/39 backend + 5/5 pages (see `/app/test_reports/iteration_3.json`)

## Iteration 2 (2026-07-04) — Forex Extension
- Added 7 forex/commodity instruments (EURUSD, GBPUSD, USDJPY, GBPJPY, AUDUSD,
  USDCAD, XAUUSD) via yfinance. Total universe now 19.
- Forex-specific windows in IST: primary 18:30–21:30 (London/NY overlap),
  secondary 12:30–14:30 (London open). Skip 30 min pre-Friday-close.
- Strategy adaptations for forex (Volume = 0 in yfinance forex data):
  - BOS impulse filter switched from volume ≥ 1.5×SMA20 to range ≥ 1.2×ATR(14)
  - VWAP falls back to session-anchored TWAP when total volume is 0
  - Precision-aware rounding via pip_decimals (4 for majors, 2 for JPY/gold)
- Server changes:
  - `asset_class` query param on `/api/watchlist`, `/api/signals`, `/api/analytics`,
    `/api/instruments`, `/api/signals/today`
  - Signals include `asset_class`; analytics adds `by_asset_class`
  - `_annotate_stale` flags OPEN forex signals older than 24h (`stale`, `age_hours`)
  - Two scheduler crons: weekday 9-21 IST + Saturday 0-2 IST (covers forex windows)
  - Watchlist parallelized via `asyncio.gather`, plus TTL cache (45s quotes, 60s candles):
    latency 51s → 4.8s cold / 0.76s warm
  - Settings auto-migration merges any newly-added instruments on startup
- Frontend changes:
  - New `AssetClassTabs` component (All / Equity / Forex)
  - Tabs on Live Signals, Trade Log, Analytics, Backtest
  - TopBar shows dual EQ/FX status pills
  - `INSTRUMENT_META` map on frontend for pip-aware price formatting
  - Trade Log adds `Class` column, stale-warning icon; Analytics adds "By Asset Class"
  - Settings groups instruments by class with Enable All / Disable All per group
- Tested: 23/23 backend + all 5 page flows (see /app/test_reports/iteration_2.json)

## Prioritized Backlog
- P1: In-memory TTL cache (30-60s) for `/api/watchlist` to reduce yfinance/NSE calls
- P1: Add MongoDB indexes on `signals.id` (unique), `signals.trade_date`, `signals.instrument`
- P1: Fix TATAMOTORS ticker mapping (yfinance says delisted — investigate alt symbol)
- P2: DialogDescription for accessibility on CloseTradeDialog
- P2: Realtime auto-refresh notification when new signals appear
- P2: Chart preview on signal card (mini candles around entry)
- P3: Multi-user + JWT auth
- P3: Email/Telegram alerts on new signals
- P3: Manual signal creation (paper "what-if")

## Known Limitations
- yfinance 5m/15m data limited to ~60 days (backtest capped at 55 days)
- NSE unofficial JSON may throttle from cloud IPs (yfinance fallback active)
- TATAMOTORS.NS currently returns no yfinance data (delisted per Yahoo)
