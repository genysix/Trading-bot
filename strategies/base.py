# strategies/base.py
# -*- coding: utf-8 -*-
"""
Interface minimale pour les stratégies.
Chaque stratégie doit implémenter on_bar(bar) et peut renvoyer des ordres {"action": "..."}.
"""

from __future__ import annotations
from typing import Optional, Dict, Any


class BaseStrategy:
    """
    Interface minimale.
    """
    def on_bar(self, bar: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Traite une nouvelle barre et peut retourner un ordre (ENTER/EXIT).
        """
        raise NotImplementedError("on_bar() doit être implémenté.")
