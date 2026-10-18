/** "(415) 555-0142" for US numbers in any form; anything else as given. */
export function phone(n: string | null | undefined): string {
  if (!n) return "unknown";
  const d = n.replace(/\D/g, "").slice(-10);
  return d.length === 10 ? `(${d.slice(0, 3)}) ${d.slice(3, 6)}-${d.slice(6)}` : n;
}

const timeFmt = new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });

export function clock(iso: string | number | Date | null | undefined): string {
  if (iso == null) return "—";
  const d = iso instanceof Date ? iso : new Date(iso);
  return Number.isNaN(d.getTime()) ? "—" : timeFmt.format(d);
}

/** Elapsed time, compact: "45s", "4:05", "1h 12m". */
export function elapsed(fromIso: string, now: number): string {
  const s = Math.max(0, Math.floor((now - Date.parse(fromIso)) / 1000));
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  return `${Math.floor(s / 3600)}h ${Math.floor(s / 60) % 60}m`;
}

export function seconds(fromIso: string | null, toIso: string | null): number | null {
  if (!fromIso || !toIso) return null;
  return (Date.parse(toIso) - Date.parse(fromIso)) / 1000;
}

export const pct = (v: number | null | undefined) => (v == null ? "—" : `${Math.round(v * 100)}%`);

export const num = (v: number | string | null | undefined, unit = "") => (v == null ? "—" : `${v}${unit}`);

export const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;
