# SmartCCTV / Meridian — AI Agent Build Spec v2

Read `SmartCCTV_Updated_Plan_v2.md` first — it explains *why*. Read `SmartCCTV_Software_Design_Document.md` (v1) for backend/model detail this file doesn't repeat. Read `AGENT_BUILD_SPEC.md` (v1) §0–§1 ground rules — they still apply (test before proceeding, log deviations to `BUILD_LOG.md`, no unfounded claims, strict config validation, never silently drop scope).

**This file's job:** turn `Meridian___Surveillance_Operations_Platform.html` (one static file, all-mock data, confirmed zero `fetch()` calls) into the real frontend of the system already specified in v1, wired to a real backend, with the Video Analysis bug fixed. **Do not rewrite the visual design.** Every color, layout, and component in the source file is approved — the job is plumbing, not redesign.

---

## 0. Before touching anything

1. Open `Meridian___Surveillance_Operations_Platform.html` and locate these exact anchors (search for them, they exist verbatim):
   - `// ===================== CORE BINDINGS =====================`
   - `const html = htm.bind(React.createElement);`
   - Every `function XPage(...)` — these are your 11 page components.
   - Every `const X_SEED`, `const X_DEFAULTS`, or bare `const X = [...]`/`const X = {...}` above the components — these are the mock data sources to delete, one by one, as each page is wired.
2. Confirm the CDN script list at the top (React, ReactDOM, htm, Chart.js from cdnjs/jsdelivr) — these become real npm packages, not CDN tags, in the new project.
3. Run a plain-text diff check after each page migration: extract that page's JSX-equivalent output and confirm the rendered DOM structure (element types, class names, test-ids you add) is unchanged from the original, only the data source changed. If you don't have a visual diff tool, take a manual screenshot before and after each page migration and eyeball it — do not skip this, it's the only guard against silent redesign creep.

---

## 1. Milestone order

Follow `SmartCCTV_Updated_Plan_v2.md` §8 (U1–U6) exactly, in order. Do not start U3 (Video Analysis rebuild) before U2's API client exists — Video Analysis needs the same typed client every other page uses. **U3 is the highest-priority milestone** — it's the specific bug the user reported. If time is constrained, U1+U2+U3 alone is an acceptable partial delivery; say so explicitly in `BUILD_LOG.md` rather than half-finishing U4–U6.

---

## 2. U1: Scaffold and lossless port

### 2.1 New project
```
web/
  package.json          # React 18, TypeScript, Vite, @tanstack/react-query, chart.js + react-chartjs-2
  vite.config.ts
  tsconfig.json
  src/
    main.tsx
    App.tsx              # from function App() — router/nav shell, unchanged logic
    theme/tokens.css      # extract every CSS custom property / hex value from ref.html's <style> block verbatim
    icons/Icon.tsx         # from function Icon() + ICN constant — keep every icon path exactly
    components/
      RiskBadge.tsx StatusDot.tsx SignalChips.tsx Gauge.tsx Sparkline.tsx
      ConfidenceBar.tsx EvidenceCanvas.tsx NetworkGraph.tsx TopologyGraph.tsx
      LiveFeedCanvas.tsx CameraGridTile.tsx AlertRow.tsx IncidentCard.tsx
      ChartCanvas.tsx ToastStack.tsx NotificationDrawer.tsx CommandPalette.tsx
      SaveBar.tsx FieldRow.tsx NumberField.tsx TypeIcon.tsx
    pages/
      CommandCenterPage.tsx VideoAnalysisPage.tsx IncidentsPage.tsx AlertsPage.tsx
      CameraMapPage.tsx CameraGridPage.tsx IdentityTopologyPage.tsx
      HistoryPage.tsx AnalyticsPage.tsx IntegrityAuditPage.tsx SystemHealthPage.tsx
      SettingsPage.tsx  (+ its 6 tab subcomponents: DetectionSettingsTab, RiskSettingsTab,
                          NotificationsSettingsTab, PrivacySettingsTab, RetentionSettingsTab,
                          SystemSettingsTab, UsersSettingsTab)
    modals/
      IncidentInvestigationModal.tsx  ConfirmPanel.tsx  DismissPanel.tsx
    mock/                 # TEMPORARY — every seed const goes here first, deleted page-by-page in U2–U6
      seed.ts
```
One component per file, named exports matching the original function names exactly (grep-ability for future maintainers who know the original file).

### 2.2 Translation pattern (`htm` → JSX)
The original uses `html\`<div className=${x}>...\`` tagged templates. Mechanical translation:
```js
// BEFORE (htm)
return html`<div className="card"><${RiskBadge} level=${incident.risk} /></div>`;
// AFTER (JSX)
return <div className="card"><RiskBadge level={incident.risk} /></div>;
```
Rules: `${expr}` → `{expr}`. `<${Component} .../>` → `<Component .../>`. `class Name` stays `className`. Self-closing tags stay self-closing. Do this for every component — it is mechanical, not creative; if a translation seems to require changing behavior, it's a translation mistake, fix it, don't "improve" it.

### 2.3 U1 done-when
- [ ] `npm run dev` renders all 11 pages, navigable via the sidebar, **still using `mock/seed.ts`** (copied verbatim from the original's constants) — zero visual difference from the original file.
- [ ] `grep -r "htm\." web/src` returns nothing (fully translated).
- [ ] Screenshot comparison for all 11 pages: original vs. ported, side by side, confirmed matching.

---

## 3. U2: Real API client + wire 3 pages

### 3.1 `api/client.ts`
One typed function per endpoint in SDD v1 §8. Pattern:
```ts
export async function listAlerts(params: AlertFilters): Promise<Alert[]> { ... }
export async function getAlert(id: string): Promise<AlertDetail> { ... }
export async function decideAlert(id: string, body: DecisionRequest): Promise<DecisionResult> { ... }
// ... one per SDD v1 §8 row
```
Types (`Alert`, `AlertDetail`, `DecisionRequest`, `Camera`, `Zone`, etc.) come from SDD v1 §7.2 JSON schemas — **do not invent field names**, match the schema exactly, including `entity`, `global_id`, `reasons`, `types`, `clip_sha256`, etc. Base URL from `import.meta.env.VITE_API_BASE`.

### 3.2 `ws/client.ts`
Single WebSocket connection to `/ws`, reconnect with backoff, typed message union matching SDD v1 §8 (`alert.created`, `alert.updated`, `camera.status`, `tamper.raised`, `tamper.cleared`, `health.tick`). Expose a small pub-sub hook (`useWsEvent('alert.created', handler)`) that pages subscribe to.

### 3.3 Wire these 3 pages first (they share the most data shape with §5's priority fix, and validate the client end to end before Video Analysis depends on it)
- `CommandCenterPage`: replace `ALERTS`/`CAMERAS`/`HOST_STATS`/`ACTIVITY_FEED_SEED` reads with `useQuery` calls to `listAlerts`, `listCameras`, `getHealth`; subscribe to `alert.created` for the live activity feed instead of reading `ACTIVITY_FEED_SEED`.
- `AlertsPage` / `IncidentsPage`: same pattern; `IncidentInvestigationModal`'s Confirm/Dismiss buttons call `decideAlert` for real — **this makes the review workflow real for the first time**.
- `HistoryPage`: `listAlerts` with `status=confirmed,dismissed` and real pagination (the original likely paginates a static array client-side — replace with server-side pagination params).

### 3.4 U2 done-when
- [ ] Backend running locally (from v1 `AGENT_BUILD_SPEC.md` M1–M2) with at least a few seeded alerts in the DB.
- [ ] Command Center, Alerts, Incidents, History show real DB content, update live via WS when a new alert is inserted directly in the DB (manual test).
- [ ] `Confirm`/`Dismiss` in the modal actually changes `alerts.status` in the database and appends to the hash chain (verify via `/integrity/verify`).
- [ ] `mock/seed.ts` entries for these 4 pages deleted.

---

## 4. U3: Video Analysis rebuild — the priority fix

This is the specific bug reported: *"after video upload, it analyses frame by frame, but it doesn't give any alerts."* Root cause confirmed in `SmartCCTV_Updated_Plan_v2.md` §5.1: the original `spawnDetection()` is a random-number generator with **no connection to the uploaded video's actual content**. Fixing this is not a tuning task, it's a wiring task.

### 4.1 Backend work (new, not in v1 — do this first, UI depends on it)
1. Add `analysis_jobs` table (see plan v2 §6).
2. `POST /analysis/upload`: accept multipart file, save to a temp path, create a job row (`status=queued`), return `{job_id}`. Kick off an `analysis_worker` (subprocess or background task) that:
   - Extracts one frame (e.g. the 10th frame) and returns it for the zone-drawing step, OR runs immediately in no-zone mode if the user skipped drawing (per plan v2 §5.4 — this is a UX choice, implement the zone-draw path, it's the better experience and reuses `ZoneEditor`).
   - Runs the **exact same** `core/cascade.py` → `core/tracking.py` → `core/risk/engine.py` chain used by live workers (SDD v1 §6.1), with `ING-01`'s "local file" source — **do not write a second detection pipeline**, import the same `core/` modules.
   - Streams per-frame detections and the running risk score over `/analysis/{job_id}/stream` (WS) as it processes.
   - On completion, writes any real alerts to the `alerts` table (same schema, same hash chain, same evidence capture as a live camera would) and marks the job `done`.
3. `GET /analysis/{job_id}/status`, `GET /analysis/{job_id}/result` per plan v2 §5.3.

### 4.2 Frontend work
Rewrite `VideoAnalysisPage.tsx`:
1. **Delete** `spawnDetection`, `INCIDENT_TYPES` random pick, `liveConfidence`/`box` fake-state logic, `ANALYSIS_STAGES` if it was decorative-only (keep it if it's a real progress indicator, now driven by real `status`).
2. File drop → `POST /analysis/upload` → get `job_id`.
3. Show the extracted frame → reuse the existing `ZoneCanvas`/`ZoneEditor` component (from the Camera pages, **do not build a second polygon-drawing UI**) → let the user draw 0 or more zones → `PUT` them against this job (or pass inline in the analyze-start call, backend's choice, document it in `BUILD_LOG.md`).
4. "Analyze" button → starts the backend job (if not auto-started on upload) → open the `/analysis/{job_id}/stream` WebSocket.
5. Render real bounding boxes and a **live risk score per tracked person** (reuse `Gauge`/`Sparkline`) as WS messages arrive — this is the critical UX fix from plan v2 §5.4: the user must see risk climbing even when no alert fires, so "nothing crossed threshold" is visually distinct from "nothing was detected."
6. On `status=done`: show `GET /analysis/{job_id}/result` — real alerts (if any) rendered exactly like `IncidentCard`/`AlertRow` elsewhere in the app (reuse those components, don't build new ones).
7. **Required empty-state copy** (do not skip this, it's the fix for the exact confusion in this conversation):
   - No zone drawn + no alerts: *"No zone was drawn, so restricted-area signals were skipped. Detected people reached a maximum risk score of {X} out of {threshold} from movement signals alone."*
   - Zone drawn + no alerts: *"No alert threshold was reached. Highest risk score observed: {X} out of {threshold} at {timestamp}. See the risk timeline above."*
   - Never show a bare "No alerts" with no number attached — always show the actual peak score reached, so the user can see *how close* it got, not just yes/no.

### 4.3 U3 done-when
- [ ] Uploading a video of an empty room produces a near-zero risk timeline and the correct empty-state message with a real score shown.
- [ ] Uploading a staged clip (per v1 SDD §12.2 — a person loitering + running, or a bag left and walked away) produces a real alert with a real clip and real reasons, end to end, no randomness involved anywhere in the path.
- [ ] `grep -c "spawnDetection\|INCIDENT_TYPES\|seededRandom" web/src/pages/VideoAnalysisPage.tsx` returns 0.
- [ ] Manually verified: running the same clip twice gives the **same** result both times (deterministic pipeline, not random) — this is the core proof the bug is fixed.

---

## 5. U4: Camera Map/Grid + Identity & Topology

1. Add `map_x`, `map_y` columns to `cameras` (Alembic migration) and an admin UI affordance to set them (drag-on-map, or simple numeric fields in the camera edit drawer — reuse `CameraMapPage`'s existing map rendering, just feed it real coordinates instead of `LOCATIONS`).
2. `CameraGridPage`: replace `CAMERAS` seed with `listCameras()`; live thumbnails via `GET /cameras/{id}/snapshot` polled every few seconds (MJPEG live view is a stretch goal, snapshot polling is acceptable for V1 per SDD v1 §9.3 S5).
3. `IdentityTopologyPage`: wire `TopologyGraph` to `GET/PUT /topology`. Add the new `GET /identity/ghosts` endpoint (backend: expose `core/identity/linker.py`'s in-memory ghost list, read-only, from the `identity_service` process — see SDD v1 §5.2) and replace the static `GHOSTS` constant with it, polled or pushed via WS.

**U4 done-when:** Camera Map shows cameras at real configured positions; Identity & Topology shows live in-transit ghosts (or an empty state if none), not the static seed array.

---

## 6. U5: Settings, Users, Integrity & Audit, System Health

1. `SettingsPage`'s 6 tabs: each tab's form fields already match `SETTINGS_DEFAULTS`/`RISK_ENGINE_DEFAULTS` field names — wire `GET /settings` (load) and `PUT /settings` (the existing `SaveBar` component's save action) per tab. Preserve the original's diff-before-save UX if present; if not present, add it per SDD v1 §9.3 S10 ("every save shows a diff").
2. `UsersSettingsTab`: wire to `CRUD /users`.
3. `IntegrityAuditPage`: wire `CHAIN_HEAD`/`CHAIN_LENGTH`/`CHAIN_LAST_VERIFIED` to `GET /integrity/head` + `GET /integrity/verify`; `AUDIT_LOG` to `GET /audit` with real filters.
4. `SystemHealthPage`: wire `WORKER_STATS`/`HOST_STATS` to `GET /health/cameras` + `GET /health`.

**U5 done-when:** changing a risk threshold in Settings and saving it causes the next live worker cycle to actually use the new value (confirms the full loop: UI → API → DB → worker reload, per SDD v1 §6.7 "workers reload scales every 5 s" — same mechanism applies to all risk params, not just learned weights).

---

## 7. U6: Analytics + final cleanup

1. `AnalyticsPage`: wire `CATEGORY_TOTALS`/`CONFIDENCE_HISTOGRAM`/`ChartCanvas` calls to `GET /metrics/summary` and `GET /metrics/cameras`. Keep any "this is a proxy, not ground truth" caveat text from the original if present; add it per SDD v1 §12.2 if not.
2. Delete `mock/seed.ts` entirely.
3. Run the full acceptance check from `SmartCCTV_Updated_Plan_v2.md` §9:
   ```
   grep -r "seededRandom\|Math.random\|pick(" web/src   # must return nothing
   ```
4. Kill the backend process while the UI is open; confirm every page shows a connection error state, not stale-looking fake data.

---

## 8. Definition of done (every milestone)

Same as v1 `AGENT_BUILD_SPEC.md` §3, plus:
- [ ] No page silently falls back to `mock/seed.ts` data if an API call fails — show a loading/error state instead (a mock fallback that looks identical to real data is exactly the failure mode that caused this whole debugging session).
- [ ] Every deleted mock constant is confirmed unused (`grep` for its name across `web/src`) before removing it from `mock/seed.ts`.
- [ ] Screenshot diff taken before/after each page's wiring, attached or referenced in the milestone's `BUILD_LOG.md` entry.

## 9. If you get stuck
Same protocol as v1 `AGENT_BUILD_SPEC.md` §5 — log to `BUILD_LOG.md` under `## OPEN QUESTION`, resolve conservatively (prefer showing an honest error/empty state over inventing plausible-looking fallback data — that instinct is exactly what produced the bug this whole spec exists to fix).
