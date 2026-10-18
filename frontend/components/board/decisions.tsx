"use client";

import { useState, type ReactNode } from "react";
import { api, useAction } from "@/lib/api";
import { phone, pct, plural } from "@/lib/format";
import { CLUSTER, FLAG, RESOLVE_OUTCOME, TRANSFER, label } from "@/lib/labels";
import type { Suggestion } from "@/lib/types";
import { useSelectedCall } from "../selected-call";
import { Button, cx } from "../ui";

type Act = ReturnType<typeof useAction>;
const TOAST = {
  accept: "Done. Logged as your decision.",
  snooze: "OK. I'll ask again in 2 minutes.",
  dismiss: "Dismissed.",
  resolve: "Alert closed and logged.",
};

/** Everything the line suggested that needs a person. Red alerts first. */
export function Decisions({ list }: { list: Suggestion[] }) {
  const action = useAction();
  const [showAllRed, setShowAllRed] = useState(false);
  if (!list.length) return null;

  const reds = list.filter((s) => s.type === "red_not_connected");
  const rest = list.filter((s) => s.type !== "red_not_connected");
  // Show two red alerts in full and fold the rest, so the other decisions stay visible.
  const shown = showAllRed ? reds : reds.slice(0, 2);
  const hidden = showAllRed ? [] : reds.slice(2);

  return (
    <section className="flex flex-col gap-3" aria-label="Decisions waiting for you">
      {shown.map((s) => (
        <Decision key={s.id} s={s} action={action} />
      ))}
      {hidden.length > 0 && (
        <div className="flex flex-wrap items-center gap-3 rounded-[20px] border border-red-line bg-red-tint px-5 py-3">
          <b className="text-red-ink">+{plural(hidden.length, "more red caller")} not connected</b>
          <span className="min-w-0 flex-[1_1_300px] truncate">{hidden.map((s) => s.evidence.caller_name || "Caller").join(" · ")}</span>
          <Button size="sm" onClick={() => setShowAllRed(true)}>
            Show all
          </Button>
        </div>
      )}
      {rest.map((s) => (
        <Decision key={s.id} s={s} action={action} />
      ))}
    </section>
  );
}

function decide(action: Act, s: Suggestion, verb: keyof typeof TOAST, body?: unknown) {
  return action.run(`${s.id}:${verb}`, () => api.post(`/api/suggestions/${s.id}/${verb}`, body), {
    success: TOAST[verb],
    // Take the card off the board right away; the refresh that follows confirms it.
    optimistic: () => action.mutate("/api/suggestions", (list?: Suggestion[]) => list?.filter((x) => x.id !== s.id), { revalidate: false }),
  });
}

function Decision({ s, action }: { s: Suggestion; action: Act }) {
  const busy = (verb: string) => action.pending === `${s.id}:${verb}`;
  const standard = (acceptLabel: string, variant: "dark" | "amber" = "dark", dark = false) => (
    <>
      <Button variant={variant} busy={busy("accept")} onClick={() => decide(action, s, "accept")}>
        {acceptLabel}
      </Button>
      <Button variant={dark ? "ghost-dark" : "default"} busy={busy("snooze")} onClick={() => decide(action, s, "snooze")}>
        Not yet, ask in 2 min
      </Button>
      <Button variant={dark ? "ghost-dark" : "default"} size="sm" busy={busy("dismiss")} onClick={() => decide(action, s, "dismiss")}>
        Dismiss
      </Button>
    </>
  );

  switch (s.type) {
    case "red_not_connected":
      return <RedAlert s={s} action={action} />;

    case "surge_mode": {
      const e = s.evidence;
      return (
        <Shell tone="navy" kicker="Decision 1 · suggested by the line, needs you" title="Switch on surge mode?" actions={standard("Switch on surge mode", "amber", true)}>
          <Evidence dark>
            <Ev v={e.calls} l={`calls in ${e.window_min} min (normal ≈ ${Math.round(e.normal)})`} />
            <Ev v={e.red_waiting} l="red flags waiting" />
            <Ev v={e.hung_up_early} l="hung up early" />
          </Evidence>
          <p className="text-[13px] text-[#AEB6C6]">Surge mode gives held callers the longer surge callback windows. Only a person can switch it on.</p>
        </Shell>
      );
    }

    case "status_message":
      return <StatusMessageDecision s={s} action={action} busy={busy} />;

    case "staffing_nurses": {
      const e = s.evidence;
      const n = s.recommendation.count;
      return (
        <Shell kicker="Decision 3 · staffing" title={`Call in ${plural(n, "nurse")}?`} actions={standard("Record: call them in")}>
          <Evidence>
            <Ev v={e.amber_queue} l="waiting for a person" />
            <Ev v={`${e.oldest_amber_min} min`} l="oldest wait" />
            <Ev v={e.red_calls} l="red calls, 30 min" />
            {e.red_no_answer > 0 && <Ev v={e.red_no_answer} l="sent to 911" />}
            <Ev v={e.on_phones} l="nurses on phones" />
          </Evidence>
          <p className="text-[13px] text-muted">Accepting records your decision. Paging staff happens outside Night Ledger.</p>
        </Shell>
      );
    }

    case "staffing_doctors":
      return (
        <Shell kicker="Decision 3 · rough signal only" title={`Consider calling in ${s.recommendation.count ?? ""} ER doctors`} actions={standard("Record decision")}>
          <p>
            {plural(s.evidence.red_calls, "red-flag call")} in {s.evidence.window_min} min. Phone calls can&apos;t measure how full the ER is.
          </p>
        </Shell>
      );
  }
}

function RedAlert({ s, action }: { s: Extract<Suggestion, { type: "red_not_connected" }>; action: Act }) {
  const { open } = useSelectedCall();
  const e = s.evidence;
  const flags = e.red_flags.map((f) => label(FLAG, f)).join(", ") || "Red flag";
  return (
    <div role="alert" className="flex flex-wrap items-center gap-x-5 gap-y-3.5 rounded-[20px] border border-red-line bg-red-tint px-5 py-[18px]">
      <svg width="22" height="20" viewBox="0 0 18 16" aria-hidden className="shrink-0">
        <path d="M9 0l9 16H0z" fill="#D42A2A" />
        <path d="M9 6v4M9 12.5v.5" stroke="#fff" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
      <div className="flex min-w-0 flex-[1_1_380px] flex-col gap-1.5">
        <h2 className="text-[19px] font-extrabold">Red caller not connected</h2>
        <div>
          {flags} · {e.caller_name || "Unknown caller"} · call back <b className="tabular-nums">{phone(e.callback_number)}</b> ·{" "}
          {TRANSFER[e.transfer_status]?.label ?? e.transfer_status}
        </div>
        <div className="text-[13px] text-muted">This alert can&apos;t be snoozed or dismissed. Close it with what happened.</div>
      </div>
      <div className="flex flex-wrap gap-2">
        {(Object.keys(RESOLVE_OUTCOME) as (keyof typeof RESOLVE_OUTCOME)[]).map((o, i) => (
          <Button key={o} variant={i === 0 ? "red" : "default"} disabled={action.pending === `${s.id}:resolve`} onClick={() => decide(action, s, "resolve", { outcome: o })}>
            {RESOLVE_OUTCOME[o]}
          </Button>
        ))}
        {s.call_id && (
          <Button size="sm" onClick={() => open(s.call_id!)}>
            Handoff Card
          </Button>
        )}
      </div>
    </div>
  );
}

function StatusMessageDecision({ s, action, busy }: { s: Extract<Suggestion, { type: "status_message" }>; action: Act; busy: (v: string) => boolean }) {
  // Local draft: the poll refreshes the suggestion every 2 s without touching what the supervisor typed.
  const [text, setText] = useState(s.recommendation.message);
  const e = s.evidence;
  return (
    <Shell
      kicker="Decision 2 · pre-approved wording"
      title="Play this message to every caller?"
      actions={
        <>
          <Button variant="dark" busy={busy("accept")} disabled={!text.trim()} onClick={() => decide(action, s, "accept", { message: text.trim() })}>
            Activate message
          </Button>
          <Button busy={busy("snooze")} onClick={() => decide(action, s, "snooze")}>
            Not yet
          </Button>
          <Button size="sm" busy={busy("dismiss")} onClick={() => decide(action, s, "dismiss")}>
            Dismiss
          </Button>
        </>
      }
    >
      <div>
        <b>{e.calls}</b> calls in the last 10 min are about <b>{label(CLUSTER, e.cluster)}</b> ({pct(e.share)}).
      </div>
      <label className="sr-only" htmlFor={`msg-${s.id}`}>
        Status message
      </label>
      <textarea
        id={`msg-${s.id}`}
        value={text}
        onChange={(ev) => setText(ev.target.value)}
        rows={2}
        className="w-full resize-y rounded-[14px] border border-line bg-soft px-3 py-2.5 text-sm leading-normal outline-none focus:ring-2 focus:ring-blue"
      />
      {text !== s.recommendation.message && <span className="text-[13px] text-muted">Edited. Your wording is logged alongside the template.</span>}
    </Shell>
  );
}

// ------------------------------------------------------------------ pieces

function Shell({ tone, kicker, title, actions, children }: { tone?: "navy"; kicker: string; title: string; actions: ReactNode; children: ReactNode }) {
  return (
    <div
      className={cx(
        "flex flex-wrap items-center gap-x-5 gap-y-3.5 rounded-[20px] border px-5 py-[18px]",
        tone === "navy" ? "border-navy bg-navy text-white" : "border-line bg-white",
      )}
    >
      <div className="flex min-w-0 flex-[1_1_420px] flex-col gap-2">
        <span className={cx("text-[13px] font-bold", tone === "navy" ? "text-[#AEB6C6]" : "text-muted")}>{kicker}</span>
        <h2 className="text-[19px] font-extrabold">{title}</h2>
        {children}
      </div>
      <div className="flex flex-wrap gap-2">{actions}</div>
    </div>
  );
}

const Evidence = ({ children, dark }: { children: ReactNode; dark?: boolean }) => (
  <div className={cx("flex flex-wrap gap-2", dark && "[&>div]:bg-white/10")}>{children}</div>
);

const Ev = ({ v, l }: { v: ReactNode; l: string }) => (
  <div className="flex min-w-[90px] flex-col rounded-xl bg-soft px-3 py-2">
    <b className="text-xl font-extrabold tabular-nums">{v}</b>
    <span className="text-xs opacity-80">{l}</span>
  </div>
);
