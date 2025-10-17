# indicators/atr.py
import pandas as pd
import numpy as np

def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = df["high"].values, df["low"].values, df["close"].shift(1).values
    tr = np.maximum(h - l, np.maximum(abs(h - c), abs(l - c)))
    atr = pd.Series(tr, index=df.index).ewm(alpha=1/period, adjust=False).mean()
    return atr
