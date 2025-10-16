# strategies/turtle_like.py
# -*- coding: utf-8 -*-
"""
Stratégie Turtle-like (breakout + stops basés volatilité), version squelette.
- Paramètres par défaut inclus ICI (propres à la stratégie).
- Validation défensive des hyperparamètres.
- Implémente la logique de sortie F6 : Trailing ATR et Donchian inverse (activables séparément).
- Les entrées (breakouts) / sizing / pyramiding seront ajoutés à l’étape suivante, pour valider le squelette file-by-file.

Conventions d'I/O :
- La stratégie est agnostique des sources de données.
- Le moteur de backtest doit appeler `on_bar(bar)` séquentiellement avec des barres ordonnées.
- Une "barre" est un dict (ou objet) avec au minimum : {"time", "open", "high", "low", "close", "volume"}.
- Les indicateurs sont calculés à partir d'un tampon interne de barres (self._bars).
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Literal, Dict, Any, List
import math

try:
    import pandas as pd
    import numpy as np
except Exception as e:
    raise ImportError("Ce module nécessite pandas et numpy. Installe: pip install pandas numpy") from e


PositionSide = Literal["FLAT", "LONG", "SHORT"]


@dataclass
class TurtleParams:
    # --- PARAMÈTRES GÉNÉRAUX ---

    # Risque par trade (en fraction du capital). Valeurs possibles : float > 0.
    # Conseillé en réel: 0.005 à 0.02 (0.5% à 2%). Pour test: tu as choisi 0.05 (5%) possible mais agressif.
    RISK_PER_TRADE: float = 0.05

    # Effet de levier maximal à ne pas dépasser (contrainte logique côté exécution/backtest).
    # Valeurs possibles : float >= 1.0 (ex: 1.0 à 5.0). Tu as demandé par défaut 2.0.
    MAX_LEVERAGE: float = 2.0

    # Timeframe utilisé par cette instance (indicatif). Chaîne libre; la granularité réelle vient des données.
    # Valeurs possibles : "M1","M5","M15","H1","H4","D1","W1".
    TIMEFRAME: str = "D1"

    # --- INDICATEURS ---

    # Longueur de l'ATR (Average True Range). Entier >= 1. Classique: 14, 20, 30.
    ATR_LEN: int = 20

    # Longueur de la moyenne mobile exponentielle (filtre de tendance).
    # Entier >= 1. Classique: 100, 200, 300. Peut être ignorée si USE_TREND_FILTER=False
    EMA_TREND_LEN: int = 200

    # Activer le filtre de tendance EMA200 (True/False).
    # Si True : on considérera plus tard d’autoriser LONG seulement si close > EMA et SHORT si close < EMA.
    USE_TREND_FILTER: bool = True

    # --- SORTIES (F6) ---

    # Activer le Trailing Stop basé sur l’ATR (True/False).
    USE_TRAIL_ATR: bool = True

    # Multiple du Trailing Stop ATR. Float > 0. Plus grand = stop plus large (plus patient).
    # Exemples raisonnables: 1.5, 2.0, 2.5, 3.0
    TRAIL_K: float = 2.5

    # Activer la sortie par canal Donchian inverse (True/False).
    USE_DONCHIAN_EXIT: bool = True

    # Fenêtre Donchian pour la sortie inverse. Entier >= 2 (ex: 10, 20).
    DONCHIAN_EXIT_Y: int = 20

    # --- EXÉCUTION / COÛTS (simples placeholders, affinés côté moteur) ---

    # Modèle de slippage "per_tick" = valeur moyenne (ticks/points) ajoutée au prix de fill.
    # Peut être modélisé en moteur. Ici, on conserve la valeur comme référence.
    SLIPPAGE_PER_TICK: float = 0.5

    # Commission fixe par trade (placeholder; traité côté moteur).
    COMMISSION_PER_TRADE: float = 0.0

    # --- CONTRÔLES / SÉCURITÉ ---

    # Si True, on lève ValueError en cas de paramètre incohérent. Si False, on clamp/ajuste silencieusement.
    STRICT_VALIDATION: bool = True

    def validate(self) -> None:
        """Valide/coerce les paramètres pour éviter de tout faire planter en cas de test incohérent."""
        def _err(msg: str):
            if self.STRICT_VALIDATION:
                raise ValueError(msg)

        # RISK_PER_TRADE
        if not (isinstance(self.RISK_PER_TRADE, (int, float)) and self.RISK_PER_TRADE > 0):
            _err("RISK_PER_TRADE doit être un float > 0.")
            self.RISK_PER_TRADE = max(0.0001, float(self.RISK_PER_TRADE) if isinstance(self.RISK_PER_TRADE, (int,float)) else 0.01)

        # MAX_LEVERAGE
        if not (isinstance(self.MAX_LEVERAGE, (int, float)) and self.MAX_LEVERAGE >= 1.0):
            _err("MAX_LEVERAGE doit être >= 1.0")
            self.MAX_LEVERAGE = max(1.0, float(self.MAX_LEVERAGE) if isinstance(self.MAX_LEVERAGE, (int,float)) else 1.0)

        # ATR_LEN
        if not (isinstance(self.ATR_LEN, int) and self.ATR_LEN >= 1):
            _err("ATR_LEN doit être un entier >= 1.")
            self.ATR_LEN = int(max(1, int(self.ATR_LEN) if isinstance(self.ATR_LEN, (int,)) else 20))

        # EMA_TREND_LEN
        if not (isinstance(self.EMA_TREND_LEN, int) and self.EMA_TREND_LEN >= 1):
            _err("EMA_TREND_LEN doit être un entier >= 1.")
            self.EMA_TREND_LEN = int(max(1, int(self.EMA_TREND_LEN) if isinstance(self.EMA_TREND_LEN, (int,)) else 200))

        # TRAIL_K
        if not (isinstance(self.TRAIL_K, (int, float)) and self.TRAIL_K > 0):
            _err("TRAIL_K doit être un float > 0.")
            self.TRAIL_K = float(self.TRAIL_K) if isinstance(self.TRAIL_K, (int,float)) and self.TRAIL_K > 0 else 2.5

        # DONCHIAN_EXIT_Y
        if not (isinstance(self.DONCHIAN_EXIT_Y, int) and self.DONCHIAN_EXIT_Y >= 2):
            _err("DONCHIAN_EXIT_Y doit être un entier >= 2.")
            self.DONCHIAN_EXIT_Y = int(max(2, int(self.DONCHIAN_EXIT_Y) if isinstance(self.DONCHIAN_EXIT_Y, (int,)) else 20))

        # SLIPPAGE_PER_TICK
        if not (isinstance(self.SLIPPAGE_PER_TICK, (int, float)) and self.SLIPPAGE_PER_TICK >= 0):
            _err("SLIPPAGE_PER_TICK doit être un float >= 0.")
            self.SLIPPAGE_PER_TICK = float(self.SLIPPAGE_PER_TICK) if isinstance(self.SLIPPAGE_PER_TICK, (int,float)) and self.SLIPPAGE_PER_TICK >= 0 else 0.5

        # COMMISSION_PER_TRADE
        if not (isinstance(self.COMMISSION_PER_TRADE, (int, float)) and self.COMMISSION_PER_TRADE >= 0):
            _err("COMMISSION_PER_TRADE doit être un float >= 0.")
            self.COMMISSION_PER_TRADE = float(self.COMMISSION_PER_TRADE) if isinstance(self.COMMISSION_PER_TRADE, (int,float)) and self.COMMISSION_PER_TRADE >= 0 else 0.0


class TurtleLikeStrategy:
    """
    Implémentation squelette Turtle-like.
    - Gère un tampon de barres (pandas DataFrame) pour calculer ATR / EMA / Donchian.
    - État interne : position, prix d'entrée, stop, etc.
    - Pour l’instant : logique de SORTIE (Trailing ATR + Donchian inverse) + hooks pour ENTRÉE à venir.
    """

    def __init__(self, params: Optional[TurtleParams] = None):
        self.params = params or TurtleParams()
        self.params.validate()

        self._bars: List[Dict[str, Any]] = []
        self._df: Optional[pd.DataFrame] = None  # data consolidée pour indicateurs

        # État de position
        self.position: PositionSide = "FLAT"
        self.entry_price: Optional[float] = None
        self.stop_price: Optional[float] = None

        # Placeholders pour métriques simples
        self.closed_trades: List[Dict[str, Any]] = []

    # -------------------------
    # API publique minimaliste
    # -------------------------

    def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Appelé séquentiellement par le moteur de backtest pour chaque nouvelle barre.
        Renvoie éventuellement un ordre simulé sous forme d’un dict (ex: {"action":"EXIT","price":...})
        ou None s'il n'y a rien à exécuter sur cette barre.
        """
        self._append_bar(bar)
        if self._df is None or len(self._df) < max(self.params.ATR_LEN, self.params.DONCHIAN_EXIT_Y) + 2:
            return None  # pas assez d'historique pour indicateurs/stops

        # 1) Mettre à jour indicateurs
        self._compute_indicators()

        # 2) Gérer sorties si position ouverte
        exit_order = self._maybe_exit(bar)
        if exit_order is not None:
            return exit_order

        # 3) (Prochain commit) Générer signaux d'ENTRÉE (breakouts / filtre EMA / sizing)
        #    Pour l’instant, on ne traite que les sorties comme convenu.
        return None

    # -------------------------
    # Indicateurs & utils
    # -------------------------

    def _append_bar(self, bar: Dict[str, Any]) -> None:
        # Validation sommaire de la barre
        for key in ("time", "open", "high", "low", "close"):
            if key not in bar:
                raise KeyError(f"Bar manquante clé obligatoire: {key}")
        self._bars.append(bar)
        # mettra à jour _df au besoin
        self._df = None  # lazy rebuild

    def _compute_indicators(self) -> None:
        # Construit un DataFrame une seule fois par on_bar (lazy)
        if self._df is None:
            self._df = pd.DataFrame(self._bars)
            # Assure colonnes
            for col in ("open", "high", "low", "close"):
                self._df[col] = pd.to_numeric(self._df[col], errors="coerce")
            # ATR
            self._df["tr"] = self._true_range(self._df["high"], self._df["low"], self._df["close"])
            self._df["atr"] = self._df["tr"].rolling(window=self.params.ATR_LEN, min_periods=self.params.ATR_LEN).mean()

            # EMA pour filtre tendance
            if self.params.USE_TREND_FILTER:
                self._df["ema_trend"] = self._df["close"].ewm(span=self.params.EMA_TREND_LEN, adjust=False).mean()
            else:
                self._df["ema_trend"] = np.nan

            # Donchian pour sortie inverse
            y = self.params.DONCHIAN_EXIT_Y
            self._df["donch_low_y"] = self._df["low"].rolling(window=y, min_periods=y).min()
            self._df["donch_high_y"] = self._df["high"].rolling(window=y, min_periods=y).max()

    @staticmethod
    def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
        prev_close = close.shift(1)
        tr1 = high - low
        tr2 = (high - prev_close).abs()
        tr3 = (low - prev_close).abs()
        return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

    # -------------------------
    # Sorties (F6)
    # -------------------------

    def _maybe_exit(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Applique la logique de sortie :
        - Trailing stop ATR (optionnel)
        - Donchian inverse (optionnel)
        Logique OR : si l'une déclenche, on sort.
        """
        if self.position == "FLAT":
            return None

        df = self._df
        last = df.iloc[-1]
        close = float(last["close"])
        atr = float(last["atr"]) if not math.isnan(last["atr"]) else None

        if atr is None or atr <= 0:
            return None  # pas d’ATR => pas de trailing cohérent

        exit_by_atr = False
        exit_by_donch = False

        if self.position == "LONG":
            # Trailing ATR
            if self.params.USE_TRAIL_ATR:
                candidate_stop = close - self.params.TRAIL_K * atr
                self.stop_price = max(self.stop_price or -np.inf, candidate_stop)
                # sortie si close <= stop
                if close <= self.stop_price:
                    exit_by_atr = True

            # Donchian inverse (clôture sous le plus bas Y)
            if self.params.USE_DONCHIAN_EXIT:
                donch_low = float(last["donch_low_y"]) if not math.isnan(last["donch_low_y"]) else None
                if donch_low is not None and close < donch_low:
                    exit_by_donch = True

        elif self.position == "SHORT":
            if self.params.USE_TRAIL_ATR:
                candidate_stop = close + self.params.TRAIL_K * atr
                self.stop_price = min(self.stop_price or np.inf, candidate_stop)
                if close >= self.stop_price:
                    exit_by_atr = True

            if self.params.USE_DONCHIAN_EXIT:
                donch_high = float(last["donch_high_y"]) if not math.isnan(last["donch_high_y"]) else None
                if donch_high is not None and close > donch_high:
                    exit_by_donch = True

        if exit_by_atr or exit_by_donch:
            # On retourne un ordre de sortie (le moteur décidera du prix: close, open next, etc.)
            order = {
                "action": "EXIT",
                "reason": "TRAIL_ATR" if exit_by_atr else "DONCHIAN_INVERSE",
                "position": self.position,
                "stop_price": self.stop_price,
                "close": close,
                "time": bar.get("time")
            }
            # Reset état interne de position — le moteur confirmera réellement l’exécution
            self.position = "FLAT"
            self.entry_price = None
            self.stop_price = None
            return order

        return None

    # -------------------------
    # Hooks entrée / gestion position (à compléter étape suivante)
    # -------------------------

    def maybe_enter_long(self, entry_price: float) -> Optional[Dict[str, Any]]:
        """
        Hook d’entrée LONG (à compléter à l’étape “entrées”).
        Place aussi un stop initial basé ATR si USE_TRAIL_ATR.
        """
        if self.position != "FLAT":
            return None
        self.position = "LONG"
        self.entry_price = float(entry_price)
        self.stop_price = None
        # Stop initial cohérent (optionnel)
        if self.params.USE_TRAIL_ATR and self._df is not None:
            atr = float(self._df.iloc[-1]["atr"])
            if not math.isnan(atr) and atr > 0:
                self.stop_price = self.entry_price - self.params.TRAIL_K * atr
        return {"action": "ENTER", "side": "LONG", "price": self.entry_price}

    def maybe_enter_short(self, entry_price: float) -> Optional[Dict[str, Any]]:
        """
        Hook d’entrée SHORT (à compléter à l’étape “entrées”).
        """
        if self.position != "FLAT":
            return None
        self.position = "SHORT"
        self.entry_price = float(entry_price)
        self.stop_price = None
        if self.params.USE_TRAIL_ATR and self._df is not None:
            atr = float(self._df.iloc[-1]["atr"])
            if not math.isnan(atr) and atr > 0:
                self.stop_price = self.entry_price + self.params.TRAIL_K * atr
        return {"action": "ENTER", "side": "SHORT", "price": self.entry_price}
# Fin du fichier strategies/turtle_like.py