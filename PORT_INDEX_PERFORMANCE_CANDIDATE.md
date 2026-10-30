# PSI116 Indexed Port Search — performance candidate (read-only qualification note)

## Observed failure and bottleneck
Owner screenshot (private EF-05-PRO.TEST.xml) shows **12/89 selected short owners validated after 430 seconds** in the PR #10 browser Worker build. That is an observed application rate, **not** the CPU cost of a single repair. The existing worker keeps the UI responsive but repeatedly invokes full source resolution, atomic connection closure and independent pre-Final replay; Worker isolation alone does not improve computation.

Private source: 898,252 bytes, 41 branches, 1,654 Node occurrences. The original source stays private; no bytes or modified engineering output are committed.

Local CPython cProfile of one real removal and its independent replay logged ~98 million function calls in the unindexed code. Most cumulative time was in `PortModel.candidates` -> `repair` -> `moving_group`, which scans every source node and PIPE group for each candidate. The repeated target-identity search scans the full model again. This creates repeated whole-model search costs during the source replay.

## Scoped optimization — engineering decisions unchanged
Only `converters/psi116_topology_resolver/connection_ports.py` changes:
1. Preindex source records by branch and positive NodeNumber. `moving_group` examines the only two populations capable of meeting the **original** predicate, in original record order.
2. Index 1e-6 exact-position contacts in 3D; retain final Euclidean distance check and fall back to original scan for non-indexable coordinates. Guard numeric overflow.
3. Preindex moved PIPE membership. Test pre-existing collapse on untouched groups and recompute actual post-move collapse only on touched groups. A move may repair a pre-existing collapsed pipe; do not veto such a rescue by cached source state.
4. Use exact moved source keys rather than all model records to compute possible NodeNumber aliases, retaining source record order.
5. Preindex candidate endpoints in 25 mm 3D cells. Search +/-2 neighboring cells (not just +/-1) so the original inclusive **25 mm + 1e-9** tolerance at cell boundaries cannot be missed. Preserve the existing diameter, direction, closed-end, branch and ambiguity checks.
6. Cache immutable component-kind classification per PortModel. No policy threshold, source parser, connection disposition, Weight/Final writer, mutation, or lineage logic is changed.

No cached decision is reused across changed XML revisions; every new `resolve_psi116` rebuilds indexes from the current source.

## Evidence matrix
- **Synthetic parity:** `tests/test_port_index_parity.py` contains a separate unindexed reference implementation and compares exact candidate lists and moving-group results, including errors, across 0/0.5/25/25+epsilon/100 mm, shared positive identity, negative helpers, restraints, duplicates and far-branch controls.
- **Local existing Python tests:** 71/71 PASS, including the new independent parity test.
- **Private original analysis:** baseline and indexed complete findings/plan/short-element JSON have matching canonical SHA-256. **89** eligible GASK owners unchanged.
- **Private original transaction+replay:** first two independent selections produce byte-identical corrected XML, transaction JSON, validation JSON, complete lineage and handoff JSON. The first eight sequential owners also pass independently with exact source replay, reducing occurrences 1654 -> 1638 and eligible count 89 -> 81. These are local Python tests, not Chromium acceptance.
- **Representative local CPython timing:** baseline first selected owner transaction 3.86 s + pre-Final 5.74 s; indexed 1.02 s + pre-Final 1.73 s (approximately 3.5x for this one matched scenario). Times vary; profile instrumentation and local Python are not comparable to Windows Pyodide.
- **Real private-source browser speed:** NOT_RUN on the indexed head. Public pinned fixture GitHub Chromium/Pyodide CI is a distinct gate.

## HOLDs and acceptance
Remain **DRAFT / MERGE HOLD**. Before accepting:
1. Exact-head Python + Node and real pinned-public-fixture Chromium CI PASS.
2. Independent reviewer checks complete source parity, 25 mm + epsilon cell-boundary safety, shared labels, restraints, collapse-repair cases, tampered receipts and pre-Final replay, rather than relying on an author benchmark.
3. Owner runs original input at the **new exact head** in Windows/Chromium; records elapsed time, 89 selected/accounted status, responsiveness and cancellation; downloads validated current XML and receipts.
4. Engineering review separately reconciles removals and still-open cases. Do not infer 89 successful drops from the initial eligible count or from performance.

No Pages/mainline merge, production deployment, original file publication, or native CII/Final release is authorized by this note.
