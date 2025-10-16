# data/downloader.py
# -*- coding: utf-8 -*-
"""
Orchestrateur de téléchargement OHLCV.
- Source-agnostique : prend une "datasource" avec une API: fetch_ohlc(symbol, timeframe, start, end) -> DataFrame
- Gère le chunking temporel, l'idempotence, et l'écriture locale via data/store.py (Parquet).
- Inclut des garde-fous (validation, tri, fusion sans doublons).

Dépendances : pandas, pyarrow (pour Parquet), data/store.py
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Tuple, Dict, Any, Callable
import pandas as pd

# Import local
from data.store import (
    build_series_path,
    write_series_parquet,
    read_series_parquet,
    normalize_ohlc_df,
    series_date_range,
)


# -------------------------
# Paramètres / Config
# -------------------------

@dataclass
class DownloadConfig:
    # Racine pour stocker les fichiers Parquet localement. Ex: "data_local"
    DATA_ROOT: str = "data_local"

    # Taille de chunk temporel (en jours) si start/end très larges.
    # Valeurs possibles : int >= 1 (ex: 30, 90, 180)
    CHUNK_DAYS: int = 120

    # Comportement d'écriture : "merge" = union sans doublons ; "overwrite" ; "append"
    WRITE_MODE: str = "merge"

    # Si True, tente d'éviter de re-télécharger la période déjà présente (lit la plage existante).
    SKIP_IF_UP_TO_DATE: bool = True


# -------------------------
# Fonctions utilitaires
# -------------------------

def _daterange_chunks(start: pd.Timestamp, end: pd.Timestamp, chunk_days: int):
    """Générateur de (chunk_start, chunk_end) inclusifs, tz-aware si possible."""
    cur = start
    step = pd.Timedelta(days=int(chunk_days))
    while cur <= end:
        nxt = min(cur + step, end)
        yield cur, nxt
        cur = nxt + pd.Timedelta(seconds=1)  # éviter recouvrement exact


# -------------------------
# API principale
# -------------------------

def download_ohlc(
    *,
    datasource: Any,
    symbol: str,
    timeframe: str,
    start: Any,
    end: Any,
    cfg: Optional[DownloadConfig] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Tuple[int, Tuple[pd.Timestamp, pd.Timestamp]]:
    """
    Télécharge les OHLCV pour (symbol, timeframe, [start, end]) depuis 'datasource',
    et écrit en Parquet (merge par défaut).

    Paramètres :
    - datasource : objet avec méthode fetch_ohlc(symbol, timeframe, start, end) -> DataFrame OHLCV
    - symbol (str)    : ex. "XAUUSD"
    - timeframe (str) : ex. "M1","M5","H1","H4","D1","W1" (selon datasource)
    - start/end       : pd.Timestamp compatible (str ISO, datetime, etc.)
    - cfg             : DownloadConfig (par défaut : merge, chunk=120j, skip_up_to_date=True)
    - metadata        : sidecar JSON (ex: {"provider":"oanda","note":"historical import"})

    Retour :
    - (nb_lignes_après_merge, (t_min, t_max)) dans le fichier Parquet.
    """
    cfg = cfg or DownloadConfig()
    path = build_series_path(cfg.DATA_ROOT, symbol, timeframe)

    # Normaliser timestamps (UTC si store.py param le force)
    start_ts = pd.to_datetime(start, utc=True)
    end_ts = pd.to_datetime(end, utc=True)
    if start_ts > end_ts:
        raise ValueError("start > end")

    # Si on veut éviter les re-téléchargements inutiles
    if cfg.SKIP_IF_UP_TO_DATE:
        rng = series_date_range(path)
        if rng is not None:
            t0, t1 = rng
            # Si la série couvre déjà la fenêtre demandée, on peut lire & sortir
            if t0 <= start_ts and t1 >= end_ts:
                df = read_series_parquet(path)
                return len(df), (df["time"].iloc[0], df["time"].iloc[-1])
            # Sinon, on télécharge uniquement la partie manquante :
            # - avant t0 si start < t0
            # - après t1 si end > t1
            # On traitera ça par chunks ci-dessous.

    # Téléchargement chunké
    total_rows = 0
    acc_df = None

    for chunk_start, chunk_end in _daterange_chunks(start_ts, end_ts, cfg.CHUNK_DAYS):
        # Optimisation : si SKIP_IF_UP_TO_DATE et on a rng existant, skipper les sous-plages déjà couvertes
        if cfg.SKIP_IF_UP_TO_DATE and rng is not None:
            t0, t1 = rng
            # Sous-plage intégralement incluse déjà -> skip
            if chunk_start >= t0 and chunk_end <= t1:
                continue

        # Fetch auprès de la datasource
        df_chunk = datasource.fetch_ohlc(symbol=symbol, timeframe=timeframe, start=chunk_start, end=chunk_end)
        if df_chunk is None or len(df_chunk) == 0:
            continue

        df_chunk = normalize_ohlc_df(df_chunk)
        total_rows += len(df_chunk)

        # Écriture au fil de l'eau (merge) pour robustness si beaucoup de chunks
        write_series_parquet(
            df_chunk,
            path,
            mode=cfg.WRITE_MODE,
            metadata=metadata or {"symbol": symbol, "timeframe": timeframe, "source": getattr(datasource, "NAME", "unknown")}
        )

    # Lecture finale pour report
    df_final = read_series_parquet(path)
    return len(df_final), (df_final["time"].iloc[0], df_final["time"].iloc[-1])
