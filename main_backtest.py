# --- PATH SAFETY HEADER ---
from __future__ import annotations
import sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
# -----------------------------------------------------------

from backtest.report_text import generate_text_report

report = generate_text_report(
    result=result,
    df_prices=df,                # le DataFrame OHLC chargé
    initial_capital=args.capital,
    symbol=args.symbol,
    timeframe=args.timeframe
)
print(report)

if __name__ == "__main__":
    main()