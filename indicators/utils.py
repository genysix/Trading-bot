# indicators/utils.py
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

# --- Utils internes -----------------------------------------------------------

def _ensure_series(x, name: Optional[str] = None) -> pd.Series:
    """
    Convertit x en pd.Series si nécessaire et assure un dtype float.
    """
    if isinstance(x, pd.Series):
        s = x.copy()
    else:
        s = pd.Series(x, name=name)
    s = pd.to_numeric(s, errors="coerce")
    return s


def _validate_window(window: int, var_name: str = "window") -> int:
    """
    Valide qu'une fenêtre est un entier >= 1, sinon lève ValueError.
    """
    if not isinstance(window, int) or window < 1:
        raise ValueError(f"{var_name} doit être un entier >= 1 (reçu: {window})")
    return window
