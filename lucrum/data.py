"""Coinbase Exchange public market data (no API key needed)."""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

REST = "https://api.exchange.coinbase.com"
WS = "wss://ws-feed.exchange.coinbase.com"
MAX_CANDLES = 300  # Coinbase limit per request
VALID_GRANULARITY = (60, 300, 900, 3600, 21600, 86400)

_session = requests.Session()
_session.headers["User-Agent"] = "lucrum/2.0"


def _get(path: str, params: dict | None = None, retries: int = 3):
    for attempt in range(retries):
        try:
            r = _session.get(REST + path, params=params, timeout=10)
            if r.status_code == 429:  # rate limited
                time.sleep(0.5 * (attempt + 1))
                continue
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            if attempt == retries - 1:
                raise
            time.sleep(0.5 * (attempt + 1))
    raise RuntimeError(f"rate limited on {path}")


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def candles(product: str, granularity: int = 60, bars: int = 300, end: float | None = None) -> pd.DataFrame:
    """OHLCV bars, oldest first, indexed by unix-second open time. Paginates past the 300 limit."""
    if granularity not in VALID_GRANULARITY:
        raise ValueError(f"granularity must be one of {VALID_GRANULARITY}")
    end = end or time.time()
    end = end - end % granularity
    rows: list = []
    while len(rows) < bars:
        n = min(MAX_CANDLES, bars - len(rows))
        start = end - n * granularity
        chunk = _get(f"/products/{product}/candles", {"granularity": granularity, "start": _iso(start), "end": _iso(end)})
        if not chunk:
            break
        rows.extend(chunk)
        end = start
        if len(rows) < bars:
            time.sleep(0.12)  # stay under the public rate limit
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows, columns=["time", "low", "high", "open", "close", "volume"]).astype(float)
    df["time"] = df["time"].astype(int)
    df = df.drop_duplicates("time").sort_values("time").set_index("time")
    return df[["open", "high", "low", "close", "volume"]].tail(bars)


def usd_products() -> list[dict]:
    prods = _get("/products")
    return [p for p in prods if p.get("quote_currency") == "USD" and p.get("status") == "online"
            and not p.get("trading_disabled") and not p.get("cancel_only")]


def select_top(n: int = 5, granularity: int = 300, min_usd_volume: float = 5_000_000) -> list[dict]:
    """Rank USD pairs by volatility, but only among liquid ones.

    The old cryptoselect.py ranked every currency in /exchange-rates (including fiat) by
    raw volatility, which favours illiquid coins whose spread eats any edge.
    """
    stats = _get("/products/stats")
    liquid = []
    for p in usd_products():
        s = (stats.get(p["id"]) or {}).get("stats_24hour") or {}
        try:
            usd_vol = float(s["volume"]) * float(s["last"])
        except (KeyError, TypeError, ValueError):
            continue
        if usd_vol >= min_usd_volume:
            liquid.append((p["id"], usd_vol))

    def score(item):
        pid, usd_vol = item
        try:
            df = candles(pid, granularity, 288)
        except Exception:
            return None
        if len(df) < 50:
            return None
        vol = np.log(df["close"]).diff().std()
        # choppiness: mean reversion likes prices that oscillate rather than trend
        net = abs(np.log(df["close"].iloc[-1] / df["close"].iloc[0]))
        path = np.log(df["close"]).diff().abs().sum()
        chop = 1 - net / path if path else 0
        return {"product": pid, "volatility": float(vol), "chop": float(chop), "usd_volume": usd_vol,
                "score": float(vol * chop)}

    with ThreadPoolExecutor(4) as ex:
        scored = [s for s in ex.map(score, liquid) if s]
    scored.sort(key=lambda s: s["score"], reverse=True)
    return scored[:n]
