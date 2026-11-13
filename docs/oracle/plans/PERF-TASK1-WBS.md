# PERF Task 1: GLRD Step 4 Preview result publication · step-by-step plan

**Template:** [STEP-BY-STEP-WBS-TEMPLATE.md](../STEP-BY-STEP-WBS-TEMPLATE.md) · **Status:** PLAN, nothing sent · 4 Nov 2026
**Repo:** `reallakshman19/3D_Converters_v0.5a` · start `2b2939051bcd1f24e01163996f890168cfb311d9` (PR #10 head; base PR #2 `814157b1`)
**Chats:**
- perf-planner: <CHAT_URL_REDACTED> (browser tab `seed`). It wrote the Task 1 brief, a four-task sequence, and the IR timing advice.
- perf-coder: <CHAT_URL_REDACTED> (browser tab `tab-1`). It did Steps 2–7 as patches.

## Where it stands (observed 4 Nov)

| Original step | What exists | Evidence level |
|---|---|---|
| 1 Read | Call-flow note in the chat | L0 |
| 2+3 Callback and v7 wrapper | Cumulative patch, chat download link only | **L1** (mocked harness) |
| 4 Generation guard | Incremental patch, chat link only | L1 |
| 5 Fail-closed | Incremental patch, link only; it also edits `preview-rating-snapshot.js` and 2 existing tests | L1 |
| 6 Storage failures | Incremental patch, link only; it adds `xml-cii-adapted-state.js` and a new test file | L1 |
| 7 Tests A–F | Patch plus test file. The coder says it ran on "a reduced legacy-renderer fixture" | L1 |
| Local agent (pasted back) | Correctly BLOCKED: no patch is in any repo, and `onPreviewCommitted` is absent from all history | — |

**Gap:** every step from 2 on passed at L1 only. Nothing has been applied to a real checkout, so the whole chain is unverified.

## Preserved rules (repeat in every card)

- Do not change any engineering calculation. That covers bore/wall authority, material and rating rules, weight ranking, the piping-class resolver, and XML/CII conversion.
- Do not touch Pyodide, PR #2 indexing, or PR #6 code.
- No push to main, no merge, no approvals.
- No Owner/private data in chats or on GitHub.
- Anything not run is NOT_RUN.

## WBS from here

| WBS | Step | Expected outcome | Tests / proof | Level | Actor | Depends on |
|---|---|---|---|---|---|---|
| **1.R1** | Bring the patches into the repo | All 5 patches (2+3, 4, 5, 6, 7) apply in order to a clean worktree at `2b293905`, as one local branch with one commit per step | `git apply --check` per patch, then `git diff --stat`, then `node --check` on changed files | L2 | Oracle runner (files from perf-coder) | Owner yes to download the 5 patches |
| **1.R2** | Run the real tests | Tests A–F plus the storage tests run against the **production** renderer and wrapper (not a reduced fixture). The existing `xml-cii-preview-cache-v7`, weight-match snapshot and DTXR manual-protection suites stay green. | `node --test` with pass/total per file; every failure attributed to a step | L2 | runner | 1.R1 |
| **1.R3** | Repair what L2 shows | One FIX-UP card per failing step, listing exact failures with file:line. The coder fixes them in a patch on top of the branch, and the runner re-runs 1.R2. | Same as 1.R2, all green | L1→L2 | perf-coder + runner | 1.R2 (only if red) |
| **1.R4** | Check other bridge readers | `xml-cii-adapted-preview-dryrun.js:13` and the non-v7 `xml-cii-adapted-preview-diagnostics-audit.js:101` still read `xml-cii-pv-cache-v8-dtxr`. Either they still work, or they are migrated, with a test. | Tests named per reader | L2 | perf-coder + runner | 1.R2 |
| **1.R5** | DECIDE (Owner) | Confirm the coder's Step 5 choice: the optional v7 envelope is still **written** but never **restored**. Keep it or drop it. | — | — | Owner | 1.R2 |
| **1.R6** | Browser checks | `glrd_issue9_cache_containment_browser.mjs` and `glrd_issue9_real_workbench_v7_wrapper_probe.mjs` run in Chromium on their fixtures. Compare the UI-downloaded enriched XML to the same-job reference (30 branches, 826,478 bytes, `d12b2fc3…`) **only if the job is identical**. | Probe output plus byte/hash comparison, or a NOT_RUN reason | L3 | runner (Chromium needed) | 1.R2–1.R4 |
| **1.P** | **PROTOTYPE (Owner rule: no merge without it)** | The Owner runs Step 4 Preview in the browser on the real inputs: `3D_Converters@3377b7f4:Benchmarks/XML-CII-2019/revamped/GLRD-1000-PI-01 - BM2.xml` (31 branches, 1,196 nodes) with `STF_2026Nov03-0839_managed_stage.json` (86 branches, 716 DTXR). Build, Rebuild and Fetch Rating as per DTXR all work. The downloaded enriched XML equals the same-job reference (826,478 B, `d12b2fc3…`) when the job is identical. | Owner tries it; Oracle records the verdict | L4 | Owner | 1.R6 |
| **1.R7** | Report and draft PR | READY FOR REVIEW or BLOCKED report in the template's RETURN format. The branch is pushed as a **new DRAFT PR** based on PR #10's branch (Owner yes to push). | Report check | — | Oracle (+ Owner yes) | 1.R6 |
| **1.R8** | Independent review (IR Stage 2) | A fresh reviewer scores the exact head (≥92, ≥17 per category). Per the planner's advice, IR **Stage 1 can start now**, blind, in parallel. | Score | — | fresh IR | 1.R7 |
| 1.D1–D3 | Planner's Tasks 2–4 (stale-rating protection, PR #2 cleanup, profiling) | **DEFERRED**: no card until 1.R8 passes and the Owner picks | — | — | — | 1.R8 |

## Gate rule for this task

perf-coder has no repo, so it can only ever reach L1. **No new step card goes to perf-coder until the runner has brought the previous step to L2.** That is the rule the sample run broke at Step 3.

## Prerequisites on this PC

- Git, Node 22 and gh are present.
- **Chromium** (for 1.R6): `npx playwright install chromium` in the worktree. That's a download, so it needs Owner yes.
- **GLRD fixtures** (for 1.R6): if they are Owner-private, report counts and EQUAL/DIFFERENT only.

## Ledger

- 4 Nov · PERF-TASK1 STEP 1.R1 · SENT to perf-coder (tab-1). Verified: in the thread, composer empty, coder responding. Awaiting RETURN.
- 4 Nov · STEP 1.R1 RETURN: 5 patches + SHA-256 (ZIP 19,489 B, `be779efa…`); coder CAN push via its GitHub tools. GATE: **NEXT**. Coder told to HOLD until STEP 1.R1b. Open (Owner): (a) download the ZIP for the runner, or (b) coder pushes the 5 patches as commits on a new branch from `2b293905`.

- 4 Nov · **OWNER DECISION: route (b).** perf-coder pushes the 5 patches unchanged as 5 commits on a new branch from `2b293905`; no PR, no merge. Sending STEP 1.R1b.
- 4 Nov · STEP 1.R1b RETURN: PARTIAL.
  - Branch `fix/glrd-preview-direct-handoff-20261104` holds Step 2+3 `8766f7d5` and Step 4 `f95d2e57`, the tip (confirmed via gh).
  - **Step 5 does not apply** to the real `preview-rating-snapshot.js`: the hunk expects 2 blank lines where the real file has 1. That shows the patches were built against reconstructed sources, not the real file. Steps 6–7 were not attempted.
  - GATE: **FIX-UP needed** (regenerate Steps 5–7 against the real branch tip) after the runner checks Steps 2–4 at L2. Runner launched on `f95d2e57`.
- 4 Nov · Runner @`f95d2e57`: PARTIAL.
  - Wiring is sound and there's no runtime regression.
  - One stale assertion (cache-v7 test :107).
  - Bridge readers are left in snapshot.js:7, cache-v7.js:8, diagnostics-audit.js:101 and dryrun.js:13.
  - FIX-UP sent.
- 4 Nov · STEP 1.R1b-FIX RETURN (L2 application):
  - `2102543a` assertion fix.
  - `1f8db7ac` Step 5.
  - `97cb583d` Step 6.
  - `cabd271c` Step 7: 9 tests on the production modules.
  - 8 files changed, +518/−133. dryrun and diagnostics-audit are untouched.
  - The coder claims no runtime results.
  - GATE: pending the runner at `cabd271c` (launched).
- 4 Nov · RUNNER L2 @`cabd271c`: **PARTIAL**.
  - Syntax OK on 9 files.
  - 442 test files run at the tip vs 440 at base: identical except the 2 new files (direct-publication 9/9, storage-failure 5/5). **0 new failures.** Pre-existing reds are unchanged.
  - The Step 7 tests import the production modules (direct-publication.test.mjs:6–13) and all reach real assertions.
  - Mutant (b), re-enabling persisted-row restore: **RED** (cache-v7 and storage-failure). Good.
  - **Mutant (a), removing the generation checks (renderer.js:257, 259, 421, together): stays GREEN.** Test E does not exercise the Step 4 guard; something earlier (renderer :241 or the v7 wrapper) masks it.
  - GATE: 1.R1b → NEXT on application. Opens **1.R3 (repair what L2 shows)**: a test-only card so that Test E actually fails when the generation guard is removed.

## First card (sent 4 Nov)

This one isn't for perf-coder. The Oracle asks it for the 5 patch files:

```
STEP 1.R1 of PERF-TASK1 — hand over the patches          (step 1 of 8)
BASE: none (no code change)
WHY: Steps 2–7 passed only in an isolated harness. Before anything else they must be applied to a real checkout of 2b2939051bcd1f24e01163996f890168cfb311d9 and run there.
DO:
1. List every patch you produced, in apply order (Step 2+3, Step 4, Step 5, Step 6, Step 7), with file name, size and SHA-256.
2. Give a download link for each, or one ZIP with all five plus a SHA256SUMS file.
3. State whether you can push a branch to GitHub yourself (yes/no). Do not push now.
EXPECTED OUTCOME: five patch files with hashes, in order.
TESTS: none (the Oracle's runner applies them).
EVIDENCE LEVEL NEEDED: L0.
DO NOT: change any patch content; start new code.
RETURN: RETURN format (items 1–7). Then STOP and wait.
```
- 4 Nov · STAND-IN DECISION: STEP 1.R3 (test-only; make Test E fail when the renderer.js:257/259/421 generation guard is removed; each check alone reported) SENT to perf-coder, verified in thread, responding. Reason: the guard has no failing test, so it could silently regress; test-only means no product risk.
- 4 Nov · STEP 1.R3 RETURN: test-only commit 9cd54ce0 (+145, direct-publication test). Mask = v7 wrapper renderer-v7.js:152 rejects the stale generation before the legacy renderer. 3 new tests; L1 mutants: each of :257/:259/:421 alone RED, all three RED. Full suites NOT_RUN by coder. STAND-IN: L2 runner launched (real mutants a-d).
- 4 Nov · RUNNER L2 @9cd54ce0: SUPPORTS. Test-only (1 file). direct-publication 12/12, storage-failure 5/5, cache-v7 6/6. REAL mutants: (a) all three -> 3 RED; :257, :259, :421 alone -> each RED on its own test. All 339 files: 117 pre-existing fails, identical names, 0 new. GATE 1.R3: NEXT. STAND-IN: STEP 1.R4 (bridge readers dryrun.js:13 + diagnostics-audit.js:101; writer table, KEEP/MIGRATE/RETIRE per reader with a test) SENT to perf-coder.
- 4 Nov · STEP 1.R4 RETURN: head b99c0eb1 (4 commits, 7 files, PRODUCTION changes): dryrun + non-v7 diagnostics RETIRE old-key cleanup; B31.3 wall-update + wall-audit MIGRATE to generation-bound handoff (diagnostics-audit-v7.js:21-41); new retirement test (5). Nobody writes the old key. Coder ran nothing at L2. STAND-IN: L2 runner launched (full suite by name, B31.3 tests, 2 real mutants, old-key grep).
- 4 Nov · RUNNER L2 @b99c0eb1: SUPPORTS. 7 files (prod: wall-audit, wall-update, diagnostics-audit-v7 handoff getter, diagnostics-audit, dryrun; tests 2). Named tests 32/32. B31.3 + mode-a 9/10, the 1 fail identical at base. Full suite head 1725/1603/117 vs base 1720/1598/117, identical failing names, 0 new. Mutants: (a) old-key fallback RED, (b1) generation check RED, (b2) clear-on-start SURVIVES (redundant behind build flag + generation compare). Old key: only constants + v7 cleanup + tests; production never reads/writes it. GATE 1.R4: NEXT -> 1.R5 (keep/drop v7 envelope).
- 5 Nov · STAND-IN DECISION 1.R5: DROP the optional v7 envelope WRITE (written, never restored = dead storage and a possibly stale second copy; the generation-bound handoff is the sole authority). Keep the legacy-key cleanup. Card sent to perf-coder (tab-1 6aeae4fd), working: remove the write; stop and report if any reader exists; tests for no-write and stale-envelope-ignored+cleaned; real mutant. NEXT after it: 1.R6 browser checks (Chromium install = Owner), then 1.P Owner prototype.
- 5 Nov · STEP 1.R5 RETURN: head 3e4b3b11 (1 fwd commit on b99c0eb1, 4 files +100/-63): envelope write removed from cache-v7.js, in-memory rating publication kept; no production readers of the key; tests no-write + stale-envelope cleanup + Build/Rebuild regression; coder L1 only (mutant re-enabled setItem RED at source level). STAND-IN: L2 runner launched (rb-perf-r5 vs rb-perf-r5-base; key grep, named + full suite, 3 real mutants).
- 5 Nov · RUNNER L2 @3e4b3b11: SUPPORTS. 4 files +100/-63 as claimed; renderer guards, R4 handoff, Weight Match/PR340/rating-consumer untouched. Production: no setItem/getItem on the envelope key, only removeItem in cleanup/discard. Targeted 30/30; full suite head 1727/1605/117 vs base 1725/1603/117, identical failing names, 0 new. Changed tests are stricter (no reads, no writes), current rating still asserted. Mutants (a) re-add write RED x3, (b) restore stale envelope RED x2, (c) drop cleanup RED x1. Notes: new Build/Rebuild test not itself shown to kill (a) (others do); browser probe tests/glrd_issue9_real_workbench_v7_wrapper_probe.mjs still expects an envelope -> must be updated or retired in 1.R6. GATE 1.R5: NEXT -> 1.R6 browser checks (needs Owner Chromium install).
- 5 Nov · OWNER: "Installed, send card". Found system Chrome 156 (C:\Program Files\Google\Chrome\Application\chrome.exe) + puppeteer Chrome builds; probes take --chromium. STEP 1.R6 coder part SENT to perf-coder (tab-1 6aeae4fd, card plans/cards/PERF-1.R6.md sha e8540930), working: update the stale v7 wrapper probe to assert envelope ABSENT, check containment probe, CHROME_PATH fallback, node --check. L3 probe RUN still BLOCKED on Owner inputs not found locally: GLRD BM2 xml, STF_2026Nov03-0839_managed_stage.json, config, linelist, piping-class, weight, material-map.
- 5 Nov · STEP 1.R6 (coder part) RETURN: head 60012c05 (1 fwd commit on 3e4b3b11; ORACLE verified FETCH_HEAD, diff = 1 test file +71/-4, no production change). Wrapper probe now asserts envelope ABSENT after initial Build, idle, manual Build, Rebuild, Fetch Rating; rating checked against direct in-memory publication; CHROME_PATH fallback. ORACLE node --check: both probes exit 0. FINDING: glrd_issue9_cache_containment_browser.mjs (unchanged) still expects the legacy xml-cii-pv-cache-v8-dtxr bridge to be WRITTEN after Build; production has no writer of that key since R4 (only constants + cleanup) -> second stale probe, will fail on a real run. GATE 1.R6 code: FIX-UP (containment probe). L3 probe run still BLOCKED on Owner GLRD inputs (Drive GLRD-INPUTS empty).
- 5 Nov · OWNER: "Yes, send fix-up". STEP 1.R6-FIX SENT to perf-coder (tab-1): containment probe asserts -dtxr and v8-rating-policy keys ABSENT, stale -dtxr cleaned and never restored, rating from in-memory publication, CHROME_PATH fallback; one file only.
- 5 Nov · STEP 1.R6-FIX RETURN: head 386b739a (1 fwd commit on 60012c05; ORACLE: FETCH_HEAD match, 1 test file +55/-17, node --check exit 0, no production change). Cache asserts correct: -dtxr + v8-rating-policy ABSENT after initial Build, idle, manual Build; both seeded stale beforehand; rating checked vs in-memory snapshot and DOM; CHROME_PATH fallback. BEYOND CARD (flag): probe now drives renderer-v7.js (was renderer.js; consistent with the wrapper probe and diagnostics-audit-v7), and the idle assertion is INVERTED: old "idle must NOT read the staged source", new "v7 wrapper MUST resolve the staged source at idle entry" (+ stale DOM rating cleared). Matches v7 code (:31-32, :161), but a source read on idle is a perf-relevant contract -> verify in P-LT4/P-LT6 timing and Owner 1.P. GATE 1.R6 code: NEXT (L3 run), note carried. L3 still BLOCKED on GLRD inputs.
- 5 Nov · LOCAL TESTS (Owner-side agent, report oracle-docs/perf-rigid-runnable-localtests-20261105.md): P-LT1 @386b739a 1727/1605/117 vs base b99c0eb1 1725/1603/117, identical failing names (consistent with Oracle R5 run; only non-suite .mjs probes changed since) PASS; P-LT2 node --check both 0 PASS (Oracle confirmed earlier). P-LT3..7 BLOCKED on GLRD inputs.

- 2026-11-05 11:02Z · Owner "ok proceed" on #109: Oracle merge denied again by the permission classifier (Merge Without Review); not worked around; #109 unchanged (draft, fb701f2b, green). Owner "Yes, start both": rigid 2.5 runner (R-LT3..R-LT8 on BM2) and perf P-LT3..P-LT7 runner launched in background.

- 2026-11-05 11:01Z · RUNNER P-LT3..P-LT7 @386b739a: NOT_RUN (not a failure). Both probes need a workbench config JSON (/__glrd/config.json: linelist/pipingClass/weight masterRows, material mapRows, overrides); stage JSON has none (86 BRANCH objects, no config keys). Probe defects found: (1) CDP race 'Execution context was destroyed' 100% (wait+retry fixes, scratch only); (2) containment probe hard-codes 30 branches (BM2 has 31); (3) neither probe writes enriched XML, so P-LT5 NOT_COMPARABLE (reference d12b2fc3 not local). Idle microbench ({} config): no regression, idle source-resolve also at baseline 2b293905 (renderer-v7.js:192), cost dominated by SHA-256 authority ~25-33 ms. localStorage 0 keys after idle. NEXT: config JSON (Owner export or Oracle builds via the app's Import Masters) + 1.R7 probe fix-up card (needs Owner yes).

- 2026-11-05 11:07Z Â· Owner "Yes, both": STEP 1.R7 (test-only probe fix-up: CDP wait+retry, branch count from job, enriched-XML capture --out-xml) SENT to perf-coder (Drive Handoffs/PERF-1.R7, 3204 B, sha256 7e07bfcb4482362db29d65533f346ac04b330b1560e8f30c0f11044bd66f8b56), delivered, working. Config builder launched: BM2 workbench config via the app's own Import Masters (default mapping) -> downloads/GLRD-INPUTS/derived/, plus Weight Match enriched XML if available.
- 2026-11-05 11:40Z Â· STEP 1.R7 RETURN (chat): head bc29605c. ORACLE: FETCH_HEAD match, 1 fwd commit on 386b739a, 2 test files only (+102/-11, containment +64/-? , wrapper +49), no production change; node --check both exit 0; CDP retry helper present in both (:112); hard-coded 30 gone; --out-xml capture added (:290, :324). GATE 1.R7 code: NEXT (static OK). L3 run P-LT3..P-LT7 waits on the BM2 config (builder running). Oracle worktree or-perf-r7 @bc29605c.

- 2026-11-05 11:55Z Â· CONFIG BUILT via the app's own Import Masters (app 386b739a, default mapping): downloads/GLRD-INPUTS/derived/bm2-workbench-config.json 8,433,327 B sha256 766da8fa5711c373e309e975f6c1bb8fedc7caf4b835d9dbc9909af3de876bd8; bm2-enriched.xml (standalone Run runXmlCii2019Workflow + createEnrichedXml) 695,061 B sha256 9608d9ad8735fa1eea0202b215801e4154c04286e581dabdd34aca17016563f8; README.md. Masters: piping class 10,699 rows, weights 1,595, material map 383; LINE LIST UNUSABLE (default = first sheet 'Coversheet', 15 rows; the popup's sheet selector has no handler). Enriched: 268/994 nodes weighted (VALV 35/35, FLAN 95/95, RIGID 8/10), DTXR on 803.
- APP DEFECTS FOUND (3D_Converters_v0.5a @386b739a): (D1) the 'XML->CII Workflow' popup cannot open: legacy-adapter.js imported under two ?v= tags (ModelConvertersTab.js:6 vs xml-cii-workflow-bridge.js:9) -> two module instances, popup sees no bridge; (D2) popup 'Workbook Sheet' dropdown unbound (only the retired shell binds it, legacy-adapter.js:8263) -> line list always Coversheet; (D3) all 86 nodes with OD 168.3 (6in) carry BoreMm 200.000 (DN200, expected DN150) - not investigated.
- OWNER CASE CONFIRMED IN APP OUTPUT (ORACLE read of bm2-enriched.xml): FLAN =134234934/24692 (P4110003/B2), endpoint 1 OD 60.3 Weight 8, endpoint 2 OD 26.7 (3/4in, '19 mm') Weight 15 (= 2in CL900 master row, ~147 N). Same pattern on 5 more flanges (25776/25840/25904/25968/26032) and on 60.3 vs 48.3 flanges. The wrong-size weight is produced by the app's JS Weight Match, upstream of the Python exporter that 2.3c fixes.
- 2026-11-05 15:13Z Â· RUNNER L3 P-LT3..P-LT7 @bc29605c (real BM2 + Oracle-built config): SUPPORTS 1.P (browser part). P-LT3 wrapper PASS (31 rows; envelope absent after Build/idle/Build/Rebuild/Fetch Rating; rating = in-memory publication). P-LT4 containment PASS (derived branch count 31; -dtxr and v8-rating-policy seeded stale, cleaned, never restored; idle fail-closed). P-LT5 Run on pristine config byte-EQUAL to derived/bm2-enriched.xml (sha 9608d9ad, ORACLE confirmed); committed --out-xml differs only because Fetch Rating mutates the shared config before Run (10 Rating + 2 Weight nodes, explained). P-LT7 0 localStorage keys at head (baseline 2b293905 leaves 2). P-LT6 medians head vs 2b293905: Build -14.9%, idle -4.9%, manual Build -13.5%, Rebuild -5.7%, Fetch Rating -8.8% (timing via scratch-instrumented probe copies). ORACLE spot-check: both report status PASS, XML hash equal. GATE 1.R7/L3: PASS. NEXT: 1.P Owner prototype (Step 4 Preview on BM2 in the app). Note: the probe's Run-after-Fetch-Rating reuse of a mutated config is a probe nit, not a product issue.
- 2026-11-05 15:33Z Â· Owner "Yes, all of it": STEP 1.R8 (D1 legacy-adapter single module specifier so the workflow popup opens; D2 popup Workbook Sheet handler; D3 BoreMm root cause, fix only code) SENT to perf-coder (Drive Handoffs/PERF-1.R8/, 3164 B, sha 7e57b3f4bf4c071eb89421a22b51415117b27efbb308c3606da02af3bb62b7e7); delivered, working. 1.P how-to written: oracle-docs/PERF-1P-HOWTO.md (blocked until 1.R8 passes: the popup is the only UI route to Step 4 Preview).

- 2026-11-05 16:00Z Â· STEP 1.R8 RETURN (chat): head d58f0706. Coder: legacy-adapter import URLs aligned, popup/shell share one sheet-selection function, OD->DN 4/4; NOT RUN: full node suite, real popup click, real BM2 workbook, BoreMm comparison. L2/L3 runner launched (suite, real Chromium popup + Linelist sheet + BoreMm diff on BM2).

- 2026-11-05 16:48Z · RUNNER L2/L3 1.R8 @d58f0706: PARTIAL. D1 popup opens from a real click with non-null bridge (bc29605c: no overlay) and Step 4 is reachable through the UI (Build Preview 5.9 s, 31 branches). D2 Linelist re-read works (16 rows; lineNo, pipingClass, material, bore, P1, T1-T3 mapped; rating not). D3 NO EFFECT: enrichment-run-parity.js:489/:212/:221 setBranchNodeFacts overwrites per-node BoreMm with the branch sizeMm (likely preview-renderer.js:55 _stagedBranchBoreMm); Run output with old config byte-identical (9608d9ad), 6in still 200. Suite 1732/1609/118: +1 = new xlsx-based test cannot load (no node_modules), not a code failure. Probes PASS. NEW: real popup Build leaves localStorage xml-cii-pv-cache-v5 (probe path 0 keys): popup may not use the v7 path; Linelist now feeding changes MaterialName to 'DSS' on 265 nodes, MaterialCode lost on 114, process values on 8 branches. Outputs scratch run-perf-r8 (config-r8 cd892ab9..., enriched-r8 922efb9d...). GATE 1.R8: FIX-UP. Card PERF-1.R9.md drafted; OWNER Q24.

- 2026-11-05 17:03Z Â· STEP 1.R9 SENT (Owner "Yes, all four"), sha 5c93de30...; delivered.

- 2026-11-05 20:40Z · STEP 1.R9 RETURN (chat): head 072846562cd7. Coder NOT RUN: full suite, real BM2 Chrome workflow, enriched-XML comparison, node --check. Gate pending (after A closure and rigid 2.3e gates, to stay under the usage limit).

- 2026-11-06 07:41Z Â· RUNNER L2/L3 1.R9 @07284656: PARTIAL. F1 FIXED (Run + popup: BoreMm follows OD; 168.3 -> 150 x86, 114.3 -> 100 x23, 219.1 -> 200, 88.9 -> 80 x90; 173 nodes changed; B6 150 mm). F2 FIXED (popup uses v7 wrapper; no xml-cii-pv-cache-* write; v5 key came from the legacy popup renderer). Suite 1739/1617/117 = old names, 0 new; sheet test runs. Probes PASS. BLOCKER: real popup path slow (medians: first visit 185 s, Build 21.9 s, idle 0.65 s, Build 20.7 s, Rebuild 19.8 s, Fetch Rating 191.9 s vs probe 3.4/0.25/5.0/5.3/5.6 s; legacy d58f0706 Build 1.4 s); hypothesis: ~9.7 MB localStorage config save (config-store.js:115/118, legacy-adapter.js:1584). Weights: 12 changed, second end of 6 reducing FLAN pairs (OD 48.3: 15 -> 13.037; OD 26.7: 15 -> 7.789) = app Weight Match still weights each endpoint of a reducing flange (APP-WM1 rule: SIZE_CONFLICT -> review). Material: line-list governs; 'DSS' not in material map; 77 LTCS + 74 DSS nodes carry code 338 (A790 duplex) -> Owner data question. GATE 1.R9: FIX-UP. Card PERF-1.R10.md drafted (OWNER Q29). APP-WM1 precondition (bore source fixed) now MET.

- 2026-11-06 14:50Z · 1.R10 @182b9acd GATE REPAIR (runner run-perf-r10\RUNNER-PERF-1.R10.md). Next: 1.R11 card drafted, Owner yes pending (Q33).
