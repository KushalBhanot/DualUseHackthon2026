"use client";

/** Shown when the backend can't be reached. With data already on screen, it says it's stale. */
export function ConnectionBanner({ error, hasData }: { error: unknown; hasData: boolean }) {
  if (!error) return null;
  return (
    <div role="alert" className="flex flex-wrap items-center gap-2 rounded-[20px] border border-amber-line bg-amber-tint px-5 py-3 text-sm text-amber-ink">
      <b>Can&apos;t reach the Night Ledger backend.</b>
      <span>
        {hasData ? "Showing the last data received; retrying every few seconds." : "Retrying every few seconds."} Is it running on port 8000?
      </span>
    </div>
  );
}
