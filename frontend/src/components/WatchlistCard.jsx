import { useState } from "react";
import { fmtNum } from "@/lib/format";
import { TrendUp, TrendDown, Minus } from "@phosphor-icons/react";
import SetupChart from "@/components/SetupChart";

export default function WatchlistCard({ item }) {
    const [expanded, setExpanded] = useState(false);
    const up = (item.pct ?? 0) > 0;
    const down = (item.pct ?? 0) < 0;
    const Trend = up ? TrendUp : down ? TrendDown : Minus;
    const color = up ? "var(--ts-long)" : down ? "var(--ts-short)" : "var(--ts-text-secondary)";
    const decimals = item.pip_decimals ?? 2;
    const prefix = item.price_prefix ?? "";
    const clickable = !!item.approaching_setup;
    return (
        <div className="border-b" style={{ borderColor: "var(--ts-border)" }}>
            <div
                data-testid={`watchlist-item-${item.symbol}`}
                className={`flex items-center justify-between px-4 py-3 ts-hover ${clickable ? "cursor-pointer" : ""}`}
                onClick={() => clickable && setExpanded(v => !v)}
            >
                <div className="flex flex-col">
                    <div className="flex items-center gap-2">
                        <span className="font-bold text-sm">{item.symbol}</span>
                        {item.asset_class === "FOREX" && (
                            <span className="text-[9px] px-1.5 py-0.5 uppercase tracking-widest font-mono"
                                  style={{ color: "var(--ts-text-tertiary)", border: "1px solid var(--ts-border)" }}>
                                FX
                            </span>
                        )}
                        {item.approaching_setup && (
                            <span className="text-[9px] px-1.5 py-0.5 uppercase tracking-widest font-mono"
                                  style={{ color: "var(--ts-focus)", border: "1px solid var(--ts-border)" }}
                                  data-testid={`approaching-${item.symbol}`}>
                                approaching{expanded ? " ▾" : " ▸"}
                            </span>
                        )}
                    </div>
                    <span className="text-[10px] text-[color:var(--ts-text-tertiary)] uppercase tracking-widest">
                        {item.name}
                    </span>
                </div>
                <div className="text-right">
                    <div className="font-mono text-sm font-semibold">{prefix}{fmtNum(item.ltp, decimals)}</div>
                    <div className="flex items-center justify-end gap-1 text-xs font-mono" style={{ color }}>
                        <Trend size={12} weight="bold" />
                        <span>{fmtNum(item.pct, 2)}%</span>
                    </div>
                </div>
            </div>
            {expanded && (
                <div className="px-4 pb-3">
                    <SetupChart symbol={item.symbol} />
                </div>
            )}
        </div>
    );
}
