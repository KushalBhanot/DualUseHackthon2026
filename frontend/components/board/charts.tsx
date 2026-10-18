"use client";

import { useState } from "react";
import { clock } from "@/lib/format";
import { LANE, LANE_ORDER } from "@/lib/labels";
import type { Lane, VolumeBucket } from "@/lib/types";
import { LANE_BG, cx } from "../ui";

/** Legend for the three lanes: a swatch beside ink text (text never wears the series colour). */
export function LaneLegend({ className }: { className?: string }) {
  return (
    <div className={cx("flex flex-wrap gap-3.5 text-xs font-semibold text-ink-2", className)}>
      {LANE_ORDER.map((l) => (
        <span key={l} className="flex items-center gap-1.5">
          <span className={cx("h-2.5 w-2.5 rounded-[3px]", LANE_BG[l])} />
          {LANE[l]}
        </span>
      ))}
    </div>
  );
}

/**
 * Stacked columns by lane. Red sits on the baseline so the urgent count is always easy to read.
 * Hover (or focus) a column for its numbers; a hidden table carries the same data for screen readers.
 */
export function LaneColumns({
  data,
  height = 124,
  bucketLabel,
  caption,
}: {
  data: VolumeBucket[];
  height?: number;
  bucketLabel: (b: VolumeBucket) => string;
  caption: string;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const max = Math.max(1, ...data.map((b) => b.red + b.amber + b.green));
  const h = hover != null ? data[hover] : null;

  return (
    <div className="relative">
      <div className="flex items-end" style={{ height }} onMouseLeave={() => setHover(null)}>
        {data.map((b, i) => {
          const total = b.red + b.amber + b.green;
          const segs = LANE_ORDER.filter((l) => b[l] > 0);
          return (
            <div
              key={b.bucket}
              tabIndex={0}
              aria-label={`${bucketLabel(b)}: ${total} calls`}
              onMouseEnter={() => setHover(i)}
              onFocus={() => setHover(i)}
              onBlur={() => setHover(null)}
              className="flex h-full flex-1 cursor-default items-end justify-center px-px outline-none focus-visible:bg-soft"
            >
              <div className={cx("flex w-full max-w-6 flex-col-reverse gap-[2px]", hover === i && "opacity-80")}>
                {total === 0 ? (
                  <span className="h-1.5 rounded-[3px] bg-soft" />
                ) : (
                  segs.map((l, j) => (
                    <span
                      key={l}
                      className={cx(LANE_BG[l], j === segs.length - 1 && "rounded-t-[4px]")}
                      style={{ height: Math.max(3, (b[l] / max) * (height - 6 - 2 * (segs.length - 1))) }}
                    />
                  ))
                )}
              </div>
            </div>
          );
        })}
      </div>
      {h && hover != null && (
        <div
          className="pointer-events-none absolute -top-2 z-10 -translate-y-full rounded-xl bg-ink px-3 py-2 text-xs text-white shadow-lg"
          style={{ left: `${((hover + 0.5) / data.length) * 100}%`, transform: `translate(${hover > data.length / 2 ? "-100%" : "0"}, -100%)` }}
        >
          <div className="mb-1 font-bold">{bucketLabel(h)}</div>
          {LANE_ORDER.map((l) => (
            <div key={l} className="flex items-center gap-2 tabular-nums">
              <span className={cx("size-2 rounded-[2px]", LANE_BG[l])} />
              <span className="flex-1">{LANE[l]}</span>
              <b>{h[l]}</b>
            </div>
          ))}
        </div>
      )}
      <table className="sr-only">
        <caption>{caption}</caption>
        <thead>
          <tr>
            <th>Time</th>
            {LANE_ORDER.map((l) => (
              <th key={l}>{LANE[l]}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.map((b) => (
            <tr key={b.bucket}>
              <td>{bucketLabel(b)}</td>
              {LANE_ORDER.map((l) => (
                <td key={l}>{b[l]}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** A tiny single-series column sparkline. Decorative: the number beside it carries the value. */
export function Spark({ series, className, barClass = "bg-blue" }: { series: number[]; className?: string; barClass?: string }) {
  const max = Math.max(1, ...series);
  return (
    <div aria-hidden className={cx("flex items-end gap-[2px]", className)}>
      {series.map((n, i) => (
        <span key={i} className={cx("flex-1 rounded-t-[2px]", n ? barClass : "bg-soft")} style={{ height: `${Math.max(12, (n / max) * 100)}%` }} />
      ))}
    </div>
  );
}

/** Lane mix as a ring, with the total in the middle. */
export function LaneDonut({ mix }: { mix: Record<Lane, number> }) {
  const total = mix.red + mix.amber + mix.green;
  const r = 62;
  const C = 2 * Math.PI * r;
  const gap = total > 1 ? 4 : 0;
  let offset = 0;
  return (
    <svg width="160" height="160" viewBox="0 0 160 160" role="img" aria-label={`Lane mix: ${mix.red} now, ${mix.amber} a person soon, ${mix.green} can wait`}>
      <circle cx="80" cy="80" r={r} fill="none" stroke="#F3F5F7" strokeWidth="14" />
      <g transform="rotate(-90 80 80)">
        {LANE_ORDER.map((l) => {
          const len = total ? (mix[l] / total) * C : 0;
          const el = mix[l] ? (
            <circle
              key={l}
              cx="80"
              cy="80"
              r={r}
              fill="none"
              stroke={`var(--color-lane-${l})`}
              strokeWidth="14"
              strokeDasharray={`${Math.max(0.01, len - gap)} ${C}`}
              strokeDashoffset={-offset}
            />
          ) : null;
          offset += len;
          return el;
        })}
      </g>
      <text x="80" y="86" textAnchor="middle" fontSize="30" fontWeight="800" fill="#111827">
        {total}
      </text>
      <text x="80" y="106" textAnchor="middle" fontSize="12" fill="#6B7280">
        calls
      </text>
    </svg>
  );
}

export const minuteLabel = (b: VolumeBucket) => clock(b.bucket).slice(0, 5);
