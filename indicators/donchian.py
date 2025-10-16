# indicators/donchian.py
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


def donchian_high(high, window: int = 20, min_periods: Optional[int] = None) -> pd.Series:
    """
    Donchian high = maximum des 'high' sur 'window' barres.

    Paramètres :
    - window (int >= 1) : longueur de la fenêtre. Classiques : 10, 20, 55.
    - min_periods : si None => min_periods = window.

    Retour :
    - pd.Series 'donch_high_{window}'.
    """
    w = _validate_window(window, "window")
    mp = w if min_periods is None else int(min_periods)
    h = _ensure_series(high, name="high")
    out = h.rolling(window=w, min_periods=mp).max()
    out.name = f"donch_high_{w}"
    return out


def donchian_low(low, window: int = 20, min_periods: Optional[int] = None) -> pd.Series:
    """
    Donchian low = minimum des 'low' sur 'window' barres.

    Paramètres :
    - window (int >= 1) : longueur de la fenêtre. Classiques : 10, 20, 55.
    - min_periods : si None => min_periods = window.

    Retour :
    - pd.Series 'donch_low_{window}'.
    """
    w = _validate_window(window, "window")
    mp = w if min_periods is None else int(min_periods)
    l = _ensure_series(low, name="low")
    out = l.rolling(window=w, min_periods=mp).min()
    out.name = f"donch_low_{w}"
    return out