import { useEffect, useRef } from "react";
import { ColorType, IChartApi, ISeriesApi, UTCTimestamp, createChart } from "lightweight-charts";
import { C } from "./MarketChart";

export interface EquitySeries {
  name: string;
  color: string;
  data: { time: number; value: number }[];
}

const dedupe = (d: { time: number; value: number }[]) => {
  const m = new Map<number, number>();
  d.forEach((p) => m.set(p.time, p.value));
  return [...m.entries()].sort((a, b) => a[0] - b[0]).map(([time, value]) => ({ time: time as UTCTimestamp, value }));
};

export default function EquityChart({ series, height = 200 }: { series: EquitySeries[]; height?: number }) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const s = useRef<ISeriesApi<"Area">[]>([]);
  const names = series.map((x) => x.name).join("|");

  useEffect(() => {
    const c = createChart(el.current!, {
      height,
      autoSize: true,
      layout: { background: { type: ColorType.Solid, color: "transparent" }, textColor: C.text, fontFamily: "Inter, sans-serif", fontSize: 11 },
      grid: { vertLines: { visible: false }, horzLines: { color: C.grid } },
      rightPriceScale: { borderColor: C.border },
      timeScale: { borderColor: C.border, timeVisible: true },
      handleScroll: false,
      handleScale: false,
    });
    chart.current = c;
    s.current = series.map((x, i) =>
      c.addAreaSeries({
        lineColor: x.color,
        lineWidth: 2,
        topColor: i === 0 ? x.color + "40" : "transparent",
        bottomColor: "transparent",
        priceLineVisible: false,
        priceFormat: { type: "price", precision: 2, minMove: 0.01 },
      }),
    );
    return () => {
      c.remove();
      chart.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [names]);

  useEffect(() => {
    series.forEach((x, i) => s.current[i]?.setData(dedupe(x.data)));
    chart.current?.timeScale().fitContent();
  }, [series]);

  return <div ref={el} style={{ height }} />;
}
