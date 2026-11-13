# Handover — Project B: XML Compare Utilities (lane B) · checkpoint 9 Nov 2026

LOCAL/DRIVE ONLY (contains chat URLs). Never publish.

| Item | Value |
|---|---|
| Repo | reallakshman19/XML_Compare_Utilities (public) |
| main | e09c81d18ea52379a06d4e8aa7bb553689ba0353 |
| PR #258 | Step 1.2 invariant-first ALIAS_COINCIDENT_NODE writer — MERGED 7 Nov 19:03Z, merge 7dc17dee066d03d59cd324221107a54d3cf62872 (gated head 35c0489d; runner SUPPORTS, reviewer 93) |
| PR #259 | B3 same-run coincidence proof (read-only) — rebased onto main (B3-R5), MERGED 8 Nov 00:10Z, merge e09c81d1 (gated head f84afed8; B3 content reviewer 94; rebase runner SUPPORTS, CI 13/13) |
| Coder | coder-b8 — <CHAT_URL_REDACTED> (chat title "Replan Coordinate Evidence") |
| Backup coder / IR | ir-257 — <CHAT_URL_REDACTED> |
| Receipts issue | #239 |
| State | IDLE. Nothing in flight. |
| Local-only code | None. Review checkouts or-258*, or-259*, rb-257*, rev-257* are disposable. |

## CAESAR facts the lane relies on
Attribute names case-sensitive; only exactly -1.0101 is the unset sentinel; DELTA_X/Y/Z are the authoritative displacement in declared units; XML whitespace is only #x20/#x9/#xA/#xD; bend TO/curvature nodes sit off their DELTA position.

## Next step (optional, needs Owner OK)
Follow-up card from reviewer notes (non-blocking):
- a test at exactly 0.001 mm (pin the <= boundary);
- a near-sentinel DELTA on row 0 (reviewer mutant "skip row 0" survives);
- FROM_/TO_ coordinates still read case-insensitively;
- units not checked;
- misleading test name ("non-DELTA literal coordinate formatting unchanged") and comment at PatchBack.js:174; duplicated frame-mapping hypot;
- new check runs before the REF alignment check (less clear refusal code).
After that, lane B feeds lane C (transfer to CII).

## Oracle probes (reusable)
oracle\scratch\rev-12r4\probe12r4b.mjs (argv[2] = file URL of uxml/), oracle\scratch\rev-12r5\writer12_argv.mjs, rev-12r5\attacks12r5.mjs, run-12r5\attack12r5.mjs.
