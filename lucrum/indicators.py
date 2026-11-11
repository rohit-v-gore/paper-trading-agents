"""Technical indicators. All functions take/return pandas objects and never mutate input."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, adjust=False).mean()


def bollinger(close: pd.Series, window: int = 20, k: float = 2.0) -> pd.DataFrame:
    ma = close.rolling(window).mean()
    sd = close.rolling(window).std(ddof=0)
    upper, lower = ma + k * sd, ma - k * sd
    width = (upper - lower).replace(0, np.nan)  # flat bands -> NaN instead of div/0
    return pd.DataFrame({
        "bb_mid": ma,
        "bb_upper": upper,
        "bb_lower": lower,
        "pct_b": (close - lower) / width,
        "bb_width": width / ma,  # relative band width
    })


def rsi(close: pd.Series, window: int = 14) -> pd.Series:
    """Wilder's RSI (the original scripts used a simple rolling mean, which is noisier)."""
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = gain / loss.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(loss != 0, 100.0)


def atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    prev = df["close"].shift()
    tr = pd.concat([df["high"] - df["low"], (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()


def adx(df: pd.DataFrame, window: int = 14) -> pd.Series:
    """Average Directional Index: < ~25 means ranging market, where mean reversion works."""
    up = df["high"].diff()
    down = -df["low"].diff()
    plus_dm = np.where((up > down) & (up > 0), up, 0.0)
    minus_dm = np.where((down > up) & (down > 0), down, 0.0)
    a = atr(df, window)
    alpha = 1 / window
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / a
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=alpha, adjust=False).mean() / a
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return dx.ewm(alpha=alpha, adjust=False, min_periods=window).mean()


def compute_all(df: pd.DataFrame, cfg) -> pd.DataFrame:
    out = df.copy()
    out = out.join(bollinger(out["close"], cfg.bb_window, cfg.bb_k))
    out["rsi"] = rsi(out["close"], cfg.rsi_window)
    out["ema_fast"] = ema(out["close"], cfg.ema_fast)
    out["ema_slow"] = ema(out["close"], cfg.ema_slow)
    out["atr"] = atr(out, cfg.atr_window)
    out["adx"] = adx(out, cfg.adx_window)
    return out
