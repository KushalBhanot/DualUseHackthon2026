"use client";

import { memo, useState } from "react";
import { api, useAction, useStatusMessages } from "@/lib/api";
import { pct, plural } from "@/lib/format";
import { CLUSTER, label } from "@/lib/labels";
import type { Board, Kpis, SurgeState } from "@/lib/types";
import { useSelectedCall } from "../selected-call";
import { Button, Card, CardHeader, Chip, Empty, Tag, cx } from "../ui";
import { LaneColumns, LaneLegend, Spark, minuteLabel } from "./charts";

// ------------------------------------------------------------------ KPIs

export const KpiRow = memo(function KpiRow({ k, last10 }: { k: Kpis; last10: number[] }) {
  const lateAmber = (k.oldest_amber_min ?? 0) > k.amber_target_min;
  return (
    <div className="grid grid-cols-2 gap-3 sm:gap-5 lg:grid-cols-5">
      <Tile label="Calls, last 10 min" value={k.calls_10min}>
        <Spark series={last10} className="mt-1.5 h-[34px]" barClass="bg-yellow" />
      </Tile>
      <Tile label="On the line now" value={k.on_line} note={`${k.total} tonight · ${k.hung_up} hung up`} />
      <Tile
        label="Red handoff, median"
        value={k.red_median_handoff_s == null ? "—" : `${k.red_median_handoff_s} s`}
        alert={k.red_not_connected > 0 ? "red" : undefined}
        note={k.red_not_connected ? <b className="text-red-ink">{k.red_not_connected} not connected</b> : "target under 10 s"}
      />
      <Tile
        label="Waiting for a person"
        value={k.amber_waiting}
        alert={lateAmber ? "amber" : undefined}
        note={
          <>
            oldest <Tag>{k.oldest_amber_min ?? 0} min</Tag> · target {k.amber_target_min}
          </>
        }
      />
      <section className="col-span-2 flex flex-col gap-1 rounded-[20px] bg-gradient-to-br from-[#5DB8F2] to-blue px-5 py-[18px] text-white lg:col-span-1">
        <span className="text-[13px] font-semibold opacity-95">Answered without a person</span>
        <span className="text-[30px] font-extrabold leading-tight tabular-nums">{pct(k.ai_handled_share)}</span>
        <div className="mt-1.5 h-1.5 rounded-full bg-white/35">
          <div className="h-1.5 rounded-full bg-white transition-[width] duration-500" style={{ width: `${Math.round((k.ai_handled_share ?? 0) * 100)}%` }} />
        </div>
        <span className="text-[13px] opacity-95">{plural(k.handled_by_ai, "caller")} got their answer · red flags always reach a nurse</span>
      </section>
    </div>
  );
});

function Tile({ label, value, note, alert, children }: { label: string; value: React.ReactNode; note?: React.ReactNode; alert?: "red" | "amber"; children?: React.ReactNode }) {
  return (
    <Card
      className={cx(
        "flex min-w-0 flex-col gap-1 px-5 py-[18px]",
        alert === "red" && "border-red-line bg-[#FFF8F8]",
        alert === "amber" && "border-amber-line bg-[#FFFBF3]",
      )}
    >
      <span className="text-[13px] font-semibold text-muted">{label}</span>
      <span className="text-[30px] font-extrabold leading-tight tabular-nums">{value}</span>
      {note && <span className="text-[13px] text-muted">{note}</span>}
      {children}
    </Card>
  );
}

// ------------------------------------------------------------------ status message banner

export function StatusBanner({ message }: { message: string | null }) {
  const { run, pending } = useAction();
  if (!message) return null;
  return (
    <section className="flex flex-wrap items-center gap-3 rounded-[20px] border border-blue-line bg-[#F5FAFE] px-5 py-4">
      <Chip tone="blue">Playing to every caller</Chip>
      <span className="min-w-0 flex-[1_1_400px]">{message}</span>
      <Button size="sm" busy={pending === "stopmsg"} onClick={() => run("stopmsg", () => api.post("/api/status-message", { text: null }), { success: "Status message stopped." })}>
        Stop message
      </Button>
    </section>
  );
}

// ------------------------------------------------------------------ watch: what callers keep asking

export const Watch = memo(function Watch({ clusters, series, active }: { clusters: Board["clusters"]; series: Board["cluster_series"]; active: string | null }) {
  return (
    <Card className="min-w-0 flex-[1.3_1_420px] overflow-hidden">
      <CardHeader title="Watch · what callers keep asking" hint="Calls grouped by topic. Sparklines show the last 10 minutes." right={<span className="text-[13px] font-semibold text-muted">last 3 h · sparkline 10 min</span>} />
      {clusters.length ? (
        clusters.slice(0, 7).map((c) => <ClusterRow key={c.cluster} c={c} series={series[c.cluster] ?? []} active={active} />)
      ) : (
        <Empty>Topics appear here as calls come in. One card instead of 140 calls.</Empty>
      )}
    </Card>
  );
});

function ClusterRow({ c, series, active }: { c: Board["clusters"][number]; series: number[]; active: string | null }) {
  const [picking, setPicking] = useState(false);
  const { data: msgs } = useStatusMessages();
  const { run, pending } = useAction();
  const templates = msgs?.templates.filter((t) => t.cluster === c.cluster) ?? [];
  const playing = templates.some((t) => t.text === active);

  return (
    <div className="border-t border-hair px-5 py-3">
      <div className="grid grid-cols-[1fr_auto] items-center gap-3">
        <div className="min-w-0">
          <div className="truncate font-bold">{label(CLUSTER, c.cluster)}</div>
          <div className="text-[13px] text-muted">
            <b className="tabular-nums text-ink">{c.calls}</b> callers ·{" "}
            {c.red_flags ? <b className="text-red-ink">{plural(c.red_flags, "red flag")}</b> : "0 red flags"}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <Spark series={series} className="hidden h-[22px] w-[70px] sm:flex" />
          {playing ? (
            <Chip tone="blue">Message playing</Chip>
          ) : templates.length ? (
            <Button size="sm" aria-expanded={picking} onClick={() => setPicking((p) => !p)}>
              Status message…
            </Button>
          ) : null}
        </div>
      </div>
      {picking && !playing && (
        <div className="animate-fade-in mt-3 flex flex-col gap-2">
          {templates.map((t) => (
            <div key={t.id} className="flex flex-wrap items-center gap-3 rounded-xl bg-soft px-3 py-2.5">
              <span className="min-w-0 flex-[1_1_240px] text-sm">{t.text}</span>
              <Button
                size="sm"
                variant="dark"
                busy={pending === t.id}
                onClick={async () => {
                  if (await run(t.id, () => api.post("/api/status-message", { text: t.text, template_id: t.id }), { success: "Status message now plays to every caller." })) setPicking(false);
                }}
              >
                Play this
              </Button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// ------------------------------------------------------------------ volume

export const Volume = memo(function Volume({ data }: { data: Board["volume_1min"] }) {
  return (
    <Card className="min-w-0 flex-[1_1_360px] pb-4">
      <CardHeader title="Calls per minute" right={<LaneLegend />} />
      <div className="px-5">
        <LaneColumns data={data} bucketLabel={minuteLabel} caption="Calls per minute over the last 20 minutes, by lane" />
        <div className="flex justify-between pt-1.5 text-xs text-muted">
          <span>20 min ago</span>
          <span>now</span>
        </div>
      </div>
    </Card>
  );
});

// ------------------------------------------------------------------ respond bar

export function RespondBar({ board }: { board: Board }) {
  const { open } = useSelectedCall();
  const { run, pending } = useAction();
  const s: SurgeState = board.surge;
  const next = board.amber_queue[0];
  return (
    <div className="fixed inset-x-3 bottom-3 z-10 flex items-center sm:flex-wrap gap-2.5 rounded-[28px] bg-navy py-2.5 pl-2.5 pr-2.5 text-white shadow-xl sm:pl-5 sm:rounded-full md:bottom-8 md:left-[116px] md:right-10">
      <b className="hidden text-sm sm:inline">Response</b>
      <span className="hidden text-[13px] text-[#9AA3B5] lg:inline">The AI sorts. Surge mode, broadcasts and call-ins wait for you.</span>
      <span className="hidden flex-1 sm:block" />
      {next && (
        <Button variant="ghost-dark" className="min-w-0 flex-1 sm:max-w-[260px] sm:flex-none" onClick={() => open(next.call_id)}>
          <span className="truncate">
            <span className="hidden sm:inline">Next callback: </span>
            <span className="sm:hidden">Next: </span>
            {next.caller_name || "caller"}
          </span>
        </Button>
      )}
      <Button
        variant={s.surge_on ? "ghost-dark" : "amber"}
        busy={pending === "surge"}
        onClick={() => run("surge", () => api.post("/api/surge", { on: !s.surge_on }), { success: s.surge_on ? "Surge mode off." : "Surge mode on." })}
      >
        <span className="sm:hidden">{s.surge_on ? "Surge off" : "Surge on"}</span>
        <span className="hidden sm:inline">{s.surge_on ? "Switch surge mode off" : "Switch on surge mode"}</span>
      </Button>
    </div>
  );
}
