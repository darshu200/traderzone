import { useEffect, useMemo, useState } from "react";
import TopBar from "@/components/TopBar";
import { getInstruments, getSettings, updateSettings } from "@/lib/api";
import { Switch } from "@/components/ui/switch";
import { toast } from "sonner";

export default function SettingsPage() {
    const [instruments, setInstruments] = useState([]);
    const [active, setActive] = useState(new Set());
    const [saving, setSaving] = useState(false);

    useEffect(() => {
        Promise.all([getInstruments(), getSettings()]).then(([inst, s]) => {
            setInstruments(inst);
            setActive(new Set(s.active_instruments));
        });
    }, []);

    const grouped = useMemo(() => {
        const g = { EQUITY: [], FOREX: [] };
        for (const i of instruments) {
            (g[i.asset_class] || (g[i.asset_class] = [])).push(i);
        }
        return g;
    }, [instruments]);

    const toggle = (sym) => {
        const next = new Set(active);
        if (next.has(sym)) next.delete(sym); else next.add(sym);
        setActive(next);
    };

    const toggleClass = (cls, enable) => {
        const next = new Set(active);
        for (const i of grouped[cls] || []) {
            if (enable) next.add(i.symbol); else next.delete(i.symbol);
        }
        setActive(next);
    };

    const save = async () => {
        setSaving(true);
        try {
            await updateSettings({ active_instruments: Array.from(active) });
            toast.success("Settings saved");
        } catch { toast.error("Save failed"); }
        finally { setSaving(false); }
    };

    const renderGroup = (cls, label) => {
        const items = grouped[cls] || [];
        if (!items.length) return null;
        const activeInGroup = items.filter(i => active.has(i.symbol)).length;
        return (
            <div className="mb-6 ts-surface">
                <div className="px-4 py-3 border-b flex items-center justify-between"
                     style={{ borderColor: "var(--ts-border)" }}>
                    <div className="flex items-center gap-3">
                        <div className="ts-label">{label}</div>
                        <span className="text-xs text-[color:var(--ts-text-secondary)] font-mono">
                            {activeInGroup} / {items.length} active
                        </span>
                    </div>
                    <div className="flex gap-2">
                        <button className="ts-btn-ghost !text-[10px] !px-2 !py-1"
                                onClick={() => toggleClass(cls, true)}
                                data-testid={`enable-all-${cls.toLowerCase()}`}>
                            Enable all
                        </button>
                        <button className="ts-btn-ghost !text-[10px] !px-2 !py-1"
                                onClick={() => toggleClass(cls, false)}
                                data-testid={`disable-all-${cls.toLowerCase()}`}>
                            Disable all
                        </button>
                    </div>
                </div>
                {items.map((i) => (
                    <div key={i.symbol}
                        className="flex items-center justify-between px-4 py-3 ts-hover border-b"
                        style={{ borderColor: "var(--ts-border)" }}>
                        <div>
                            <div className="font-semibold">{i.symbol}
                                <span className="ml-2 ts-badge-neutral">{i.type}</span>
                            </div>
                            <div className="text-xs text-[color:var(--ts-text-tertiary)]">{i.name}</div>
                        </div>
                        <Switch
                            data-testid={`toggle-${i.symbol}`}
                            checked={active.has(i.symbol)}
                            onCheckedChange={() => toggle(i.symbol)}
                        />
                    </div>
                ))}
            </div>
        );
    };

    return (
        <div className="flex-1 flex flex-col">
            <TopBar title="Settings" subtitle="Toggle which instruments are actively scanned" />

            <div className="p-6">
                <div className="flex items-center justify-between mb-4">
                    <div className="ts-label" data-testid="active-count">
                        {active.size} active / {instruments.length} total
                    </div>
                    <button data-testid="save-settings-btn" className="ts-btn-primary"
                        onClick={save} disabled={saving}>
                        {saving ? "Saving…" : "Save Changes"}
                    </button>
                </div>

                {renderGroup("EQUITY", "Equity / Index (NSE)")}
                {renderGroup("FOREX",  "Forex / Commodities")}

                <div className="mt-2 ts-surface p-4">
                    <div className="ts-label mb-2">Strategy Parameters (read-only)</div>
                    <ul className="text-sm text-[color:var(--ts-text-secondary)] space-y-1 font-mono">
                        <li>• BOS on 15m close beyond recent swing. Equity: vol ≥ 1.5× SMA20. Forex: candle range ≥ 1.2× ATR(14).</li>
                        <li>• Order block = last opposite-colored candle before impulse</li>
                        <li>• 5m rejection retest inside OB, price on right side of VWAP (TWAP for forex)</li>
                        <li>• Equity windows: 09:30–11:15 &amp; 13:30–14:45 IST</li>
                        <li>• Forex windows: London 08:00–17:00 Europe/London &amp; New York 08:00–17:00 America/New_York (DST-safe; IST equivalents shift ±1h across DST transitions)</li>
                        <li>• Stop: OB extreme ± 0.10–0.15 × ATR(14); minimum 1:3 RR required</li>
                        <li>• Forex: no entries in last 30 min before Friday 17:00 America/New_York close; open positions &gt; 24h are flagged for review</li>
                    </ul>
                </div>
            </div>
        </div>
    );
}
