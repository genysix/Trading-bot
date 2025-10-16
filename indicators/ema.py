def ema(close, length: int = 200, adjust: bool = False) -> pd.Series:
    """
    EMA (Exponential Moving Average) de 'close'.

    Paramètres :
    - length (int >= 1) : période de l'EMA. Classiques : 50, 100, 200, 300.
      * Valeurs possibles : entier >= 1. Plus grand => tendance plus “lente/robuste”.
    - adjust (bool) : paramètre pandas ewm(). False = pondération récursive standard.

    Retour :
    - pd.Series 'ema_{length}' alignée à 'close'.

    Remarques :
    - Les premières valeurs seront NaN jusqu’à accumuler assez d’historique effectif.
    """
    l = _validate_window(length, "length")
    c = _ensure_series(close, name="close")
    out = c.ewm(span=l, adjust=adjust).mean()
    out.name = f"ema_{l}"
    return out