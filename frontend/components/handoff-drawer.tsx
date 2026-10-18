"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, useAction, useCall } from "@/lib/api";
import { clock, phone, seconds } from "@/lib/format";
import { DETAIL_FIELD, DETAIL_STATUS, FLAG, LANE, LANE_ORDER, REASON, TRANSFER, humanize, label } from "@/lib/labels";
import type { CallDetail, Lane } from "@/lib/types";
import { useSelectedCall } from "./selected-call";
import { Button, Chip, LANE_BG, LANE_TONE, Spinner, cx, inputClass } from "./ui";

/** The Handoff Card: everything a nurse or supervisor needs about one call. */
export function HandoffDrawer() {
  const { id, close } = useSelectedCall();
  const { data: c, error } = useCall(id);
  const closeBtn = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);

  useEffect(() => {
    if (!id) return;
    opener.current = document.activeElement;
    closeBtn.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && close();
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
      (opener.current as HTMLElement | null)?.focus?.();
    };
  }, [id, close]);

  if (!id) return null;
  const stale = c && c.call_id !== id; // keepPreviousData: don't show the last call under the new id

  return (
    <>
      <div className="animate-fade-in fixed inset-0 z-20 bg-ink/30" onClick={close} aria-hidden />
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Handoff Card"
        className="animate-drawer-in fixed inset-2 z-30 flex flex-col overflow-hidden rounded-3xl border border-line bg-white shadow-2xl sm:inset-auto sm:bottom-5 sm:right-5 sm:top-5 sm:w-[min(560px,calc(100vw-40px))]"
      >
        <div className="flex items-start gap-3 border-b border-hair px-[22px] pb-3.5 pt-5">
          <div className="min-w-0 flex-1">
            {c && !stale ? (
              <>
                <div className="text-[13px] font-bold text-muted">
                  Handoff Card · arrived {clock(c.started_at)} · {c.source === "simulated" ? "simulated" : "live call"}
                  {c.on_line && " · on the line now"}
                </div>
                <h2 className="truncate text-[22px] font-extrabold">{c.caller_name || "Unknown caller"}</h2>
                <div className="mt-0.5 font-semibold tabular-nums">
                  {phone(c.callback_number || c.from_number)}
                  {c.callback_source && <span className="ml-2 text-[13px] font-medium text-muted">{c.callback_source === "confirmed" ? "read back and confirmed" : "from caller ID"}</span>}
                </div>
              </>
            ) : (
              <h2 className="text-[22px] font-extrabold">Handoff Card</h2>
            )}
          </div>
          {c && !stale && (
            <Chip tone={c.lane ? LANE_TONE[c.lane] : "grey"} className="px-3 py-1.5 text-[13px]">
              {c.lane ? LANE[c.lane] : "Sorting"}
            </Chip>
          )}
          <Button ref={closeBtn} size="sm" onClick={close} aria-label="Close Handoff Card">
            ✕
          </Button>
        </div>
        {error && !c ? (
          <div className="p-6 text-muted">This call couldn&apos;t be loaded. It may have been removed by a board reset.</div>
        ) : !c || stale ? (
          <div className="flex items-center gap-2 p-6 text-muted">
            <Spinner /> Loading the call…
          </div>
        ) : (
          <Body c={c} />
        )}
      </aside>
    </>
  );
}

function Body({ c }: { c: CallDetail }) {
  const rr = c.rules_result;
  const jev = c.jev_result;
  const flagToTransfer = seconds(c.red_flag_at, c.transfer_started_at);
  const toNurse = c.transfer_status === "connected" ? seconds(c.transfer_started_at, c.transfer_ended_at) : null;
  const details = Object.entries(c.details ?? {});

  return (
    <>
      <div className="flex flex-1 flex-col gap-[18px] overflow-auto overscroll-contain px-[22px] pb-[22px] pt-4">
        <Sec title="Why they called">
          <div className="text-base font-bold">{c.intent || c.summary || "—"}</div>
          {c.summary && c.intent && <p className="mt-1.5 text-sm text-ink-2">{c.summary}</p>}
        </Sec>

        <Sec title="Red-flag screen">
          <div className="flex flex-wrap gap-1.5">
            {c.red_flags.length ? c.red_flags.map((f) => <Chip key={f} tone="red">{label(FLAG, f)}</Chip>) : <Chip tone="green">No red flags</Chip>}
            {c.reason && <Chip tone="amber">{label(REASON, c.reason)}</Chip>}
            {c.needs_review && <Chip>Needs review</Chip>}
          </div>
        </Sec>

        <Sec title="Why this lane">
          <div className="grid grid-cols-[auto_1fr] items-center gap-x-3 gap-y-2 rounded-[14px] bg-soft px-3.5 py-3 text-sm">
            <span className="text-muted">Rules</span>
            <span>
              <b>{rr?.lane ? LANE[rr.lane] : "No lane"}</b>
              {rr?.red_flags?.length ? ` · ${rr.red_flags.map((f) => label(FLAG, f)).join(", ")}` : ""}
              {rr?.reason ? ` · ${label(REASON, rr.reason)}` : ""}
            </span>
            <span className="text-muted">Model</span>
            <span>
              {jev?.lane ? (
                <>
                  <b>{LANE[jev.lane]}</b>
                  {jev.confidence != null && <span className="ml-1.5 rounded-lg bg-ink px-2 py-[3px] text-xs font-bold tabular-nums text-white">{Math.round(jev.confidence * 100)}%</span>}
                  {jev.latency_ms != null && <span className="ml-1.5 text-muted">{jev.latency_ms} ms</span>}
                </>
              ) : (
                <span className="text-muted">Not run (rules only)</span>
              )}
            </span>
            <span className="text-muted">Final</span>
            <span>
              <b>{c.lane ? LANE[c.lane] : "—"}</b> · the higher lane wins. Only a person can lower a lane.
            </span>
          </div>
        </Sec>

        {(c.transfer_status || c.red_flag_at) && (
          <Sec title="Warm transfer">
            <div className="grid grid-cols-[auto_1fr_auto] items-center gap-x-3 gap-y-2 text-sm">
              <span className="text-muted">Outcome</span>
              <span className="font-bold">{c.transfer_status ? TRANSFER[c.transfer_status]?.label : "In progress"}</span>
              {c.transfer_status ? <Chip tone={TRANSFER[c.transfer_status]?.tone ?? "grey"}>{humanize(c.transfer_status)}</Chip> : <span />}
              <span className="text-muted">Red flag → transfer</span>
              <span className="font-bold tabular-nums">{flagToTransfer == null ? "—" : `${flagToTransfer.toFixed(1)} s`}</span>
              <Chip tone={flagToTransfer != null && flagToTransfer > 10 ? "amber" : "grey"}>target 10 s</Chip>
              {toNurse != null && (
                <>
                  <span className="text-muted">Nurse answered in</span>
                  <span className="font-bold tabular-nums">{toNurse.toFixed(1)} s</span>
                  <span />
                </>
              )}
              <span className="text-muted">Nurse line</span>
              <span className="tabular-nums">{c.transfer_target ? phone(c.transfer_target) : "—"}</span>
              <span />
            </div>
          </Sec>
        )}

        {details.length > 0 && (
          <Sec title="Details, read back to the caller">
            <div className="flex flex-col gap-2.5">
              {details.map(([field, d]) => {
                const st = DETAIL_STATUS[d.status] ?? { tone: "grey" as const, label: d.status };
                const misheard = d.model_heard && d.model_heard !== d.value;
                return (
                  <div key={field} className="grid grid-cols-[88px_1fr_auto] items-start gap-x-3 text-sm">
                    <span className="pt-0.5 text-muted">{DETAIL_FIELD[field] ?? humanize(field)}</span>
                    <span className="min-w-0">
                      <span className="font-bold tabular-nums">{field === "callback_number" ? phone(d.value) : d.value}</span>
                      {d.read_back && <span className="block text-[13px] text-muted">Read back: “{d.read_back}”</span>}
                      {misheard && (
                        <span className="block text-[13px] text-amber-ink">
                          Speech model heard {field === "callback_number" ? phone(d.model_heard) : d.model_heard}; the transcript wins.
                        </span>
                      )}
                    </span>
                    <Chip tone={st.tone}>
                      {st.label}
                      {d.attempts && d.attempts > 1 ? ` · ${d.attempts} tries` : ""}
                    </Chip>
                  </div>
                );
              })}
            </div>
          </Sec>
        )}

        {c.has_recording && (
          <Sec title="Recording">
            <audio controls preload="none" src={`/api/calls/${encodeURIComponent(c.call_id)}/recording`} className="w-full" />
          </Sec>
        )}

        <Sec title="What was said">
          <Transcript items={c.transcript} live={c.status === "ongoing"} />
        </Sec>

        <Sec title="Ladder">
          <Ladder lane={c.lane} />
        </Sec>

        <Sec title="Log">
          <div className="flex flex-col gap-1.5 text-[13px]">
            {c.events.length ? (
              c.events.slice(-12).map((e, i) => (
                <div key={i} className="flex gap-2.5">
                  <span className="shrink-0 tabular-nums text-muted">{clock(e.created_at)}</span>
                  <span>
                    {humanize(e.type)}
                    {e.actor === "supervisor" && <b> · you</b>}
                    {typeof e.payload?.reason === "string" && <span className="text-muted"> · “{e.payload.reason}”</span>}
                  </span>
                </div>
              ))
            ) : (
              <span className="text-muted">No events.</span>
            )}
          </div>
        </Sec>
      </div>
      <LaneFooter c={c} />
    </>
  );
}

function Transcript({ items, live }: { items: CallDetail["transcript"]; live: boolean }) {
  const end = useRef<HTMLDivElement>(null);
  const count = items.length;
  useEffect(() => {
    if (live) end.current?.scrollIntoView({ block: "nearest" });
  }, [count, live]);

  if (!count) return <span className="text-sm text-muted">{live ? "Waiting for the first words…" : "No transcript."}</span>;
  return (
    <div className="flex flex-col gap-2">
      {items.map((t) =>
        t.role === "user" || t.role === "agent" ? (
          <div
            key={t.item_id}
            className={cx(
              "max-w-[88%] rounded-[14px] px-3 py-2.5 text-sm leading-normal",
              t.role === "user" ? "self-start rounded-bl-[4px] bg-blue-tint" : "self-end rounded-br-[4px] bg-soft",
            )}
          >
            <b className="block text-[11px] tracking-wider text-muted">{t.role === "user" ? "CALLER" : "AI"}</b>
            {t.content}
          </div>
        ) : (
          <div key={t.item_id} className="self-center text-xs text-muted">
            {systemLine(t.role, t.content)}
          </div>
        ),
      )}
      <div ref={end} />
    </div>
  );
}

function systemLine(role: string, content: string | null): string {
  try {
    const j = content ? JSON.parse(content) : {};
    if (role === "node_transition") return `→ ${humanize(j.new_node_name ?? j.node_name ?? "next step")}`;
    if (role === "tool_call_invocation") return `Tool: ${humanize(j.name ?? "call")}`;
    if (role === "tool_call_result") return "Tool result received";
  } catch {
    /* content wasn't JSON */
  }
  return humanize(role);
}

const STEPS = ["Ask", "Slow", "Hold: can wait", "Hold: a person soon", "Hand to a person"];
const STEP_OF: Record<Lane, number> = { green: 2, amber: 3, red: 4 };

function Ladder({ lane }: { lane: Lane | null }) {
  const step = lane ? STEP_OF[lane] : 0;
  return (
    <div className="grid grid-cols-5 gap-1.5 text-center text-xs font-bold">
      {STEPS.map((n, i) => (
        <div key={n}>
          <div className={cx("mb-1.5 h-2 rounded", i === step && lane ? LANE_BG[lane] : i < step ? "bg-[#C9D1DA]" : "bg-soft")} />
          <span className={i === step ? "" : "text-muted"}>{n}</span>
        </div>
      ))}
    </div>
  );
}

function LaneFooter({ c }: { c: CallDetail }) {
  const { run, pending } = useAction();
  const [target, setTarget] = useState<Lane | null>(null);
  const [reason, setReason] = useState("");
  const others = LANE_ORDER.filter((l) => l !== c.lane);

  const submit = async () => {
    if (!target) return;
    const ok = await run("lane", () => api.post(`/api/calls/${encodeURIComponent(c.call_id)}/lane`, { lane: target, reason }), {
      success: "Lane changed and logged under your name.",
    });
    if (ok) {
      setTarget(null);
      setReason("");
    }
  };

  return (
    <div className="border-t border-hair px-[22px] py-3.5">
      {target ? (
        <form
          className="flex flex-col gap-2.5"
          onSubmit={(e) => {
            e.preventDefault();
            submit();
          }}
        >
          <label className="text-[13px] font-semibold text-muted" htmlFor="lane-reason">
            Why move this caller to “{LANE[target]}”? This is logged under your name.
          </label>
          <input id="lane-reason" autoFocus required value={reason} onChange={(e) => setReason(e.target.value)} className={inputClass} placeholder="e.g. Spoke to the caller, routine refill only" />
          <div className="flex flex-wrap gap-2">
            <Button type="submit" variant="dark" busy={pending === "lane"} disabled={!reason.trim()}>
              Move to {LANE[target]}
            </Button>
            <Button onClick={() => setTarget(null)}>Cancel</Button>
          </div>
        </form>
      ) : (
        <Foot>
          {others.map((l) => (
            <Button key={l} size="sm" onClick={() => setTarget(l)}>
              {c.lane && LANE_ORDER.indexOf(l) > LANE_ORDER.indexOf(c.lane) ? "Lower" : "Raise"} to {LANE[l]}…
            </Button>
          ))}
        </Foot>
      )}
    </div>
  );
}

const Foot = ({ children }: { children: ReactNode }) => <div className="flex flex-wrap gap-2">{children}</div>;

const Sec = ({ title, children }: { title: string; children: ReactNode }) => (
  <section>
    <h3 className="mb-2 text-[13px] font-bold text-muted">{title}</h3>
    {children}
  </section>
);
