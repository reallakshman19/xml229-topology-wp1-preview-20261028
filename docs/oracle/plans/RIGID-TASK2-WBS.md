# RIGID Task 2: XML → CII 2019 element RIGID mass · step-by-step plan

**Template:** [STEP-BY-STEP-WBS-TEMPLATE.md](../STEP-BY-STEP-WBS-TEMPLATE.md) · **Status:** PLAN, nothing sent · 4 Nov 2026
**Repo:** `reallakshman19/3D_Converters_v0.5a` · baseline `52c20ee8c53bcfe278ad33ccdc3f9e4dfb1f6aa3` (converter blob `a55539cf…`)
**Chats:**
- rigid-planner: <CHAT_URL_REDACTED> (browser tab `tab-2`). It reviewed PR #8, proved the pointer chain at the baseline, and wrote the task brief.
- rigid-coder: <CHAT_URL_REDACTED> (browser tab `tab-3`). It produced a fix kit and a local-agent test plan.

## Where it stands (observed 4 Nov)

**Proven (rigid-planner, from source at the baseline):**
- `_build_rigid_indices` gives a 1-based pointer.
- Row 13 field 2 of each ELEMENTS record carries that pointer.
- `_rigid_weight_for_edge` returns `to_node.weight`, multiplied by the weight scale.

**rigid-coder's kit:**
- 9 allocator unit tests pass and 4 exporter integration tests are **skipped**. Evidence level L1.
- The kit is a download link only, not applied anywhere.
- The coder found its own defect: `xml_to_cii2019_patched.py::_build_conversion_model` loses mass held on pruned short-element nodes. Its repro resolves `[0,0]` where it should be `[8,16]`.

**rigid-coder's kit breaks the brief (blocking):**
- It splits a component's mass **by length by default** ("apportioned by their actual lengths"). The brief allows that only when uniform distribution is **explicitly authorised** (rule A); unknown cases must **block** (rule E).
- It keeps missing/zero mass as **zero**. The brief says "Do not use a default of zero for a missing allocation".
- rigid-planner predicted exactly this: a low-thinking agent "may otherwise implement a simple length-ratio formula everywhere".

**Repo facts:**
- The baseline `52c20ee8` is the merge of PR #5 into PR #1's branch, made after PR #1 had already merged to main (`a3b3d7e3`). PRs #3, #4 and #5 are therefore **not on main**.
- Open DRAFT **PR #8** (`0db938fa`, same branch) overlaps: duplicate split-mass ownership, and both converter paths.

## Preserved rules (repeat in every card)

- No change to the CII format: row 1 is FROM/TO, row 13 field 2 is the 1-based RIGID pointer, 0 means none.
- Keep the pointer generation, weight scale and number formatting.
- Keep the RIGID classification rules.
- Never invent an allocation rule; unknown → block with a diagnostic.
- No default of zero for a missing allocation.
- Do not edit source fixtures in place.
- No push or merge; no Owner/private data.

## WBS from here

| WBS | Step | Expected outcome | Tests / proof | Level | Actor | Depends on |
|---|---|---|---|---|---|---|
| **2.0** | DECIDE (Owner): allocation policy | Written answers: **(a)** which component families may use length split (rule A) or mass per length (rule B), and which are discrete (rule C, e.g. flanges); **(b)** where approved masses come from (XML Weight? weight master? engineer file?); **(c)** what happens to real models with no approved allocation yet: block, or warn and mark UNVERIFIED | — | — | Owner (rigid-planner can draft the options) | — |
| **2.0b** | DECIDE (Owner): landing and PR #8 | Where the fix lands. Main lacks PRs #3–#5, so the choice is retarget to main, or a new branch from `52c20ee8` as a draft PR. Also: is PR #8 superseded, merged first, or mined for tests? | — | — | Owner | — |
| **2.1** | Discover on a real model | On one public or benchmark XML, a census of the surviving RIGID elements: how many, how many components span more than one element, whether component identity is readable from the XML, how many duplicate weights there are, and how many are lost to short-element pruning. Counts only. | Runner runs the **baseline** converter and parses the CII | L2 | runner (needs Python) | — |
| **2.2** | Make the resolver follow policy | Kit revised: no default length split; each component follows its 2.0 rule; unknown, missing, negative, non-finite or contradictory mass is an explicit error (not zero). Tests A (2.865 / 12.135 → 28.65 / 121.35) and B (19.1 mm discrete → 150) both pass. | Allocator unit tests incl. A, B, F, G; a mutant where a default length split makes F go RED | L1 | rigid-coder | 2.0 |
| **2.3** | Fix pruned-node provenance in both entry points | The patched entry point and the base keep the mass source from pruned nodes. Also check `xml_to_cii2019_direction.py`, `…_runtime_custody.py` and any other `ConversionModel` builders. | The coder's provenance regression: RED before the fix, GREEN after (expected `[10.0, 20.0]`, no pruned node in ELEMENTS) | L1 | rigid-coder | 2.2 |
| **2.4** | Apply and run for real | Kit applied to a clean worktree at `52c20ee8`. All targeted tests pass with **0 skipped**. Existing converter tests (`test_xml_to_cii2019_patched_process`, `…_master_addon`, `…_actual_bm8`) are unchanged or have explained diffs. | unittest/pytest totals; `git diff --check` | L2 | runner | 2.3 |
| **2.5** | Real CII evidence | Generated `.cii` files are parsed back. For each weighted RIGID element: element ID → FROM/TO → length → rule → mass → row 13 pointer → RIGID record → emitted weight. Per-component conservation holds. Scale 1 vs 10 changes only the weights. Unaffected elements (bends, reducers, restraints) are byte-identical. | Parsed table; diff of non-RIGID sections | L2 | runner | 2.4 |
| **2.P** | **PROTOTYPE (Owner rule: no merge without it)** | GLRD BM2 (`3D_Converters@3377b7f4:Benchmarks/XML-CII-2019/revamped/GLRD-1000-PI-01 - BM2.xml`; 54 Rigid=2 nodes; 146 FLAN, 202 GASK, 70 VALV, 54 RIGID, 13 FBLI) is converted to CII. For each RIGID element the Owner sees the element, length, rule, mass and pointer, and checks the weights in CAESAR II. | Owner tries it; Oracle records the verdict | L4 | Owner | 2.5 |
| **2.6** | Report and draft PR | RETURN format; a new DRAFT PR on the branch chosen in 2.0b (Owner yes to push) | Report check | — | Oracle (+ Owner yes) | 2.5 |
| **2.7** | Independent review | Fresh reviewer, ≥92 and ≥17 per category, plus engineering sign-off on the 2.0 rules | Score | — | fresh IR + Owner | 2.6 |

## Gate rule for this task

- **No code card is sent until 2.0 is answered.** Without the policy, any resolver is a guess, and the current kit already guessed.
- 2.1 can run in parallel with 2.0, because it only reads.
- rigid-coder can only reach L1, so the runner brings each step to L2 before the next card.

## Prerequisites on this PC

- **Python 3 is not installed.** The runner needs it for the converter and the tests in 2.1, 2.4 and 2.5. Installing it is a download, so it needs Owner yes; use the official portable build, as with Node.
- pytest, if the existing converter tests need it: install into a venv inside the scratch folder.
- The kit and the provenance test are chat download links. Downloading them needs Owner yes.

## Ledger

- 4 Nov · RIGID-TASK2 STEP 2.0 · SENT to rigid-planner (tab-2). Verified: in the thread, composer empty, planner responding. Awaiting RETURN, then the Owner answers the decision sheet.
- 4 Nov · STEP 2.0 RETURN: decision sheet (families FLAN/VALV/INST/GASK = C/D, RIGID/OTHER = D; mass sources table; missing/defaulted zero = UNKNOWN; recommends option 1 = block final export, allow UNVERIFIED preview). GATE: **NEXT**; BLOCKED on Owner section E. Planner told to STOP.
- 4 Nov · rigid-coder (tab-3) told to HOLD: kit contradicts rules A/E and "no default zero"; no new kits, kit not to be applied; asked only for the list of files that would change.
- 4 Nov · 20-min check: rigid-coder acknowledged HOLD and listed the kit files (incl. `rigid_mass_assignment.py`, `tests/test_xml_to_cii2019_element_rigid_mass.py`, `xml_to_cii2019_element_rigid_mass.patch`). Not a RETURN; no gate.

- 4 Nov · **OWNER DECISION 2.0: accept rigid-planner's recommendation as the working policy** (changeable later):
  - FLAN/FBLI, VALV, INST, GASK = C (whole mass on one identified element) or D (approved split).
  - RIGID and other Rigid=2 = D only.
  - A/B (length split, mass per length) only with explicit physical justification.
  - Missing, invalid or defaulted zero = UNKNOWN.
  - No approved allocation → BLOCK the final CII export; a diagnostic preview marked UNVERIFIED is allowed.
- 4 Nov · Sending 2.1 (L0 census) → rigid-planner and 2.2 (resolver per policy) → rigid-coder.
- 4 Nov · STEP 2.1 RETURN (L0):
  - The 54 Rigid=2 nodes are all ComponentType RIGID, paired with FLAN (44), FBLI (5) and BRAN (5); every one has Weight=0.
  - 53 RIGID auxiliaries are projected. Node 3540 is pruned at 0 mm. Node 3380's edge points to a different-reference FLAN (/30497).
  - 33 nodes are removed by pruning.
  - Under the policy, 0 allocate automatically and 54/54 block.
  - **Oracle verified: the whole BM2 XML has 0 non-zero Weights.** Weights therefore enter later, via Weight Match / the enriched XML, so the prototype input must be the enriched XML (open question to the Owner).
  - GATE: **NEXT** (L0 met).
- 4 Nov · STEP 2.2 RETURN (L1): default length split removed; versioned allocation input bound to model and element SHA-256; blocks on UNKNOWN. 24/24 unit tests pass and the mutant goes RED. 4 exporter tests are left for L2. Revised kit ZIP is 35,070 B, SHA-256 `0e4ca49f…`. The coder can push. GATE: **NEXT to L2**, pending the Owner's route (push a branch, or download plus install Python).
- 4 Nov · OWNER: rigid route = **coder pushes a branch**. STEP 2.2b sent: branch `fix/xml-cii2019-element-rigid-mass-20261104` from `52c20ee8`.
- 4 Nov · STEP 2.2b RETURN: **BLOCKED**.
  - Kit verified (`0e4ca49f…`, 24/24); intended files are `xml_to_cii2019.py` (modify), `rigid_mass_assignment.py` (add) and `tests/test_xml_to_cii2019_element_rigid_mass.py` (add).
  - The coder's GitHub write interface could not transfer the content unchanged, so it created **no** branch or commit, rather than retype the code. That was correct.
  - GATE: STOP → Owner. The fallback is the download route plus Python.
- 4 Nov · OWNER "download + Python":
  - Kit downloaded via the browser, 35,070 B, SHA-256 **`0e4ca49f…` matches**. Stored in C:/Users/reall/tools/_downloads/rigid-kit-2.2.
  - Python 3.12.10 installed (python.org NuGet, SHA-512 verified) in C:/Users/reall/tools/python, on the user PATH.
  - Worktree `D:/CodeD/topofix-agents/rb-rigid` @52c20ee8: `git apply` of the kit patch is clean (3 files, +800/−21; new files byte-identical to the kit). The coder's installer was NOT run.
  - Runner (L2) launched.
- 4 Nov · RUNNER L2 on kit 2.2: **PARTIAL** → GATE: **FIX-UP needed**.
  - **Doesn't compile.** `xml_to_cii2019.py:1849` has a SyntaxError: a literal newline where `"\n"` belongs, in the `--rigid-manifest-out` write. As applied, the module can't be imported.
  - **With only that line fixed (scratch copy): 28/28 pass, 0 skipped**, including the 4 integration tests.
  - Existing tests match base, plus 2 new failures that are expected under the policy (no allocation input → `RigidMassResolutionError`): `test_xml_to_cii2019_patched_process::test_final_xml_enrichment_…` and `test_xml_to_cii_restraint_axis_lineno::…test_rigid_weight_and_material_code_emit…`. They need explicit allocation fixtures, not weakened assertions.
  - There is no UNVERIFIED preview mode; only `--rigid-manifest-only`, which emits no CII.
  - Owner "Yes, send fix-up". **FIX-UP 2.2 sent** to rigid-coder (verified in the thread). It covers:
    1. the syntax fix;
    2. versioned allocation fixtures for the 2 existing tests, plus "blocks without fixture" sibling tests;
    3. a `--rigid-preview-unverified` style preview, labelled UNVERIFIED (the default still blocks);
    4. a diagnostic that names the branch, FROM→TO and the source node.

    It returns one revised ZIP plus its SHA-256.
  - **Real GLRD BM2: base itself cannot convert the raw file** (`ValueError: Edge 1 received multiple restraints`, xml_to_cii2019.py:905). So the real-file block was not observed, which confirms the prototype input must be the app's enriched XML, not the raw BM2.
- 4 Nov · **OWNER, on the mass source:** component mass comes from the **weight masters**, matched on **bore + length + rating** for the component type taken from **DTXR / name**.
  - So the approved component mass = the weight-master value for the matched (type, bore, rating, length). The policy rule (C/D) then decides which surviving element(s) carry it.
  - The raw XML Weight=0 is expected; the weights enter through Weight Match. The prototype input should come through that path.
  - **OWNER, on empirical matches:** the empirical 60–100% matches are a **validation** of the master value, and a **fallback** only when the weight master has no entry (for example a non-standard value).
  - Working precedence for "approved mass":
    1. weight-master match (type from DTXR/name + bore + length + rating);
    2. empirical fallback (60–100%) only when there is no master entry, carried as source=EMPIRICAL with its confidence;
    3. otherwise UNKNOWN → block final export / UNVERIFIED preview.
  - A master value that fails empirical validation (outside ±50%) goes to review and is not auto-approved. (This last point is the Oracle's reading; confirm with the Owner if it matters.)

## First card (sent 4 Nov) → rigid-planner, for 2.0

```
STEP 2.0 of RIGID-TASK2 — draft the allocation policy for the Owner          (step 1 of 9)
BASE: 52c20ee8c53bcfe278ad33ccdc3f9e4dfb1f6aa3 (read only)
WHY: the coder's kit splits every component's mass by length by default and keeps missing mass as zero. That breaks rules A and E of the brief. The Owner must set the policy before any more code is written.
DO:
1. List the component families that carry RIGID weight in this converter (flange, valve, …), each with the XML fields that identify it.
2. For each family, propose rule A, B, C or D, with one sentence of engineering reason, and mark which need the Owner's or an engineer's decision.
3. List the possible sources of approved mass (XML Weight, weight master, engineer file) and what each can and cannot prove.
4. Give 2–3 options for real models that have no approved allocation yet (block / warn + UNVERIFIED / …), your suggestion first.
EXPECTED OUTCOME: a one-page decision sheet the Owner can answer in a few lines.
TESTS: each family claim cites file:line at 52c20ee8.
EVIDENCE LEVEL NEEDED: L0.
DO NOT: write code; decide for the Owner.
RETURN: RETURN format. Then STOP.
```
- 4 Nov · STAND-IN DECISION: ±50% rule ADOPTED. A weight-master mass outside ±50% of the empirical (60-100%) validation is flagged REVIEW, never auto-approved into the final CII; it may appear in the UNVERIFIED preview. Reason: a gap that large usually means a wrong type/bore/rating match, and review costs time, never a wrong weight. The Owner can override.
- 4 Nov · 2.2-FIX ZIP picked up (landed as .tmp in Downloads; SHA-256 6816cda8… MATCH), moved to D:/CodeD/downloads/rigid-kit-2.2fix/. ORACLE L2 on clean 52c20ee8 (converter blob a55539cf MATCH): git apply --check OK; 5 files (3 modified, 2 new; patched.py untouched as promised); py_compile 5/5 OK; new suite 33/33 OK (27 policy/preview + 6 exporter integration); both legacy files 24/24 pass (the 2 earlier policy reds now use explicit D allocations + no-policy siblings); git diff --check clean. Wider xml_to_cii tests: head 44 pass / 8 fail, base 42 pass / 8 fail, SAME 8 failures (actual_bm8 x2, master_addon x5, inputxml_sidecar x1) = pre-existing, 0 new. UNVERIFIED preview flag + manifest present. Kept as LOCAL-ONLY commit 803b0eb in rb-rigid2 (never pushed). GATE 2.2: NEXT -> 2.3.
- Note: the kit takes mass only from an engineer-approved allocation JSON. The Owner's mass source (weight master by type+bore+length+rating, empirical fallback tagged EMPIRICAL, ±50% REVIEW) is NOT built yet -> new step 2.3b after 2.3.
- 4 Nov · STAND-IN DECISION: STEP 2.3 (pruned-node provenance in every ConversionModel builder; incremental patch on 52c20ee8+2.2-FIX; regression RED->GREEN in both entry points; per-builder mutants) SENT to rigid-coder, verified, working. New delivery rule in the card: files to Google Drive Handoffs/RIGID-2.3/ with SHA-256. 2.3b (Owner mass source) announced, not sent.
- 4 Nov · STEP 2.3 RETURN via Google Drive Handoffs/RIGID-2.3 (10 files; every SHA-256 MATCH; patch 5e7e2178). ORACLE L2 on 803b0eb: apply OK, only xml_to_cii2019_patched.py changed (+29/-1) + new test; compile OK; tests/ 35/35 (33 + 2 provenance); xml_to_cii suite 44 pass / same 8 pre-existing fails, 0 new; diff --check clean. REAL mutant (fix reverted) -> provenance test ERROR (RED); restored -> GREEN. Builder table: base xml_to_cii2019.py:970 already OK; direction/runtime_custody delegate to patched. GATE 2.3: NEXT. Local-only commit in rb-rigid2. Next: 2.3b Owner mass source.
- 4 Nov · STAND-IN DECISION: STEP 2.3b-A (DISCOVER_FIRST, read-only: weight-master sources, DTXR/name flow, existing empirical logic, proposed lookup + provenance fields MASTER/EMPIRICAL/APPROVED_ALLOCATION/UNKNOWN with OK/REVIEW/UNKNOWN) SENT to rigid-coder; report to Drive Handoffs/RIGID-2.3b-A. Reason: matching keys (bore units, rating forms, length bands) must be seen before code.
- 4 Nov · STEP 2.3b-A RETURN (read-only): report via Drive Handoffs/RIGID-2.3b-A (SHA-256 96a3bcac… MATCH, copied to D:/CodeD/downloads/rigid-2.3b-A). Master = docs/Masters/wtValveweights.json (1,595 rows; 354 no length, 93 nonpositive, 246 blank DN, 563 RF/RTJ vs BW differ); the Python exporter loads NO master today. DTXR flow via master_addon.py:223-230/562-595 + dtxr-resolver.js; XmlNode lacks DTXR/bore/rating -> must capture before pruning. Empirical estimator exists (empirical-weight-estimator.js:88-212), no length input; 60-100% = candidate-match confidence, ±50% = mass deviation (separate fields). GATE 2.3b-A: NEXT.
- 4 Nov · STAND-IN DECISIONS on the 4 open questions:
  (1) RF/RTJ vs BW: explicit connection evidence required, else REVIEW. Reason: masses differ in 563 rows; guessing gives wrong weights.
  (2) Length match: within ±0.5 mm is a master match; wider is a REVIEW candidate. Reason: rounding only, no silent near-match.
  (3) Master found but no empirical estimate available: status OK with flag VALIDATION_UNAVAILABLE (NOT REVIEW). Reason: Owner said master first, empirical is validation and fallback; missing validation must not demote the master. (Coder suggested REVIEW; overruled.)
  (4) Type unsupported by both master and empirical, or manual mass: UNKNOWN (blocks final CII). Reason: Owner rule, missing = UNKNOWN.
  Master rows with missing length or nonpositive weight count as "no entry".
- 4 Nov · OWNER DECISION (supersedes stand-in decision 2): length tolerance = ±6 mm. A master row whose length is within ±6 mm of the source length is a master match; outside ±6 mm is not a match (fall to empirical / UNKNOWN per rules). STAND-IN detail: if several rows fall within ±6 mm, take the nearest length; if the nearest candidates tie and their weights differ, status REVIEW (MASTER_AMBIGUOUS). Record matched length delta in provenance (lengthDeltaMm).
- NEXT (not sent yet): STEP 2.3b-B implement (capture DTXR/bore/rating/length per source node before pruning; master lookup with normalisation incl. 150#/CL150/150 LB; empirical validation + fallback EMPIRICAL; provenance fields; feeds C/D allocation; tests + mutants; files via Drive Handoffs/RIGID-2.3b-B).
- 4 Nov · STAND-IN: STEP 2.3b-B (implement mass source; card D:/CodeD/oracle/plans/cards/RIGID-2.3b-B.md, incl. Owner +-6 mm) SENT to rigid-coder (seed 6aeafc82), verified working. Files due in Drive Handoffs/RIGID-2.3b-B.
- 4 Nov · STEP 2.3b-B RETURN via Drive Handoffs/RIGID-2.3b-B (9 files, every SHA-256 MATCH; copied to D:/CodeD/downloads/rigid-2.3b-B). Coder: L1 complete. STAND-IN: L2 runner launched on new worktree rb-rigid2b from 6020415 (apply, compile, tests base vs head, decision probes incl. 6.0/6.1 mm, real mutants, local-only commit if OK).
- 4/5 Nov · ORACLE L2 2.3b-B (rb-rigid2b @6020415 + patch, staged, NOT committed): apply OK, 12 files +988/-19, compile 11/11; weight-source 31/31; earlier rigid suites unchanged; wider set same pre-existing fails. All decision probes PASS (6.0 match/6.1 miss, tie, ratings, bores, CONNECTION_UNPROVEN, ±50.0/50.1, VALIDATION_UNAVAILABLE, UNKNOWN final block + UNVERIFIED preview, provenance after pruning). Mutants 9/9 RED. Real master 1595/412 excluded/1183 eligible (34 TYPE_UNRESOLVED, 1144 OK, 5 MASS_DEVIATION). 2 NEW fails = non-hermetic integration tests (expect UNKNOWN, real data gives EMPIRICAL/OK). GATE 2.3b-B: FIX-UP. STAND-IN decisions: accept A1-only empirical port (A2 deferred); accept master miss + no connection -> REVIEW CONNECTION_UNPROVEN. FIX-UP card sent to rigid-coder (hermetic tests + 1 real-master wiring test), files to Drive Handoffs/RIGID-2.3b-B-FIX.
- 5 Nov · 2.3b-B-FIX RETURN (Drive, 4 files MATCH; test-only, 1 file +39/-1, file SHA aeb8e249 as claimed). ORACLE L2 in rb-rigid2b: 77/77 (integration 11 incl. 2 hermetic + real-master test, weight-source 31, rigid policy 33, provenance 2) on Python 3.14.5; diff --check clean. GATE 2.3b-B: PASS. Local-only commit a0eb2f1 (never push). NEXT: 2.4 per plan.
- 5 Nov · STAND-IN: STEPS 2.4 (all rigid + converter tests at a0eb2f1 vs 52c20ee8, 0 skipped) and 2.5 (GLRD BM2 -> CII, parsed RIGID table, conservation, scale 1 vs 10, non-RIGID byte-identical) runner launched in new worktree rb-rigid24. NEXT: 2.P Owner prototype in CAESAR II.
- 5 Nov · RUNNER 2.4 @a0eb2f1 (rb-rigid24, base rb-rigid24-base 52c20ee8): diff 12 files +2206/-31, diff --check clean; targeted rigid 101 tests 0 skipped 0 failed; converter suites same failing names base/head (master_addon 5, actual_bm8 2 = Owner file absent, sidecar 1 = existing gate), only +2 new passes. GATE 2.4: PASS. 2.5: NOT_RECEIVED - BM2 file is at 3D_Converters@3377b7f4 (plan), but commit 3377b7f4 is not in the local clone (needs git fetch). Proxy GLRD-1000-PI-01.xml: final refuses UNKNOWN (65 elements, no allocation), preview crashes on existing REDUCERS path, base exporter fails on multi-restraint edge. --weight-scale exists. NEXT: fetch 3377b7f4, extract BM2 to the worktree (not committed), rerun 2.5.
- 5 Nov · STAND-IN: 2.5 rerun launched in rb-rigid24: read-only git fetch for 3377b7f4, BM2 extracted to scratch only (never committed), final + preview, scale 1 vs 10, base comparison.
- 5 Nov · 2.5 rerun: NOT_RECEIVED again. Read-only fetch OK, but 3377b7f4 is on no remote ref (fetch by SHA: no remote ref; no BM2 / XML-CII-2019/revamped path on any ref; only the original GLRD-1000-PI-01.xml exists). No local copy found on D:\ or the Drive. Original not substituted. BLOCKED on OWNER: supply the BM2 xml, or push the commit/branch that holds it.
- 5 Nov · R-LT2 smoke on public GLRD-1000-PI-01.xml (Owner-side agent run; ORACLE spot-check L2): multi-restraint ValueError identical head/base (pre-existing); contracted_direction REDUCERS ValueError identical at base and at head in preview mode (pre-existing; head final mode refuses UNKNOWN first); direction.py final refuses UNKNOWN RIGID mass (65 elements, new fail-closed policy); preview writes 308 elements / 49 restraints with UNVERIFIED banner (Oracle confirmed). R-LT2 PASS (no new crash). R-LT3..7 BLOCKED on BM2.
- 5 Nov · OWNER (programme map, PROGRAMME-MAP.md): rigid has TWO goals: (1) when a RIGID (Flange+Valve+Flange) is split into flange/valve/flange and blinds, coordinate data and continuity are lost; lane A (TopoFix continuity) must integrate with the XML->CII app once done; (2) RIGID weight errors, Owner case "19mm=150N which is for 109mm flange" = wrong-size weight. ADDED acceptance case R-LT8: no RIGID/flange element may take a weight from a different size; find the 19 mm -> 150 N case and show it corrected or refused. ORACLE check on the public GLRD-1000-PI-01.xml at a0eb2f1 preview: 65 RIGID all UNKNOWN (RATING/LENGTH/BORE_UNRESOLVED 65, TYPE_UNRESOLVED 61), so the case is not checkable on the public file; it needs BM2. Goal (1) has no WBS step yet: OPEN (which step, after lane A).

- 2026-11-05 11:02Z · Owner "ok proceed" on #109: Oracle merge denied again by the permission classifier (Merge Without Review); not worked around; #109 unchanged (draft, fb701f2b, green). Owner "Yes, start both": rigid 2.5 runner (R-LT3..R-LT8 on BM2) and perf P-LT3..P-LT7 runner launched in background.

- 2026-11-05 11:05Z · Rigid 2.5 runner stopped on dirty worktrees (only R-LT2 smoke leftovers: tracked .pyc + test_out.cii, 3 untracked smoke files). STAND-IN: backed up to scratch rigid24-leftovers, restored both worktrees (status clean, a0eb2f1 / 52c20ee); runner resumed with PYTHONDONTWRITEBYTECODE=1 and outputs to scratch only. Inputs: all 6 SHA-256 MATCH.

- 2026-11-05 11:07Z Â· RUNNER 2.5 on BM2 @a0eb2f1 vs 52c20ee: PARTIAL. All 6 input SHA MATCH; LL/piping-class/weights xlsx/material map NOT consumed (no CLI args; head reads repo docs/Masters/wtValveweights.json, 1595 rows). BM2 has no mass in the Python path (all 1196 Weights 0, 0 DTXR; STF staged JSON changes nothing). R-LT3 PASS (final refuses UNKNOWN 53 with named codes). R-LT4 PARTIAL (53 RIGID, pointers 1..53, manifest 53/53, weights UNVERIFIED; conservation untestable). R-LT5 PARTIAL (1 vs 10 byte-identical, no numeric weight). R-LT6 PASS (non-RIGID byte-identical). R-LT7 PASS (146/202/70/54/13, Rigid=2 54; CII 53 RIGID, node 3540 pruned). R-LT8 PARTIAL: Owner case located = 6 FLAN on 2in lines, endpoint OD 60.3 vs 26.7 (19 mm), 109 mm long; master row 252 DN50 CL900 109 mm 15 kg (~147 N). Head refuses them UNKNOWN on BM2; base 0.0. Synthetic probe: master match never crosses sizes, +-6 mm holds, BUT empirical A1 fallback ignores length: DN50 19 mm RF -> OK EMPIRICAL 13.8 kg (gap). 2.4 suites 98/98 OK. CSV in scratch run-rigid25. NEXT: real masses need the app Weight Match enriched XML (config builder running); Owner policy Q15.
- 2026-11-05 11:22Z Â· Owner "Yes, send card" (Q15): STEP 2.3c (empirical fallback OK only if element length within +-6 mm of a reference length for same type/DN/rating: repo dimension table, else master rows of that size; else REVIEW LENGTH_UNVERIFIED) SENT to rigid-coder (Drive Handoffs/RIGID-2.3c/, 3832 B, sha256 fe15ac35158dca41e5ebf12cc9584c9f3005dae7d6fae51ef37cb44aaf192e2b); delivered, working. Files due in Handoffs/RIGID-2.3c/.

- 2026-11-05 11:55Z Â· CONFIG BUILT via the app's own Import Masters (app 386b739a, default mapping): downloads/GLRD-INPUTS/derived/bm2-workbench-config.json 8,433,327 B sha256 766da8fa5711c373e309e975f6c1bb8fedc7caf4b835d9dbc9909af3de876bd8; bm2-enriched.xml (standalone Run runXmlCii2019Workflow + createEnrichedXml) 695,061 B sha256 9608d9ad8735fa1eea0202b215801e4154c04286e581dabdd34aca17016563f8; README.md. Masters: piping class 10,699 rows, weights 1,595, material map 383; LINE LIST UNUSABLE (default = first sheet 'Coversheet', 15 rows; the popup's sheet selector has no handler). Enriched: 268/994 nodes weighted (VALV 35/35, FLAN 95/95, RIGID 8/10), DTXR on 803.
- APP DEFECTS FOUND (3D_Converters_v0.5a @386b739a): (D1) the 'XML->CII Workflow' popup cannot open: legacy-adapter.js imported under two ?v= tags (ModelConvertersTab.js:6 vs xml-cii-workflow-bridge.js:9) -> two module instances, popup sees no bridge; (D2) popup 'Workbook Sheet' dropdown unbound (only the retired shell binds it, legacy-adapter.js:8263) -> line list always Coversheet; (D3) all 86 nodes with OD 168.3 (6in) carry BoreMm 200.000 (DN200, expected DN150) - not investigated.
- OWNER CASE CONFIRMED IN APP OUTPUT (ORACLE read of bm2-enriched.xml): FLAN =134234934/24692 (P4110003/B2), endpoint 1 OD 60.3 Weight 8, endpoint 2 OD 26.7 (3/4in, '19 mm') Weight 15 (= 2in CL900 master row, ~147 N). Same pattern on 5 more flanges (25776/25840/25904/25968/26032) and on 60.3 vs 48.3 flanges. The wrong-size weight is produced by the app's JS Weight Match, upstream of the Python exporter that 2.3c fixes.
- 2026-11-05 12:00Z · STEP 2.3c RETURN (chat + Drive Handoffs/RIGID-2.3c, 9 files, all SHA-256 MATCH, copied to downloads/rigid-2.3c). Coder L1: 3 files +249/-10, 113/113, 3/3 mutants RED; Owner 19 mm case -> REVIEW LENGTH_UNVERIFIED, emitted mass null; reference order DIMENSION_TABLE (vendor/create-pipe-data-db.js:62-81 B16.10) -> MASTER_ROWS -> NONE. ORACLE L2 runner launched (new worktree rb-rigid23c = a0eb2f1 + patch) incl. 2.5 re-run on the app-built bm2-enriched.xml (real weights).

- 2026-11-05 12:10Z Â· RUNNER L2 2.3c: SUPPORTS (3 files +249/-10 exactly; targeted 101 -> 113, 0 fail 0 skip; wider suites same failing names; 10/10 own mutants RED; decision probes all as specified; B16.10 table = 1 usable row, Gate DN200 CL150 RF 292 / RTJ 305 / BW 419 mm). ORACLE REPRO (worktree or-rigid23c = a0eb2f1 + patch): Owner DN50 CL900 RF 19 mm -> REVIEW LENGTH_UNVERIFIED, mass none, ref 109 MASTER_ROWS; master hit 109 unchanged 15 kg; DN20 109 -> REVIEW (ref 77); 54/54 tests OK. GATE 2.3c: PASS. Local-only commit 2888219 on a0eb2f1 (NEVER push).
- 2.5 RE-RUN on app-built bm2-enriched.xml (real weights): PARTIAL, does not yet support 2.P. head == a0eb2f1 byte-identical: 144 RIGID / 130 components; REVIEW/MASTER 33 (CONNECTION_UNPROVEN), REVIEW/UNKNOWN 2, UNKNOWN 109 (TYPE_UNRESOLVED 109, SOURCE_LENGTH_CONFLICT 107); final refuses, preview all UNVERIFIED; non-RIGID byte-identical to base. The 2.3c branch is never reached on BM2. ROOT CAUSES (pre-existing, Python exporter side): (1) type text 'WELDING NECK FLANGE' does not match the weldneck pattern WELD\s*NECK -> all FLAN/RIGID TYPE_UNRESOLVED; (2) the app writes a different ElementLengthMm and Weight on each flange endpoint (93 FLAN) -> SOURCE_LENGTH_CONFLICT; (3) ConnectionType empty on every rigid-family node and 'FLGD' not recognised -> CONNECTION_UNPROVEN (35 valves); (4) data: OD 168.3 with BoreMm 200 (86), 114.3/400, 219.1/400, 88.9/50 (60), 26.7 and 48.3 with 50; 'BALL VALVE FLOAT RB' typed Full Bore; '...1500#' valves with Rating 900. BASE still emits the app's wrong-size weights on 28 RIGID elements (6 x 3/4in-end flanges at 15, 6 x 60.3/48.3 at 15, 6 x 88.9/BoreMm50 at 17, E403 29, E419 23.947, 8 x 6in tagged DN200). What-if E4 tagged DN200 610 mm RF: a0 OK EMPIRICAL 743.6 kg (wrong size), head REVIEW; as DN150 MASTER 365 kg. CSV: scratch run-rigid23c.
- 2026-11-05 15:33Z Â· Owner "Yes, all of it": STEP 2.3d (type text WELDING NECK, geometry length source, FLGD = flanged but REVIEW if RF/RTJ/BW changes mass, OD->DN check BORE_OD_CONFLICT / SIZE_CONFLICT) SENT to rigid-coder (Drive Handoffs/RIGID-2.3d/: card 4724 B sha d5ada74e79de0c12d0933790fe128070c3350e36cf6dcf5d56ff613b35c5a4b6 + bm2-enriched.xml 695061 B sha 9608d9ad...); delivered, working. QUEUED for rigid-coder after 2.3d: app Weight Match size fix (Q17, approved) in 3D_Converters_v0.5a.

- 2026-11-05 16:00Z Â· STEP 2.3d RETURN (Drive Handoffs/RIGID-2.3d: 15 files, all SHA-256 MATCH, copied to downloads/rigid-2.3d). Coder BM2 counts on bm2-enriched.xml: 144 RIGID, before REVIEW 35 / UNKNOWN 109 -> after REVIEW 144 (CONNECTION_UNPROVEN 116, BORE_OD_CONFLICT 15, SIZE_CONFLICT 13, MASTER_MISS 1); 0 numeric masses; final BLOCKED, preview UNVERIFIED. Type and length now resolve; RF vs RTJ evidence is the remaining blocker. L2 runner launched (new worktree rb-rigid23d = 2888219 + patch), incl. a check of whether the piping-class master carries flange facing.

- 2026-11-05 16:11Z Â· RUNNER L2 2.3d: SUPPORTS with conditions (3 files +118/-16 incl. new test file; targeted 91 -> 99, 0 fail/skip; converter suites same failing names; counts on bm2-enriched.xml match the coder; 0 numeric masses; preview CII byte-identical base/patched and scale 1/10). Mutants 14/17 RED; survivors M14 (OD tolerance 0.5 -> 40) and M17 (OD_DN_UNRESOLVED removed) are real gaps (DN50 with OD 61/75 -> OK 15 kg), M8 masked. OD table: 12 match the cited CSV, 4 rounding diffs within 0.5, 13 not in the CSV. ORACLE REPRO: Owner 60.3/26.7 -> REVIEW SIZE_CONFLICT; OD168.3+200 -> REVIEW BORE_OD_CONFLICT; clean DN50 109 RF -> OK 15 kg; OD 61.0 -> REVIEW OD_DN_UNRESOLVED. GATE 2.3d: FIX-UP. FINDINGS: CONNECTION_UNPROVEN 116 is caused by the master's empty BW column (131 WN rows have no BW mass; valve row 857 BW blank), not a real mass difference; piping class master has NO facing/end column (PMSTable: Piping Class, Size, SCH, Wall thickness, Material_Name, PMSMat_*, Rating, Corrosion); data: 7 '1500#' valves with Rating 900, 26 'FLOAT RB' typed Full Bore. Card RIGID-2.3e.md drafted (F1-F3 fix-up + Owner ruling R1 on empty BW + R2 rating cross-check + R3 reduced bore); OWNER Q21.

- 2026-11-05 17:03Z Â· OWNER RULING ("Yes, all four"): blank/0 BW mass on a weldneck/flange row or a FLGD valve row = BW not applicable, RF/RTJ mass applies, flagged FACING_ASSUMED_RF_RTJ, with RATING_CONFLICT and reduced-bore checks. STEP 2.3e SENT, sha 2b901574...; delivered.

- 2026-11-05 20:2xZ · STEP 2.3e RETURN (Drive, 18 files SHA MATCH, downloads/rigid-2.3e). Coder BM2: OK 82 FACING_ASSUMED_RF_RTJ (82 x 15 kg), REVIEW 62 (CONNECTION_UNPROVEN 26, RATING_CONFLICT 8, BORE_OD_CONFLICT 15, SIZE_CONFLICT 13); final still blocked. Gate pending.

- 2026-11-05 20:51Z Â· RUNNER L2 2.3e: SUPPORTS with conditions. 3 files +272/-40 (new guardrail tests); targeted 101 -> 116, 0 fail/skip; converter suites same failing names; F1-F3, R1-R3 as specified; 22/25 mutants RED (X4 equivalent, X7 FLGD token boundary unpinned, X17 RB guard DN code-only). BM2: OK 82 / REVIEW 62 matches coder; all 82 numeric = Weldneck DN50 CL900, OD 60.3/60.3, geometry 109 mm vs CA8 row 252 (delta <= 0.0086 mm), 15 kg, FACING_ASSUMED_RF_RTJ; none on 19 mm or mismatched OD. C1 DOUBLE COUNT: 82 records = 68 components; 14 split flange components carry 15 kg on both CII elements (1230 kg naive vs 1020 kg real). Final export still refused (no versioned allocation input). ORACLE CHECK: 82 rows, 68 components, 14 with 2 records, sum 1230, max delta 0.0086 mm. GATE 2.3e: PASS for its scope. Local commits a65e443 (2.3d) + 7fa1123 (2.3e) on 2888219 in or-rigid23c (NEVER push). Cards drafted: RIGID-2.3f.md (C1 double count + X7 + X17; OWNER Q26) and RIGID-APP-WM1.md (Owner-approved Q17; held until perf 1.R9 bore source passes, because both touch app bore logic).

- 2026-11-06 07:29Z Â· Owner "Yes, all three": 2.3f approved; staged in Drive (sha 7bf5fb0e...); send pending ChatGPT sign-in (handover section 9.2).

- 2026-11-06 13:54Z · 2.3f GATE PASS -> local commit e026012 (or-rigid23c). Evidence: runner scratch run-rigid23f\RUNNER-RIGID-2.3f.md; return D:\CodeD\downloads\rigid-2.3f\ (16/16 sums). Notes N1-N3 in state/lanes.md.
