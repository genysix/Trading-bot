# -*- coding: utf-8 -*-
"""
Main backtest launcher for the Trading-bot project.
Executes a complete Turtle-like backtest and prints the final performance report.
"""

from __future__ import annotations
import sys
import pathlib
import argparse
import pandas as pd
from dotenv import load_dotenv

# --- Setup import paths ---
ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# --- Project imports ---
from data.store import load_series                     # Must return OHLCV DataFrame
from backtest.engine import BacktestEngine, EngineConfig
from backtest.metrics import compute_basic_metrics
from backtest.report_text import generate_text_report
from strategies.turtle_like import TurtleLikeConfig, TurtleLikeStrategy


# ---------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------
def parse_args():
    p = argparse.ArgumentParser(description="Run Turtle-like backtest on historical data")
    p.add_argument("--symbol", default="XAU_USD", help="Instrument symbol (ex: XAU_USD, EUR_USD, BTC_USD)")
    p.add_argument("--timeframe", default="D1", help="Timeframe (ex: M15, H1, H4, D1)")
    p.add_argument("--start", default=None, help="Start date (YYYY-MM-DD)")
    p.add_argument("--end", default=None, help="End date (YYYY-MM-DD)")
    p.add_argument("--capital", type=float, default=100000.0, help="Initial wallet / starting capital")
    p.add_argument("--data-root", default="data_local", help="Root directory where local OHLC data are stored")
    p.add_argument("--ema", type=int, default=50, help="EMA period (0 = disabled)")
    p.add_argument("--donchian", type=int, default=55, help="Donchian channel period for breakouts")
    p.add_argument("--atr", type=int, default=20, help="ATR period")
    return p.parse_args()


# ---------------------------------------------------------
# Main function
# ---------------------------------------------------------
def main():
    load_dotenv()
    args = parse_args()

    # 1) Load historical OHLC data
    print(f"\nLoading {args.symbol} ({args.timeframe}) ...")
    df = load_series(
        symbol=args.symbol,
        timeframe=args.timeframe,
        root=args.data_root,
        start=args.start,
        end=args.end,
    )

    if df is None or df.empty:
        raise RuntimeError("❌ No data found — please download historical data first via main_download.py")

    # Ensure correct time index
    if "time" not in df.columns:
        df["time"] = df.index
    df = df.sort_values("time").reset_index(drop=True)

    # 2) Initialize Turtle-like strategy
    strat_cfg = TurtleLikeConfig(
        DONCHIAN=args.donchian,
        EMA_PERIOD=args.ema,
        ATR_PERIOD=args.atr,
        RISK_PER_TRADE=0.01,          # 1% risk per trade
        STOP_K=2.0,
        TRAIL_K=3.0,
        VALUE_PER_POINT=1.0,
        PYRAMID_UNITS=0,
    )
    strategy = TurtleLikeStrategy(strat_cfg)
    strategy.bind_prices(df)

    # 3) Backtest engine configuration
    engine = BacktestEngine(
        EngineConfig(
            INITIAL_CAPITAL=args.capital,
            EXECUTION="next_open",     # or "close"
            COMMISSION_PER_TRADE=0.0,
            SLIPPAGE_PER_TICK=0.0,
        )
    )

    # 4) Run backtest
    print(f"Running backtest on {args.symbol} ({args.timeframe}) ...")
    result = engine.run(strategy=strategy, df=df, symbol=args.symbol)

    # 5) Compute metrics and generate report
    metrics = compute_basic_metrics(result)
    report = generate_text_report(
        result=result,
        df_prices=df,
        initial_capital=args.capital,
        symbol=args.symbol,
        timeframe=args.timeframe,
        metrics=metrics,
    )

    # 6) Display final formatted report
    print("\n" + "=" * 90)
    print(report)
    print("=" * 90 + "\n")


# ---------------------------------------------------------
# Entry point
# ---------------------------------------------------------
if __name__ == "__main__":
    main()
