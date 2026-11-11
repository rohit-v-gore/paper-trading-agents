import { useEffect, useReducer } from "react";
import type { Bar, MarketState, Portfolio, Snapshot, Trade } from "./types";

export interface State {
  connected: boolean;
  feed: string;
  granularity: number;
  strategy: Record<string, number | boolean>;
  markets: Record<string, MarketState>;
  portfolio: Portfolio | null;
  trades: Trade[];
}

type Msg =
  | { type: "snapshot"; data: Snapshot }
  | { type: "tick"; product: string; price: number; bar: Bar }
  | { type: "bar"; product: string; bar: Bar; signal: string; reason: string }
  | { type: "trade"; trade: Trade; portfolio: Portfolio }
  | { type: "portfolio"; data: Portfolio }
  | { type: "status"; feed: string }
  | { type: "_conn"; connected: boolean };

const initial: State = {
  connected: false,
  feed: "connecting",
  granularity: 60,
  strategy: {},
  markets: {},
  portfolio: null,
  trades: [],
};

function reducer(s: State, m: Msg): State {
  switch (m.type) {
    case "_conn":
      return { ...s, connected: m.connected };
    case "snapshot":
      return {
        ...s,
        feed: m.data.feed,
        granularity: m.data.config.engine.granularity,
        strategy: m.data.config.strategy,
        markets: m.data.markets,
        portfolio: m.data.portfolio,
        trades: m.data.trades,
      };
    case "status":
      return { ...s, feed: m.feed };
    case "tick": {
      const mk = s.markets[m.product];
      if (!mk) return s;
      return { ...s, markets: { ...s.markets, [m.product]: { ...mk, price: m.price, forming: m.bar } } };
    }
    case "bar": {
      const mk = s.markets[m.product];
      if (!mk) return s;
      const bars = mk.bars.length && mk.bars[mk.bars.length - 1].time === m.bar.time
        ? [...mk.bars.slice(0, -1), m.bar]
        : [...mk.bars, m.bar].slice(-600);
      return {
        ...s,
        markets: { ...s.markets, [m.product]: { ...mk, bars, forming: null, signal: m.signal, reason: m.reason } },
      };
    }
    case "trade":
      return { ...s, trades: [...s.trades, m.trade].slice(-500), portfolio: m.portfolio };
    case "portfolio":
      return { ...s, portfolio: m.data };
  }
}

export function useLucrum(): State {
  const [state, dispatch] = useReducer(reducer, initial);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 1000;
    let closed = false;
    let timer: number | undefined;

    const connect = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => {
        retry = 1000;
        dispatch({ type: "_conn", connected: true });
      };
      ws.onmessage = (e) => dispatch(JSON.parse(e.data) as Msg);
      ws.onclose = () => {
        dispatch({ type: "_conn", connected: false });
        if (!closed) timer = window.setTimeout(connect, (retry = Math.min(retry * 2, 15000)));
      };
    };
    // paint immediately from REST; the websocket then streams updates
    fetch("/api/snapshot")
      .then((r) => (r.ok ? r.json() : null))
      .then((d) => d && dispatch({ type: "snapshot", data: d }))
      .catch(() => {});
    connect();
    return () => {
      closed = true;
      window.clearTimeout(timer);
      ws?.close();
    };
  }, []);

  return state;
}
