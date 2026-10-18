import type { Metadata } from "next";
import { CallsView } from "@/components/views/calls-view";

export const metadata: Metadata = { title: "All calls" };

export default function Page() {
  return <CallsView />;
}
