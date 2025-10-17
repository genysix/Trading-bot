# -*- coding: utf-8 -*-
"""
api_tests/test_oanda_connection.py
Test de connexion OANDA sans arguments CLI (tout via .env)

Variables attendues dans .env (à la racine du repo) :
  OANDA_ENV=practice                 # practice | live (défaut: practice)
  OANDA_API_KEY=xxxxxxxxxxxxxxxx
  OANDA_ACCOUNT_ID=001-001-xxxxxxx-001
  OANDA_PRACTICE_HOST=https://api-fxpractice.oanda.com   # optionnel
  OANDA_LIVE_HOST=https://api-fxtrade.oanda.com          # optionnel

  # Options de test (facultatives)
  OANDA_SYMBOL=XAU_USD
  OANDA_GRANULARITY=D               # D, H4, H1, M15, etc.
  OANDA_CANDLES_COUNT=10
  OANDA_DEBUG=false                 # true pour afficher les valeurs lues

Usage :
  python api_tests/test_oanda_connection.py
"""

from __future__ import annotations
import os
import sys
import json
from pathlib import Path
from typing import Any, Dict, Optional, List

import requests
from dotenv import load_dotenv
from pathlib import Path

# Toujours charger le .env à la racine du projet
project_root = Path(__file__).resolve().parents[1]
env_path = project_root / ".env"

if not env_path.exists():
    raise FileNotFoundError(f"Fichier .env introuvable à {env_path}")


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def clean_env(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    return value.strip().strip('"').strip("'")


def pretty(obj: Any) -> str:
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False, default=str)
    except Exception:
        return str(obj)


def http_get(base: str, path: str, token: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    url = f"{base}{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    r = requests.get(url, headers=headers, params=params, timeout=20)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code} on {url}\n{r.text}")
    return r.json()


def ping_api(base: str, token: str) -> List[Dict[str, Any]]:
    data = http_get(base, "/v3/accounts", token)
    accounts = data.get("accounts", [])
    print(f"✅ API OK — {len(accounts)} compte(s) détecté(s)")
    return accounts


def account_summary(base: str, token: str, acc_id: str) -> Dict[str, Any]:
    data = http_get(base, f"/v3/accounts/{acc_id}/summary", token)
    summary = data.get("account", {})
    if not summary:
        raise RuntimeError("Réponse inattendue : summary vide.")
    print("✅ Compte — résumé:")
    print(pretty({
        "id": summary.get("id"),
        "alias": summary.get("alias"),
        "currency": summary.get("currency"),
        "balance": summary.get("balance"),
        "NAV": summary.get("NAV"),
        "openTradeCount": summary.get("openTradeCount"),
        "pendingOrderCount": summary.get("pendingOrderCount"),
        "pl": summary.get("pl"),
        "resettablePL": summary.get("resettablePL"),
    }))
    return summary


def list_instruments(base: str, token: str, acc_id: str) -> List[Dict[str, Any]]:
    data = http_get(base, f"/v3/accounts/{acc_id}/instruments", token)
    instruments = data.get("instruments", [])
    print(f"✅ Instruments disponibles : {len(instruments)}")
    return instruments


def fetch_candles(base: str, token: str, instrument: str, granularity: str, count: int = 10):
    params = {"granularity": granularity, "count": count, "price": "M"}  # mid
    data = http_get(base, f"/v3/instruments/{instrument}/candles", token, params)
    candles = data.get("candles", [])
    print(f"✅ Bougies reçues : {len(candles)}")
    if candles:
        print("--- Aperçu des 3 dernières bougies (UTC) ---")
        for c in candles[-3:]:
            m = c.get("mid", {})
            print(f"{c.get('time')} | complete={c.get('complete')} | o={m.get('o')} h={m.get('h')} l={m.get('l')} c={m.get('c')}")
    return candles


# ----------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------
def main():
    # Charger le .env depuis la racine du projet, même si ce script est ailleurs
    load_dotenv(dotenv_path=env_path)

    # Lire et nettoyer les variables
    env = (clean_env(os.getenv("OANDA_ENV")) or "practice").lower()
    api_key = clean_env(os.getenv("OANDA_API_KEY"))
    account_id = clean_env(os.getenv("OANDA_ACCOUNT_ID"))
    practice_host = clean_env(os.getenv("OANDA_PRACTICE_HOST")) or "https://api-fxpractice.oanda.com"
    live_host = clean_env(os.getenv("OANDA_LIVE_HOST")) or "https://api-fxtrade.oanda.com"

    symbol = clean_env(os.getenv("OANDA_SYMBOL")) or "XAU_USD"
    granularity = clean_env(os.getenv("OANDA_GRANULARITY")) or "D"
    try:
        count = int(clean_env(os.getenv("OANDA_CANDLES_COUNT")) or "10")
    except ValueError:
        count = 10

    debug_flag = (clean_env(os.getenv("OANDA_DEBUG")) or "false").lower() in ("1", "true", "yes", "y")

    if debug_flag:
        print("DEBUG ENV →", {
            "OANDA_ENV": env,
            "OANDA_API_KEY": "***" if api_key else None,
            "OANDA_ACCOUNT_ID": account_id,
            "OANDA_PRACTICE_HOST": practice_host,
            "OANDA_LIVE_HOST": live_host,
            "OANDA_SYMBOL": symbol,
            "OANDA_GRANULARITY": granularity,
            "OANDA_CANDLES_COUNT": count,
        })

    if not api_key or not account_id:
        print("❌ Variables manquantes : OANDA_API_KEY et/ou OANDA_ACCOUNT_ID")
        sys.exit(2)

    base = live_host if env == "live" else practice_host

    print(f"▶️ Environnement : {env}")
    print(f"▶️ Host : {base}")
    print(f"▶️ Compte : {account_id}")
    print(f"▶️ Instrument : {symbol} | Granularity: {granularity} | Count: {count}")
    print("-" * 80)

    try:
        ping_api(base, api_key)
        account_summary(base, api_key, account_id)

        instruments = list_instruments(base, api_key, account_id)
        found = any(i.get("name", "").upper() == symbol.upper() for i in instruments)
        if found:
            print(f"✅ Instrument {symbol} disponible sur ce compte.")
        else:
            print(f"⚠️ Instrument {symbol} non trouvé sur ce compte.")

        fetch_candles(base, api_key, symbol, granularity, count)
        print("\n✅ Connexion et récupération réussies.")
        sys.exit(0)

    except Exception as e:
        print("\n❌ Erreur pendant le test OANDA:")
        print(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
