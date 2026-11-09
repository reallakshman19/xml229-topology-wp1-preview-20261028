# Handover — PERF Task 1: XML→CII "4 Preview" speed · checkpoint 9 Nov 2026

LOCAL/DRIVE ONLY (contains chat URLs). Never publish.

| Item | Value |
|---|---|
| Repo | reallakshman19/3D_Converters_v0.5a (public) |
| Branch | fix/glrd-preview-direct-handoff-20261104 — no PR, never merge without Owner prototype + word |
| Head | b66b29c1bed0c52dd56e964035dca784a4e90379 (1.R15) · previous f03085f2 (1.R14) · suite base 11c8726c (1759 tests / 1637 pass / 117 fail) |
| Coder | perf-coder-2 — <CHAT_URL_REDACTED> (title "Performance Handoff Return"; may load blank: wait / one same-URL reload) |
| State | 1.R15 gated REPAIR 9 Nov 03:27Z. Coder idle. Card PERF-1.R16 DRAFTED, NOT SENT. |
| Invariants | Engine-path BM2 output 687,252 B sha 5cf2bfbe (R12 config); saved config 31,593 B sha 0b4905e8; Preview tables identical. |

## What is achieved (measured by Oracle runners, real Chrome, DOM.disable)
- Lost first-visit Build click FIXED (1.R14): first click builds 4/4; committed BM2 gate 3/3.
- Fetch notice 0.04 s (base 11.5 s); post-Fetch longest main-thread task 95-137 ms (< 200 ms).
- First Build ~3 s, Build after idle ~2.2 s, Rebuild ~2.3 s (workbench-config flow); whole dryrun 1.62-1.79 s; rating authority still ~0.8 s.
- Saved config bytes and Preview output unchanged.

## Still open (1.R15 runner, scratch\run-perf-r15\RUNNER-PERF-1.R15.md)
- Headless evidence script exits 1: the probe in tests/xml-cii-workflow-popup-browser.mjs:304-306 times out waiting for "Fetch configuration Worker message" (the product save itself works).
- 1 new suite failure: tests/xml-cii-preview-strict-line-authority.test.mjs (sandbox lacks dtxr-resolver.js); suite 1785/1662/118.
- Surviving mutants: W3, J1, J4a, J4b, J4e, J4f (legacy-adapter generation/retry wiring untested).
- BM2 UI Run fails in the converter (REDUCERS/AlphaAngle, Endpoint 1 owner) at every version — separate product bug, see plans/cards/REDUCERS-R1-PROPOSAL.md.

## Inputs (for runners)
- GLRD inputs: D:\CodeD\downloads\GLRD-INPUTS (public sources; MANIFEST.md) — workbench config GLRD-INPUTS\derived\bm2-workbench-config.json.
- R12 Oracle config: (session scratchpad) run-perf-r10\fx\config.json — copied into the Drive pack under inputs\.
- Runner tools to reuse: oracle\scratch\run-perf-r14\tools and run-perf-r15 (CDP harness with DOM.disable, longtask observer, gate scripts, CPU logger, mutants15.json).

## Next 5 actions
1. Ask the Owner: send PERF-1.R16 (plans/cards/PERF-1.R16.md) and accept the perf lane after it?
2. On OK: stage in Drive Handoffs/PERF-1.R16/ (verify sha), send to perf-coder-2.
3. Gate 1.R16: headless exits 0 printing 5 timings + converter error + engine sha; suite 0 new failures; W3/J1/J4* mutants RED.
4. Decide the REDUCERS bug route with the Owner (check v0.4 d40a6db fix pattern first).
5. Owner prototype run (1.P how-to) on real inputs before any merge.

## Card history
PERF-1.R13 … PERF-1.R16 in plans/cards; WBS + ledger plans/PERF-TASK1-WBS.md; runner reports scratch\run-perf-r13 / r14 / r15.
