# UXML-SHORT-DROP-HUB — exact short-owner edit-ops/v1 extension

**Scope:** PSI116 only, synthetic/public qualification. XCU owns UXML at the
existing pinned commit; TopoFix consumes it through the same verified runtime.
No reader copy, no new XML serializer, no CII/Final release. All CLOS,
questioned joins, review-only Apply and existing threshold/tolerance holds remain.

## Why the existing kind cannot be reused

`SAFE_DROP_PIPE_GEOMETRY` only removes a proven expendable plain-pipe record
from an ordinary Auto-fix action. It does **not** express deleting an entire
short gasket/inline component owner and then closing the *surrounding* ports.
Reusing that kind would incorrectly enlarge its authority. The narrow new kind
is `DROP_SHORT_ELEMENT` under **the unchanged `uxml-edit-ops/v1` envelope**.

## One explicit source-bound transaction

A selected operation is exactly:

- `kind: DROP_SHORT_ELEMENT`; `sourceActionId: SHORT:<branchIndex>:<componentRefNo>`.
- `opId: UXML-OP-<sourceActionId>`; `fileSha256` is the original source SHA.
- `targets`: **sorted exact union** of removed owner record keys and any
  original records whose `NodeNumber` or `Position` changes during closure,
  all verified against XCU `components[*].sourceRefs[0]`.
- `params[0].request`: exactly `{id, sourceSha256, nodeKeys}`, matching the
  current native `short_elements()` qualified owner.
- `params[0].leftKey/rightKey/lengthBasis/lengthMm`: regenerated from the
  existing native short-elements detector, never user-asserted authority.
- `params[0].edits`: sorted field-level effects from the existing
  `apply_short_element` **disposable in-memory native transaction**:
  `{recordKey, field:"Source record", before:"Present", after:"Removed"}`
  for each removed source owner record, and `NodeNumber`/`Position`
  `before/after` for each actually modified surrounding record. An op never
  embeds removed raw XML or exports corrected XML as its parameters.
- `policy`: exactly one `selected_action_ids` entry equal to that request's
  ID and exactly one `short_element_requests` entry, with current
  `minimum_confidence`, `require_no_blocking_plan_actions`, and
  `apply_all_safe=false`. Joint/manual requests are refused.

No inferred CLOS closure, unverified owner, unqualified curved element, selection
outside ≤6 mm, or review-only case is admitted. The native short detector,
short-element transaction, validation and pre-Final lineage remain unchanged.

## Writer safety and exact parity

`export_edit_ops()` computes the canonical operation from a disposable native
transaction of the UXML-fed Python resolver. It validates the full selected
owner, exact record effects, sourceRefs and the XCU loss contract. An original
record deletion is a whole-record write (`*`); a retained record touches only
its exact `NodeNumber`/`Position` fields. Loss-contract paths on any touched
record/field fail closed, as do CLOS, source drift and missing refs.

`apply_edit_ops(original, uxml, ops)` independently parses the **original**
PSI116 bytes, rechecks original sourceRefs and recomputes the canonical op
(including targets and params), then delegates the edit exclusively to
`transaction.apply_topofix_transaction()` with that one source-bound short
request. It never edits the original path. The Worker also independently runs
the **direct** native transaction on the same source for comparison; complete
transaction and validation reports and final XML bytes must be **EQUAL**.
DIFFERENT/UNAVAILABLE causes no emitted corrected XML and no download.

The 89-item case remains the *existing sequential* algorithm: each item uses
its own current-source SHA, explicit selection and native validation; the next
item sees only the last committed revision. A mismatching item cannot enter the
checkpoint. A previous validated checkpoint is retained privately but must be
reverified before release after a hub mismatch.

## Read-only pre-Apply Operations preview

With hub EQUAL, the Owner selects short elements in the existing ≤6 mm preview,
then chooses **Preview selected UXML edit operations**. Each selected item is
separately simulated against the same **current read-only source** for exact
edit-op projection; this is not a guarantee that its future post-prior-transaction
revision will remain qualified. The preview lists short ops alongside existing
Auto ops with exact original keys and field changes. Any selection, source,
revision, route, parity or epoch change invalidates the short-preview admission.
A separate explicit **Apply all selected & close** remains required.

The deliberate pre-Apply simulation may add latency for many selections;
this assignment records per-item execution milliseconds in synthetic test logs
and does **not** attempt performance optimization.

## Negative obligations

Unknown kind, widened policy, multiple short requests, altered owner keys,
arbitrary closure targets, altered params, source SHA drift, UXML loss path,
CLOS write and parity mismatch are refused with named reasons. Tests use only
synthetic PSI116 and the verified pinned XCU reader. No Owner record, name,
coordinate, source hash or source filename is committed to GitHub.


## Deleted owner raw-only children — source-bound exception (1 Nov 2026)

Only `DROP_SHORT_ELEMENT` uses this exception. When the native short-owner
transaction deletes a complete original source record, each lossContract entry
with the **exact** code
`PSI116_RAW_SOURCE_ONLY_NOT_SEMANTICALLY_CARRIED` and a strict descendant
`sourcePath` of that deleted record is **removed with the original record**.
The op carries sorted unique `removedWithRecord: [{recordKey, field}]` entries.
The read-only Operations preview labels these
**Removed with the deleted element: SIF, InsulationThickness, ...**
and also includes source-linked entries in the visible JSON/CSV exports.

This is **not** permission to reconstruct or silently discard raw data on
retained records: a loss at the deleted record's path itself, any other loss
code beneath a deleted owner, or a loss on a retained record's edited
`Position`/`NodeNumber` remains an immediate
`UXML_LOSS_CONTRACT_FIELD_TOUCH` refusal. `_loss_veto` for every other
disposition, the pinned XCU reader, policy, threshold and CLOS barriers stay
unchanged. The patched XML is still produced exclusively by the existing
native transaction writer and must compare byte-for-byte with the direct
native route for the same explicit short request. This is not engineering
acceptance or a review-only Apply authorization.

Synthetic tests explicitly exercise three guard mutants and source nonmutation,
native patch/direct byte equality, read-only preview disclosure and Chromium
rendering. No private Owner file or findings are included.
