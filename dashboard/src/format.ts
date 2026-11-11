export const precisionFor = (p: number | null | undefined) =>
  !p ? 2 : p < 0.1 ? 6 : p < 1 ? 5 : p < 10 ? 4 : 2;

export const fmtPrice = (p: number | null | undefined) =>
  p == null ? "—" : p.toLocaleString("en-US", { minimumFractionDigits: precisionFor(p), maximumFractionDigits: precisionFor(p) });

export const fmtUsd = (v: number | null | undefined, signed = false) => {
  if (v == null || Number.isNaN(v)) return "—";
  const s = Math.abs(v).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 2 });
  return signed ? (v > 0 ? "+" : v < 0 ? "−" : "") + s : v < 0 ? "−" + s : s;
};

export const fmtPct = (v: number | null | undefined, signed = true, digits = 2) =>
  v == null || Number.isNaN(v) ? "—" : `${signed && v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v).toFixed(digits)}%`;

export const fmtTime = (t: number, withDate = false) =>
  new Date(t * 1000).toLocaleString([], withDate
    ? { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }
    : { hour: "2-digit", minute: "2-digit", second: "2-digit" });

export const tone = (v: number | null | undefined) => (v == null || v === 0 ? "" : v > 0 ? "up" : "down");

export const coin = (product: string) => product.replace("-USD", "");
