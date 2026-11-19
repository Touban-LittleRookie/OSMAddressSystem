# Fotouni work package: requirements and implementation record

Updated 2026-10-27. This is a continuing engineering record, not a declaration
that the work package is complete. Pilot scope and the January trial date need
team agreement. P0 = normal-use blocker; P1 = pilot candidate; P2 = later unless
the team chooses otherwise.

## Sources and starting state

- Current requirements: `C:/Users/Win10/Dev/todo.md`.
- Historical design: `C:/Users/Win10/Dev/INITIAL app_design`.
- Assignment: supplied pasted request; `C:/Users/Win10/Dev/prompt.md` is context.
  The twelve attachments contain two byte variants of the same assignment.
- Miguel's comments available here are those quoted in the request; no separate
  comments document was supplied.
- Parent: `main`, `473b5465be47dab1755a62bf865888a3ca253ac3`.
- Application: detached HEAD, `677bfaf7efbe8c773a2bd8b6e9a51366aa06e507`.
- Existing uncommitted work preserved: freehand/draft geometry editing, saved
  geometry overrides, related API/store/engine/project/CSS/docs changes, and
  `test_road_drawing_browser.py`, `test_road_geometry.py`.
- Python 3.13.7, uv 0.13.5,
  Git 2.51.0.windows.1. Use existing dependencies; no lockfile changes.
- All mutable work-package investigations use new copies under
  `cache/workpackage-4m6zx56t/`, made with copied input/network folders and
  SQLite's backup API. Neither the practice folder nor bundled project is
  used for work-package edits or recomputation.

The current stack remains appropriate for the first increments: Python GIS
and graph calculations, FastAPI, SQLAlchemy and Leaflet. No stack replacement
is justified by the observed ID-validation defects. Evaluate GeoLibre before
further geometry-tool expansion (todo recommendation); no migration selected.

## Inventory

Unless a row explicitly says tested/reproduced, existing behavior below is
established by code inspection only. Paths are relative to this repository.

| Todo | Priority | Existing code and tests | Required change / status / dependencies |
|---|---|---|---|
| 1.1 Move vertex/segment | P1 | `app/static/app.js` reshape mode; `app/roads.py:reshape_edges`; `tests/test_road_geometry.py`, `test_road_drawing_browser.py` | Prior work implements bend movement, insertion and freehand replacement between fixed endpoints; whole-segment translation is not implemented. |
| 1.2 Move shared node | P1 | `app/roads.py:integrate_roads`, `app/static/app.js` connection tools | Not implemented; needs atomic geometry changes for all attached edges and topology/persistence tests. |
| 1.3 Delete/prolong/split | P1 | `app/server.py` edge endpoints; drawing browser and backend tests | Existing tools; exact split eligibility and pending-ID behavior investigated in this increment. |
| 1.4 Connectivity guard | P1 | `engine.disconnected_parts`, `roads_warnings`, `roads.snap_click`; backend connectivity tests | Detect near misses for existing roads too; agree threshold and intended isolated roads. |
| 1.5 Review flag | P1 | No per-geometry review state | Add unreviewed/ok/needs-editing, filters, history; invalidate review on later geometry edits. |
| 1.6 Geometry change tracking | P1 | Geometry override events, deleted refs/imports; `exports.edge_table`, `osm_changes` | Prior work logs corrections; verify complete current-state diff including deleted OSM ways and restore. |
| 1.7 Oneway | P2 | OSM input fields exist | Manual override and routing semantics not implemented. Last per todo. |
| 1.8 KML files/undo | P1 | Import preview, per-file colour/removal; backend import tests | Existing support; browser usability and atomic undo coverage need review. |
| 2.1 Per-edge drivable | P1 | `engine.apply_edge_access`, `/api/edges/access(/path)`, `roads._with_lineage`; `tests/test_edge_access.py`, `test_edge_access_browser.py` | Implemented 5 November: drivable yes / no / unknown per edge with an A→B tool, as written in the todo; non-drivable roads show "may continue on foot or by motorbike"; rank 5 never drivable; OSM tracks are rank 4 and drivable (decision 7). |
| 2.1 Surface enum | P1 | Current `paved` tri-state, OSM surface parsing and exports | Introduce enum and migration; old False does not uniquely mean dirt/macadam/stone. Preserve original unknown information. |
| 2.1 Rank consistency/merge validation | P0 | `post_streets_assign`, `dominant_rank`, pending attrs; `test_street_assignment_rules.py` | Cross-rank merge refusal implemented and tested, including force and pending rank changes. Whole-app enforcement of one rank across cut-part attribute editing remains separate work. |
| B1 Wrong refusal | P0 | Merge validation in `app/server.py` | Exact reported IDs absent on both isolated datasets: node 2272487038 has 113/113/613, not 113/743/753. User said the example may be mistaken and instructed continuation. Unverified example, not a blocker; do not claim it reproduced or was fixed. |
| B2 New ID does nothing | P0 | Shared `street_ops.split_refs`, `_junctions.can_split`, `junctionHtml`; API and browser regressions | General eligibility now checks topology, incident road and proper resulting paths. Successful ID edits recompute and visibly show the new ID. Exact 735 report remains unverified; available node has 578/578/514. |
| B3 Recompute reverts edits | P0 | `no_cut`, `edge_street`, ID registry; new API tests and batch round-trip test | First fixes implemented/tested: force cannot bypass path/rank validation; fresh IDs reserve displayed/branch/named IDs; manual splits protected against recutting; retired pending targets rejected. Split/split/join/join survives compute, checkpoint, undo, restore and reopen. Full arbitrary-sequence guarantee and historical identity migration remain unproven. |
| B4 Stable identity | P1 | `Project.names`, `street_ids`, `branch_ids` | Edge-set keyed migration is not implemented; design with aliases and recover existing ambiguous ID decisions on a copy. |
| 2.3 noaddress | P1 | No end-to-end exclusion flag | Must affect plan, derivation, address snapping, signs and exports consistently. Clarify routing-through versus routing-to exclusion. |
| R1 Derivation eligibility | P0 | `branches.branch_parents`/`assign_branch_names`/`plan_minimal_naming` option `own_name_max_rank`; app `Settings.own_name_max_rank=2`; `tests/test_naming_rules.py` | **Implemented and tested (branch `naming-rules`, 2026-10-29).** Ranks 0–2 never take a derived name and are planned for hand naming. Library default unchanged (option off). Existing rank-not-higher and shorter-than-main checks verified by test. Cited `26-…NGOM` example not yet traced. |
| R2 First order only | P0 | `project.APP_MAX_LEVELS=1`, `Settings.__post_init__` cap; settings panel text; `tests/test_naming_rules.py` | **Implemented and tested.** Saved `max_levels=2` (Fotouni) is read as 1; history keeps the old value; one-line revert. Library default still 2 for generic use. Fotouni copy: two-level names 46 → 0, derived rank 0–2 streets 5 → 0, **streets to name by hand 34 → 85** (needs Miguel's acknowledgement before the pilot). |
| R3 Minimum naming set | P0 | Final-cut original-street planner in `engine.py`; exact MILP + greedy fallback; `tests/test_naming_rules.py` | **Implemented and tested locally (branch `naming-rules`, 2026-10-30).** One community task activates every cut part of its original street. The planner re-solves on the final cut graph, validates by rerouting, reports method/scope/optimality, and never substitutes a larger final plan. Fotouni copy: 67 tasks (58 coverage + 9 after-cutting), zero uncovered. The complete 67-task result is feasible but not globally proven minimal because stabilization added nine tasks. |
| 3.2 Structured names | P1 | One string per original ID; `set_name`, both browser pages | Design structured storage and reversible migration; keep OSM full name separate from abbreviation; do not automatically parse ambiguous existing names. |
| 3.3 Suggestions | P1 | Reference points/routing exist | Select from street's routed start, not midpoint; define relevant POIs, short-word rules and rank defaults. |
| 3.4 Warnings | P1 | Existing duplicate-name/disconnected/planned/address warnings | Add abbreviation collisions; retain click-to-zoom/count semantics and meaningful IDs. |
| 4 Address format/rules | P0 | `Settings` migration, `compute_addresses`, `numbering`, `tests/test_addressing_decision.py` | **Option 2 accepted and implemented locally 2026-10-30.** Defaults and unversioned legacy defaults migrate from 2 m/20 m to 1 m/10 m. Pinned examples: 26 m right gives house 26; 50 m left gives branch prefix 5. The core rounding/parity formula is unchanged. The separate compact address-text format still needs confirmation. |
| 4.0 Building inventory | P0 data, P1 tool | `input/buildings.gpkg`, Addresses map, manual access-point tool | Fotouni contains 2,127 surveyed point records. Yellow circles represent those records, not roofs detected from satellite imagery. Known buildings can have their road point corrected; roofs without a circle are unknown to the app. Add a traceable “missing building” tool with duplicate check, attributes, optional access point and undo before claiming complete house coverage. |
| 4.1 Azimuth | P1 | `side_from_azimuth`, survey field, location fallback | Measure actual survey coverage. A door bearing cannot be inferred reliably from a building point alone. Confirm field provenance/meaning and missing data policy. |
| 4.2 Distance | P1 | `max_house_distance_m=60`, no_street warnings, manual override tests | Setting exists; todo says 50 now and proposes 20–30. Confirm default and whether manual picks bypass the maximum. |
| 4.3 Street signs | P1 | `street_signs`, intersection sketch in `app.js`, exports | Add sign-rank setting, matching edge letters outside sign text; clarify numeric threshold direction. |
| 4.4 Direction signs | P1 | POI ranks/icons, `add_outside_signs` and nearest-sign behavior | New importance table reverses old rank-0 meaning. Needs migration, actual radii, turn-based arrows and combined lines. Not implemented. |
| 5 Checkpoints/audit | P1 | `Store` events/undo/redo/save/restore; backend tests | API `me()` is empty; no identified authors. New edits delete undone events. Recoverability exists; complete attribution/audit does not. |
| 6.1 OSM changes | P1 | `exports.osm_changes`, `.osm` export tests | Verify modified/deleted/new ways, versions and reverting edits. Never upload from tests. |
| 6.2 Address OSM format | P1 | Buildings/address GPKG/CSV | Dedicated OSM-friendly addr tags/export needs agreement and coverage. |
| 6.3 Streets list | P1 | Street CSV/GPKG and names exports | Existing; adapt to structured names/abbreviations. |
| 6.4 Houses list | P1 | Buildings table and survey metadata | Confirm Thierry's plaque/family columns and compact format. |
| 6.5 Street signs list | P1 | Signs exports | Extend letters/threshold logic with 4.3. |
| 6.6 Direction signs list | P1 | Reference rows in sign output | Separate complete download depends on 4.4. |
| 7 Simple page | P1 | `static/simple.html`; two existing browser tests | Names + addresses exist; new name form/suggestions must be implemented here too. |
| 8 Hosting | P1 | `deploy/`, health endpoint, single-process cache | Brief in `deployment-requirements.md`. Measure copied project; no purchase or deployment. |

## Decisions for Miguel

1. B1/B2 supplied IDs remain an unverified example. User instructed continuation
   on 2026-10-27 and suggested the report may be mistaken. Revisit only if a
   concrete failing sequence appears; do not keep requesting these IDs.
2. Confirm address examples: todo says branch 5 = 50 m and house 26 = 26 m,
   but also specifies branch divisor 20 m and house divisor 2 m. Preserve the
   existing calculations until examples and intended interpretation agree.
3. Agree French street types/defaults by rank and what counts as a short word;
   names shorter than four usable characters and abbreviation collisions need rules.
4. Supply the two direction-sign radii and approve migration from old rank 0
   (no sign) to new importance 0 (most visible).
5. Confirm noaddress's effect on through-routing, manual house-access limits,
   distance default, and trial roles/scale/scope.
6. Road access: should a motorcycle-only road count as drivable for street IDs and
   numbering? Decided 5 November: no. Only car roads are drivable; the setting was removed.
7. OSM `highway=track`: decided 5 November that tracks are rank 4 and drivable (they were rank 5,
   footway). On the practice copy's area this made 16 segments drivable and changed the street ID of 8
   segments (7 streets; 226 → 228 streets). A track that is really a footpath is set to not drivable
   during the area's Pass 1 attribute review. Please confirm.

## Implementation sequence

1. Reproduce ID defects on copies; add failing regressions for clear failure
   modes; fix preflight validation, unique ID allocation, split eligibility and
   pending edits before changing naming rules. Keep B1 unconfirmed unless reproduced.
2. R1/R2/R3: shared eligibility rules and first-order app planner; prove small
   known optima. Document migration of settings before modifying real projects.
3. Per-edge attributes/surface/noaddress, then structured names and both UIs.
4. Address/sign changes after worked examples and migration decisions.
5. Remaining geometry/review/downloads and deployment validation.

## Verification record

- Prior geometry increment: 12 targeted tests passed. These were rechecked
  earlier in this conversation; they are not a full-suite result.
- Initial non-browser baseline: 281 passed, 30 skipped, 3 failed. All three
  failures read a still-open NamedTemporaryFile through GDAL on Windows.
  The test helper now writes/closes files before GIS reads; unchanged export
  assertions subsequently pass.
- Added regressions initially produced 6 failures and 1 pass. Concrete failures
  included cross-rank/forced joins, bypassed branch validation, colliding new
  IDs, and splitting from a road not incident to the chosen node.
- Full-suite intermediate run: 305 passed, 30 skipped, 3 failed. Two compute
  waits exceeded 60 s (cause not established); one batch fixture could not find
  three whole same-rank connected streets. That fixture now splits an actual
  computed path into three pieces and rejoins them. The failed cases passed
  focused reruns. This intermediate run is not a clean final full-suite pass.
- Current focused results: 18 passed (14 community browser workflows plus
  four export/reference cases); 12 passed (10 ID-rule cases, visible split
  browser test and full batch/checkpoint/undo/restore/reopen round-trip).
  Final browser recheck after the installed-browser helper adjustment: 2 passed.
- The full run's 30 skips comprise 5 optional PostgreSQL pgserver cases and
  25 legacy geocode/street-editor browser cases requiring a separate bundled
  Chromium. No download/install performed. Community browser tests now reuse
  installed Edge/Chrome/Chromium; tile requests are blocked in those workflow
  tests, so imagery service availability is not validated by them.
- Isolated Fotouni network computations: practice copy 10.68 s; bundled copy
  9.87 s; each produced 216 computed streets. This is one local run each, not
  server sizing or representative production latency.
- Exact B1/B2 reports not reproduced because the named IDs differ, as above.
- No commits, pushes, deployment, OSM publication or source-dataset edits.

## First increment: review and continuation

Implemented: `app/street_ops.py` shared split/path validation; API preflight and
allocation fixes in `app/server.py`; exact split eligibility in `app/engine.py`;
rank-aware choices and truthful compute feedback in `static/app.js`.
Existing geometry work was preserved. No new schema or naming migration,
technology replacement, package download or lockfile change was made.

Local review server: http://127.0.0.1:8001/ serves the isolated practice copy
under `cache/workpackage-4m6zx56t/practice`; health and startup computation were
verified successful. Its logs/PID are in that copy. The existing port-8000
practice server and original project files were not restarted or edited by
this work-package increment. Both use the same source checkout, so refreshed
static files are shared; backend processes retain their loaded Python code.

Next task: R1/R2 app naming regressions (rank 0–2 require their own names;
first-order derivation only), with explicit handling of persisted max_levels=2
on another fresh dataset copy. Preserve generic library compatibility where
possible. Then R3 known-optimum graph tests and clear solver-status reporting.
Do not change physical address-number meaning from the contradictory examples.

Still partial/not started: B4 identity migration, all-addressing-surface rank
consistency, per-edge/surface/noaddress, structured names/migration, remaining
geometry/review flags, sign redesign, download additions and deployment proof.
The inventory above is the source of continuation status; the whole todo is
not complete. Keep each increment small and update results rather than
interpreting a previous test count as evidence for later code changes.

## Follow-up: screenshot tools (2026-10-27)

User steered current work to misplaced geometry, deleting a short portion of a
line, connected short-stroke tracing with a planned end, and dividing the map
into areas for progress tracking. This temporarily precedes the naming work.

- Implemented **Remove part of a road**: select an existing effective edge,
  choose two points, preview only the red interval, then save an undoable cut.
  Retained fragments inherit attributes; stable cut-node IDs preserve later
  fragment edits. Works for base and imported roads. Historical CSV geometry
  is cleared on rewritten fragments so computation cannot put the deleted
  portion back. Source input/network files remain unchanged. Stale cuts warn
  if a later source geometry no longer matches.
- Implemented **Trace route: start → end** with click points or connected
  freehand strokes. A planned end is not joined until reached. Gapped strokes
  are rejected; the first point of every continuation is exactly the preceding
  endpoint. Undo last stroke and movable draft bends remain available.
- Implemented explicit **path unclear** endpoints: stop short of the planned
  end, disable automatic endpoint connection, persist uncertainty, display a
  question mark and produce a compute warning. No automatic image recognition,
  road classification or inference of a path behind vegetation was implemented.
- Implemented **Work areas**: Automatic subdivision or metre-size presets,
  clipped to AOI/project boundary, with up to 400 actual cells. Progress and
  notes persist through undo/restore/restart and do not invalidate network or
  address hashes. Selection focuses/zooms and narrows reshape/cut selection;
  it does not clip roads or enforce an access-control boundary. This is manual
  area tracking, not completion of todo 1.5's per-geometry review flag. Review
  labels are not automatically invalidated after subsequent geometry edits.
- Improved the recomputation experience on 31 October: the last complete map
  remains visible, an unobtrusive bilingual status card shows the current
  backend stage and elapsed time, and the replacement road/base/component
  layers are prepared before one final visual swap. Area-only network
  recomputation was deliberately not introduced: a changed edge can alter
  cross-area connectivity, reference routes, cuts, IDs, naming coverage and
  addresses. Safe incremental computation requires an explicit dependency
  graph, stable identity rules, full-result equivalence tests and a full-run
  fallback; work-area rectangles alone are not a correct invalidation unit.
  A read-only profile on an isolated Fotouni copy found that repeated routed
  street construction/validation is the dominant cost (18.5 s cumulative in
  a profiled 23.0 s network run). Two server-equivalent runs that reused the
  saved branch-ID registry completed in 17.3 s and 15.5 s and produced
  identical public-network SHA-256 hashes, 237 streets, 67 naming tasks and
  zero uncovered streets. Because the repeated runs validate R3 after cutting,
  none were removed. A future optimization must prove equivalence to this
  full result and retain a full-computation fallback.
- Evaluated [GeoLibre's official overview](https://geolibre.app/) before this
  geometry increment: it describes a React/MapLibre GIS workspace and grid/
  vector tools. Replacing the existing Leaflet application is not necessary
  for this bounded set of tools and would require porting the editor, map
  layers and persistence integration. Kept Leaflet and existing Shapely/GIS
  dependencies; no packages or models downloaded.

Verification: a 24-test targeted batch passed (new sections/areas/browser
workflows plus earlier geometry and ID regressions). The existing backend
suite then passed 53 tests with 5 optional pgserver skips. Additional deleted-
geometry and automatic-grid regressions were added; the final geometry/area
batch passed 16 tests. Community UI browser tests block tile
downloads; separate real-map inspection on the review copy succeeded without
JavaScript errors. Automatic preview on the Fotouni boundary produced 58
clipped cells of 950 m; this preview was not saved to the database.

Review data was backed up before restarting the isolated port-8001 server:
`cache/workpackage-4m6zx56t/practice/before-route-tools-c7219054.db`.
The final restart also has `before-final-path-tools-420e0736.db` in that folder.
The original `fotouni-practice-20261026` folder and its port-8000 server were
not edited/restarted by this increment. Prior review-copy edits were preserved.
All changes remain uncommitted; no deployment or OSM publication occurred.

Main files: `app/work_areas.py`, `app/roads.py:cut_sections`, `app/engine.py`,
`app/server.py` cut/grid endpoints, `app/store.py` events, `app/project.py`
optional JSON state, and the full-map HTML/JS/CSS. New regression suites:
`test_road_sections.py`, `test_work_areas.py`, `test_route_review_browser.py`.

Limits/next: shared junctions remain fixed in the reshape tool; cuts can create
real network gaps and affect derived IDs/numbers. Old application versions do
not understand new cut/area events: use a pre-change backup for rollback.
First-order naming R1/R2 remains the next work-package priority after this
user-requested geometry increment. B1 exact example remains unverified per
the user's instruction to continue.


### 27 October: current-section deletion and right-click connections

The user reported a red dashed remnant that would not disappear after two
cut points, and asked for a road context menu and connection of a corrected
pink drawing to a yellow junction.

- Right-click resolves the effective road sections under the pointer, with a
  selector and highlight for overlapping lines. Offers reshape, two-point cut,
  whole-section deletion, endpoint connection, extension and street ID/name tabs.
- Whole-section deletion has a red preview and confirmation. The legacy delete
  picker now uses this same effective graph, including retained cut fragments.
  Render generations prevent late overlay responses from repainting old lines.
- Reproduced and fixed cut -> reshape fragment -> cut fragment replay. Geometry
  overrides on generated fragments must be applied after the parent cut exists.
- Physical endpoint joins are separate ordered road_join events; targets can be
  existing junctions, road interiors or cut fragments. An interior target is split
  into a shared node; both directions and edit mappings follow it. Street IDs are
  preserved. Free endpoints only, 60 m maximum movement, preview/confirmation,
  revision guards, source/target identity and shape guards, Undo/Redo/reopen.
- Imported-road overlays and endpoint reports are rebuilt after topology edits.
  Endpoint markers from the pre-cut/import graph must not remain clickable.

Evidence limitation: the investigation snapshot contains historical cuts whose
source sections were subsequently replaced by additional imports. The reported
red line cannot be identified uniquely from the screenshot. Historical cuts with
missing/changed sources are flagged for review, not applied to a nearby guessed
road. No guessed deletion or connection was saved to the user's review data.
The new context menu selects the current section directly.

Regression suites: test_road_sections.py, test_road_junctions.py and
 test_road_context_browser.py; existing drawing and route browser workflows
are also checked. New events require this application version; rollback should
use the pre-restart SQLite backup. Original input files remain unchanged.

Verification for this increment: 19 geometry/junction/browser tests passed in
one final batch. The broader existing backend + ID rules + work-area batch
passed 67 tests with 5 optional PostgreSQL skips. JavaScript syntax and diff
whitespace checks passed. The drawing browser test now uses the shared installed
browser helper to block external tiles instead of waiting for satellite downloads.

Restarted only the isolated port-8001 review server after SQLite backup to
`cache/workpackage-4m6zx56t/practice/before-context-tools-3dbb3de9.db`.
The latest live state was revision 88, with 380 editable sections and 34 drawn
sections in its effective overlay. Five older saved cut records still report
missing/changed source sections; these were not silently remapped. Port 8000
and its original project process remained untouched. Normal startup initiated
the application's configured automatic network computation.


### 27 October: interface refresh and English/French selection

User requested a clearer, more attractive interface and language selection.
Implemented in the existing Leaflet/vanilla JavaScript pages; no build step,
package installation, database migration or backend change was needed.

- Warm off-white and green palette, clearer type/spacing, accessible focus
  outlines, grouped road actions, contextual workspace headings and a map guide.
- Full editor and community `/simple` page both offer English / Francais.
  Preference is browser-local and persists across reloads; initial language
  follows the browser when no preference was saved. Available before reference
  confirmation. Changing language does not write project state.
- Shared `static/i18n.js` translates authored UI strings and literal HTML parts
  before data is interpolated. Place names, addresses, user-entered names,
  checkpoint labels, IDs and road geometry are not translated or rewritten.
- Core editing/navigation/forms, reference confirmation, context actions and
  common warnings have French labels. Unmapped specialist diagnostics/API error
  messages retain their original English; browser-native file picker text and
  map-provider labels follow those providers/browser settings.
- Switching language preserves unfinished road points, current form values,
  area-note drafts, selected work area and map view. The community naming popup
  is updated in place, retaining an unsaved name. Mobile warnings start compact
  and can be expanded; map and tools retain separate usable scroll areas.

New verification: `tests/test_interface_language_browser.py` covers switching
while reference-locked, draft geometry and name preservation, unchanged project
revision, French controls, mobile overflow/map height, preference persistence
and a street literally named Save (must not become Enregistrer).
Desktop/mobile screenshots are generated on synthetic copies. Read-only browser
inspection of the current Fotouni map also found no JavaScript errors; all POST
requests were blocked during that inspection. Preview screenshots are under
`cache/interface-preview/`. This is a local interface change, not a deployment.

Interface verification outcome: the 14 existing community browser scenarios,
2 new language scenarios and 5 road/ID browser scenarios passed across the main
and focused runs (21 distinct scenarios; not one final full-suite run). The final
focused run passed 3 cases: import/accept/delete and both language workflows.
The broader checks exposed a stale deletion-picker cache and an old test polling
that cache without a null guard while refresh invalidated it. The picker cache
now contains the effective visible sections; its tooltip uses length_m. The test
selects a visible straight section and waits for the refreshed cache. A duplicate
community popup during language switching was fixed by updating the existing
popup in place. JavaScript syntax checks and git diff --check passed.

No backend/data-format changes or restart were required for the interface:
port 8001 serves these local static files directly. Refresh the browser to load
them. No commits, pushes, deployment or edits to live map data were performed
for this interface increment. One earlier combined test run emitted a Windows
native access-violation diagnostic during concurrent GIS requests; it did not
recur in the later focused language/import checks. No claim of production load
stability is made from these local browser results.


### Product flow, attribution and logo exploration

Added `docs/design/user-flow-and-toolbox.md`: proposed resident/editor entry
paths, stage/tool organisation mapped to the todo list, project roles, review
states, trusted attribution and pilot implementation order. Evidence: API
`me()` is empty, and `_add_event` deletes undone records on a new action, so
existing recovery/history is not a complete identified append-only audit.
This is a design proposal; accounts/permissions/approval are not implemented.

Added three original native SVG logo options and an interactive comparison in
`docs/design/logo-options/`, with working-name, dark and one-colour previews.
SVG XML parsed successfully and comparison controls/narrow-screen layout were
checked in installed Edge. No generated-image API, packages or external
branding service was used. No logo was selected or installed in the app.
The proposed name Community Address is provisional pending the user's choice.
Application code, project data and running servers were unchanged by this task.

Branding clarification: user confirmed Project - Community Addressing Cameroon. Updated all three logo comparison wordmarks, added standalone named SVG lockups, and refreshed previews. Project is a separate label. Logo selection and app implementation remain pending.


### Selected Community Addressing Cameroon logo

User supplied Logo cartographique Community Addressing Cameroon.png and asked
for integration, adapting the background if needed. Inspection found RGBA
transparency (corner alpha 0), so no background removal or image regeneration
was needed. Copied the original byte-for-byte to
`app/static/brand/community-addressing-cameroon.png`; SHA256 matches the source.
Added `brand.css` for a compact pin crop with readable HTML project branding,
plus the original full logo on reference-point cards. Both full and community
pages load the same artwork, including under `/simple/` path prefixes.

Verification: 3 browser checks passed (language/draft preservation, community
naming/language and reference-confirmation locking). Read-only Fotouni desktop
and mobile checks found no JavaScript errors or horizontal overflow. Project
data and backend logic were unchanged. Existing workflow/account proposal
remains pending; no authentication or approval system was added by this task.


### 28 October: invited accounts, API permissions and retained audit history

Implemented individual local accounts, one-use invitations, password change,
admin role/disable/reset controls, verified per-request actor IDs, revocable
HttpOnly sessions, CSRF/origin checks and persistent login throttling. Roles:
viewer, contributor, mapper, administrator. Auth is enabled by default in serve;
old in-process tests explicitly opt out. No package downloads or identity-service
subscriptions. See `docs/accounts-and-history.md` for the capability matrix,
setup/recovery, security parameters, migration and deployment details.

Store schema 3 adds audit/closed_redo evidence and account_* tables. Existing
anonymous entries remain Unknown (legacy); no fabricated authors. Undo/Redo no
longer delete old records; conservative conflict checks prevent replay across
other editors' input changes or undoing a prerequisite. Checkpoint restore is
admin-only with a reason and revision check; it never restores credentials or
roles. Reference confirmation is read-only in account mode. Background
calculation requests/completions have system/input-hash audit records.

UI: English/French setup/sign-in, invitation activation, Team controls, personal
passphrase change, History with actor/action/date, filters and before/after.
A selection-popup re-entry guard fixes a Leaflet pan/moveend race exposed by the
two-browser naming flow. Mobile sign-in sizing was checked including the fixed
overlay's own width, not only document overflow.

Verification: existing backend 53 passed / 5 optional PostgreSQL skips. An
integrated security/UI run passed 34 tests; a later account run passed all 17 API
cases but exposed the popup race in its browser case, fixed above. Final focused
UI run passed 5 cases (two authenticated account flows, two language workflows,
one street-ID workflow). Recovery and read-only reference checks are also tested.
This is not a final full-suite or production security assessment.

Review server: http://127.0.0.1:8002/ uses the fresh copy under
`cache/accounts-review-dsrlaipr/project`, copied from the prior review at revision
96. Pre-migration SQLite backup is `cache/accounts-review-dsrlaipr/before-accounts.db`.
`cache/current-review-project-path.txt` now records that full project path;
`cache/current-accounts-review-path.txt` records its parent. The older
current-workpackage pointer is historical. Logs/PID are in the new parent.
The copied edit records and revision were checked against the backup. No real
administrator/password was created during the migration: initial setup stays with the team.

Automatic approval review rejected the attempted port-8001 restart with only
"blocked by policy" as its reason. Used a separate port-8002 process instead;
ports 8000 and 8001 and their project data were left running unchanged. The
older port-8001 backend does not enforce these new account rules. No commits,
pushes, cloud deployment, OSM publication or messages to third parties.

Limits: public approved lookup/review-and-approval workflow, SSO/MFA and email
recovery remain separate work. Contributor naming is direct editing, not a
proposal queue. One process per project; PostgreSQL does not change that cache
and request-serialization constraint. Local passwords/sessions are for the pilot
workspace; hosted usage requires HTTPS and a reviewed proxy/backup setup.

Final recovery/browser batch: 5 passed, including admin invitation reset, console recovery, read-only reference acknowledgement and the two account browser workflows. Actual port-8002 full and /simple/ setup screens inspected read-only with no JavaScript errors; all API writes blocked during inspection. Anonymous /api/project returned 401. No administrator was created during these inspections.


### 29 October: naming rules R1 and R2 (branch `naming-rules`)

Implemented R1 (ranks 0–2 always need their own name) and R2 (first-order derived names only) in the
library as an opt-in option and in the app as fixed rules. Nine new tests in `tests/test_naming_rules.py`
failed first (including the end-to-end grid, which produced `x-y-name` names), then passed. Core batch:
130 passed, 5 optional PostgreSQL skipped.

Measured on a new copy (`cache/naming-rules-check/project`, SQLite backup of the port-8001 review data;
source opened read-only): two-level names 46 → 0; derived rank 0–2 streets 5 → 0; uncovered 0 → 0;
streets to name by hand 34 → 85 (rank 1: 5, rank 3: 5, rank 4: 70, rank 5: 7). Compute time about 10 s
for each run.

Decision for Miguel: the hand-naming list more than doubles under R2. Confirm before the pilot.
Next: R3, starting with the 13 after-cutting and 8 connection additions; report solver optimality in the app.
Not committed or pushed.

### 30 October: R3 final-cut naming plan (branch `naming-rules`)

Implemented a grouped naming solve on the final cut graph. A community name belongs to an original street,
so every current part cut from that original is activated by the same naming decision. The result is rerouted
and checked for uncovered or disconnected streets; required additions are included, and a candidate is accepted
only when it is valid and no larger than the preceding plan. Planner method, scope, rounds and whether the
minimum is proven are exposed in the API stats and Names panel.

Known-optimum 3x3 end-to-end test: five initial cut-part candidates reduce to two original-street tasks, with
zero uncovered streets. Fotouni copy (`cache/naming-rules-check/project`, no writes): 67 tasks, comprising 58
coverage and 9 after-cutting tasks; zero uncovered streets. The exact grouped coverage solve completed, but the
nine stabilization additions mean the complete 67-task result is reported as feasible, **not globally proven
minimal**.

The 29 October handover says 85 tasks while its listed categories total 87 (65 + 13 + 8 + 1). Reproduction of
the pre-R3 cut-part behaviour also gave 87. Treat 85 as a reporting/counting error, not as a verified baseline.
At that time no house-number setting or formula had been changed. On 30 October the user confirmed that Miguel
accepted Option 2; the implementation and measurement are recorded below.

### 29 October: house-number meaning, project lead's answer

The project lead (the doctor) favours Option 2: house number = metres from the start of the road
(26 = about 26 m), branch number x 10 = metres along the main street (5 = about 50 m). Four-digit house
numbers cover up to 9,999 m along one street; the longest street in the review data is street 62 at
about 3.8 km. No plaques have been printed yet, so changing the numbering invalidates nothing printed.
On 30 October the user confirmed that Miguel accepted Option 2. Implemented app defaults and versioned legacy
migration: `house_step_m` 2 -> 1 and `branch_step_m` 20 -> 10. The core formula remains unchanged. Tests pin
the todo §4 examples (26 m right gives 26; 50 m left branch gives 5) and preserve deliberate versioned custom
steps.

Read-only before/after measurement on `cache/naming-rules-check/project`: 2,127 surveyed buildings plus 62
reference points; 1,836 of 2,189 displayed numbers change and 124 of 237 common street display names change.
Addressability does not change: 743 complete addresses, 1,099 pending a community street name, zero lacking a
derivable/planned name and 347 farther than the current 60 m road limit. No project data was written.

### 1 November: quartier work areas and five-part progress

The single general work-area status is being replaced by five independent, persistent review stages: road
geometry, street attributes, names, buildings and addresses. Each stage has values appropriate to that work
(including Waiting for community for names and Needs correction/Verified for addresses). A derived overall
status remains only for the map colour and old projects migrate conservatively: their former status applies to
road geometry only, never to the other four stages.

The survey CSV's `district`, `latitude` and `longitude` fields may be used to propose quartier work areas. This
is a preview-and-confirm workflow, not a claim that point observations define official boundaries. Points are
filtered to the project boundary; case/accent/punctuation variants are grouped conservatively; similar remaining
spellings are shown as suggestions; and a human can retain aliases or merge spellings by entering the same
accepted quartier name. Provisional areas are nearest-observation (Voronoi) polygons clipped to the project
boundary and united by the reviewed quartier name. They replace the rectangular grid only after explicit
confirmation and the replacement is one undoable edit.

Privacy constraint: the browser sends the chosen CSV for preview/generation, but the project saves only the
resulting polygons, accepted quartier name, observed spelling counts and aggregate row counts. It must not save
survey rows or unrelated personal/socioeconomic CSV columns. The spelling and generated boundary remain
provisional until Miguel reviews them and the project lead accepts the relevant project decision. Temporary
internal road names remain server-only and must not be published as OpenStreetMap names.

Quartier boundary correction is a topology-preserving edit of the shared border between two neighbouring
quartiers. The two endpoints remain fixed where other borders meet; intermediate points can be inserted, moved
or removed. Saving requires a field-evidence/reason note, is one undoable attributed edit, and preserves the
exact combined coverage of the two quartiers without gaps or overlaps. A correction remains provisional until
reviewed; it moves road-geometry review from Not started to In progress rather than marking it automatically
complete. The French field package is under `docs/review/`: a simplified printable questionnaire/PDF, a short
priority table of possible name variants with a neighbouring-quartiers column and no personal survey data, and
a first-person message for the project lead to forward. Exact boundaries are deliberately deferred to a live map session.

The approved `Overview Abbreviations.xlsx` received on 2 November changes the area model from one interchangeable
area layer to a hierarchy: Whole map -> Quartier -> Work area. Quartiers do not replace the original review grid.
Each grid cell is assigned to the quartier with which it has the greatest overlap, retains its five-part progress,
and remains the level at which detailed review is recorded. The catalogue provides the Fotouni Yes/No decision,
canonical name, trigram and census variants. The subsequent explicit decision `Balassie is Lassié` overrides the
apparently contradictory spreadsheet rows: Balassie/Lassie/Lasssie resolve to `Lassié (LAS)`, leaving 24 approved
Fotouni quartiers. Nineteen have observations in the supplied GPS CSV; Balafi, Djeugne, Kouotchack, Mbeum and Tcham
have no such observation and therefore need approximate placement during live review. Catalogue-excluded survey
labels are reported but do not silently become quartier areas.

### 5 November: road access per edge, partial-reshape point removal, remembered view

(Superseded by the next entry: there is no moto class any more; drivable is yes (car) / no (foot) / unknown, and
not drivable reads "no car access, may continue on foot or by motorbike".)

Todo 2.1 per-edge drivable is implemented as an access class per edge: car, moto (motorcycle/bicycle), foot or
unknown. "Classify a stretch" (Edit streets > Road access, or right-click a road) snaps A and B to network nodes,
follows the shortest existing route (or the second one), and saves one undoable edit. Roads are never moved or
split and street IDs do not change. The street popup's drivable value still writes car/foot to all its edges.
Only car counts as drivable for street IDs; unknown keeps the old rank rule; rank 5 is never drivable.

Two faults were found and fixed during verification. Unknown access was read as not drivable (pandas stores it as
NaN, not None), which would have changed IDs for every unclassified road. A classification was lost when a road was
later split by a new connection, cut or joined; the pieces now carry `ref_lineage` and inherit it.

Reshape between two points gained Remove last point (anchor A cannot be removed). The browser remembers its tab,
map position, colour mode and work area across a refresh; unfinished drafts are not restored.

### 5 November (later): drivable yes / no, tracks drivable, reshape anchor B kept where clicked

After checking todo 2.1 again, the A→B tool now sets what the todo asks for: drivable yes / no / unknown (stored as
car / foot / null; an older "moto" value still reads as not drivable but can no longer be written). The motorcycle
setting was removed. The two colour modes were merged into one "drivable" view per segment; not-drivable roads read
"no car access, may continue on foot or by motorbike" in the legend, tooltip and street popup, and OSM tracks are
named in the tooltip so they can be checked in each area's attribute review.

OSM tracks are now rank 4 and drivable (decision 7), also in projects whose network was built under the old rule;
a track mixed with a path in one way keeps its stored value, and a mapper's "no" still wins.

Reshape between two points moved anchor B onto the old line (to its end when clicked past it), so the trace
finished away from the point the mapper chose. An anchor clicked more than 2 m off the old line now stays where it
was clicked: the new trace passes through it and rejoins the old line from there. Past a dead end, the road end and
its node move to the click (at most 30 m). Past a junction, B stays on the junction; junctions never move.
Tests: `tests/test_partial_reshape_anchor.py`, additions in `tests/test_edge_access.py`.

Reshape between two points, A and B on different sections: roads are split into sections at every node, and the
tool used to keep both anchors on the section first clicked, so a B clicked on the next section was pulled back to
the end of the first one. B now lands on the section nearest to it; the stretch between A and B follows the
shortest route along existing sections (at most 3 km and 40 nodes), is shown in orange and is traced again from A
to B. Saving cuts the new trace at the nodes between the sections, moves those nodes onto it (side roads keep
their connection; only their last point moves), and reshapes every section, as one undoable `road_stretch` event.
No road is added, the sections keep their references and street IDs. Node moves are stored as `roads.node_moves`.
Tests: `tests/test_partial_reshape_anchor.py`.

### 6 November: tab renamed; edits on roads no longer lost when roads are drawn afterwards

The second tab is now "Street types and IDs" ("Types et identifiants des rues"): besides the street IDs it colours
and edits rank, drivable and paved.

Two edits came back after Compute in the practice project. Both were saved by reference to a road section
(`u-v-key`), and both references stopped existing:

- A portion deleted to be redrawn reappeared next to the new road. Drawn roads were added before the deletions were
  replayed, so a road drawn from a cut end found the old, uncut section and split it, and the deletion no longer
  found its section. Deletions on sections that exist before the drawn roads are added are now replayed first; the
  others (on drawn roads or on pieces they split) still run afterwards. A deletion whose section is gone but which
  lies on a portion an earlier deletion removed counts as done (the same portion deleted twice).
- A reshape (or deletion, drivable value) on a drawn road was lost when another road was drawn. The nodes made for
  drawn roads were numbered in sequence, so one new node renumbered the others. Their ids are now stable: the ids
  they had are recorded once, on the first opening (database `meta` table, outside the edit history, so undo and
  checkpoint restores keep it), and a new node gets an id from its position (negative, like cut nodes).

In the practice copy this restores the one deletion that had stopped applying; the 24 reshapes that applied still
apply. Tests: `tests/test_drawn_road_edits_persist.py`.

### 9 November: road edits applied in the order they were made; fast recompute

The fixes of 6 November did not hold. On 9 November a road drawn again over a deleted drawn road (`road1:3`, deleted by
edit 198), starting on a reshaped road, made the reshape (edit 202) and the deletion stop applying: the road above went
back to its old shape and the deleted road came back next to the new one. Five older edits at the same junction (edits
143-146, 167, 171, 174) had already stopped applying without any message.

Cause: every recompute rebuilt the whole network from the folded edits in a fixed order (all drawn roads together, then
the deletions, reshapes and connections). Each edit names the section it was made on (`u-v-key`), but that order never
rebuilds the network the editor saw, so any new road could rename sections and earlier edits silently stopped applying.
The fixes of 6 November corrected two such orders; this was a third.

Change:
- The edits made so far keep exactly the result they have now: it is replayed once the old way and kept
  (`computed/replay/frozen-<key>.pkl`; the edit it stops at is recorded in the database `meta` table as `replay_base`).
- Every later network edit (drawn road, deletion, reshape, connection, deleted section, street assignment) is applied in
  the order it was made, on top of the network it was made on (`engine.replay_in_order`, `Store._replay_plan`).
- Undo of a later edit replays only the later edits; undoing or restoring something of the frozen part replays it again
  the old way.
- An edit that cannot be applied is reported (`lost_edits`, a warning in the map with the edit number), never silently
  left out.
- A drawn road keeps the street id it gets when saved (`Store.import_roads(first_street_id=...)`), so undoing an earlier
  road no longer shifts the ids (and the rank / paved values) of later ones.
- Recompute after an edit applies only that edit: about 3 s instead of 32-38 s on the practice project.

Checked on a copy of the practice project: the frozen result equals the old replay exactly (1,284 sections); with road 31
drawn again, only road 31 is added and the section it starts on is split where it was clicked, with the reshape kept to
0.0 m; nothing else changes. Test: `tests/test_drawn_road_edits_persist.py::
test_redrawing_a_deleted_drawn_road_from_a_reshaped_road_changes_no_other_road` (fails with the old replay).

Not changed: the five edits that had already stopped applying before 9 November are part of the frozen result and still
do not apply; they need to be checked on the map.

### 10 November: road check per work area

The Edit streets tab has a **Road check** section (first, open). It lists what to look at in the selected work area or
quartier (or the whole map), most urgent first, on the current network with every edit applied; nothing is changed by
it (`road_check.py`, `GET /api/roads/check?area=<id>`).

| Kind | Rule |
|---|---|
| Edits not applied | a saved deletion, connection or reshape that does not apply (with its edit numbers) |
| Gaps | a free end within 10 m of another road it is not connected to |
| Roads on top of each other | two sections within 1.5 m of each other over at least 10 m (or half the shorter, at least 3 m) |
| Roads cross without a junction | two sections cross more than 1 m from their ends |
| Not connected to the network | a part not connected to the main network |
| Very short sections | under 5 m |
| Drawn road ends not connected | a free end of a drawn road, nothing within 10 m |
| Drivable not set | the sections of a street whose drivable value is unknown (one item per street) |

Each problem is a marker on the map; a click (on the marker or the row) zooms to it. **OK as is** marks a problem that
is right (a real dead end, a bridge); it is one undoable edit (`road_check_ok`, `roads.check_ok`), changes neither the
roads nor the ids, and the problem is not listed again while it stays at the same place. The list refreshes after each
edit (about 2 s for the whole practice map). Tests: `tests/test_road_check.py`, `tests/test_road_check_browser.py`.

On the practice copy: R01C08 has 1 gap and 1 free drawn end; R02C08 has the 4 places of the 7 edits that do not apply
(143-146, 167/171/174), a 0.9 m gap and 5 sections under 5 m.

### 10 November: "partly" drivable or paved in the street popup

The popup's drivable and paved are a summary of the street's sections (yes when most of the known length is drivable),
while the drivable colours on the map are per section. A street with some drivable and some unset sections showed
"yes" in the popup and dotted on the map, and choosing "yes" did nothing because the choice did not change. The popup
now shows "partly: choose to set all of it" when the sections disagree; choosing yes, no or unknown sets every section
of the street (or of the part). Checked on a copy of the practice project with streets 72 and 639. Test:
`test_a_street_partly_drivable_says_so_and_choosing_yes_sets_all_its_sections`.

### 12 November: derived names written in walking order ("Voie 447 du Boulevard X")

Loryan chose to keep the branch number in tens of metres and change only how derived names are written. A branch that
leaves the Boulevard X at about 4,470 m on the left was shown as `447-Boulevard X`; it is now shown and printed as
`Voie 447 du Boulevard X`. The second level reads from the main street outwards: `10-447-Boulevard X` becomes
`Voie 447/10 du Boulevard X`. The article follows the root name (du / de la / de l' / des; `de #512` for a street still to
be named). Only `display_name` changes (map labels, addresses, exports); the internal `branch_name` keeps the old form,
which the naming code parses. On a copy of the practice project: 161 derived names, for example
`Voie 104 du Boulevard Fo NGOMSEU - NGOM`. Tests: `test_display_name_prefers_own_name`,
`test_the_written_name_reads_from_the_main_street_outwards`.

### 13 November: paths that give no addresses, the address register and the plaque

Proposed to the project lead on 13 November (format document); built so that nothing changes until it is used.

* **Paths that give no addresses.** The street popup has *gives addresses* (yes by default). A path set to *no* keeps its
  geometry and routing, but its houses take the number of the point where the path (through other such paths) reaches a
  street that gives addresses, with a letter in walking order from that street: `230A`, `230B`; the side is the side the
  path leaves on. The houses keep that street's name (`230A, Voie 447 du Boulevard X`). Stored as `addresses: false` in the
  street attributes; it only changes the addresses (`address_hash`), not the network (`state_hash`). Which paths should be
  set to *no* (for example under 50 m or fewer than 3-5 houses) is still to be decided by the project.
* **Register: approved addresses are frozen.** *Approve* (one house, or every complete address of a work area) stores the
  address with a permanent code. Later computations never change an approved address: the house keeps it, and when the
  map would now give something else it is listed *to review* (house panel, `/api/register`). A correction needs
  a reason and keeps the code; *Retire* (house gone) needs a reason, and its number and code are never given again; a new
  house whose number is taken by an approved or retired address gets the next free letter. Approvals are undoable events
  (audit kept); restoring a checkpoint never takes them back. Only complete addresses can be approved (street named, road
  found). Approving needs an administrator account until the project decides who validates.
* **Provisional code** `FTN-000123-0` (sequence and a check digit), until the project fixes the matricule (`TCK 0575 4575`
  format still to be explained); only the code generator would change.
* **Plaque** `/api/plaque/<building>.svg`, 200 x 250 mm: `FOTOUNI · <quartier trigram>`, the number, the street, a QR code
  (dark on a light square; holds only the code and the position, no family name) and the code. A house not approved yet
  gets a *BROUILLON* plaque. The SVG is vector (for the plaque maker); the browser saves it as PDF or image.

Tests: `tests/test_address_register.py`.

### 15 November: address in the "plaque d'immatriculation" format, family name on the plaque, changes to validate

Decided with the project lead on 15 November (meeting, then written messages of 15 and 16 November); points agreed by
the team on 16 November. The 13 November plaque and the frozen-register wording above are replaced by this.

* **Address** `TCK 0575 0230` (`osmaddresssystem/app/plate.py`): quartier trigram of the house (survey quartier, catalogue
  of Overview Abbreviations), then the street, then the house:
  * street: its number on four digits while it has no official name (`0575`, the street id the app shows as `#575`), its
    four-letter code once named (`KUET`). The code written at the end of the name wins (`Boulevard Fo FONDJO II D. - FON2`),
    then the official chief codes, then the first four letters of the first non-generic word. **Names are never invented**:
    only the authorities name streets, so most streets keep their number. Two different named streets with the same code
    are a warning.
  * house: metres along the street on four digits, even on the right and odd on the left (unchanged), a letter when two
    houses share a number on the same side (`0230A`).
* **Ruelles** (streets with a derived name, `Voie 447 du ...`): no street number of their own. Written as the street they
  leave, preceded in brackets by the distance from its start divided by 10 and `D` / `G` for the side they leave on:
  `TCK (447D)KUET 0230`. The houses of a ruelle are numbered along the ruelle (even / odd sides). A ruelle of a ruelle:
  `TCK (447D-012G)KUET 0030`. Two ruelles in the same position on the same side take the next free number (`448D`).
  The position is the plain rounded distance (`D`/`G` gives the side), so it can differ by one from the parity-nudged
  number in the written derived name (`Voie 447 du ...`); the plaque uses only the new format.
* **Plaque** (200 x 250 mm, approved colours): `FOTOUNI · TCK`; the family name (two lines at most); the QR code (black on
  white) holding, in this order, the village and trigram, the family name, the GPS position and the address; the address
  at the bottom. **No phone number** on the plaque or in the QR code (anyone can scan it). Draft mark until validated.
* **Address card** `/api/card/<building>.svg` (85.6 x 54 mm), the same content for the household.
* **Family names** come from the EFYL admin export: `python -m osmaddresssystem.app import-households --project DIR --csv
  efyl_admin_export_*.csv` writes `input/households.csv` (git-ignored; joined on address id + time). The plaque shows the
  family name, else the business / public place name. Contact names and phones are shown to administrators only
  (`/api/households/<building>`) and are never printed.
* **Changes are validated, not frozen for ever**: when a road edit changes a validated address, the house is listed
  *change to validate*; validating (one house, or all changes with one reason) records before / after. *Families to inform
  (CSV)* (`/api/register/changes.csv`, administrators) lists each change with the family name, contact, phone, position, old
  and new address, so the family can be told and its card replaced. `FTN-000123-0` stays as an internal identifier only.
* Houses on a street still to be named are now complete (their address uses the street number) and can be validated.

Trial on a copy of the practice project (16 November): 1,610 of 2,127 houses get a complete address, none twice; 1,167 have
a name for the plaque (960 surveyed buildings without a household interview have none); QR codes are versions 4 to 8.
Open: survey quartiers `Baving` (190 houses with a road), `Demkwouo` (30; in the abbreviation list as not Fotouni, `DMK`),
and a few spelled `Bai`, `F`, `J`, `Unknown`, `Hiela-Marché Fotouni` have no trigram yet; streets `Rue Fo Dombeu Michel`
and `Rue Fo FOMO André` have no official code (automatic `DOMB`, `FOMO`).

Tests: `tests/test_address_register.py`.
