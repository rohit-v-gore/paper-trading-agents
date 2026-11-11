from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class StrategyConfig:
    # Indicator windows
    bb_window: int = 20
    bb_k: float = 2.0
    rsi_window: int = 14
    ema_fast: int = 9
    ema_slow: int = 50
    atr_window: int = 14
    adx_window: int = 14

    # Entry: price stretched below the lower band, oversold, in a ranging regime
    entry_pct_b: float = 0.05      # %B at or below this (0 = on the lower band)
    entry_rsi: float = 32.0        # RSI at or below this
    max_adx: float = 30.0          # skip strong trends (mean reversion fails there)
    require_reversal_bar: bool = True  # bar must close green: don't catch a falling knife
    edge_mult: float = 1.5         # expected move back to mid band must exceed edge_mult x round-trip fees

    # Exit
    exit_pct_b: float = 0.55       # take profit once price recovers past the middle band
    exit_rsi: float = 68.0         # or momentum is overbought
    stop_atr: float = 2.0          # hard stop distance in ATRs
    max_hold_bars: int = 60        # time stop

    # Risk / sizing
    risk_per_trade: float = 0.01   # risk 1% of equity per trade (stop distance based)
    max_alloc: float = 0.25        # never put more than 25% of equity in one coin
    fee_rate: float = 0.0025       # per side. Coinbase Advanced maker fee at the $10k-50k tier


@dataclass
class EngineConfig:
    products: list[str] = field(default_factory=lambda: ["BTC-USD", "ETH-USD", "SOL-USD", "DOGE-USD", "XRP-USD"])
    granularity: int = 60          # bar size in seconds (60, 300, 900, ...)
    starting_cash: float = 10_000.0
    history_bars: int = 300        # bars to seed indicators with on start
    auto_select: bool = False      # pick top coins by liquidity-weighted volatility instead of `products`
    auto_select_n: int = 5
    paper: bool = True             # live trading is not wired up; paper only


def to_dict(cfg) -> dict:
    return asdict(cfg)
