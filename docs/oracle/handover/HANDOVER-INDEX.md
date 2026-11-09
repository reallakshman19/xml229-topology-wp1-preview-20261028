# TopoFix programme — HANDOVER INDEX · checkpoint 9 Nov 2026

**For the next Oracle (same Claude, new PC). Read this page first, then `state/lanes.md` (the only "now"), then the per-project page.**
LOCAL/DRIVE ONLY: this pack quotes chat URLs and Owner-file details. Never publish it; the public copy is the redacted PR #27 docs.

---

## 1. The overall concept (what we are building and why)

The Owner (reallakshman19) runs one programme with five pieces, all about getting piping-stress models from one tool's XML into CAESAR II (`.cii`) correctly, without silently losing topology, coordinates or weights.

```
                 ┌──────────── XCU: UXML hub, strict readers, XML patch-back ─────────────┐
 Source CII ─┐   │                                                                         │
 Target CII ─┴─► enriched XMLs ─► MAP nodes/elements ─► EDIT in XML (lane B) ─► EXPORT target CII   = lane C
                 │                                                                         │
 Model XML ──────┴─► UXML ─► TopoFix finds + fixes (lane A) ─► edit ops ─► patch original XML (lane B) = A + B
 Model XML (PSI116 / PipeStressExport) ─► XML→CII standalone app (3D_Converters):
        Step 4 Preview speed (PERF) · RIGID split + weight correctness (RIGID) · CII export
                                         ▲ lane A's continuity check integrates here later
```

| Piece | Repo (all PUBLIC) | Aim in one line | State 9 Nov |
|---|---|---|---|
| **A** TopoFix | xml229-topology-wp1-preview-20261028 | find/fix topology & continuity on any XML, read-only on originals | PR #36 merged; idle; A4 hardening card to draft |
| **B** XML Compare (XCU) | XML_Compare_Utilities | edit the original XML safely (alias/coincident-node ops, patch-back, proofs) | #258 + #259 merged (main e09c81d1); idle |
| **C** CII→CII transfer | (XCU / CII toolkit) | move node names / properties (e.g. PRESSURE1) from a source CII to a target CII via enriched XML | not started (Owner: later) |
| **PERF** Task 1 | 3D_Converters_v0.5a | make the XML→CII app's "4 Preview" tab (Fetch / Build / Rebuild) fast and reliable | 1.R15 gated REPAIR; 1.R16 drafted, not sent |
| **RIGID** Task 2 | 3D_Converters (PR #406) | RIGID (flange+valve+flange) split keeps the right weight per element; prove it in actual CII bytes | S1 accepted; S2-R2 gated REPAIR; S2-R3 drafted, not sent |

Shared invariants across all pieces: reader and CAESAR II must see the same topology; originals are patched only by XCU; never auto-join a questioned connection; never invent a weight (unknown stays unknown, never 0); never commit Owner files.

---

## 2. CII and XML architecture (what the code actually does)

### 2.1 The XML formats
- **CAESAR II Input XML** (lanes B, C): `<CAESARII><PIPINGMODEL><PIPINGELEMENT FROM_NODE TO_NODE DELTA_X DELTA_Y DELTA_Z DIAMETER ...>`.
  - Attribute names are **case-sensitive** (`delta_x` is not `DELTA_X`).
  - **Only exactly -1.0101 means "unset"** (the sentinel); -1.010095 is a real number. The S3 reader once treated anything within 1e-5 of the sentinel as 0, which was the 1.2-R4 hole.
  - `DELTA_*` are the authoritative displacement in the declared length unit; literal FROM_/TO_ coordinates are optional and must agree with the DELTAs.
  - XML whitespace is only #x20/#x9/#xA/#xD (NBSP is not whitespace).
  - Bend TO and curvature nodes sit off their DELTA position; nodes placed from the TIP sit at it.
- **PSI116 / PipeStressExport XML** (A, PERF, RIGID): `<PipeStressExport><Pipe><Branch><Branchname>…<Node>` records with `NodeNumber`, `Endpoint` 1/2, `ComponentType` (RIGID, FLAN, VALV, REDU, PCOM, TEE…), `Weight`, `AlphaAngle`, bore, rating, position. A component is described by its endpoint records; PCOM = pipe-component connection spans.
- **BM2** = the Owner's benchmark model (public in 3D_Converters). **Enriched R9** = BM2 + staged STF + Import Masters (weights, ratings, line list, piping class, material map) → `bm2-enriched-R9.xml`, 687,252 B, sha256 `5cf2bfbe…e00c`. **R9 is an Owner file: Drive only, never in git** (a 71 % derived copy leaked into the public PR #406 branch history at ef4fae3e; the Owner chose "replace, keep history").

### 2.2 XML → CII in 3D_Converters (PERF + RIGID)
```
UI (tabs/model-converters/legacy-adapter.js, workflow/*)
  Step 4 Preview: Build / Rebuild / Fetch Rating
     xml-cii-adapted-preview-dryrun.js  →  dryrun-core (parse, nodeRows, weightRanking)
        → preview-rating-authority.js (DTXR staged index, ~0.8 s)  → bore-wall-authority.js
     Fetch: notice at once, config saved by a Worker (core/config-save-worker.js, fetch-worker-commit.js), rating journal (config-store.js)
  Run → converters/xmltocii2019_runner.js → Python engine
Python engine (converters/scripts/)
  xml_to_cii2019*.py: parse XML → edges (from/to nodes) → ConversionModel
     {edges, bend_edges, rigid_edges, reducer_edges, sif_edges, restraints + edge_to_*_index maps}
  xml229_native_final_mass_binding.py: binds physical masses to RIGID owners (rules :827-856, :975-1044)
  serializer → CII 2019 text: fixed-width 13-char columns; CONTROL; ELEMENTS (15 lines per element,
     row 13 = pointers into auxiliary sections); auxiliary RIGID (weight as force, N = 10 × kg), BEND, REDUCERS (needs AlphaAngle), SIF, RESTRAINTS…
```
- **Rigid weight rules:** R-LT9 (the 109 mm element is the flange: 15 kg / 150 N once; the 19.1 mm span is NOT a flange). R-LT10 (unknown component weight = W_ref × L / L_ref: L < flange L + 6 mm → row 252 (109 mm, 15 kg) so 19.1 mm → 2.63 kg / 26.3 N **SUGGESTED**; else row 974 (368 mm, 47 kg); missing/NaN → REVIEW/null). Unknown is never written as a real 0 in the proof's status sidecar.
- **Known product bug (BM2 UI Run, every version):** `xml_to_cii2019_contracted_direction.py:660` raises "REDUCERS auxiliary edge has no PSI116 reducer component owner/AlphaAngle" because `_component_owner_node` (:521-525) picks the REDU **Endpoint 1** record (no AlphaAngle; the angle is on Endpoint 2). 7 of 9 BM2 reducers (/24704, /25788, /25852, /25916, /25980, /26044, /27546). Candidate fix pattern: v0.4 commit d40a6db (now pushed, branch fix/xml-cii-reducer-internal-edge-r1.4). Proposal: plans/cards/REDUCERS-R1-PROPOSAL.md.

### 2.3 XCU (lane B) and TopoFix (lane A)
- XCU reads Input XML strictly (`uxml/UxmlInputXmlSchemaMapper.js`, "S3" solved positions), applies **edit-op envelopes** (`uxml-edit-ops/v1`, e.g. `ALIAS_COINCIDENT_NODE`) to the **original bytes** (`uxml/UxmlEditOpsPatchBack.js`): every proof row's exact DELTA must agree with S3's to-from within 0.001 mm, otherwise a named refusal. B3 (`UxmlInputXmlSameRunCoincidence.js`) is a read-only same-run coincidence proof.
- TopoFix (`converters/psi116_topology_resolver/*`) finds and fixes topology on the UXML hub; A3 hardened the hub-shape refusals.

---

## 3. How work is run (the Oracle method)

- **Roles:** Owner decides; Oracle (this Claude) plans, writes step cards, gates every RETURN, never merges without the Owner's word per PR. Coders are ChatGPT chats driven through the built-in browser pane.
- **Card flow:** card file in `plans/cards/` → copy to `G:\My Drive\Handoffs\<STEP>\` (check size + SHA-256 on the Drive copy) → chat message "Drive Handoffs/<folder>/: <name> <size> B sha256 <h>. Card text (¶ = new line): …" (lines joined by " ¶ "). Never type '@'; never type backslash-u escapes (write <U+00A0>). Verify delivery: card appears once, composer empty. A RETURN counts only if it starts "RETURN · STEP X" AFTER the card text.
- **Gate (every RETURN):** verify head / forward-only / scope on GitHub → Oracle repro (own probe) → L2 runner agent → fresh reviewer agent when it could pass. **PASS = reviewer ≥ 92 and every category ≥ 17 and runner SUPPORTS.** At most 3 agents at once; perf timing needs a quiet machine (one Chrome; DOM.disable before timing).
- **Owner rules:** ask before any NEW card, new chat, download outside Drive Handoffs, install, push, post; never merge product PRs without the Owner's word for that PR; never retry a permission-classifier denial; Owner files stay local/Drive; no merge to main without a prototype the Owner runs (Owner may override, as for #36).
- **State files:** `state/lanes.md` (table at top + dated log; open Owner questions numbered), `TOPOFIX-STORY.md` (timeline), `plans/*-WBS.md`, `plans/cards/*`, gate reports in `scratch/run-*` and `scratch/rev-*`. 20-min check prompt: `state/check-prompt.txt` (+ v3 deltas in the cron prompt).

---

## 4. Next 5 planned actions per project

### A — TopoFix (idle)
1. Ask the Owner whether to run the lane A prototype (tools/lane-a-prototype.ps1) on main 787e9914 first.
2. Draft card A4 (fix A3 limits L1-L5: document/restore the 25 refusal codes, test the AttributeError remap, named error for wrong-typed free labels, bounded handling of pathological JSON, scope the remap away from engine analysis).
3. On Owner OK: stage A4 in Drive, send to coder-a6, new branch off main, new PR.
4. Gate A4 (Oracle repro with rev-a3 probes + runner + fresh reviewer).
5. Plan lane A's integration into the XML→CII app (continuity after RIGID split — rigid aim 2) with the Owner.

### B — XML Compare (idle)
1. Ask the Owner whether to send the small follow-up card (0.001 mm boundary test, row-0 near-sentinel test, FROM_/TO_ case-sensitivity, units, misleading test name/comment, refusal order).
2. Draft + stage + send it to coder-b8 on a new branch off main e09c81d1.
3. Gate it (probe12r4b.mjs, writer12_argv.mjs, attacks12r5.mjs + runner + reviewer).
4. Write the lane B "edit path" summary that lane C will consume (op envelope, refusals, patch-back guarantees).
5. Close receipts issue #239 for steps 1.2 and B3 (comment only on Owner OK).

### C — CII→CII transfer (not started)
1. Ask the Owner to open lane C and approve a new chat for coder-c1.
2. Coordinate with ciifr M10 (node map) / M11 (authorized mapped transfer) to avoid duplicate work (COORDINATION_REQUIRED).
3. Send onboarding + C0 DISCOVER_FIRST (read-only: list the CII sections/fields to transfer, e.g. node names, PRESSURE1; how enriched XML carries them).
4. Gate C0 facts; design C1 (map source↔target nodes/elements) as a prototype on a real pair of CIIs.
5. C2: edit via lane B's path and export the target CII; Owner prototype run before any merge.

### PERF — 3D_Converters_v0.5a (1.R15 REPAIR; 1.R16 drafted)
1. Ask the Owner: send 1.R16 (K1 headless evidence probe, K2 one new test failure + W3/J1/J4a/b/e/f mutants, K3 rating cost if cheap) — and whether to accept the perf lane after it (round 16; Fetch 0.04 s, first Build ~3 s, Rebuild ~2.3 s, long task < 200 ms are met).
2. On OK: stage PERF-1.R16 in Drive, send to perf-coder-2.
3. Gate 1.R16 with the run-perf-r15 tools (headless exits 0 with timings + converter error + engine sha; suite 0 new failures vs 1759/1637/117; mutants RED).
4. Decide the REDUCERS bug route with the Owner (REDUCERS-R1-PROPOSAL.md: repo v0.5a vs v0.4, coder, check d40a6db first).
5. Owner prototype (1.P how-to) on real inputs before any merge of the perf branch.

### RIGID — 3D_Converters PR #406 (S2-R2 REPAIR; S2-R3 drafted)
1. Ask the Owner: send S2-R3 (Q1 synthetic test must DERIVE R-LT9/R-LT10/HELD/REVIEW; Q2 no CI step passes by skipping under an R9 name; Q3 position-rule mutants X2/X3/X9; Q4 pin the 3.2 mm merge window X1).
2. On OK: stage RIGID-S2-R3 in Drive, send to rigid-coder-3.
3. Gate S2-R3 (run-s2r2 tools + R9 env vars; local exact-R9 CII must stay 9bd0f4ae; reviewer ≥ 92).
4. Then S3 = independent actual-byte release proof (route accepted 6 Nov); release stays BLOCKED until S3 passes and the Owner decides.
5. Rigid aim 2 (continuity after split, with lane A) and the REDUCERS owner bug touch the same converter: sequence them with the Owner so two coders never edit xml_to_cii2019* at once.

---

## 5. Open Owner questions at handover
- Send S2-R3 (rigid)? Send 1.R16 (perf) and accept perf after it?
- REDUCERS product bug: route (repo, coder, new chat?).
- A4 card (lane A)? Lane B follow-up card? Open lane C?

## 6. Where everything is
- Oracle state: `D:\CodeD\oracle` → Drive copy `G:\My Drive\Handoffs\ORACLE-STATE-20261109\` (see NEW-PC-SETUP.md).
- Per-project pages: HANDOVER-A / -B / -C / -PERF / -RIGID.md (this folder).
- Pushed backup branches (9 Nov): see HANDOVER-PLAN-20261109.md section "Pushed" and lanes.md 9 Nov entry.
