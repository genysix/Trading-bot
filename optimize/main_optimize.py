# optimize/main_optimize.py
# -*- coding: utf-8 -*-
"""
Lance un gridsearch sur un Parquet local en utilisant strategies/turtle_like.
Exemples :
  python optimize/main_optimize.py --symbol XAU_USD --timeframe D1 --start 2020-01-01 --end 2024-09-11 \
    --export results/xau_d1_grid.csv

NB : tant que les ENTRÉES ne sont pas finalisées dans turtle_like.py, il est probable
qu'il n'y ait pas de trades. Ce fichier sert d’enveloppe prête pour la suite.
"""

from __future__ import annotations
import argparse
import os
import pandas as pd
from dotenv import load_dotenv

from config.config import DATA_ROOT, DEFAULT_SLIPPAGE, DEFAULT_COMMISSION, INITIAL_CAPITAL
from data.store import build_series_path, read_series_parquet
from backtest.engine import EngineConfig
from optimize.gridsearch import run_grid


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="GridSearch Turtle-like sur données locales")
    parser.add_argument("--symbol", required=True, help="ex. XAU_USD")
    parser.add_argument("--timeframe", required=True, choices=["M1","M5","M15","H1","H4","D1","W1"])
    parser.add_argument("--start", required=False, default=None)
    parser.add_argument("--end", required=False, default=None)
    parser.add_argument("--data-root", default=DATA_ROOT)
    parser.add_argument("--exec-timing", choices=["close","next_open"], default="next_open")
    parser.add_argument("--slippage", type=float, default=DEFAULT_SLIPPAGE)
    parser.add_argument("--commission", type=float, default=DEFAULT_COMMISSION)
    parser.add_argument("--capital", type=float, default=INITIAL_CAPITAL)
    parser.add_argument("--export", default=None, help="Chemin CSV pour exporter la table des résultats")
    args = parser.parse_args()

    # Charger la série
    path = build_series_path(args.data_root, args.symbol, args.timeframe)
    if not os.path.exists(path):
        raise SystemExit(f"Fichier introuvable : {path}. Lance d'abord main_download.py.")

    df = read_series_parquet(path)
    if args.start:
        df = df[df["time"] >= pd.to_datetime(args.start, utc=True)]
    if args.end:
        df = df[df["time"] <= pd.to_datetime(args.end, utc=True)]
    if len(df) < 10:
        raise SystemExit("Pas assez de données après filtrage.")

    # Engine config
    eng_cfg = EngineConfig(
        EXECUTION_TIMING=args.exec_timing,
        SLIPPAGE_ABS=args.slippage,
        COMMISSION_FIXED=args.commission,
        INITIAL_CAPITAL=args.capital,
        DEFAULT_QTY=1.0,
        POINT_VALUE=1.0,
        ALLOW_SHORT=True
    )

    # Import tardif pour éviter dépendances circulaires
    from strategies.turtle_like import TurtleLikeStrategy, TurtleParams

    # Fabrique de stratégie à partir d'un dict de params
    def make_strategy(p: dict):
        params = TurtleParams(
            RISK_PER_TRADE=p.get("RISK_PER_TRADE", 0.05),
            MAX_LEVERAGE=p.get("MAX_LEVERAGE", 2.0),
            TIMEFRAME=args.timeframe,
            ATR_LEN=p.get("ATR_LEN", 20),
            EMA_TREND_LEN=p.get("EMA_TREND_LEN", 200),
            USE_TREND_FILTER=p.get("USE_TREND_FILTER", True),
            USE_TRAIL_ATR=p.get("USE_TRAIL_ATR", True),
            TRAIL_K=p.get("TRAIL_K", 2.5),
            USE_DONCHIAN_EXIT=p.get("USE_DONCHIAN_EXIT", True),
            DONCHIAN_EXIT_Y=p.get("DONCHIAN_EXIT_Y", 20),
            SLIPPAGE_PER_TICK=p.get("SLIPPAGE_PER_TICK", args.slippage),
            COMMISSION_PER_TRADE=p.get("COMMISSION_PER_TRADE", args.commission),
            STRICT_VALIDATION=True
        )
        return TurtleLikeStrategy(params)

    # Grille de paramètres (point de départ ; tu ajusteras)
    param_grid = {
        "ATR_LEN": [14, 20, 30],
        "TRAIL_K": [1.5, 2.0, 2.5, 3.0],
        "DONCHIAN_EXIT_Y": [10, 20, 55],
        "EMA_TREND_LEN": [100, 200, 300],
        "USE_TREND_FILTER": [True, False],
        "USE_TRAIL_ATR": [True],
        "USE_DONCHIAN_EXIT": [True],
        # RISK & LEVERAGE peuvent être ajoutés ici quand le sizing sera implémenté
    }

    out = run_grid(
        df=df,
        make_strategy=make_strategy,
        engine_cfg=eng_cfg,
        param_grid=param_grid,
        symbol=args.symbol,
        export_csv_path=args.export
    )

    # Affiche les 10 meilleurs
    with pd.option_context("display.max_columns", None, "display.width", 200):
        print(out.head(10))

    if args.export:
        print(f"\n→ Résultats exportés : {args.export} ({len(out)} lignes)")


if __name__ == "__main__":
    main()
