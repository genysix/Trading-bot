# backtest/engine.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Dict, Any, List, Optional
import pandas as pd

@dataclass
class EngineConfig:
    INITIAL_CAPITAL: float = 100_000.0
    EXECUTION: str = "next_open"        # "close" ou "next_open"
    COMMISSION_PER_TRADE: float = 0.0
    SLIPPAGE_PER_TICK: float = 0.0

class BacktestEngine:
    def __init__(self, cfg: EngineConfig):
        self.cfg = cfg

    def _validate_df(self, df: pd.DataFrame):
        for c in ("time","open","high","low","close"):
            if c not in df.columns:
                raise ValueError(f"Colonne manquante: {c}")
        if not df.index.is_monotonic_increasing:
            df.sort_index(inplace=True)

    def run(self, strategy, df: pd.DataFrame, symbol: str = "XAU_USD") -> Dict[str,Any]:
        self._validate_df(df)
        cash = float(self.cfg.INITIAL_CAPITAL)
        qty = 0.0
        position_price = None
        trades: List[Dict[str,Any]] = []
        equity_curve = []

        df = df.copy().reset_index(drop=True)

        for i in range(len(df)):
            bar = df.iloc[i]
            bar_dict = dict(
                time=bar["time"] if "time" in df.columns else None,
                open=float(bar["open"]),
                high=float(bar["high"]),
                low=float(bar["low"]),
                close=float(bar["close"]),
                volume=float(bar["volume"]) if "volume" in df.columns else None,
                i=i
            )

            signal = strategy.on_bar(bar_dict)

            # Execution price
            if self.cfg.EXECUTION == "close":
                exec_price = bar_dict["close"]
            else:  # next_open
                next_open = df.iloc[i+1]["open"] if i+1 < len(df) else bar_dict["close"]
                exec_price = float(next_open)

            if signal:
                act = signal.get("action")
                side = signal.get("side")
                size = float(signal.get("qty", 0.0))

                if act == "ENTER" and side == "LONG" and qty == 0.0 and size > 0:
                    # Buy
                    cost = size * exec_price
                    cost += self.cfg.COMMISSION_PER_TRADE
                    if cost <= cash:
                        cash -= cost
                        qty = size
                        position_price = exec_price
                        trades.append({"time": bar_dict["time"], "type":"BUY", "price":exec_price, "qty":size})
                elif act == "EXIT" and qty > 0.0:
                    # Sell
                    proceeds = qty * exec_price - self.cfg.COMMISSION_PER_TRADE
                    cash += proceeds
                    trades.append({"time": bar_dict["time"], "type":"SELL", "price":exec_price, "qty":qty})
                    qty = 0.0
                    position_price = None

            # mark-to-market
            mkt = qty * bar_dict["close"]
            equity = cash + mkt
            equity_curve.append({"time": bar_dict["time"], "equity": equity})

        return {
            "symbol": symbol,
            "trades": trades,
            "equity_curve": pd.DataFrame(equity_curve),
            "final_cash": cash,
            "final_position_qty": qty,
        }
