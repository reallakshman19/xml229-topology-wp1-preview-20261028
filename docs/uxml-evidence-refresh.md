# UXML-EVIDENCE-REFRESH · bounded read-only follow-up

**Owner stand-in authorization:** 31 October 2026, 23:19. New draft stacked
on independently accepted UXML-PREVIEW PR #20 @ `32e85066`. No merge.

## Exact revision custody

The **connection evidence** button was previously disabled after validated
bulk short-element and approved manual-queue publications because their
source, findings and revision changed but their ordinary Analyze
`analysisProof` did not. The button correctly failed closed.

Both existing publication paths now call one shared
`refreshPublishedEvidence(generation, revision, sourceRef)` **only after**
a previously validated working revision has been published. This schedules
one **new, read-only** Worker analysis using the same
`readOnlyAnalysisJob`, `acceptAnalysis` and
`establishCurrentAnalysisProof` as ordinary Analyze and single Auto-fix.
No prior transaction/lineage receipt is relabelled as a fresh analysis.
Success requires a complete topology-only result, exact current
`epoch`, `revision`, `sourceRef`, source SHA and same hub/parity route,
and publishes the new result and its current source-bound proof.

Until recheck finishes the button stays disabled. If the recheck fails,
has a wrong source hash, or an epoch/revision/source/route changes while
waiting, the connection-evidence download stays disabled, the last fully
validated working XML remains intact and the **Connection evidence**
status line names the reason (for example
`EVIDENCE_RECHECK_SOURCE_DRIFT`,
`EVIDENCE_RECHECK_STALE_REVISION` or
`EVIDENCE_RECHECK_FAILED:Error`). The user can choose Analyze to retry.
No extra approvals or transaction path are introduced. Successful
partial checkpoint publications, including existing cancel/error
checkpoint surfaces, use the same guarded refresh.

This additional read-only verification is separate from **operations
preview**: errors there do not change hub parity or native Auto-fix.
Python's preview builder exception now carries only
`UXML_OPS_PREVIEW_BUILDER_FAILURE:<exception class>`; the raw
`str(exc)` message does not cross the JS/Python boundary.

## Qualification, public synthetic only

`node --test tests/uxml-evidence-refresh.browser.mjs` mounts the real
Topology UI with an **injected** `runEngine` wrapper around the actual
module Worker/Pyodide. For each existing bulk short and manual queue
publication it asserts: a fresh proof enables the connection evidence
download on the new revision, and a deliberately stale recheck result
keeps evidence disabled with a visible reason while preserving corrected
XML. This is an actual Worker and existing Python transaction, not a
test-only product mutation method.

`tests/test_uxml_operations_preview.py` injects a synthetic exception
message into the read-only builder and verifies the returned error code
contains only the exception class, never the raw message. All existing
S2, native Python, Node, synthetic Chromium/Pyodide and original browser
audits must continue passing.

**HOLD:** XCU reader ownership/pin unchanged; no engine, policy, CLOS,
240.6 mm join, tolerance, Auto-fix, engineering acceptance, merge,
release, native Final/CII or private Owner model use.
