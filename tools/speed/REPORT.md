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

## OWNER FILE (Oracle run)

Oracle-supplied aggregate only, at harness head `a66c7507eb6e8ee382a426bb9b4416631d40e8fd`:
Windows, native execution, 89/89 applied, **902.9 s total**, **10.15 s/owner**
(unrounded 10.14494 s/owner). No private source, identifiers, paths,
coordinates, hashes or raw receipts were obtained by this lane. No browser
timing is implied. These measured Owner-file shares supersede the synthetic
ranking for optimization selection; the synthetic results above remain historical.

| Exclusive stage | Wall share | Approx. s/owner | Calls / owner or repeat evidence |
|---|---:|---:|---|
| `memo_copy` | 17.87% | 1.81 | 15 |
| `lineage_recheck` | 16.58% | 1.68 | 5 |
| `memo_digest` | 12.61% | 1.28 | 51 |
| `other` | 9.52% | 0.97 | Not supplied |
| `native_transaction_nested` | 8.87% | 0.90 | 2; 1 repeat/owner |
| `parse` | 7.90% | 0.80 | 15; 1069 repeated fingerprints of 1336 calls |
| `model_analyse` | 7.89% | 0.80 | 3 |
| `uxml_reader` | 4.19% | 0.43 | Not supplied |
| `memo_other` | 3.07% | 0.31 | Not supplied |
| `native_transaction_direct` | 2.42% | 0.25 | Not supplied |
| `native_transaction_export` | 2.41% | 0.24 | Not supplied |
| `uxml_adapter` | 2.33% | 0.24 | Not supplied |
| `canonical_rederivation` | 1.50% | 0.15 | Not supplied |
| `canonical_export` | 1.42% | 0.14 | Not supplied |
| validate / apply / replay / patch_back / compare / hub_parity | <0.5% each | <0.051 each | Not supplied |

Percentages and durations are rounded; no unreported stage breakdown or
repeat-duration measurements have been invented. The top three Owner-file
stages are memo copy, lineage recheck and memo digest (47.06% combined).

## OPTIONS

Ranked by Owner-file measured addressable cost, not by assumed achievable
speedup. Each option below is independent, calculated from 902.9/89 s per
owner; do not add the savings or multiply them into a browser prediction.
The measured shares are ceilings on eligible stage cost, not proof that
the entire cost is removable. Conditional estimates assume equal cost per
call where only counts are known and no replacement overhead. Distinct
digest inputs and identical lineage contexts were not counted by the
Oracle run, so their true savings and runtime are NOT_RUN. No option is
implemented; no change to #34.

1. **Immutable memo, no defensive deep copies + one digest per distinct
   input**. Measured addressable share **30.48%** (17.87% copy + 12.61%
   digest; 15 copy and 51 digest calls/owner). Absolute stage-elimination
   floor **7.05 s/owner**, not attainable if digest work remains.
   With full elimination of the copy bucket and D distinct digest inputs
   per owner, estimated removable share is
   `17.87 + 12.61 * (51-D)/51` percent and expected time is
   `(902.9/89) * (1 - share/100)`. For an explicitly illustrative D=5,
   this is **29.24% / 7.18 s/owner**; D=5 is not measured.
   Count actual distinct immutable inputs (source, document, hub, config,
   policy and other digest payloads) and their costs before choosing a
   design. Keep route/version/provenance distinctions and every owner’s
   separate validated transaction, fresh revision, independent replay and
   EQUAL hub/patch parity; use genuinely immutable snapshots or isolated
   mutable materialization, never alias mutable cached state.
   Risk: high — mutable aliasing, stale digest keys and cross-route
   contamination; require mutation-isolation, stale-source/config/policy
   and exact byte-parity tests. New allocation/immutability costs must be
   included in an end-to-end benchmark.

2. **Reuse lineage subcomputations on identical bytes and authority**.
   Measured addressable share **16.58%** (5 calls/owner); absolute
   stage-elimination floor **8.46 s/owner**. If four of five
   equal-cost calls were safely reusable, the conditional removable
   share would be **13.26% / 8.80 s/owner**. This is a
   scenario, not a measured repeat count: lineage build and verification
   are different operations and identical bytes alone do not prove
   interchangeable evidence. Instrument exact inputs and distinct
   semantic contexts first. Cache only pure deterministic
   canonicalization/witness subcomputations keyed by exact source/fixed
   bytes, operations, revision, policy/config, route and schema/code
   version; independently verify the authoritative receipt and keep
   every owner’s own validated transaction, independent replay and
   EQUAL parity. Never reuse a successful verdict as a substitute for
   independent verification. Risk: high — stale lineage, masked
   witness/operation drift, or circular self-verification; require
   negative lineage mutants and independent reproduction tests.
   The nested transaction bucket (8.87%) is not added to this estimate.

3. **Exact-byte parse cache**. Measured addressable share **7.90%**;
   1069/1336 repeated fingerprints (80.01% of parse calls). Conditional
   equal-cost estimate **6.32% / 9.50 s/owner** if
   those repeats are all eligible and cache overhead is zero. Absolute
   stage-elimination floor **9.34 s/owner**. The repeat count
   is measured, but repeat time is not; parser, XML-root and clone
   functions have different output contracts, so distinguish operation,
   parser version/options and authority, key by exact bytes including BOM
   and line endings, invalidate on changed bytes/revision, and return
   immutable parse results or isolated trees. Keep each owner’s own
   transaction, all validation/replay and EQUAL hub/patch parity; do not
   skip a required independent parse/check merely because bytes match.
   Risk: medium/high — shared tree mutation, stale source identity,
   parser-mode collisions, memory pressure and new copying overhead;
   require CRLF/BOM, changed-byte, mutation-isolation and parity tests.

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
   invented aggregate and Oracle-supplied Owner-file counts/timings are committed. Native Node CLI startup and disk I/O
   differ from browser/Pyodide; the Oracle runs the private file separately.

## FAILING

None in the delivered harness tests. No browser run was attempted; the Oracle's
subsequent native Owner-file run is recorded above.
Full repository suite not run; acceptance and targeted regressions above passed.
