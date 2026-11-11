"""FastAPI server: runs the paper engine and serves the dashboard.

    python -m lucrum.server            # http://localhost:8000
    python -m lucrum.server --auto     # pick coins by liquidity-weighted volatility
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import backtest
from .config import EngineConfig, StrategyConfig
from .engine import IND_COLS, Engine, _clean

DIST = Path(__file__).resolve().parent.parent / "dashboard" / "dist"
engine: Engine | None = None


def _json(obj):
    return json.loads(json.dumps(obj, default=lambda o: None if isinstance(o, float) and math.isnan(o) else str(o)))


def build_app(ecfg: EngineConfig, scfg: StrategyConfig) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app):
        global engine
        engine = Engine(ecfg, scfg)
        task = asyncio.create_task(engine.start())
        yield
        task.cancel()

    app = FastAPI(title="Lucrum", lifespan=lifespan)

    @app.get("/api/snapshot")
    async def snapshot():
        return JSONResponse(_json(engine.snapshot()))

    @app.get("/api/backtest")
    async def run_backtest(product: str = "BTC-USD", granularity: int = 300, bars: int = Query(1500, le=6000)):
        res = await asyncio.to_thread(backtest.compare, product, granularity, bars, scfg)
        ind = res["v2"]["indicators"]
        out_bars = []
        for t, r in ind.iterrows():
            d = {"time": int(t), **{c: _clean(r[c]) for c in ("open", "high", "low", "close", "volume", *IND_COLS)}}
            out_bars.append(d)
        payload = {"product": product, "granularity": granularity, "bars": out_bars}
        for name in ("v2", "legacy"):
            payload[name] = {
                "metrics": res[name]["metrics"],
                "trades": [t.to_dict() for t in res[name]["trades"]],
                "equity": [{"time": t, "value": v} for t, v in res[name]["equity"]],
            }
        return JSONResponse(_json(payload))

    @app.websocket("/ws")
    async def ws(sock: WebSocket):
        await sock.accept()
        q = engine.subscribe()
        try:
            await sock.send_text(json.dumps(_json({"type": "snapshot", "data": engine.snapshot()})))
            while True:
                msg = await q.get()
                await sock.send_text(json.dumps(_json(msg)))
        except (WebSocketDisconnect, RuntimeError):
            pass
        finally:
            engine.unsubscribe(q)

    if DIST.exists():
        app.mount("/", StaticFiles(directory=DIST, html=True), name="dashboard")
    return app


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--granularity", type=int, default=60)
    ap.add_argument("--products", nargs="*")
    ap.add_argument("--auto", action="store_true", help="auto-select coins")
    ap.add_argument("--cash", type=float, default=10_000)
    ap.add_argument("--fee", type=float, default=StrategyConfig.fee_rate)
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")
    ecfg = EngineConfig(granularity=a.granularity, starting_cash=a.cash, auto_select=a.auto)
    if a.products:
        ecfg.products = a.products
    import uvicorn
    uvicorn.run(build_app(ecfg, StrategyConfig(fee_rate=a.fee)), host="127.0.0.1", port=a.port, log_level="warning")


if __name__ == "__main__":
    main()
