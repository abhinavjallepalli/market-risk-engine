"""Portfolio and model settings. Change these first when you experiment."""

START_DATE = "2019-01-01"          # long enough to include the March 2020 crash

# Market value in INR of each long stock position
EQUITY = {
    "RELIANCE.NS": 1_000_000,
    "TCS.NS": 1_000_000,
    "HDFCBANK.NS": 1_000_000,
    "INFY.NS": 1_000_000,
    "ICICIBANK.NS": 1_000_000,
    "ITC.NS": 1_000_000,
    "LT.NS": 1_000_000,
    "SBIN.NS": 1_000_000,
}

# INR value of a long USD position (gains when the rupee weakens)
FX = {"USDINR=X": 1_700_000}

INDEX = "^NSEI"            # option underlying (NIFTY 50)
VOL_INDEX = "^INDIAVIX"    # used as the implied volatility of the options

# qty > 0 is long, qty < 0 is short. Strike = moneyness x today's NIFTY level.
OPTIONS = [
    {"name": "Long NIFTY put (hedge)", "kind": "put", "moneyness": 0.98, "days": 30, "qty": 150},
    {"name": "Short NIFTY call", "kind": "call", "moneyness": 1.03, "days": 30, "qty": -150},
]

RISK_FREE = 0.065
TRADING_DAYS = 252

VAR_CONF = 0.99            # 99% VaR
ES_CONF = 0.975            # 97.5% Expected Shortfall (the FRTB standard)
HORIZON_DAYS = 10          # regulatory horizon, via square-root-of-time scaling
LOOKBACK = 500             # days of history used for VaR
MC_SIMS = 20_000
BACKTEST_DAYS = 250

# 1-day 99% VaR limits in INR. Tune these once you see your real numbers.
LIMITS = {"Equity": 200_000, "FX": 20_000, "Options": 60_000, "Total": 220_000}
WARNING_LEVEL = 0.80       # flag when utilisation passes 80%

# Hypothetical stress scenarios: shock applied to each group of risk factors
STRESS_SCENARIOS = {
    "Equity crash (-10%, vol +50%)": {"equity": -0.10, "fx": 0.00, "vol": 0.50},
    "Rupee depreciation (USDINR +5%)": {"equity": 0.00, "fx": 0.05, "vol": 0.10},
    "Sharp rally (+5%, vol -20%)": {"equity": 0.05, "fx": -0.01, "vol": -0.20},
    "Risk-off (-7%, USDINR +3%, vol +80%)": {"equity": -0.07, "fx": 0.03, "vol": 0.80},
}
COVID_WINDOW = ("2020-02-19", "2020-03-23")   # historical replay
