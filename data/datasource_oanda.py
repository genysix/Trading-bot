# data/datasource_oanda.py
# -*- coding: utf-8 -*-
"""
Client OANDA v20 (REST) minimaliste et prêt pour évoluer :
- Historique OHLC (candles) : fetch_ohlc()
- Ping compte / instruments : ping_account(), list_instruments()
- Stubs d'exécution pour plus tard : place_market_order(), place_limit_order(), close_position(), get_open_trades(), get_positions()

Design :
- Pas de secret en dur : lecture via variables d'environnement OANDA_*
- Environnement 'practice' (défaut) ou 'live'
- Gestion simple du rate limiting et pagination (candles)
- Conversion auto en DataFrame OHLCV standard

Dépendances : requests, pandas
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict, Any, List, Literal, Tuple
import os
import time
import math
import requests
import pandas as pd


# -------------------------
# Constantes / endpoints
# -------------------------

OANDA_ENV = Literal["practice", "live"]

# URL base par environnement
BASE_URLS = {
    "practice": "https://api-fxpractice.oanda.com",
    "live":     "https://api-fxtrade.oanda.com",
}

# Granularités OANDA vs nos timeframes (mapping minimal)
# Note : OANDA candles: S5,S10,S15,S30,M1,M2,M4,M5,M10,M15,M30,H1,H2,H3,H4,H6,H8,H12,D,W,M
TF_TO_OANDA = {
    "M1": "M1",
    "M5": "M5",
    "M15": "M15",
    "H1": "H1",
    "H4": "H4",
    "D1": "D",
    "W1": "W",
}


# -------------------------
# Config client
# -------------------------

@dataclass
class OandaConfig:
    # Token d'API :
    # - Valeurs possibles : chaîne JWT fournie par OANDA (ne jamais commit)
    # - Par défaut, lu dans l'env: OANDA_API_TOKEN
    API_TOKEN: Optional[str] = None

    # ID du compte :
    # - Valeurs possibles : chaîne alphanum (ex. "101-001-12345678-001")
    # - Par défaut, lu dans l'env: OANDA_ACCOUNT_ID
    ACCOUNT_ID: Optional[str] = None

    # Environnement OANDA : "practice" (défaut) ou "live"
    ENV: OANDA_ENV = "practice"

    # Timeout HTTP (sec)
    TIMEOUT: int = 30

    # Max retries simples (erreurs transitoires 5xx)
    MAX_RETRIES: int = 3

    # Pause entre retries (sec)
    RETRY_SLEEP: float = 1.0

    # Prix de référence pour candles : "M" (mid), "B" (bid), "A" (ask)
    # Valeurs possibles : "M","B","A"
    CANDLE_PRICE: str = "M"

    # Limite max de candles par requête (OANDA supporte 'count' jusqu'à 5000)
    # Valeurs possibles : int 1..5000 (selon compte)
    MAX_CANDLES_PER_REQ: int = 5000

    def resolve(self):
        """Récupère tokens/env depuis os.environ si non fournis."""
        if not self.API_TOKEN:
            self.API_TOKEN = os.getenv("OANDA_API_TOKEN", None)
        if not self.ACCOUNT_ID:
            self.ACCOUNT_ID = os.getenv("OANDA_ACCOUNT_ID", None)
        if self.ENV not in BASE_URLS:
            raise ValueError("ENV doit être 'practice' ou 'live'")
        if not self.API_TOKEN:
            raise ValueError("API_TOKEN manquant (env OANDA_API_TOKEN ou OandaConfig.API_TOKEN)")
        if not self.ACCOUNT_ID:
            raise ValueError("ACCOUNT_ID manquant (env OANDA_ACCOUNT_ID ou OandaConfig.ACCOUNT_ID)")


# -------------------------
# Client
# -------------------------

class OandaClient:
    NAME = "oanda"

    def __init__(self, cfg: Optional[OandaConfig] = None):
        self.cfg = cfg or OandaConfig()
        self.cfg.resolve()
        self.base_url = BASE_URLS[self.cfg.ENV]
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {self.cfg.API_TOKEN}",
            "Content-Type": "application/json"
        })

    # -------------
    # Utilitaires HTTP
    # -------------
    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = self.base_url + path
        for attempt in range(1, self.cfg.MAX_RETRIES + 1):
            r = self.session.get(url, params=params, timeout=self.cfg.TIMEOUT)
            if r.status_code >= 500:
                time.sleep(self.cfg.RETRY_SLEEP)
                continue
            if r.status_code == 429:
                # rate limit — attendre puis retry simple
                time.sleep(1.0 + attempt * 0.5)
                continue
            r.raise_for_status()
            return r.json()
        # Dernière tentative
        r = self.session.get(url, params=params, timeout=self.cfg.TIMEOUT)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
        url = self.base_url + path
        for attempt in range(1, self.cfg.MAX_RETRIES + 1):
            r = self.session.post(url, json=json_body, timeout=self.cfg.TIMEOUT)
            if r.status_code >= 500:
                time.sleep(self.cfg.RETRY_SLEEP)
                continue
            if r.status_code == 429:
                time.sleep(1.0 + attempt * 0.5)
                continue
            r.raise_for_status()
            return r.json()
        r = self.session.post(url, json=json_body, timeout=self.cfg.TIMEOUT)
        r.raise_for_status()
        return r.json()

    def _put(self, path: str, json_body: Dict[str, Any]) -> Dict[str, Any]:
        url = self.base_url + path
        r = self.session.put(url, json=json_body, timeout=self.cfg.TIMEOUT)
        if r.status_code == 429:
            time.sleep(1.5)
            r = self.session.put(url, json=json_body, timeout=self.cfg.TIMEOUT)
        r.raise_for_status()
        return r.json()

    # -------------
    # Sanity / Info
    # -------------
    def ping_account(self) -> Dict[str, Any]:
        """
        Retourne un résumé du compte (solde, NAV, etc.) — simple test de connectivité.
        """
        path = f"/v3/accounts/{self.cfg.ACCOUNT_ID}/summary"
        return self._get(path)

    def list_instruments(self) -> List[Dict[str, Any]]:
        """
        Liste les instruments tradables pour le compte (utile pour vérifier disponibilité).
        """
        path = f"/v3/accounts/{self.cfg.ACCOUNT_ID}/instruments"
        data = self._get(path)
        return data.get("instruments", [])

    # -------------
    # OHLC historique
    # -------------
    def fetch_ohlc(self, *, symbol: str, timeframe: str, start, end) -> pd.DataFrame:
        """
        Récupère des chandeliers OANDA dans [start, end] (inclus), convertit en DataFrame OHLCV.
        - symbol (ex: "XAU_USD" chez OANDA ; mapping "XAUUSD" -> "XAU_USD" à gérer côté appelant si besoin)
        - timeframe : map via TF_TO_OANDA
        - start/end : pd.Timestamp/str (UTC recommandé)

        Retour : DataFrame avec colonnes : time, open, high, low, close, volume
        """
        gran = TF_TO_OANDA.get(timeframe)
        if gran is None:
            raise ValueError(f"Timeframe non supporté par OANDA: {timeframe}")

        # Normalisation dates ISO
        start_iso = pd.to_datetime(start, utc=True).isoformat()
        end_iso   = pd.to_datetime(end,   utc=True).isoformat()

        params = {
            "from": start_iso,
            "to": end_iso,
            "granularity": gran,
            "price": self.cfg.CANDLE_PRICE,
            "count": self.cfg.MAX_CANDLES_PER_REQ,  # plafond ; OANDA respectera from/to
        }
        path = f"/v3/instruments/{symbol}/candles"
        data = self._get(path, params=params)
        candles = data.get("candles", [])

        rows = []
        for c in candles:
            if not c.get("complete", False):
                continue
            t = pd.to_datetime(c["time"], utc=True)
            # Prix mid/bid/ask structure diffère ; ici on supporte 'M','B','A'
            px_key = {"M": "mid", "B": "bid", "A": "ask"}[self.cfg.CANDLE_PRICE]
            o = float(c[px_key]["o"])
            h = float(c[px_key]["h"])
            l = float(c[px_key]["l"])
            cl = float(c[px_key]["c"])
            v = float(c.get("volume", 0.0))
            rows.append({"time": t, "open": o, "high": h, "low": l, "close": cl, "volume": v})

        df = pd.DataFrame(rows)
        # Le store normalisera/validera encore ; ici on tri/uniq déjà
        if len(df):
            df = df.sort_values("time").drop_duplicates("time", keep="last").reset_index(drop=True)
        return df

    # -------------
    # Trading (stubs pour plus tard)
    # -------------
    def place_market_order(
        self,
        *,
        symbol: str,
        units: float,
        side: Literal["buy", "sell"],
        time_in_force: Literal["FOK", "IOC"] = "FOK",
        client_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place un ordre au marché.
        - units : nombre (positif) d'unités. OANDA signe par côté ; on convertit via side.
        - side  : "buy" (long) ou "sell" (short).
        """
        path = f"/v3/accounts/{self.cfg.ACCOUNT_ID}/orders"
        signed_units = units if side == "buy" else -abs(units)
        body = {
            "order": {
                "type": "MARKET",
                "instrument": symbol,
                "units": str(signed_units),
                "timeInForce": time_in_force,
                **({"clientExtensions": {"tag": client_tag}} if client_tag else {})
            }
        }
        return self._post(path, body)

    def place_limit_order(
        self,
        *,
        symbol: str,
        units: float,
        side: Literal["buy", "sell"],
        price: float,
        gtd_time: Optional[str] = None,
        client_tag: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Place un ordre limite.
        - price (float) : prix limite.
        - gtd_time (str ISO) : expiration si timeInForce=GTD ; sinon GTC par défaut.
        """
        path = f"/v3/accounts/{self.cfg.ACCOUNT_ID}/orders"
        signed_units = units if side == "buy" else -abs(units)
        order = {
            "type": "LIMIT",
            "instrument": symbol,
            "units": str(signed_units),
            "price": str(price),
            "timeInForce": "GTC",
        }
        if gtd_time:
            order["timeInForce"] = "GTD"
            order["gtdTime"] = gtd_time
        if client_tag:
            order["clientExtensions"] = {"tag": client_tag}
        return self._post(path, {"order": order})

    def close_position(self, *, symbol: str, long_units: Optional[str] = "ALL", short_units: Optional[str] = "ALL") -> Dict[str, Any]:
        """
        Ferme la position sur un instrument :
        - long_units  : "ALL", "NONE" ou un nombre (str) à clôturer.
        - short_units : idem côté short.
        """
        path = f"/v3/accounts/{self.cfg.ACCOUNT_ID}/positions/{symbol}/close"
        body: Dict[str, Any] = {}
        if long_units:
            body["longUnits"] = long_units
        if short_units:
            body["shortUnits"] = short_units
        return self._put(path, body)

    def get_open_trades(self) -> List[Dict[str, Any]]:
        """
        Liste des trades ouverts sur le compte.
        """
        path = f"/v3/accounts/{self.cfg.ACCOUNT_ID}/openTrades"
        data = self._get(path)
        return data.get("trades", [])

    def get_positions(self) -> List[Dict[str, Any]]:
        """
        Liste des positions agrégées par instrument.
        """
        path = f"/v3/accounts/{self.cfg.ACCOUNT_ID}/openPositions"
        data = self._get(path)
        return data.get("positions", [])
# Fin du fichier data/datasource_oanda.py