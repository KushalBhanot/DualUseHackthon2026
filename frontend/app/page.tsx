import type { Metadata } from "next";
import { BoardView } from "@/components/board/board-view";

export const metadata: Metadata = { title: "Supervisor board" };

export default function Page() {
  return <BoardView />;
}
