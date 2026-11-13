# L4-S1 — sequential short-drop speed measurement

Base: `4eaf89b58646cf5cb08617b32e64fdcb72450e3b` (merged #37, memo #33 present).
Only five files added under `tools/speed/`; no product changes, no PR #34 changes.

## MEASURED

Invented default seed 116: 41 branches, 1,654 nodes, 89 initially eligible
short GASK owners and 40 short restraint-blocked GASK owners. Native CPython,
Node pinned XCU reader (all seven Git blob hashes verified), existing memo ON,
one owner per checked-in Worker Python job. No browser or private source used.

Command: `python3 -B tools/speed/measure.py /tmp/l4fixture.xml --owners 89 --out /tmp/l4-89.json`
(with `XCU_UXML_ROOT` pointing to the staged pinned reader).

- Requested: 89; attempted: 89; applied with EQUAL: 89; skipped: 0.
- Total measured owner wall: **655.529 s**; mean: **7.365 s/owner**.
- Min/max owner wall: 6.337/8.691 s.
- Sum of exclusive stages: 655.529 s; maximum per-owner accounting error: 0.000000%.
- Source bytes unchanged. Initial selection, reader pin verification and final JSON writing excluded from owner wall. No corrected model is published.

Exclusive times below add to wall (including measured residual `other`); inclusive
transaction call times below overlap nested stages and must not be added again.

| Stage | Total s | Mean s/owner | Share % | Calls | Calls/owner | Repeats |
|---|---:|---:|---:|---:|---:|---:|
| `parse` | 33.741 | 0.379 | 5.15 | 1336 | 15.01 | 1069 |
| `model_analyse` | 108.491 | 1.219 | 16.55 | 268 | 3.01 | 1 |
| `resolve` | 0.812 | 0.009 | 0.12 | 623 | 7.00 | 356 |
| `native_transaction_direct` | 8.499 | 0.095 | 1.30 | 89 | 1.00 | 0 |
| `native_transaction_export` | 8.550 | 0.096 | 1.30 | 89 | 1.00 | 0 |
| `native_transaction_validate` | 0.068 | 0.001 | 0.01 | 89 | 1.00 | 89 |
| `native_transaction_apply` | 0.154 | 0.002 | 0.02 | 89 | 1.00 | 89 |
| `native_transaction_replay` | 0.083 | 0.001 | 0.01 | 89 | 1.00 | 89 |
| `native_transaction_nested` | 32.083 | 0.360 | 4.89 | 178 | 2.00 | 89 |
| `uxml_reader` | 25.001 | 0.281 | 3.81 | 89 | 1.00 | 0 |
| `uxml_adapter` | 7.470 | 0.084 | 1.14 | 89 | 1.00 | 0 |
| `canonical_export` | 6.493 | 0.073 | 0.99 | 89 | 1.00 | 0 |
| `canonical_rederivation` | 8.335 | 0.094 | 1.27 | 89 | 1.00 | 0 |
| `patch_back` | 1.670 | 0.019 | 0.25 | 89 | 1.00 | 0 |
| `patch_back_compare` | 0.348 | 0.004 | 0.05 | 89 | 1.00 | 0 |
| `hub_parity` | 4.900 | 0.055 | 0.75 | 178 | 2.00 | 0 |
| `lineage_recheck` | 47.484 | 0.534 | 7.24 | 445 | 5.00 | 0 |
| `memo_digest` | 87.242 | 0.980 | 13.31 | 4539 | 51.00 | 0 |
| `memo_copy` | 200.272 | 2.250 | 30.55 | 1335 | 15.00 | 0 |
| `memo_other` | 12.118 | 0.136 | 1.85 | 267 | 3.00 | 178 |
| `other` | 61.717 | 0.693 | 9.41 | 89 | 1.00 | 0 |

Transaction call breakdown, inclusive (the JSON retains each call per owner):

| Call | Total inclusive s | Mean inclusive s/call | Calls | Same bytes | Same bytes/policy/route repeats |
|---|---:|---:|---:|---:|---:|
| direct | 187.926 | 2.112 | 89 | 0 | 0 |
| export | 104.653 | 1.176 | 89 | 89 | 0 |
| validate | 35.393 | 0.398 | 89 | 89 | 89 |
| apply | 31.202 | 0.351 | 89 | 89 | 89 |
| replay | 33.821 | 0.380 | 89 | 89 | 89 |
| nested | 95.501 | 0.537 | 178 | 89 | 89 |

Actual memo counters (deltas over the timed owners):

| Counter | Total | Per owner |
|---|---:|---:|
| `source_resolve_hit` | 444 | 4.99 |
| `source_resolve_miss` | 179 | 2.01 |
| `source_resolve_store` | 179 | 2.01 |
| `transaction_hit` | 267 | 3.00 |
| `transaction_miss` | 178 | 2.00 |
| `transaction_store` | 178 | 2.00 |
| `uxml_resolve_hit` | 178 | 2.00 |
| `uxml_resolve_miss` | 89 | 1.00 |
| `uxml_resolve_store` | 89 | 1.00 |

Acceptance and regressions (invented fixtures only):

- `python3 -B -m unittest discover -s tools/speed -p test_speed_tools.py -v`: 3/3 PASS. T1 verifies deterministic exact counts and existing reader; T2 CLI five owners all EQUAL and all named stages/call counts, sum within 5%; T3 measurement ON and OFF produce identical PSI116 bytes to independent uninstrumented API calls; original unchanged.
- `python3 -B -m unittest discover -s tests -p test_short_elements.py -v`: 9/9 PASS.
- `node --test tests/short-bulk.test.mjs tests/short-bulk-publication-order.test.mjs`: 20/20 PASS.
- Total 32/32 tests; 3 card acceptance + 29 targeted regression tests.

## WHERE THE TIME GOES

1. **memo_copy** — 200.272 s (30.55% wall).
2. **model_analyse** — 108.491 s (16.55% wall).
3. **memo_digest** — 87.242 s (13.31% wall).

The five short transaction invocations per successful owner are direct, export,
validate, apply and independent pre-Final replay; nested closure transactions
are separately counted. All five outer calls use the same source bytes within
an owner, but the native and UXML routes have distinct authority. Validate,
apply and replay repeat the UXML-route transaction work already requested for
that owner. Actual memo transaction hit/miss counts above show how much is
already cached: 267 hits versus 178 misses. The earlier
pre-memo 4x native transaction and 12x analysis observations must not be carried
forward as if they were today's measurements.

Reader/clone/root parse calls: 1336 total, 1069
repeated source-byte fingerprints within one owner. Model analyzer calls:
268 total, 1 repeated fingerprints;
resolver entries: 623 total, 356 repeated.
The fingerprint does not prove that an independent authority or a revised
model may be replaced; clone/root parsing and analysis have different purposes.
Repeated XML bytes alone do not imply identical policy, route or witness.
Memo hits still incur digest construction, defensive copying and bookkeeping.
The actual hot spots are more useful than simply counting outer calls.

## OPTIONS

Ranked diagnostic targets only. Shares are measured ceilings for the named
cost buckets, not predicted speedups or guaranteed removable fractions. No
option is implemented. Every option retains one validated transaction and
EQUAL hub/patch parity for each owner, in serial revision order; no batching.

1. **Reduce defensive memo copy cost** (target `memo_copy`: 30.55% of measured wall).
   Investigate immutable snapshots or narrowly copy-on-write witnesses so
   consumers cannot mutate cached authority. Preserve current key, route,
   policy, validation, independent replay and EQUAL publication gates.
   Risk: high; aliasing or shallow copies could silently contaminate later
   owners. Require adversarial mutation-isolation tests and exact output parity.
2. **Optimize analyzer implementation, not the number of required checks**
   (target `model_analyse`: 16.55% wall; the repeated-call count is not a time share).
   Profile inner loops and improve equivalent data structures; keep every
   independent analysis, validation, replay and per-owner EQUAL comparison.
   Risk: medium/high; changes can alter topology order, identity or tolerance
   behavior. Require full topology and transaction regression coverage.
3. **Avoid redundant memo key digest construction within an immutable input**
   (target `memo_digest`: 13.31% wall).
   Reuse a digest only with proven unchanged bytes, witness, policy and route;
   invalidate on every revision and preserve separate authority and all checks.
   Risk: high if stale key identity causes false cache hits. Require stale
   witness/source/policy/route and mutation negative tests before considering it.

## DECISIONS

1. Execute the checked-in Worker Python snippet instead of creating a second
   repair algorithm; mirror its serial selection/recheck receipt gates in the
   harness. No browser, no CII/Final release and no changes to the product.
2. Generate deterministic, straight synthetic geometry distributed across 41
   branches; 40 planted non-eligible spans use restraints. The Owner model's
   complexity and browser performance are not inferred from this fixture.
3. Use exclusive nested clocks, retaining inclusive per-call times for diagnosis;
   `other` is the measured residual, including probe overhead, JSON and scratch
   I/O. Full native parses are counted separately from fragment parsing.
4. Keep memo ON and the pinned reader unchanged; count the extra pre-Final
   replay, nested closure calls, and actual memo hits/misses separately.
5. Select first N eligible IDs in initial order, refresh authority each revision;
   account for known no-output refusals as skips and stop on unexpected drift.
6. No private data leaves the local harness; timing JSON contains ordinal,
   counts and durations only, no source bytes, paths, IDs or hashes. Only the
   invented aggregate is committed. Native Node CLI startup and disk I/O
   differ from browser/Pyodide; the Oracle runs the private file separately.

## FAILING

None. No browser or Owner-file run was attempted, by instruction.
Full repository suite not run; acceptance and targeted regressions above passed.
