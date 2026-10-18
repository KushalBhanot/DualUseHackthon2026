"use client";

import { memo, type ComponentProps, type ReactNode } from "react";
import { useNow } from "@/lib/api";
import { elapsed } from "@/lib/format";
import type { Lane } from "@/lib/types";

const cx = (...c: (string | false | null | undefined)[]) => c.filter(Boolean).join(" ");
export { cx };

// ------------------------------------------------------------------ buttons

type Variant = "default" | "dark" | "red" | "amber" | "ghost-dark";
const VARIANT: Record<Variant, string> = {
  default: "border-[#E1E5EA] bg-white text-ink hover:bg-[#F4F6F8]",
  dark: "border-ink bg-ink text-white hover:bg-black",
  red: "border-lane-red bg-lane-red text-white hover:bg-[#B92222]",
  amber: "border-yellow bg-yellow text-ink hover:bg-[#F0B53F]",
  "ghost-dark": "border-navy-3 bg-navy-2 text-white hover:bg-navy-3",
};

export function Button({
  variant = "default",
  size = "md",
  busy,
  className,
  children,
  disabled,
  ...rest
}: ComponentProps<"button"> & { variant?: Variant; size?: "sm" | "md"; busy?: boolean }) {
  return (
    <button
      type="button"
      {...rest}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className={cx(
        "inline-flex cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-full border font-semibold transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue disabled:cursor-not-allowed disabled:opacity-50",
        size === "sm" ? "min-h-9 px-3.5 text-[13px]" : "min-h-11 px-[18px] text-sm",
        VARIANT[variant],
        className,
      )}
    >
      {busy && <Spinner />}
      {children}
    </button>
  );
}

export const Spinner = () => (
  <span aria-hidden className="size-3.5 animate-spin rounded-full border-2 border-current border-r-transparent opacity-70" />
);

// ------------------------------------------------------------------ chips

export type Tone = "red" | "red-soft" | "amber" | "green" | "blue" | "grey" | "purple";
const TONE: Record<Tone, string> = {
  red: "bg-lane-red text-white",
  "red-soft": "bg-red-tint text-red-ink",
  amber: "bg-amber-tint text-amber-ink",
  green: "bg-green-tint text-green-ink",
  blue: "bg-blue-tint text-blue-ink",
  grey: "bg-soft text-ink-2",
  purple: "bg-purple-tint text-purple-ink",
};

export function Chip({ tone = "grey", className, children, title }: { tone?: Tone; className?: string; children: ReactNode; title?: string }) {
  return (
    <span title={title} className={cx("inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-bold", TONE[tone], className)}>
      {children}
    </span>
  );
}

export const LANE_TONE: Record<Lane, Tone> = { red: "red", amber: "amber", green: "green" };
export const LANE_BG: Record<Lane, string> = { red: "bg-lane-red", amber: "bg-lane-amber", green: "bg-lane-green" };

export const Tag = ({ children, className }: { children: ReactNode; className?: string }) => (
  <span className={cx("inline-block rounded-lg bg-ink px-2 py-[3px] text-xs font-bold tabular-nums text-white", className)}>{children}</span>
);

// ------------------------------------------------------------------ layout

export function Card({ className, children, ...rest }: { className?: string; children: ReactNode } & React.HTMLAttributes<HTMLElement>) {
  return (
    <section {...rest} className={cx("rounded-[20px] border border-line bg-white", className)}>
      {children}
    </section>
  );
}

export function CardHeader({ title, right, hint }: { title: ReactNode; right?: ReactNode; hint?: string }) {
  return (
    <div className="flex items-center gap-2 px-5 pb-3 pt-[18px]">
      <h2 className="flex items-center gap-2 text-base font-bold" title={hint}>
        {title}
      </h2>
      <span className="flex-1" />
      {right}
    </div>
  );
}

export function PageHeader({ title, sub, right }: { title: ReactNode; sub?: ReactNode; right?: ReactNode }) {
  return (
    <header className="flex flex-wrap items-start gap-4">
      <div className="min-w-0">
        <h1 className="text-[26px] font-bold tracking-tight sm:text-[30px]">{title}</h1>
        {sub && <div className="mt-1.5 text-[15px] text-muted">{sub}</div>}
      </div>
      <div className="flex-1" />
      {right && <div className="flex flex-wrap items-center gap-2.5">{right}</div>}
    </header>
  );
}

export const Empty = ({ children }: { children: ReactNode }) => <div className="px-[18px] py-[22px] text-sm text-muted">{children}</div>;

export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden className={cx("animate-pulse rounded-[20px] bg-white/70", className)} />;
}

// ------------------------------------------------------------------ controls

export function Toggle({ on, onChange, label, disabled }: { on: boolean; onChange: (on: boolean) => void; label: string; disabled?: boolean }) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={on}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!on)}
      className={cx(
        "relative h-[26px] w-11 shrink-0 cursor-pointer rounded-full transition-colors disabled:opacity-50",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue",
        on ? "bg-lane-green" : "bg-[#D7DBE1]",
      )}
    >
      <span className={cx("absolute top-[3px] size-5 rounded-full bg-white shadow-sm transition-[left]", on ? "left-[21px]" : "left-[3px]")} />
    </button>
  );
}

export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: string }[];
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="flex rounded-full bg-soft p-1">
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cx(
            "min-h-9 cursor-pointer rounded-full px-3.5 text-[13px] font-bold transition-colors",
            value === o.value ? "bg-ink text-white" : "text-ink-2 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Field({ label, children, className }: { label: string; children: ReactNode; className?: string }) {
  return (
    <label className={cx("flex flex-col gap-1.5 text-[13px] font-semibold text-muted", className)}>
      {label}
      {children}
    </label>
  );
}

export const inputClass =
  "min-h-11 rounded-[14px] border-0 bg-soft px-3.5 text-[15px] font-medium text-ink outline-none placeholder:text-muted/70 focus:ring-2 focus:ring-blue";

// ------------------------------------------------------------------ live time

/** "4:05" since `from`, ticking. Its own component so only this text re-renders each second. */
export const Elapsed = memo(function Elapsed({ from, className }: { from: string; className?: string }) {
  const now = useNow();
  return <span className={className}>{now ? elapsed(from, now) : "…"}</span>;
});
