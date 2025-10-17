# -*- coding: utf-8 -*-
"""
main.py
Récupération OANDA + affichage du rapport texte standard (backtest/report_text.py).

ENV (.env à la racine) :
  OANDA_ENV=practice | live
  OANDA_API_KEY=...
  OANDA_ACCOUNT_ID=...
  OANDA_PRACTICE_HOST=https://api-fxpractice.oanda.com   # (opt)
  OANDA_LIVE_HOST=https://api-fxtrade.oanda.com          # (opt)

  # Options d'exécution (facultatives)
  OANDA_SYMBOL=XAU_USD
  OANDA_GRANULARITY=H1
  OANDA_CANDLES_COUNT=500
  OANDA_DEBUG=false

  # Capital de départ pour le rapport
  INITIAL_CAPITAL=10000
"""

from __future__ import annotations
import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv

# Import de ton client OANDA et du générateur de rapport
from api.oanda import OandaClient
from backtest.report_text import generate_text_report


def _clean_env(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    return v.strip().strip('"').strip("'")


def _to_prices_df(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Convertit les bougies OANDA (mid) en DataFrame avec colonnes :
    time, open, high, low, close
    """
    rows = []
    for c in candles:
        t = pd.to_datetime(c.get("time"))
        m = c.get("mid", {}) or {}
        try:
            rows.append(
                {
                    "time": t,
                    "open": float(m.get("o")),
                    "high": float(m.get("h")),
                    "low": float(m.get("l")),
                    "close": float(m.get("c")),
                    "complete": bool(c.get("complete", False)),
                }
            )
        except (TypeError, ValueError):
            # skip bougie invalide
            continue
    df = pd.DataFrame(rows).dropna()
    df = df.sort_values("time").reset_index(drop=True)
    return df


def _build_equity_curve(df_prices: pd.DataFrame, initial_capital: float) -> pd.DataFrame:
    """
    Équity 'buy&hold' (échelle proportionnelle) sur la série close.
    Retourne DataFrame avec colonnes ['time', 'equity'] (attendu par report_text).
    """
    if df_prices.empty:
        return pd.DataFrame(columns=["time", "equity"])
    close0 = float(df_prices["close"].iloc[0])
    scale = initial_capital / max(1e-12, close0)
    equity = scale * df_prices["close"].astype(float).values
    return pd.DataFrame({"time": df_prices["time"].values, "equity": equity})


def main() -> int:
    # --- Localisation / chargement .env
    here = Path(__file__).resolve()
    project_root = here.parent
    env_path = project_root / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path)
    else:
        load_dotenv()

    # --- Lecture ENV d’exécution
    env = (_clean_env(os.getenv("OANDA_ENV")) or "practice").lower()
    symbol = _clean_env(os.getenv("OANDA_SYMBOL")) or "XAU_USD"
    granularity = _clean_env(os.getenv("OANDA_GRANULARITY")) or "D"
    try:
        count = int(_clean_env(os.getenv("OANDA_CANDLES_COUNT")) or "300")
    except ValueError:
        count = 300
    debug_flag = (_clean_env(os.getenv("OANDA_DEBUG")) or "false").lower() in ("1", "true", "yes", "y")
    try:
        initial_capital = float(_clean_env(os.getenv("INITIAL_CAPITAL")) or "10000")
    except ValueError:
        initial_capital = 10000.0

    # --- Client OANDA
    try:
        client = OandaClient.from_env()
    except Exception as e:
        print(f"❌ Erreur d'initialisation du client OANDA : {e}")
        return 2

    if debug_flag:
        print("DEBUG ENV →", {
            "OANDA_ENV": env,
            "OANDA_API_KEY": "***" if os.getenv("OANDA_API_KEY") else None,
            "OANDA_ACCOUNT_ID": client.account_id,
            "OANDA_PRACTICE_HOST": client.practice_host,
            "OANDA_LIVE_HOST": client.live_host,
            "OANDA_SYMBOL": symbol,
            "OANDA_GRANULARITY": granularity,
            "OANDA_CANDLES_COUNT": count,
            "INITIAL_CAPITAL": initial_capital,
        })

    print(f"▶️ Environnement : {env}")
    print(f"▶️ Host : {client.base}")
    print(f"▶️ Compte : {client.account_id}")
    print(f"▶️ Instrument : {symbol} | Granularity: {granularity} | Count: {count}")
    print("-" * 80)

    try:
        # 1) (optionnel) Ping + résumé pour s'assurer que tout va bien
        accounts = client.ping()
        print(f"✅ API OK — {len(accounts)} compte(s) détecté(s)")
        summary = client.account_summary()
        print("✅ Compte — résumé (balance/NAV):",
              json.dumps({"balance": summary.get("balance"), "NAV": summary.get("NAV")}, ensure_ascii=False))

        # 2) Vérif instrument (facultatif)
        instruments = client.instruments()
        found = any((i.get("name") or "").upper() == symbol.upper() for i in instruments)
        if found:
            print(f"✅ Instrument {symbol} disponible sur ce compte.")
        else:
            print(f"⚠️ Instrument {symbol} non trouvé sur ce compte.")

        # 3) Récupération bougies -> DataFrame prix
        candles = client.candles(symbol, granularity=granularity, count=count, price="M")
        print(f"✅ Bougies reçues : {len(candles)}")
        df_prices = _to_prices_df(candles)
        if df_prices.empty:
            raise RuntimeError("Aucune bougie exploitable reçue (df_prices vide).")

        # 4) Courbe d’équité (buy&hold) + structure result (trades/equity_curve)
        equity_df = _build_equity_curve(df_prices, initial_capital)
        # Pour l’instant, pas de moteur de stratégie ici : on passe une liste de trades vide.
        # (report_text gère proprement ce cas et affichera 'No long or short trades found')
        result: Dict[str, Any] = {
            "trades": [],                 # ou liste de dicts: {"time", "type": "BUY"/"SELL", "price", "qty"}
            "equity_curve": equity_df,    # DataFrame avec ['time','equity']
        }

        # 5) Génération et AFFICHAGE du rapport texte standard
        report = generate_text_report(
            result=result,
            df_prices=df_prices[["time", "open", "high", "low", "close"]],
            initial_capital=initial_capital,
            symbol=symbol,
            timeframe=granularity,
            metrics=None,  # laissé à None ; le module calcule tout en interne
        )
        print("\n" + report)

        return 0

    except Exception as e:
        print("\n❌ Erreur pendant l'exécution :")
        print(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
