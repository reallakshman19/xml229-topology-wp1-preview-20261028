# Source-reference preservation candidate — WBS 1.3

The engineer now receives a source-qualified preservation review when a coincident
PIPE removal cannot be justified. The review names the absorbed and owner records,
NodeName/ComponentRefNo, OD/wall values, the veto, and the manual source-model
decision plus re-export/reanalysis steps. It offers no Auto fix for that proposal.

This is a bounded repair on preview baseline
`1b9804b21aacd14e12a884f98b5958b9441a9cc2`, under native issue #4. It is authored
implementation and self-assessed validation. IR `6ae2d5ac` returned PARTIAL /
INDEPENDENCE_NOT_ESTABLISHED on the earlier candidate `9804e2c`; see native issue
#2 comment 6494348817. Its source/JS observations do not qualify Python replay or
browser execution. No product
merge, deployment, protected PR #346 integration or engineering acceptance occurs.

## What changed

- Planner coalescing resolves original occurrence witnesses before considering a
  removal. It shares the actual removal vetoes with the transaction, including
  nonempty ComponentRefNo, and passes the selected resolver configuration.
- An unproven removal becomes nonmutating `REVIEW_SOURCE_RECORD`; it does not
  globally block unrelated validated actions or silently adopt a new alias repair.
- The backend independently rejects reference-bearing deletion, including a
  synthetic legacy plan that bypasses the new planner. The old private guard
  import remains available for existing falsifiers.
- Bulk screening requires explicit empty reference evidence. The audit displays
  the source-specific manual directions through the existing escaped renderer.
- The Pyodide topology loader registers the shared policy module. No runtime,
  writer, native CII, Final or Weight ownership changes.

## Source and expected behavior

The exact public S0 remains external to the repository: FirstpassXML, 144471 bytes,
SHA256 `feee5a5a6399207337e63bc56c8afb001fe37ab30c6a7a9283333ec60f6eea38`, at
`3D_Converters@cba348152faa9c2077d5c91a5f85b4b81d2e8e25`.

The original 66 mutating proposals are now accounted for as 39 applied, 17
shared-occurrence conflicts and 10 nonmutating preservation-review proposals.
All 216 source records remain; the 48 pre-existing NodeNumber alias operations
are retained. The previous 40-action digest/count is historical, not a target.
These are action/proposal counts, not a measured number of engineering cases.

This rule conservatively rejects a populated reference even if another source
record shares it. No engineering exception, component-ownership transfer or
semantic deduplication rule is inferred from equal text or XYZ.

## Reproduce and review

```
python -B -m unittest discover -s tests -v
node --test tests/audit-view.test.mjs tests/batch-plan.test.mjs
```

The focused regressions first fail on the original candidate: full transaction
loses a unique reference, planner offers deletion, UI screening accepts it and
the audit omits its precise manual message. The repaired candidate retains the
safe empty-reference positive control and existing NodeName/restraint/rigid/
weight/position/diameter/wall vetoes. Direct selection of a review action rejects.

The existing browser journey now checks source-specific manual guidance, absence
of Auto fix for the preservation case, all 216 records and their engineering
fields in the downloaded XML. It retains the actual batch-report download for
the new candidate when executed. In this environment that browser journey is
NOT_RUN: browser installation returned invalid/truncated archives before launch.
This must not be represented as browser acceptance or original historical receipt
recovery. The existing deployment workflow is unchanged and was not dispatched.
It runs only on main/manual dispatch and its Python pattern covers gap tests;
IR must explicitly run the full Python command above for these new regressions.

## Remaining limits

### Missing source-map hardening — IR P1 follow-up

The IR reproduced that `previewBatchPlan(findings, actions, null)` bypassed the
client's PIPE removal screen. The helper now always checks removal witnesses,
including when the map is omitted/null or has no matching record. Missing proof
uses the existing explicit preservation rejection and does not reserve keys that
would block an unrelated alias action. Map and plain-object positive controls
with an explicit empty-reference PIPE remain eligible. The Python guard and
workspace invocation are unchanged; this is not evidence of live unsafe XML
deletion. The regression fails on `9804e2c` and passes after this repair (20 Node
tests). The changed candidate needs review; the prior IR return is not silently
rebound to the new head.

Distinct-principal review and independent engineering expectations remain pending.
This patch does not qualify every populated source field, establish connection
intent, solve the residual 1790/1800/1810 case, consolidate cases, implement strict
PSI116 admission or demonstrate manual S1 identity reconciliation. Those WBS
outcomes remain open. No XML/CII source or corrected engineering file is committed.
