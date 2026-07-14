"""
Large-universe backtest: pulls the REAL, current Nifty 500 constituent list
live from NSE Indices, then runs the exact same (already-fixed) backtest
engine across all of them — no changes to strategy.py/backtest.py needed.

This is a ONE-OFF, separate statistical test. It does NOT touch your live
app's 19-instrument watchlist/dashboard in any way — INSTRUMENTS is only
extended in-memory, inside this script's own process.

Given ~500 stocks x 3 data fetches each, this will take a while (45-90+
min depending on your connection and Yahoo's rate limiting). Progress is
checkpointed to CSV every 25 symbols, so you can stop it (Ctrl+C) and still
keep everything computed so far.

Run from the backend folder with your venv active:
    python debug_large_universe_outcomes.py
"""
import csv
import io
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import requests
import pandas as pd

import constants
from backtest import run_backtest

END_DT = datetime.now()
START_DT = END_DT - timedelta(days=58)
START = START_DT.strftime("%Y-%m-%d")
END = END_DT.strftime("%Y-%m-%d")
MID_DT = START_DT + (END_DT - START_DT) / 2
MID = MID_DT.strftime("%Y-%m-%d")

CHECKPOINT_FILE = "large_universe_signals.csv"
MAX_WORKERS = 6  # modest concurrency — enough to speed things up without
                  # tripping Yahoo's rate limiting


def fetch_nifty500_symbols() -> list[str]:
    """Pull the real, current Nifty 500 list. Tries the official source
    first, falls back to a GitHub mirror if that fails."""
    sources = [
        "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
        "https://raw.githubusercontent.com/kprohith/nse-stock-analysis/master/ind_nifty500list.csv",
    ]
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in sources:
        try:
            r = requests.get(url, headers=headers, timeout=15)
            r.raise_for_status()
            df = pd.read_csv(io.StringIO(r.text))
            col = "Symbol" if "Symbol" in df.columns else df.columns[2]
            symbols = [str(s).strip() for s in df[col].dropna().tolist()]
            symbols = [s for s in symbols if s and s.upper() != "SYMBOL"]
            if len(symbols) > 100:
                print(f"Fetched {len(symbols)} symbols from {url}")
                return symbols
        except Exception as e:
            print(f"Source failed ({url}): {e}")
    raise RuntimeError("Could not fetch Nifty 500 list from any source.")


def register_instrument(symbol: str):
    """Inject a stock into the in-memory INSTRUMENTS dict, if not already
    present (your existing 12 stay as-is with their real metadata)."""
    if symbol in constants.INSTRUMENTS:
        return
    constants.INSTRUMENTS[symbol] = {
        "yf": f"{symbol}.NS", "name": symbol, "type": "stock",
        "asset_class": "EQUITY", "nse": symbol,
        "pip_decimals": 2, "price_prefix": "\u20b9",
    }


def run_one(symbol: str) -> dict:
    try:
        register_instrument(symbol)
        result = run_backtest(symbol, START, END)
        return {"symbol": symbol, "signals": result["signals"], "error": None}
    except Exception as e:
        return {"symbol": symbol, "signals": [], "error": str(e)}


def main():
    symbols = fetch_nifty500_symbols()
    # Don't duplicate the ones already in your curated watchlist
    existing = {s for s, m in constants.INSTRUMENTS.items() if m.get("asset_class") == "EQUITY"}
    symbols = [s for s in symbols if s not in existing]
    print(f"Testing {len(symbols)} additional Nifty 500 stocks "
          f"(your existing {len(existing)} equities excluded, already tested separately)\n")

    all_signals = []
    errors = []
    done = 0
    start_time = time.time()

    with open(CHECKPOINT_FILE, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["instrument", "asset_class", "direction", "setup_type", "call_type",
                          "timestamp", "entry", "stoploss", "target", "rr", "rr_tier",
                          "outcome", "exit_price", "r_multiple"])

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(run_one, s): s for s in symbols}
            for fut in as_completed(futures):
                res = fut.result()
                done += 1
                if res["error"]:
                    errors.append(f"{res['symbol']}: {res['error']}")
                else:
                    for s in res["signals"]:
                        s["instrument"] = res["symbol"]
                        all_signals.append(s)
                        writer.writerow([
                            s.get("instrument"), s.get("asset_class"), s.get("direction"),
                            s.get("setup_type"), s.get("call_type"), s.get("timestamp"),
                            s.get("entry"), s.get("stoploss"), s.get("target"),
                            s.get("rr"), s.get("rr_tier"),
                            s.get("outcome"), s.get("exit_price"), s.get("r_multiple"),
                        ])
                if done % 25 == 0 or done == len(symbols):
                    f.flush()
                    elapsed = time.time() - start_time
                    print(f"[{done}/{len(symbols)}] done, {len(all_signals)} signals so far, "
                          f"{elapsed/60:.1f} min elapsed, {len(errors)} errors")

    print(f"\nFinished. Total signals: {len(all_signals)}  Errors: {len(errors)}")
    if errors:
        print("First 10 errors (usually just thin/no data for that symbol — expected for some):")
        for e in errors[:10]:
            print(f"  - {e}")

    # ---- Aggregate ----
    closed = [s for s in all_signals if s.get("outcome") in ("WON", "LOST")]
    won = [s for s in closed if s["outcome"] == "WON"]
    win_rate = round(len(won) / len(closed) * 100, 2) if closed else 0.0
    net_r = round(sum(s["r_multiple"] for s in closed), 2)
    avg_r = round(net_r / len(closed), 3) if closed else 0.0

    print("\n=== OVERALL (large universe) ===")
    print(f"Closed trades : {len(closed)}")
    print(f"Won / Lost    : {len(won)} / {len(closed) - len(won)}")
    print(f"Win rate      : {win_rate}%")
    print(f"Average R     : {avg_r}")
    print(f"NET R         : {net_r}")

    train = [s for s in closed if s.get("timestamp", "") < MID]
    test = [s for s in closed if s.get("timestamp", "") >= MID]
    for label, grp in (("TRAIN half", train), ("TEST half", test)):
        w = [s for s in grp if s["outcome"] == "WON"]
        wr = round(len(w) / len(grp) * 100, 2) if grp else 0.0
        nr = round(sum(s["r_multiple"] for s in grp), 2) if grp else 0.0
        print(f"{label:12s}: trades={len(grp):4d}  win_rate={wr:6.2f}%  net_r={nr:8.2f}")

    print("\n--- BY RR TIER ---")
    tiers = sorted({s.get("rr_tier") for s in closed if s.get("rr_tier")},
                   key=lambda t: int(t.split(":")[1]))
    for t in tiers:
        grp = [s for s in closed if s.get("rr_tier") == t]
        w = [s for s in grp if s["outcome"] == "WON"]
        wr = round(len(w) / len(grp) * 100, 2) if grp else 0.0
        nr = round(sum(s["r_multiple"] for s in grp), 2)
        breakeven = round(100 / (int(t.split(":")[1]) + 1), 1)
        print(f"{t:6s}: trades={len(grp):4d}  win_rate={wr:6.2f}%  "
              f"(breakeven {breakeven}%)  net_r={nr:8.2f}")

    print("\n--- BY SETUP TYPE ---")
    for st in ("BOS-OB-Retest", "Liquidity-Sweep"):
        grp = [s for s in closed if s.get("setup_type") == st]
        w = [s for s in grp if s["outcome"] == "WON"]
        wr = round(len(w) / len(grp) * 100, 2) if grp else 0.0
        nr = round(sum(s["r_multiple"] for s in grp), 2) if grp else 0.0
        print(f"{st:18s}: trades={len(grp):4d}  win_rate={wr:6.2f}%  net_r={nr:8.2f}")

    print(f"\nFull detail: {CHECKPOINT_FILE}")


if __name__ == "__main__":
    main()
