import { useEffect, useState, useCallback } from "react";
import TopBar from "@/components/TopBar";
import AssetClassTabs from "@/components/AssetClassTabs";
import { getAnalytics } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import {
    LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
    BarChart, Bar,
} from "recharts";

export default function AnalyticsPage() {
    const [assetClass, setAssetClass] = useState("ALL");
    const [data, setData] = useState(null);
    const load = useCallback(async () => {
        setData(null);
        setData(await getAnalytics(assetClass));
    }, [assetClass]);
    useEffect(() => { load(); }, [load]);

    if (!data) return (
        <div className="flex-1 flex flex-col">
            <TopBar title="Performance Analytics" />
            <div className="p-6 text-[color:var(--ts-text-secondary)]">Loading…</div>
        </div>
    );

    const equity = (data.equity_curve || []).map((e, i) => ({ idx: i + 1, cum: e.cum_r, t: e.t }));
    const setupData = Object.entries(data.by_setup || {}).map(([k, v]) => ({ name: k, count: v }));
    const instrData = Object.entries(data.by_instrument || {}).map(([k, v]) => ({
        name: k, total: v.total, won: v.won, lost: v.lost, r: v.r,
    }));
    const byType = Object.entries(data.by_type || {}).map(([k, v]) => ({ name: k, ...v }));
    const byAsset = Object.entries(data.by_asset_class || {}).map(([k, v]) => ({ name: k, ...v }));

    return (
        <div className="flex-1 flex flex-col">
            <TopBar title="Performance Analytics" subtitle="Win-rate, R-multiple and equity curve across all recorded signals" />

            <div className="px-6 py-3 border-b flex items-center gap-3" style={{ borderColor: "var(--ts-border)" }}>
                <span className="ts-label">Asset Class</span>
                <AssetClassTabs value={assetClass} onChange={setAssetClass} dataTestidPrefix="analytics-ac" />
            </div>

            <div className="p-6 grid grid-cols-4 gap-4">
                <KPI label="Total Signals" value={data.total_signals} />
                <KPI label="Win Rate" value={`${fmtNum(data.win_rate)}%`} color="var(--ts-focus)" />
                <KPI label="Avg R" value={`${data.avg_r > 0 ? "+" : ""}${fmtNum(data.avg_r)}R`}
                     color={data.avg_r >= 0 ? "var(--ts-long)" : "var(--ts-short)"} />
                <KPI label="Closed" value={`${data.closed} / ${data.total_signals}`}
                     sub={`Open: ${data.open}`} />
            </div>

            <div className="px-6 pb-6 grid grid-cols-12 gap-4">
                <div className="col-span-8 ts-surface p-4" data-testid="equity-curve">
                    <div className="ts-label mb-2">Equity Curve (Cumulative R)</div>
                    <ResponsiveContainer width="100%" height={280}>
                        <LineChart data={equity}>
                            <CartesianGrid strokeDasharray="3 3" stroke="#27272A" />
                            <XAxis dataKey="idx" stroke="#71717A" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} />
                            <YAxis stroke="#71717A" tick={{ fontSize: 10, fontFamily: "IBM Plex Mono" }} />
                            <Tooltip contentStyle={{ background: "#121215", border: "1px solid #27272A", fontSize: 12 }} />
                            <Line type="monotone" dataKey="cum" stroke="#00E5FF" strokeWidth={2} dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                    {equity.length === 0 && (
                        <div className="text-center py-10 text-[color:var(--ts-text-tertiary)] text-sm">
                            No closed trades yet. Mark outcomes in Trade Log to see the curve.
                        </div>
                    )}
                </div>

                <div className="col-span-4 ts-surface p-4">
                    <div className="ts-label mb-3">By Setup Type</div>
                    <ResponsiveContainer width="100%" height={120}>
                        <BarChart data={setupData}>
                            <XAxis dataKey="name" hide />
                            <Tooltip contentStyle={{ background: "#121215", border: "1px solid #27272A", fontSize: 12 }} />
                            <Bar dataKey="count" fill="#00E5FF" />
                        </BarChart>
                    </ResponsiveContainer>
                    <div className="space-y-1 mt-2">
                        {setupData.map((s) => (
                            <div key={s.name} className="flex justify-between text-xs">
                                <span>{s.name}</span>
                                <span className="font-mono">{s.count}</span>
                            </div>
                        ))}
                        {setupData.length === 0 && <div className="text-xs text-[color:var(--ts-text-tertiary)]">No data</div>}
                    </div>

                    <div className="ts-label mt-4 mb-2">By Asset Class</div>
                    {byAsset.length === 0 && <div className="text-xs text-[color:var(--ts-text-tertiary)]">No data</div>}
                    {byAsset.map((v) => {
                        const closed = v.won + v.lost;
                        const wr = closed ? Math.round((v.won / closed) * 100) : 0;
                        return (
                            <div key={v.name} className="flex justify-between items-center text-xs py-1 border-b"
                                 style={{ borderColor: "var(--ts-border)" }}
                                 data-testid={`analytics-asset-${v.name}`}>
                                <span>{v.name}</span>
                                <span className="font-mono text-[color:var(--ts-text-secondary)]">{v.total} · {wr}% win · {v.r > 0 ? "+" : ""}{fmtNum(v.r)}R</span>
                            </div>
                        );
                    })}

                    <div className="ts-label mt-4 mb-2">By Call Type</div>
                    {byType.length === 0 && <div className="text-xs text-[color:var(--ts-text-tertiary)]">No data</div>}
                    {byType.map((v) => {
                        const closed = v.won + v.lost;
                        const wr = closed ? Math.round((v.won / closed) * 100) : 0;
                        return (
                            <div key={v.name} className="flex justify-between items-center text-xs py-1 border-b" style={{ borderColor: "var(--ts-border)" }}>
                                <span>{v.name}</span>
                                <span className="font-mono text-[color:var(--ts-text-secondary)]">{v.total} · {wr}% win · {v.r > 0 ? "+" : ""}{fmtNum(v.r)}R</span>
                            </div>
                        );
                    })}
                </div>

                <div className="col-span-12 ts-surface p-4">
                    <div className="ts-label mb-2">By Instrument</div>
                    <table className="ts-table w-full" data-testid="by-instrument-table">
                        <thead>
                            <tr>
                                <th>Symbol</th>
                                <th className="text-right">Total</th>
                                <th className="text-right">Won</th>
                                <th className="text-right">Lost</th>
                                <th className="text-right">Cum R</th>
                                <th className="text-right">Win %</th>
                            </tr>
                        </thead>
                        <tbody>
                            {instrData.map((i) => {
                                const closed = i.won + i.lost;
                                const wr = closed ? Math.round((i.won / closed) * 100) : 0;
                                return (
                                    <tr key={i.name}>
                                        <td className="font-semibold">{i.name}</td>
                                        <td className="text-right font-mono">{i.total}</td>
                                        <td className="text-right font-mono" style={{ color: "var(--ts-long)" }}>{i.won}</td>
                                        <td className="text-right font-mono" style={{ color: "var(--ts-short)" }}>{i.lost}</td>
                                        <td className="text-right font-mono" style={{ color: i.r >= 0 ? "var(--ts-long)" : "var(--ts-short)" }}>
                                            {i.r > 0 ? "+" : ""}{fmtNum(i.r)}R
                                        </td>
                                        <td className="text-right font-mono">{wr}%</td>
                                    </tr>
                                );
                            })}
                            {instrData.length === 0 && (
                                <tr><td colSpan={6} className="text-center py-6 text-[color:var(--ts-text-tertiary)]">No data yet</td></tr>
                            )}
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    );
}

function KPI({ label, value, color, sub }) {
    return (
        <div className="ts-surface p-4" data-testid={`kpi-${label.toLowerCase().replace(/\s+/g, "-")}`}>
            <div className="ts-label">{label}</div>
            <div className="mt-1 text-2xl font-black font-mono tracking-tight" style={{ color: color || "var(--ts-text-primary)" }}>
                {value}
            </div>
            {sub && <div className="text-xs text-[color:var(--ts-text-tertiary)] mt-1">{sub}</div>}
        </div>
    );
}
