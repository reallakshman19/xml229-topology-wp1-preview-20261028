# CODER-CHECKPOINT · UXML-BULK-SPEED · coder-b2

**Owner authorization:** UXML-BULK-SPEED, 1 Nov 2026, TopoFix only. **DRAFT / HOLD**; never merge. The Owner's real-file observation was approximately 12 seconds per item for 89 selected short drops, not an independently measured run in this branch.

## Exact custody

- Source base: TopoFix [PR #24](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/pull/24), head `c4a53e31e79a7acf5120194a3a440522c6cf407a`, branch `feat/uxml-short-drop-hub-20261101-a2`. It had independently passed 93. A separate coder-a2 is changing short PREVIEW logic; **do not touch** `uxml_operations_preview.py` or the preview portion of `workspace-app.mjs`.
- New branch `feat/uxml-bulk-speed-20261101-b2`, [DRAFT PR #26](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/pull/26), base exactly the #24 branch. **Check latest head on PR #26** and exact-head CI before any review. No XCU UXML code or file ownership changed; pinned XCU identity unchanged.
- Changed implementation only in `tabs/topology-workspace/short-bulk.mjs`, `tabs/topology-workspace/topology-worker-client.mjs`, `tabs/topology-workspace/topology-worker.mjs`, and `converters/xml-cii-2019-standalone/topology-integration.js`. Supporting test/CI/documentation files are additive or test-only. **No workspace-app.mjs edits**, UI preview changes, engine transaction/validation rules, CLOS/tolerances, source reader bytes, or policy widening.
- `converters/xml-cii-2019-standalone/engine.js` is unchanged, as are the Python resolver, transaction, adapter, edit-ops, lineage, and original source-preservation guards.

## Step 1: measured before optimization (real Chromium/Pyodide, synthetic)

Generate **336 synthetic component occurrences / 339 Node records**, verified PSI116 namespace, with one eligible three-mm GASK short owner and 333 simple distant PIPE filler occurrences. No Owner file, private hash, name, coordinates, or traces entered repo. The product is instrumented only when `topologyBulkSpeedProfile` is set by bulk apply; phase clocks are numerical, with no private source values.

**Baseline CI:** [run #41264751795](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/actions/runs/41264751795), instrument-only head `265168ae`, SUCCESS. Hub parity EQUAL, native committed, downloadable validated revision.

| Synthetic phase (ms) | Before | Optimized first warm item |
|---|---:|---:|
| Complete one-item bulk from Apply through UI publish | 2853.7 | 2697.3 |
| Worker round-trip | 2253.3 | 2136.4 |
| Pyodide resolve | 76.6 | 74.4 |
| Hub EQUAL parity calculation | 105.7 | 100.5 |
| Native transaction | 303.4 | 288.9 |
| Original source edit-ops / patch-back comparison | 1171.6 | 1108.2 |
| Full validation/recheck and findings | 508.1 | 481.4 |
| Verified hub reader load + mapping | 50.5 | 47.0 |
| Final UI refresh | 508.7 | 488.1 |

**Optimized first-item CI:** [run #41265051398](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/actions/runs/41265051398), intermediate head `ab573010`, SUCCESS. This is a ~5.5% single warm-item improvement. Do not extrapolate 12 seconds → 2.7 seconds for the Owner's private source; the 89-item warm Worker benefit is not contained in a single-item timing. The full source-bound patch compare (~1.1 seconds) is not skipped or sampled.

## Step 2: performance-only bounded implementation

- `runShortBulk`: explicitly opens/closes one scoped bulk lease (if engine client supports it), labels every hub item as `topologyBulkSession`, and retains original per-item transaction/validation/lineage/parity gates. One request, one Worker round trip, one EQUAL or fail, one new source SHA and revision, one checkpoint per successful item. Progress still increments per item without canvas re-render; final UI publication remains the existing single refresh at batch end.
- `topology-worker-client`: when a bulk lease is active, DO NOT recycle the otherwise warm Pyodide Worker after each eight completed jobs. After release, the next read-only evidence job may run on it and ordinary idle eight-job recycle resumes. Cancellation and crash still terminate the Worker and invalidate pending jobs.
- `topology-worker`: within a live Worker, cache the fully SHA-1-verified XCU reader module **only** for explicit bulk jobs. Every item re-hashes its changed XML bytes, re-reads those bytes through the verified immutable mapping function and re-runs full Python hub parity and patch-back comparison. Any reader verification failure clears the cache and fails closed; a new Worker verifies all pinned blobs again.
- `topology-integration.js`: after all native transaction, complete validation, signed lineage, pre-Final verification and post-fix findings/plan sidecars are collected into JS, remove only the *ephemeral* `/work/...` scratch directory for this pre-Final bulk item. Nothing is deleted in the ordinary, nonbulk or native Final paths. The Worker stays warm without retaining 89 sets of transient files.
- Timing telemetry records Worker source SHA computation, hub-reader load and map, Pyodide resolve, hub parity, transaction, patch comparison, validation/recheck, Worker round trip and UI end-of-batch publication. Timings are observational and never used as authorization.
- Deliberate holds: no merging 89 items into one transaction, no bypass of checking any item, no skip of parity/recheck, no hub gate/policy change. An item-2 DIFFERENT blocks the batch and disables working download, even though item 1's separately validated checkpoint remains internally available.

## Test and final return

- `tests/short-bulk.test.mjs`: 3/3 revisions and EQUAL checks; item-two DIFFERENT rejects with only one checkpoint; one begin/end lease; existing 89-headless and cancellation cases.
- `tests/topology-worker-client.test.mjs`: 12 consecutive jobs use ONE warm Worker during a bulk lease and post-bulk recheck recycles it; cancel invalidates a stale result.
- `tests/uxml-bulk-speed.browser.mjs`: baseline/after same generated 336-element source, real Chromium Worker/Pyodide, source/UXML parity, transaction, UI refresh.
- `tests/uxml-bulk-three.browser.mjs`: real synthetic 3-source-owner success (3 EQUAL, revision 3, download enabled); forced DIFFERENT on actual Worker output of item 2 (revision 1, no item 3, download disabled).
- `.github/workflows/uxml-bulk-speed.yml`: immutable external Pyodide WASM/stdlib SHA checks, unchanged pinned XCU reader, headless Chromium exact-head tests.
- Final status is **NOT accepted** until both specialized and full TopoFix CI at FINAL EXACT HEAD PASS and independent non-author reviewer meets 92/100 and >=17/category. Any unexecuted trial is NOT_RUN.

## Fresh-agent resume

Read latest `work_returned ORACLE-CYCLE-RECEIPT` on [TopoFix issue #12](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/issues/12) for exact final head, test counts, CI and honest NOT_RUN. Confirm source base still #24 head `c4a53e31`; do not rebase into coder-a2's live preview work without Owner authorization. The engineering release is HOLD; original Owner file trial, true 89-item timing and any native CII/Final are NOT_RUN. Next actor is Oracle, assigning independent review/Owner real-file acceptance.
