const TABS = [
    { key: "ALL", label: "All" },
    { key: "EQUITY", label: "Equity" },
    { key: "FOREX", label: "Forex" },
];

export default function AssetClassTabs({ value, onChange, showAll = true, dataTestidPrefix = "ac" }) {
    const tabs = showAll ? TABS : TABS.filter(t => t.key !== "ALL");
    return (
        <div
            className="inline-flex border rounded-sm overflow-hidden"
            style={{ borderColor: "var(--ts-border)" }}
            data-testid={`${dataTestidPrefix}-tabs`}
        >
            {tabs.map(t => {
                const active = value === t.key;
                return (
                    <button
                        key={t.key}
                        data-testid={`${dataTestidPrefix}-tab-${t.key.toLowerCase()}`}
                        onClick={() => onChange(t.key)}
                        className="px-3 py-1.5 text-[11px] font-mono uppercase tracking-widest transition-colors"
                        style={{
                            background: active ? "var(--ts-focus)" : "transparent",
                            color: active ? "#000" : "var(--ts-text-secondary)",
                            borderRight: "1px solid var(--ts-border)",
                        }}
                    >
                        {t.label}
                    </button>
                );
            })}
        </div>
    );
}
