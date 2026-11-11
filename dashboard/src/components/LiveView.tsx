import { useMemo, useState } from "react";
import type { State } from "../useLucrum";
import type { Bar } from "../types";
import MarketChart, { C, toMarkers } from "./MarketChart";
import EquityChart from "./EquityChart";
import Sparkline from "./Sparkline";
import { coin, fmtPct, fmtPrice, fmtTime, fmtUsd, tone } from "../format";

export default function LiveView({ s }: { s: State }) {
  const products = Object.keys(s.markets);
  const [sel, setSel] = useState<string | null>(null);
  const product = sel && s.markets[sel] ? sel : products[0];
  const m = product ? s.markets[product] : null;

  const bars: Bar[] = useMemo(() => {
    if (!m) return [];
    const f = m.forming;
    return f && (!m.bars.length || f.time > m.bars[m.bars.length - 1].time) ? [...m.bars, f] : m.bars;
  }, [m]);

  const trades = s.trades.filter((t) => t.product === product);
  const markers = useMemo(() => toMarkers(trades, s.granularity), [trades.length, product, s.granularity]); // eslint-disable-line
  const pos = s.portfolio?.positions.find((p) => p.product === product);
  const lastClosed = m?.bars[m.bars.length - 1];

  if (!m) return <div className="empty">Loading markets…</div>;

  return (
    <div className="live">
      <aside className="watchlist panel">
        <div className="panel-title">Watchlist</div>
        {products.map((p) => {
          const mk = s.markets[p];
          const closes = mk.bars.slice(-90).map((b) => b.close);
          const ref = mk.open_24h ?? closes[0];
          const chg = mk.price && ref ? (mk.price / ref - 1) * 100 : null;
          const held = s.portfolio?.positions.some((x) => x.product === p);
          return (
            <button key={p} className={`watch ${p === product ? "active" : ""}`} onClick={() => setSel(p)}>
              <div className="watch-top">
                <span className="sym">{coin(p)}{held && <span className="held-dot" title="open position" />}</span>
                <span className="mono">{fmtPrice(mk.price)}</span>
              </div>
              <div className="watch-bot">
                <Sparkline values={closes} up={(chg ?? 0) >= 0} />
                <span className={`mono small ${tone(chg)}`}>{fmtPct(chg)}</span>
              </div>
              <div className={`reason ${mk.signal}`}>{mk.reason}</div>
            </button>
          );
        })}
      </aside>

      <section className="panel chart-panel">
        <div className="chart-head">
          <div>
            <span className="big-sym">{product}</span>
            <span className="mono big-price">{fmtPrice(m.price)}</span>
          </div>
          <div className="legend">
            <span><i style={{ background: C.band }} />Bollinger {String(s.strategy.bb_window)}, {String(s.strategy.bb_k)}σ</span>
            <span><i style={{ background: C.mid }} />Mid</span>
            <span><i style={{ background: C.ema }} />EMA {String(s.strategy.ema_slow)}</span>
            <span className="muted">{s.granularity / 60}m bars</span>
          </div>
        </div>
        <MarketChart
          bars={bars}
          markers={markers}
          stop={pos?.stop}
          entry={pos?.entry}
          rsiBounds={[Number(s.strategy.entry_rsi ?? 30), Number(s.strategy.exit_rsi ?? 70)]}
          resetKey={product}
        />
      </section>

      <aside className="side">
        <SetupCard bar={lastClosed} s={s} />
        <div className="panel">
          <div className="panel-title">Equity</div>
          <EquityChart series={[{ name: "equity", color: C.rsi, data: s.portfolio?.equity_curve ?? [] }]} height={150} />
        </div>
        <div className="panel">
          <div className="panel-title">Open positions</div>
          {s.portfolio?.positions.length ? (
            <table className="tbl">
              <thead><tr><th>Coin</th><th>Entry</th><th>Stop</th><th>P&amp;L</th></tr></thead>
              <tbody>
                {s.portfolio.positions.map((p) => (
                  <tr key={p.product} onClick={() => setSel(p.product)}>
                    <td>{coin(p.product)}</td>
                    <td className="mono">{fmtPrice(p.entry)}</td>
                    <td className="mono">{fmtPrice(p.stop)}</td>
                    <td className={`mono ${tone(p.unrealized)}`}>{fmtUsd(p.unrealized, true)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : <div className="muted pad">Flat. Waiting for a setup.</div>}
        </div>
      </aside>

      <section className="panel trades">
        <div className="panel-title">Paper trades</div>
        <TradeTable trades={s.trades} />
      </section>
    </div>
  );
}

function SetupCard({ bar, s }: { bar?: Bar; s: State }) {
  const c = s.strategy as Record<string, number>;
  if (!bar || bar.pct_b == null) return <div className="panel"><div className="panel-title">Entry checklist</div><div className="muted pad">Warming up…</div></div>;
  const edge = bar.bb_mid ? (bar.bb_mid - bar.close) / bar.close : 0;
  const need = 2 * c.fee_rate * c.edge_mult;
  const rows: [string, string, boolean][] = [
    ["Stretched below band", `%B ${bar.pct_b.toFixed(2)} ≤ ${c.entry_pct_b}`, bar.pct_b <= c.entry_pct_b],
    ["Oversold", `RSI ${bar.rsi?.toFixed(0)} ≤ ${c.entry_rsi}`, (bar.rsi ?? 100) <= c.entry_rsi],
    ["Ranging, not trending", `ADX ${bar.adx?.toFixed(0)} ≤ ${c.max_adx}`, (bar.adx ?? 100) <= c.max_adx],
    ["Reversal bar", bar.close > bar.open ? "green close" : "red close", bar.close > bar.open],
    ["Edge beats fees", `${(edge * 100).toFixed(2)}% ≥ ${(need * 100).toFixed(2)}%`, edge >= need],
  ];
  const pctB = Math.max(-0.2, Math.min(1.2, bar.pct_b));
  return (
    <div className="panel">
      <div className="panel-title">Entry checklist <span className="muted">last closed bar</span></div>
      <div className="gauge">
        <div className="gauge-track"><div className="gauge-zone" /><div className="gauge-dot" style={{ left: `${((pctB + 0.2) / 1.4) * 100}%` }} /></div>
        <div className="gauge-labels"><span>lower band</span><span>mid</span><span>upper</span></div>
      </div>
      <ul className="checks">
        {rows.map(([k, v, ok]) => (
          <li key={k} className={ok ? "ok" : ""}><span className="tick">{ok ? "✓" : "·"}</span><span>{k}</span><span className="mono muted">{v}</span></li>
        ))}
      </ul>
    </div>
  );
}

export function TradeTable({ trades }: { trades: State["trades"] }) {
  if (!trades.length) return <div className="muted pad">No trades yet. v2 only trades when every entry condition lines up, so it can sit flat for a while.</div>;
  return (
    <div className="tbl-wrap">
      <table className="tbl">
        <thead><tr><th>Time</th><th>Coin</th><th>Side</th><th>Price</th><th>Qty</th><th>Fee</th><th>P&amp;L</th><th>Reason</th></tr></thead>
        <tbody>
          {[...trades].reverse().map((t, i) => (
            <tr key={i}>
              <td className="mono muted">{fmtTime(t.time, true)}</td>
              <td>{coin(t.product)}</td>
              <td><span className={`pill ${t.side}`}>{t.side}</span></td>
              <td className="mono">{fmtPrice(t.price)}</td>
              <td className="mono">{t.qty.toPrecision(4)}</td>
              <td className="mono muted">{fmtUsd(t.fee)}</td>
              <td className={`mono ${tone(t.pnl)}`}>{t.pnl == null ? "" : fmtUsd(t.pnl, true)}</td>
              <td className="muted">{t.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
