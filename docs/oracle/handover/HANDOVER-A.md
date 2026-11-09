# Handover — Project A: TopoFix PSI116 hub (lane A) · checkpoint 9 Nov 2026

LOCAL/DRIVE ONLY (contains chat URLs). Never publish.

| Item | Value |
|---|---|
| Repo | reallakshman19/xml229-topology-wp1-preview-20261028 (public) |
| Work | PR #36 — MERGED to main 7 Nov 01:02Z by the Oracle on the Owner's word; merge commit 787e99140863de5f9f70d67ffc3e4dfd0be67e13 (gated head 45179aa85d7ebff7c3f1095a57c1e33445659031) |
| Note | Owner merged WITHOUT the L4 prototype run (explicit override of "no merge without prototype"). |
| Coder | coder-a6 — <CHAT_URL_REDACTED> (page can be slow: fresh tab, wait ~30 s for the composer) |
| Receipts issue | #12 in the same repo |
| State | IDLE. Nothing in flight. |
| Local-only code | None (all on GitHub). Review checkouts or-36*, rb-36*, inv-35 are disposable. |

## Last accepted step
A3 accepted 6 Nov 20:40Z "with limits" L1-L5:
- L1 25 refusal codes changed to UXML_PSI116_HUB_SHAPE_INVALID, undocumented in the PR.
- L2 AttributeError remap has no committed test (mutant survives).
- L3 wrong-typed free-label fields report as differences, not a named error.
- L4 pathological JSON (100,000-deep, >4300-digit integers) gives a traceback / raw text.
- L5 the remap also wraps engine analysis.

## Next step (needs Owner OK)
Draft card **A4** = fix L1-L5 (small hardening card, forward commits on a new branch off main 787e9914, new PR). Gate as usual (Oracle repro + L2 runner + fresh reviewer, PASS >= 92 and every category >= 17). Optionally first: the Owner's lane A prototype run (tools/lane-a-prototype.ps1) on main.

## Records
lanes.md (Q40-Q44, 7 Nov 01:02Z entry), TOPOFIX-STORY.md, plans/LANES-ABC-CII-WBS.md, plans/cards/STEP-A3*.md, gate reports in oracle\scratch\rev-a3* / run-a3*.
