"""Loads daily prices: from Yahoo Finance, a local cache, or a synthetic demo set."""
import os

import numpy as np
import pandas as pd

import config as cfg

CACHE = os.path.join(os.path.dirname(__file__), "data", "prices.csv")


def all_tickers():
    return list(cfg.EQUITY) + list(cfg.FX) + [cfg.INDEX, cfg.VOL_INDEX]


def load_prices(demo=False, refresh=False):
    """Returns a DataFrame of daily closes, one column per risk factor."""
    if demo:
        return _synthetic_prices()
    if os.path.exists(CACHE) and not refresh:
        return pd.read_csv(CACHE, index_col=0, parse_dates=True)

    import yfinance as yf

    raw = yf.download(all_tickers(), start=cfg.START_DATE, auto_adjust=True, progress=False)
    prices = raw["Close"][all_tickers()].ffill().dropna()
    if prices.empty:
        raise RuntimeError("No data downloaded. Check your connection or run with --demo.")
    os.makedirs(os.path.dirname(CACHE), exist_ok=True)
    prices.to_csv(CACHE)
    return prices


def _synthetic_prices(seed=7):
    """Correlated random walks, so the code runs with no internet. Not real data."""
    rng = np.random.default_rng(seed)
    tickers = all_tickers()
    dates = pd.bdate_range(cfg.START_DATE, pd.Timestamp.today().normalize())
    n, k = len(dates), len(tickers)

    market = rng.standard_t(df=4, size=n) * 0.008          # fat-tailed market factor
    returns = np.empty((n, k))
    for j, t in enumerate(tickers):
        noise = rng.standard_normal(n)
        if t in cfg.EQUITY:
            returns[:, j] = 1.0 * market + 0.010 * noise
        elif t in cfg.FX:
            returns[:, j] = -0.10 * market + 0.0025 * noise  # rupee weakens in sell-offs
        elif t == cfg.INDEX:
            returns[:, j] = market + 0.002 * noise
        else:                                                # volatility index
            returns[:, j] = -4.0 * market + 0.03 * noise
    start = {t: 1000.0 for t in tickers}
    start.update({"USDINR=X": 70.0, cfg.INDEX: 11000.0, cfg.VOL_INDEX: 16.0})
    prices = pd.DataFrame(np.exp(np.cumsum(returns, axis=0)), index=dates, columns=tickers)
    prices = prices * pd.Series(start)
    # keep the volatility index in a realistic range
    prices[cfg.VOL_INDEX] = 16.0 * np.exp(pd.Series(returns[:, -1], index=dates).rolling(60, min_periods=1).sum())
    return prices
