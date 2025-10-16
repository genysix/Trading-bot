# indicators/atr.py
# -*- coding: utf-8 -*-
"""
Indicateurs techniques de base (purs, sans dépendances projet) :

Notes :
- Tous les indicateurs retournent un pd.Series aligné à l'index d'entrée.
- Validation défensive : longueurs >= 1, types numériques, etc.
- min_periods = window (par défaut) => NaN jusqu’à disposer d’assez d’historique.
"""

from __future__ import annotations
from typing import Optional
import pandas as pd
import numpy as np


def true_range(high, low, close) -> pd.Series:
    """
    Calcule le True Range bar-par-bar.

    Paramètres :
    - high : Série des plus hauts (pd.Series ou array-like)
    - low  : Série des plus bas  (pd.Series ou array-like)
    - close: Série des clôtures  (pd.Series ou array-like)

    Retour :
    - pd.Series du True Range, alignée à l'index de 'close'

    Hypothèses :
    - Les séries ont la même longueur et le même index (si Series).
    """
    h = _ensure_series(high, name="high")
    l = _ensure_series(low, name="low")
    c = _ensure_series(close, name="close")

    prev_close = c.shift(1)
    tr1 = h - l
    tr2 = (h - prev_close).abs()
    tr3 = (l - prev_close).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    tr.name = "true_range"
    return tr


def atr(high, low, close, window: int = 14, min_periods: Optional[int] = None) -> pd.Series:
    """
    ATR (Average True Range) = moyenne du True Range sur 'window' barres.

    Paramètres :
    - window (int >= 1) : longueur de lissage. Classiques : 14, 20, 30.
    - min_periods (int|None) : nb mini d'observations pour produire une valeur.
        * Si None : min_periods = window (comportement le plus sûr).
        * Valeurs possibles : int >= 1 et <= window (ou > window si tu veux des NaN prolongés).

    Retour :
    - pd.Series 'atr' alignée aux entrées.

    Remarques :
    - Utilise une moyenne mobile simple (SMA). Si tu veux une RMA/Wilder, on peut l’ajouter.
    """
    w = _validate_window(window, "window")
    mp = w if min_periods is None else int(min_periods)
    if mp < 1:
        raise ValueError("min_periods doit être >= 1")
    tr = true_range(high, low, close)
    out = tr.rolling(window=w, min_periods=mp).mean()
    out.name = f"atr_{w}"
    return out