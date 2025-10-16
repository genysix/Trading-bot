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

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Literal, Dict, Any, List, Tuple
import math

import pandas as pd
import numpy as np

from indicators.core import atr as ind_atr, donchian_high, donchian_low, ema as ind_ema


PositionSide = Literal["FLAT", "LONG", "SHORT"]


@dataclass
class TurtleParams:
    # ====== PARAMÈTRES GÉNÉRAUX ======

    # Risque par trade (fraction du capital). Valeurs possibles : float > 0.
    # Conseils pratique en réel : 0.005–0.02 (0.5%–2%). Pour tests agressifs : 0.05 (5%) possible.
    RISK_PER_TRADE: float = 0.05

    # Capital de base utilisé par le sizing (si l’engine ne pousse pas l’equity courante).
    # Valeurs possibles : float > 0. Ex : 1000.0
    BASE_CAPITAL: float = 1000.0

    # Effet de levier maximal logique (contrainte côté stratégie). Valeurs : float >= 1.0
    MAX_LEVERAGE: float = 2.0

    # Autoriser les positions SHORT. Valeurs : bool
    ALLOW_SHORT: bool = True

    # Timeframe indicatif (pour logs/rapports). Valeurs : "M1","M5","M15","H1","H4","D1","W1"
    TIMEFRAME: str = "D1"

    # Valeur monétaire par 1.0 de mouvement de prix *par unité de qty*.
    # Exemple conceptuel : si 1.0 de mouvement vaut 1 $ par unité, VALUE_PER_POINT = 1.0.
    # Adapte selon instrument (CFD, lot, contrat). Valeurs : float > 0.
    VALUE_PER_POINT: float = 1.0

    # Quantité minimale et maximale par ordre (garde-fous). Valeurs : float > 0, min <= max.
    MIN_QTY: float = 0.001
    MAX_QTY: float = 1e9  # tu ajusteras selon courtier/instrument

    # ====== INDICATEURS / TENDANCE ======

    # Longueur ATR (entier >= 1). Classiques : 14, 20, 30.
    ATR_LEN: int = 20

    # Longueur EMA pour filtre de tendance (entier >= 1). Ex : 100, 200, 300.
    EMA_TREND_LEN: int = 200

    # Activer filtre tendance EMA (True/False).
    # Si True : LONG seulement si close > EMA ; SHORT seulement si close < EMA.
    USE_TREND_FILTER: bool = True

    # ====== ENTRÉES BREAKOUT DONCHIAN ======

    # Fenêtre Donchian d'entrée (entier >= 2). Classiques : 20, 55.
    DONCHIAN_ENTRY_X: int = 20

    # Confirmer les entrées uniquement sur clôture au-dessus/au-dessous du canal ? (True/False)
    # True = confirme à la clôture ; False = signal intrabar (plus agressif).
    CONFIRM_ON_CLOSE: bool = True

    # ====== STOPS & SORTIES ======

    # Stop initial = STOP_K * ATR (float > 0). Ex : 1.0–2.0. Plus grand = stop plus large.
    STOP_K: float = 1.0

    # Activer le Trailing ATR (True/False). Si True, stop suiveur à TRAIL_K * ATR.
    USE_TRAIL_ATR: bool = True

    # Multiple du Trailing Stop ATR. Float > 0. Ex : 1.5, 2.0, 2.5, 3.0
    TRAIL_K: float = 2.5

    # Activer la sortie Donchian inverse (True/False). Si True : sortie quand close casse le canal opposé (Y).
    USE_DONCHIAN_EXIT: bool = True

    # Fenêtre Donchian de sortie inverse (entier >= 2). Souvent 10–20 (peut différer de X).
    DONCHIAN_EXIT_Y: int = 20

    # ====== PYRAMIDING ======

    # Nombre d’ajouts (unités supplémentaires) au maximum après l’entrée initiale. Entier >= 0.
    # Ex : 0 (désactivé), 1–4 (classique Turtle).
    PYRAMID_UNITS: int = 0

    # Pas d’ajout en ATR : à chaque mouvement favorable de (PYRAMID_STEP_ATR * ATR), on ajoute 1 unité.
    # Valeurs : float > 0. Ex : 0.5, 1.0.
    PYRAMID_STEP_ATR: float = 0.5

    # ====== COÛTS (placeholders) ======

    # Slippage moyen par trade (en unités de prix). Ici utilisé seulement comme info/trace possible.
    SLIPPAGE_PER_TICK: float = 0.5

    # Commission fixe par trade (info/trace — l’engine la gère réellement).
    COMMISSION_PER_TRADE: float = 0.0

    # ====== CONTRÔLE ======

    # Validation stricte : si True, on lève en cas d’incohérence ; sinon on corrige au mieux.
    STRICT_VALIDATION: bool = True

    def validate(self) -> None:
        """Validation/coercition défensive des paramètres."""
        def _err(msg: str):
            if self.STRICT_VALIDATION:
                raise ValueError(msg)

        for name in ("RISK_PER_TRADE","BASE_CAPITAL","MAX_LEVERAGE","VALUE_PER_POINT",
                     "MIN_QTY","MAX_QTY","STOP_K","TRAIL_K","SLIPPAGE_PER_TICK","COMMISSION_PER_TRADE"):
            val = getattr(self, name)
            if not isinstance(val, (int, float)):
                _err(f"{name} doit être numérique.")
                continue
            if name in ("RISK_PER_TRADE","BASE_CAPITAL","VALUE_PER_POINT","MIN_QTY","STOP_K","TRAIL_K"):
                if val <= 0: _err(f"{name} doit être > 0.")
            if name == "MAX_LEVERAGE" and val < 1.0:
                _err("MAX_LEVERAGE doit être >= 1.0")
            if name == "SLIPPAGE_PER_TICK" and val < 0:
                _err("SLIPPAGE_PER_TICK doit être >= 0.")
            if name == "COMMISSION_PER_TRADE" and val < 0:
                _err("COMMISSION_PER_TRADE doit être >= 0.")

        for name in ("ATR_LEN","EMA_TREND_LEN","DONCHIAN_ENTRY_X","DONCHIAN_EXIT_Y","PYRAMID_UNITS"):
            val = getattr(self, name)
            if not isinstance(val, int) or val < (2 if "DONCHIAN" in name else 1):
                _err(f"{name} doit être un entier valide (>=2 pour Donchian, sinon >=1).")

        if self.MIN_QTY > self.MAX_QTY:
            _err("MIN_QTY ne doit pas être > MAX_QTY")

        if not isinstance(self.USE_TREND_FILTER, bool): _err("USE_TREND_FILTER doit être bool.")
        if not isinstance(self.USE_TRAIL_ATR, bool):    _err("USE_TRAIL_ATR doit être bool.")
        if not isinstance(self.USE_DONCHIAN_EXIT, bool): _err("USE_DONCHIAN_EXIT doit être bool.")
        if not isinstance(self.ALLOW_SHORT, bool):       _err("ALLOW_SHORT doit être bool.")
        if not isinstance(self.CONFIRM_ON_CLOSE, bool):  _err("CONFIRM_ON_CLOSE doit être bool.")


class TurtleLikeStrategy:
    """
    Stratégie Turtle-like v1
    - Calcule ATR/EMA/Donchian via indicators.core
    - Gère entrées, sizing, stops, pyramiding et sorties (F6)
    """

    def __init__(self, params: Optional[TurtleParams] = None):
        self.params = params or TurtleParams()
        self.params.validate()

        # Tampon historique
        self._bars: List[Dict[str, Any]] = []
        self._df: Optional[pd.DataFrame] = None

        # État de position
        self.position: PositionSide = "FLAT"
        self.entry_price: Optional[float] = None
        self.stop_price: Optional[float] = None
        self.qty: float = 0.0

        # Pyramiding
        self.added_units: int = 0
        self.next_add_price: Optional[float] = None  # prix seuil pour prochain ajout

        # Reporting
        self.closed_trades: List[Dict[str, Any]] = []

    # -----------------------
    # API publique
    # -----------------------

    def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        self._append_bar(bar)
        if self._df is None or len(self._df) < max(self.params.ATR_LEN,
                                                   self.params.DONCHIAN_ENTRY_X,
                                                   self.params.DONCHIAN_EXIT_Y) + 2:
            return None

        self._compute_indicators()

        # 1) Sorties (si position ouverte) — logique OR (ATR trail OU Donchian inverse)
        exit_order = self._maybe_exit()
        if exit_order is not None:
            return exit_order

        # 2) Pyramiding (si position ouverte et autorisé)
        add_order = self._maybe_pyramid()
        if add_order is not None:
            return add_order

        # 3) Entrées (si FLAT)
        if self.position == "FLAT":
            enter_order = self._maybe_enter()
            if enter_order is not None:
                return enter_order

        return None

    # -----------------------
    # Indicateurs & DF
    # -----------------------

    def _append_bar(self, bar: Dict[str, Any]) -> None:
        for k in ("time","open","high","low","close"):
            if k not in bar:
                raise KeyError(f"Bar manquante clé obligatoire : {k}")
        self._bars.append(bar)
        self._df = None  # recalcul lazy

    def _compute_indicators(self) -> None:
        if self._df is not None:
            return
        df = pd.DataFrame(self._bars)
        for c in ("open","high","low","close"):
            df[c] = pd.to_numeric(df[c], errors="coerce")

        # ATR
        df["atr"] = ind_atr(df["high"], df["low"], df["close"], window=self.params.ATR_LEN)

        # EMA filtre tendance
        if self.params.USE_TREND_FILTER:
            df["ema_trend"] = ind_ema(df["close"], length=self.params.EMA_TREND_LEN)
        else:
            df["ema_trend"] = np.nan

        # Donchian entrée/sortie
        X = self.params.DONCHIAN_ENTRY_X
        Y = self.params.DONCHIAN_EXIT_Y
        df[f"donch_high_{X}"] = donchian_high(df["high"], window=X)
        df[f"donch_low_{X}"]  = donchian_low(df["low"], window=X)
        df[f"donch_high_{Y}"] = donchian_high(df["high"], window=Y)
        df[f"donch_low_{Y}"]  = donchian_low(df["low"], window=Y)

        self._df = df

    # -----------------------
    # Entrées
    # -----------------------

    def _maybe_enter(self) -> Optional[Dict[str, Any]]:
        last = self._df.iloc[-1]
        prev = self._df.iloc[-2]  # pour confirmer sur clôture précédente si besoin

        close = float(last["close"])
        atr = float(last["atr"]) if not math.isnan(last["atr"]) else None
        if atr is None or atr <= 0:
            return None

        X = self.params.DONCHIAN_ENTRY_X
        dhX = float(last[f"donch_high_{X}"]) if not math.isnan(last[f"donch_high_{X}"]) else None
        dlX = float(last[f"donch_low_{X}"])  if not math.isnan(last[f"donch_low_{X}"])  else None

        ema_ok_long = True
        ema_ok_short = True
        if self.params.USE_TREND_FILTER:
            ema = float(last["ema_trend"]) if not math.isnan(last["ema_trend"]) else None
            if ema is None:
                return None
            ema_ok_long  = close > ema
            ema_ok_short = close < ema

        # Détection du signal : au close (confirmé) ou intrabar
        def breakout_long() -> bool:
            if dhX is None: return False
            if self.params.CONFIRM_ON_CLOSE:
                # On exige que la (bar - 1) ait clôturé > dhX_prev (plus strict). Simpli : on check current close > dhX
                return close > dhX
            else:
                # Intrabar : on pourrait utiliser le high courant ; ici on reste au close pour simplicité stable
                return close > dhX

        def breakout_short() -> bool:
            if dlX is None: return False
            if self.params.CONFIRM_ON_CLOSE:
                return close < dlX
            else:
                return close < dlX

        # Essai LONG
        if ema_ok_long and breakout_long():
            qty, stop_init = self._compute_qty_and_stop(side="LONG", entry_price=close, atr=atr)
            if qty <= 0:
                return None
            self._enter_position("LONG", entry_price=close, qty=qty, atr=atr, stop_init=stop_init)
            return {"action":"ENTER","side":"LONG","qty":qty,"price":close,"time":self._df.iloc[-1]["time"]}

        # Essai SHORT
        if self.params.ALLOW_SHORT and ema_ok_short and breakout_short():
            qty, stop_init = self._compute_qty_and_stop(side="SHORT", entry_price=close, atr=atr)
            if qty <= 0:
                return None
            self._enter_position("SHORT", entry_price=close, qty=qty, atr=atr, stop_init=stop_init)
            return {"action":"ENTER","side":"SHORT","qty":qty,"price":close,"time":self._df.iloc[-1]["time"]}

        return None

    def _compute_qty_and_stop(self, *, side: PositionSide, entry_price: float, atr: float) -> Tuple[float, float]:
        """
        Taille = (capital * RISK%) / (STOP_K * ATR * VALUE_PER_POINT)
        Stop initial :
          LONG  : entry - STOP_K * ATR
          SHORT : entry + STOP_K * ATR
        """
        # capital courant approximé
        capital = float(self.params.BASE_CAPITAL)

        denom = max(1e-12, self.params.STOP_K * atr * self.params.VALUE_PER_POINT)
        raw_qty = (capital * self.params.RISK_PER_TRADE) / denom

        # bornes
        qty = max(self.params.MIN_QTY, min(raw_qty, self.params.MAX_QTY))

        if side == "LONG":
            stop_init = entry_price - self.params.STOP_K * atr
        else:
            stop_init = entry_price + self.params.STOP_K * atr

        return qty, stop_init

    def _enter_position(self, side: PositionSide, *, entry_price: float, qty: float, atr: float, stop_init: float) -> None:
        self.position = side
        self.entry_price = float(entry_price)
        self.qty = float(qty)

        # Stop de travail (initial) ; pourra être relevé par trailing
        self.stop_price = float(stop_init)

        # Init pyramiding
        self.added_units = 0
        self.next_add_price = self._compute_next_add_price(side, entry_price, atr)

    # -----------------------
    # Pyramiding
    # -----------------------

    def _compute_next_add_price(self, side: PositionSide, ref_price: float, atr: float) -> Optional[float]:
        if self.params.PYRAMID_UNITS <= 0:
            return None
        step = self.params.PYRAMID_STEP_ATR
        if step <= 0 or atr <= 0:
            return None
        if side == "LONG":
            return ref_price + step * atr
        elif side == "SHORT":
            return ref_price - step * atr
        return None

    def _maybe_pyramid(self) -> Optional[Dict[str, Any]]:
        if self.position == "FLAT" or self.params.PYRAMID_UNITS <= 0:
            return None

        last = self._df.iloc[-1]
        close = float(last["close"])
        atr = float(last["atr"]) if not math.isnan(last["atr"]) else None
        if atr is None or atr <= 0:
            return None

        if self.added_units >= self.params.PYRAMID_UNITS:
            return None

        if self.next_add_price is None:
            return None

        # Condition : prix a parcouru +step ATR (LONG) / -step ATR (SHORT) par rapport au dernier add
        if self.position == "LONG" and close >= self.next_add_price:
            # Ajout d'une unité de la même taille que l'initiale (simple). Option : fraction de l'initiale.
            add_qty = self.qty  # même taille — ajuste si tu veux un escalier
            self.added_units += 1
            self.next_add_price = self._compute_next_add_price("LONG", self.next_add_price, atr)
            return {"action":"ENTER","side":"LONG","qty":add_qty,"price":close,"time":last["time"],"reason":"PYRAMID"}

        if self.position == "SHORT" and close <= self.next_add_price:
            add_qty = self.qty
            self.added_units += 1
            self.next_add_price = self._compute_next_add_price("SHORT", self.next_add_price, atr)
            return {"action":"ENTER","side":"SHORT","qty":add_qty,"price":close,"time":last["time"],"reason":"PYRAMID"}

        return None

    # -----------------------
    # Sorties (Trailing ATR + Donchian inverse) — logique OR
    # -----------------------

    def _maybe_exit(self) -> Optional[Dict[str, Any]]:
        if self.position == "FLAT":
            return None

        last = self._df.iloc[-1]
        close = float(last["close"])
        atr = float(last["atr"]) if not math.isnan(last["atr"]) else None
        if atr is None or atr <= 0:
            return None

        exit_by_atr = False
        exit_by_donch = False

        # Trailing ATR
        if self.params.USE_TRAIL_ATR:
            if self.position == "LONG":
                candidate = close - self.params.TRAIL_K * atr
                self.stop_price = max(self.stop_price or -np.inf, candidate)
                if close <= self.stop_price:
                    exit_by_atr = True
            elif self.position == "SHORT":
                candidate = close + self.params.TRAIL_K * atr
                self.stop_price = min(self.stop_price or np.inf, candidate)
                if close >= self.stop_price:
                    exit_by_atr = True

        # Donchian inverse (sur clôture)
        if self.params.USE_DONCHIAN_EXIT:
            Y = self.params.DONCHIAN_EXIT_Y
            if self.position == "LONG":
                dlow = float(last[f"donch_low_{Y}"]) if not math.isnan(last[f"donch_low_{Y}"]) else None
                if dlow is not None and close < dlow:
                    exit_by_donch = True
            elif self.position == "SHORT":
                dhigh = float(last[f"donch_high_{Y}"]) if not math.isnan(last[f"donch_high_{Y}"]) else None
                if dhigh is not None and close > dhigh:
                    exit_by_donch = True

        if exit_by_atr or exit_by_donch:
            reason = "TRAIL_ATR" if exit_by_atr else "DONCHIAN_INVERSE"
            order = {
                "action":"EXIT",
                "reason": reason,
                "position": self.position,
                "qty": self.qty,
                "stop_price": self.stop_price,
                "price": close,
                "time": last["time"]
            }
            # Reset état
            self.position = "FLAT"
            self.entry_price = None
            self.stop_price = None
            self.qty = 0.0
            self.added_units = 0
            self.next_add_price = None
            return order

        return None
    