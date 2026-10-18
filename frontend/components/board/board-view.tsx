"use client";

import { useDeferredValue, useEffect, useMemo, useRef, useState } from "react";
import { useBoard, useNow, useSim, useSuggestions } from "@/lib/api";
import { clock } from "@/lib/format";
import { ConnectionBanner } from "../connection";
import { PageHeader, Skeleton, cx } from "../ui";
import { Decisions } from "./decisions";
import { Incoming, Lanes } from "./lanes";
import { KpiRow, RespondBar, StatusBanner, Volume, Watch } from "./panels";

export function BoardView() {
  const { data: board, error } = useBoard();
  const { data: suggestions } = useSuggestions();
  const { data: sim } = useSim();
  const [query, setQuery] = useState("");
  const deferredQuery = useDeferredValue(query);
  const search = useRef<HTMLInputElement>(null);

  // ⌘K / Ctrl+K focuses the filter. The listener is removed while the board is hidden.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const last10 = useMemo(() => board?.volume_1min.slice(-10).map((b) => b.calls) ?? [], [board?.volume_1min]);
  const scenario = sim?.scenario ? sim.scenarios.find((s) => s.id === sim.scenario)?.label : null;

  return (
    <>
      <PageHeader
        title="Night shift, K. Mensah"
        sub={
          <>
            Harbor General · after-hours line · <LiveClock />
            {scenario && <> · simulated: {scenario}</>}
          </>
        }
        right={
          <>
            {board && <SurgeBadge on={board.surge.surge_on} />}
            <label className="flex min-h-12 min-w-0 flex-1 items-center gap-2.5 rounded-2xl bg-soft pl-4 pr-2 sm:min-w-[260px] sm:flex-none">
              <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden>
                <circle cx="11" cy="11" r="7" fill="none" stroke="#6B7280" strokeWidth="2" />
                <path d="M20 20l-4-4" stroke="#6B7280" strokeWidth="2" strokeLinecap="round" />
              </svg>
              <span className="sr-only">Filter calls</span>
              <input
                ref={search}
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onKeyDown={(e) => e.key === "Escape" && setQuery("")}
                placeholder="Filter callers, intents…"
                className="min-w-0 flex-1 bg-transparent text-[15px] outline-none"
              />
              <kbd className="hidden rounded-[10px] bg-white px-2.5 py-1.5 font-sans text-[13px] text-muted sm:inline">⌘ K</kbd>
            </label>
          </>
        }
      />

      <ConnectionBanner error={error} hasData={!!board} />

      {!board ? (
        <BoardSkeleton />
      ) : (
        <>
          <Decisions list={suggestions ?? []} />
          <StatusBanner message={board.surge.status_message} />
          <KpiRow k={board.kpis} last10={last10} />
          <Incoming calls={board.unsorted} />
          <Lanes board={board} query={deferredQuery} />
          <div className="flex flex-wrap items-start gap-5">
            <Watch clusters={board.clusters} series={board.cluster_series} active={board.surge.status_message} />
            <Volume data={board.volume_1min} />
          </div>
          <RespondBar board={board} />
        </>
      )}
    </>
  );
}

function LiveClock() {
  const now = useNow();
  return <span className="tabular-nums">{now ? clock(now) : "--:--:--"}</span>;
}

function SurgeBadge({ on }: { on: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex min-h-11 items-center gap-2 rounded-full px-4 text-sm font-extrabold",
        on ? "border border-amber-line bg-amber-tint text-amber-ink" : "bg-soft text-ink-2",
      )}
    >
      {on && <span className="animate-pulse-soft size-2 rounded-full bg-lane-amber" />}
      {on ? "Surge mode on" : "Surge mode off"}
    </span>
  );
}

function BoardSkeleton() {
  return (
    <>
      <div className="grid grid-cols-2 gap-5 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-[120px] bg-soft" />
        ))}
      </div>
      <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
        {Array.from({ length: 3 }, (_, i) => (
          <Skeleton key={i} className="h-[320px] bg-soft" />
        ))}
      </div>
    </>
  );
}
