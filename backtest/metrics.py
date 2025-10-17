# backtest/metrics.py
import pandas as pd
import numpy as np

def compute_basic_metrics(result: dict) -> dict:
    eq = result["equity_curve"]["equity"].astype(float)
    ret = eq.pct_change().fillna(0.0)
    cumret = (1 + ret).prod() - 1
    max_dd = (eq / eq.cummax() - 1).min()
    sharpe = (ret.mean() / (ret.std() + 1e-12)) * np.sqrt(252)  # D1 ~252
    return {
        "final_equity": float(eq.iloc[-1]),
        "cum_return": float(cumret),
        "max_drawdown": float(max_dd),
        "sharpe_like": float(sharpe),
        "n_trades": len(result["trades"]),
    }
