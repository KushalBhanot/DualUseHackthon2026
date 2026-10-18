"use client";

import { useCallback, useState, useSyncExternalStore } from "react";
import useSWR, { useSWRConfig, type SWRConfiguration } from "swr";
import { useToast } from "@/components/toast";
import type { Analytics, Board, CallDetail, CallRow, Lane, NurseLine, SimState, StatusMessages, Suggestion } from "./types";

export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(path, { ...init, headers: { "content-type": "application/json", ...init?.headers } });
  if (!r.ok) {
    const body = await r.json().catch(() => null);
    const detail = body?.detail;
    const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((d) => d.msg).join("; ") : r.statusText;
    throw new ApiError(msg || `Request failed (${r.status})`, r.status);
  }
  return r.status === 204 ? (undefined as T) : r.json();
}

// ------------------------------------------------------------------ structural sharing

// Each poll parses fresh JSON, so every object is new even when nothing changed. `share` keeps the
// previous object wherever the new one is deep-equal, matching list items by their id, so a new
// call at the top of a lane re-renders one row instead of the whole lane.
type Json = unknown;
const isObj = (v: Json): v is Record<string, Json> => typeof v === "object" && v !== null && !Array.isArray(v);
const idOf = (v: Json) => (isObj(v) ? (v.call_id ?? v.id ?? v.item_id ?? v.bucket ?? v.cluster) : undefined) as string | number | undefined;

function share(prev: Json, next: Json): Json {
  if (prev === next) return prev;
  if (Array.isArray(prev) && Array.isArray(next)) {
    const byId = new Map<unknown, Json>();
    for (const p of prev) {
      const id = idOf(p);
      if (id !== undefined) byId.set(id, p);
    }
    let same = prev.length === next.length;
    const out = next.map((n, i) => {
      const id = idOf(n);
      const s = share(id !== undefined && byId.has(id) ? byId.get(id) : prev[i], n);
      if (s !== prev[i]) same = false;
      return s;
    });
    return same ? prev : out;
  }
  if (isObj(prev) && isObj(next)) {
    const keys = Object.keys(next);
    let same = keys.length === Object.keys(prev).length;
    const out: Record<string, Json> = {};
    for (const k of keys) {
      out[k] = share(prev[k], next[k]);
      if (out[k] !== prev[k]) same = false;
    }
    return same ? prev : out;
  }
  return next;
}

const last = new Map<string, Json>();

export async function fetcher<T>(path: string): Promise<T> {
  const data = share(last.get(path), await request<T>(path));
  last.set(path, data);
  return data as T;
}

export const api = {
  post: <T = unknown>(path: string, body?: unknown) => request<T>(path, { method: "POST", body: body === undefined ? undefined : JSON.stringify(body) }),
  patch: <T = unknown>(path: string, body: unknown) => request<T>(path, { method: "PATCH", body: JSON.stringify(body) }),
};

// ------------------------------------------------------------------ reads

// The board is the hot path: poll it often. SWR deduplicates identical keys across components,
// pauses while the tab is hidden, and keeps the previous object when nothing changed, so
// memoised rows don't re-render on an idle poll.
const LIVE: SWRConfiguration = { refreshInterval: 2000 };

export const useBoard = () => useSWR<Board>("/api/board", LIVE);
export const useSuggestions = () => useSWR<Suggestion[]>("/api/suggestions", LIVE);
export const useCall = (id: string | null) =>
  useSWR<CallDetail>(id ? `/api/calls/${encodeURIComponent(id)}` : null, {
    refreshInterval: (c) => (c?.status === "ongoing" ? 1500 : 6000),
  });
export const useCalls = (lane: Lane | "", source: string) =>
  useSWR<CallRow[]>(`/api/calls?limit=300${lane ? `&lane=${lane}` : ""}${source ? `&source=${source}` : ""}`, { refreshInterval: 4000 });
export const useAnalytics = (minutes: number) => useSWR<Analytics>(`/api/analytics?minutes=${minutes}`, { refreshInterval: 10000 });
export const useNurseLines = () => useSWR<NurseLine[]>("/api/nurse-lines", { refreshInterval: 15000 });
export const useStatusMessages = () => useSWR<StatusMessages>("/api/status-messages", { refreshInterval: 15000 });
export const useSim = () => useSWR<SimState>("/api/sim", { refreshInterval: (s) => (s?.running ? 1000 : 5000) });

// ------------------------------------------------------------------ writes

/**
 * Run a write, toast the outcome, then refresh every /api read so the whole UI agrees.
 * `optimistic` updates the cache first, so the click feels instant; on failure the refresh
 * puts the server's truth back.
 */
export function useAction() {
  const { mutate } = useSWRConfig();
  const toast = useToast();
  const [pending, setPending] = useState<string | null>(null);

  const refresh = useCallback(() => mutate((key) => typeof key === "string" && key.startsWith("/api/")), [mutate]);

  const run = useCallback(
    async (id: string, fn: () => Promise<unknown>, opts: { success?: string; optimistic?: () => void } = {}) => {
      setPending(id);
      try {
        opts.optimistic?.();
        await fn();
        if (opts.success) toast(opts.success);
        return true;
      } catch (e) {
        toast(e instanceof Error ? e.message : "Something went wrong", "error");
        return false;
      } finally {
        setPending(null);
        refresh();
      }
    },
    [refresh, toast],
  );

  return { run, pending, mutate };
}

// ------------------------------------------------------------------ time

// One shared ticker for every "waiting 4:05" label, instead of a timer per row.
const listeners = new Set<() => void>();
let nowValue = Date.now();
let timer: ReturnType<typeof setInterval> | null = null;

function subscribe(cb: () => void) {
  listeners.add(cb);
  if (!timer) {
    nowValue = Date.now();
    timer = setInterval(() => {
      nowValue = Date.now();
      listeners.forEach((l) => l());
    }, 1000);
  }
  return () => {
    listeners.delete(cb);
    if (!listeners.size && timer) {
      clearInterval(timer);
      timer = null;
    }
  };
}

/** Current time, updated every second; 0 during prerender so nothing time-based is baked into HTML. */
export const useNow = () =>
  useSyncExternalStore(
    subscribe,
    () => nowValue,
    () => 0,
  );
