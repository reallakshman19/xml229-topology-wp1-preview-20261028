> **ARCHIVED HISTORICAL RECONCILIATION (1 Nov 2026):** This document describes PR #25 and the retired pre-Apply short preview. It is retained for provenance only. Do NOT follow its preview/admission instructions. Current merged #32 performs direct Apply; see [uxml-short-drop-edit-ops.md](./uxml-short-drop-edit-ops.md).

# UXML-SHORT-PREVIEW-MAIN-RECONCILE — source-bound reconciliation

**Date:** 1 Nov 2026 · **Scope:** only PR #25 read-only partial-preview integration into actual `main`.
**Verified origin/main:** `eaecd21d5a827e7860238103d3bd86bd3a78438e` (PR #28 merge).
**Source heads:** #24 `c4a53e31e79a7acf5120194a3a440522c6cf407a`;
#25 `8245d60420b107c65a01b032df975f4d4d09c7da`;
#26 `1280c2f3bb0a0f1afffbef7a53f3db289b132011`.
#28 merged #26's changes into main, which is ahead of #26 by the merge commit.
The old #25 is left UNMODIFIED for independent evaluation.
GitHub compare: `#24..main` modifies ten performance-only paths;
`#24..#25` modifies nine preview-only paths; the **only overlapping
product implementation path** is the conversion Worker snippet listed below.

## File-level conflict and retention matrix

| File | PR #25 intent | Current main / #26 inheritance | Disposition and retained guards |
| --- | --- | --- | --- |
| `converters/xml-cii-2019-standalone/topology-integration.js` | Preserve named, source-safe builder-error codes rather than exception-type-only/zero-op mismatch | #26 performance clocks and bounded profiling of Python/reader stages; same preexisting hub parity/patch writer | **Manual localized integration:** replace only the presentation-error `except` body. Retain all speed marks, direct-versus-patch EQUAL, sourceRefs and no-final-export rules |
| `tabs/topology-workspace/workspace-app.mjs` | N ready / M refused; ID and safe code, locate, deselect, invalidate on selection/epoch/SHA/revision, exact fresh all-accepted Apply | Blob in main exactly matches #24; #26 did not touch UI | Integrate PR #25 preview changes; do not change runShortBulk or connection policy |
| `converters/psi116_topology_resolver/uxml_operations_preview.py` | Independent export and projection of each short request; accepted ops plus exact refused items | Blob in main exactly matches #24 | Integrate PR #25 read-only preview. A rejected item remains rejected and cannot create a mutation op |
| `tabs/topology-workspace/short-bulk.mjs` | No preview task changes in #25 | #26 measured serial bulk, one native transaction and validation per item, source SHA, EQUAL per item, retained revision, warm Worker session | **Keep main byte-identical**; no optimization regression or weakening of eligibility |
| `tabs/topology-workspace/topology-worker.mjs` | No preview task change | #26 warm Worker/session and timing plumbing | **Keep main byte-identical** |
| `tabs/topology-workspace/topology-worker-client.mjs` | No preview task change | #26 bounded Worker reuse and cancellation isolation | **Keep main byte-identical** |
| `tabs/topology-workspace/short-preview-model.mjs` and `tests/short-preview-model.test.mjs` | Exact disjoint set partition; safe refusal descriptions and forged-set rejection | Absent from main | New files from #25 |
| `docs/uxml-operations-preview.md` | Per-item response contract and dismissal behavior | Unchanged from #24 | Integrate PR #25 documentation |
| `tests/test_uxml_operations_preview.py`, `tests/test_uxml_short_drop_hub.py`, `tests/uxml-evidence-refresh.browser.mjs` | Three-owner source-loss refusal, real named-builder error, re-preview/locate/deselect/mutation tests | Identical to #24 | Integrate independent #25 tests |
| `tests/uxml-bulk-three.browser.mjs` | Needs combined preview/bulk coverage | #26 real Worker 3-item warm bulk, item-two DIFFERENT and retained revisions | **Preserve main test and strengthen** to verify 3/0 selected-op preview, forced invalidate-and-repreview, per-item transaction/validation/EQUAL receipts, and mismatch handling |

### Safety invariants and tests

The unchanged Python native engine alone determines short-drop eligibility, source
tombstones and closure; no CLOS edits, questioned joins, changed tolerance/policy,
review-only Apply, or other-format release permitted.

**Preview:** accepted ops match exactly the source-qualified selected IDs with
a complete, disjoint refused partition; every refused owner has code, plain reason
and original-record navigation; deselect revokes the old preview. Apply requires
a fresh 100%-accepted preview bound to source digest, epoch, revision and EQUAL.

**Execution:** after this UI admission, the unchanged main bulk-speed runner still
runs one native transaction, complete validation and **independent EQUAL** per owner,
retaining each revision. Worker/Worker-client reuse stays as merged. DIFFERENT
stops before further Apply and keeps download disabled; cancellation/stale
responses cannot release, per the existing Worker-client protocol tests.

**Custody:** Main branch was read and pinned before branching; the new draft is
based directly on this main head and deliberately does not merge/cherry-pick
other feature branches. Independent non-author review and any private Owner trial
remain separate gates. No private input is included.
