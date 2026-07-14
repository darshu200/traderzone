import { useEffect, useState, useCallback } from "react";
import TopBar from "@/components/TopBar";
import CloseTradeDialog from "@/components/CloseTradeDialog";
import AssetClassTabs from "@/components/AssetClassTabs";
import { getSignals, deleteSignal, INSTRUMENTS_LIST, INSTRUMENT_META } from "@/lib/api";
import { fmtNum, fmtTimeIST } from "@/lib/format";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Trash, Warning } from "@phosphor-icons/react";
import { toast } from "sonner";

const OUTCOMES = ["ALL", "OPEN", "WON", "LOST", "BREAKEVEN"];

export default function TradeLogPage() {
    const [rows, setRows] = useState([]);
    const [filter, setFilter] = useState("ALL");
    const [instFilter, setInstFilter] = useState("ALL");
    const [assetClass, setAssetClass] = useState("ALL");
    const [dialogOpen, setDialogOpen] = useState(false);
    const [dialogSignal, setDialogSignal] = useState(null);

    const load = useCallback(async () => {
        const params = { limit: 500 };
        if (instFilter !== "ALL") params.instrument = instFilter;
        if (assetClass !== "ALL") params.asset_class = assetClass;
        const data = await getSignals(params);
        const filtered = filter === "ALL" ? data : data.filter((s) => (s.outcome || "OPEN") === filter);
        setRows(filtered);
    }, [filter, instFilter, assetClass]);

    useEffect(() => { load(); }, [load]);

    const handleDelete = async (id) => {
        if (!window.confirm("Delete this signal?")) return;
        try { await deleteSignal(id); toast.success("Deleted"); load(); }
        catch { toast.error("Delete failed"); }
    };

    const openClose = (s) => { setDialogSignal(s); setDialogOpen(true); };

    const fmtPx = (n, sym) => {
        const m = INSTRUMENT_META[sym] || { pip: 2, prefix: "" };
        return `${m.prefix}${fmtNum(n, m.pip)}`;
    };

    return (
        <div className="flex-1 flex flex-col">
            <TopBar title="Trade Log" subtitle="Every signal ever generated. Mark outcomes to update analytics." />

            <div className="px-6 py-4 flex items-center gap-3 border-b" style={{ borderColor: "var(--ts-border)" }}>
                <div className="flex items-center gap-2">
                    <span className="ts-label">Asset</span>
                    <AssetClassTabs value={assetClass} onChange={setAssetClass} dataTestidPrefix="log-ac" />
                </div>
                <div className="flex items-center gap-2">
                    <span className="ts-label">Outcome</span>
                    <Select value={filter} onValueChange={setFilter}>
                        <SelectTrigger data-testid="filter-outcome" className="w-40 h-9">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            {OUTCOMES.map((o) => <SelectItem key={o} value={o}>{o}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="flex items-center gap-2">
                    <span className="ts-label">Instrument</span>
                    <Select value={instFilter} onValueChange={setInstFilter}>
                        <SelectTrigger data-testid="filter-instrument" className="w-44 h-9">
                            <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                            <SelectItem value="ALL">ALL</SelectItem>
                            {INSTRUMENTS_LIST.map((i) => <SelectItem key={i} value={i}>{i}</SelectItem>)}
                        </SelectContent>
                    </Select>
                </div>
                <div className="ml-auto ts-label" data-testid="trade-log-count">
                    {rows.length} record(s)
                </div>
            </div>

            <div className="flex-1 overflow-auto">
                {rows.length === 0 ? (
                    <div className="p-10 text-center text-[color:var(--ts-text-secondary)]">
                        <img
                            alt="empty"
                            src="https://images.unsplash.com/photo-1510519138101-570d1dca3d66?crop=entropy&cs=srgb&fm=jpg&ixid=M3w3NTY2NzV8MHwxfHNlYXJjaHwxfHxlbXB0eSUyMGRlc2slMjBub3RlYm9vayUyMGRhcmt8ZW58MHx8fHwxNzgzMTAzMzM5fDA&ixlib=rb-4.1.0&q=85"
                            className="w-40 h-24 object-cover mx-auto rounded-sm opacity-40 grayscale mb-3"
                        />
                        <div className="text-lg font-black tracking-tight">No trades yet</div>
                        <div className="text-sm mt-1">Signals generated during market hours will appear here.</div>
                    </div>
                ) : (
                    <table className="ts-table w-full" data-testid="trade-log-table">
                        <thead>
                            <tr>
                                <th>Time</th>
                                <th>Instrument</th>
                                <th>Class</th>
                                <th>Dir</th>
                                <th>Setup</th>
                                <th className="text-right">Entry</th>
                                <th className="text-right">Stop</th>
                                <th className="text-right">Target</th>
                                <th className="text-right">RR</th>
                                <th>Type</th>
                                <th>Outcome</th>
                                <th className="text-right">Exit</th>
                                <th className="text-right">R</th>
                                <th></th>
                            </tr>
                        </thead>
                        <tbody>
                            {rows.map((r) => (
                                <tr key={r.id} data-testid={`trade-row-${r.id}`}>
                                    <td className="font-mono text-xs">{fmtTimeIST(r.timestamp)}</td>
                                    <td className="font-semibold">
                                        <div className="flex items-center gap-1">
                                            {r.instrument}
                                            {r.stale && (
                                                <span title={`Open ${r.age_hours}h — review`}
                                                      data-testid={`stale-flag-${r.id}`}
                                                      style={{ color: "var(--ts-short)" }}>
                                                    <Warning size={12} weight="bold" />
                                                </span>
                                            )}
                                        </div>
                                    </td>
                                    <td>
                                        <span className="ts-badge-neutral"
                                              style={{ color: r.asset_class === "FOREX" ? "var(--ts-focus)" : "var(--ts-text-secondary)" }}>
                                            {r.asset_class || "EQUITY"}
                                        </span>
                                    </td>
                                    <td>
                                        <span className={r.direction === "LONG" ? "ts-badge-long" : "ts-badge-short"}>
                                            {r.direction}
                                        </span>
                                    </td>
                                    <td className="text-xs text-[color:var(--ts-text-secondary)]">{r.setup_type}</td>
                                    <td className="text-right font-mono">{fmtPx(r.entry, r.instrument)}</td>
                                    <td className="text-right font-mono" style={{ color: "var(--ts-short)" }}>{fmtPx(r.stoploss, r.instrument)}</td>
                                    <td className="text-right font-mono" style={{ color: "var(--ts-long)" }}>{fmtPx(r.target, r.instrument)}</td>
                                    <td className="text-right font-mono">1:{fmtNum(r.rr)}</td>
                                    <td><span className="ts-badge-neutral">{r.call_type}</span></td>
                                    <td>
                                        <OutcomeBadge outcome={r.outcome || "OPEN"} />
                                    </td>
                                    <td className="text-right font-mono">{r.exit_price ? fmtPx(r.exit_price, r.instrument) : "—"}</td>
                                    <td className="text-right font-mono" style={{
                                        color: r.r_multiple > 0 ? "var(--ts-long)" :
                                               r.r_multiple < 0 ? "var(--ts-short)" : undefined
                                    }}>
                                        {r.r_multiple === null || r.r_multiple === undefined ? "—" : `${r.r_multiple > 0 ? "+" : ""}${fmtNum(r.r_multiple)}R`}
                                    </td>
                                    <td>
                                        <div className="flex items-center gap-1 justify-end">
                                            {(!r.outcome || r.outcome === "OPEN") && (
                                                <button className="ts-btn-ghost !text-[10px] !px-2 !py-1"
                                                    onClick={() => openClose(r)}
                                                    data-testid={`close-row-${r.id}`}>Close</button>
                                            )}
                                            <button className="p-1 text-[color:var(--ts-text-tertiary)] hover:text-[color:var(--ts-short)]"
                                                onClick={() => handleDelete(r.id)}
                                                data-testid={`delete-row-${r.id}`}>
                                                <Trash size={14} weight="bold" />
                                            </button>
                                        </div>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                )}
            </div>

            <CloseTradeDialog
                signal={dialogSignal} open={dialogOpen}
                onOpenChange={setDialogOpen} onSaved={load}
            />
        </div>
    );
}

function OutcomeBadge({ outcome }) {
    if (outcome === "WON") return <span className="ts-badge-long">WON</span>;
    if (outcome === "LOST") return <span className="ts-badge-short">LOST</span>;
    if (outcome === "BREAKEVEN") return <span className="ts-badge-neutral">BE</span>;
    return <span className="ts-badge-neutral">OPEN</span>;
}
