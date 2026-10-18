"use client";

import { memo, useMemo } from "react";
import { LANE, LANE_RULE } from "@/lib/labels";
import type { Board, CallRow as Row, Lane } from "@/lib/types";
import { useSelectedCall } from "../selected-call";
import { Card, Empty, LANE_BG, cx } from "../ui";
import { CallRow } from "./call-row";

export function matches(c: Row, q: string) {
  if (!q) return true;
  const t = q.toLowerCase();
  return [c.caller_name, c.intent, c.cluster, c.reason, c.callback_number, ...c.red_flags].some((v) => v?.toLowerCase().includes(t));
}

export function Lanes({ board, query }: { board: Board; query: string }) {
  const { id, open } = useSelectedCall();
  const cols: [Lane, Row[]][] = [
    ["red", board.red],
    ["amber", board.amber_queue],
    ["green", board.green],
  ];
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-3">
      {cols.map(([lane, calls]) => (
        <LaneColumn key={lane} lane={lane} calls={calls} count={board.lanes[lane] ?? 0} query={query} selected={id} onOpen={open} />
      ))}
    </div>
  );
}

const LaneColumn = memo(function LaneColumn({
  lane,
  calls,
  count,
  query,
  selected,
  onOpen,
}: {
  lane: Lane;
  calls: Row[];
  count: number;
  query: string;
  selected: string | null;
  onOpen: (id: string) => void;
}) {
  const shown = useMemo(() => calls.filter((c) => matches(c, query)), [calls, query]);
  return (
    <Card className="flex flex-col overflow-hidden" aria-label={LANE[lane]}>
      <div className={cx("h-[5px]", LANE_BG[lane])} />
      <div className="flex items-center gap-2.5 border-b border-hair px-[18px] py-4">
        <div>
          <h2 className="font-bold">{LANE[lane]}</h2>
          <div className="text-xs text-muted">{LANE_RULE[lane]}</div>
        </div>
        <span className="ml-auto text-[26px] font-extrabold tabular-nums">{count}</span>
      </div>
      <div className="flex max-h-[430px] flex-col overflow-auto overscroll-contain [contain:content]">
        {shown.length ? (
          shown.map((c) => <CallRow key={c.call_id} c={c} selected={selected === c.call_id} onOpen={onOpen} />)
        ) : (
          <Empty>{query ? "No calls match the filter." : lane === "red" ? "No red-flag callers right now." : "Nobody here yet."}</Empty>
        )}
      </div>
    </Card>
  );
});

/** Live calls the classifiers haven't placed yet. Only shown while there are some. */
export function Incoming({ calls }: { calls: Row[] }) {
  const { id, open } = useSelectedCall();
  if (!calls.length) return null;
  return (
    <Card className="overflow-hidden" aria-label="On the line, being sorted">
      <div className="flex items-center gap-2 px-5 pb-2 pt-4">
        <span className="animate-pulse-soft size-2 rounded-full bg-blue" />
        <h2 className="font-bold">On the line, being sorted</h2>
        <span className="text-[13px] text-muted">The red-flag screen runs on every word the caller says.</span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3">
        {calls.map((c) => (
          <CallRow key={c.call_id} c={c} selected={id === c.call_id} onOpen={open} />
        ))}
      </div>
    </Card>
  );
}
