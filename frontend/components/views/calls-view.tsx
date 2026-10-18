"use client";

import { memo, useDeferredValue, useMemo, useState } from "react";
import { useCalls } from "@/lib/api";
import { clock } from "@/lib/format";
import { CLUSTER, FLAG, LANE, TRANSFER, label } from "@/lib/labels";
import type { CallRow, Lane } from "@/lib/types";
import { matches } from "../board/lanes";
import { ConnectionBanner } from "../connection";
import { useSelectedCall } from "../selected-call";
import { Card, Chip, LANE_TONE, PageHeader, Segmented, cx, inputClass } from "../ui";

const LANES: { value: Lane | ""; label: string }[] = [
  { value: "", label: "All" },
  { value: "red", label: LANE.red },
  { value: "amber", label: LANE.amber },
  { value: "green", label: LANE.green },
];
const SOURCES = [
  { value: "", label: "All sources" },
  { value: "retell", label: "Live" },
  { value: "simulated", label: "Simulated" },
];

export function CallsView() {
  const [lane, setLane] = useState<Lane | "">("");
  const [source, setSource] = useState("");
  const [query, setQuery] = useState("");
  const q = useDeferredValue(query);
  const { data, error, isLoading } = useCalls(lane, source);
  const { id, open } = useSelectedCall();
  const rows = useMemo(() => (data ?? []).filter((c) => matches(c, q)), [data, q]);

  return (
    <>
      <PageHeader
        title="All calls"
        sub="Every call, newest first. Click one for its Handoff Card."
        right={
          <>
            <Segmented label="Source" value={source} onChange={setSource} options={SOURCES} />
            <Segmented label="Lane" value={lane} onChange={setLane} options={LANES} />
          </>
        }
      />
      <ConnectionBanner error={error} hasData={!!data} />
      <input type="search" aria-label="Filter calls" placeholder="Filter by caller, intent, topic, number…" value={query} onChange={(e) => setQuery(e.target.value)} className={cx(inputClass, "max-w-md")} />
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="bg-band text-left text-[13px] font-semibold text-muted">
                <th className="px-3 py-2.5 font-semibold">Time</th>
                <th className="px-3 py-2.5 font-semibold">Lane</th>
                <th className="px-3 py-2.5 font-semibold">Caller</th>
                <th className="px-3 py-2.5 font-semibold">Why they called</th>
                <th className="px-3 py-2.5 font-semibold">Topic</th>
                <th className="px-3 py-2.5 font-semibold">Outcome</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c) => (
                <Row key={c.call_id} c={c} selected={id === c.call_id} onOpen={open} />
              ))}
              {!rows.length && (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-muted">
                    {isLoading ? "Loading calls…" : q ? "No calls match the filter." : "No calls yet. Start a scenario from Demo controls, or call the line."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>
      {data && data.length >= 300 && <p className="text-[13px] text-muted">Showing the newest 300 calls.</p>}
    </>
  );
}

const Row = memo(function Row({ c, selected, onOpen }: { c: CallRow; selected: boolean; onOpen: (id: string) => void }) {
  return (
    <tr
      tabIndex={0}
      onClick={() => onOpen(c.call_id)}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen(c.call_id))}
      className={cx("cursor-pointer border-t border-hair outline-none focus-visible:bg-blue-tint", selected ? "bg-blue-tint" : "hover:bg-[#FAFBFC]")}
    >
      <td className="whitespace-nowrap px-3 py-3 tabular-nums">{clock(c.started_at)}</td>
      <td className="px-3 py-3">{c.lane ? <Chip tone={LANE_TONE[c.lane]}>{LANE[c.lane]}</Chip> : <Chip>Sorting</Chip>}</td>
      <td className="whitespace-nowrap px-3 py-3 font-bold">
        {c.caller_name || "Unknown"}
        {c.source === "retell" && (
          <Chip tone="purple" className="ml-2">
            Live
          </Chip>
        )}
      </td>
      <td className="min-w-[220px] px-3 py-3">
        {c.intent || "—"}
        {c.red_flags.length > 0 && <span className="block text-[13px] font-semibold text-red-ink">{c.red_flags.map((f) => label(FLAG, f)).join(", ")}</span>}
      </td>
      <td className="px-3 py-3">{label(CLUSTER, c.cluster)}</td>
      <td className="whitespace-nowrap px-3 py-3">
        {c.transfer_status ? TRANSFER[c.transfer_status]?.label : c.on_line ? "On the line" : c.disconnection_reason === "user_hangup" ? "Hung up" : "Handled"}
      </td>
    </tr>
  );
});
