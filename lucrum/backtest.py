"""Bar-by-bar backtester using the same strategy objects as the live engine.

Signals are computed on a bar's close and filled at the NEXT bar's open (no look-ahead).
Stops are checked against each bar's low; if a bar gaps below the stop, it fills at the open.
"""
from __future__ import annotations

import argparse
import math

import numpy as np
import pandas as pd

from . import data
from .config import StrategyConfig
from .indicators import compute_all
from .strategy import LegacyBollinger, MeanReversionV2, Position, Trade


def run(df: pd.DataFrame, strat, product: str = "", cash: float = 10_000.0) -> dict:
    cfg = strat.cfg
    ind = compute_all(df, cfg)
    fee = cfg.fee_rate
    pos: Position | None = None
    pending = None  # (action, signal) to fill at next open
    trades: list[Trade] = []
    equity_curve = []
    entry_cost = 0.0
    rows = list(ind.itertuples())
    cols = list(ind.columns)

    def as_series(r):
        return pd.Series(dict(zip(cols, r[1:])))

    for i, r in enumerate(rows):
        t = int(r.Index)
        # 1) fill orders decided on the previous bar
        if pending is not None:
            action, sig = pending
            pending = None
            px = r.open
            if action == "buy" and pos is None:
                # keep the signal's stop *distance*, re-anchored to the actual fill price
                has_stop = not math.isnan(sig.stop) and sig.stop > 0
                stop = px - (rows[i - 1].close - sig.stop) if has_stop else 0.0
                qty = strat.size(cash, cash, px, stop)
                if qty * px > 1:
                    f = qty * px * fee
                    cash -= qty * px + f
                    entry_cost = qty * px + f
                    pos = Position(qty, px, t, stop)
                    trades.append(Trade(product, "buy", t, px, qty, f, sig.reason))
            elif action == "sell" and pos is not None:
                cash, pos = _close(pos, px, t, fee, cash, entry_cost, trades, product, sig.reason)

        # 2) intrabar stop
        if pos is not None and pos.stop > 0 and strat.stop_hit(pos, r.low):
            px = min(r.open, pos.stop)
            cash, pos = _close(pos, px, t, fee, cash, entry_cost, trades, product, "stop loss")

        # 3) evaluate on close
        if pos is not None:
            pos.bars_held += 1
        if i + 1 >= strat.warmup():
            sig = strat.on_bar(as_series(r), pos)
            if sig.action in ("buy", "sell"):
                pending = (sig.action, sig)

        mark = cash + (pos.qty * r.close if pos else 0)
        equity_curve.append((t, mark))

    if pos is not None:  # mark-to-market close at the end
        cash, pos = _close(pos, rows[-1].close, int(rows[-1].Index), fee, cash, entry_cost, trades, product, "end of test")
        equity_curve[-1] = (equity_curve[-1][0], cash)

    return {"trades": trades, "equity": equity_curve, "metrics": metrics(equity_curve, trades, df), "indicators": ind}


def _close(pos, px, t, fee, cash, entry_cost, trades, product, reason):
    proceeds = pos.qty * px
    f = proceeds * fee
    cash += proceeds - f
    trades.append(Trade(product, "sell", t, px, pos.qty, f, reason, pnl=proceeds - f - entry_cost))
    return cash, None


def metrics(equity_curve, trades, df) -> dict:
    eq = pd.Series([e for _, e in equity_curve], dtype=float)
    start, end = eq.iloc[0], eq.iloc[-1]
    rets = eq.pct_change().dropna()
    bar_secs = int(df.index[1] - df.index[0]) if len(df) > 1 else 60
    periods_per_year = 365 * 24 * 3600 / bar_secs
    sharpe = float(rets.mean() / rets.std() * math.sqrt(periods_per_year)) if rets.std() > 0 else 0.0
    dd = float((eq / eq.cummax() - 1).min())
    sells = [t for t in trades if t.side == "sell"]
    wins = [t for t in sells if (t.pnl or 0) > 0]
    buy_hold = float(df["close"].iloc[-1] / df["close"].iloc[0] - 1)
    return {
        "return_pct": float((end / start - 1) * 100),
        "buy_hold_pct": buy_hold * 100,
        "sharpe": sharpe,
        "max_drawdown_pct": dd * 100,
        "trades": len(sells),
        "win_rate_pct": (len(wins) / len(sells) * 100) if sells else 0.0,
        "fees_paid": float(sum(t.fee for t in trades)),
        "avg_trade_pnl": float(np.mean([t.pnl for t in sells])) if sells else 0.0,
    }


def compare(product: str, granularity: int, bars: int, cfg: StrategyConfig | None = None) -> dict:
    cfg = cfg or StrategyConfig()
    df = data.candles(product, granularity, bars)
    out = {"product": product, "granularity": granularity, "bars": len(df)}
    for strat in (MeanReversionV2(cfg), LegacyBollinger(cfg)):
        res = run(df, strat, product)
        out[strat.name] = res
    return out


def main():
    ap = argparse.ArgumentParser(description="Backtest v2 vs the legacy Bollinger rules")
    ap.add_argument("products", nargs="*", default=["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "XRP-USD"])
    ap.add_argument("--granularity", type=int, default=60)
    ap.add_argument("--bars", type=int, default=2880)
    ap.add_argument("--fee", type=float, default=StrategyConfig.fee_rate)
    a = ap.parse_args()
    cfg = StrategyConfig(fee_rate=a.fee)
    hdr = f"{'product':10} {'strat':7} {'return%':>8} {'B&H%':>7} {'sharpe':>7} {'maxDD%':>7} {'trades':>6} {'win%':>5} {'fees$':>8}"
    print(hdr)
    print("-" * len(hdr))
    for p in a.products:
        res = compare(p, a.granularity, a.bars, cfg)
        for name in ("v2", "legacy"):
            m = res[name]["metrics"]
            print(f"{p:10} {name:7} {m['return_pct']:8.2f} {m['buy_hold_pct']:7.2f} {m['sharpe']:7.2f} "
                  f"{m['max_drawdown_pct']:7.2f} {m['trades']:6d} {m['win_rate_pct']:5.0f} {m['fees_paid']:8.2f}")


if __name__ == "__main__":
    main()
