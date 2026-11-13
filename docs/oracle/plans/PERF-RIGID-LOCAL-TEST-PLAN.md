# Perf Task 1 + Rigid Task 2 · Local test-run plan (Oracle, 5 Nov)

Everything below runs on this PC in new worktrees. Nothing is pushed or posted. Owner files stay local; outside this PC only counts, hashes and EQUAL/DIFFERENT are reported. Each run writes a table to `oracle-docs\` (case, expected, actual, PASS/FAIL).

Tools: Node `C:\Users\reall\tools\node`, Git `C:\Users\reall\tools\git\cmd`, Python `C:\Python314\python.exe` (unittest, PYTHONUTF8=1), Chrome 156 `C:\Program Files\Google\Chrome\Application\chrome.exe` (pass `--chromium` or set `CHROME_PATH`).

Inputs needed from the Owner, in Drive `Handoffs\GLRD-INPUTS\`. They are copied to `D:\CodeD\downloads\glrd-inputs\` with SHA-256:
- `GLRD-1000-PI-01 - BM2.xml`, used by both tasks.
- `STF_2026Nov03-0839_managed_stage.json`, plus the config, linelist, piping-class, weight and material-map files for the same job. These are for perf only.

## Perf Task 1 (Step 4 Preview publication) · branch head after 1.R6-FIX

| ID | Test | Expected | Needs inputs? | Status |
|---|---|---|---|---|
| P-LT1 | Full `tests/*.test.mjs` at the final head vs base `b99c0eb1`, `--test-concurrency=4` | Same 117 failing names, 0 new; new tests pass | no | runnable now (last run at 3e4b3b11: 1727/1605/117, 0 new) |
| P-LT2 | `node --check` on both browser probes | exit 0 | no | runnable now (60012c05: both 0) |
| P-LT3 | Wrapper probe `glrd_issue9_real_workbench_v7_wrapper_probe.mjs` in Chrome: Build, idle, Build, Rebuild, Fetch Rating | PASS; envelope absent after every action; rating equals the in-memory publication | yes | blocked |
| P-LT4 | Containment probe `glrd_issue9_cache_containment_browser.mjs` in Chrome | PASS; `-dtxr` and `v8-rating-policy` absent; stale entry cleaned, never restored | yes | blocked; waits for 1.R6-FIX |
| P-LT5 | Enriched XML from the probe vs the same-job reference (826,478 B, `d12b2fc3…`) | EQUAL, but only if the job is identical (same input hashes); otherwise NOT_COMPARABLE with the reason | yes | blocked |
| P-LT6 | Timing: probe `--label baseline` at PR #10 head `2b293905` vs `--label optimized` at the final head, 3 runs each, same inputs | Report the median per action. No pass mark is set in the WBS; the Owner judges in 1.P. | yes | blocked |
| P-LT7 | localStorage dump after P-LT3 and P-LT4 | No envelope or `-dtxr` keys; list every key name, never values | yes | blocked |

Gate: P-LT1 to P-LT5 and P-LT7 green means 1.R6 PASS and the 1.P Owner prototype can start. P-LT6 is evidence for the Owner, not a gate.

## Rigid Task 2 (rigid mass source) · local commit a0eb2f1 (never pushed)

| ID | Test | Expected | Needs inputs? | Status |
|---|---|---|---|---|
| R-LT1 | The 2.4 rigid suites (101 tests, 0 skipped) plus converter suites at a0eb2f1 vs 52c20ee8 | Same failing names | no | PASS 5 Nov; rerun only if the code changes |
| R-LT2 | Smoke on the public original `Benchmarks/XML to CII 2019/GLRD-1000-PI-01.xml`: final + preview at head and base | Known so far: final refuses UNKNOWN (65 elements); preview crashes on the existing REDUCERS path; base fails on a multi-restraint edge. The task is to classify each as new or pre-existing. | no | runnable now |
| R-LT3 | BM2 to CII, final mode | Refuses only with named codes (UNKNOWN/REVIEW counts), or writes CII | yes | blocked |
| R-LT4 | BM2 to CII, `--rigid-preview-unverified`; parse the .cii back; per-RIGID table: element, FROM/TO, length, rule C/D, source/status, mass, lengthDeltaMm (±6 mm, nearest row), row-13 pointer, emitted weight | 54 RIGID elements tabulated; per-component mass conserved | yes | blocked |
| R-LT5 | Scale 1 vs `--weight-scale 10`, diff the CII files | Only weight fields differ | yes | blocked |
| R-LT6 | Head vs base on BM2: non-RIGID sections (bends, reducers, restraints, flanges, valves) | Byte-identical | yes | blocked |
| R-LT7 | Counts vs the WBS (146 FLAN, 202 GASK, 70 VALV, 54 RIGID, 13 FBLI) | EQUAL | yes | blocked |

Gate: R-LT3 to R-LT7 green means 2.5 PASS, and the Owner then checks weights in CAESAR II (2.P). If R-LT2 shows a NEW crash at head, that is a FIX-UP before 2.5.

## Order once the inputs arrive (about 30–40 min total)
1. Copy the inputs and hash them.
2. Run R-LT3 to R-LT7.
3. Once 1.R6-FIX returns, run P-LT1 to P-LT5 and P-LT7, then P-LT6.

Runnable now, without inputs: P-LT1, P-LT2 and R-LT2.

| R-LT8 | Owner falsifier: wrong-size weight. On BM2 (and the public file if resolvable), list every RIGID/flange element with its length, bore, master row and weight; the 19 mm -> 150 N (109 mm flange) case must be corrected or refused, and no element may take a weight from a different bore or size | No cross-size weight; the Owner case resolved or refused with a named code | yes (BM2) | blocked. On the public file all 65 are UNKNOWN (unresolved bore/rating/length) |
