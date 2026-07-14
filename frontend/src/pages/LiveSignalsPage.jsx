import { useEffect, useState, useCallback, useMemo } from "react";
import TopBar from "@/components/TopBar";
import SignalCard from "@/components/SignalCard";
import WatchlistCard from "@/components/WatchlistCard";
import RejectedSignalsPanel from "@/components/RejectedSignalsPanel";
import CloseTradeDialog from "@/components/CloseTradeDialog";
import AssetClassTabs from "@/components/AssetClassTabs";
import { getTodaySignals, getWatchlist, getMarketStatus } from "@/lib/api";
import { Broadcast } from "@phosphor-icons/react";

export default function LiveSignalsPage() {
    const [assetClass, setAssetClass] = useState("ALL");
    const [signals, setSignals] = useState([]);
    const [watchlist, setWatchlist] = useState([]);
    const [status, setStatus] = useState(null);
    const [loading, setLoading] = useState(true);
    const [dialogOpen, setDialogOpen] = useState(false);
    const [dialogSignal, setDialogSignal] = useState(null);

    // Sort priority: instruments with a live signal today > approaching a
    // setup > everything else. Needed once the watchlist grew past ~20
    // instruments, so the important rows don't get buried by scrolling.
    const sortedWatchlist = useMemo(() => {
        const withSignalToday = new Set(signals.map((s) => s.instrument));
        const rank = (item) => {
            if (withSignalToday.has(item.symbol)) return 0;
            if (item.approaching_setup) return 1;
            return 2;
        };
        return [...watchlist].sort((a, b) => {
            const r = rank(a) - rank(b);
            if (r !== 0) return r;
            return a.symbol.localeCompare(b.symbol);
        });
    }, [watchlist, signals]);

    const load = useCallback(async () => {
        try {
            const [s, w, st] = await Promise.all([
                getTodaySignals(assetClass),
                getWatchlist(assetClass),
                getMarketStatus(),
            ]);
            setSignals(s || []);
            setWatchlist(w || []);
            setStatus(st || null);
        } catch (e) { /* ignore */ }
        setLoading(false);
    }, [assetClass]);

    useEffect(() => {
        load();
        const id = setInterval(load, 60000);
        return () => clearInterval(id);
    }, [load]);

    const openClose = (s) => { setDialogSignal(s); setDialogOpen(true); };

    return (
        <div className="flex-1 flex flex-col">
            <TopBar title="Live Signals" subtitle="Real-time BOS + Order Block setups on 15m/5m timeframes" />
            <div className="px-6 py-3 border-b flex items-center gap-3" style={{ borderColor: "var(--ts-border)" }}>
                <span className="ts-label">Asset Class</span>
                <AssetClassTabs value={assetClass} onChange={setAssetClass} dataTestidPrefix="live-ac" />
            </div>
            <div className="grid grid-cols-12 gap-0 flex-1">
                <div className="col-span-8 border-r p-6 overflow-y-auto" style={{ borderColor: "var(--ts-border)" }}>
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                            <Broadcast size={18} weight="bold" color="#00E5FF" />
                            <h2 className="text-lg font-black tracking-tight">TODAY&apos;S FEED</h2>
                            <span className="ts-badge-neutral" data-testid="signals-count">{signals.length}</span>
                        </div>
                    </div>

                    {loading ? (
                        <div className="text-[color:var(--ts-text-secondary)] text-sm">Loading…</div>
                    ) : signals.length === 0 ? (
                        <EmptyState status={status} />
                    ) : (
                        <div className="grid grid-cols-1 xl:grid-cols-2 gap-4" data-testid="signals-grid">
                            {signals.map((s) => (
                                <SignalCard key={s.id} signal={s} onClose={openClose} />
                            ))}
                        </div>
                    )}
                </div>

                <div className="col-span-4 flex flex-col" style={{ background: "var(--ts-surface)" }}>
                    <RejectedSignalsPanel />
                    <div className="px-4 py-4 border-b flex items-center justify-between"
                         style={{ borderColor: "var(--ts-border)" }}>
                        <h2 className="text-sm font-bold tracking-widest uppercase">Watchlist</h2>
                        <span className="ts-label">{watchlist.length} instruments</span>
                    </div>
                    <div className="flex-1 overflow-y-auto" data-testid="watchlist">
                        {(() => {
                            const withSignalToday = new Set(signals.map((s) => s.instrument));
                            let lastGroup = null;
                            return sortedWatchlist.map((w) => {
                                const group = withSignalToday.has(w.symbol) ? "SIGNAL TODAY"
                                    : w.approaching_setup ? "APPROACHING" : "WATCHING";
                                const showHeader = group !== lastGroup;
                                lastGroup = group;
                                return (
                                    <div key={w.symbol}>
                                        {showHeader && (
                                            <div className="px-4 pt-3 pb-1 text-[9px] uppercase tracking-widest"
                                                 style={{ color: "var(--ts-text-tertiary)" }}>
                                                {group}
                                            </div>
                                        )}
                                        <WatchlistCard item={w} />
                                    </div>
                                );
                            });
                        })()}
                    </div>
                </div>
            </div>

            <CloseTradeDialog
                signal={dialogSignal} open={dialogOpen}
                onOpenChange={setDialogOpen} onSaved={load}
            />
        </div>
    );
}

function EmptyState({ status }) {
    const eq = status?.session_equity || "09:15 - 15:30 IST";
    const fxOverlap = status?.session_forex_overlap_ist || "—";
    const fxLondon = status?.session_forex_secondary_ist || "—";
    return (
        <div className="relative border p-10 text-center" style={{ borderColor: "var(--ts-border)" }}>
            <div
                className="absolute inset-0 opacity-20 grayscale"
                style={{
                    backgroundImage:
                        "url(https://images.unsplash.com/photo-1745509267699-1b1db256601e?crop=entropy&cs=srgb&fm=jpg&ixid=M3w4NjA2MTJ8MHwxfHNlYXJjaHwyfHxhYnN0cmFjdCUyMGZpbmFuY2lhbCUyMGNoYXJ0JTIwZGFya3xlbnwwfHx8fDE3ODMxMDMzMzl8MA&ixlib=rb-4.1.0&q=85)",
                    backgroundSize: "cover", backgroundPosition: "center",
                }}
            />
            <div className="relative">
                <div className="ts-label mb-2">Idle</div>
                <div className="text-lg font-black tracking-tight">Waiting for next setup…</div>
                <div className="mt-2 text-sm text-[color:var(--ts-text-secondary)] max-w-md mx-auto">
                    <div>Equity: {eq}</div>
                    <div>Forex (today, DST-adjusted):</div>
                    <div className="font-mono text-[color:var(--ts-focus)]">
                        {fxLondon} <span className="text-[color:var(--ts-text-tertiary)]">London open</span>
                    </div>
                    <div className="font-mono text-[color:var(--ts-focus)]">
                        {fxOverlap} <span className="text-[color:var(--ts-text-tertiary)]">London/NY overlap</span>
                    </div>
                </div>
            </div>
        </div>
    );
}
