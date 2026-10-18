"use client";

import type { ReactNode } from "react";
import { SWRConfig } from "swr";
import { fetcher } from "@/lib/api";
import { HandoffDrawer } from "./handoff-drawer";
import { SelectedCallProvider } from "./selected-call";
import { ToastProvider } from "./toast";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <SWRConfig
      value={{
        fetcher,
        keepPreviousData: true,
        dedupingInterval: 1000,
        focusThrottleInterval: 2000,
        errorRetryInterval: 3000,
      }}
    >
      <ToastProvider>
        <SelectedCallProvider>
          {children}
          <HandoffDrawer />
        </SelectedCallProvider>
      </ToastProvider>
    </SWRConfig>
  );
}
