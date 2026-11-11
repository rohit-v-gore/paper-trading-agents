"""Trading logic shared by the backtester and the live paper engine.

`MeanReversionV2` is the improved strategy. `LegacyBollinger` reproduces the original
Bollinger.py rules so the two can be compared on identical data.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from .config import StrategyConfig


@dataclass
class Position:
    qty: float
    entry_price: float
    entry_time: int
    stop: float
    bars_held: int = 0


@dataclass
class Trade:
    product: str
    side: str            # "buy" | "sell"
    time: int            # unix seconds
    price: float
    qty: float
    fee: float
    reason: str
    pnl: Optional[float] = None  # set on sells, net of both fees

    def to_dict(self) -> dict:
        return self.__dict__.copy()


@dataclass
class Signal:
    action: str          # "buy" | "sell" | "hold"
    reason: str = ""
    stop: float = math.nan


class MeanReversionV2:
    """Bollinger/RSI mean reversion with a regime filter, fee-aware edge check,
    ATR stops, a time stop and risk-based sizing.

    Fixes vs. the original scripts:
      * signals evaluated on closed OHLC bars, not one ticker poll every 5 minutes
      * Wilder RSI, population-std bands, no divide-by-zero on flat bands
      * ADX filter: no mean-reversion entries into strong trends
      * entry needs a green reversal bar, not just touching the band
      * trades are skipped when the expected move can't cover Coinbase fees
      * hard stop-loss (the old "only sell above purchase price" rule could hold a loser forever)
      * position size from risk budget instead of all-in
    """

    name = "v2"

    def __init__(self, cfg: StrategyConfig):
        self.cfg = cfg

    def warmup(self) -> int:
        c = self.cfg
        return max(c.bb_window, c.rsi_window, c.ema_slow, c.atr_window, c.adx_window * 2) + 1

    def on_bar(self, row: pd.Series, pos: Optional[Position]) -> Signal:
        c = self.cfg
        if any(pd.isna(row.get(k)) for k in ("pct_b", "rsi", "atr", "adx", "bb_mid")):
            return Signal("hold", "warming up")

        if pos is None:
            round_trip = 2 * c.fee_rate
            expected = (row["bb_mid"] - row["close"]) / row["close"]
            if row["pct_b"] > c.entry_pct_b:
                return Signal("hold")
            if row["rsi"] > c.entry_rsi:
                return Signal("hold", "not oversold")
            if row["adx"] > c.max_adx:
                return Signal("hold", "trending, skip")
            if c.require_reversal_bar and row["close"] <= row["open"]:
                return Signal("hold", "waiting for reversal bar")
            if expected < round_trip * c.edge_mult:
                return Signal("hold", "edge < fees")
            stop = row["close"] - c.stop_atr * row["atr"]
            return Signal("buy", f"%B {row['pct_b']:.2f}, RSI {row['rsi']:.0f}, ADX {row['adx']:.0f}", stop)

        if row["pct_b"] >= c.exit_pct_b:
            return Signal("sell", "take profit: back to mid band")
        if row["rsi"] >= c.exit_rsi:
            return Signal("sell", "take profit: RSI overbought")
        if pos.bars_held >= c.max_hold_bars:
            return Signal("sell", "time stop")
        return Signal("hold")

    def size(self, equity: float, cash: float, price: float, stop: float) -> float:
        c = self.cfg
        risk_per_unit = max(price - stop, price * 1e-4)
        qty = (equity * c.risk_per_trade) / risk_per_unit
        qty = min(qty, equity * c.max_alloc / price, cash / (price * (1 + c.fee_rate)))
        return max(qty, 0.0)

    def stop_hit(self, pos: Position, low: float) -> bool:
        return low <= pos.stop


class LegacyBollinger:
    """Faithful port of the original Bollinger.py signal rules (all-in, no stop)."""

    name = "legacy"

    def __init__(self, cfg: StrategyConfig, threshold: float = 0.15):
        self.cfg = cfg
        self.threshold = threshold

    def warmup(self) -> int:
        return self.cfg.bb_window + 1

    def on_bar(self, row: pd.Series, pos: Optional[Position]) -> Signal:
        if pd.isna(row.get("pct_b")):
            return Signal("hold")
        if pos is None and row["pct_b"] < self.threshold:
            return Signal("buy", "%B < 0.15", stop=0.0)
        if pos is not None and row["pct_b"] > 1 - self.threshold and row["close"] > pos.entry_price:
            return Signal("sell", "%B > 0.85 and above entry")
        return Signal("hold")

    def size(self, equity: float, cash: float, price: float, stop: float) -> float:
        return cash / (price * (1 + self.cfg.fee_rate))

    def stop_hit(self, pos: Position, low: float) -> bool:
        return False
