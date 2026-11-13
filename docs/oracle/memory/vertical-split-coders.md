---
name: vertical-split-coders
description: "Owner-approved (1 Nov 2026) three vertical coder lanes - A fix flow, B formats, C property transfer (CIIFR) - each owning a whole user journey and its files."
metadata:
  node_type: memory
  type: project
  originSessionId: d2448049-7a1c-40aa-9cb7-82f273120f0b
  modified: 2026-11-01T15:34:01.248Z
---

Since 1 Nov 2026 19:33 the coders are split by user journey, not by layer:
- **A, fix flow** (TopoFix, PSI116/XML family): edit/export ops, operations preview, PSI116 patcher, all of `tabs/topology-workspace/` including bulk apply and the Worker.
- **B, formats** (InputXML, Categorised, Enriched): XCU `uxml/`, the Categorised converter and InputXML Workspace, `uxml_adapter.py`, `uxml_compare.py`, `uxml-browser-reader.mjs`, the format patchers, and its own `uxml-format-router.mjs` (A adds the one hook-in line).
- **C, property transfer** (CIIFR, CII format): XCU CII property-transfer tabs, `prototypes/ciifr-xmlv3/`, the CII converters. Not opened until CIIFR coding resumes at I2; CIIFR has its own Oracle.

**Why:** The Owner asked to "make vertical split between these 3 as far as possible" so coders stop colliding on shared files (e.g. `workspace-app.mjs`) and each successor inherits one coherent journey.

**How to apply:** Every brief lists the other lanes' files under DO NOT. Shared seams have one owner: the XCU hub is B's (A pins it, C never uses it as a CII store); the screen hook-in is A's; InputXML-to-CII bridge changes go Oracle-to-Oracle first. Full text is in handover spec §4.1. Related: [[buddy-handover-at-checkpoint]].
