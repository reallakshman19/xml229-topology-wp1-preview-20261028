# Topology short-element UI responsiveness — architectural repair candidate

## Symptom and source basis
Owner supplied a private 898,252-byte PSI116 XML with 41 branches and 1,654 Node occurrences. A local read-only owner grouping finds 130 GASK groups with source spans ≤6 mm. This is a screening count, **not** a certified count of eligible removals. The original source is not uploaded to this repository.

The prior workspace used a direct main-thread import of `engine.js`, which executes the Pyodide topology Python stage. Selected element drops invoke repeated full transactions and topology reanalysis; Python/WASM work on the UI thread can prevent paint, navigation and cancellation. The preview button synchronously rendered all candidates, without paginated navigation, making it hard to distinguish opening a preview from a blocked operation.

## Architecture
1. `topology-worker.mjs` owns the Pyodide engine strictly for PSI116 `topologyPreFinalOnly` jobs. It refuses native CII/Final, enriched output and Weight transfers. The shared engine and Python transaction are unchanged.
2. `topology-worker-client.mjs` creates one dedicated, disposable module Worker per mounted topology workspace. It correlates request IDs, rejects worker crash/timeout, terminates on cancel or source replacement, and rejects late responses. Unsupported Worker environments fail closed rather than falling back to main-thread Python.
3. `workspace-app.mjs` keeps the source-authoritative plan/short candidates unchanged. Clicking the short preview runs **no Python** and builds at most 24 candidate rows. Selected source IDs persist across pages. The preview is explicitly labeled as nonmutating and scrolls into view.
4. Apply still performs one selected owner per atomically validated transaction, checks its source identity and source SHA at each pass, builds tombstones, verifies lineage, reanalyzes, and publishes a new working revision only on success.
5. Per-pass progress is visible, **Cancel** remains enabled throughout a multi-pass batch, and cancellation terminates the worker and invalidates the workspace generation. Last validated XML/receipt remains available. All batch exits use `try/finally` to release busy state. A worker timeout (180 s per job), crash, or validation failure stops without publishing an unvalidated revision.

## Safety and unchanged policy
- No change to ≤6 mm removal qualification, straight two-port length evidence, allowed component types, bore/facing checks, 25 mm automatic closure policy, Weight custody, source references, restraints, or source-lineage gates.
- No new auto-approval: preview is nonmutating; explicit selection and Apply remain mandatory.
- A user's original file is never overwritten; no native CII, O1, Final, or Weight master is released.
- Sequential validated passes remain separate, not combined into an unchecked multi-owner operation.

## Qualification
Local Node worker-protocol tests: 4/4 PASS (result, cancellation, crash, pre-Final rejection). Browser/Pyodide end-to-end with the exact private original: **NOT_RUN** in this authoring environment. The repo's read-only PR validation workflow must run `tests/audit-browser.mjs` with pinned public FirstpassXML and real Chromium; independent review must qualify the actual result on the private input.

Suggested original-input acceptance: open preview without main-thread stall, confirm ≤24 visible rows and source-specific eligibility, select 1 GASK, apply and validate exact tombstones/retained changes/source SHA, then a multi-selection with intermediate progress and Cancel. Verify error/timeout preserves the previously validated working revision. No engineering acceptance is inferred from a responsive UI.
