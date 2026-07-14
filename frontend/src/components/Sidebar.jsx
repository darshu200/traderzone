import { NavLink } from "react-router-dom";
import { ChartLine, ListChecks, ChartBar, ClockCounterClockwise, Gear, Broadcast, Wallet } from "@phosphor-icons/react";

const NAV = [
    { to: "/", label: "Live Signals", icon: Broadcast, testid: "nav-live" },
    { to: "/log", label: "Trade Log", icon: ListChecks, testid: "nav-log" },
    { to: "/analytics", label: "Analytics", icon: ChartBar, testid: "nav-analytics" },
    { to: "/capital", label: "Capital & P&L", icon: Wallet, testid: "nav-capital" },
    { to: "/backtest", label: "Backtest", icon: ClockCounterClockwise, testid: "nav-backtest" },
    { to: "/settings", label: "Settings", icon: Gear, testid: "nav-settings" },
];

export default function Sidebar() {
    return (
        <aside
            data-testid="sidebar"
            className="w-56 shrink-0 h-screen sticky top-0 border-r flex flex-col"
            style={{ borderColor: "var(--ts-border)", background: "var(--ts-surface)" }}
        >
            <div className="px-4 py-5 border-b" style={{ borderColor: "var(--ts-border)" }}>
                <div className="flex items-center gap-2">
                    <ChartLine size={22} weight="bold" color="#00E5FF" />
                    <div>
                        <div className="font-black text-base tracking-tight" style={{ fontFamily: "Chivo" }}>
                            TRADESIGNAL
                        </div>
                        <div className="ts-label mt-0.5">NSE • Paper Trading</div>
                    </div>
                </div>
            </div>
            <nav className="flex-1 py-3">
                {NAV.map(({ to, label, icon: Icon, testid }) => (
                    <NavLink
                        key={to}
                        to={to}
                        end={to === "/"}
                        data-testid={testid}
                        className={({ isActive }) => `ts-nav-link ${isActive ? "active" : ""}`}
                    >
                        <Icon size={16} weight="bold" />
                        <span>{label}</span>
                    </NavLink>
                ))}
            </nav>
            <div className="px-4 py-3 text-[10px] text-[color:var(--ts-text-tertiary)] border-t" style={{ borderColor: "var(--ts-border)" }}>
                For personal research only. Not trading advice.
            </div>
        </aside>
    );
}
