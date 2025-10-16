# optimize/gridsearch.py
# -*- coding: utf-8 -*-
"""
GridSearch générique pour stratégies bar-par-bar du projet.
- Exécute des backtests sur une grille d'hyperparamètres (stratégie fournie)
- Concatène les résultats (métriques) dans un DataFrame
- Export optionnel CSV/Parquet pour visualisation (heatmaps, etc.)
"""

from __future__ import annotations
from typing import Dict, Any, List, Iterable, Tuple, Callable, Optional
import itertools
import pandas as pd

from backtest.engine import BacktestEngine, EngineConfig
from backtest.metrics import compute_trade_stats, compute_equity_stats


def product_dict(param_grid: Dict[str, Iterable[Any]]) -> List[Dict[str, Any]]:
    """
    Transforme {"A":[1,2], "B":[10,20]} en
    [{"A":1,"B":10}, {"A":1,"B":20}, {"A":2,"B":10}, {"A":2,"B":20}]
    """
    keys = list(param_grid.keys())
    vals = [list(v) for v in param_grid.values()]
    combos = []
    for tup in itertools.product(*vals):
        combos.append({k: v for k, v in zip(keys, tup)})
    return combos


def run_grid(
    *,
    df: pd.DataFrame,
    make_strategy: Callable[[Dict[str, Any]], Any],
    engine_cfg: EngineConfig,
    param_grid: Dict[str, Iterable[Any]],
    symbol: str = "XAU_USD",
    scorer: Optional[Callable[[Dict[str, Any], Dict[str, Any], Dict[str, Any]], float]] = None,
    export_csv_path: Optional[str] = None
) -> pd.DataFrame:
    """
    Lance un gridsearch :
    - make_strategy(params_dict) -> instance de stratégie configurée
    - engine_cfg : config de l'engine (slippage, commission, timing…)
    - param_grid : dictionnaire {param: liste_de_valeurs}
    - scorer(params, trade_stats, equity_stats) -> score (float) ; si None, on utilise Calmar-like = CAGR / |MaxDD|

    Retour :
    - DataFrame avec colonnes: params..., nb_trades, hit_ratio, pf, CAGR, MaxDD, Sharpe, final_equity, score
    """
    combos = product_dict(param_grid)
    rows: List[Dict[str, Any]] = []

    for i, p in enumerate(combos, 1):
        strat = make_strategy(p)
        engine = BacktestEngine(engine_cfg)
        result = engine.run(strat, df, symbol=symbol)

        tstats = compute_trade_stats(result["trades"])
        estats = compute_equity_stats(result["equity_curve"])

        if scorer is None:
            # Score par défaut : Calmar-like
            dd = abs(estats.get("MaxDD", 0.0))
            score = (estats.get("CAGR", 0.0) / dd) if dd > 0 else 0.0
        else:
            score = float(scorer(p, tstats, estats))

        row = dict(p)
        row.update({
            "nb_trades": tstats["nb_trades"],
            "hit_ratio": tstats["hit_ratio"],
            "profit_factor": tstats["profit_factor"],
            "CAGR": estats["CAGR"],
            "MaxDD": estats["MaxDD"],
            "Sharpe": estats["Sharpe"],
            "final_equity": result["final_equity"],
            "score": score
        })
        rows.append(row)

    out = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)

    if export_csv_path:
        out.to_csv(export_csv_path, index=False)

    return out
