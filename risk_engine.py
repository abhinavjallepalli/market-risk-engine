"""Core risk maths: option pricing, portfolio P&L, VaR, ES, backtest, stress, attribution."""
import numpy as np
import pandas as pd
from scipy.stats import chi2, norm

import config as cfg


# ---------------------------------------------------------------- Black-Scholes
def bs_price(S, K, T, vol, kind, r=cfg.RISK_FREE):
    """Black-Scholes price of a European option. Works on numbers or arrays."""
    S, vol = np.asarray(S, dtype=float), np.asarray(vol, dtype=float)
    d1 = (np.log(S / K) + (r + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    d2 = d1 - vol * np.sqrt(T)
    if kind == "call":
        return S * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * norm.cdf(-d1)


def bs_greeks(S, K, T, vol, kind, r=cfg.RISK_FREE):
    """Delta, gamma, vega (per 1.00 change in vol) and theta (per year)."""
    d1 = (np.log(S / K) + (r + 0.5 * vol**2) * T) / (vol * np.sqrt(T))
    d2 = d1 - vol * np.sqrt(T)
    gamma = norm.pdf(d1) / (S * vol * np.sqrt(T))
    vega = S * norm.pdf(d1) * np.sqrt(T)
    decay = -S * norm.pdf(d1) * vol / (2 * np.sqrt(T))
    if kind == "call":
        delta = norm.cdf(d1)
        theta = decay - r * K * np.exp(-r * T) * norm.cdf(d2)
    else:
        delta = norm.cdf(d1) - 1
        theta = decay + r * K * np.exp(-r * T) * norm.cdf(-d2)
    return {"delta": delta, "gamma": gamma, "vega": vega, "theta": theta}


# -------------------------------------------------------------------- Portfolio
class Portfolio:
    """Today's positions. `pnl()` revalues them under any set of factor returns."""

    def __init__(self, prices):
        last = prices.iloc[-1]
        self.factors = list(prices.columns)
        self.spot = float(last[cfg.INDEX])
        self.vol = float(last[cfg.VOL_INDEX]) / 100
        self.equity = pd.Series(cfg.EQUITY, dtype=float)
        self.fx = pd.Series(cfg.FX, dtype=float)
        self.options = [
            {**o, "K": o["moneyness"] * self.spot, "T": o["days"] / cfg.TRADING_DAYS}
            for o in cfg.OPTIONS
        ]

    def option_value(self, S, vol):
        return sum(o["qty"] * bs_price(S, o["K"], o["T"], vol, o["kind"]) for o in self.options)

    def pnl_by_class(self, returns):
        """P&L in INR per asset class for each row of factor returns.

        Stocks and FX are linear. Options are fully revalued with Black-Scholes,
        so their non-linearity (gamma) and volatility risk (vega) are captured.
        """
        S = self.spot * (1 + returns[cfg.INDEX])
        vol = np.maximum(self.vol * (1 + returns[cfg.VOL_INDEX]), 0.01)
        return pd.DataFrame({
            "Equity": returns[self.equity.index] @ self.equity,
            "FX": returns[self.fx.index] @ self.fx,
            "Options": self.option_value(S, vol) - self.option_value(self.spot, self.vol),
        })

    def pnl(self, returns):
        return self.pnl_by_class(returns).sum(axis=1)

    def greeks(self):
        """Position-level Greeks (already multiplied by quantity)."""
        rows = []
        for o in self.options:
            g = bs_greeks(self.spot, o["K"], o["T"], self.vol, o["kind"])
            rows.append({"Option": o["name"], "Strike": o["K"], "Qty": o["qty"],
                         "Value": o["qty"] * float(bs_price(self.spot, o["K"], o["T"], self.vol, o["kind"])),
                         **{k.capitalize(): o["qty"] * v for k, v in g.items()}})
        return pd.DataFrame(rows)

    def linear_exposures(self):
        """INR exposure to a 100% move in each factor (delta-vega approximation).

        This is what the parametric method uses: it sees options only through
        delta and vega, and ignores gamma.
        """
        w = pd.Series(0.0, index=self.factors)
        w[self.equity.index] = self.equity
        w[self.fx.index] = self.fx
        g = self.greeks()
        w[cfg.INDEX] += g["Delta"].sum() * self.spot
        w[cfg.VOL_INDEX] += g["Vega"].sum() * self.vol
        return w


# -------------------------------------------------------------------- VaR and ES
def var_es_from_pnl(pnl, var_conf=cfg.VAR_CONF, es_conf=cfg.ES_CONF):
    """VaR is the loss quantile; ES is the average loss beyond its own quantile."""
    pnl = np.asarray(pnl)
    var = -np.quantile(pnl, 1 - var_conf)
    cutoff = np.quantile(pnl, 1 - es_conf)
    es = -pnl[pnl <= cutoff].mean()
    return var, es


def historical_var(portfolio, returns):
    """Replay each past day's market move on today's portfolio."""
    return var_es_from_pnl(portfolio.pnl(returns))


def parametric_var(portfolio, returns):
    """Variance-covariance: assumes normal returns and a linear portfolio."""
    w = portfolio.linear_exposures()
    sigma = float(np.sqrt(w @ returns.cov() @ w))
    var = norm.ppf(cfg.VAR_CONF) * sigma
    es = sigma * norm.pdf(norm.ppf(cfg.ES_CONF)) / (1 - cfg.ES_CONF)
    return var, es


def monte_carlo_var(portfolio, returns, seed=42):
    """Simulate correlated normal returns, then fully revalue the portfolio."""
    rng = np.random.default_rng(seed)
    sims = rng.multivariate_normal(np.zeros(returns.shape[1]), returns.cov().values, cfg.MC_SIMS)
    return var_es_from_pnl(portfolio.pnl(pd.DataFrame(sims, columns=returns.columns)))


def component_var(portfolio, returns):
    """Splits parametric VaR across factors. The components add up to the total."""
    w = portfolio.linear_exposures()
    cov = returns.cov()
    sigma = float(np.sqrt(w @ cov @ w))
    comp = norm.ppf(cfg.VAR_CONF) * w * (cov @ w) / sigma
    out = pd.DataFrame({"Exposure (INR)": w, "Component VaR": comp})
    out["% of VaR"] = out["Component VaR"] / out["Component VaR"].sum()
    return out.sort_values("Component VaR", ascending=False)


# --------------------------------------------------------------------- Backtest
def backtest(portfolio, returns):
    """Compare each day's P&L with the VaR predicted from the previous LOOKBACK days.

    Uses today's positions throughout (a "static portfolio" backtest).
    """
    pnl = portfolio.pnl(returns)
    var = -pnl.rolling(cfg.LOOKBACK).quantile(1 - cfg.VAR_CONF).shift(1)
    table = pd.DataFrame({"P&L": pnl, "VaR 99%": var}).dropna().tail(cfg.BACKTEST_DAYS)
    table["Breach"] = table["P&L"] < -table["VaR 99%"]
    return table


def kupiec_test(n, x, p=1 - cfg.VAR_CONF):
    """Kupiec proportion-of-failures test. H0: the breach rate equals p."""
    rate = x / n
    log_h0 = (n - x) * np.log(1 - p) + x * np.log(p)
    log_h1 = (n - x) * np.log(1 - rate) + x * np.log(rate) if 0 < x < n else 0.0
    lr = -2 * (log_h0 - log_h1)
    p_value = 1 - chi2.cdf(lr, df=1)
    return lr, p_value


def traffic_light(breaches):
    """Basel zones for 250 days at 99%."""
    return "Green" if breaches <= 4 else "Yellow" if breaches <= 9 else "Red"


# ----------------------------------------------------------------------- Stress
def stress_tests(portfolio, prices):
    scenarios = {}
    for name, s in cfg.STRESS_SCENARIOS.items():
        shock = pd.Series(0.0, index=portfolio.factors)
        shock[list(cfg.EQUITY) + [cfg.INDEX]] = s["equity"]
        shock[list(cfg.FX)] = s["fx"]
        shock[cfg.VOL_INDEX] = s["vol"]
        scenarios[name] = shock
    start, end = cfg.COVID_WINDOW
    if prices.index[0] <= pd.Timestamp(start):
        window = prices.loc[start:end]
        scenarios[f"COVID replay ({start} to {end})"] = window.iloc[-1] / window.iloc[0] - 1
    shocks = pd.DataFrame(scenarios).T
    out = portfolio.pnl_by_class(shocks)
    out["Total"] = out.sum(axis=1)
    return out


# ------------------------------------------------------------- P&L attribution
def pnl_attribution(portfolio, prices, days=10):
    """Explain the option book's daily P&L with the Greeks.

    Actual = full revaluation. Explained = delta + gamma + vega + theta.
    What is left over is the unexplained P&L.
    """
    S, vol = prices[cfg.INDEX], prices[cfg.VOL_INDEX] / 100
    dt = 1 / cfg.TRADING_DAYS
    rows = []
    for i in range(len(prices) - days, len(prices)):
        s0, s1, v0, v1 = S.iloc[i - 1], S.iloc[i], vol.iloc[i - 1], vol.iloc[i]
        row = dict.fromkeys(["Delta", "Gamma", "Vega", "Theta", "Actual"], 0.0)
        for o in portfolio.options:
            g = bs_greeks(s0, o["K"], o["T"], v0, o["kind"])
            row["Delta"] += o["qty"] * g["delta"] * (s1 - s0)
            row["Gamma"] += o["qty"] * 0.5 * g["gamma"] * (s1 - s0) ** 2
            row["Vega"] += o["qty"] * g["vega"] * (v1 - v0)
            row["Theta"] += o["qty"] * g["theta"] * dt
            row["Actual"] += o["qty"] * float(
                bs_price(s1, o["K"], o["T"] - dt, v1, o["kind"]) - bs_price(s0, o["K"], o["T"], v0, o["kind"]))
        row["Explained"] = row["Delta"] + row["Gamma"] + row["Vega"] + row["Theta"]
        row["Unexplained"] = row["Actual"] - row["Explained"]
        rows.append(pd.Series(row, name=prices.index[i].date()))
    return pd.DataFrame(rows)[["Delta", "Gamma", "Vega", "Theta", "Explained", "Actual", "Unexplained"]]


# ----------------------------------------------------------------------- Limits
def limit_report(portfolio, returns):
    """Standalone 99% historical VaR per asset class against its limit."""
    by_class = portfolio.pnl_by_class(returns)
    by_class["Total"] = by_class.sum(axis=1)
    rows = []
    for name, limit in cfg.LIMITS.items():
        var, _ = var_es_from_pnl(by_class[name])
        use = var / limit
        status = "BREACH" if use > 1 else "WARNING" if use > cfg.WARNING_LEVEL else "OK"
        rows.append({"Desk": name, "VaR 99% 1d": var, "Limit": limit, "Utilisation": use, "Status": status})
    return pd.DataFrame(rows)
