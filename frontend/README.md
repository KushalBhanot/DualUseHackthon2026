# Night Ledger frontend

The supervisor board: Next.js 16 (App Router), React 19, Tailwind CSS 4, TypeScript, SWR.
It talks only to the FastAPI backend in [../backend](../backend). `/api/*` is proxied by Next.js, so there's no CORS setup.

## Run it

Start the backend first (see [../backend/README.md](../backend/README.md)), then:

```bash
cd frontend
npm install
npm run dev            # http://localhost:3000
```

Open **Demo controls** (the ▷ icon) and start **Serious earthquake** to fill the board.

Production: `npm run build && npm start`. The backend address defaults to `http://localhost:8000`. Rewrites are resolved at build time, so set it when you build: `BACKEND_URL=https://api.example.org npm run build`.

`npm run typecheck` checks the types without building.

## Pages

| Route | What it does |
|---|---|
| `/` | Board: decisions waiting for the supervisor, KPIs, the three lanes, what callers keep asking, calls per minute, surge toggle |
| `/calls` | Every call, filterable by lane, source and text |
| `/analytics` | Lane mix, red-flag handoff timing, classifier agreement, detail confirmation, safety-net events |
| `/setup` | Nurse lines for red transfers, pre-approved status messages, surge mode and callback windows |
| `/demo` | Start, pause and reset simulated scenarios |

Clicking any call opens its **Handoff Card**: red flags, why it's in its lane (rules vs model), warm-transfer timing, captured details with read-back, recording, live transcript, event log. It's also where a supervisor changes a lane, with a reason that's logged.

## How it stays fast

- Pages are prerendered static shells; data loads client-side with SWR. Only the visible page polls (hidden routes stay mounted but their effects stop), and polling pauses when the tab is hidden.
- The fetcher shares structure with the previous response (`lib/api.ts`), so a new call re-renders one memoised row, not the whole lane.
- The board endpoint returns slim rows and is gzipped. Transcripts and details load only for the open Handoff Card.
- Elapsed-time labels share one 1 s ticker and re-render only their own text.
- Actions update the cache optimistically (a decided suggestion disappears at once), then refresh every `/api` read.
- Charts are plain SVG/HTML, with no chart library. Manrope is self-hosted through `next/font`.

## Layout

```
app/                  routes (layout.tsx holds the sidebar, providers and the Handoff Card)
components/board/     board: decisions, KPIs, lanes, call rows, charts, response bar
components/views/     calls, analytics, setup, demo
components/           handoff-drawer, sidebar, toast, ui primitives
lib/                  api.ts (fetching, actions, ticker), types.ts, labels.ts, format.ts
```
