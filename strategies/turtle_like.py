# strategies/turtle_like.py
# -*- coding: utf-8 -*-
"""
Stratégie Turtle-like complète (v1)
- Entrées : breakouts Donchian (X) avec filtre EMA (optionnel)
- Sorties : Trailing ATR + Donchian inverse (logique OR)
- Sizing : risque % du capital / (ATR * STOP_K * VALUE_PER_POINT)
- Pyramiding : ajout d'unités tous les PYRAMID_STEP_ATR * ATR (jusqu'à PYRAMID_UNITS)
- Indicateurs : via indicators/core.py

Conventions d'I/O :
- Moteur de backtest appelle .on_bar(bar) (bar: dict "time","open","high","low","close","volume?")
- La stratégie retourne { "action":"ENTER"/"EXIT", "side":"LONG/SHORT", "qty":float, ... } ou None
- Le moteur exécute au close ou next open (selon EngineConfig), applique slippage/commission.

Avertissement :
- Code pour expérimentation. Le trading réel comporte des risques importants.
"""
# strategies/turtle_like.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any
import pandas as pd

from indicators.donchian import donchian
from indicators.atr import atr

@dataclass
class TurtleLikeConfig:
    DONCHIAN: int = 55
    EMA_PERIOD: int = 0          # 0 = filtre OFF
    ATR_PERIOD: int = 20
    RISK_PER_TRADE: float = 0.01
    STOP_K: float = 2.0
    TRAIL_K: float = 3.0
    VALUE_PER_POINT: float = 1.0
    PYRAMID_UNITS: int = 0

class TurtleLikeStrategy:
    def __init__(self, cfg: TurtleLikeConfig):
        self.cfg = cfg
        self.df: Optional[pd.DataFrame] = None
        self.pos_qty = 0.0
        self.entry_price: Optional[float] = None
        self.trailing: Optional[float] = None

    def bind_prices(self, df: pd.DataFrame):
        self.df = df
        self.df["ema"] = df["close"].ewm(span=self.cfg.EMA_PERIOD, adjust=False).mean() if self.cfg.EMA_PERIOD>0 else None
        self.df["atr"] = atr(df, self.cfg.ATR_PERIOD)
        self.df["don_hi"], self.df["don_lo"] = donchian(df, self.cfg.DONCHIAN)

    def _sizing(self, price: float, bar_idx: int) -> float:
        # risque% du capital / (ATR * STOP_K * VALUE_PER_POINT)
        capital = 100_000.0  # le moteur passe le capital mark-to-market; ici simple base
        a = float(self.df.loc[bar_idx, "atr"])
        if not a or a <= 0:
            return 0.0
        risk_per_unit = a * self.cfg.STOP_K * self.cfg.VALUE_PER_POINT
        qty = (capital * self.cfg.RISK_PER_TRADE) / risk_per_unit
        return max(0.0, float(qty))

    def on_bar(self, bar: Dict[str,Any]):
        # On suppose que bind_prices a été appelé par le moteur avant run()
        i = bar["i"]
        if self.df is None:
            raise RuntimeError("bind_prices(df) doit être appelé avant run()")

        price = bar["close"]
        don_hi = self.df.loc[i, "don_hi"]
        don_lo = self.df.loc[i, "don_lo"]
        ema_ok = True if self.cfg.EMA_PERIOD == 0 else (price >= self.df.loc[i, "ema"])

        # Sortie trailing ATR (logique OR avec Donchian inverse)
        if self.pos_qty > 0:
            a = self.df.loc[i, "atr"]
            trail = price - self.cfg.TRAIL_K * a
            self.trailing = trail if self.trailing is None else max(self.trailing, trail)

            exit_by_trail = price <= (self.trailing or price)
            exit_by_don_inverse = price <= don_lo if pd.notna(don_lo) else False

            if exit_by_trail or exit_by_don_inverse:
                self.pos_qty = 0.0
                self.entry_price = None
                self.trailing = None
                return {"action":"EXIT","side":"LONG","qty":None}

        # Entrée breakout Donchian avec filtre EMA (optionnel)
        if self.pos_qty == 0 and pd.notna(don_hi) and ema_ok and price >= don_hi:
            q = self._sizing(price, i)
            if q > 0:
                self.pos_qty = q
                self.entry_price = price
                self.trailing = None
                return {"action":"ENTER","side":"LONG","qty":q}

        return None
