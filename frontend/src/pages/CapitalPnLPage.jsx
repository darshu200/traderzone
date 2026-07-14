import { useEffect, useState, useCallback } from "react";
import TopBar from "@/components/TopBar";
import {
    getCapitalSettings, updateCapitalSettings, getQuantitySuggestion,
    takeTrade, closeTrade, listCapitalTrades, getDailyPnl, getTodaySignals,
} from "@/lib/api";
import { fmtNum, fmtTimeIST } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Warning, CheckCircle } from "@phosphor-icons/react";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from "recharts";
import { toast } from "sonner";

export default function CapitalPnLPage() {
    const [settings, setSettings] = useState(null);
    const [settingsForm, setSettingsForm] = useState(null);
    const [dailyPnl, setDailyPnl] = useState(null);
    const [openTrades, setOpenTrades] = useState([]);
    const [allTrades, setAllTrades] = useState([]);
    const [signals, setSignals] = useState([]);
    const [previewFor, setPreviewFor] = useState(null); // signal id currently previewing
    const [preview, setPreview] = useState(null);
    const [qtyOverride, setQtyOverride] = useState("");
    const [entryOverride, setEntryOverride] = useState("");
    const [closeInputs, setCloseInputs] = useState({}); // trade_id -> exit price string

    const load = useCallback(async () => {
        const [s, dp, open, all, sigs] = await Promise.all([
            getCapitalSettings(), getDailyPnl(),
            listCapitalTrades({ status: "OPEN" }), listCapitalTrades({}),
            getTodaySignals(),
        ]);
        setSettings(s); setSettingsForm(s); setDailyPnl(dp);
        setOpenTrades(open); setAllTrades(all); setSignals(sigs);
    }, []);

    useEffect(() => { load(); const id = setInterval(load, 30000); return () => clearInterval(id); }, [load]);

    const takenSignalIds = new Set(allTrades.map((t) => t.signal_id));
    const availableSignals = signals.filter((s) => !takenSignalIds.has(s.id));

    const saveSettings = async () => {
        try {
            const body = {
                starting_capital: Number(settingsForm.starting_capital),
                risk_per_trade_pct: Number(settingsForm.risk_per_trade_pct),
                intraday_leverage: Number(settingsForm.intraday_leverage),
                btst_leverage: Number(settingsForm.btst_leverage),
            };
            const updated = await updateCapitalSettings(body);
            setSettings(updated); setSettingsForm(updated);
            toast.success("Settings saved");
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Could not save settings");
        }
    };

    const openPreview = async (signal) => {
        setPreviewFor(signal.id);
        setPreview(null);
        const res = await getQuantitySuggestion(signal.id);
        setPreview(res);
        setQtyOverride(String(res.sizing.quantity));
        setEntryOverride(String(res.signal.dashboard_price ?? res.signal.entry));
    };

    const confirmTake = async (signalId) => {
        try {
            await takeTrade({
                signal_id: signalId,
                quantity_override: Number(qtyOverride),
                actual_entry_price: Number(entryOverride),
            });
            toast.success("Trade recorded");
            setPreviewFor(null); setPreview(null);
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Could not record trade");
        }
    };

    const submitClose = async (tradeId) => {
        const val = closeInputs[tradeId];
        if (!val) { toast.error("Enter exit price"); return; }
        try {
            await closeTrade(tradeId, { actual_exit_price: Number(val) });
            toast.success("Trade closed");
            setCloseInputs((c) => ({ ...c, [tradeId]: "" }));
            load();
        } catch (e) {
            toast.error(e?.response?.data?.detail || "Could not close trade");
        }
    };

    if (!settings || !dailyPnl) {
        return (
            <div className="flex-1 flex flex-col">
                <TopBar title="Capital & P&L" />
                <div className="p-6 text-[color:var(--ts-text-secondary)]">Loading…</div>
            </div>
        );
    }

    const equity = [
        { date: "Start", capital: dailyPnl.starting_capital },
        ...dailyPnl.days.map((d) => ({ date: d.date.slice(5), capital: d.running_capital })),
    ];
    const totalPnl = dailyPnl.total_pnl_rupees;
    const todayStr = new Date().toISOString().slice(0, 10);
    const todayRow = dailyPnl.days.find((d) => d.date === todayStr);

    return (
        <div className="flex-1 flex flex-col">
            <TopBar title="Capital & P&L" subtitle="Real-money position sizing, day-by-day P&L — separate from the R-multiple based Analytics page" />

            <div className="p-6 grid grid-cols-4 gap-4">
                <KPI label="Current Capital" value={`₹${fmtNum(dailyPnl.current_capital, 0)}`} />
                <KPI label="Total P&L" value={`${totalPnl >= 0 ? "+" : ""}₹${fmtNum(totalPnl, 0)}`}
                     color={totalPnl >= 0 ? "var(--ts-long)" : "var(--ts-short)"} />
                <KPI label="Today's P&L" value={todayRow ? `${todayRow.actual_pnl_rupees >= 0 ? "+" : ""}₹${fmtNum(todayRow.actual_pnl_rupees, 0)}` : "₹0"}
                     color={todayRow && todayRow.actual_pnl_rupees < 0 ? "var(--ts-short)" : "var(--ts-long)"}
                     sub={todayRow ? `${todayRow.trades} trades closed today` : "No trades closed today"} />
                <KPI label="Open Positions" value={openTrades.length} />
            </div>

            {/* Settings */}
            <div className="px-6 pb-6">
                <div className="ts-surface p-4">
                    <div className="ts-label mb-3">Risk Settings</div>
                    <div className="grid grid-cols-5 gap-3 items-end">
                        <Field label="Starting Capital (₹)">
                            <Input type="number" value={settingsForm.starting_capital}
                                   onChange={(e) => setSettingsForm({ ...settingsForm, starting_capital: e.target.value })} />
                        </Field>
                        <Field label="Risk / Trade (%)">
                            <Input type="number" step="0.1" value={settingsForm.risk_per_trade_pct}
                                   onChange={(e) => setSettingsForm({ ...settingsForm, risk_per_trade_pct: e.target.value })} />
                        </Field>
                        <Field label="Intraday Leverage">
                            <Input type="number" step="0.5" value={settingsForm.intraday_leverage}
                                   onChange={(e) => setSettingsForm({ ...settingsForm, intraday_leverage: e.target.value })} />
                        </Field>
                        <Field label="BTST Leverage">
                            <Input type="number" step="0.5" value={settingsForm.btst_leverage}
                                   onChange={(e) => setSettingsForm({ ...settingsForm, btst_leverage: e.target.value })} />
                        </Field>
                        <Button onClick={saveSettings} data-testid="save-capital-settings">Save</Button>
                    </div>
                    <div className="text-[10px] mt-2" style={{ color: "var(--ts-text-tertiary)" }}>
                        Starting capital can only be changed before any trades are recorded — after that,
                        current capital reflects real trading history.
                    </div>
                </div>
            </div>

            {/* Equity curve */}
            <div className="px-6 pb-6">
                <div className="ts-surface p-4">
                    <div className="ts-label mb-2">Real ₹ Equity Curve</div>
                    <ResponsiveContainer width="100%" height={220}>
                        <LineChart data={equity}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                            <XAxis dataKey="date" stroke="#71717A" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} />
                            <YAxis stroke="#71717A" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} domain={["auto", "auto"]} />
                            <Tooltip contentStyle={{ background: "#121215", border: "1px solid #27272A", fontSize: 12 }} />
                            <Line type="monotone" dataKey="capital" stroke="#00E5FF" strokeWidth={2} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                    {equity.length <= 1 && (
                        <div className="text-center py-6 text-[color:var(--ts-text-tertiary)] text-sm">
                            No closed real-money trades yet.
                        </div>
                    )}
                </div>
            </div>

            {/* Take a signal */}
            <div className="px-6 pb-6">
                <div className="ts-surface p-4">
                    <div className="ts-label mb-3">Today's Signals — Not Yet Taken</div>
                    {availableSignals.length === 0 && (
                        <div className="text-sm text-[color:var(--ts-text-tertiary)]">
                            No untaken signals right now.
                        </div>
                    )}
                    <div className="space-y-2">
                        {availableSignals.map((s) => (
                            <div key={s.id} className="border rounded p-3" style={{ borderColor: "var(--ts-border)" }}
                                 data-testid={`take-signal-${s.instrument}`}>
                                <div className="flex items-center justify-between text-sm">
                                    <div className="flex items-center gap-2">
                                        <span className="font-bold">{s.instrument}</span>
                                        <span style={{ color: s.direction === "LONG" ? "var(--ts-long)" : "var(--ts-short)" }}>
                                            {s.direction}
                                        </span>
                                        <span className="text-[color:var(--ts-text-tertiary)]">{s.setup_type}</span>
                                        <span className="text-[color:var(--ts-text-tertiary)]">{s.call_type}</span>
                                        {s.already_invalid_at_detection && (
                                            <span className="flex items-center gap-1 text-[10px] uppercase" style={{ color: "#FF453A" }}>
                                                <Warning size={12} /> already past SL/target
                                            </span>
                                        )}
                                    </div>
                                    <Button size="sm" variant="outline" onClick={() => openPreview(s)}>
                                        Preview & Take
                                    </Button>
                                </div>
                                <div className="text-xs mt-1 font-mono text-[color:var(--ts-text-secondary)]">
                                    Theoretical entry {fmtNum(s.entry)} · Dashboard price {fmtNum(s.dashboard_price ?? s.entry)} ·
                                    Real RR {s.real_rr_at_detection != null ? `1:${fmtNum(s.real_rr_at_detection, 1)}` : "—"} ·
                                    {" "}{fmtTimeIST(s.timestamp)}
                                </div>

                                {previewFor === s.id && (
                                    <div className="mt-3 p-3 border-t" style={{ borderColor: "var(--ts-border)" }}>
                                        {!preview ? (
                                            <div className="text-xs text-[color:var(--ts-text-tertiary)]">Calculating…</div>
                                        ) : (
                                            <>
                                                <div className="grid grid-cols-4 gap-3 text-xs mb-3">
                                                    <MiniStat label="Risk Amount" value={`₹${fmtNum(preview.sizing.risk_amount, 0)}`} />
                                                    <MiniStat label="Leverage" value={`${preview.sizing.leverage_used}x`} />
                                                    <MiniStat label="Capital Required" value={`₹${fmtNum(preview.sizing.capital_required, 0)}`} />
                                                    <MiniStat label="Suggested Qty" value={preview.sizing.quantity} />
                                                </div>
                                                {preview.sizing.margin_limited && (
                                                    <div className="text-[11px] mb-2 flex items-center gap-1" style={{ color: "#FF9F0A" }}>
                                                        <Warning size={12} /> Quantity capped by available capital/margin, not risk %.
                                                    </div>
                                                )}
                                                {preview.sizing.insufficient_capital && (
                                                    <div className="text-[11px] mb-2 flex items-center gap-1" style={{ color: "#FF453A" }}>
                                                        <Warning size={12} /> Insufficient capital — quantity would be 0.
                                                    </div>
                                                )}
                                                <div className="grid grid-cols-3 gap-3 items-end">
                                                    <Field label="Quantity">
                                                        <Input type="number" value={qtyOverride}
                                                               onChange={(e) => setQtyOverride(e.target.value)} />
                                                    </Field>
                                                    <Field label="Actual Entry Price">
                                                        <Input type="number" value={entryOverride}
                                                               onChange={(e) => setEntryOverride(e.target.value)} />
                                                    </Field>
                                                    <div className="flex gap-2">
                                                        <Button onClick={() => confirmTake(s.id)} data-testid={`confirm-take-${s.instrument}`}>
                                                            <CheckCircle size={14} className="mr-1" /> Confirm
                                                        </Button>
                                                        <Button variant="ghost" onClick={() => { setPreviewFor(null); setPreview(null); }}>
                                                            Cancel
                                                        </Button>
                                                    </div>
                                                </div>
                                            </>
                                        )}
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>
                </div>
            </div>

            {/* Open positions */}
            <div className="px-6 pb-6">
                <div className="ts-surface p-4">
                    <div className="ts-label mb-3">Open Real-Money Positions</div>
                    <table className="ts-table w-full">
                        <thead>
                            <tr>
                                <th>Instrument</th><th>Dir</th><th className="text-right">Qty</th>
                                <th className="text-right">Entry</th><th className="text-right">Risk ₹</th>
                                <th>Close At</th><th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {openTrades.map((t) => (
                                <tr key={t.id}>
                                    <td className="font-semibold">{t.instrument}</td>
                                    <td style={{ color: t.direction === "LONG" ? "var(--ts-long)" : "var(--ts-short)" }}>{t.direction}</td>
                                    <td className="text-right font-mono">{t.quantity}</td>
                                    <td className="text-right font-mono">{fmtNum(t.actual_entry_price)}</td>
                                    <td className="text-right font-mono">₹{fmtNum(t.risk_amount, 0)}</td>
                                    <td>
                                        <Input type="number" className="h-7 w-28" placeholder="exit price"
                                               value={closeInputs[t.id] || ""}
                                               onChange={(e) => setCloseInputs((c) => ({ ...c, [t.id]: e.target.value }))} />
                                    </td>
                                    <td>
                                        <Button size="sm" onClick={() => submitClose(t.id)} data-testid={`close-trade-${t.instrument}`}>
                                            Close
                                        </Button>
                                    </td>
                                </tr>
                            ))}
                            {openTrades.length === 0 && (
                                <tr><td colSpan={7} className="text-center py-6 text-[color:var(--ts-text-tertiary)]">No open positions</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>

            {/* Daily P&L table - the actual ask */}
            <div className="px-6 pb-6">
                <div className="ts-surface p-4">
                    <div className="ts-label mb-3">Daily P&L — Actual ₹ vs R-Implied ₹</div>
                    <table className="ts-table w-full" data-testid="daily-pnl-table">
                        <thead>
                            <tr>
                                <th>Date</th><th className="text-right">Trades</th>
                                <th className="text-right">Won</th><th className="text-right">Lost</th>
                                <th className="text-right">Actual P&L</th>
                                <th className="text-right">R-Implied P&L</th>
                                <th className="text-right">Gap</th>
                                <th className="text-right">% of Capital</th>
                                <th className="text-right">Running Capital</th>
                            </tr>
                        </thead>
                        <tbody>
                            {dailyPnl.days.map((d) => {
                                const gap = round2(d.actual_pnl_rupees - d.r_implied_pnl_rupees);
                                return (
                                    <tr key={d.date}>
                                        <td className="font-mono">{d.date}</td>
                                        <td className="text-right font-mono">{d.trades}</td>
                                        <td className="text-right font-mono" style={{ color: "var(--ts-long)" }}>{d.wins}</td>
                                        <td className="text-right font-mono" style={{ color: "var(--ts-short)" }}>{d.losses}</td>
                                        <td className="text-right font-mono" style={{ color: d.actual_pnl_rupees >= 0 ? "var(--ts-long)" : "var(--ts-short)" }}>
                                            {d.actual_pnl_rupees >= 0 ? "+" : ""}₹{fmtNum(d.actual_pnl_rupees, 0)}
                                        </td>
                                        <td className="text-right font-mono text-[color:var(--ts-text-secondary)]">
                                            {d.r_implied_pnl_rupees >= 0 ? "+" : ""}₹{fmtNum(d.r_implied_pnl_rupees, 0)}
                                        </td>
                                        <td className="text-right font-mono" style={{ color: Math.abs(gap) > 50 ? "#FF9F0A" : "var(--ts-text-tertiary)" }}>
                                            {gap >= 0 ? "+" : ""}₹{fmtNum(gap, 0)}
                                        </td>
                                        <td className="text-right font-mono">{fmtNum(d.pnl_pct_of_capital)}%</td>
                                        <td className="text-right font-mono">₹{fmtNum(d.running_capital, 0)}</td>
                                    </tr>
                                );
                            })}
                            {dailyPnl.days.length === 0 && (
                                <tr><td colSpan={9} className="text-center py-6 text-[color:var(--ts-text-tertiary)]">No closed trades yet</td></tr>
                            )}
                        </tbody>
                    </table>
                    <div className="text-[10px] mt-2" style={{ color: "var(--ts-text-tertiary)" }}>
                        "Gap" is the difference between what actually happened in rupees and what the R-multiples alone
                        would imply at fixed risk — this is the number that stays at 0 once position sizing is working correctly.
                    </div>
                </div>
            </div>
        </div>
    );
}

function KPI({ label, value, color, sub }) {
    return (
        <div className="ts-surface p-4">
            <div className="ts-label">{label}</div>
            <div className="mt-1 text-2xl font-black font-mono tracking-tight" style={{ color: color || "var(--ts-text-primary)" }}>
                {value}
            </div>
            {sub && <div className="text-xs text-[color:var(--ts-text-tertiary)] mt-1">{sub}</div>}
        </div>
    );
}

function MiniStat({ label, value }) {
    return (
        <div>
            <div className="text-[9px] uppercase tracking-widest text-[color:var(--ts-text-tertiary)]">{label}</div>
            <div className="font-mono font-semibold">{value}</div>
        </div>
    );
}

function Field({ label, children }) {
    return (
        <div>
            <div className="text-[9px] uppercase tracking-widest text-[color:var(--ts-text-tertiary)] mb-1">{label}</div>
            {children}
        </div>
    );
}

function round2(n) { return Math.round(n * 100) / 100; }
