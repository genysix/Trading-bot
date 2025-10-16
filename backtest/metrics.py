# backtest/metrics.py
# -*- coding: utf-8 -*-
"""
Métriques de base pour évaluer un backtest (simples, extensibles plus tard).
- compute_trade_stats(trades)
- compute_equity_stats(equity_curve)
"""

from __future__ import annotations
from typing import Dict, Any, List
import math
import pandas as pd


def compute_trade_stats(trades: List[Any]) -> Dict[str, Any]:
    """
    Calcule quelques stats à partir d'une liste de Trade (backtest/engine.Trade).
    Retourne : nb_trades, hit_ratio, avg_win, avg_loss, profit_factor, total_pnl
    """
    if not trades:
        return {"nb_trades": 0, "hit_ratio": 0.0, "avg_win": 0.0, "avg_loss": 0.0, "profit_factor": 0.0, "total_pnl": 0.0}

    pnls = [t.pnl for t in trades]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]

    nb = len(trades)
    hit = len(wins) / nb if nb > 0 else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    pf = (sum(wins) / abs(sum(losses))) if losses else float("inf")
    total = sum(pnls)

    return {
        "nb_trades": nb,
        "hit_ratio": hit,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": pf,
        "total_pnl": total
    }


def compute_equity_stats(equity_curve: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    À partir d'une equity_curve [{"time":..., "equity":...}, ...], calcule :
    - CAGR (approx. sur période totale)
    - Max drawdown
    - Sharpe simple (quotidien approximé si possible)
    """
    if not equity_curve:
        return {"CAGR": 0.0, "MaxDD": 0.0, "Sharpe": 0.0}

    df = pd.DataFrame(equity_curve)
    df = df.dropna(subset=["equity"])
    if len(df) < 2:
        return {"CAGR": 0.0, "MaxDD": 0.0, "Sharpe": 0.0}

    # Retours simples
    df["ret"] = df["equity"].pct_change().fillna(0.0)

    # Max Drawdown
    roll_max = df["equity"].cummax()
    dd = df["equity"] / roll_max - 1.0
    max_dd = dd.min()

    # CAGR approximé
    start_eq = float(df["equity"].iloc[0])
    end_eq = float(df["equity"].iloc[-1])
    days = (pd.to_datetime(df["time"].iloc[-1]) - pd.to_datetime(df["time"].iloc[0])).days
    years = max(days / 365.25, 1e-9)
    cagr = (end_eq / start_eq) ** (1.0 / years) - 1.0 if start_eq > 0 else 0.0

    # Sharpe simple (sans risk-free, annualisé avec sqrt(252))
    mu = df["ret"].mean()
    sd = df["ret"].std(ddof=1)
    sharpe = (mu / sd) * (252 ** 0.5) if sd > 0 else 0.0

    return {"CAGR": cagr, "MaxDD": float(max_dd), "Sharpe": float(sharpe)}
