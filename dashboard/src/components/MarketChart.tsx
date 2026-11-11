import { useEffect, useRef } from "react";
import {
  ColorType,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  IPriceLine,
  LineStyle,
  SeriesMarker,
  Time,
  UTCTimestamp,
  createChart,
} from "lightweight-charts";
import type { Bar, Trade } from "../types";
import { precisionFor } from "../format";

export const C = {
  bg: "#0d1117",
  grid: "#171d27",
  border: "#232b38",
  text: "#8b96a8",
  up: "#22c983",
  down: "#f0506e",
  upA: "rgba(34,201,131,0.35)",
  downA: "rgba(240,80,110,0.35)",
  band: "#7c6cff",
  bandFill: "rgba(124,108,255,0.07)",
  mid: "#a99fff",
  ema: "#f2b544",
  rsi: "#5ab0ff",
  legacy: "#9aa4b5",
};

const baseOptions = (height: number) => ({
  height,
  autoSize: true,
  layout: {
    background: { type: ColorType.Solid, color: "transparent" },
    textColor: C.text,
    fontFamily: "Inter, system-ui, sans-serif",
    fontSize: 11,
  },
  grid: { vertLines: { color: C.grid }, horzLines: { color: C.grid } },
  rightPriceScale: { borderColor: C.border },
  timeScale: { borderColor: C.border, timeVisible: true, secondsVisible: false, rightOffset: 4 },
  crosshair: { mode: CrosshairMode.Normal },
  localization: { timeFormatter: (t: number) => new Date(t * 1000).toLocaleString() },
});

const T = (t: number) => t as UTCTimestamp;
const line = (bars: Bar[], key: keyof Bar) =>
  bars.map((b) => (b[key] == null ? { time: T(b.time) } : { time: T(b.time), value: b[key] as number }));

export function toMarkers(trades: Trade[], granularity: number, ghost = false): SeriesMarker<Time>[] {
  return trades.map((t) => {
    const time = T(Math.floor(t.time / granularity) * granularity);
    const buy = t.side === "buy";
    const color = ghost ? C.legacy : buy ? C.up : C.down;
    return {
      time,
      position: buy ? "belowBar" : "aboveBar",
      shape: buy ? "arrowUp" : "arrowDown",
      color,
      text: ghost ? "" : buy ? "BUY" : t.reason === "stop loss" ? "STOP" : "SELL",
      size: ghost ? 0.8 : 1.2,
    } as SeriesMarker<Time>;
  });
}

interface Props {
  bars: Bar[];
  markers: SeriesMarker<Time>[];
  stop?: number | null;
  entry?: number | null;
  rsiBounds: [number, number];
  height?: number;
  resetKey: string;
  fit?: boolean;
}

export default function MarketChart({ bars, markers, stop, entry, rsiBounds, height = 420, resetKey, fit = false }: Props) {
  const priceEl = useRef<HTMLDivElement>(null);
  const rsiEl = useRef<HTMLDivElement>(null);
  const r = useRef<{
    chart: IChartApi;
    rsiChart: IChartApi;
    candles: ISeriesApi<"Candlestick">;
    vol: ISeriesApi<"Histogram">;
    upper: ISeriesApi<"Line">;
    lower: ISeriesApi<"Line">;
    mid: ISeriesApi<"Line">;
    ema: ISeriesApi<"Line">;
    rsi: ISeriesApi<"Line">;
    lines: IPriceLine[];
    key: string;
    first: number;
    len: number;
  } | null>(null);

  useEffect(() => {
    const chart = createChart(priceEl.current!, baseOptions(height));
    const rsiChart = createChart(rsiEl.current!, {
      ...baseOptions(120),
      timeScale: { ...baseOptions(120).timeScale, visible: false },
    });
    const vol = chart.addHistogramSeries({ priceScaleId: "vol", priceFormat: { type: "volume" }, lastValueVisible: false, priceLineVisible: false });
    chart.priceScale("vol").applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } });
    const bandOpts = { color: C.band, lineWidth: 1 as const, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
    const upper = chart.addLineSeries(bandOpts);
    const lower = chart.addLineSeries(bandOpts);
    const mid = chart.addLineSeries({ ...bandOpts, color: C.mid, lineStyle: LineStyle.Dashed });
    const ema = chart.addLineSeries({ ...bandOpts, color: C.ema, lineWidth: 2 as const });
    const candles = chart.addCandlestickSeries({
      upColor: C.up, downColor: C.down, borderVisible: false, wickUpColor: C.up, wickDownColor: C.down,
    });
    const rsi = rsiChart.addLineSeries({ color: C.rsi, lineWidth: 2, priceLineVisible: false, priceFormat: { type: "price", precision: 0, minMove: 1 } });
    rsi.createPriceLine({ price: rsiBounds[0], color: C.up, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: "" });
    rsi.createPriceLine({ price: rsiBounds[1], color: C.down, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: "" });
    rsiChart.priceScale("right").applyOptions({ autoScale: false, scaleMargins: { top: 0.08, bottom: 0.08 } });

    // keep the RSI pane scrolled/zoomed with the price pane
    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) rsiChart.timeScale().setVisibleLogicalRange(range);
    });
    rsiChart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (range) chart.timeScale().setVisibleLogicalRange(range);
    });

    r.current = { chart, rsiChart, candles, vol, upper, lower, mid, ema, rsi, lines: [], key: "", first: 0, len: 0 };
    return () => {
      chart.remove();
      rsiChart.remove();
      r.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const s = r.current;
    if (!s || !bars.length) return;
    const last = bars[bars.length - 1];
    const incremental = s.key === resetKey && s.first === bars[0].time && (bars.length === s.len || bars.length === s.len + 1);
    const volBar = (b: Bar) => ({ time: T(b.time), value: b.volume, color: b.close >= b.open ? C.upA : C.downA });
    const pt = (b: Bar, k: keyof Bar) => (b[k] == null ? { time: T(b.time) } : { time: T(b.time), value: b[k] as number });

    if (incremental) {
      s.candles.update({ time: T(last.time), open: last.open, high: last.high, low: last.low, close: last.close });
      s.vol.update(volBar(last));
      if (last.bb_upper != null) {
        s.upper.update(pt(last, "bb_upper"));
        s.lower.update(pt(last, "bb_lower"));
        s.mid.update(pt(last, "bb_mid"));
        s.ema.update(pt(last, "ema_slow"));
        s.rsi.update(pt(last, "rsi"));
      } else {
        // forming bar: keep panes aligned with whitespace
        [s.upper, s.lower, s.mid, s.ema, s.rsi].forEach((x) => x.update({ time: T(last.time) }));
      }
    } else {
      const p = precisionFor(last.close);
      s.candles.applyOptions({ priceFormat: { type: "price", precision: p, minMove: 10 ** -p } });
      s.candles.setData(bars.map((b) => ({ time: T(b.time), open: b.open, high: b.high, low: b.low, close: b.close })));
      s.vol.setData(bars.map(volBar));
      s.upper.setData(line(bars, "bb_upper"));
      s.lower.setData(line(bars, "bb_lower"));
      s.mid.setData(line(bars, "bb_mid"));
      s.ema.setData(line(bars, "ema_slow"));
      s.rsi.setData(line(bars, "rsi"));
      s.rsi.applyOptions({ autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 100 } }) });
      if (s.key !== resetKey) {
        const n = bars.length;
        if (fit) s.chart.timeScale().fitContent();
        else s.chart.timeScale().setVisibleLogicalRange({ from: Math.max(0, n - 180), to: n + 4 });
      }
    }
    s.key = resetKey;
    s.first = bars[0].time;
    s.len = bars.length;
  }, [bars, resetKey, fit]);

  useEffect(() => {
    const s = r.current;
    if (!s) return;
    const times = new Set(bars.map((b) => b.time));
    s.candles.setMarkers(markers.filter((m) => times.has(m.time as number)).sort((a, b) => (a.time as number) - (b.time as number)));
  }, [markers, bars]);

  useEffect(() => {
    const s = r.current;
    if (!s) return;
    s.lines.forEach((l) => s.candles.removePriceLine(l));
    s.lines = [];
    if (entry) s.lines.push(s.candles.createPriceLine({ price: entry, color: C.text, lineStyle: LineStyle.Dotted, lineWidth: 1, axisLabelVisible: true, title: "entry" }));
    if (stop) s.lines.push(s.candles.createPriceLine({ price: stop, color: C.down, lineStyle: LineStyle.Dashed, lineWidth: 1, axisLabelVisible: true, title: "stop" }));
  }, [stop, entry]);

  return (
    <div className="chart-stack">
      <div ref={priceEl} style={{ height }} />
      <div className="pane-label">RSI {rsiBounds[0]} / {rsiBounds[1]}</div>
      <div ref={rsiEl} style={{ height: 120 }} />
    </div>
  );
}
