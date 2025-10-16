# data/resampling.py
# -*- coding: utf-8 -*-
"""
Resampling OHLCV : agrège une série intraday (ex. M1) vers M5/M15/H1/H4/D1, etc.

Fonctions principales :
- resample_ohlc(df, rule, *, tz='UTC', label='right', closed='right')
- upsample_fill(df, rule) [optionnel, pour aligner à un calendrier plus fin avec forward-fill]

Conventions & attentes :
- df contient au minimum : ["time","open","high","low","close"], optionnel "volume"
- df est normalisé (time trié croissant, tz-aware de préférence)
- rule est une règle pandas ("5T","15T","1H","4H","1D","1W")

Notes :
- Pour OHLC : O=first, H=max, L=min, C=last
- Pour volume : somme
- Les périodes fermées à droite (closed='right') + label='right' sont standards pour chandeliers 
  (la barre timestampée à 10:00 couvre (9:00,10:00]).
"""

from __future__ import annotations
from typing import Optional
import pandas as pd


# --- Paramètres par défaut du module -----------------------------------------

# Timezone par défaut pour index temporel en sortie (si df['time'] est naïf)
DEFAULT_TZ = "UTC"

# Label/Closed par défaut pour resample (valeurs standard pour chandeliers)
# label : "right" => l'étiquette de la barre est la fin de l’intervalle
# closed: "right" => l'intervalle est du type (t-Δ, t]
DEFAULT_LABEL = "right"
DEFAULT_CLOSED = "right"


# --- Helpers -----------------------------------------------------------------

def _ensure_datetime_index(df: pd.DataFrame, tz: Optional[str] = DEFAULT_TZ) -> pd.DataFrame:
    """Assure un DatetimeIndex sur df, à partir de la colonne 'time'. Convertit en tz si nécessaire."""
    if "time" not in df.columns:
        raise ValueError("DataFrame doit contenir la colonne 'time' pour resampling.")
    out = df.copy()
    dt = pd.to_datetime(out["time"], utc=(tz is not None))
    if tz:
        if dt.dt.tz is None:
            dt = dt.dt.tz_localize(tz)
        else:
            dt = dt.dt.tz_convert(tz)
    out = out.set_index(dt)
    out.index.name = "time"
    return out


def _resample_agg_dict(has_volume: bool) -> dict:
    """Retourne le dict d'agrégation pour OHLCV selon présence de 'volume'."""
    agg = {
        "open":  "first",
        "high":  "max",
        "low":   "min",
        "close": "last",
    }
    if has_volume:
        agg["volume"] = "sum"
    return agg


# --- API principale -----------------------------------------------------------

def resample_ohlc(
    df: pd.DataFrame,
    rule: str,
    *,
    tz: Optional[str] = DEFAULT_TZ,
    label: str = DEFAULT_LABEL,
    closed: str = DEFAULT_CLOSED,
    dropna: bool = True
) -> pd.DataFrame:
    """
    Agrège un DataFrame OHLC(V) selon la règle pandas 'rule'.

    Paramètres :
    - rule (str) : règles pandas ("5T","15T","1H","4H","1D","1W")
        * Valeurs possibles : toute string compatible pandas.DateOffset
    - tz (str|None) : timezone pour index. Si None, conserve tz existante.
    - label (str)  : "left" ou "right" (étiquette de la barre)
    - closed (str) : "left" ou "right" (côté fermé de l’intervalle)
    - dropna (bool): supprime les barres avec NaN sur OHLC (souvent causé par trous)

    Retour :
    - DataFrame resamplé avec colonnes ["time","open","high","low","close","volume?"]
    """
    if not {"time","open","high","low","close"}.issubset(df.columns):
        raise ValueError("Colonnes OHLC requises manquantes.")

    has_vol = "volume" in df.columns
    agg = _resample_agg_dict(has_vol)

    x = _ensure_datetime_index(df, tz=tz)
    rs = x.resample(rule, label=label, closed=closed).agg(agg)

    # Nettoyage : certaines fenêtres vides produisent des NaN
    if dropna:
        rs = rs.dropna(subset=["open","high","low","close"], how="any")

    # Re-projeter 'time' en colonne pour rester cohérent avec le reste du projet
    rs = rs.reset_index()
    return rs


def upsample_fill(
    df: pd.DataFrame,
    rule: str,
    *,
    tz: Optional[str] = DEFAULT_TZ,
    method: str = "ffill"
) -> pd.DataFrame:
    """
    Aligne la série sur une grille temporelle plus fine (ex. D1 -> H1) en remplissant (ffill).
    Utile pour aligner plusieurs séries sur le même calendrier. 
    Ne crée pas d'OHLC synthétique pertinent pour le trading (à utiliser avec prudence).

    Paramètres :
    - rule (str) : règle pandas ("1T","5T","1H", etc.)
    - method (str): méthode de remplissage ("ffill","bfill")

    Retour :
    - DataFrame aligné avec 'time' en colonne.
    """
    x = _ensure_datetime_index(df, tz=tz).copy()
    # On ne peut pas "agréger" des OHLC à l'upsample ; on remplit les champs (ex. close) si besoin
    # Ici on remplit toutes colonnes par ffill/bfill
    rs = x.resample(rule).asfreq()
    rs = rs.fillna(method=method)
    rs = rs.reset_index()
    return rs
# --- Fin du module -----------------------------------------------------------