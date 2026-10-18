"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api, useAction, useSim } from "@/lib/api";
import type { SimState } from "@/lib/types";
import { Button, Card, Chip, PageHeader, cx } from "../ui";

const NOTES: Record<string, string> = {
  serious_earthquake:
    "Collapsed buildings, regional outage. Volume ramps fast, so the surge prompt, the outage message and staffing suggestions fire on their own. Includes the chest-pain caller who first asks if you're open.",
  big_fire: "Wildfire, evacuations, smoke. Breathing complaints are red flags even when they sound routine.",
  small_fire: "Apartment fire, a few patients. The system should not escalate: no surge prompt.",
  small_earthquake: 'Short spike, few red flags. Where "Not yet, ask in 2 min" earns its place.',
  tuesday: "An ordinary night on the after-hours line: refills, rescheduling, one post-op bleed.",
};

export function DemoView() {
  const { data: sim } = useSim();
  const { run, pending } = useAction();
  const router = useRouter();
  const [confirmReset, setConfirmReset] = useState(false);

  const start = async (scenario: string, mode: "drip" | "instant") => {
    const ok = await run(`${scenario}:${mode}`, () => api.post<SimState>("/api/sim/start", { scenario, mode }), {
      success: mode === "drip" ? "Scenario started. Calls are arriving." : "Scenario loaded.",
    });
    if (ok) router.push("/");
  };

  return (
    <>
      <PageHeader
        title="Demo controls"
        sub="Team only. Simulated calls go straight into the database and through the real rules and supervisor engine, so the board fills like a real night."
        right={
          <>
            {sim?.running && (
              <Button busy={pending === "stop"} onClick={() => run("stop", () => api.post("/api/sim/stop"), { success: "Drip paused." })}>
                Pause drip
              </Button>
            )}
            {confirmReset ? (
              <>
                <span className="text-sm font-semibold">Remove every simulated call?</span>
                <Button
                  variant="red"
                  busy={pending === "reset"}
                  onClick={async () => {
                    await run("reset", () => api.post("/api/sim/reset"), { success: "Board reset." });
                    setConfirmReset(false);
                  }}
                >
                  Reset board
                </Button>
                <Button onClick={() => setConfirmReset(false)}>Cancel</Button>
              </>
            ) : (
              <Button onClick={() => setConfirmReset(true)}>Reset board…</Button>
            )}
          </>
        }
      />

      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        {(sim?.scenarios ?? []).map((s) => {
          const current = sim?.scenario === s.id;
          const running = current && sim?.running;
          return (
            <Card key={s.id} className={cx("flex flex-col gap-2.5 p-5", current && "border-blue bg-[#F5FAFE]")}>
              <div className="flex items-center gap-2">
                <h2 className="font-bold">{s.label}</h2>
                {current && <Chip tone="blue">{running ? `Running · ${sim!.inserted}/${sim!.total}` : "Last run"}</Chip>}
              </div>
              {running && (
                <div className="h-1.5 rounded-full bg-blue-tint" role="progressbar" aria-valuemin={0} aria-valuemax={sim!.total} aria-valuenow={sim!.inserted} aria-label="Calls inserted">
                  <div className="h-1.5 rounded-full bg-blue transition-[width] duration-500" style={{ width: `${(sim!.inserted / Math.max(1, sim!.total)) * 100}%` }} />
                </div>
              )}
              <p className="flex-1 text-sm leading-relaxed text-muted">{NOTES[s.id]}</p>
              <span className="text-xs text-muted">{s.default_count} calls</span>
              <div className="flex flex-wrap gap-2">
                <Button variant={running ? "default" : "dark"} busy={pending === `${s.id}:drip`} onClick={() => start(s.id, "drip")}>
                  {running ? "Restart" : "Start"} live
                </Button>
                <Button busy={pending === `${s.id}:instant`} onClick={() => start(s.id, "instant")}>
                  Load instantly
                </Button>
              </div>
            </Card>
          );
        })}
      </div>

      <Card className="p-5 text-sm leading-relaxed">
        <h2 className="mb-1.5 font-bold">Live phone calls</h2>
        Run <code className="rounded bg-soft px-1.5 py-0.5">retell/connect.sh</code> with the backend up. It opens a tunnel to port 8000, points the agent&apos;s webhook
        and tools at it, and sets the phone number&apos;s inbound webhook to <code className="rounded bg-soft px-1.5 py-0.5">/retell/inbound</code>. Real calls appear
        on the board as they happen, with a purple <Chip tone="purple">Live call</Chip> chip and a live transcript in the Handoff Card.
      </Card>
    </>
  );
}
