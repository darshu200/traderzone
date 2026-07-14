import { useEffect, useState } from "react";
import { getRejectedSignals } from "@/lib/api";
import { ClockCounterClockwise } from "@phosphor-icons/react";

export default function RejectedSignalsPanel() {
    const [data, setData] = useState(null);
    const [expanded, setExpanded] = useState(false);

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            const res = await getRejectedSignals();
            if (!cancelled) setData(res);
        };
        load();
        const id = setInterval(load, 60000);
        return () => { cancelled = true; clearInterval(id); };
    }, []);

    if (!data || data.count === 0) return null;

    return (
        <div className="border-b" style={{ borderColor: "var(--ts-border)" }}>
            <button
                className="w-full px-4 py-3 flex items-center justify-between text-left"
                onClick={() => setExpanded((e) => !e)}
                data-testid="rejected-signals-toggle"
            >
                <span className="flex items-center gap-2 text-sm font-bold">
                    <ClockCounterClockwise size={16} weight="bold" color="#FF9F0A" />
                    Missed (too stale)
                </span>
                <span className="font-mono text-sm font-semibold" style={{ color: "#FF9F0A" }}>
                    {data.count} today
                </span>
            </button>
            {expanded && (
                <div className="px-4 pb-3">
                    <div className="text-[10px] uppercase tracking-widest text-[color:var(--ts-text-tertiary)] mb-2">
                        Avg staleness: {data.avg_staleness_min}m &nbsp;·&nbsp;
                        BOS-OB-Retest: {data.by_setup_type["BOS-OB-Retest"] || 0} &nbsp;·&nbsp;
                        Liquidity-Sweep: {data.by_setup_type["Liquidity-Sweep"] || 0}
                    </div>
                    <div className="space-y-1.5 max-h-64 overflow-y-auto">
                        {data.rows.slice(0, 20).map((r, i) => (
                            <div key={i} className="flex items-center justify-between text-xs py-1 border-b"
                                 style={{ borderColor: "var(--ts-border)" }}>
                                <span className="font-bold">{r.instrument}</span>
                                <span style={{ color: "var(--ts-text-tertiary)" }}>{r.direction}</span>
                                <span style={{ color: "var(--ts-text-tertiary)" }}>{r.setup_type}</span>
                                <span className="font-mono" style={{ color: "#FF9F0A" }}>
                                    +{r.staleness_min}m
                                </span>
                            </div>
                        ))}
                    </div>
                    <div className="text-[9px] mt-2" style={{ color: "var(--ts-text-tertiary)" }}>
                        These had a valid setup but took too long to confirm to still be actionable.
                    </div>
                </div>
            )}
        </div>
    );
}
