"""
Runs the REAL backtest (with SL/target outcome simulation) across every
instrument, then reports win rate, average R, and net R (profitability in
R-multiples) both per-instrument and combined overall. Also writes a CSV of
every individual signal for your own inspection in Excel.

Run from the backend folder with your venv active:
    python debug_all_outcomes.py
"""
import csv
from datetime import datetime, timedelta

from constants import ALL_SYMBOLS
from backtest import run_backtest

END_DT = datetime.now()
START_DT = END_DT - timedelta(days=58)
START = START_DT.strftime("%Y-%m-%d")
END = END_DT.strftime("%Y-%m-%d")
MID_DT = START_DT + (END_DT - START_DT) / 2
MID = MID_DT.strftime("%Y-%m-%d")

print(f"Full window: {START} -> {END}")
print(f"Train half (tune/inspect here): {START} -> {MID}")
print(f"Test half (do NOT tune against this — just check it once): {MID} -> {END}\n")

all_signals = []
per_instrument = []

for sym in ALL_SYMBOLS:
    print(f"Running {sym} ...")
    result = run_backtest(sym, START, END)
    for s in result["signals"]:
        s["instrument"] = sym  # ensure present even if missing
        all_signals.append(s)
    summ = result["summary"]
    per_instrument.append({
        "instrument": sym,
        "asset_class": result.get("asset_class", ""),
        "total": summ["total"], "won": summ["won"], "lost": summ["lost"],
        "open": summ["open"], "win_rate": summ["win_rate"], "avg_r": summ["avg_r"],
        "net_r": round(sum(s.get("r_multiple", 0.0) for s in result["signals"]
                            if s.get("outcome") in ("WON", "LOST")), 2),
    })

# ---- Per-instrument table ----
print("\n" + "=" * 100)
print(f"{'Instrument':<12}{'Class':<8}{'Total':>7}{'Won':>6}{'Lost':>6}{'Open':>6}"
      f"{'WinRate%':>10}{'AvgR':>8}{'NetR':>8}")
print("-" * 100)
for r in per_instrument:
    print(f"{r['instrument']:<12}{r['asset_class']:<8}{r['total']:>7}{r['won']:>6}"
          f"{r['lost']:>6}{r['open']:>6}{r['win_rate']:>10}{r['avg_r']:>8}{r['net_r']:>8}")

# ---- Overall aggregate ----
closed = [s for s in all_signals if s.get("outcome") in ("WON", "LOST")]
won = [s for s in closed if s["outcome"] == "WON"]
lost = [s for s in closed if s["outcome"] == "LOST"]
opened = [s for s in all_signals if s.get("outcome") == "OPEN"]

total_signals = len(all_signals)
win_rate = round(len(won) / len(closed) * 100, 2) if closed else 0.0
avg_r_all = round(sum(s["r_multiple"] for s in closed) / len(closed), 3) if closed else 0.0
net_r = round(sum(s["r_multiple"] for s in closed), 2)
avg_win_r = round(sum(s["r_multiple"] for s in won) / len(won), 2) if won else 0.0

print("=" * 100)
print("\n--- OVERALL (all instruments combined, closed trades only for rates) ---")
print(f"Total signals generated : {total_signals}")
print(f"Closed (Won+Lost)       : {len(closed)}")
print(f"Still Open              : {len(opened)}")
print(f"Won                     : {len(won)}")
print(f"Lost                    : {len(lost)}")
print(f"Win rate                : {win_rate}%")
print(f"Average R per closed trade : {avg_r_all}  (positive = net profitable in R-multiples)")
print(f"Average R on WINNERS only  : {avg_win_r}  (should be >= 3.0, your minimum RR)")
print(f"NET R (sum of all closed trades' R) : {net_r}")
print(f"\nInterpretation: if every trade risked the same % of capital, NET R of "
      f"{net_r} means the system would have made {net_r}x your per-trade risk "
      f"amount in total over this window (negative = net loss).")


def _half_stats(sigs, label):
    c = [s for s in sigs if s.get("outcome") in ("WON", "LOST")]
    w = [s for s in c if s["outcome"] == "WON"]
    wr = round(len(w) / len(c) * 100, 2) if c else 0.0
    nr = round(sum(s["r_multiple"] for s in c), 2) if c else 0.0
    print(f"{label:12s}: trades={len(c):3d}  win_rate={wr:6.2f}%  net_r={nr:7.2f}")


train_sigs = [s for s in all_signals if s.get("timestamp", "") < MID]
test_sigs = [s for s in all_signals if s.get("timestamp", "") >= MID]

print("\n--- TRAIN vs TEST HALF (the real check — don't tune against TEST) ---")
_half_stats(train_sigs, "TRAIN half")
_half_stats(test_sigs, "TEST half")
print("If TEST looks meaningfully worse than TRAIN, recent changes were likely")
print("fit to TRAIN-half noise rather than a real, generalizing edge.")

print("\n--- BY RR TIER (does a lower RR target actually win enough to be worth it?) ---")
tiers = sorted({s.get("rr_tier") for s in closed if s.get("rr_tier")},
               key=lambda t: int(t.split(":")[1]))
for t in tiers:
    tier_sigs = [s for s in closed if s.get("rr_tier") == t]
    w = [s for s in tier_sigs if s["outcome"] == "WON"]
    wr = round(len(w) / len(tier_sigs) * 100, 2) if tier_sigs else 0.0
    nr = round(sum(s["r_multiple"] for s in tier_sigs), 2)
    breakeven = round(100 / (int(t.split(":")[1]) + 1), 1)
    print(f"{t:6s}: trades={len(tier_sigs):3d}  win_rate={wr:6.2f}%  "
          f"(breakeven needs {breakeven}%)  net_r={nr:7.2f}")

# ---- CSV export ----
fname = "backtest_all_signals.csv"
with open(fname, "w", newline="") as f:
    writer = csv.writer(f)
    writer.writerow(["instrument", "asset_class", "direction", "setup_type", "call_type",
                      "timestamp", "entry", "stoploss", "target", "rr", "rr_tier",
                      "outcome", "exit_price", "r_multiple"])
    for s in all_signals:
        writer.writerow([
            s.get("instrument"), s.get("asset_class"), s.get("direction"),
            s.get("setup_type"), s.get("call_type"), s.get("timestamp"),
            s.get("entry"), s.get("stoploss"), s.get("target"), s.get("rr"),
            s.get("rr_tier"),
            s.get("outcome"), s.get("exit_price"), s.get("r_multiple"),
        ])
print(f"\nFull signal-level detail written to: {fname}")
print("Open it in Excel to inspect every individual trade.")