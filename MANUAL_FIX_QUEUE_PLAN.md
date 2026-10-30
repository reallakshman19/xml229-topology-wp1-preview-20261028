# Manual Fix Queue — Draft implementation plan

Status: DRAFT / HOLD (not engineering acceptance)
Base dependency: PR #10 at a5fc0acbe489d85de881f28c9792ce5673ec86aa.
Additional integration baseline: private local PSI116 atomic-browser + compact manual R2 files, source byte custody must be retained.

Objective: Queue manually reviewed source-to-partner port matches, qualify each by the existing second-pass preview and approval authority, apply source-bound verified repairs without intermediate canvas redraw, and reconcile approved/applied/blocked/stale/unprocessed. The queue must not auto-approve inferred connections.

Non-negotiables:
- Preserve source SHA and exact source keys; every approved proposal stores partner, movement, preview evidence, approval explanation and epoch.
- Never mark BRAN/REDU node 10/20 as executable absent qualifying port witness.
- Duplicate occupied/overlapping moving groups are conflicts.
- Revalidate every queued item on the current working revision. Stale previews require re-review; never auto-ratify.
- Atomic verified checkpoint and full lineage receipt before publishing, cancellation terminates Worker.
- No change to PSI116 engineering rules, automatic 25mm limit, Final/Weight, or topology acceptance.
- Keep Source evidence and technical metadata accessible with concise default case display.

Gates:
1. Independently test the actual queue state machine (approval, duplicates/conflicts, stale, cancel, failure).
2. Full Node/Python suite + real Chromium/Pyodide repository public fixture on exact head.
3. Original private file Windows acceptance and independent reviewer qualification.
4. DRAFT/HOLD until explicit Owner release authorization.
