import { useEffect, useRef, useState } from "react";
import { createChart, ColorType, LineStyle } from "lightweight-charts";
import { getChart } from "@/lib/api";

/**
 * Shows the recent candle window for one instrument, with the swing level
 * it's approaching OR (for an open trade) the exact entry/stoploss/target
 * lines and the trigger candle marked — same idea as a broker's setup view.
 *
 * Only renders for symbols the backend has actually cached a chart for
 * (approaching a setup, or currently OPEN) — everything else gets nothing
 * to show, by design, so this never implies "here's a chart" for a symbol
 * with no active setup.
 */
export default function SetupChart({ symbol }) {
    const containerRef = useRef(null);
    const chartRef = useRef(null);
    const seriesRef = useRef(null);
    const [data, setData] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        let cancelled = false;
        setLoading(true);
        getChart(symbol).then((res) => {
            if (!cancelled) {
                setData(res);
                setLoading(false);
            }
        });
        return () => { cancelled = true; };
    }, [symbol]);

    useEffect(() => {
        if (!data || !containerRef.current) return;

        const chart = createChart(containerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: "transparent" },
                textColor: "#A1A1AA",
                fontSize: 11,
            },
            grid: {
                vertLines: { color: "#27272A" },
                horzLines: { color: "#27272A" },
            },
            width: containerRef.current.clientWidth,
            height: 280,
            timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#27272A" },
            rightPriceScale: { borderColor: "#27272A" },
            crosshair: { mode: 0 },
        });
        chartRef.current = chart;

        const series = chart.addCandlestickSeries({
            upColor: "#00E676", downColor: "#FF3B30",
            borderUpColor: "#00E676", borderDownColor: "#FF3B30",
            wickUpColor: "#00E676", wickDownColor: "#FF3B30",
        });
        seriesRef.current = series;
        series.setData(data.candles);

        const isLong = data.direction === "LONG";

        if (data.entry != null) {
            series.createPriceLine({
                price: data.entry, color: "#3B82F6", lineWidth: 2,
                lineStyle: LineStyle.Solid, title: "Entry",
            });
        }
        if (data.stoploss != null) {
            series.createPriceLine({
                price: data.stoploss, color: "#FF3B30", lineWidth: 2,
                lineStyle: LineStyle.Dashed, title: "Stoploss",
            });
        }
        if (data.target != null) {
            series.createPriceLine({
                price: data.target, color: "#00E676", lineWidth: 2,
                lineStyle: LineStyle.Dashed, title: "Target",
            });
        }
        if (data.swing) {
            series.createPriceLine({
                price: data.swing.price, color: "#F59E0B", lineWidth: 1,
                lineStyle: LineStyle.Dotted,
                title: data.swing.type === "high" ? "Swing high" : "Swing low",
            });
        }

        // Mark the exact candle that triggered/started the setup — the
        // BOS/sweep candle, or for an open trade, structural_start_ts.
        const triggerTime = data.trigger_time || (data.swing && data.swing.time);
        if (triggerTime) {
            series.setMarkers([{
                time: triggerTime,
                position: isLong ? "belowBar" : "aboveBar",
                color: isLong ? "#00E676" : "#FF3B30",
                shape: isLong ? "arrowUp" : "arrowDown",
                text: data.status === "open" ? "Trigger" : "Swing",
            }]);
        }

        chart.timeScale().fitContent();

        const handleResize = () => {
            if (containerRef.current) {
                chart.applyOptions({ width: containerRef.current.clientWidth });
            }
        };
        window.addEventListener("resize", handleResize);
        return () => {
            window.removeEventListener("resize", handleResize);
            chart.remove();
        };
    }, [data]);

    if (loading) {
        return (
            <div className="ts-surface p-4 flex items-center justify-center" style={{ height: 280 }}>
                <span className="text-[11px] uppercase tracking-widest text-[color:var(--ts-text-tertiary)]">
                    Loading chart…
                </span>
            </div>
        );
    }

    if (!data) {
        // Not approaching, not open — nothing to show, and that's correct.
        return null;
    }

    return (
        <div className="ts-surface p-3 flex flex-col gap-2">
            <div className="flex items-center justify-between px-1">
                <span className="font-bold text-sm tracking-tight">{symbol}</span>
                <span className="ts-badge-neutral text-[10px]">
                    {data.status === "open" ? "OPEN TRADE" : "APPROACHING"}
                </span>
            </div>
            <div ref={containerRef} style={{ width: "100%", height: 280 }} />
        </div>
    );
}
