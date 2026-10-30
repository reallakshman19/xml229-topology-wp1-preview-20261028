# Manual Fix Queue — implementation and original-file acceptance

Status: DRAFT / HOLD. This is a reviewable experimental queue, not an engineering acceptance or production release.

## Architectural boundary
This branch is stacked on PR #10. The queue only applies manually previewed, explicitly approved port connections using the existing PSI116 `preview_connection`, `approved_connection`, `TransactionPolicy`, lineage and pre-Final replay. It does **not** infer intended connectivity from distance, autofill approvals, bypass the inclusive 25 mm automatic policy, or authorize Final, native CII, Weight or O1.

The UI inserts a Manual Fix Queue beside Second Pass. The owner chooses exact source + partner ports, requests a Python preview, inspects before/after and displacement, enters a design reference (10+ characters), confirms, and chooses **Add approved pair to queue**. No XML is changed upon enqueue.

A queue item stores:
- original working source SHA-256 and finding ID;
- both exact physical port keys, approved move/target keys and full move-key list;
- preview repair and before/after witness, exact approved movement fingerprint;
- design evidence and explicit approval state.

The queue rejects duplicate findings and overlapping source ports/movement keys. It never queues a preview that did not qualify.

## Apply and source change
**Apply approved fixes & recheck** submits approved entries to the dedicated topology Worker, sequentially, without repainting the canvas per item. For each entry, the Worker first runs a *new* authoritative source-bound preview against the current validated XML. The new movement and all before/after witnesses must exactly match what was approved; any new delta, missing finding, changed target or incompatible port is blocked and stops further mutations. Matching qualified entries are submitted as individual atomic `SECOND_PASS` transactions to the existing engine and independently replayed; every output must pass sourceSHA, fixedSHA, transaction, validation, lineage and pre-Final handoff checks.

The last verified checkpoint may be published on a later rejection or cancellation, with an explicit audit ledger. Future queued items are marked stale for new review; no automatic re-approval. A single final UI repaint replaces per-action canvas renders.

Statuses: `APPROVED` → `APPLIED`, `BLOCKED`, or `STALE`; selected count equals applied + blocked + unprocessed/re-review. Queue admission does not edit source. The user can remove/clear queued proposals without changing XML.

## Qualified failures
- BRAN node 10 / REDU node 20 at the same XYZ is **review only**. All six pair directions among its three source witnesses were source-rejected as `INCOMPATIBLE_PORTS`. The queue does not invent a second-pass witness.
- Shared moving groups or occupied target/source keys cannot be queued as independent actions.
- An unqualified port preview, missing diameter/direction, restraint, pipe collapse or changed movement cannot become an executable action.
- Cancellation terminates the Worker; late results are discarded. Last verified XML is retained.

## Test gates
1. Node unit tests: admission with/without consent, duplicate/conflict, fresh-source replay, stale movement and cancellation.
2. Repository Python/Node suite and exact-head public-fixture Chromium/Pyodide workflow.
3. On the private original or validated working XML: test queued legitimate connection(s), source witness/port selection, approval, identity drift after an earlier fix, and blocked BRAN/REDU case; download corrected working XML and repair history.
4. Independent reviewer verifies byte-based receipts, original source, retention of unmodified records and no unauthorized geometry or Weight edits.
5. Owner decision only after the above; PR stays Draft/HOLD. This stacked PR cannot be merged independently of its PR #10 base.

## Notes on performance
The manual queue intentionally remains sequential inside the Worker because different connection-movement groups may share engineering ownership. The earlier **short-element** atomic batch optimization is a separate independent-branch proof, not automatically transferable to arbitrary manual connection repairs.
