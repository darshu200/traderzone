"""Capital & real-money P&L calculations. Pure functions — no DB/network I/O
here, so they're straightforward to unit test independently of FastAPI/Mongo.

Key principle (from real observed data): R-multiples only translate into
consistent rupee outcomes if position size is computed so every trade risks
the same rupee amount. Without that, a wide-stop 1:1 loss and a narrow-stop
1:2 win can net a rupee LOSS even though the R-multiples sum positive.
"""
from __future__ import annotations
import math
from typing import Optional


def leverage_for_call_type(call_type: str, intraday_leverage: float, btst_leverage: float) -> float:
    """INTRADAY (MIS) gets margin leverage; BTST/delivery (CNC) requires
    full cash — no leverage. Default 5x intraday / 1x BTST per user's
    actual Zerodha margin terms, but both are configurable since real
    per-stock MIS margin varies."""
    if call_type == "INTRADAY":
        return max(intraday_leverage, 1.0)
    return max(btst_leverage, 1.0)  # BTST/delivery — effectively 1x


def compute_risk_amount(capital: float, risk_per_trade_pct: float) -> float:
    return round(capital * (risk_per_trade_pct / 100.0), 2)


def compute_stop_distance(entry_price: float, stoploss: float) -> float:
    return abs(entry_price - stoploss)


def compute_risk_based_quantity(risk_amount: float, stop_distance: float) -> int:
    """Quantity such that a full stop-out loses ~risk_amount, regardless of
    how wide or narrow the stop is. This is the fix for the R-vs-rupee gap."""
    if stop_distance <= 0:
        return 0
    return max(0, math.floor(risk_amount / stop_distance))


def compute_margin_capped_quantity(available_capital: float, entry_price: float, leverage: float) -> int:
    """Max shares affordable given available capital and leverage — a
    separate ceiling from the risk-based quantity. The trade uses
    whichever of the two is SMALLER."""
    if entry_price <= 0 or leverage <= 0:
        return 0
    return max(0, math.floor((available_capital * leverage) / entry_price))


def compute_final_quantity(risk_based_qty: int, margin_capped_qty: int) -> int:
    return max(0, min(risk_based_qty, margin_capped_qty))


def compute_capital_required(quantity: int, entry_price: float, leverage: float) -> float:
    if leverage <= 0:
        return quantity * entry_price
    return round((quantity * entry_price) / leverage, 2)


def compute_real_rr_at_detection(dashboard_price: float, stoploss: float, target: float,
                                  direction: str) -> Optional[float]:
    """RR as it actually stands at the moment the signal was detected —
    NOT the strategy's theoretical RR from its own confirmation candle.
    Confirmation delay can make this meaningfully better or worse."""
    stop_distance = compute_stop_distance(dashboard_price, stoploss)
    if stop_distance <= 0:
        return None
    reward = abs(target - dashboard_price)
    return round(reward / stop_distance, 2)


def check_already_invalid(dashboard_price: float, stoploss: float, target: float,
                           direction: str) -> bool:
    """True if price has already crossed the stoploss or reached the target
    by the moment of detection — the trade is effectively already resolved
    before a human could act on it. Separate from time-based staleness."""
    if direction == "LONG":
        return dashboard_price <= stoploss or dashboard_price >= target
    else:  # SHORT
        return dashboard_price >= stoploss or dashboard_price <= target


def compute_realized_pnl(quantity: int, entry_price: float, exit_price: float,
                          direction: str) -> float:
    sign = 1 if direction == "LONG" else -1
    return round(quantity * (exit_price - entry_price) * sign, 2)


def compute_pnl_pct_of_capital(pnl_rupees: float, capital_at_time: float) -> float:
    if capital_at_time <= 0:
        return 0.0
    return round((pnl_rupees / capital_at_time) * 100, 3)


def compute_position_sizing(
    *, capital: float, risk_per_trade_pct: float, dashboard_price: float,
    stoploss: float, target: float, direction: str, call_type: str,
    intraday_leverage: float, btst_leverage: float,
) -> dict:
    """One-shot computation used both when suggesting a trade and when
    actually recording one. Returns everything the UI needs to show and
    everything needed to persist a real_trades record."""
    risk_amount = compute_risk_amount(capital, risk_per_trade_pct)
    stop_distance = compute_stop_distance(dashboard_price, stoploss)
    leverage = leverage_for_call_type(call_type, intraday_leverage, btst_leverage)
    risk_based_qty = compute_risk_based_quantity(risk_amount, stop_distance)
    margin_capped_qty = compute_margin_capped_quantity(capital, dashboard_price, leverage)
    final_qty = compute_final_quantity(risk_based_qty, margin_capped_qty)
    capital_required = compute_capital_required(final_qty, dashboard_price, leverage)
    real_rr = compute_real_rr_at_detection(dashboard_price, stoploss, target, direction)
    already_invalid = check_already_invalid(dashboard_price, stoploss, target, direction)

    return {
        "risk_amount": risk_amount,
        "stop_distance": round(stop_distance, 4),
        "leverage_used": leverage,
        "risk_based_quantity": risk_based_qty,
        "margin_capped_quantity": margin_capped_qty,
        "quantity": final_qty,
        "capital_required": capital_required,
        "margin_limited": margin_capped_qty < risk_based_qty,
        "real_rr_at_detection": real_rr,
        "already_invalid_at_detection": already_invalid,
        "insufficient_capital": final_qty == 0 and risk_based_qty > 0,
    }
