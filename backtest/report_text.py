# backtest/report_text.py
from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Any, Optional, Tuple
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# --------------------------------------------
# Helpers numériques / formatage
# --------------------------------------------
def _pct(x: float, digits: int = 2) -> str:
    return f"{x:.{digits}f} %"

def _money(x: float, digits: int = 2) -> str:
    return f"{x:,.{digits}f} $"

def _fmt_dt(x) -> str:
    if pd.isna(x) or x is None:
        return "N/A"
    if isinstance(x, (pd.Timestamp, datetime)):
        return x.replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")
    return str(x)

# --------------------------------------------
# Paires de trades (BUY -> SELL)
# --------------------------------------------
@dataclass
class TradePair:
    entry_time: Optional[pd.Timestamp]
    exit_time: Optional[pd.Timestamp]
    entry_price: float
    exit_price: float
    qty: float
    ret_pct: float
    duration: pd.Timedelta

def _pair_trades(trades: List[Dict[str, Any]]) -> List[TradePair]:
    """
    Attendu: trades list with dicts: {"time", "type": BUY/SELL, "price", "qty"}
    Retour: liste de TradePair complétés (BUY puis SELL). Les positions partielles ne sont pas gérées (= minimal viable).
    """
    pairs: List[TradePair] = []
    buf_buy: Optional[Dict[str, Any]] = None
    for t in trades:
        t_time = pd.to_datetime(t.get("time"))
        t_type = t.get("type", "").upper()
        price = float(t.get("price", np.nan))
        qty = float(t.get("qty", 0.0))

        if t_type == "BUY" and buf_buy is None:
            buf_buy = {"time": t_time, "price": price, "qty": qty}
        elif t_type == "SELL" and buf_buy is not None:
            # fermeture totale supposée
            entry_price = float(buf_buy["price"])
            exit_price = price
            ret = (exit_price - entry_price) / entry_price * 100.0
            duration = t_time - buf_buy["time"]
            pairs.append(
                TradePair(
                    entry_time=buf_buy["time"],
                    exit_time=t_time,
                    entry_price=entry_price,
                    exit_price=exit_price,
                    qty=buf_buy["qty"],
                    ret_pct=ret,
                    duration=duration if isinstance(duration, pd.Timedelta) else pd.Timedelta(seconds=0),
                )
            )
            buf_buy = None
        else:
            # autres cas: on ignore (ex: BUY alors qu'une position est déjà ouverte)
            pass
    return pairs

# --------------------------------------------
# Drawdown (profondeur et durée max)
# --------------------------------------------
@dataclass
class DDStats:
    max_depth: float            # ex: -25.64 (%)
    max_duration_days: float    # ex: 24.17 (jours)

def _drawdown_stats(equity: pd.Series) -> DDStats:
    # profondeur
    roll_max = equity.cummax()
    dd = equity / roll_max - 1.0
    max_depth = float(dd.min() * 100.0) if len(dd) else 0.0

    # durée (peak -> recovery)
    # On mesure la plus longue séquence où equity reste sous son cumul max précédent
    duration = 0
    max_duration = 0
    for i in range(1, len(equity)):
        if equity.iloc[i] < roll_max.iloc[i]:
            duration += 1
            max_duration = max(max_duration, duration)
        else:
            duration = 0
    return DDStats(max_depth=max_depth, max_duration_days=float(max_duration))

# --------------------------------------------
# Ratios (Sharpe / Sortino / Calmar)
# --------------------------------------------
def _sharpe(ret_daily: pd.Series, rf: float = 0.0) -> float:
    # ret_daily en décimal (ex: 0.001 = 0.1%)
    mu = ret_daily.mean() - rf / 252.0
    sd = ret_daily.std(ddof=0)
    if sd == 0 or np.isnan(sd):
        return 0.0
    return float(mu / sd * np.sqrt(252))

def _sortino(ret_daily: pd.Series, rf: float = 0.0) -> float:
    downside = ret_daily[ret_daily < 0]
    dd = downside.std(ddof=0)
    mu = ret_daily.mean() - rf / 252.0
    if dd == 0 or np.isnan(dd):
        return 0.0
    return float(mu / dd * np.sqrt(252))

def _calmar(equity: pd.Series) -> float:
    if equity.empty:
        return 0.0
    ret_daily = equity.pct_change().dropna()
    cagr = (equity.iloc[-1] / equity.iloc[0]) ** (252.0 / max(1, len(ret_daily))) - 1.0
    roll_max = equity.cummax()
    dd = equity / roll_max - 1.0
    max_dd = abs(float(dd.min()))
    if max_dd == 0:
        return 0.0
    return float(cagr / max_dd)

# --------------------------------------------
# Statistiques journalières
# --------------------------------------------
@dataclass
class DayStats:
    total_days: int
    win_days: int
    neutral_days: int
    lose_days: int
    best_day_dt: Optional[pd.Timestamp]
    best_day_ret: float
    worst_day_dt: Optional[pd.Timestamp]
    worst_day_ret: float
    longest_win_streak_len: int
    longest_win_streak_end: Optional[pd.Timestamp]
    longest_lose_streak_len: int
    longest_lose_streak_end: Optional[pd.Timestamp]

def _day_stats(equity: pd.Series, neutral_eps: float = 1e-12) -> DayStats:
    if equity.empty:
        return DayStats(0,0,0,0,None,0.0,None,0.0,0,None,0,None)
    daily = equity.resample("1D").last().dropna()
    ret = daily.pct_change().dropna() * 100.0

    win = (ret > neutral_eps).sum()
    lose = (ret < -neutral_eps).sum()
    neutral = len(ret) - win - lose

    best_idx = ret.idxmax() if len(ret) else None
    worst_idx = ret.idxmin() if len(ret) else None
    best_val = float(ret.max()) if len(ret) else 0.0
    worst_val = float(ret.min()) if len(ret) else 0.0

    # streaks
    longest_win = 0; cur_win = 0; end_win = None
    longest_lose = 0; cur_lose = 0; end_lose = None
    for dt, v in ret.items():
        if v > neutral_eps:
            cur_win += 1
            cur_lose = 0
        elif v < -neutral_eps:
            cur_lose += 1
            cur_win = 0
        else:
            cur_win = 0; cur_lose = 0

        if cur_win > longest_win:
            longest_win = cur_win
            end_win = dt
        if cur_lose > longest_lose:
            longest_lose = cur_lose
            end_lose = dt

    return DayStats(
        total_days=len(daily),
        win_days=int(win),
        neutral_days=int(neutral),
        lose_days=int(lose),
        best_day_dt=best_idx,
        best_day_ret=float(best_val),
        worst_day_dt=worst_idx,
        worst_day_ret=float(worst_val),
        longest_win_streak_len=int(longest_win),
        longest_win_streak_end=end_win,
        longest_lose_streak_len=int(longest_lose),
        longest_lose_streak_end=end_lose
    )

# --------------------------------------------
# Rapport principal
# --------------------------------------------
def generate_text_report(
    result: Dict[str, Any],
    df_prices: pd.DataFrame,
    initial_capital: float,
    symbol: str,
    timeframe: str,
    metrics: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Rend un texte strictement formaté comme demandé par l'utilisateur.
    Hypothèses:
      - result["trades"] : liste BUY/SELL (voir BacktestEngine)
      - result["equity_curve"] : DataFrame avec colonnes ["time","equity"]
      - df_prices : OHLC avec colonne 'time' ou index DatetimeIndex
    """

    # --- périodes
    # On privilégie df_prices['time'] si présent, sinon index
    if "time" in df_prices.columns:
        start_dt = pd.to_datetime(df_prices["time"].iloc[0])
        end_dt   = pd.to_datetime(df_prices["time"].iloc[-1])
        first_close = float(df_prices["close"].iloc[0])
        last_close  = float(df_prices["close"].iloc[-1])
    else:
        start_dt = pd.to_datetime(df_prices.index[0])
        end_dt   = pd.to_datetime(df_prices.index[-1])
        first_close = float(df_prices["close"].iloc[0])
        last_close  = float(df_prices["close"].iloc[-1])

    # --- equity & rendements
    eq_df = result.get("equity_curve", pd.DataFrame())
    if not eq_df.empty and "equity" in eq_df.columns:
        eq = eq_df.set_index(pd.to_datetime(eq_df["time"]))["equity"].astype(float)
    else:
        # fallback si equity_curve absent: buy&hold sur capital initial (déconseillé, mais permissif)
        scale = initial_capital / max(1e-12, first_close)
        eq = pd.Series(scale * df_prices["close"].values, index=pd.to_datetime(df_prices["time"] if "time" in df_prices.columns else df_prices.index))
    ret_daily = eq.pct_change().dropna()

    # --- drawdowns & ratios
    dd = _drawdown_stats(eq)
    sharpe = _sharpe(ret_daily)
    sortino = _sortino(ret_daily)
    calmar = _calmar(eq)

    # --- performances
    final_equity = float(eq.iloc[-1])
    perf_pct = (final_equity / initial_capital - 1.0) * 100.0
    buy_hold_pct = (last_close / first_close - 1.0) * 100.0
    perf_vs_bh = perf_pct - buy_hold_pct

    # --- trades
    trades = result.get("trades", [])
    pairs = _pair_trades(trades)
    n_trades = len(pairs)
    avg_profit = float(np.mean([t.ret_pct for t in pairs])) if n_trades else 0.0
    win_count = sum(1 for t in pairs if t.ret_pct > 0)
    lose_count = sum(1 for t in pairs if t.ret_pct <= 0)
    win_rate = (win_count / n_trades * 100.0) if n_trades else 0.0

    # best / worst trade
    if n_trades:
        best = max(pairs, key=lambda t: t.ret_pct)
        worst = min(pairs, key=lambda t: t.ret_pct)
        mean_duration = sum((t.duration for t in pairs), pd.Timedelta(0)) / n_trades
        good_pairs = [t for t in pairs if t.ret_pct > 0]
        bad_pairs = [t for t in pairs if t.ret_pct <= 0]
        avg_good = float(np.mean([t.ret_pct for t in good_pairs])) if good_pairs else 0.0
        avg_bad = float(np.mean([t.ret_pct for t in bad_pairs])) if bad_pairs else 0.0
        mean_good_dur = sum((t.duration for t in good_pairs), pd.Timedelta(0)) / len(good_pairs) if good_pairs else pd.Timedelta(0)
        mean_bad_dur = sum((t.duration for t in bad_pairs), pd.Timedelta(0)) / len(bad_pairs) if bad_pairs else pd.Timedelta(0)
    else:
        best = worst = None
        mean_duration = pd.Timedelta(0)
        avg_good = avg_bad = 0.0
        mean_good_dur = mean_bad_dur = pd.Timedelta(0)

    # mean trades / day
    total_days = max(1, (end_dt.normalize() - start_dt.normalize()).days + 1)
    mean_trades_per_day = n_trades / total_days if total_days > 0 else 0.0

    # --- stats journalières
    dstats = _day_stats(eq)

    # --- sections Entrées/Sorties (type & side)
    # Dans ce moteur minimal: LONG - Market uniquement
    count_buy = sum(1 for t in trades if t.get("type", "").upper() == "BUY")
    count_sell = sum(1 for t in trades if t.get("type", "").upper() == "SELL")

    # --- Pair Result (une ligne par (timeframe, symbol))
    # Ici, une seule paire: f"{timeframe}-{symbol}"
    if n_trades:
        sum_result = float(np.sum([t.ret_pct for t in pairs]))
        mean_trade = float(np.mean([t.ret_pct for t in pairs]))
        worst_trade = float(np.min([t.ret_pct for t in pairs]))
        best_trade = float(np.max([t.ret_pct for t in pairs]))
        line_pair = {
            "Trades": n_trades,
            "Pair": f"{timeframe}-{symbol}",
            "Sum-result": sum_result,
            "Mean-trade": mean_trade,
            "Worst-trade": worst_trade,
            "Best-trade": best_trade,
            "Win-rate": win_rate,
        }
    else:
        line_pair = {
            "Trades": 0,
            "Pair": f"{timeframe}-{symbol}",
            "Sum-result": 0.0,
            "Mean-trade": 0.0,
            "Worst-trade": 0.0,
            "Best-trade": 0.0,
            "Win-rate": 0.0,
        }

    # --------------------------------------------
    # Construction du rendu EXACT demandé
    # --------------------------------------------
    out = []

    # En-tête période & capital initial
    out.append(f"Period: [{_fmt_dt(start_dt)}] -> [{_fmt_dt(end_dt)}]")
    out.append(f"Initial wallet: {_money(initial_capital)}")
    out.append("")

    # --- General Information ---
    out.append("--- General Information ---")
    out.append(f"Final wallet: {_money(final_equity)}")
    out.append(f"Performance: {_pct(perf_pct)}")
    out.append(f"Sharpe Ratio: {sharpe:.2f} | Sortino Ratio: {sortino:.2f} | Calmar Ratio: {calmar:.2f}")
    out.append(f"Worst Drawdown T|D: {_pct(dd.max_depth)} | -{dd.max_duration_days:.2f}%".replace("%", "") + "%")
    out.append(f"Buy and hold performance: {_pct(buy_hold_pct)}")
    out.append(f"Performance vs buy and hold: {_pct(perf_vs_bh)}")
    out.append(f"Total trades on the period: {n_trades}")
    out.append(f"Average Profit: {_pct(avg_profit)}")
    out.append(f"Global Win rate: {_pct(win_rate)}")
    out.append("")

    # --- Trades Information ---
    out.append("--- Trades Information ---")
    out.append(f"Mean Trades per day: {mean_trades_per_day:.1f}")
    out.append(f"Mean Trades Duration: {str(mean_duration)}")
    if best is not None:
        out.append(
            f"Best trades: +{abs(best.ret_pct):.2f} % the {_fmt_dt(best.entry_time)} -> {_fmt_dt(best.exit_time)} "
            f"({timeframe}-{symbol})"
        )
    else:
        out.append("Best trades: N/A")
    if worst is not None:
        sign = "-" if worst.ret_pct < 0 else "+"
        out.append(
            f"Worst trades: {sign}{abs(worst.ret_pct):.2f} % the {_fmt_dt(worst.entry_time)} -> {_fmt_dt(worst.exit_time)} "
            f"({timeframe}-{symbol})"
        )
    else:
        out.append("Worst trades: N/A")
    out.append(f"Total Good trades on the period: {win_count}")
    out.append(f"Total Bad trades on the period: {lose_count}")
    out.append(f"Average Good Trades result: {_pct(avg_good)}")
    out.append(f"Average Bad Trades result: {_pct(avg_bad)}")
    out.append(f"Mean Good Trades Duration: {str(mean_good_dur)}")
    out.append(f"Mean Bad Trades Duration: {str(mean_bad_dur)}")
    out.append("")

    # --- Days Informations ---
    out.append("--- Days Informations ---")
    out.append(f"Total: {dstats.total_days} days recorded")
    if dstats.total_days > 0:
        win_pct = dstats.win_days / dstats.total_days * 100.0
        neutral_pct = dstats.neutral_days / dstats.total_days * 100.0
        lose_pct = dstats.lose_days / dstats.total_days * 100.0
    else:
        win_pct = neutral_pct = lose_pct = 0.0
    out.append(f"Winning days: {dstats.win_days} days ({win_pct:.2f}%)")
    out.append(f"Neutral days: {dstats.neutral_days} days ({neutral_pct:.2f}%)")
    out.append(f"Loosing days: {dstats.lose_days} days ({lose_pct:.2f}%)")
    out.append(f"Longest winning streak: {dstats.longest_win_streak_len} days ({_fmt_dt(dstats.longest_win_streak_end)})")
    out.append(f"Longest loosing streak: {dstats.longest_lose_streak_len} days ({_fmt_dt(dstats.longest_lose_streak_end)})")
    out.append(f"Best day: {_fmt_dt(dstats.best_day_dt)} ({_pct(dstats.best_day_ret)})")
    out.append(f"Worst day: {_fmt_dt(dstats.worst_day_dt)} ({_pct(dstats.worst_day_ret)})")
    # Message final si aucune position long/short détectée (selon ton exemple)
    if count_buy == 0 and count_sell == 0:
        out.append("!!! No long or short trades found")
    out.append("")

    # ---------------- Entries ----------------
    out.append("---------------- Entries ----------------")
    out.append(f"LONG - Market              {count_buy} (100.0%)" if count_buy else "LONG - Market              0 (0.0%)")
    # ----------------- Exits -----------------
    out.append("----------------- Exits -----------------")
    out.append(f"LONG - Market              {count_sell} (100.0%)" if count_sell else "LONG - Market              0 (0.0%)")
    out.append("----------------------------------------")
    out.append("")

    # --- Pair Result ---
    out.append("--- Pair Result ---")
    out.append("-----------------------------------------------------------------------------------------------")
    out.append("Trades      Pair     Sum-result     Mean-trade    Worst-trade     Best-trade       Win-rate")
    out.append("-----------------------------------------------------------------------------------------------")
    out.append(
        f"{line_pair['Trades']:<5}   {line_pair['Pair']:<15}"
        f"{line_pair['Sum-result']:>10.2f} %        {line_pair['Mean-trade']:>6.2f} %"
        f"        {line_pair['Worst-trade']:>6.2f} %        {line_pair['Best-trade']:>6.2f} %"
        f"        {line_pair['Win-rate']:>6.2f} %"
    )

    return "\n".join(out)
