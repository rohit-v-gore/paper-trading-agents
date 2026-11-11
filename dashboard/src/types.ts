export interface Bar {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  bb_mid?: number | null;
  bb_upper?: number | null;
  bb_lower?: number | null;
  pct_b?: number | null;
  rsi?: number | null;
  ema_fast?: number | null;
  ema_slow?: number | null;
  atr?: number | null;
  adx?: number | null;
}

export interface Trade {
  product: string;
  side: "buy" | "sell";
  time: number;
  price: number;
  qty: number;
  fee: number;
  reason: string;
  pnl: number | null;
}

export interface MarketState {
  product: string;
  price: number | null;
  open_24h: number | null;
  signal: string;
  reason: string;
  bars: Bar[];
  forming: Bar | null;
}

export interface PositionView {
  product: string;
  qty: number;
  entry: number;
  price: number;
  stop: number;
  value: number;
  unrealized: number;
  bars_held: number;
}

export interface Portfolio {
  cash: number;
  equity: number;
  start: number;
  pnl: number;
  realized: number;
  fees: number;
  wins: number;
  closed: number;
  positions: PositionView[];
  equity_curve: { time: number; value: number }[];
}

export interface Snapshot {
  config: { engine: Record<string, unknown> & { granularity: number }; strategy: Record<string, number | boolean> };
  feed: string;
  markets: Record<string, MarketState>;
  portfolio: Portfolio;
  trades: Trade[];
}

export interface Metrics {
  return_pct: number;
  buy_hold_pct: number;
  sharpe: number;
  max_drawdown_pct: number;
  trades: number;
  win_rate_pct: number;
  fees_paid: number;
  avg_trade_pnl: number;
}

export interface StratResult {
  metrics: Metrics;
  trades: Trade[];
  equity: { time: number; value: number }[];
}

export interface BacktestResult {
  product: string;
  granularity: number;
  bars: Bar[];
  v2: StratResult;
  legacy: StratResult;
}
