import { fmtNum, fmtTimeIST } from "@/lib/format";
import { INSTRUMENT_META } from "@/lib/api";
import { Target, ShieldCheck, ArrowUpRight, ArrowDownRight, Warning } from "@phosphor-icons/react";

export default function SignalCard({ signal, onClose }) {
    const isLong = signal.direction === "LONG";
    const badgeClass = isLong ? "ts-badge-long" : "ts-badge-short";
    const Arrow = isLong ? ArrowUpRight : ArrowDownRight;
    const color = isLong ? "var(--ts-long)" : "var(--ts-short)";
    const meta = INSTRUMENT_META[signal.instrument] || { pip: 2, prefix: "₹" };
    const pfx = meta.prefix;
    const dp = meta.pip;

    return (
        <div
            data-testid={`signal-card-${signal.direction.toLowerCase()}`}
            className="ts-surface ts-fadein p-4 flex flex-col gap-3 hover:border-[color:var(--ts-text-secondary)] transition-colors"
        >
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                    <Arrow size={18} weight="bold" color={color} />
                    <span className="font-bold text-base tracking-tight">{signal.instrument}</span>
                    <span className={badgeClass}>{signal.direction}</span>
                    {signal.asset_class === "FOREX" && (
                        <span className="ts-badge-neutral" style={{ color: "var(--ts-focus)" }}>FX</span>
                    )}
                </div>
                <span className="ts-badge-neutral">{signal.call_type}</span>
            </div>

            <div className="flex items-center justify-between text-[10px] uppercase tracking-widest text-[color:var(--ts-text-secondary)] border-b pb-2"
                 style={{ borderColor: "var(--ts-border)" }}>
                <span>{signal.setup_type}</span>
                <span className="font-mono flex items-center gap-1.5">
                    {fmtTimeIST(signal.timestamp)}
                    {typeof signal.detected_delay_min === "number" && signal.detected_delay_min >= 2 && (
                        <span title="Time between this signal's entry candle and when it was actually detected/posted"
                              style={{ color: "var(--ts-text-tertiary)" }}>
                            (+{Math.round(signal.detected_delay_min)}m delay)
                        </span>
                    )}
                </span>
            </div>

            <div className="grid grid-cols-3 gap-2">
                <div>
                    <div className="ts-label">Entry</div>
                    <div className="font-mono text-base font-semibold">{pfx}{fmtNum(signal.entry, dp)}</div>
                </div>
                <div>
                    <div className="ts-label flex items-center gap-1"><ShieldCheck size={10}/> Stop</div>
                    <div className="font-mono text-base" style={{ color: "var(--ts-short)" }}>
                        {pfx}{fmtNum(signal.stoploss, dp)}
                    </div>
                </div>
                <div>
                    <div className="ts-label flex items-center gap-1"><Target size={10}/> Target</div>
                    <div className="font-mono text-base" style={{ color: "var(--ts-long)" }}>
                        {pfx}{fmtNum(signal.target, dp)}
                    </div>
                </div>
            </div>

            <div className="flex items-center justify-between border-t pt-3" style={{ borderColor: "var(--ts-border)" }}>
                <div>
                    <div className="ts-label">R : R</div>
                    <div className="font-mono text-sm font-semibold" style={{ color: "var(--ts-focus)" }}>
                        1 : {fmtNum(signal.rr, 2)}
                    </div>
                </div>
                <div className="flex gap-2 items-center">
                    {signal.stale && (
                        <span className="ts-badge-neutral flex items-center gap-1"
                              style={{ color: "var(--ts-short)", borderColor: "var(--ts-short-border)" }}
                              data-testid={`stale-${signal.id}`}>
                            <Warning size={10} weight="bold" /> REVIEW ({signal.age_hours}h)
                        </span>
                    )}
                    <span className={`ts-badge-neutral`} data-testid={`signal-outcome-${signal.id}`}>
                        {signal.outcome || "OPEN"}
                    </span>
                    {onClose && signal.outcome === "OPEN" && (
                        <button
                            data-testid={`close-trade-${signal.id}`}
                            onClick={() => onClose(signal)}
                            className="ts-btn-ghost !py-1 !px-2 !text-[10px]"
                        >
                            Close
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
}
