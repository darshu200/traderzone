"""Constants shared across TradeSignal backend."""
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")
LONDON_TZ = ZoneInfo("Europe/London")
NY_TZ = ZoneInfo("America/New_York")

# ---------------------------------------------------------------------------
# EQUITY / INDEX INSTRUMENTS (NSE)
# ---------------------------------------------------------------------------
EQUITY_INSTRUMENTS = {
    "NIFTY":       {"yf": "^NSEI",         "name": "NIFTY 50",        "type": "index",
                    "asset_class": "EQUITY", "nse": "NIFTY 50",     "pip_decimals": 2,
                    "price_prefix": "₹"},
    "BANKNIFTY":   {"yf": "^NSEBANK",      "name": "BANK NIFTY",      "type": "index",
                    "asset_class": "EQUITY", "nse": "NIFTY BANK",   "pip_decimals": 2,
                    "price_prefix": "₹"},
    "RELIANCE":    {"yf": "RELIANCE.NS",   "name": "Reliance",        "type": "stock",
                    "asset_class": "EQUITY", "nse": "RELIANCE",     "pip_decimals": 2, "price_prefix": "₹"},
    "HDFCBANK":    {"yf": "HDFCBANK.NS",   "name": "HDFC Bank",       "type": "stock",
                    "asset_class": "EQUITY", "nse": "HDFCBANK",     "pip_decimals": 2, "price_prefix": "₹"},
    "ICICIBANK":   {"yf": "ICICIBANK.NS",  "name": "ICICI Bank",      "type": "stock",
                    "asset_class": "EQUITY", "nse": "ICICIBANK",    "pip_decimals": 2, "price_prefix": "₹"},
    "SBIN":        {"yf": "SBIN.NS",       "name": "State Bank",      "type": "stock",
                    "asset_class": "EQUITY", "nse": "SBIN",         "pip_decimals": 2, "price_prefix": "₹"},
    "TMPV":        {"yf": "TMPV.NS",       "name": "Tata Motors Passenger Vehicles", "type": "stock",
                    "asset_class": "EQUITY", "nse": "TMPV",         "pip_decimals": 2, "price_prefix": "₹"},
    "TATASTEEL":   {"yf": "TATASTEEL.NS",  "name": "Tata Steel",      "type": "stock",
                    "asset_class": "EQUITY", "nse": "TATASTEEL",    "pip_decimals": 2, "price_prefix": "₹"},
    "BHARTIARTL":  {"yf": "BHARTIARTL.NS", "name": "Bharti Airtel",   "type": "stock",
                    "asset_class": "EQUITY", "nse": "BHARTIARTL",   "pip_decimals": 2, "price_prefix": "₹"},
    "LT":          {"yf": "LT.NS",         "name": "Larsen & Toubro", "type": "stock",
                    "asset_class": "EQUITY", "nse": "LT",           "pip_decimals": 2, "price_prefix": "₹"},
    "AXISBANK":    {"yf": "AXISBANK.NS",   "name": "Axis Bank",       "type": "stock",
                    "asset_class": "EQUITY", "nse": "AXISBANK",     "pip_decimals": 2, "price_prefix": "₹"},
    "KOTAKBANK":   {"yf": "KOTAKBANK.NS",  "name": "Kotak Bank",      "type": "stock",
                    "asset_class": "EQUITY", "nse": "KOTAKBANK",    "pip_decimals": 2, "price_prefix": "₹"},

    # --- Expanded universe: liquid Nifty 500 sector leaders (added after
    # large-universe backtest validation showed a real, consistent edge) ---
    # Banking (additional)
    "BANKBARODA":  {"yf": "BANKBARODA.NS", "name": "Bank of Baroda",   "type": "stock",
                    "asset_class": "EQUITY", "nse": "BANKBARODA",  "pip_decimals": 2, "price_prefix": "₹"},
    "PNB":         {"yf": "PNB.NS",        "name": "Punjab National Bank", "type": "stock",
                    "asset_class": "EQUITY", "nse": "PNB",         "pip_decimals": 2, "price_prefix": "₹"},
    "FEDERALBNK":  {"yf": "FEDERALBNK.NS", "name": "Federal Bank",     "type": "stock",
                    "asset_class": "EQUITY", "nse": "FEDERALBNK",  "pip_decimals": 2, "price_prefix": "₹"},
    "INDUSINDBK":  {"yf": "INDUSINDBK.NS", "name": "IndusInd Bank",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "INDUSINDBK",  "pip_decimals": 2, "price_prefix": "₹"},
    # IT
    "TCS":         {"yf": "TCS.NS",        "name": "TCS",              "type": "stock",
                    "asset_class": "EQUITY", "nse": "TCS",         "pip_decimals": 2, "price_prefix": "₹"},
    "INFY":        {"yf": "INFY.NS",       "name": "Infosys",          "type": "stock",
                    "asset_class": "EQUITY", "nse": "INFY",        "pip_decimals": 2, "price_prefix": "₹"},
    "HCLTECH":     {"yf": "HCLTECH.NS",    "name": "HCL Technologies", "type": "stock",
                    "asset_class": "EQUITY", "nse": "HCLTECH",     "pip_decimals": 2, "price_prefix": "₹"},
    "WIPRO":       {"yf": "WIPRO.NS",      "name": "Wipro",            "type": "stock",
                    "asset_class": "EQUITY", "nse": "WIPRO",       "pip_decimals": 2, "price_prefix": "₹"},
    "TECHM":       {"yf": "TECHM.NS",      "name": "Tech Mahindra",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "TECHM",       "pip_decimals": 2, "price_prefix": "₹"},
    "LTM":         {"yf": "LTM.NS",        "name": "LTIMindtree (LTM)", "type": "stock",
                    "asset_class": "EQUITY", "nse": "LTM",         "pip_decimals": 2, "price_prefix": "₹"},
    # Pharma
    "SUNPHARMA":   {"yf": "SUNPHARMA.NS",  "name": "Sun Pharma",       "type": "stock",
                    "asset_class": "EQUITY", "nse": "SUNPHARMA",   "pip_decimals": 2, "price_prefix": "₹"},
    "DIVISLAB":    {"yf": "DIVISLAB.NS",   "name": "Divi's Labs",      "type": "stock",
                    "asset_class": "EQUITY", "nse": "DIVISLAB",    "pip_decimals": 2, "price_prefix": "₹"},
    "CIPLA":       {"yf": "CIPLA.NS",      "name": "Cipla",            "type": "stock",
                    "asset_class": "EQUITY", "nse": "CIPLA",       "pip_decimals": 2, "price_prefix": "₹"},
    "DRREDDY":     {"yf": "DRREDDY.NS",    "name": "Dr Reddy's",       "type": "stock",
                    "asset_class": "EQUITY", "nse": "DRREDDY",     "pip_decimals": 2, "price_prefix": "₹"},
    "LUPIN":       {"yf": "LUPIN.NS",      "name": "Lupin",            "type": "stock",
                    "asset_class": "EQUITY", "nse": "LUPIN",       "pip_decimals": 2, "price_prefix": "₹"},
    # FMCG
    "HINDUNILVR":  {"yf": "HINDUNILVR.NS", "name": "Hindustan Unilever", "type": "stock",
                    "asset_class": "EQUITY", "nse": "HINDUNILVR",  "pip_decimals": 2, "price_prefix": "₹"},
    "ITC":         {"yf": "ITC.NS",        "name": "ITC",              "type": "stock",
                    "asset_class": "EQUITY", "nse": "ITC",         "pip_decimals": 2, "price_prefix": "₹"},
    "NESTLEIND":   {"yf": "NESTLEIND.NS",  "name": "Nestle India",     "type": "stock",
                    "asset_class": "EQUITY", "nse": "NESTLEIND",   "pip_decimals": 2, "price_prefix": "₹"},
    "BRITANNIA":   {"yf": "BRITANNIA.NS",  "name": "Britannia",        "type": "stock",
                    "asset_class": "EQUITY", "nse": "BRITANNIA",   "pip_decimals": 2, "price_prefix": "₹"},
    "TATACONSUM":  {"yf": "TATACONSUM.NS", "name": "Tata Consumer",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "TATACONSUM",  "pip_decimals": 2, "price_prefix": "₹"},
    # Auto
    "MARUTI":      {"yf": "MARUTI.NS",     "name": "Maruti Suzuki",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "MARUTI",      "pip_decimals": 2, "price_prefix": "₹"},
    "BAJAJ-AUTO":  {"yf": "BAJAJ-AUTO.NS", "name": "Bajaj Auto",       "type": "stock",
                    "asset_class": "EQUITY", "nse": "BAJAJ-AUTO",  "pip_decimals": 2, "price_prefix": "₹"},
    "EICHERMOT":   {"yf": "EICHERMOT.NS",  "name": "Eicher Motors",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "EICHERMOT",   "pip_decimals": 2, "price_prefix": "₹"},
    "HEROMOTOCO":  {"yf": "HEROMOTOCO.NS", "name": "Hero MotoCorp",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "HEROMOTOCO",  "pip_decimals": 2, "price_prefix": "₹"},
    "ASHOKLEY":    {"yf": "ASHOKLEY.NS",   "name": "Ashok Leyland",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "ASHOKLEY",    "pip_decimals": 2, "price_prefix": "₹"},
    # Metal
    "JSWSTEEL":    {"yf": "JSWSTEEL.NS",   "name": "JSW Steel",        "type": "stock",
                    "asset_class": "EQUITY", "nse": "JSWSTEEL",    "pip_decimals": 2, "price_prefix": "₹"},
    "HINDALCO":    {"yf": "HINDALCO.NS",   "name": "Hindalco",         "type": "stock",
                    "asset_class": "EQUITY", "nse": "HINDALCO",    "pip_decimals": 2, "price_prefix": "₹"},
    "VEDL":        {"yf": "VEDL.NS",       "name": "Vedanta",          "type": "stock",
                    "asset_class": "EQUITY", "nse": "VEDL",        "pip_decimals": 2, "price_prefix": "₹"},
    "ADANIENT":    {"yf": "ADANIENT.NS",   "name": "Adani Enterprises", "type": "stock",
                    "asset_class": "EQUITY", "nse": "ADANIENT",    "pip_decimals": 2, "price_prefix": "₹"},
    "NATIONALUM":  {"yf": "NATIONALUM.NS", "name": "National Aluminium", "type": "stock",
                    "asset_class": "EQUITY", "nse": "NATIONALUM",  "pip_decimals": 2, "price_prefix": "₹"},
    # Energy / Power
    "NTPC":        {"yf": "NTPC.NS",       "name": "NTPC",             "type": "stock",
                    "asset_class": "EQUITY", "nse": "NTPC",        "pip_decimals": 2, "price_prefix": "₹"},
    "POWERGRID":   {"yf": "POWERGRID.NS",  "name": "Power Grid",       "type": "stock",
                    "asset_class": "EQUITY", "nse": "POWERGRID",   "pip_decimals": 2, "price_prefix": "₹"},
    "ONGC":        {"yf": "ONGC.NS",       "name": "ONGC",             "type": "stock",
                    "asset_class": "EQUITY", "nse": "ONGC",        "pip_decimals": 2, "price_prefix": "₹"},
    "COALINDIA":   {"yf": "COALINDIA.NS",  "name": "Coal India",       "type": "stock",
                    "asset_class": "EQUITY", "nse": "COALINDIA",   "pip_decimals": 2, "price_prefix": "₹"},
    "BPCL":        {"yf": "BPCL.NS",       "name": "BPCL",             "type": "stock",
                    "asset_class": "EQUITY", "nse": "BPCL",        "pip_decimals": 2, "price_prefix": "₹"},
    # Cement
    "ULTRACEMCO":  {"yf": "ULTRACEMCO.NS", "name": "UltraTech Cement", "type": "stock",
                    "asset_class": "EQUITY", "nse": "ULTRACEMCO",  "pip_decimals": 2, "price_prefix": "₹"},
    "SHREECEM":    {"yf": "SHREECEM.NS",   "name": "Shree Cement",     "type": "stock",
                    "asset_class": "EQUITY", "nse": "SHREECEM",    "pip_decimals": 2, "price_prefix": "₹"},
    "AMBUJACEM":   {"yf": "AMBUJACEM.NS",  "name": "Ambuja Cements",   "type": "stock",
                    "asset_class": "EQUITY", "nse": "AMBUJACEM",   "pip_decimals": 2, "price_prefix": "₹"},
    "ACC":         {"yf": "ACC.NS",        "name": "ACC",              "type": "stock",
                    "asset_class": "EQUITY", "nse": "ACC",         "pip_decimals": 2, "price_prefix": "₹"},
    # Telecom
    "INDUSTOWER":  {"yf": "INDUSTOWER.NS", "name": "Indus Towers",     "type": "stock",
                    "asset_class": "EQUITY", "nse": "INDUSTOWER",  "pip_decimals": 2, "price_prefix": "₹"},
    # NBFC / Insurance
    "BAJFINANCE":  {"yf": "BAJFINANCE.NS", "name": "Bajaj Finance",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "BAJFINANCE",  "pip_decimals": 2, "price_prefix": "₹"},
    "BAJAJFINSV":  {"yf": "BAJAJFINSV.NS", "name": "Bajaj Finserv",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "BAJAJFINSV",  "pip_decimals": 2, "price_prefix": "₹"},
    "HDFCLIFE":    {"yf": "HDFCLIFE.NS",   "name": "HDFC Life",        "type": "stock",
                    "asset_class": "EQUITY", "nse": "HDFCLIFE",    "pip_decimals": 2, "price_prefix": "₹"},
    "SBILIFE":     {"yf": "SBILIFE.NS",    "name": "SBI Life",         "type": "stock",
                    "asset_class": "EQUITY", "nse": "SBILIFE",     "pip_decimals": 2, "price_prefix": "₹"},
    "SHRIRAMFIN":  {"yf": "SHRIRAMFIN.NS", "name": "Shriram Finance",  "type": "stock",
                    "asset_class": "EQUITY", "nse": "SHRIRAMFIN",  "pip_decimals": 2, "price_prefix": "₹"},
    # Infra / Capital Goods
    "ADANIPORTS":  {"yf": "ADANIPORTS.NS", "name": "Adani Ports",      "type": "stock",
                    "asset_class": "EQUITY", "nse": "ADANIPORTS",  "pip_decimals": 2, "price_prefix": "₹"},
    "SIEMENS":     {"yf": "SIEMENS.NS",    "name": "Siemens",          "type": "stock",
                    "asset_class": "EQUITY", "nse": "SIEMENS",     "pip_decimals": 2, "price_prefix": "₹"},
    "ABB":         {"yf": "ABB.NS",        "name": "ABB India",        "type": "stock",
                    "asset_class": "EQUITY", "nse": "ABB",         "pip_decimals": 2, "price_prefix": "₹"},
    "BEL":         {"yf": "BEL.NS",        "name": "Bharat Electronics", "type": "stock",
                    "asset_class": "EQUITY", "nse": "BEL",         "pip_decimals": 2, "price_prefix": "₹"},
    "BHEL":        {"yf": "BHEL.NS",       "name": "BHEL",             "type": "stock",
                    "asset_class": "EQUITY", "nse": "BHEL",        "pip_decimals": 2, "price_prefix": "₹"},
    # Consumer / Retail
    "TITAN":       {"yf": "TITAN.NS",      "name": "Titan Company",    "type": "stock",
                    "asset_class": "EQUITY", "nse": "TITAN",       "pip_decimals": 2, "price_prefix": "₹"},
    "ASIANPAINT":  {"yf": "ASIANPAINT.NS", "name": "Asian Paints",     "type": "stock",
                    "asset_class": "EQUITY", "nse": "ASIANPAINT",  "pip_decimals": 2, "price_prefix": "₹"},
    "DMART":       {"yf": "DMART.NS",      "name": "Avenue Supermarts (DMart)", "type": "stock",
                    "asset_class": "EQUITY", "nse": "DMART",       "pip_decimals": 2, "price_prefix": "₹"},
    # Realty
    "DLF":         {"yf": "DLF.NS",        "name": "DLF",              "type": "stock",
                    "asset_class": "EQUITY", "nse": "DLF",         "pip_decimals": 2, "price_prefix": "₹"},
    "GODREJPROP":  {"yf": "GODREJPROP.NS", "name": "Godrej Properties", "type": "stock",
                    "asset_class": "EQUITY", "nse": "GODREJPROP",  "pip_decimals": 2, "price_prefix": "₹"},
}

# ---------------------------------------------------------------------------
# FOREX / GOLD (yfinance)
# JPY pairs = 2 decimals; majors = 4; XAUUSD = 2 decimals.
# ---------------------------------------------------------------------------
FOREX_INSTRUMENTS = {
    "EURUSD": {"yf": "EURUSD=X", "name": "EUR / USD",  "type": "forex",
               "asset_class": "FOREX", "nse": None, "pip_decimals": 4, "price_prefix": ""},
    "GBPUSD": {"yf": "GBPUSD=X", "name": "GBP / USD",  "type": "forex",
               "asset_class": "FOREX", "nse": None, "pip_decimals": 4, "price_prefix": ""},
    "USDJPY": {"yf": "USDJPY=X", "name": "USD / JPY",  "type": "forex",
               "asset_class": "FOREX", "nse": None, "pip_decimals": 2, "price_prefix": ""},
    "GBPJPY": {"yf": "GBPJPY=X", "name": "GBP / JPY",  "type": "forex",
               "asset_class": "FOREX", "nse": None, "pip_decimals": 2, "price_prefix": ""},
    "AUDUSD": {"yf": "AUDUSD=X", "name": "AUD / USD",  "type": "forex",
               "asset_class": "FOREX", "nse": None, "pip_decimals": 4, "price_prefix": ""},
    "USDCAD": {"yf": "USDCAD=X", "name": "USD / CAD",  "type": "forex",
               "asset_class": "FOREX", "nse": None, "pip_decimals": 4, "price_prefix": ""},
    "XAUUSD": {"yf": "GC=F", "name": "Gold Spot",  "type": "commodity",
               "asset_class": "FOREX", "nse": None, "pip_decimals": 2, "price_prefix": "$"},
}

INSTRUMENTS = {**EQUITY_INSTRUMENTS, **FOREX_INSTRUMENTS}
ALL_SYMBOLS = list(INSTRUMENTS.keys())
EQUITY_SYMBOLS = list(EQUITY_INSTRUMENTS.keys())
FOREX_SYMBOLS = list(FOREX_INSTRUMENTS.keys())

# ---------------------------------------------------------------------------
# Session windows
# ---------------------------------------------------------------------------
# NSE equities (IST — India does not observe DST, so fixed hours are safe)
SESSION_START_HH, SESSION_START_MM = 9, 15
SESSION_END_HH, SESSION_END_MM = 15, 30

ENTRY_WINDOWS = [
    ((9, 30),  (11, 15)),   # morning
    ((13, 30), (14, 45)),   # afternoon
]
BTST_WINDOW = ((13, 30), (14, 45))

# ---------------------------------------------------------------------------
# Forex sessions — sourced from native tz to stay correct across US/UK DST.
# London and New York both observe DST; India does not. Hard-coded IST windows
# silently drift by an hour twice a year, so we compute everything from local
# open/close and convert to IST at display time only.
# ---------------------------------------------------------------------------
# Local session boundaries (native local time in each session's tz):
LONDON_OPEN_LOCAL = (8, 0)     # 08:00 Europe/London
LONDON_CLOSE_LOCAL = (17, 0)   # 17:00 Europe/London
NY_OPEN_LOCAL = (8, 0)         # 08:00 America/New_York
NY_CLOSE_LOCAL = (17, 0)       # 17:00 America/New_York — global forex week close on Friday
LONDON_OPEN_WINDOW_HOURS = 2   # first 2 hours of London = secondary entry window

# Skip entries in this many minutes BEFORE the Friday NY 17:00 close
FRIDAY_CLOSE_BUFFER_MIN = 30

# Default max hold before "flag for review" on the trade log
FOREX_MAX_HOLD_HOURS = 24
BTST_MAX_HOLD_DAYS = 2  # if neither SL nor target hit within 2 trading days,
                        # force-close at last available price rather than
                        # leaving the position open indefinitely

# Strategy filters (shared)
MAX_SIGNALS_PER_INSTRUMENT_PER_DAY = 2

# If a signal's own entry timestamp is already older than this by the time
# its confirmation chain (BOS -> retest -> rejection/CHoCH) finishes
# resolving, it's no longer actionable — reject it outright instead of
# showing a "fresh-looking" card for a trade that's already played out.
MAX_SIGNAL_STALENESS_MIN = 15
VOLUME_MULTIPLIER = 1.5
ATR_PERIOD = 14
ATR_BUFFER_MIN = 0.10
ATR_BUFFER_MAX = 0.15
MIN_RR = 3.0        # your original 1:3 target — kept as a reference label
MIN_RR_FLOOR = 1.0  # hard floor: signals below 1:1 are rejected outright
                    # (risking more than the potential reward); everything
                    # from 1:1 up is now accepted and tagged with its real RR
