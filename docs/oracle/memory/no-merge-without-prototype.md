---
name: no-merge-without-prototype
description: Owner rule — never merge to main unless the change is proven in a prototype the Owner runs on real inputs
metadata:
  node_type: memory
  type: feedback
  originSessionId: eeea536d-530e-4f7a-993d-7aee477f4abf
  modified: 2026-11-04T10:57:24.252Z
---

Do not merge anything to main unless it has been proven in a prototype first (Owner, 4 Nov 2026, about the 3D_Converters perf and rigid fixes).

**Why:** passing tests, mocked harnesses and review scores have repeatedly not matched real behaviour; the Owner trusts what runs on real inputs. This matches the prototype-first skill (each step ends in something the user runs on the real inputs).

**How to apply:** every WBS plan ends with a prototype step (a runnable build on the real input, tried by the Owner) before any merge step; work stays on draft PRs / branches until then. Merging is still only on the Owner's explicit "merge". Related: [[oracle-step-gate]].
