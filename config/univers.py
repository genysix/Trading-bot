# config/univers.py
# -*- coding: utf-8 -*-
"""
Univers d'actifs par profil (à étendre selon tes besoins).
Les noms doivent correspondre aux "symboles" attendus par la datasource ou à mapper en amont.
"""

from __future__ import annotations
from typing import Dict, List

# Profil "pilot" pour premiers tests
UNIVERSES: Dict[str, List[str]] = {
    # Metals / FX / Indices / Oil (noms OANDA ici, pour être plug-and-play)
    "pilot": ["XAU_USD", "EUR_USD", "USD_JPY", "SPX500_USD", "NAS100_USD", "UKOIL_USD", "WTICO_USD"],
    # Si tu veux un univers "gold-only" pour ton premier run :
    "gold_only": ["XAU_USD"],
}
