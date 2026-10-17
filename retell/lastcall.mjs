// Print a readable timeline of a call: transcript, ladder transitions, tool calls, and the Watch-feed analysis.
//   node lastcall.mjs            most recent call
//   node lastcall.mjs call_xxx   a specific call
import { execFileSync } from "node:child_process";

const cli = (...args) => {
  const out = execFileSync("npx", ["--yes", "@retell-ai/retell-cli", ...args], { encoding: "utf8" });
  return JSON.parse(out);
};

let id = process.argv[2];
if (!id) {
  const list = cli("list-calls", "--limit", "1");
  id = (list.items || list)[0]?.call_id;
  if (!id) throw new Error("no calls yet");
}
const c = cli("get-call", id);

console.log(`${c.call_id}  ${c.call_type}  ${c.call_status}  from=${c.from_number ?? "-"}  ${Math.round((c.duration_ms ?? 0) / 1000)}s  ended=${c.disconnection_reason ?? "-"}\n`);

for (const t of c.transcript_with_tool_calls || []) {
  if (t.role === "tool_call_invocation") {
    const step = t.name.startsWith("transition_to_") ? `>> MOVE UP to ${t.name.slice(14)}` : `>> tool ${t.name}`;
    console.log(`${step}  ${t.arguments && t.arguments !== "{}" ? t.arguments : ""}`);
  } else if (t.role === "tool_call_result") {
    console.log(`   result: ${String(t.content).slice(0, 140)}`);
  } else {
    console.log(`${t.role.padEnd(5)}  ${t.content}`);
  }
}

const a = c.call_analysis;
if (a) {
  console.log(`\nsummary: ${a.call_summary}`);
  console.log(a.custom_analysis_data);
} else {
  console.log("\n(analysis not ready yet; rerun in ~30s after the call ends)");
}
