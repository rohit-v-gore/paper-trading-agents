"""Live paper-trading engine.

Streams trades from the Coinbase websocket `ticker` channel, builds OHLCV bars,
runs the strategy on every closed bar and checks stops on every tick. All orders
are simulated (paper). State changes are pushed to subscribers (the dashboard).
"""
from __future__ import annotations

import asyncio
import csv
import json
import logging
import math
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import websockets

from . import data
from .config import EngineConfig, StrategyConfig
from .indicators import compute_all
from .strategy import MeanReversionV2, Position, Trade

log = logging.getLogger("lucrum.engine")
RUNS = Path(__file__).resolve().parent.parent / "runs"
IND_COLS = ["bb_mid", "bb_upper", "bb_lower", "pct_b", "rsi", "ema_fast", "ema_slow", "atr", "adx"]
KEEP_BARS = 600


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
        return None
    return float(v)


class Market:
    def __init__(self, product: str, granularity: int):
        self.product = product
        self.g = granularity
        self.bars = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        self.ind = pd.DataFrame()
        self.forming: dict | None = None
        self.price: float | None = None
        self.open_24h: float | None = None
        self.signal = "hold"
        self.reason = "warming up"
        self.pending: tuple | None = None
        self.last_tick_push = 0.0

    def seed(self, df: pd.DataFrame, cfg: StrategyConfig):
        now_bar = int(time.time()) // self.g * self.g
        closed = df[df.index < now_bar]
        self.bars = closed.tail(KEEP_BARS).copy()
        if len(df) and df.index[-1] >= now_bar:
            r = df.iloc[-1]
            self.forming = {"time": int(df.index[-1]), "open": r.open, "high": r.high, "low": r.low,
                            "close": r.close, "volume": r.volume}
        if len(self.bars):
            self.price = float(df["close"].iloc[-1])
        self.recompute(cfg)

    def recompute(self, cfg: StrategyConfig):
        if len(self.bars) >= 2:
            self.ind = compute_all(self.bars.astype(float), cfg)

    def bar_dict(self, t: int, row) -> dict:
        d = {"time": int(t), "open": float(row["open"]), "high": float(row["high"]),
             "low": float(row["low"]), "close": float(row["close"]), "volume": float(row["volume"])}
        if t in self.ind.index:
            irow = self.ind.loc[t]
            for c in IND_COLS:
                d[c] = _clean(irow[c])
        return d

    def history(self) -> list[dict]:
        return [self.bar_dict(t, r) for t, r in self.bars.iterrows()]


class Engine:
    def __init__(self, ecfg: EngineConfig | None = None, scfg: StrategyConfig | None = None):
        self.ecfg = ecfg or EngineConfig()
        self.scfg = scfg or StrategyConfig()
        self.strategy = MeanReversionV2(self.scfg)
        self.cash = self.ecfg.starting_cash
        self.positions: dict[str, Position] = {}
        self.entry_cost: dict[str, float] = {}
        self.trades: list[Trade] = []
        self.equity: list[tuple[int, float]] = []
        self.markets: dict[str, Market] = {}
        self.subscribers: set[asyncio.Queue] = set()
        self.feed_status = "starting"
        self.started_at = int(time.time())
        self.selection: list[dict] = []
        RUNS.mkdir(exist_ok=True)
        self.trade_log = RUNS / f"trades_{datetime.now():%Y%m%d_%H%M%S}.csv"

    # ---------- lifecycle ----------
    async def start(self):
        products = self.ecfg.products
        if self.ecfg.auto_select:
            self.feed_status = "selecting coins"
            try:
                self.selection = await asyncio.to_thread(data.select_top, self.ecfg.auto_select_n)
                products = [s["product"] for s in self.selection] or products
            except Exception as e:
                log.warning("auto-select failed, using defaults: %s", e)
        self.feed_status = "loading history"
        for p in products:
            m = Market(p, self.ecfg.granularity)
            try:
                df = await asyncio.to_thread(data.candles, p, self.ecfg.granularity, self.ecfg.history_bars)
                m.seed(df, self.scfg)
                if len(m.bars) >= self.strategy.warmup():
                    # show the current setup state, but never trade on a stale bar
                    m.reason = self.strategy.on_bar(m.ind.iloc[-1], None).reason or "no setup"
            except Exception as e:
                log.warning("history for %s failed: %s", p, e)
            self.markets[p] = m
        self._mark_equity()
        await self.broadcast({"type": "snapshot", "data": self.snapshot()})
        await asyncio.gather(self._feed(), self._bar_clock(), self._equity_clock())

    async def _feed(self):
        backoff = 1
        sub = {"type": "subscribe", "product_ids": list(self.markets), "channels": ["ticker"]}
        while True:
            try:
                async with websockets.connect(data.WS, ping_interval=20, max_size=2**22) as ws:
                    await ws.send(json.dumps(sub))
                    self.feed_status = "live"
                    await self.broadcast({"type": "status", "feed": self.feed_status})
                    backoff = 1
                    async for raw in ws:
                        msg = json.loads(raw)
                        if msg.get("type") == "ticker" and msg.get("product_id") in self.markets:
                            ts = datetime.fromisoformat(msg["time"].replace("Z", "+00:00")[:26] + "+00:00").timestamp() \
                                if "time" in msg else time.time()
                            await self.on_tick(msg["product_id"], float(msg["price"]),
                                               float(msg.get("last_size") or 0), ts, msg.get("open_24h"))
            except Exception as e:
                self.feed_status = f"reconnecting ({type(e).__name__})"
                log.warning("feed error: %s", e)
                await self.broadcast({"type": "status", "feed": self.feed_status})
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    async def _bar_clock(self):
        """Close bars on time even when a quiet coin has no trades in the new interval."""
        g = self.ecfg.granularity
        while True:
            now = time.time()
            await asyncio.sleep(g - now % g + 0.25)
            bar_start = int(time.time()) // g * g
            for m in self.markets.values():
                if m.forming and m.forming["time"] < bar_start:
                    await self._close_bar(m)

    async def _equity_clock(self):
        while True:
            await asyncio.sleep(5)
            self._mark_equity()
            await self.broadcast({"type": "portfolio", "data": self.portfolio()})

    # ---------- market events ----------
    async def on_tick(self, product: str, price: float, size: float, ts: float, open_24h=None):
        m = self.markets[product]
        m.price = price
        if open_24h:
            m.open_24h = float(open_24h)
        bar_t = int(ts) // m.g * m.g
        if m.forming and bar_t > m.forming["time"]:
            await self._close_bar(m)
        if m.forming is None or bar_t > m.forming["time"]:
            m.forming = {"time": bar_t, "open": price, "high": price, "low": price, "close": price, "volume": 0.0}
            if m.pending:  # orders decided on the last close fill at this bar's open
                await self._execute(m, *m.pending, price, bar_t)
                m.pending = None
        f = m.forming
        f["high"], f["low"], f["close"] = max(f["high"], price), min(f["low"], price), price
        f["volume"] += size

        pos = self.positions.get(product)
        if pos and pos.stop > 0 and price <= pos.stop:
            await self._sell(m, price, int(ts), "stop loss")

        now = time.monotonic()
        if now - m.last_tick_push > 0.25:
            m.last_tick_push = now
            await self.broadcast({"type": "tick", "product": product, "price": price, "bar": f})

    async def _close_bar(self, m: Market):
        f = m.forming
        m.forming = None
        m.bars.loc[f["time"]] = [f["open"], f["high"], f["low"], f["close"], f["volume"]]
        m.bars = m.bars.tail(KEEP_BARS)
        m.recompute(self.scfg)
        pos = self.positions.get(m.product)
        if pos:
            pos.bars_held += 1
        sig = self.strategy.on_bar(m.ind.iloc[-1], pos) if len(m.bars) >= self.strategy.warmup() \
            else type("S", (), {"action": "hold", "reason": "warming up", "stop": math.nan})()
        m.signal, m.reason = sig.action, sig.reason or ("in position" if pos else "no setup")
        if sig.action in ("buy", "sell"):
            m.pending = (sig.action, sig.reason, f["close"] - sig.stop if sig.action == "buy" else 0.0)
        await self.broadcast({"type": "bar", "product": m.product, "bar": m.bar_dict(f["time"], m.bars.loc[f["time"]]),
                              "signal": m.signal, "reason": m.reason})

    # ---------- paper broker ----------
    async def _execute(self, m: Market, action: str, reason: str, stop_dist: float, price: float, t: int):
        if action == "buy" and m.product not in self.positions:
            stop = price - stop_dist
            qty = self.strategy.size(self.total_equity(), self.cash, price, stop)
            if qty * price < 1:
                m.reason = "insufficient cash"
                return
            fee = qty * price * self.scfg.fee_rate
            self.cash -= qty * price + fee
            self.entry_cost[m.product] = qty * price + fee
            self.positions[m.product] = Position(qty, price, t, stop)
            await self._record(Trade(m.product, "buy", t, price, qty, fee, reason))
        elif action == "sell" and m.product in self.positions:
            await self._sell(m, price, t, reason)

    async def _sell(self, m: Market, price: float, t: int, reason: str):
        pos = self.positions.pop(m.product)
        proceeds = pos.qty * price
        fee = proceeds * self.scfg.fee_rate
        self.cash += proceeds - fee
        pnl = proceeds - fee - self.entry_cost.pop(m.product, 0)
        await self._record(Trade(m.product, "sell", t, price, pos.qty, fee, reason, pnl))

    async def _record(self, tr: Trade):
        self.trades.append(tr)
        new = not self.trade_log.exists()
        with self.trade_log.open("a", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(tr.to_dict()))
            if new:
                w.writeheader()
            w.writerow(tr.to_dict())
        log.info("%s %s %.6f @ %.4f (%s)", tr.side.upper(), tr.product, tr.qty, tr.price, tr.reason)
        self._mark_equity()
        await self.broadcast({"type": "trade", "trade": tr.to_dict(), "portfolio": self.portfolio()})

    # ---------- views ----------
    def total_equity(self) -> float:
        return self.cash + sum(p.qty * (self.markets[k].price or p.entry_price) for k, p in self.positions.items())

    def _mark_equity(self):
        self.equity.append((int(time.time()), self.total_equity()))
        self.equity = self.equity[-5000:]

    def portfolio(self) -> dict:
        eq = self.total_equity()
        positions = []
        for k, p in self.positions.items():
            px = self.markets[k].price or p.entry_price
            positions.append({"product": k, "qty": p.qty, "entry": p.entry_price, "price": px, "stop": p.stop,
                              "value": p.qty * px, "unrealized": p.qty * px - self.entry_cost.get(k, 0),
                              "bars_held": p.bars_held})
        sells = [t for t in self.trades if t.side == "sell"]
        return {
            "cash": self.cash, "equity": eq, "start": self.ecfg.starting_cash,
            "pnl": eq - self.ecfg.starting_cash, "positions": positions,
            "realized": sum(t.pnl or 0 for t in sells), "fees": sum(t.fee for t in self.trades),
            "wins": sum(1 for t in sells if (t.pnl or 0) > 0), "closed": len(sells),
            "equity_curve": [{"time": t, "value": v} for t, v in self.equity],
        }

    def snapshot(self) -> dict:
        return {
            "config": {"engine": self.ecfg.__dict__, "strategy": self.scfg.__dict__},
            "feed": self.feed_status,
            "selection": self.selection,
            "markets": {k: {"product": k, "price": m.price, "open_24h": m.open_24h, "signal": m.signal,
                            "reason": m.reason, "bars": m.history(), "forming": m.forming}
                        for k, m in self.markets.items()},
            "portfolio": self.portfolio(),
            "trades": [t.to_dict() for t in self.trades[-500:]],
        }

    # ---------- pub/sub ----------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        self.subscribers.add(q)
        return q

    def unsubscribe(self, q):
        self.subscribers.discard(q)

    async def broadcast(self, msg: dict):
        for q in list(self.subscribers):
            if q.full():
                try:
                    q.get_nowait()
                except asyncio.QueueEmpty:
                    pass
            q.put_nowait(msg)
