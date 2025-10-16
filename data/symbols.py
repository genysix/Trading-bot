# data/symbols.py
# -*- coding: utf-8 -*-
"""
Mapping utilitaire de symboles "génériques" -> symboles spécifiques OANDA (et inverse).
Tu peux l'étendre selon les besoins.
"""

from __future__ import annotations
from typing import Dict

GENERIC_TO_OANDA: Dict[str, str] = {
    "XAUUSD": "XAU_USD",
    "EURUSD": "EUR_USD",
    "USDJPY": "USD_JPY",
    "US500":  "SPX500_USD",
    "NAS100": "NAS100_USD",
    "UKOIL":  "UKOIL_USD",
    "USOIL":  "WTICO_USD",
}

OANDA_TO_GENERIC: Dict[str, str] = {v: k for k, v in GENERIC_TO_OANDA.items()}


def to_oanda(symbol: str) -> str:
    """
    Convertit un symbole "générique" (ex. XAUUSD) en symbole OANDA (XAU_USD).
    Si déjà au format OANDA, renvoie tel quel.
    """
    return GENERIC_TO_OANDA.get(symbol, symbol)


def to_generic(symbol: str) -> str:
    """
    Convertit un symbole OANDA (ex. XAU_USD) en "générique" (XAUUSD).
    Si non mappé, renvoie tel quel.
    """
    return OANDA_TO_GENERIC.get(symbol, symbol)
