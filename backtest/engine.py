# backtest/engine.py
# -*- coding: utf-8 -*-
"""
Moteur minimal de backtest (bar-by-bar) pour stratégies "événementielles".
- Feed un DataFrame OHLC à la stratégie (on_bar).
- Exécute les ordres que la stratégie renvoie (ENTER/EXIT).
- Paramètre le timing d'exécution: au close courant OU à l'open de la prochaine barre.
- Applique slippage absolu et commission fixe.
- Enregistre les trades et calcule un PnL simple (sans levier ni valeur de point=1.0 par défaut).

A intégrer avec strategies/turtle_like.py (déjà fourni).
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Literal, Optional, Dict, Any, List
import pandas as pd
import math


ExecutionTiming = Literal["close", "next_open"]


@dataclass
class EngineConfig:
    # --- QUAND EXÉCUTER LES ORDRES ---
    # "close"      : exécute au close de la barre courante (risque de look-ahead si la stratégie utilise ce close pour décider)
    # "next_open"  : exécute à l'open de la barre suivante (recommandé pour éviter look-ahead)
    EXECUTION_TIMING: ExecutionTiming = "next_open"

    # --- SLIPPAGE ---
    # Slippage absolu en unités de prix (float >= 0). Ex: 0.5 => on dégrade le prix d'exécution de 0.5.
    # NB: c'est volontairement simple. On branchera plus tard un modèle par "tick" ou proportionnel à l'ATR.
    SLIPPAGE_ABS: float = 0.5

    # --- COMMISSIONS ---
    # Commission fixe par trade (entrée ou sortie). float >= 0.
    COMMISSION_FIXED: float = 0.0

    # --- CAPITAL / QTY ---
    # Capital de départ (affiché pour info ; le sizing réel sera géré par la stratégie plus tard).
    INITIAL_CAPITAL: float = 1000.0

    # Quantité par défaut si la stratégie ne la fournit pas (placeholder).
    DEFAULT_QTY: float = 1.0

    # Valeur du point (multiplier de PnL). Par défaut 1.0 ; à ajuster selon instrument (ex: futures).
    POINT_VALUE: float = 1.0

    # Autoriser les shorts (placeholder : l'engine ne crée pas d'ordres lui-même, mais on garde l'option pour la suite).
    ALLOW_SHORT: bool = True


@dataclass
class PositionState:
    side: Literal["FLAT", "LONG", "SHORT"] = "FLAT"
    entry_price: Optional[float] = None
    qty: float = 0.0  # positive (unités, non notionnel)
    # Pour reporting
    entry_time: Optional[Any] = None


@dataclass
class Trade:
    symbol: str
    side: Literal["LONG", "SHORT"]
    qty: float
    entry_time: Any
    entry_price: float
    exit_time: Any
    exit_price: float
    pnl: float  # en "monnaie" = (exit-entry)*dir*qty*POINT_VALUE - commissions_totales
    reason: str  # raison de sortie (ex: TRAIL_ATR, DONCHIAN_INVERSE, MANUAL, etc.)


class BacktestEngine:
    """
    BacktestEngine
    --------------
    - run(strategy, df, symbol="XAUUSD")
    - Retourne un dict de résultats (trades, equity simple, stats de base).
    """

    def __init__(self, config: Optional[EngineConfig] = None):
        self.cfg = config or EngineConfig()

        # État runtime
        self.position = PositionState()
        self.trades: List[Trade] = []
        self.equity_curve: List[Dict[str, Any]] = []

        # Sanity checks
        if self.cfg.SLIPPAGE_ABS < 0:
            raise ValueError("SLIPPAGE_ABS doit être >= 0")
        if self.cfg.COMMISSION_FIXED < 0:
            raise ValueError("COMMISSION_FIXED doit être >= 0")
        if self.cfg.DEFAULT_QTY <= 0:
            raise ValueError("DEFAULT_QTY doit être > 0")
        if self.cfg.POINT_VALUE <= 0:
            raise ValueError("POINT_VALUE doit être > 0")

    def run(self, strategy, df: pd.DataFrame, symbol: str = "XAUUSD") -> Dict[str, Any]:
        """
        Exécute un backtest simple.
        df: DataFrame avec colonnes au minimum ["time","open","high","low","close"] ordonnées dans le temps.
        """
        self._validate_df(df)
        capital = float(self.cfg.INITIAL_CAPITAL)

        # On parcourt bar par bar
        n = len(df)
        for i in range(n):
            bar = self._row_to_bar(df.iloc[i])

            # Feed la stratégie
            order = strategy.on_bar(bar)

            # Exécuter l'ordre s'il y en a un
            if order is not None and isinstance(order, dict) and "action" in order:
                # Détermine le prix d'exécution selon timing
                exec_index = i
                exec_field = "close"
                if self.cfg.EXECUTION_TIMING == "next_open":
                    if i + 1 < n:
                        exec_index = i + 1
                        exec_field = "open"  # on exécute à l'open suivant
                    else:
                        # Pas de barre suivante : on exécute au close courant
                        exec_index = i
                        exec_field = "close"

                fill_price = float(df.iloc[exec_index][exec_field])

                # Slippage simple : on détériore le prix côté "achat" vs "vente"
                # Conventions:
                # - ENTER LONG / EXIT SHORT : on "paie" => prix + slippage
                # - ENTER SHORT / EXIT LONG : on "reçoit" => prix - slippage
                action = order["action"].upper()
                reason = order.get("reason", "NA")

                if action == "ENTER":
                    side = order.get("side", "").upper()
                    qty = float(order.get("qty", self.cfg.DEFAULT_QTY))
                    if qty <= 0:
                        qty = self.cfg.DEFAULT_QTY

                    if side == "LONG":
                        px = fill_price + self.cfg.SLIPPAGE_ABS
                        self._enter_long(px, qty, df.iloc[exec_index]["time"])
                        # Commission sur entrée
                        capital -= self.cfg.COMMISSION_FIXED

                    elif side == "SHORT":
                        if not self.cfg.ALLOW_SHORT:
                            pass  # ignorer ou lever une erreur selon politique
                        else:
                            px = fill_price - self.cfg.SLIPPAGE_ABS
                            self._enter_short(px, qty, df.iloc[exec_index]["time"])
                            capital -= self.cfg.COMMISSION_FIXED

                elif action == "EXIT":
                    # Si on n'a pas de position, ignorer
                    if self.position.side == "FLAT":
                        continue

                    if self.position.side == "LONG":
                        px = fill_price - self.cfg.SLIPPAGE_ABS
                        pnl = (px - self.position.entry_price) * self.position.qty * self.cfg.POINT_VALUE
                        # Commission sur sortie
                        pnl -= self.cfg.COMMISSION_FIXED
                        capital += pnl
                        self._close_trade(symbol, px, df.iloc[exec_index]["time"], pnl, reason)

                    elif self.position.side == "SHORT":
                        px = fill_price + self.cfg.SLIPPAGE_ABS
                        pnl = (self.position.entry_price - px) * self.position.qty * self.cfg.POINT_VALUE
                        pnl -= self.cfg.COMMISSION_FIXED
                        capital += pnl
                        self._close_trade(symbol, px, df.iloc[exec_index]["time"], pnl, reason)

            # Equity snapshot (simple : capital + PnL latent non compté ici)
            self.equity_curve.append({
                "time": df.iloc[i]["time"],
                "equity": capital
            })

        return {
            "trades": self.trades,
            "equity_curve": self.equity_curve,
            "final_equity": capital,
            "nb_trades": len(self.trades),
            "symbol": symbol,
            "execution_timing": self.cfg.EXECUTION_TIMING,
            "slippage_abs": self.cfg.SLIPPAGE_ABS,
            "commission_fixed": self.cfg.COMMISSION_FIXED
        }

    # -----------------------
    # Helpers internes
    # -----------------------

    def _validate_df(self, df: pd.DataFrame) -> None:
        required = {"time", "open", "high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"DataFrame manquant colonnes: {missing}")
        if not df.index.is_monotonic_increasing:
            df = df.sort_index()  # on pourrait trier, mais je préfère prévenir
        # Vérifier ordonnancement temporel: on suppose croissant
        # (optionnel: test strict avec assert)

    @staticmethod
    def _row_to_bar(row: pd.Series) -> Dict[str, Any]:
        return {
            "time": row["time"],
            "open": float(row["open"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "close": float(row["close"]),
            "volume": float(row["volume"]) if "volume" in row and not pd.isna(row["volume"]) else 0.0
        }

    def _enter_long(self, price: float, qty: float, t) -> None:
        # Fermer short si ouvert (flat policy) puis ouvrir long
        if self.position.side == "SHORT":
            # Forcer fermeture avant inversion (sans enregistrer trade, car c'est géré par EXIT)
            # Ici on suppose que l'ordre EXIT viendra de la stratégie ; on évite les survites.
            pass

        self.position.side = "LONG"
        self.position.entry_price = price
        self.position.qty = qty
        self.position.entry_time = t

    def _enter_short(self, price: float, qty: float, t) -> None:
        if self.position.side == "LONG":
            pass
        self.position.side = "SHORT"
        self.position.entry_price = price
        self.position.qty = qty
        self.position.entry_time = t

    def _close_trade(self, symbol: str, exit_price: float, t, pnl: float, reason: str) -> None:
        tr = Trade(
            symbol=symbol,
            side=self.position.side,  # LONG ou SHORT
            qty=self.position.qty,
            entry_time=self.position.entry_time,
            entry_price=float(self.position.entry_price),
            exit_time=t,
            exit_price=float(exit_price),
            pnl=float(pnl),
            reason=reason
        )
        self.trades.append(tr)
        # Reset position
        self.position = PositionState()
