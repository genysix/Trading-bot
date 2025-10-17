# indicators/donchian.py
import pandas as pd

def donchian(df: pd.DataFrame, period: int = 20):
    hi = df["high"].rolling(period, min_periods=period).max()
    lo = df["low"].rolling(period, min_periods=period).min()
    return hi, lo
