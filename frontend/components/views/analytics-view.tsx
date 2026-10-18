"use client";

import { useState, type ReactNode } from "react";
import { useAnalytics } from "@/lib/api";
import { clock, num, pct } from "@/lib/format";
import { LANE, LANE_ORDER, humanize } from "@/lib/labels";
import { LaneColumns, LaneDonut, LaneLegend } from "../board/charts";
import { ConnectionBanner } from "../connection";
import { Card, CardHeader, Empty, LANE_BG, PageHeader, Segmented, Skeleton, cx } from "../ui";

const WINDOWS = [
  { value: "60", label: "1 h" },
  { value: "180", label: "3 h" },
  { value: "720", label: "12 h" },
];

const EVENT_NOTES: Record<string, string> = {
  red_flag_detected: "red flags detected while the caller was talking",
  context_injected: "times the agent was steered to a nurse mid-call",
  rules_miss: "red flags the model caught and the rules missed",
  stt_model_mismatch: "details the speech model misheard; the transcript won",
  detail_confirmed: "details read back and confirmed",
  detail_rejected: "read-backs the caller said were wrong",
  confirm_disagreement: "agent said confirmed, caller's words didn't",
  analysis_mismatch: "post-call analysis disagreed with a captured detail",
};

export function AnalyticsView() {
  const [win, setWin] = useState("60");
  const { data: a, error } = useAnalytics(Number(win));

  return (
    <>
      <PageHeader
        title="Analytics"
        sub="How the line, the rules and the model are doing."
        right={<Segmented label="Time window" value={win} onChange={setWin} options={WINDOWS} />}
      />
      <ConnectionBanner error={error} hasData={!!a} />
      {!a ? (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          <Skeleton className="h-[200px] bg-soft" />
          <Skeleton className="h-[200px] bg-soft" />
        </div>
      ) : (
        <>
          <div className="flex flex-wrap gap-5">
            <Card className="flex flex-[1_1_360px] flex-wrap items-center gap-6 p-5">
              <LaneDonut mix={a.lane_mix} />
              <div className="grid flex-1 grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2.5 text-sm">
                {LANE_ORDER.map((l) => (
                  <Legend key={l} swatch={LANE_BG[l]} label={LANE[l]} value={a.lane_mix[l]} />
                ))}
              </div>
            </Card>
            <Card className="min-w-0 flex-[2_1_480px] pb-4">
              <CardHeader title="Calls per 5 minutes" right={<LaneLegend />} />
              <div className="px-5">
                {a.volume_5min.length ? (
                  <LaneColumns data={a.volume_5min} height={150} bucketLabel={(b) => clock(b.bucket).slice(0, 5)} caption="Calls per 5 minutes by lane" />
                ) : (
                  <Empty>No calls in this window.</Empty>
                )}
              </div>
            </Card>
          </div>

          <h2 className="mt-2 text-lg font-bold">Red-flag handoffs</h2>
          <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
            <Stat label="Red-flag calls" value={a.handoff.red_calls} note={`${a.handoff.connected} reached a nurse`} />
            <Stat label="Red flag → transfer" value={num(a.handoff.mean_sec_flag_to_transfer, " s")} note="mean · target under 10 s" />
            <Stat label="Nurse answered in" value={num(a.handoff.mean_sec_to_nurse_answer, " s")} note="mean, connected transfers" />
            <Stat
              label="Told to call 911"
              value={pct(a.handoff.share_told_to_call_911)}
              note={`${a.handoff.told_to_call_911} no answer · ${a.handoff.other_not_connected} other`}
              alert={(a.handoff.share_told_to_call_911 ?? 0) > 0.2}
            />
          </div>

          <h2 className="mt-2 text-lg font-bold">Classifiers and details</h2>
          <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-4">
            <Stat
              label="Rules and model agree"
              value={a.classifiers.jev_classified ? pct(a.classifiers.rules_jev_agree / a.classifiers.jev_classified) : "—"}
              note={a.classifiers.jev_classified ? `${a.classifiers.jev_classified} calls run through Jev` : "Jev not configured: rules only"}
            />
            <Stat label="Model confidence" value={a.classifiers.mean_jev_confidence == null ? "—" : pct(a.classifiers.mean_jev_confidence)} note={`mean · ${num(a.classifiers.mean_jev_latency_ms, " ms")} latency`} />
            <Stat label="Details confirmed" value={pct(a.details.confirmation_rate)} note={`${a.details.confirmed ?? 0} confirmed · ${a.details.unconfirmed ?? 0} unconfirmed`} />
            <Stat label="Rules misses" value={a.events.rules_miss ?? 0} note="model caught a red flag the rules missed" />
          </div>

          <Card className="overflow-hidden">
            <CardHeader title="What the safety nets did" />
            {Object.keys(a.events).length ? (
              <table className="w-full text-sm">
                <tbody>
                  {Object.entries(a.events)
                    .sort((x, y) => y[1] - x[1])
                    .map(([type, n]) => (
                      <tr key={type} className="border-t border-hair">
                        <td className="w-16 px-5 py-3 text-right text-base font-extrabold tabular-nums">{n}</td>
                        <td className="px-3 py-3">
                          <b>{humanize(type)}</b>
                          <span className="ml-2 text-muted">{EVENT_NOTES[type]}</span>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            ) : (
              <Empty>Nothing yet in this window.</Empty>
            )}
          </Card>
        </>
      )}
    </>
  );
}

function Legend({ swatch, label, value }: { swatch: string; label: string; value: number }) {
  return (
    <>
      <span className={cx("h-2.5 w-3.5 rounded-[3px]", swatch)} />
      <span>{label}</span>
      <b className="tabular-nums">{value}</b>
    </>
  );
}

function Stat({ label, value, note, alert }: { label: string; value: ReactNode; note: string; alert?: boolean }) {
  return (
    <Card className={cx("flex min-w-0 flex-col gap-1 px-5 py-[18px]", alert && "border-red-line bg-[#FFF8F8]")}>
      <span className="text-[13px] font-semibold text-muted">{label}</span>
      <span className="text-[30px] font-extrabold leading-tight tabular-nums">{value}</span>
      <span className="text-[13px] text-muted">{note}</span>
    </Card>
  );
}
