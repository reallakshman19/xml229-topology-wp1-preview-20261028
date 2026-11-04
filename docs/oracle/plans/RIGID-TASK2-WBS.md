# RIGID Task 2: XML → CII 2019 element RIGID mass · step-by-step plan

**Template:** [STEP-BY-STEP-WBS-TEMPLATE.md](../STEP-BY-STEP-WBS-TEMPLATE.md) · **Status:** PLAN, nothing sent · 4 Nov 2026
**Repo:** `reallakshman19/3D_Converters_v0.5a` · baseline `52c20ee8c53bcfe278ad33ccdc3f9e4dfb1f6aa3` (converter blob `a55539cf…`)
**Chats:**
- rigid-planner: https://chatgpt.com/c/6aeaaf92-6ec4-83ed-bb69-fab4867f714d (browser tab `tab-2`). It reviewed PR #8, proved the pointer chain at the baseline, and wrote the task brief.
- rigid-coder: https://chatgpt.com/c/6aeafc82-3b1c-83ed-be24-c31321532193 (browser tab `tab-3`). It produced a fix kit and a local-agent test plan.

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
