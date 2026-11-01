# TOPO-A — brief for the ChatGPT agent (31 Oct 2026)

**You are the TOPO-A writer.** The Oracle (a Claude Code session) checks every return before the Owner sees it. Report only in [issue #12](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/issues/12).

## Owner intent
Topology must give auditable automatic fixes where they are safe, and clear manual-review directions everywhere else. An engineer believes Node A (CLOS-declared end) and Node B should connect: they are 240.6 mm apart, both the same OD, with X/Z aligned. The tool hides this pair because of the CLOS declaration. The tool must let the engineer **find it and see why it is hidden**. It must **never join it automatically**.

Spec: [TOPO-A concept spec R1](https://github.com/reallakshman19/progress-page/blob/main/docs/TOPO_A_ASSISTED_CONNECTION_CONCEPT_SPEC_R1.md), sections 2, 3.1 and 5.

## What exists (checkpoint)
- Draft [PR #13](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/pull/13) at head `209ec34c`, built on the stack PR #11 → PR #10. It adds a read-only `closureBindingWitnesses` list to the findings payload. Each row is one CLOS-bound port occurrence, with the exact source keys and binding kinds taken from `connection_ports.bound_closure_records()`.
- Independent review passed at 92/100. Tests pass: 85/85 Python (`python -m unittest discover -s tests -p "test_*.py"`) and 49/49 Node (`node --test tests/*.test.mjs`).
- PRs #10 and #11 are frozen bases. Never push to their branches.

## Your task: make it visible on screen (P1, review-only)
Work on a new branch off `209ec34c`, and open a draft PR against PR #13's branch `feat/topo-a-p0-closure-witness`.

1. **Finish the carried-forward items first:**
   - (a) The browser (Pyodide) runtime file list in `converters/xml-cii-2019-standalone/topology-integration.js` must load `closure_witness.py`. Today the browser shows the EVIDENCE_UNAVAILABLE row instead.
   - (b) Add a test where an off-port declaration binds a same-number record between 1e-6 and 25 mm away. It must fail if the radius in `closure_witness.py:74` is shrunk.
   - (c) Remove or relax the flaky `< 0.25 s` wall-clock assert.
   - (d) Optional: reuse the resolver's `PortModel` instead of the second build at `models.py:277`, if it can be done additively.
2. **Add a "Find / Review Connection" panel** in the topology workspace UI, separate from the Manual Fix list:
   - Node Number A and Node Number B inputs.
   - Show **every** matching occurrence: branch, component/ref, endpoint, CLOS declaration with its source key, 3D distance and vector in mm, OD/wall.
   - Duplicate Node Numbers force a branch/port choice. Never silently pick the nearest occurrence.
   - Highlight the two ports on the canvas. Any line between them is visibly a *proposal*, not a solver edge.
   - The status is always **REVIEW ONLY**. For a CLOS end, show `CONFLICTS_WITH_CLOS`, and show that the correction belongs upstream in CAD/design, followed by a reimport.
   - Missing numbers and helper-only endpoints get specific messages.
3. **Tests:** a browser-free unit test for the lookup and disposition logic, plus a browser audit check in `tests/audit-browser.mjs` using a synthetic pair-shaped fixture. Include one test that fails if a CLOS end is offered as executable.

## Never
Edit CLOS or any XML; change the 25 mm or 6 mm tolerances; join the 240.6 mm gap; add an Apply button for these cases; build a new resolver; touch CII Writer/Weight/Final; push private model files, coordinates or hashes to GitHub; merge.

## Done = return in issue #12
- Draft PR link and head SHA.
- Changed-file list.
- Exact test commands and counts.
- One screenshot of the panel on the synthetic fixture.
- A deliberate-failure proof.
- What you ran vs only reasoned (OBSERVED / EXECUTED_HERE / NOT_RUN).

Then stop. **Owner benchmark:** you type the two node numbers and see both ends, the CLOS mark, 240.6 mm, "review only, fix upstream", and no way to apply it.
