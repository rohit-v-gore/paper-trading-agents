import { useEffect, useMemo, useState } from "react";
import type { BacktestResult, Metrics } from "../types";
import MarketChart, { C, toMarkers } from "./MarketChart";
import EquityChart from "./EquityChart";
import { TradeTable } from "./LiveView";
import { fmtPct, fmtUsd, tone } from "../format";

const GRANS = [[60, "1m"], [300, "5m"], [900, "15m"], [3600, "1h"]] as const;

export default function BacktestView({ products, strategy }: { products: string[]; strategy: Record<string, number | boolean> }) {
  const [product, setProduct] = useState(products[0] ?? "BTC-USD");
  const [gran, setGran] = useState(900);
  const [bars, setBars] = useState(1500);
  const [res, setRes] = useState<BacktestResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [showLegacy, setShowLegacy] = useState(true);

  const run = async () => {
    setLoading(true);
    setErr(null);
    try {
      const r = await fetch(`/api/backtest?product=${product}&granularity=${gran}&bars=${bars}`);
      if (!r.ok) throw new Error(await r.text());
      setRes(await r.json());
    } catch (e) {
      setErr(String(e));
    } finally {
      setLoading(false);
    }
  };
  useEffect(() => { run(); }, []); // eslint-disable-line

  const markers = useMemo(() => {
    if (!res) return [];
    const v2 = toMarkers(res.v2.trades, res.granularity);
    return showLegacy ? [...v2, ...toMarkers(res.legacy.trades, res.granularity, true)] : v2;
  }, [res, showLegacy]);

  const bh = useMemo(() => {
    if (!res?.bars.length) return [];
    const p0 = res.bars[0].close;
    return res.bars.map((b) => ({ time: b.time, value: 10000 * (b.close / p0) }));
  }, [res]);

  const span = res ? ((res.bars.length * res.granularity) / 86400).toFixed(1) : "";

  return (
    <div className="bt">
      <div className="panel bt-controls">
        <label>Coin
          <select value={product} onChange={(e) => setProduct(e.target.value)}>
            {[...new Set([...products, "BTC-USD", "ETH-USD", "SOL-USD", "AVAX-USD", "LINK-USD", "DOGE-USD"])].map((p) => <option key={p}>{p}</option>)}
          </select>
        </label>
        <label>Bars
          <div className="seg">
            {GRANS.map(([g, l]) => <button key={g} className={g === gran ? "on" : ""} onClick={() => setGran(g)}>{l}</button>)}
          </div>
        </label>
        <label>History
          <select value={bars} onChange={(e) => setBars(Number(e.target.value))}>
            {[500, 1500, 3000, 6000].map((b) => <option key={b} value={b}>{b} bars</option>)}
          </select>
        </label>
        <button className="run" onClick={run} disabled={loading}>{loading ? "Running…" : "Run backtest"}</button>
        <label className="toggle"><input type="checkbox" checked={showLegacy} onChange={(e) => setShowLegacy(e.target.checked)} /> Show old algorithm's trades</label>
        {res && <span className="muted">{res.bars.length} bars ≈ {span} days · fee {(Number(strategy.fee_rate) * 100).toFixed(2)}%/side</span>}
      </div>
      {err && <div className="panel error">{err}</div>}

      {res && (
        <>
          <div className="cmp">
            <MetricCard title="v2 (new)" m={res.v2.metrics} accent />
            <MetricCard title="Legacy Bollinger.py" m={res.legacy.metrics} />
            <div className="panel metric-card">
              <div className="panel-title">Buy &amp; hold</div>
              <div className={`metric-hero ${tone(res.v2.metrics.buy_hold_pct)}`}>{fmtPct(res.v2.metrics.buy_hold_pct)}</div>
              <div className="muted small">What holding {res.product} over the same window returned.</div>
            </div>
          </div>
          <div className="panel chart-panel">
            <div className="chart-head">
              <div><span className="big-sym">{res.product}</span><span className="muted"> backtest</span></div>
              <div className="legend">
                <span><i style={{ background: C.up }} />v2 buy</span>
                <span><i style={{ background: C.down }} />v2 sell / stop</span>
                {showLegacy && <span><i style={{ background: C.legacy }} />legacy</span>}
              </div>
            </div>
            <MarketChart bars={res.bars} markers={markers} rsiBounds={[Number(strategy.entry_rsi ?? 30), Number(strategy.exit_rsi ?? 70)]} resetKey={`${res.product}-${res.granularity}-${res.bars.length}`} height={380} fit />
          </div>
          <div className="panel">
            <div className="panel-title">Equity: $10,000 start
              <span className="legend inline"><span><i style={{ background: C.rsi }} />v2</span><span><i style={{ background: C.legacy }} />legacy</span><span><i style={{ background: C.ema }} />buy &amp; hold</span></span>
            </div>
            <EquityChart height={220} series={[
              { name: "v2", color: C.rsi, data: res.v2.equity },
              { name: "legacy", color: C.legacy, data: res.legacy.equity },
              { name: "bh", color: C.ema, data: bh },
            ]} />
          </div>
          <div className="panel">
            <div className="panel-title">v2 trades</div>
            <TradeTable trades={res.v2.trades} />
          </div>
        </>
      )}
    </div>
  );
}

function MetricCard({ title, m, accent = false }: { title: string; m: Metrics; accent?: boolean }) {
  return (
    <div className={`panel metric-card ${accent ? "accent" : ""}`}>
      <div className="panel-title">{title}</div>
      <div className={`metric-hero ${tone(m.return_pct)}`}>{fmtPct(m.return_pct)}</div>
      <dl>
        <dt>Max drawdown</dt><dd className="down">{fmtPct(m.max_drawdown_pct)}</dd>
        <dt>Sharpe</dt><dd>{m.sharpe.toFixed(2)}</dd>
        <dt>Trades</dt><dd>{m.trades}</dd>
        <dt>Win rate</dt><dd>{m.trades ? `${m.win_rate_pct.toFixed(0)}%` : "—"}</dd>
        <dt>Fees paid</dt><dd>{fmtUsd(m.fees_paid)}</dd>
      </dl>
    </div>
  );
}
