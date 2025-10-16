# backtest/report_text.py
# -*- coding: utf-8 -*-
"""
Génération d'un rapport texte "lisible humain" pour un backtest.

Entrées attendues :
- result : dict renvoyé par BacktestEngine.run(...)
    {
      "trades": List[Trade],                 # backtest.engine.Trade
      "equity_curve": List[{"time","equity"}],
      "final_equity": float,
      ...
    }
- df_prices : DataFrame OHLC (au moins ['time','close']) de la même période
- initial_capital : float (capital de départ)
- symbol : str (ex. "XAU_USD")
- timeframe : str (ex. "D1")

Sortie :
- str (rapport formaté)
"""

from __future__ import annotations
from typing import Dict, Any, List, Tuple, Optional
import math
import pandas as pd
from dataclasses import dataclass


# ---------------------------
# Petites structures utilitaires
# ---------------------------

@dataclass
class ReportConfig:
    # Nombre de lignes max à afficher dans "Pair Result" (si multi-symboles à l'avenir)
    MAX_PAIR_ROWS: int = 32

    # Tolérance pour considérer une journée "neutre" (rendement proche de 0)
    # Valeurs possibles : float >= 0, ex: 1e-12 pour exactitude ou 0.0001 (=0.01%)
    DAILY_NEUTRAL_EPS: float = 1e-12


# ---------------------------
# Aides math/format
# ---------------------------

def _fmt_money(x: float) -> str:
    return f"{x:,.2f} $".replace(",", " ")

def _fmt_pct(x: float) -> str:
    return f"{x*100:.2f} %"

def _fmt_pct_raw(x_pct: float) -> str:
    """x_pct attendu en % (ex: 12.34 pour 12.34%)."""
    return f"{x_pct:.2f} %"

def _safe_div(a: float, b: float) -> float:
    return (a / b) if b not in (0, 0.0) else 0.0

def _timedelta_mean(deltas: List[pd.Timedelta]) -> Optional[pd.Timedelta]:
    if not deltas:
        return None
    s = sum((d for d in deltas), pd.Timedelta(0))
    return s / len(deltas)

def _streaks(sign_series: pd.Series) -> Tuple[int, pd.Timestamp, int, pd.Timestamp]:
    """
    Calcule les plus longues séries gagnantes/perdantes (en nombre de jours)
    Retourne : (longest_win, date_fin_win, longest_loss, date_fin_loss)
    """
    lw, ll = 0, 0
    lw_end, ll_end = None, None

    cur_w, cur_l = 0, 0
    for t, s in sign_series.items():
        if s > 0:
            cur_w += 1
            cur_l = 0
            if cur_w > lw:
                lw = cur_w
                lw_end = t
        elif s < 0:
            cur_l += 1
            cur_w = 0
            if cur_l > ll:
                ll = cur_l
                ll_end = t
        else:
            # neutre -> reset des deux
            cur_w = cur_l = 0

    return lw, lw_end, ll, ll_end


# ---------------------------
# Mesures de risque
# ---------------------------

def _compute_sharpe(returns: pd.Series, periods_per_year: int = 252) -> float:
    mu = returns.mean()
    sd = returns.std(ddof=1)
    if sd == 0 or math.isnan(sd):
        return 0.0
    return float((mu / sd) * (periods_per_year ** 0.5))

def _compute_sortino(returns: pd.Series, periods_per_year: int = 252) -> float:
    # downside deviation
    downside = returns[returns < 0]
    dd = downside.std(ddof=1)
    mu = returns.mean()
    if dd == 0 or math.isnan(dd):
        return 0.0
    return float((mu / dd) * (periods_per_year ** 0.5))

def _compute_cagr_and_dd(equity_df: pd.DataFrame) -> Tuple[float, float]:
    """
    CAGR et Max Drawdown (sur la courbe passée telle quelle).
    equity_df : DataFrame avec colonnes ["time","equity"]
    """
    if len(equity_df) < 2:
        return 0.0, 0.0
    start_eq = float(equity_df["equity"].iloc[0])
    end_eq = float(equity_df["equity"].iloc[-1])
    days = (pd.to_datetime(equity_df["time"].iloc[-1]) - pd.to_datetime(equity_df["time"].iloc[0])).days
    years = max(days / 365.25, 1e-9)
    cagr = (end_eq / start_eq) ** (1.0 / years) - 1.0 if start_eq > 0 else 0.0

    roll_max = equity_df["equity"].cummax()
    dd = equity_df["equity"] / roll_max - 1.0
    max_dd = float(dd.min())  # négatif
    return float(cagr), float(max_dd)

def _max_drawdown_daily(equity_df: pd.DataFrame) -> float:
    """
    Max drawdown basé sur equity quotidienne (EOD).
    """
    x = equity_df.copy()
    x["date"] = pd.to_datetime(x["time"]).dt.floor("D")
    daily = x.groupby("date", as_index=False).last()
    roll_max = daily["equity"].cummax()
    dd = daily["equity"] / roll_max - 1.0
    return float(dd.min())


# ---------------------------
# Buy & Hold
# ---------------------------

def _buy_and_hold_perf(df_prices: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> float:
    """
    Renvoie la performance buy&hold en % sur [start, end] basée sur 'close'.
    """
    z = df_prices[(df_prices["time"] >= start) & (df_prices["time"] <= end)].reset_index(drop=True)
    if len(z) < 2:
        return 0.0
    p0 = float(z["close"].iloc[0])
    p1 = float(z["close"].iloc[-1])
    return (p1 / p0 - 1.0) * 100.0


# ---------------------------
# Rapport principal
# ---------------------------

def generate_text_report(
    *,
    result: Dict[str, Any],
    df_prices: pd.DataFrame,
    initial_capital: float,
    symbol: str,
    timeframe: str,
    cfg: Optional[ReportConfig] = None
) -> str:
    cfg = cfg or ReportConfig()

    trades = result.get("trades", [])
    eq_curve = pd.DataFrame(result.get("equity_curve", []))
    final_equity = float(result.get("final_equity", initial_capital))

    # Bornes de période (d'après df_prices, plus fiable)
    start_ts = pd.to_datetime(df_prices["time"].iloc[0])
    end_ts = pd.to_datetime(df_prices["time"].iloc[-1])

    # Perf brute stratégie
    perf_total = (final_equity / initial_capital - 1.0) * 100.0

    # Buy & Hold
    bh_pct = _buy_and_hold_perf(df_prices, start_ts, end_ts)
    # Perf vs buy&hold := (Final / (Initial * (1+BH))) - 1
    perf_vs_bh = final_equity / (initial_capital * (1.0 + bh_pct / 100.0)) - 1.0
    perf_vs_bh_pct = perf_vs_bh * 100.0

    # Equity returns (bar-by-bar) pour Sharpe/Sortino sur base quotidienne approx
    eq = eq_curve.copy()
    if len(eq) >= 2:
        eq["ret"] = eq["equity"].pct_change().fillna(0.0)
    else:
        eq["ret"] = 0.0

    # Regrouper par jour pour stats "Days Informations"
    eq["date"] = pd.to_datetime(eq["time"]).dt.floor("D")
    daily = eq.groupby("date", as_index=False).last()
    daily["dret"] = daily["equity"].pct_change().fillna(0.0)

    # Ratios Sharpe / Sortino (annualisés sur 252 jours)
    sharpe = _compute_sharpe(daily["dret"])
    sortino = _compute_sortino(daily["dret"])

    # CAGR et MaxDD (T) + MaxDD (D)
    cagr, maxdd_T = _compute_cagr_and_dd(eq_curve) if len(eq_curve) else (0.0, 0.0)
    maxdd_D = _max_drawdown_daily(eq_curve) if len(eq_curve) else 0.0

    # Calmar = CAGR / |MaxDD (T)|
    calmar = _safe_div(cagr, abs(maxdd_T)) if maxdd_T < 0 else 0.0

    # Trades : stats
    nb_trades = len(trades)
    wins = [t for t in trades if t.pnl > 0]
    losses = [t for t in trades if t.pnl < 0]
    win_rate = _safe_div(len(wins), nb_trades) * 100.0

    # % par trade (par rapport au prix d’entrée)
    def _trade_ret_pct(t) -> float:
        # direction LONG: (exit/entry - 1) ; SHORT: (entry/exit - 1)
        if t.side == "LONG":
            return (t.exit_price / t.entry_price - 1.0) * 100.0
        else:
            return (t.entry_price / t.exit_price - 1.0) * 100.0

    trade_pcts = [_trade_ret_pct(t) for t in trades]
    avg_profit_pct = sum(trade_pcts) / nb_trades if nb_trades else 0.0

    # Durées de trades
    durations = [pd.to_datetime(t.exit_time) - pd.to_datetime(t.entry_time) for t in trades]
    mean_duration = _timedelta_mean(durations)

    good_trades = [t for t in trades if t.pnl > 0]
    bad_trades = [t for t in trades if t.pnl < 0]

    good_pcts = [_trade_ret_pct(t) for t in good_trades]
    bad_pcts  = [_trade_ret_pct(t) for t in bad_trades]

    mean_good_pct = (sum(good_pcts) / len(good_pcts)) if good_pcts else 0.0
    mean_bad_pct  = (sum(bad_pcts) / len(bad_pcts)) if bad_pcts else 0.0

    mean_good_duration = _timedelta_mean([pd.to_datetime(t.exit_time) - pd.to_datetime(t.entry_time) for t in good_trades]) if good_trades else None
    mean_bad_duration  = _timedelta_mean([pd.to_datetime(t.exit_time) - pd.to_datetime(t.entry_time) for t in bad_trades]) if bad_trades else None

    # Best/Worst trades (par %)
    best_t = None
    worst_t = None
    if trades:
        best_t = max(trades, key=_trade_ret_pct)
        worst_t = min(trades, key=_trade_ret_pct)

    # Jours (winning / neutral / losing)
    neutral_eps = cfg.DAILY_NEUTRAL_EPS
    day_wins = (daily["dret"] >  neutral_eps).sum()
    day_neut = (daily["dret"].abs() <= neutral_eps).sum()
    day_loss = (daily["dret"] < -neutral_eps).sum()
    total_days = len(daily)

    # Best/worst day (%)
    best_day_idx = daily["dret"].idxmax() if total_days else None
    worst_day_idx = daily["dret"].idxmin() if total_days else None
    best_day_dt = daily.loc[best_day_idx, "date"] if total_days else None
    worst_day_dt = daily.loc[worst_day_idx, "date"] if total_days else None
    best_day_pct = daily.loc[best_day_idx, "dret"] * 100.0 if total_days else 0.0
    worst_day_pct = daily.loc[worst_day_idx, "dret"] * 100.0 if total_days else 0.0

    # Streaks (séquences de jours >0, <0)
    sign_series = daily.set_index("date")["dret"].apply(lambda x: 1 if x > neutral_eps else (-1 if x < -neutral_eps else 0))
    lw, lw_end, ll, ll_end = _streaks(sign_series)

    # Mean trades per day
    mean_trades_per_day = _safe_div(nb_trades, total_days)

    # Entrées/Sorties par type (actuellement, on n’a que market via engine ; on compte long/short)
    longs = [t for t in trades if t.side == "LONG"]
    shorts = [t for t in trades if t.side == "SHORT"]

    # Pair Result (tableau simplifié par symbole)
    # sum-result = somme des % de trades (approche "moyenne" — à affiner si tu veux une autre définition)
    sum_result_pct = sum(trade_pcts)
    worst_trade_pct = min(trade_pcts) if trade_pcts else 0.0
    best_trade_pct  = max(trade_pcts) if trade_pcts else 0.0

    # Construction du texte
    lines: List[str] = []

    # En-tête période / wallet
    lines.append(f"Period: [{start_ts}] -> [{end_ts}]")
    lines.append(f"Initial wallet: {_fmt_money(initial_capital)}")
    lines.append("")
    lines.append("--- General Information ---")
    lines.append(f"Final wallet: {_fmt_money(final_equity)}")
    lines.append(f"Performance: {_fmt_pct_raw(perf_total)}")
    lines.append(f"Sharpe Ratio: {sharpe:.2f} | Sortino Ratio: {sortino:.2f} | Calmar Ratio: {calmar:.2f}")
    lines.append(f"Worst Drawdown T|D: {_fmt_pct(maxdd_T)} | {_fmt_pct(maxdd_D)}")
    lines.append(f"Buy and hold performance: {_fmt_pct_raw(bh_pct)}")
    lines.append(f"Performance vs buy and hold: {_fmt_pct_raw(perf_vs_bh_pct)}")
    lines.append(f"Total trades on the period: {nb_trades}")
    lines.append(f"Average Profit: {_fmt_pct_raw(avg_profit_pct)}")
    lines.append(f"Global Win rate: {_fmt_pct_raw(win_rate)}")
    lines.append("")
    lines.append("--- Trades Information ---")
    lines.append(f"Mean Trades per day: {mean_trades_per_day:.1f}")
    lines.append(f"Mean Trades Duration: {str(mean_duration) if mean_duration is not None else 'NA'}")

    if best_t is not None:
        best_pct = _trade_ret_pct(best_t)
        lines.append(f"Best trades: {best_pct:+.2f} % the {pd.to_datetime(best_t.entry_time)} -> {pd.to_datetime(best_t.exit_time)} ({timeframe}-{symbol})")
    else:
        lines.append("Best trades: NA")

    if worst_t is not None:
        worst_pct2 = _trade_ret_pct(worst_t)
        lines.append(f"Worst trades: {worst_pct2:+.2f} % the {pd.to_datetime(worst_t.entry_time)} -> {pd.to_datetime(worst_t.exit_time)} ({timeframe}-{symbol})")
    else:
        lines.append("Worst trades: NA")

    lines.append(f"Total Good trades on the period: {len(good_trades)}")
    lines.append(f"Total Bad trades on the period: {len(bad_trades)}")
    lines.append(f"Average Good Trades result: {_fmt_pct_raw(mean_good_pct)}")
    lines.append(f"Average Bad Trades result: {_fmt_pct_raw(mean_bad_pct)}")
    lines.append(f"Mean Good Trades Duration: {str(mean_good_duration) if mean_good_duration is not None else 'NA'}")
    lines.append(f"Mean Bad Trades Duration: {str(mean_bad_duration) if mean_bad_duration is not None else 'NA'}")
    lines.append("")
    lines.append("--- Days Informations ---")
    lines.append(f"Total: {total_days} days recorded")
    lines.append(f"Winning days: {day_wins} days ({_fmt_pct_raw(_safe_div(day_wins, total_days)*100.0)})")
    lines.append(f"Neutral days: {day_neut} days ({_fmt_pct_raw(_safe_div(day_neut, total_days)*100.0)})")
    lines.append(f"Loosing days: {day_loss} days ({_fmt_pct_raw(_safe_div(day_loss, total_days)*100.0)})")
    lines.append(f"Longest winning streak: {lw} days ({lw_end if lw_end is not None else 'NA'})")
    lines.append(f"Longest loosing streak: {ll} days ({ll_end if ll_end is not None else 'NA'})")
    lines.append(f"Best day: {best_day_dt} ({best_day_pct:+.2f}%)")
    lines.append(f"Worst day: {worst_day_dt} ({worst_day_pct:+.2f}%)")

    if len(longs) == 0 and len(shorts) == 0:
        lines.append("!!! No long or short trades found")
    lines.append("")
    lines.append("---------------- Entries ----------------")
    lines.append(f"LONG - Market              {len(longs)} ({_fmt_pct_raw(_safe_div(len(longs), nb_trades)*100.0) if nb_trades else '0.00 %'})")
    lines.append(f"SHORT - Market             {len(shorts)} ({_fmt_pct_raw(_safe_div(len(shorts), nb_trades)*100.0) if nb_trades else '0.00 %'})")
    lines.append("----------------- Exits -----------------")
    # Dans notre engine, toutes les sorties sont Market
    lines.append(f"LONG - Market              {len(longs)} ({_fmt_pct_raw(_safe_div(len(longs), nb_trades)*100.0) if nb_trades else '0.00 %'})")
    lines.append(f"SHORT - Market             {len(shorts)} ({_fmt_pct_raw(_safe_div(len(shorts), nb_trades)*100.0) if nb_trades else '0.00 %'})")
    lines.append("----------------------------------------")
    lines.append("")
    lines.append("--- Pair Result ---")
    lines.append("-----------------------------------------------------------------------------------------------")
    lines.append("Trades      Pair     Sum-result     Mean-trade    Worst-trade     Best-trade       Win-rate")
    lines.append("-----------------------------------------------------------------------------------------------")

    # Ligne unique pour l’instant (un symbole) — extensible plus tard
    mean_trade_pct = avg_profit_pct
    win_rate_pair = win_rate
    lines.append(f"{nb_trades:<9d} {timeframe}-{symbol:<15} {sum_result_pct:>10.2f} %     {mean_trade_pct:>8.2f} %     {worst_trade_pct:>8.2f} %     {best_trade_pct:>8.2f} %     {win_rate_pair:>10.2f} %")

    return "\n".join(lines)
