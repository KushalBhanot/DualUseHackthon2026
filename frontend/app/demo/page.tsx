import type { Metadata } from "next";
import { DemoView } from "@/components/views/demo-view";

export const metadata: Metadata = { title: "Demo controls" };

export default function Page() {
  return <DemoView />;
}
