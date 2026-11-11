import { StrictMode, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { useLucrum } from "./useLucrum";
import LiveView from "./components/LiveView";
import BacktestView from "./components/BacktestView";
import { fmtPct, fmtUsd, tone } from "./format";

function App() {
  const s = useLucrum();
  const [tab, setTab] = useState<"live" | "backtest">("live");
  const p = s.portfolio;
  const pnlPct = p ? (p.pnl / p.start) * 100 : null;
  const live = s.connected && s.feed === "live";

  return (
    <div className="app">
      <header className="top">
        <div className="brand">
          <span className="logo">◆</span> LUCRUM
          <span className="badge">PAPER</span>
        </div>
        <nav className="tabs">
          <button className={tab === "live" ? "on" : ""} onClick={() => setTab("live")}>Live</button>
          <button className={tab === "backtest" ? "on" : ""} onClick={() => setTab("backtest")}>Backtest</button>
        </nav>
        <div className="stats">
          <Stat label="Equity" value={fmtUsd(p?.equity)} />
          <Stat label="P&L" value={`${fmtUsd(p?.pnl, true)}`} sub={fmtPct(pnlPct)} cls={tone(p?.pnl)} />
          <Stat label="Realized" value={fmtUsd(p?.realized, true)} cls={tone(p?.realized)} />
          <Stat label="Fees" value={fmtUsd(p?.fees)} />
          <Stat label="Win rate" value={p?.closed ? `${Math.round((p.wins / p.closed) * 100)}%` : "—"} sub={p ? `${p.closed} closed` : ""} />
          <div className={`feed ${live ? "on" : ""}`}><span className="dot" />{s.connected ? s.feed : "disconnected"}</div>
        </div>
      </header>
      <main>
        {tab === "live" ? <LiveView s={s} /> : <BacktestView products={Object.keys(s.markets)} strategy={s.strategy} />}
      </main>
    </div>
  );
}

function Stat({ label, value, sub, cls = "" }: { label: string; value: string; sub?: string; cls?: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{label}</div>
      <div className={`stat-value mono ${cls}`}>{value}{sub && <span className="stat-sub">{sub}</span>}</div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
