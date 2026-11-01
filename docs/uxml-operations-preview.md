# UXML-PREVIEW · read-only proposed operations

**Owner decision (31 October 2026):** "Preview on ops." This is a display
surface for authoritative S2 \`uxml-edit-ops/v1\` operations **before** the
Owner initiates any Auto-fix. It is never an approval or mutation surface.

## Source authority and workflow

The opt-in **Universal XML route (preview)** remains OFF by default.
When ON, the pinned XCU reader at
\`9f51bfcaf98af4041ec0c0615dc67c9c357b0632\` is fetched with all seven
Git blob checks, independently checked before ES-module import, and consumed
by the existing disposable Worker. The existing Python bridge computes
direct-vs-UXML topology parity. No XCU module is tracked in TopoFix.

**Only when parity is EQUAL**, the existing Python S2
\`export_edit_ops(uxml)\` selects every current-policy Auto-eligible action;
the new \`uxml_operations_preview.py\` is a **pure read-only projection**
of each returned op, not a new patcher. It reads the original source-field
text from XCU-linked source records, and derives the displayed field changes
from the exact existing proposed-change witnesses. For ordinary Auto operations, no transaction is run,
original XML rewritten, output XML generated, policy loosened or approvals
recorded. The separately selected `DROP_SHORT_ELEMENT` read-only
projection uses the existing native transaction on a disposable in-memory
copy to obtain exact deletion and closure-field witnesses; it never emits
corrected XML or authorizes Apply. See `docs/uxml-short-drop-edit-ops.md`. The Python resolver/transaction engine is unchanged.

The returned internal metadata has schema \`uxml-operations-preview/v1\`,
original-source SHA for volatile custody, an operation array, and summary.
Each operation row corresponds 1:1 to an \`uxml-edit-ops/v1\` \`opId\`;
it includes its type, plain-English name, UXML component/port IDs, exact
PSI116 \`sourceRefs.recordKey\` witnesses (with changed/witness distinction),
field-level before/after, and current eligibility reason. A source-record
removal shows "Present → Removed"; it does not serialize the removed record.
If any supported action lacks exact source witnesses/field projections,
projection fails closed and parity is DIFFERENT, never a silently partial
preview.

The summary gives total operations, counts by type, and records untouched
by **any projected field change**. Filter by kind or source record key;
each row's Find/Review button reuses the current canvas/occurrence selection.
Review-only findings are counted from the existing grouped manual audit,
and **Source Review Queue** navigates to the existing Manual fix / review
filter; no review-only action is represented as an edit operation.

The panel contains only locating and CSV/JSON export controls. Both
exports use the **current kind filter and source-key search**, so they contain
only the visible operation rows. JSON omits internal kind/action IDs and
unshown source-record counts; its summary uses the same plain kind names
and overall / visible counts displayed in the panel. CSV contains one row per
visible operation. Neither contains full XML, unmapped UXML, source hashes
or a patch. CSV escapes spreadsheet-formula introductions.

**Presentation independence:** if the Python preview builder raises or the
browser rejects its rows, the native parity badge remains **EQUAL** (assuming
topology parity was EQUAL), and native Auto-fix admission is unchanged.
The panel instead shows **"Preview unavailable: <named reason>"**, with
zero applicable preview rows and exports disabled. This is NOT a topology
DIFFERENT result. Actual topology DIFFERENT/reader UNAVAILABLE still show
the parity reason with no preview rows, even if a nonempty preview payload is
received. Source replacement, toggle, cancel or stale epoch/revision also
block preview export.

## Qualification

The pinned XCU synthetic Python test
\`tests/test_uxml_operations_preview.py\` asserts the exact 1:1 operation
count, kind, source keys, original-file nonmutation and field before/after
versus the **existing native transaction** operating only on its isolated
copy. It does not call a new writer. The browser test
\`node --test tests/uxml-operations-preview.browser.mjs\` injects
\`runEngine\`: EQUAL shows every row, filters, original location and
CSV/JSON; DIFFERENT/UNAVAILABLE show no applicable rows. The existing
\`node tests/audit-browser.mjs\` continues to qualify real Chromium and
Pyodide using synthetic fixtures; no private Owner model is checked in.

**HOLDs:** all existing CLOS, 240.6 mm join, manual/review Apply, tolerance,
policy, native CII/Final, merge and release restrictions remain unchanged.
