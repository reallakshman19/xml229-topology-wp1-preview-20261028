---
name: oracle-protocol-v2
description: TopoFix Oracle protocol v2 (draft 5 Nov 2026) lives at D:\CodeD\oracle\ORACLE-PROTOCOL-v2.md; key rules from multi-agent lessons
metadata:
  node_type: memory
  type: reference
  originSessionId: eeea536d-530e-4f7a-993d-7aee477f4abf
  modified: 2026-11-05T01:12:38.030Z
---

D:\CodeD\oracle\ORACLE-PROTOCOL-v2.md: the Oracle protocol drafted from the 4–5 Nov lessons. Status DRAFT until the Owner approves.

Key rules:
- A blocking Owner question means a push notification plus a repeat on every check. A 4 h 14 min gap happened when the session relocated and killed the timer.
- Heartbeat file plus re-arming the timer on resume.
- Input preflight at planning time.
- Runners must probe every earlier blocker, not just the card's items.
- A spec author (the IR) never alone judges its own spec; a fresh reviewer is mandatory.
- A harness needs RED baselines and positive controls, never a placeholder PASS.

Related: [[no-merge-without-prototype]], [[ir-as-backup-coder]].
