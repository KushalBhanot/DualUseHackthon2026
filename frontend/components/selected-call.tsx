"use client";

import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

// Which call's Handoff Card is open. Lives in the root layout so the drawer works from any page.
type Selected = { id: string | null; open: (id: string) => void; close: () => void };

const SelectedCall = createContext<Selected>({ id: null, open: () => {}, close: () => {} });

export const useSelectedCall = () => useContext(SelectedCall);

export function SelectedCallProvider({ children }: { children: ReactNode }) {
  const [id, setId] = useState<string | null>(null);
  const value = useMemo(() => ({ id, open: setId, close: () => setId(null) }), [id]);
  return <SelectedCall.Provider value={value}>{children}</SelectedCall.Provider>;
}
