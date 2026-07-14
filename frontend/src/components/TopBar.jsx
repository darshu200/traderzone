import { useEffect, useState } from "react";
import { getMarketStatus, runManualScan } from "@/lib/api";
import { fmtTimeIST } from "@/lib/format";
import { ArrowClockwise } from "@phosphor-icons/react";
import { toast } from "sonner";

export default function TopBar({ title, subtitle }) {
    const [status, setStatus] = useState(null);
    const [scanning, setScanning] = useState(false);

    const load = async () => {
        try { setStatus(await getMarketStatus()); } catch { /* ignore */ }
    };
    useEffect(() => {
        load();
        const id = setInterval(load, 30000);
        return () => clearInterval(id);
    }, []);

    const handleScan = async () => {
        setScanning(true);
        try {
            const r = await runManualScan();
            toast.success(`Scan complete. ${r?.report?.last_generated ?? 0} new signal(s).`);
        } catch (e) {
            toast.error("Scan failed");
        } finally { setScanning(false); load(); }
    };

    const eq = !!status?.equity_open;
    const fx = !!status?.forex_open;

    return (
        <div
            data-testid="topbar"
            className="flex items-center justify-between px-6 py-4 border-b"
            style={{ borderColor: "var(--ts-border)", background: "var(--ts-bg)" }}
        >
            <div>
                <h1 className="text-2xl font-black tracking-tight" data-testid="page-title">{title}</h1>
                {subtitle && <div className="text-sm text-[color:var(--ts-text-secondary)] mt-1">{subtitle}</div>}
            </div>
            <div className="flex items-center gap-3">
                <div className="ts-pill" data-testid="market-status-equity">
                    <span className={`ts-live-dot ${eq ? "" : "off"}`} />
                    <span className="font-mono text-[10px] tracking-widest">EQ {eq ? "OPEN" : "CLOSED"}</span>
                </div>
                <div className="ts-pill" data-testid="market-status-forex">
                    <span className={`ts-live-dot ${fx ? "" : "off"}`} />
                    <span className="font-mono text-[10px] tracking-widest">FX {fx ? "OPEN" : "CLOSED"}</span>
                </div>
                <div className="ts-pill" data-testid="market-status-time">
                    <span className="font-mono text-[10px]">{status ? fmtTimeIST(status.server_time_ist) : "…"}</span>
                </div>
                <button
                    data-testid="topbar-scan-btn"
                    onClick={handleScan}
                    disabled={scanning}
                    className="ts-btn-ghost"
                    title="Run signal scan now"
                >
                    <ArrowClockwise size={14} weight="bold" className={scanning ? "animate-spin" : ""} />
                    {scanning ? "Scanning…" : "Run Scan"}
                </button>
            </div>
        </div>
    );
}
