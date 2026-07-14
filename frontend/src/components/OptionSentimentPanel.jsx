import { useEffect, useState } from "react";
import { getOptionSentiment } from "@/lib/api";
import { fmtNum } from "@/lib/format";
import { ChartPieSlice } from "@phosphor-icons/react";

const SYMBOLS = ["NIFTY", "BANKNIFTY"];

const biasColor = (bias) => {
    if (bias === "BULLISH") return "var(--ts-long)";
    if (bias === "BEARISH") return "var(--ts-short)";
    return "var(--ts-text-secondary)";
};

function Row({ symbol }) {
    const [data, setData] = useState(null);
    const [status, setStatus] = useState("loading"); // loading | ok | unavailable

    useEffect(() => {
        let cancelled = false;
        const load = async () => {
            const res = await getOptionSentiment(symbol);
            if (cancelled) return;
            if (res) { setData(res); setStatus("ok"); }
            else { setStatus("unavailable"); }
        };
        load();
        const id = setInterval(load, 60000);
        return () => { cancelled = true; clearInterval(id); };
    }, [symbol]);

    if (status === "loading") {
        return (
            <div className="px-4 py-3 text-xs text-[color:var(--ts-text-tertiary)]">
                {symbol} — loading…
            </div>
        );
    }
    if (status === "unavailable") {
        return (
            <div className="px-4 py-3 border-b" style={{ borderColor: "var(--ts-border)" }}>
                <div className="flex items-center justify-between">
                    <span className="font-bold text-sm">{symbol}</span>
                    <span className="text-[10px] uppercase tracking-widest text-[color:var(--ts-text-tertiary)]">
                        unavailable
                    </span>
                </div>
                <div className="text-[10px] text-[color:var(--ts-text-tertiary)] mt-1">
                    Market closed or NSE rate-limited
                </div>
            </div>
        );
    }

    return (
        <div className="px-4 py-3 border-b" style={{ borderColor: "var(--ts-border)" }}>
            <div className="flex items-center justify-between mb-1.5">
                <span className="font-bold text-sm">{symbol}</span>
                <span
                    className="text-[9px] px-1.5 py-0.5 uppercase tracking-widest font-mono"
                    style={{ color: biasColor(data.oi_bias), border: `1px solid ${biasColor(data.oi_bias)}` }}
                    data-testid={`oi-bias-${symbol}`}
                >
                    {data.oi_bias}
                </span>
            </div>
            <div className="grid grid-cols-3 gap-2 text-center">
                <div>
                    <div className="text-[9px] uppercase tracking-widest text-[color:var(--ts-text-tertiary)]">PCR</div>
                    <div className="font-mono text-sm font-semibold">{fmtNum(data.pcr, 2)}</div>
                </div>
                <div>
                    <div className="text-[9px] uppercase tracking-widest text-[color:var(--ts-text-tertiary)]">Max Pain</div>
                    <div className="font-mono text-sm font-semibold">{fmtNum(data.max_pain, 0)}</div>
                </div>
                <div>
                    <div className="text-[9px] uppercase tracking-widest text-[color:var(--ts-text-tertiary)]">Spot</div>
                    <div className="font-mono text-sm font-semibold">{fmtNum(data.underlying, 0)}</div>
                </div>
            </div>
        </div>
    );
}

export default function OptionSentimentPanel() {
    return (
        <div>
            <div className="px-4 py-3 border-b flex items-center gap-2" style={{ borderColor: "var(--ts-border)" }}>
                <ChartPieSlice size={16} weight="bold" color="#00E5FF" />
                <h2 className="text-sm font-bold tracking-widest uppercase">Options Sentiment</h2>
            </div>
            {SYMBOLS.map((s) => <Row key={s} symbol={s} />)}
            <div className="px-4 py-2 text-[9px] text-[color:var(--ts-text-tertiary)] leading-relaxed">
                Live snapshot only, informational context — not a trade filter.
                PCR/Max Pain reflect current option positioning, not a
                backtested signal.
            </div>
        </div>
    );
}
