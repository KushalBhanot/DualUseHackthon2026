"use client";

import { memo } from "react";
import { FLAG, REASON, TRANSFER, label } from "@/lib/labels";
import type { CallRow as Row, Lane } from "@/lib/types";
import { Chip, Elapsed, cx } from "../ui";

const RANK: Record<Lane, number> = { green: 0, amber: 1, red: 2 };

export const CallRow = memo(function CallRow({ c, selected, onOpen }: { c: Row; selected: boolean; onOpen: (id: string) => void }) {
  const live = c.source === "retell";
  // The model placed it lower and the rules raised it: the "higher lane wins" safety net at work.
  const rulesCaught = c.jev_lane && c.lane && c.rules_lane === c.lane && RANK[c.lane] > RANK[c.jev_lane];

  return (
    <button
      type="button"
      onClick={() => onOpen(c.call_id)}
      aria-current={selected || undefined}
      className={cx(
        "grid w-full cursor-pointer grid-cols-[1fr_auto] gap-x-2.5 gap-y-[3px] border-t border-[#F3F4F6] px-[18px] py-3 text-left first:border-t-0",
        "focus-visible:relative focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-blue",
        selected ? "bg-blue-tint" : "hover:bg-[#FAFBFC]",
      )}
    >
      <span className="flex min-w-0 items-center gap-2 text-sm font-bold">
        {c.on_line && <span className="animate-pulse-soft size-2 shrink-0 rounded-full bg-lane-red" aria-label="On the line" title="On the line" />}
        <span className="truncate">{c.caller_name || "Unknown caller"}</span>
      </span>
      <span className="rounded-lg bg-ink px-2 py-[3px] text-xs font-bold tabular-nums text-white" title="Time since the call came in">
        <Elapsed from={c.started_at} />
      </span>
      <span className="col-span-2 truncate text-[13px] text-ink-2">{c.intent || (c.on_line ? "On the line, listening…" : "No intent recorded")}</span>
      <span className="col-span-2 flex flex-wrap items-center gap-1.5 empty:hidden">
        {c.red_flags.map((f) => (
          <Chip key={f} tone="red-soft">
            {label(FLAG, f)}
          </Chip>
        ))}
        {c.lane === "amber" && c.reason && <Chip tone="amber">{label(REASON, c.reason)}</Chip>}
        {c.transfer_status && <Chip tone={TRANSFER[c.transfer_status]?.tone ?? "grey"}>{TRANSFER[c.transfer_status]?.label ?? c.transfer_status}</Chip>}
        {c.disconnection_reason === "user_hangup" && <Chip>Hung up</Chip>}
        {rulesCaught && (
          <Chip tone="blue" title={`The model said ${c.jev_lane}; the rules raised it`}>
            Rules caught it
          </Chip>
        )}
        {c.needs_review && <Chip>Review</Chip>}
        {live && <Chip tone="purple">Live call</Chip>}
      </span>
    </button>
  );
});
