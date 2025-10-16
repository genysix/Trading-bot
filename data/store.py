# data/store.py
# -*- coding: utf-8 -*-
"""
Gestion locale des séries OHLCV :
- Format principal : Parquet (pyarrow) pour performance & compaction.
- Fonctions : normaliser/valider un DataFrame OHLCV, lire/écrire, fusionner sans doublons,
  filtrer par dates, utilitaires de chemins (root/symbol/timeframe), sidecar metadata.

Dépendances :
    pip install pandas pyarrow

Conventions :
- Colonnes minimales attendues : ["time","open","high","low","close"]
- Facultatives : ["volume"] (float ou int)
- 'time' en tz-aware UTC (recommandé) ou naïf (mais normalisé de façon cohérente).
- DataFrame trié strictement par 'time' croissant, sans doublon de timestamps.

Robustesse :
- Validation défensive (types/NaN/ordres des OHLC, duplication).
- Écriture atomique (fichier temporaire + os.replace).
- Mode 'append' / 'overwrite' / 'merge' (merge = union sans doublons avec tri).

Note :
- La valeur/échelle du 'price tick' n'est pas gérée ici (c'est du stockage brut).
"""

from __future__ import annotations
import os
import json
import tempfile
from typing import Optional, Iterable, Tuple, Dict, Any, List, Literal

import pandas as pd

# ---------------------------------------------------------------------------
# Paramètres module (facilement modifiables)
# ---------------------------------------------------------------------------

# Répertoire racine par défaut pour les données locales (modifiable à l'appel)
# Valeurs possibles : str (chemin existant ou à créer).
DEFAULT_DATA_ROOT = "data_local"

# Extension des fichiers de série (ici parquet). Valeurs possibles : "parquet"
SERIES_EXT = "parquet"

# Si True, on force 'time' en timezone UTC. Sinon, on laisse tel quel.
# Valeurs possibles : bool
FORCE_TIMEZONE_UTC = True

# Si True, on supprime/ignore les lignes invalides (NaN majeurs) au lieu d'échouer.
# Valeurs possibles : bool
LENIENT_DROP_BAD_ROWS = False


# ---------------------------------------------------------------------------
# Utilitaires de chemin
# ---------------------------------------------------------------------------

def build_series_path(root: str,
                      symbol: str,
                      timeframe: str,
                      ext: str = SERIES_EXT) -> str:
    """
    Construit le chemin du fichier de série pour (symbol, timeframe).

    Paramètres :
    - root (str) : répertoire racine des données.
    - symbol (str) : ex. "XAUUSD"
    - timeframe (str) : ex. "M1","M5","H1","H4","D1","W1"
    - ext (str) : extension ("parquet")

    Retour :
    - Chemin complet : {root}/{symbol}/{timeframe}.{ext}
    """
    safe_symbol = symbol.replace("/", "_")
    d = os.path.join(root, safe_symbol)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, f"{timeframe}.{ext}")


def build_metadata_path(series_path: str) -> str:
    """
    Renvoie le chemin du sidecar JSON pour un fichier série parquet.

    Ex : "/.../XAUUSD/D1.parquet" -> "/.../XAUUSD/D1.meta.json"
    """
    base, _ = os.path.splitext(series_path)
    return f"{base}.meta.json"


# ---------------------------------------------------------------------------
# Normalisation & validation
# ---------------------------------------------------------------------------

def normalize_ohlc_df(df: pd.DataFrame,
                      require_volume: bool = False,
                      force_utc: bool = FORCE_TIMEZONE_UTC) -> pd.DataFrame:
    """
    Normalise un DataFrame OHLCV :
    - colonnes obligatoires présentes
    - conversion numérique
    - 'time' en datetime (UTC si force_utc=True)
    - tri par 'time', suppression des doublons exacts sur 'time'
    - (option) s'assure que 'volume' existe (sinon le crée à 0.0)

    Paramètres :
    - require_volume (bool) : si True, lève si 'volume' manquant ; sinon crée à 0.
    - force_utc (bool) : si True, force timezone UTC.

    Retour : nouveau DataFrame normalisé.
    """
    required = ["time", "open", "high", "low", "close"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(f"Colonnes manquantes : {missing} (requis : {required})")

    out = df.copy()

    # time -> datetime
    out["time"] = pd.to_datetime(out["time"], errors="coerce", utc=False)
    if out["time"].isna().any():
        raise ValueError("Certaines lignes ont un 'time' invalide / non convertible.")
    if force_utc:
        # Si 'time' est naïf, on l'assimile à UTC ; s'il est tz-aware, on convertit en UTC
        if out["time"].dt.tz is None:
            out["time"] = out["time"].dt.tz_localize("UTC")
        else:
            out["time"] = out["time"].dt.tz_convert("UTC")

    # Numeric
    for c in ["open", "high", "low", "close"]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    if "volume" in out.columns:
        out["volume"] = pd.to_numeric(out.get("volume"), errors="coerce")
    elif require_volume:
        raise ValueError("'volume' requis mais manquant.")
    else:
        out["volume"] = 0.0

    # Drop lignes entièrement vides sur OHLC
    mask_bad = out[["open", "high", "low", "close"]].isna().any(axis=1)
    if mask_bad.any():
        if LENIENT_DROP_BAD_ROWS:
            out = out.loc[~mask_bad]
        else:
            idx = out.index[mask_bad].tolist()[:5]
            raise ValueError(f"Lignes avec NaN OHLC détectées (ex. index {idx}...). Active LENIENT_DROP_BAD_ROWS si besoin.")

    # Tri & doublons
    out = out.sort_values("time").drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)

    return out


def validate_ohlc_invariants(df: pd.DataFrame) -> None:
    """
    Vérifie des invariants de base :
    - high >= low
    - low <= open/close <= high (optionnel, on reste tolérant)
    - temps strictement croissant (après normalisation)

    Lève ValueError en cas d'incohérence (si LENIENT_DROP_BAD_ROWS=False).
    """
    if not {"time","open","high","low","close"}.issubset(df.columns):
        raise ValueError("DataFrame invalide — colonnes OHLC manquantes.")

    # high >= low
    bad = (df["high"] < df["low"])
    if bad.any():
        idx = df.index[bad].tolist()[:5]
        raise ValueError(f"Invariant violé : 'high < low' sur indices {idx}...")

    # (optionnel) bornes open/close dans [low, high] — tolérance en cas de spikes/arrondis
    # On signale sans bloquer :
    warn_mask = ((df["open"] < df["low"]) | (df["open"] > df["high"]) |
                 (df["close"] < df["low"]) | (df["close"] > df["high"]))
    if warn_mask.any():
        # Tu peux choisir de logguer un warning plutôt que d'échouer.
        pass

    # Temps croissant
    if not df["time"].is_monotonic_increasing:
        raise ValueError("La colonne 'time' doit être strictement croissante (après normalisation).")


# ---------------------------------------------------------------------------
# Lecture / écriture Parquet
# ---------------------------------------------------------------------------

def write_series_parquet(df: pd.DataFrame,
                         path: str,
                         mode: Literal["overwrite","append","merge"] = "merge",
                         metadata: Optional[Dict[str, Any]] = None) -> Tuple[int, Tuple[pd.Timestamp, pd.Timestamp]]:
    """
    Écrit une série OHLCV en Parquet.

    Paramètres :
    - df : DataFrame normalisé (ou brut — sera normalisé/validé ici).
    - path : chemin complet du fichier *.parquet
    - mode :
        * "overwrite" : remplace intégralement le fichier
        * "append"    : ajoute à la fin (ATTENTION : n'élimine pas les doublons)
        * "merge"     : lit l'existant, fusionne (union) sans doublons, trie par 'time'
    - metadata : dict optionnel à écrire dans un sidecar JSON (ex. {"symbol":"XAUUSD","timeframe":"D1"})

    Retour :
    - (nb_lignes, (t_start, t_end)) après écriture.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)

    # Normalisation & validation
    df_n = normalize_ohlc_df(df)
    validate_ohlc_invariants(df_n)

    # Merge si demandé
    if mode == "merge" and os.path.exists(path):
        existing = pd.read_parquet(path)
        existing = normalize_ohlc_df(existing)  # au cas où…
        merged = pd.concat([existing, df_n], axis=0)
        merged = merged.sort_values("time").drop_duplicates(subset=["time"], keep="last").reset_index(drop=True)
        df_n = merged
    elif mode == "append" and os.path.exists(path):
        # append simple (peut créer des doublons si l'appelant n'a pas filtré)
        pass
    elif mode not in ("overwrite","append","merge"):
        raise ValueError(f"Mode inconnu : {mode}")

    # Écriture atomique
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".tmp_", suffix=".parquet", dir=os.path.dirname(path))
    os.close(tmp_fd)
    try:
        df_n.to_parquet(tmp_path, index=False)
        os.replace(tmp_path, path)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass

    # Sidecar metadata (optionnel)
    if metadata is not None:
        meta_path = build_metadata_path(path)
        _write_json_atomic(meta_path, metadata)

    t0, t1 = df_n["time"].iloc[0], df_n["time"].iloc[-1]
    return len(df_n), (t0, t1)


def read_series_parquet(path: str,
                        start: Optional[pd.Timestamp] = None,
                        end: Optional[pd.Timestamp] = None,
                        columns: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Lit un fichier Parquet OHLCV et renvoie un DataFrame normalisé, filtré par [start, end] si fourni.

    Paramètres :
    - start/end : timestamps (tz-aware de préférence). Inclusifs.
    - columns   : sous-ensemble de colonnes si tu veux limiter l'I/O (ex. ["time","close"])

    Retour :
    - DataFrame normalisé, trié par 'time'.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    df = pd.read_parquet(path, columns=columns)
    df = normalize_ohlc_df(df)  # assure cohérence interne
    if start is not None:
        df = df[df["time"] >= _ensure_ts(start)]
    if end is not None:
        df = df[df["time"] <= _ensure_ts(end)]
    df = df.reset_index(drop=True)
    return df


def read_many(root: str,
              symbols: Iterable[str],
              timeframe: str,
              start: Optional[pd.Timestamp] = None,
              end: Optional[pd.Timestamp] = None,
              columns: Optional[List[str]] = None) -> Dict[str, pd.DataFrame]:
    """
    Lit plusieurs séries pour un timeframe donné.

    Retour :
    - dict {symbol: DataFrame}
    """
    out: Dict[str, pd.DataFrame] = {}
    for s in symbols:
        path = build_series_path(root, s, timeframe, ext=SERIES_EXT)
        if os.path.exists(path):
            out[s] = read_series_parquet(path, start=start, end=end, columns=columns)
    return out


# ---------------------------------------------------------------------------
# Metadata sidecar
# ---------------------------------------------------------------------------

def load_metadata(series_path: str) -> Optional[Dict[str, Any]]:
    """
    Charge le sidecar JSON si présent. Sinon None.
    """
    meta_path = build_metadata_path(series_path)
    if not os.path.exists(meta_path):
        return None
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json_atomic(path: str, data: Dict[str, Any]) -> None:
    """
    Écriture JSON atomique (temp + replace).
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".tmp_", suffix=".json", dir=os.path.dirname(path))
    os.close(fd)
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, default=_json_default)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def _json_default(o):
    """
    Sérialisation par défaut pour timestamps pandas/NumPy.
    """
    if isinstance(o, pd.Timestamp):
        # ISO 8601 avec timezone si dispo
        return o.isoformat()
    return str(o)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_ts(ts_like: Any) -> pd.Timestamp:
    """
    Convertit ts_like en pd.Timestamp tz-aware UTC si FORCE_TIMEZONE_UTC=True.
    """
    ts = pd.to_datetime(ts_like, utc=False)
    if FORCE_TIMEZONE_UTC:
        if ts.tz is None:
            ts = ts.tz_localize("UTC")
        else:
            ts = ts.tz_convert("UTC")
    return ts


def series_date_range(path: str) -> Optional[Tuple[pd.Timestamp, pd.Timestamp]]:
    """
    Retourne (t_start, t_end) pour un fichier parquet, ou None si absent.
    """
    if not os.path.exists(path):
        return None
    df = pd.read_parquet(path, columns=["time"])
    df = normalize_ohlc_df(df)
    return (df["time"].iloc[0], df["time"].iloc[-1])


def has_data(path: str) -> bool:
    """
    True si le fichier parquet existe ET contient >= 1 ligne.
    """
    if not os.path.exists(path):
        return False
    try:
        df = pd.read_parquet(path, columns=["time"])
        return len(df) > 0
    except Exception:
        return False
# Fin du fichier data/store.py