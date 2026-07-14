export const fmtNum = (n, d = 2) => {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
    return Number(n).toLocaleString("en-IN", {
        minimumFractionDigits: d, maximumFractionDigits: d,
    });
};
// Symbol-aware price formatter (uses instrument meta for prefix + precision)
export const fmtPrice = (n, symbol, metaMap) => {
    if (n === null || n === undefined || Number.isNaN(Number(n))) return "—";
    const meta = (metaMap || {})[symbol] || { pip: 2, prefix: "" };
    return `${meta.prefix || ""}${fmtNum(n, meta.pip)}`;
};
export const fmtPct = (n, d = 2) => {
    if (n === null || n === undefined) return "—";
    const v = Number(n);
    const sign = v > 0 ? "+" : "";
    return `${sign}${v.toFixed(d)}%`;
};
export const fmtTimeIST = (iso) => {
    if (!iso) return "—";
    try {
        const d = new Date(iso);
        return d.toLocaleString("en-IN", {
            timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit",
            hour12: false, day: "2-digit", month: "short",
        });
    } catch { return iso; }
};
export const fmtDateISOToday = () => {
    const d = new Date();
    return d.toISOString().split("T")[0];
};
export const daysAgoISO = (n) => {
    const d = new Date(); d.setDate(d.getDate() - n);
    return d.toISOString().split("T")[0];
};
