"""
Standalone diagnostic: run this directly to see exactly what yfinance returns
(or errors with) for NIFTY/BANKNIFTY intraday data, bypassing the rest of the
app entirely.

Run from the backend folder with your venv active:
    python debug_nifty_fetch.py
"""
import traceback
import yfinance as yf

try:
    from curl_cffi import requests as cffi_requests
    session = cffi_requests.Session(impersonate="chrome")
    print("Using curl_cffi impersonated session.\n")
except Exception as e:
    session = None
    print(f"curl_cffi unavailable ({e}), using default session.\n")

TESTS = [
    ("^NSEI",       "15m", "2026-06-01", "2026-07-01"),
    ("^NSEI",       "5m",  "2026-06-01", "2026-07-01"),
    ("^NSEI",       "15m", None, None),   # period-based, last 5 days
    ("^NSEBANK",    "15m", "2026-06-01", "2026-07-01"),
    ("RELIANCE.NS", "15m", "2026-06-01", "2026-07-01"),  # known-good control
]

for ticker, interval, start, end in TESTS:
    print("=" * 70)
    print(f"Ticker={ticker}  interval={interval}  start={start}  end={end}")
    try:
        kwargs = dict(tickers=ticker, interval=interval, progress=False,
                      auto_adjust=False, threads=False)
        if session is not None:
            kwargs["session"] = session
        if start and end:
            kwargs["start"] = start
            kwargs["end"] = end
        else:
            kwargs["period"] = "5d"

        df = yf.download(**kwargs)

        if df is None:
            print("RESULT: yf.download returned None")
        elif df.empty:
            print("RESULT: yf.download returned an EMPTY DataFrame")
        else:
            print(f"RESULT: OK — shape={df.shape}")
            print(df.tail(3))
    except Exception as e:
        print(f"RESULT: EXCEPTION -> {type(e).__name__}: {e}")
        traceback.print_exc()
    print()

print("=" * 70)
print("Also trying yf.Ticker().history() directly for ^NSEI as a second method:")
try:
    t = yf.Ticker("^NSEI", session=session) if session else yf.Ticker("^NSEI")
    h = t.history(period="5d", interval="15m")
    if h is None or h.empty:
        print("RESULT: Ticker.history() also returned empty/None for ^NSEI")
    else:
        print(f"RESULT: OK via Ticker.history() — shape={h.shape}")
        print(h.tail(3))
except Exception as e:
    print(f"RESULT: EXCEPTION -> {type(e).__name__}: {e}")
    traceback.print_exc()
