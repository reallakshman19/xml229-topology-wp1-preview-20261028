# PERF Task 1: GLRD Step 4 Preview result publication · step-by-step plan

**Template:** [STEP-BY-STEP-WBS-TEMPLATE.md](../STEP-BY-STEP-WBS-TEMPLATE.md) · **Status:** PLAN, nothing sent · 4 Nov 2026
**Repo:** `reallakshman19/3D_Converters_v0.5a` · start `2b2939051bcd1f24e01163996f890168cfb311d9` (PR #10 head; base PR #2 `814157b1`)
**Chats:**
- perf-planner: https://chatgpt.com/c/6aeaa603-bd6c-83ed-88c6-e6ea2b1dc11f (browser tab `seed`). It wrote the Task 1 brief, a four-task sequence, and the IR timing advice.
- perf-coder: https://chatgpt.com/c/6aeae4fd-1d50-83eb-80b3-0c1749769cdf (browser tab `tab-1`). It did Steps 2–7 as patches.

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
