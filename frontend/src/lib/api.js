import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API = `${BACKEND_URL}/api`;

export const api = axios.create({ baseURL: API, timeout: 60000 });

// Endpoints ------------------------------------------------------------
export const getMarketStatus  = () => api.get("/market/status").then(r => r.data);
export const getInstruments   = () => api.get("/instruments").then(r => r.data);
export const getWatchlist     = (asset_class) => api.get("/watchlist", { params: asset_class && asset_class !== "ALL" ? { asset_class } : {} }).then(r => r.data);
export const getSignals       = (params = {}) => api.get("/signals", { params }).then(r => r.data);
export const getTodaySignals  = (asset_class) => api.get("/signals/today", { params: asset_class && asset_class !== "ALL" ? { asset_class } : {} }).then(r => r.data);
export const updateSignal     = (id, body) => api.patch(`/signals/${id}`, body).then(r => r.data);
export const deleteSignal     = (id) => api.delete(`/signals/${id}`).then(r => r.data);
export const getAnalytics     = (asset_class) => api.get("/analytics", { params: asset_class && asset_class !== "ALL" ? { asset_class } : {} }).then(r => r.data);
export const getRejectedSignals = (asset_class) =>
    api.get("/signals/rejected", { params: asset_class && asset_class !== "ALL" ? { asset_class } : {} })
       .then(r => r.data)
       .catch(() => null);
export const getSettings      = () => api.get("/settings").then(r => r.data);
export const updateSettings   = (body) => api.put("/settings", body).then(r => r.data);
export const runBacktest      = (body) => api.post("/backtest", body).then(r => r.data);
export const runManualScan    = () => api.post("/dev/run-scan").then(r => r.data);
export const backtestCsvUrl   = (instrument, start_date, end_date) =>
    `${API}/backtest/csv?instrument=${instrument}&start_date=${start_date}&end_date=${end_date}`;

export const EQUITY_LIST = [
    "NIFTY","BANKNIFTY","RELIANCE","HDFCBANK","ICICIBANK","SBIN",
    "TMPV","TATASTEEL","BHARTIARTL","LT","AXISBANK","KOTAKBANK",
    // Expanded universe (added after large-universe backtest validation)
    "BANKBARODA","PNB","FEDERALBNK","INDUSINDBK",
    "TCS","INFY","HCLTECH","WIPRO","TECHM","LTM",
    "SUNPHARMA","DIVISLAB","CIPLA","DRREDDY","LUPIN",
    "HINDUNILVR","ITC","NESTLEIND","BRITANNIA","TATACONSUM",
    "MARUTI","BAJAJ-AUTO","EICHERMOT","HEROMOTOCO","ASHOKLEY",
    "JSWSTEEL","HINDALCO","VEDL","ADANIENT","NATIONALUM",
    "NTPC","POWERGRID","ONGC","COALINDIA","BPCL",
    "ULTRACEMCO","SHREECEM","AMBUJACEM","ACC",
    "INDUSTOWER",
    "BAJFINANCE","BAJAJFINSV","HDFCLIFE","SBILIFE","SHRIRAMFIN",
    "ADANIPORTS","SIEMENS","ABB","BEL","BHEL",
    "TITAN","ASIANPAINT","DMART",
    "DLF","GODREJPROP",
];
export const FOREX_LIST = [
    "EURUSD","GBPUSD","USDJPY","GBPJPY","AUDUSD","USDCAD","XAUUSD",
];
export const INSTRUMENTS_LIST = [...EQUITY_LIST, ...FOREX_LIST];

// Static precision map (mirrors backend constants for client-side formatting)
export const INSTRUMENT_META = {
    NIFTY:      { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BANKNIFTY:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    RELIANCE:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    HDFCBANK:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ICICIBANK:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    SBIN:       { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    TMPV:       { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    TATASTEEL:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BHARTIARTL: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    LT:         { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    AXISBANK:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    KOTAKBANK:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BANKBARODA: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    PNB:        { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    FEDERALBNK: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    INDUSINDBK: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    TCS:        { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    INFY:       { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    HCLTECH:    { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    WIPRO:      { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    TECHM:      { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    LTM:        { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    SUNPHARMA:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    DIVISLAB:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    CIPLA:      { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    DRREDDY:    { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    LUPIN:      { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    HINDUNILVR: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ITC:        { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    NESTLEIND:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BRITANNIA:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    TATACONSUM: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    MARUTI:     { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    "BAJAJ-AUTO": { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    EICHERMOT:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    HEROMOTOCO: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ASHOKLEY:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    JSWSTEEL:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    HINDALCO:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    VEDL:       { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ADANIENT:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    NATIONALUM: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    NTPC:       { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    POWERGRID:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ONGC:       { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    COALINDIA:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BPCL:       { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ULTRACEMCO: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    SHREECEM:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    AMBUJACEM:  { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ACC:        { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    INDUSTOWER: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BAJFINANCE: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BAJAJFINSV: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    HDFCLIFE:   { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    SBILIFE:    { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    SHRIRAMFIN: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ADANIPORTS: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    SIEMENS:    { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ABB:        { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BEL:        { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    BHEL:       { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    TITAN:      { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    ASIANPAINT: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    DMART:      { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    DLF:        { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    GODREJPROP: { pip: 2, prefix: "₹", asset_class: "EQUITY" },
    EURUSD:     { pip: 4, prefix: "",  asset_class: "FOREX" },
    GBPUSD:     { pip: 4, prefix: "",  asset_class: "FOREX" },
    USDJPY:     { pip: 2, prefix: "",  asset_class: "FOREX" },
    GBPJPY:     { pip: 2, prefix: "",  asset_class: "FOREX" },
    AUDUSD:     { pip: 4, prefix: "",  asset_class: "FOREX" },
    USDCAD:     { pip: 4, prefix: "",  asset_class: "FOREX" },
    XAUUSD:     { pip: 2, prefix: "$", asset_class: "FOREX" },
};

// ---- Capital & real-money P&L (separate feature, own endpoints) ----
export const getCapitalSettings   = () => api.get("/capital/settings").then(r => r.data);
export const updateCapitalSettings = (body) => api.put("/capital/settings", body).then(r => r.data);
export const getQuantitySuggestion = (signal_id) =>
    api.get("/capital/quantity-suggestion", { params: { signal_id } }).then(r => r.data);
export const takeTrade  = (body) => api.post("/capital/trades", body).then(r => r.data);
export const closeTrade = (trade_id, body) => api.patch(`/capital/trades/${trade_id}`, body).then(r => r.data);
export const listCapitalTrades = (params = {}) => api.get("/capital/trades", { params }).then(r => r.data);
export const getDailyPnl    = () => api.get("/capital/daily-pnl").then(r => r.data);
export const getEquityCurve = () => api.get("/capital/equity-curve").then(r => r.data);
