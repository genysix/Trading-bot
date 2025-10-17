from __future__ import annotations
import os
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import time
import requests
from dotenv import load_dotenv


Number = Union[int, float, str]


def _clean_env(v: Optional[str]) -> Optional[str]:
    if v is None:
        return None
    return v.strip().strip('"').strip("'")


def _as_oanda_str_num(x: Optional[Number]) -> Optional[str]:
    """OANDA attend les nombres sous forme de chaînes (ex: '1.2345' ou '100')."""
    if x is None:
        return None
    if isinstance(x, str):
        return x
    # Assure un str sans formatage exotique
    return str(x)


class OandaHTTPError(RuntimeError):
    def __init__(self, status: int, url: str, body: str):
        super().__init__(f"HTTP {status} on {url}\n{body}")
        self.status = status
        self.url = url
        self.body = body


class OandaClient:
    """
    Client fin et explicite pour OANDA v3.
    - Gère base URL practice/live selon ENV
    - Session HTTP persistante
    - Petits retries sur 429/5xx
    """

    DEFAULT_PRACTICE = "https://api-fxpractice.oanda.com"
    DEFAULT_LIVE = "https://api-fxtrade.oanda.com"

    def __init__(
        self,
        api_key: str,
        account_id: str,
        env: str = "practice",
        practice_host: Optional[str] = None,
        live_host: Optional[str] = None,
        timeout: int = 20,
        debug: bool = False,
        max_retries: int = 3,
        retry_backoff: float = 0.75,
    ):
        self.api_key = api_key
        self.account_id = account_id
        self.env = (env or "practice").lower()
        self.practice_host = practice_host or self.DEFAULT_PRACTICE
        self.live_host = live_host or self.DEFAULT_LIVE
        self.timeout = timeout
        self.debug = debug
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff

        self.base = self.live_host if self.env == "live" else self.practice_host

        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Bearer {self.api_key}",
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    # ------------------------------------------------------------------
    # Initialisation depuis .env (à la racine du repo)
    # ------------------------------------------------------------------
    @classmethod
    def from_env(cls) -> "OandaClient":
        # Localise la racine du repo à partir de ce fichier, puis charge .env
        here = Path(__file__).resolve()
        # Heuristique : si ce fichier est placé dans /data ou /api, remonte d'un niveau
        project_root = here.parents[1] if (here.parent / "..").exists() else here.parent
        env_path = project_root / ".env"
        if not env_path.exists():
            # Plan B : tente .env courant
            env_path = Path.cwd() / ".env"
        if env_path.exists():
            load_dotenv(dotenv_path=env_path)
        else:
            # Charge tout de même les variables d'environnement de l'OS
            load_dotenv()  # no-op si absent

        env = _clean_env(os.getenv("OANDA_ENV")) or "practice"
        api_key = _clean_env(os.getenv("OANDA_API_KEY"))
        account_id = _clean_env(os.getenv("OANDA_ACCOUNT_ID"))
        practice_host = _clean_env(os.getenv("OANDA_PRACTICE_HOST")) or cls.DEFAULT_PRACTICE
        live_host = _clean_env(os.getenv("OANDA_LIVE_HOST")) or cls.DEFAULT_LIVE
        debug = (_clean_env(os.getenv("OANDA_DEBUG")) or "false").lower() in ("1", "true", "yes", "y")

        if not api_key or not account_id:
            raise RuntimeError("Variables manquantes : OANDA_API_KEY et/ou OANDA_ACCOUNT_ID")

        return cls(
            api_key=api_key,
            account_id=account_id,
            env=env,
            practice_host=practice_host,
            live_host=live_host,
            debug=debug,
        )

    # ------------------------------------------------------------------
    # HTTP helpers + retry
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        url = f"{self.base}{path}"
        data = json.dumps(payload) if payload is not None else None

        for attempt in range(1, self.max_retries + 1):
            r = self.session.request(method, url, params=params, data=data, timeout=self.timeout)
            if self.debug:
                print(f"[{method}] {url} params={params} payload={payload} -> {r.status_code}")

            if r.status_code < 400:
                try:
                    return r.json()
                except Exception:
                    return {"raw": r.text}

            # Retriable ?
            if r.status_code in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                # Respecte éventuellement Retry-After
                ra = r.headers.get("Retry-After")
                sleep_s = float(ra) if (ra and ra.isdigit()) else self.retry_backoff * attempt
                if self.debug:
                    print(f"HTTP {r.status_code} — retry dans {sleep_s:.2f}s (tentative {attempt}/{self.max_retries})")
                time.sleep(sleep_s)
                continue

            # Sinon, lève une erreur explicite
            raise OandaHTTPError(r.status_code, url, r.text)

        # Ne devrait pas arriver
        raise RuntimeError("Échec HTTP après retries")

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        return self._request("GET", path, params=params)

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", path, payload=payload)

    def _put(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("PUT", path, payload=payload)

    # ------------------------------------------------------------------
    # Fonctions utilitaires pour le bot
    # ------------------------------------------------------------------
    def ping(self) -> List[Dict[str, Any]]:
        """Liste des comptes accessibles (simple test API)."""
        data = self._get("/v3/accounts")
        return data.get("accounts", [])

    def account_summary(self, account_id: Optional[str] = None) -> Dict[str, Any]:
        """Résumé de compte (NAV, balance, trades ouverts, etc.)."""
        acc = account_id or self.account_id
        data = self._get(f"/v3/accounts/{acc}/summary")
        return data.get("account", {})

    def balance(self, account_id: Optional[str] = None) -> float:
        """Solde (balance) sous forme float (attention : précision/arrondi au besoin)."""
        summary = self.account_summary(account_id)
        try:
            return float(summary.get("balance"))
        except Exception:
            # Fallback : 0.0 si non parsable
            return 0.0

    def instruments(self, account_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Instruments disponibles sur ce compte."""
        acc = account_id or self.account_id
        data = self._get(f"/v3/accounts/{acc}/instruments")
        return data.get("instruments", [])

    def candles(
        self,
        instrument: str,
        granularity: str = "H1",
        count: int = 100,
        price: str = "M",
        **extra_params: Any,
    ) -> List[Dict[str, Any]]:
        """
        Bougies (candles) pour un instrument.
        price: "M" mid, "B" bid, "A" ask, ou combinaisons "MBA"
        """
        params = {"granularity": granularity, "count": count, "price": price}
        params.update(extra_params or {})
        data = self._get(f"/v3/instruments/{instrument}/candles", params=params)
        return data.get("candles", [])

    def pricing(self, instruments: List[str]) -> List[Dict[str, Any]]:
        """Prix temps-réel (snapshot) pour une liste d'instruments."""
        params = {"instruments": ","*0 if not instruments else ",".join(instruments)}
        data = self._get(f"/v3/accounts/{self.account_id}/pricing", params=params)
        return data.get("prices", [])

    # ----- Trades / Positions / Orders -----
    def open_trades(self) -> List[Dict[str, Any]]:
        data = self._get(f"/v3/accounts/{self.account_id}/openTrades")
        return data.get("trades", [])

    def open_positions(self) -> List[Dict[str, Any]]:
        data = self._get(f"/v3/accounts/{self.account_id}/openPositions")
        return data.get("positions", [])

    def orders(self, state: str = "PENDING") -> List[Dict[str, Any]]:
        """Liste des ordres (par défaut en attente). state peut être: PENDING, FILLED, CANCELLED, ALL (via params)."""
        params = {"state": state}
        data = self._get(f"/v3/accounts/{self.account_id}/orders", params=params)
        return data.get("orders", [])

    # ----- Passage d’ordres -----
    def place_market_order(
        self,
        instrument: str,
        units: Number,
        time_in_force: str = "FOK",
        client_tag: Optional[str] = None,
        take_profit_price: Optional[Number] = None,
        stop_loss_price: Optional[Number] = None,
        trailing_stop_distance: Optional[Number] = None,
    ) -> Dict[str, Any]:
        """
        Place un ordre marché (achat si units>0, vente si units<0).

        Notes :
        - OANDA attend des nombres en str, on convertit automatiquement.
        - take_profit_price et stop_loss_price sont des prix absolus.
        - trailing_stop_distance est une distance en prix (ex: '0.0020').
        """
        order: Dict[str, Any] = {
            "order": {
                "type": "MARKET",
                "instrument": instrument,
                "units": _as_oanda_str_num(units),
                "timeInForce": time_in_force,
                "positionFill": "DEFAULT",
            }
        }
        if client_tag:
            order["order"]["clientExtensions"] = {"tag": client_tag}

        # TP/SL/Trailing
        tp = _as_oanda_str_num(take_profit_price)
        sl = _as_oanda_str_num(stop_loss_price)
        ts = _as_oanda_str_num(trailing_stop_distance)

        if tp:
            order["order"]["takeProfitOnFill"] = {"price": tp}
        if sl:
            order["order"]["stopLossOnFill"] = {"price": sl}
        if ts:
            order["order"]["trailingStopLossOnFill"] = {"distance": ts}

        data = self._post(f"/v3/accounts/{self.account_id}/orders", order)
        return data

    def place_limit_order(
        self,
        instrument: str,
        units: Number,
        price: Number,
        time_in_force: str = "GTC",
        client_tag: Optional[str] = None,
        take_profit_price: Optional[Number] = None,
        stop_loss_price: Optional[Number] = None,
    ) -> Dict[str, Any]:
        """
        Place un ordre LIMIT (exécuté quand le prix atteint le niveau).
        """
        order: Dict[str, Any] = {
            "order": {
                "type": "LIMIT",
                "instrument": instrument,
                "units": _as_oanda_str_num(units),
                "price": _as_oanda_str_num(price),
                "timeInForce": time_in_force,  # GTC/GTX/GTD
                "positionFill": "DEFAULT",
            }
        }
        if client_tag:
            order["order"]["clientExtensions"] = {"tag": client_tag}

        tp = _as_oanda_str_num(take_profit_price)
        sl = _as_oanda_str_num(stop_loss_price)
        if tp:
            order["order"]["takeProfitOnFill"] = {"price": tp}
        if sl:
            order["order"]["stopLossOnFill"] = {"price": sl}

        data = self._post(f"/v3/accounts/{self.account_id}/orders", order)
        return data

    def cancel_order(self, order_id: str) -> Dict[str, Any]:
        data = self._put(f"/v3/accounts/{self.account_id}/orders/{order_id}/cancel", payload={})
        return data

    def close_trade(self, trade_id: str, units: Union[str, Number] = "ALL") -> Dict[str, Any]:
        """
        Ferme un trade partiellement (units='100') ou totalement (units='ALL').
        """
        payload = {"units": _as_oanda_str_num(units) if units != "ALL" else "ALL"}
        data = self._put(f"/v3/accounts/{self.account_id}/trades/{trade_id}/close", payload=payload)
        return data

    def close_position(
        self,
        instrument: str,
        long_units: Optional[Union[str, Number]] = None,
        short_units: Optional[Union[str, Number]] = None,
    ) -> Dict[str, Any]:
        """
        Ferme la position sur un instrument.
        - long_units / short_units : 'ALL' ou nombre (ex: '100')
        """
        payload: Dict[str, Any] = {}
        if long_units is not None:
            payload["longUnits"] = _as_oanda_str_num(long_units) if long_units != "ALL" else "ALL"
        if short_units is not None:
            payload["shortUnits"] = _as_oanda_str_num(short_units) if short_units != "ALL" else "ALL"
        data = self._put(f"/v3/accounts/{self.account_id}/positions/{instrument}/close", payload=payload)
        return data
