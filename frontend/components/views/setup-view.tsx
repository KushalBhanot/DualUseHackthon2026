"use client";

import { useState } from "react";
import { api, useAction, useBoard, useNurseLines, useStatusMessages } from "@/lib/api";
import { phone } from "@/lib/format";
import { humanize } from "@/lib/labels";
import type { NurseLine } from "@/lib/types";
import { Button, Card, CardHeader, Chip, Empty, Field, PageHeader, Toggle, cx, inputClass } from "../ui";

const TEMPLATE_TITLE: Record<string, string> = {
  power_outage: "Power outage",
  it_outage: "IT outage",
  earthquake: "Earthquake",
  family_info: "Family asking about patients",
  offers_of_help: "Offers of help",
  fire: "Fire nearby",
};

export function SetupView() {
  return (
    <>
      <PageHeader title="Setup" sub="Agreed on a calm day, so at 2 AM you approve instead of write." />
      <div className="flex flex-wrap gap-5">
        <NurseLines />
        <Messages />
      </div>
      <Surge />
    </>
  );
}

function NurseLines() {
  const { data: lines } = useNurseLines();
  const { run, pending, mutate } = useAction();
  const [form, setForm] = useState({ label: "", number: "", priority: "3" });
  const validNumber = /^\+\d{7,15}$/.test(form.number);

  const setDuty = (n: NurseLine, on: boolean) =>
    run(`duty-${n.id}`, () => api.patch(`/api/nurse-lines/${n.id}`, { on_duty: on }), {
      success: `${n.label} ${on ? "on" : "off"} duty.`,
      optimistic: () => mutate("/api/nurse-lines", (ls?: NurseLine[]) => ls?.map((l) => (l.id === n.id ? { ...l, on_duty: on } : l)), { revalidate: false }),
    });

  const top = lines?.find((l) => l.on_duty);

  return (
    <Card className="min-w-0 flex-[1.2_1_460px] overflow-hidden">
      <CardHeader title="Nurse lines for red transfers" />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="whitespace-nowrap bg-band text-left text-[13px] text-muted">
              <th className="px-5 py-2.5 font-semibold">Line</th>
              <th className="px-3 py-2.5 font-semibold">Number</th>
              <th className="px-3 py-2.5 font-semibold">Role</th>
              <th className="px-3 py-2.5 font-semibold">Priority</th>
              <th className="px-3 py-2.5 font-semibold">On duty</th>
            </tr>
          </thead>
          <tbody>
            {lines?.map((n) => (
              <tr key={n.id} className="border-t border-hair">
                <td className="px-5 py-3 font-bold">
                  {n.label}
                  {n.id === top?.id && (
                    <Chip tone="green" className="ml-2">
                      Gets red transfers
                    </Chip>
                  )}
                </td>
                <td className="whitespace-nowrap px-3 py-3 tabular-nums">{phone(n.number)}</td>
                <td className="px-3 py-3">{humanize(n.role)}</td>
                <td className="px-3 py-3 tabular-nums">{n.priority}</td>
                <td className="px-3 py-3">
                  <Toggle on={n.on_duty} label={`On duty: ${n.label}`} disabled={pending === `duty-${n.id}`} onChange={(on) => setDuty(n, on)} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
        {lines && !lines.length && <Empty>No nurse lines yet. Red transfers go to the fallback NURSE_LINE from the backend&apos;s .env.</Empty>}
      </div>
      <p className="px-5 py-3.5 text-[13px] text-muted">
        The top on-duty line goes to Retell before each call through the inbound webhook. Changes apply from the next call.
      </p>
      <form
        className="flex flex-wrap items-end gap-2.5 px-5 pb-5"
        onSubmit={async (e) => {
          e.preventDefault();
          const ok = await run("addline", () => api.post("/api/nurse-lines", { label: form.label.trim(), number: form.number.trim(), priority: Number(form.priority) || 1 }), {
            success: "Nurse line added.",
          });
          if (ok) setForm({ label: "", number: "", priority: "3" });
        }}
      >
        <Field label="Label" className="flex-[1_1_180px]">
          <input required value={form.label} onChange={(e) => setForm({ ...form, label: e.target.value })} placeholder="Night nurse · J. Park" className={inputClass} />
        </Field>
        <Field label="Number (E.164)" className="flex-[1_1_160px]">
          <input
            required
            value={form.number}
            onChange={(e) => setForm({ ...form, number: e.target.value.replace(/[^\d+]/g, "") })}
            placeholder="+12135550100"
            inputMode="tel"
            aria-invalid={form.number !== "" && !validNumber}
            className={cx(inputClass, form.number && !validNumber && "ring-2 ring-lane-amber")}
          />
        </Field>
        <Field label="Priority" className="w-[90px]">
          <input type="number" min={1} value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} className={inputClass} />
        </Field>
        <Button type="submit" variant="dark" busy={pending === "addline"} disabled={!form.label.trim() || !validNumber}>
          Add line
        </Button>
      </form>
    </Card>
  );
}

function Messages() {
  const { data } = useStatusMessages();
  const { run, pending } = useAction();
  const active = data?.active;
  return (
    <Card className="min-w-0 flex-[1_1_420px] overflow-hidden">
      <CardHeader
        title="Status messages"
        hint="Approved ahead of time. The AI suggests one; it never writes new wording."
        right={
          active && (
            <Button size="sm" busy={pending === "stop"} onClick={() => run("stop", () => api.post("/api/status-message", { text: null }), { success: "Status message stopped." })}>
              Stop current
            </Button>
          )
        }
      />
      {data?.templates.map((t) => (
        <div key={t.id} className="flex flex-wrap items-center gap-3 border-t border-hair px-5 py-3">
          <div className="min-w-0 flex-[1_1_240px]">
            <div className="font-bold">{TEMPLATE_TITLE[t.id] ?? humanize(t.id)}</div>
            <div className="text-[13px] text-muted">{t.text}</div>
          </div>
          {active === t.text ? (
            <Chip tone="blue">Playing</Chip>
          ) : (
            <Button
              size="sm"
              busy={pending === t.id}
              onClick={() => run(t.id, () => api.post("/api/status-message", { text: t.text, template_id: t.id }), { success: "Status message now plays to every caller." })}
            >
              Activate
            </Button>
          )}
        </div>
      ))}
      {active && !data?.templates.some((t) => t.text === active) && (
        <div className="flex flex-wrap items-center gap-3 border-t border-hair bg-[#F5FAFE] px-5 py-3">
          <span className="min-w-0 flex-[1_1_240px] text-[13px]">
            <b>Edited wording playing:</b> {active}
          </span>
          <Chip tone="blue">Playing</Chip>
        </div>
      )}
    </Card>
  );
}

function Surge() {
  const { data: board } = useBoard();
  const { run, pending } = useAction();
  const s = board?.surge;
  if (!s) return null;
  return (
    <Card className="flex flex-wrap items-center gap-6 px-5 py-[18px]">
      <div>
        <div className="font-bold">Surge mode</div>
        <div className="text-[13px] text-muted">Only a person can switch it on or off.</div>
      </div>
      <Toggle
        on={s.surge_on}
        label="Surge mode"
        disabled={pending === "surge"}
        onChange={(on) => run("surge", () => api.post("/api/surge", { on }), { success: on ? "Surge mode on." : "Surge mode off." })}
      />
      <Window label="Routine callback" now={s.surge_on ? s.surge_routine_window : s.routine_callback_window} other={s.surge_on ? s.routine_callback_window : s.surge_routine_window} surge={s.surge_on} />
      <Window label="Priority callback" now={s.surge_on ? s.surge_priority_window : s.priority_callback_window} other={s.surge_on ? s.priority_callback_window : s.surge_priority_window} surge={s.surge_on} />
    </Card>
  );
}

function Window({ label, now, other, surge }: { label: string; now: string; other: string; surge: boolean }) {
  return (
    <div className="min-w-0">
      <div className="text-[13px] text-muted">{label} window, promised now</div>
      <b>{now}</b>
      <div className="text-xs text-muted">
        {surge ? "Normal" : "In surge"}: {other}
      </div>
    </div>
  );
}
