# indicators/ema.py
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

def ema(close, length: int = 200, adjust: bool = False) -> pd.Series:
    """
    EMA (Exponential Moving Average) de 'close'.

    Paramètres :
    - length (int >= 1) : période de l'EMA. Classiques : 50, 100, 200, 300.
      * Valeurs possibles : entier >= 1. Plus grand => tendance plus “lente/robuste”.
    - adjust (bool) : paramètre pandas ewm(). False = pondération récursive standard.

    Retour :
    - pd.Series 'ema_{length}' alignée à 'close'.

    Remarques :
    - Les premières valeurs seront NaN jusqu’à accumuler assez d’historique effectif.
    """
    l = _validate_window(length, "length")
    c = _ensure_series(close, name="close")
    out = c.ewm(span=l, adjust=adjust).mean()
    out.name = f"ema_{l}"
    return out