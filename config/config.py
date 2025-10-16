# config/config.py
# -*- coding: utf-8 -*-
"""
Charge .env et expose quelques paramètres globaux (non spécifiques à une stratégie).
Les paramètres propres à une stratégie restent dans son fichier (ex: strategies/turtle_like.py).
"""

from __future__ import annotations
import os
from dotenv import load_dotenv

# Charge le fichier .env à la racine du projet (ne pas committer .env)
load_dotenv()

# Racine de stockage des données locales (Parquet)
# Valeurs possibles : str (chemin). Par défaut "data_local".
DATA_ROOT: str = os.getenv("DATA_ROOT", "data_local")

# Slippage par défaut pour l'engine (en unités de prix)
# Valeurs possibles : float >= 0 (ex: 0.5)
DEFAULT_SLIPPAGE: float = float(os.getenv("DEFAULT_SLIPPAGE", "0.5"))

# Commission fixe par trade (appliquée à l'ENTER + EXIT)
# Valeurs possibles : float >= 0
DEFAULT_COMMISSION: float = float(os.getenv("DEFAULT_COMMISSION", "0.0"))

# Capital initial utilisé par l’engine pour le reporting d’équity simple
# Valeurs possibles : float > 0
INITIAL_CAPITAL: float = float(os.getenv("INITIAL_CAPITAL", "1000.0"))

# Environnement OANDA : "practice" (défaut) ou "live" — utilisé si on lance du live/download
OANDA_ENV: str = os.getenv("OANDA_ENV", "practice")

# Niveau de log générique (si tu ajoutes un logger plus tard)
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
