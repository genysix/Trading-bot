# main_download.py
# -*- coding: utf-8 -*-
"""
CLI pour télécharger des données OHLCV via OANDA et stocker en Parquet (data_local/...).
Exemples d'utilisation (depuis la racine du projet) :

    python main_download.py --symbol XAU_USD --timeframe D1 --start 2022-01-01 --end 2025-10-17
    python main_download.py --symbol XAU_USD --timeframe H1 --start -7d --end now

Options :
- --symbol       : instrument OANDA (ex. XAU_USD, EUR_USD, SPX500_USD)
- --timeframe    : M1, M5, M15, H1, H4, D1, W1
- --start / --end: date ISO (YYYY-MM-DD) ou alias relatifs : now, -7d, -1m, -1y
- --data-root    : répertoire de stockage (défaut: data_local)
- --chunk-days   : taille des segments de téléchargement (défaut: 120)
- --env          : practice|live (override du .env)
"""

from __future__ import annotations
import os
import argparse
from datetime import datetime, timedelta
import pandas as pd
from dotenv import load_dotenv

from data.datasource_oanda import OandaClient, OandaConfig
from data.downloader import download_ohlc, DownloadConfig


# --- Parsing helpers ----------------------------------------------------------

def parse_date_like(s: str) -> pd.Timestamp:
    """
    Convertit 's' en Timestamp UTC.
    - "now" : maintenant UTC
    - "-7d" : maintenant - 7 jours
    - "-1m" : maintenant - 1 mois (approximé à 30j)
    - "-1y" : maintenant - 365j
    - "YYYY-MM-DD" ou ISO
    """
    s = s.strip().lower()
    now = pd.Timestamp.utcnow().tz_localize("UTC") if pd.Timestamp.utcnow().tz is None else pd.Timestamp.utcnow()
    if s == "now":
        return now
    if s.startswith("-"):
        # relatif
        unit = s[-1]
        try:
            val = int(s[1:-1])
        except Exception:
            raise ValueError(f"Format relatif invalide : {s}")
        if unit == "d":
            return now - pd.Timedelta(days=val)
        if unit == "m":
            return now - pd.Timedelta(days=30 * val)
        if unit == "y":
            return now - pd.Timedelta(days=365 * val)
        raise ValueError(f"Unité relative inconnue : {unit} (attendu d/m/y)")
    # absolu
    return pd.to_datetime(s, utc=True)


# --- CLI ---------------------------------------------------------------------

def main():
    load_dotenv()  # charge .env à la racine

    parser = argparse.ArgumentParser(description="Téléchargement OHLCV vers Parquet via OANDA")
    parser.add_argument("--symbol", required=True, help="Instrument OANDA (ex. XAU_USD, EUR_USD)")
    parser.add_argument("--timeframe", required=True, choices=["M1","M5","M15","H1","H4","D1","W1"], help="Granularité des chandeliers")
    parser.add_argument("--start", required=True, help="Date de début (ISO) ou relatif (now, -7d, -1m, -1y)")
    parser.add_argument("--end", required=True, help="Date de fin (ISO) ou relatif")
    parser.add_argument("--data-root", default=os.getenv("DATA_ROOT", "data_local"), help="Racine de stockage (default: data_local)")
    parser.add_argument("--chunk-days", type=int, default=int(os.getenv("CHUNK_DAYS", 120)), help="Taille des chunks de téléchargement (jours)")
    parser.add_argument("--env", choices=["practice","live"], default=os.getenv("OANDA_ENV", "practice"), help="ENV OANDA (override .env)")
    args = parser.parse_args()

    # Dates
    start_ts = parse_date_like(args.start)
    end_ts = parse_date_like(args.end)
    if start_ts > end_ts:
        raise SystemExit("Erreur: --start > --end")

    # OANDA config
    cfg = OandaConfig(
        API_TOKEN=os.getenv("OANDA_API_TOKEN"),
        ACCOUNT_ID=os.getenv("OANDA_ACCOUNT_ID"),
        ENV=args.env
    )
    client = OandaClient(cfg)

    # Downloader config
    dcfg = DownloadConfig(
        DATA_ROOT=args.data_root,
        CHUNK_DAYS=args.chunk_days,
        WRITE_MODE="merge",
        SKIP_IF_UP_TO_DATE=True
    )

    # Lancer le téléchargement
    print(f"→ Téléchargement {args.symbol} {args.timeframe} [{start_ts} .. {end_ts}] (env={args.env})")
    nrows, (t0, t1) = download_ohlc(
        datasource=client,
        symbol=args.symbol,
        timeframe=args.timeframe,
        start=start_ts,
        end=end_ts,
        cfg=dcfg,
        metadata={"provider":"oanda"}
    )
    print(f"✅ Données enregistrées. Lignes: {nrows} | Période: {t0} → {t1} | Root: {args.data_root}")


if __name__ == "__main__":
    main()
# --- Fin du script -----------------------------------------------------------