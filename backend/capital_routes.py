"""Capital & real-money P&L API — entirely separate route group, mounted
into the main app. Doesn't touch any existing signals/backtest/watchlist
logic; only reads signals to suggest sizing, and writes to its own
collections (capital_settings, real_trades)."""
from __future__ import annotations
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pymongo import ReturnDocument

from capital import compute_position_sizing, compute_realized_pnl, compute_pnl_pct_of_capital

DEFAULT_SETTINGS = {
    "_id": "singleton",
    "starting_capital": 100000.0,
    "current_capital": 100000.0,
    "risk_per_trade_pct": 1.0,
    "intraday_leverage": 5.0,
    "btst_leverage": 1.0,
    "daily_loss_limit_pct": 2.0,  # informational only for now, not enforced
}


class SettingsUpdate(BaseModel):
    starting_capital: Optional[float] = None
    risk_per_trade_pct: Optional[float] = None
    intraday_leverage: Optional[float] = None
    btst_leverage: Optional[float] = None
    daily_loss_limit_pct: Optional[float] = None


class TakeTradeRequest(BaseModel):
    signal_id: str
    quantity_override: Optional[int] = None
    actual_entry_price: Optional[float] = None


class CloseTradeRequest(BaseModel):
    actual_exit_price: float
    notes: Optional[str] = None


def create_capital_router(db, ist_now_fn) -> APIRouter:
    """db: the motor AsyncIOMotorDatabase already created in server.py.
    ist_now_fn: the existing _now_ist() helper, passed in to avoid
    duplicating timezone logic."""
    router = APIRouter(prefix="/capital", tags=["capital"])

    async def _get_settings() -> dict:
        # Atomic upsert instead of find-then-insert — avoids a race where
        # two concurrent requests (e.g. the dashboard's parallel initial
        # fetches) both see "no doc yet" and both try to insert, causing
        # a DuplicateKeyError on the second one.
        doc = await db.capital_settings.find_one_and_update(
            {"_id": "singleton"},
            {"$setOnInsert": DEFAULT_SETTINGS},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return doc

    @router.get("/settings")
    async def get_settings():
        doc = await _get_settings()
        doc.pop("_id", None)
        return doc

    @router.put("/settings")
    async def update_settings(upd: SettingsUpdate):
        current = await _get_settings()
        changes = {k: v for k, v in upd.dict().items() if v is not None}
        if "starting_capital" in changes:
            # Only allow resetting starting capital if no trades exist yet —
            # otherwise current_capital (which reflects real history) would
            # get silently overwritten.
            trade_count = await db.real_trades.count_documents({})
            if trade_count == 0:
                changes["current_capital"] = changes["starting_capital"]
            else:
                raise HTTPException(400, "Cannot change starting_capital after trades exist — "
                                          "current_capital reflects real trading history now.")
        if changes:
            await db.capital_settings.update_one({"_id": "singleton"}, {"$set": changes}, upsert=True)
        doc = await _get_settings()
        doc.pop("_id", None)
        return doc

    @router.get("/quantity-suggestion")
    async def quantity_suggestion(signal_id: str):
        sig = await db.signals.find_one({"id": signal_id}, {"_id": 0})
        if not sig:
            raise HTTPException(404, "Signal not found")
        settings = await _get_settings()
        dashboard_price = sig.get("dashboard_price") or sig.get("entry")
        sizing = compute_position_sizing(
            capital=settings["current_capital"],
            risk_per_trade_pct=settings["risk_per_trade_pct"],
            dashboard_price=dashboard_price,
            stoploss=sig["stoploss"], target=sig["target"], direction=sig["direction"],
            call_type=sig.get("call_type", "INTRADAY"),
            intraday_leverage=settings["intraday_leverage"],
            btst_leverage=settings["btst_leverage"],
        )
        return {"signal": sig, "sizing": sizing, "current_capital": settings["current_capital"]}

    @router.post("/trades")
    async def take_trade(req: TakeTradeRequest):
        sig = await db.signals.find_one({"id": req.signal_id}, {"_id": 0})
        if not sig:
            raise HTTPException(404, "Signal not found")
        existing = await db.real_trades.find_one({"signal_id": req.signal_id})
        if existing:
            raise HTTPException(400, "This signal has already been marked as taken")

        settings = await _get_settings()
        dashboard_price = sig.get("dashboard_price") or sig.get("entry")
        sizing = compute_position_sizing(
            capital=settings["current_capital"],
            risk_per_trade_pct=settings["risk_per_trade_pct"],
            dashboard_price=dashboard_price,
            stoploss=sig["stoploss"], target=sig["target"], direction=sig["direction"],
            call_type=sig.get("call_type", "INTRADAY"),
            intraday_leverage=settings["intraday_leverage"],
            btst_leverage=settings["btst_leverage"],
        )
        quantity = req.quantity_override if req.quantity_override is not None else sizing["quantity"]
        if quantity <= 0:
            raise HTTPException(400, "Computed quantity is 0 — insufficient capital/margin for this trade")
        actual_entry = req.actual_entry_price if req.actual_entry_price is not None else dashboard_price

        now = ist_now_fn()
        trade_id = str(uuid.uuid4())
        doc = {
            "id": trade_id,
            "signal_id": req.signal_id,
            "instrument": sig["instrument"], "direction": sig["direction"],
            "setup_type": sig.get("setup_type"), "call_type": sig.get("call_type"),
            "rr_tier": sig.get("rr_tier"),
            "theoretical_entry": sig["entry"], "stoploss": sig["stoploss"], "target": sig["target"],
            "dashboard_price": dashboard_price,
            "real_rr_at_detection": sizing["real_rr_at_detection"],
            "already_invalid_at_detection": sizing["already_invalid_at_detection"],
            "risk_amount": sizing["risk_amount"], "stop_distance": sizing["stop_distance"],
            "leverage_used": sizing["leverage_used"],
            "quantity": quantity, "capital_required": sizing["capital_required"],
            "actual_entry_price": actual_entry,
            "status": "OPEN", "actual_exit_price": None,
            "realized_pnl_rupees": None, "realized_pnl_pct_capital": None,
            "capital_at_time_of_trade": settings["current_capital"],
            "trade_date": sig.get("trade_date"),
            "opened_at": now.isoformat(), "closed_at": None,
            "notes": "",
        }
        await db.real_trades.insert_one(doc)
        doc.pop("_id", None)
        return doc

    @router.patch("/trades/{trade_id}")
    async def close_trade(trade_id: str, req: CloseTradeRequest):
        trade = await db.real_trades.find_one({"id": trade_id})
        if not trade:
            raise HTTPException(404, "Trade not found")
        if trade["status"] == "CLOSED":
            raise HTTPException(400, "Trade already closed")

        pnl = compute_realized_pnl(trade["quantity"], trade["actual_entry_price"],
                                    req.actual_exit_price, trade["direction"])
        pnl_pct = compute_pnl_pct_of_capital(pnl, trade["capital_at_time_of_trade"])
        now = ist_now_fn()

        settings = await _get_settings()
        new_capital = round(settings["current_capital"] + pnl, 2)
        await db.capital_settings.update_one({"_id": "singleton"}, {"$set": {"current_capital": new_capital}})

        await db.real_trades.update_one(
            {"id": trade_id},
            {"$set": {
                "status": "CLOSED", "actual_exit_price": req.actual_exit_price,
                "realized_pnl_rupees": pnl, "realized_pnl_pct_capital": pnl_pct,
                "closed_at": now.isoformat(), "notes": req.notes or trade.get("notes", ""),
            }},
        )
        updated = await db.real_trades.find_one({"id": trade_id}, {"_id": 0})
        return {"trade": updated, "new_capital": new_capital}

    @router.get("/trades")
    async def list_trades(status: Optional[str] = None, trade_date: Optional[str] = None):
        q = {}
        if status in ("OPEN", "CLOSED"):
            q["status"] = status
        if trade_date:
            q["trade_date"] = trade_date
        cur = db.real_trades.find(q, {"_id": 0}).sort("opened_at", -1)
        return await cur.to_list(1000)

    @router.get("/daily-pnl")
    async def daily_pnl():
        """Rollup by the day each trade CLOSED (not opened — BTST spans
        days, so P&L belongs to the day it actually resolved)."""
        closed = await db.real_trades.find({"status": "CLOSED"}, {"_id": 0}).sort("closed_at", 1).to_list(5000)
        by_day: dict[str, dict] = {}
        for t in closed:
            day = (t.get("closed_at") or "")[:10]
            if not day:
                continue
            d = by_day.setdefault(day, {
                "date": day, "trades": 0, "wins": 0, "losses": 0,
                "actual_pnl_rupees": 0.0, "r_implied_pnl_rupees": 0.0,
            })
            d["trades"] += 1
            pnl = t.get("realized_pnl_rupees") or 0.0
            d["actual_pnl_rupees"] = round(d["actual_pnl_rupees"] + pnl, 2)
            if pnl > 0:
                d["wins"] += 1
            elif pnl < 0:
                d["losses"] += 1
            # R-implied: what the P&L WOULD be if this trade's R-multiple
            # (from the original signal) were applied to a fixed risk_amount
            # — this is the number that made the original R-vs-rupee gap
            # invisible, kept here specifically so the gap stays visible.
            risk_amount = t.get("risk_amount") or 0.0
            stop_distance = t.get("stop_distance") or 0
            if stop_distance:
                r_mult = pnl / (t["quantity"] * stop_distance) if t.get("quantity") else 0
                d["r_implied_pnl_rupees"] = round(d["r_implied_pnl_rupees"] + r_mult * risk_amount, 2)

        rows = sorted(by_day.values(), key=lambda r: r["date"])
        settings = await _get_settings()
        running = settings["starting_capital"]
        for r in rows:
            running = round(running + r["actual_pnl_rupees"], 2)
            r["running_capital"] = running
            r["pnl_pct_of_capital"] = round(
                (r["actual_pnl_rupees"] / (running - r["actual_pnl_rupees"])) * 100, 3
            ) if (running - r["actual_pnl_rupees"]) > 0 else 0.0
        return {"days": rows, "current_capital": settings["current_capital"],
                "starting_capital": settings["starting_capital"],
                "total_pnl_rupees": round(settings["current_capital"] - settings["starting_capital"], 2)}

    @router.get("/equity-curve")
    async def equity_curve():
        result = await daily_pnl()
        curve = [{"date": "start", "capital": result["starting_capital"]}]
        for r in result["days"]:
            curve.append({"date": r["date"], "capital": r["running_capital"]})
        return curve

    return router
        
