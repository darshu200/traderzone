import { useState, useMemo } from "react";
import TopBar from "@/components/TopBar";
import AssetClassTabs from "@/components/AssetClassTabs";
import { runBacktest, backtestCsvUrl, EQUITY_LIST, FOREX_LIST, INSTRUMENT_META } from "@/lib/api";
import { fmtNum, fmtTimeIST, daysAgoISO, fmtDateISOToday } from "@/lib/format";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";
import { Download, Play } from "@phosphor-icons/react";

export default function BacktestPage() {
    const [assetClass, setAssetClass] = useState("EQUITY");
    const [instrument, setInstrument] = useState("NIFTY");
    const [start, setStart] = useState(daysAgoISO(20));
    const [end, setEnd] = useState(fmtDateISOToday());
    const [busy, setBusy] = useState(false);
    const [result, setResult] = useState(null);

    const instruments = useMemo(
        () => (assetClass === "FOREX" ? FOREX_LIST : EQUITY_LIST),
        [assetClass],
    );

    const handleAssetChange = (v) => {
        setAssetClass(v);
        const list = v === "FOREX" ? FOREX_LIST : EQUITY_LIST;
        if (!list.includes(instrument)) setInstrument(list[0]);
    };

    const fmtPx = (n, sym) => {
        const m = INSTRUMENT_META[sym] || { pip: 2, prefix: "" };
        return `${m.prefix}${fmtNum(n, m.pip)}`;
    };

    const run = async () => {
        setBusy(true); setResult(null);
        try {
            const r = await runBacktest({ instrument, start_date: start, end_date: end });
            setResult(r);
            toast.success(`Backtest complete — ${r.summary.total} signal(s) found`);
        } catch (e) {
            const msg = e?.response?.data?.detail || "Backtest failed";
            toast.error(msg);
        } finally { setBusy(false); }
    };

    return (
        <div className="flex-1 flex flex-col">
            <TopBar title="Backtest" subtitle="Replay historical 15m + 5m data (yfinance) using the same strategy engine" />

            <div className="p-6 grid grid-cols-12 gap-4">
                <div className="col-span-3 ts-surface p-4 space-y-4">
                    <div>
                        <Label className="ts-label">Asset Class</Label>
                        <div className="mt-1">
                            <AssetClassTabs value={assetClass} onChange={handleAssetChange} showAll={false} dataTestidPrefix="bt-ac" />
                        </div>
                    </div>
                    <div>
                        <Label className="ts-label">Instrument</Label>
                        <Select value={instrument} onValueChange={setInstrument}>
                            <SelectTrigger data-testid="bt-instrument" className="mt-1 h-9">
                                <SelectValue />
                            </SelectTrigger>
                            <SelectContent>
                                {instruments.map((i) => <SelectItem key={i} value={i}>{i}</SelectItem>)}
                            </SelectContent>
                        </Select>
                    </div>
                    <div>
                        <Label className="ts-label">Start Date</Label>
                        <Input data-testid="bt-start" type="date" value={start}
                            onChange={(e) => setStart(e.target.value)} className="mt-1 font-mono" />
                    </div>
                    <div>
                        <Label className="ts-label">End Date</Label>
                        <Input data-testid="bt-end" type="date" value={end}
                            onChange={(e) => setEnd(e.target.value)} className="mt-1 font-mono" />
                    </div>
                    <div className="text-[10px] text-[color:var(--ts-text-tertiary)]">
                        Note: 5m/15m historical data is limited to ~60 days by yfinance.
                        Max window enforced: 55 days.
                    </div>
                    <button
                        data-testid="bt-run"
                        onClick={run} disabled={busy}
                        className="ts-btn-primary w-full justify-center"
                    >
                        <Play size={14} weight="bold" />
                        {busy ? "Running…" : "Run Backtest"}
                    </button>
                    {result && (
                        <a
                            data-testid="bt-download"
                            href={backtestCsvUrl(instrument, start, end)}
                            className="ts-btn-ghost w-full justify-center"
                            target="_blank" rel="noreferrer"
                        >
                            <Download size={14} weight="bold" /> Download CSV
                        </a>
                    )}
                </div>

                <div className="col-span-9 ts-surface">
                    {!result ? (
                        <div className="p-10 text-center text-[color:var(--ts-text-secondary)]">
                            <div className="ts-label mb-2">Ready</div>
                            <div className="text-lg font-black tracking-tight">Configure and run a backtest</div>
                            <div className="text-sm mt-2 max-w-md mx-auto">
                                Pick equity or forex, an instrument, a date range up to 55 days, and press Run Backtest.
                            </div>
                        </div>
                    ) : (
                        <>
                            <div className="grid grid-cols-5 gap-0 border-b" style={{ borderColor: "var(--ts-border)" }}>
                                <Stat label="Total" value={result.summary.total} />
                                <Stat label="Won" value={result.summary.won} color="var(--ts-long)" />
                                <Stat label="Lost" value={result.summary.lost} color="var(--ts-short)" />
                                <Stat label="Win Rate" value={`${result.summary.win_rate}%`} color="var(--ts-focus)" />
                                <Stat label="Avg R" value={`${result.summary.avg_r > 0 ? "+" : ""}${result.summary.avg_r}R`}
                                      color={result.summary.avg_r >= 0 ? "var(--ts-long)" : "var(--ts-short)"} />
                            </div>
                            <div className="overflow-auto max-h-[62vh]">
                                <table className="ts-table w-full" data-testid="bt-results-table">
                                    <thead>
                                        <tr>
                                            <th>Time</th>
                                            <th>Dir</th>
                                            <th>Setup</th>
                                            <th>Type</th>
                                            <th className="text-right">Entry</th>
                                            <th className="text-right">Stop</th>
                                            <th className="text-right">Target</th>
                                            <th className="text-right">RR</th>
                                            <th>Outcome</th>
                                            <th className="text-right">R</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {result.signals.map((s, idx) => (
                                            <tr key={idx}>
                                                <td className="font-mono text-xs">{fmtTimeIST(s.timestamp)}</td>
                                                <td><span className={s.direction === "LONG" ? "ts-badge-long" : "ts-badge-short"}>{s.direction}</span></td>
                                                <td className="text-xs text-[color:var(--ts-text-secondary)]">{s.setup_type}</td>
                                                <td><span className="ts-badge-neutral">{s.call_type}</span></td>
                                                <td className="text-right font-mono">{fmtPx(s.entry, instrument)}</td>
                                                <td className="text-right font-mono" style={{ color: "var(--ts-short)" }}>{fmtPx(s.stoploss, instrument)}</td>
                                                <td className="text-right font-mono" style={{ color: "var(--ts-long)" }}>{fmtPx(s.target, instrument)}</td>
                                                <td className="text-right font-mono">1:{fmtNum(s.rr)}</td>
                                                <td>
                                                    {s.outcome === "WON" && <span className="ts-badge-long">WON</span>}
                                                    {s.outcome === "LOST" && <span className="ts-badge-short">LOST</span>}
                                                    {s.outcome === "OPEN" && <span className="ts-badge-neutral">OPEN</span>}
                                                </td>
                                                <td className="text-right font-mono" style={{
                                                    color: s.r_multiple > 0 ? "var(--ts-long)" :
                                                           s.r_multiple < 0 ? "var(--ts-short)" : undefined
                                                }}>
                                                    {s.r_multiple ? `${s.r_multiple > 0 ? "+" : ""}${fmtNum(s.r_multiple)}R` : "—"}
                                                </td>
                                            </tr>
                                        ))}
                                        {result.signals.length === 0 && (
                                            <tr><td colSpan={10} className="text-center py-8 text-[color:var(--ts-text-tertiary)]">
                                                No signals found in this window with the current strategy filters.
                                            </td></tr>
                                        )}
                                    </tbody>
                                </table>
                            </div>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}

function Stat({ label, value, color }) {
    return (
        <div className="p-4 border-r" style={{ borderColor: "var(--ts-border)" }}>
            <div className="ts-label">{label}</div>
            <div className="text-xl font-black font-mono tracking-tight mt-1" style={{ color: color || "var(--ts-text-primary)" }}>
                {value}
            </div>
        </div>
    );
}
