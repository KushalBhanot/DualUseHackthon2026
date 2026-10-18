import type { Metadata } from "next";
import { SetupView } from "@/components/views/setup-view";

export const metadata: Metadata = { title: "Setup" };

export default function Page() {
  return <SetupView />;
}
