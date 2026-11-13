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


---

# L4-S2 — cheaper memo (13 Nov)

Base: `815ee7b7193c81988462307a726e69e9e03eff49`. Owner picked option (a) only.
No batch work, no parse cache, no lineage reuse, no changes to main or #34.
Historical status at 55efb090: T1/T2/T3/T5 PASS; the T4 legacy mutant failure was resolved at fb10b507 and freshly verified in round 2 below.
Not a merge recommendation; Owner/Oracle qualification is separate.

## MEASURED — invented 89-owner fixture

Same generator seed 116, 41 branches, 1,654 records, 89 eligible and 40
blocked short owners. Native Python and pinned Node reader (7/7 blob hashes).
Unchanged `tools/speed/measure.py` executes the Worker Python template.
Both memo ON and OFF applied all 89 owners, each EQUAL, with no skips and
byte-identical final corrected PSI116 (direct byte comparison, not only
a hash). Invented final SHA256:
`68d59d96e90ca92eb1927345e7a5bbfd3dd85527c0622ca7036ca6da64cc11a6`.
Original unchanged. No private file received; no browser run.

| Metric | S1 before (memo ON) | S2 after (memo ON) |
|---|---:|---:|
| Applied / attempted | 89/89 | 89/89 |
| Total wall seconds | 655.529 | 334.111 |
| Mean wall seconds/owner | 7.365 | 3.754 |
| Memo copy calls, total | 1335 | 0 |
| Memo copy calls/owner | 15 | 0 |
| Memo digest calls, total | 4539 | 446 |
| Memo digest calls/owner | 51 | 5.011 (max 6) |
| Transaction cache hits / misses | 267 / 178 | 267 / 178 |
| Lineage rechecks/owner | 5 | 5 |
| Hub parity calls/owner | 2 | 2 |

49.03% lower measured end-to-end owner wall, 1.962x speedup versus the
historical S1 fixture measurement. Independently executed S2 memo OFF:
750.219 s total, 8.429 s/owner, 89/89 EQUAL. Both independent processes
execute their owners serially; the ON and OFF processes run concurrently,
and some targeted regressions ran during the ON measurement. The S1
baseline is historical, not a fresh same-process A/B control. Do not
extrapolate the synthetic speedup to the Owner file (10.15 s/owner S1);
the requested ~7.2 s/owner Owner target is NOT_RUN at S2.

Exclusive stage seconds and calls from the unchanged meter:

| Stage | Before s | After s | Before calls | After calls |
|---|---:|---:|---:|---:|
| parse | 33.741 | 24.331 | 1336 | 1336 |
| model_analyse | 108.491 | 79.499 | 268 | 268 |
| resolve | 0.812 | 6.754 | 623 | 623 |
| native_transaction_direct | 8.499 | 24.444 | 89 | 89 |
| native_transaction_export | 8.550 | 24.165 | 89 | 89 |
| native_transaction_validate | 0.068 | 7.953 | 89 | 89 |
| native_transaction_apply | 0.154 | 7.714 | 89 | 89 |
| native_transaction_replay | 0.083 | 7.557 | 89 | 89 |
| native_transaction_nested | 32.083 | 24.549 | 178 | 178 |
| uxml_reader | 25.001 | 20.025 | 89 | 89 |
| uxml_adapter | 7.470 | 6.294 | 89 | 89 |
| canonical_export | 6.493 | 4.445 | 89 | 89 |
| canonical_rederivation | 8.335 | 4.790 | 89 | 89 |
| patch_back | 1.670 | 1.001 | 89 | 89 |
| patch_back_compare | 0.348 | 0.305 | 89 | 89 |
| hub_parity | 4.900 | 4.116 | 178 | 178 |
| lineage_recheck | 47.484 | 30.754 | 445 | 445 |
| memo_digest | 87.242 | 0.552 | 4539 | 446 |
| memo_copy | 200.272 | 0.000 | 1335 | 0 |
| memo_other | 12.118 | 13.560 | 267 | 267 |
| other | 61.717 | 41.304 | 89 | 89 |
| TOTAL | 655.529 | 334.111 | — | — |

Rounded stage sums may differ slightly from total. Per-owner exact stage
accounting residual error is zero. After: owner wall range 3.326–4.163 s.
Every owner had 0 memo_copy calls; first owner 6 memo_digest calls,
remaining 88 owners 5 each. Every owner has one direct/export/validate/
apply/replay call, 2 nested calls, 5 lineage calls, 2 hub parity calls,
1 patch-back comparison, 2 transaction misses and 3 hits. Aggregate
source-resolve hits/misses 444/179 and UXML-resolve hits/misses 178/89,
unchanged. No change to per-owner safety checks.

**Meter attribution caveat:** the old memo_digest hook included canonical
serialization inside _document_digest. S2 canonicalizes before exact-byte
cache lookup; the meter now counts actual digest computations on misses,
not canonicalization or byte-hash/equality lookup. memo_copy is specifically
the existing deepcopy hook; immutable snapshot creation and mutable
evidence materialization still cost time in their calling stages. Thus
the before/after *wall time*, not the disappearance of named buckets,
is the primary performance measure. A separate five-owner diagnostic
(on the same full-sized fixture, temporary local probes, not committed)
measured 19.553 s wall, 5/5 EQUAL; exclusive local totals:
canonical JSON 3.120 s / 170 calls, snapshot 0.852 s / 26 calls,
restore 0.266 s / 49 calls, cached-digest lookup 0.125 s / 170 calls,
document-bytes wrapper 0.0005 s / 35 calls. These are supplemental
overlapping-with-main-meter measurements; do not add to full-run totals.
Serialization cost remains; no claim of zero copying or zero digest
lookup overhead.

## Implementation and callers

Only product change: `converters/psi116_topology_resolver/short_memo.py`.
The existing cache keys retain exact source bytes, code version, policy,
config, source path, route, full analyzed document witness and complete
UXML provenance. Bump code version; test compares canonical witness and
config/policy SHA against the original asdict-based encoding. The digest
cache keys are actual immutable bytes, not an object identity or claimed
source SHA. Python dict equality guards hash collisions; on different
bytes a new digest is required. Bound digest LRU to 32 entries / 64 MiB,
eviction is a miss not a semantic change. Immutable default config digest
is precomputed once, reused only after exact canonical-byte equality.
Keep the document-digest mutation seam on cache misses.

Store internal snapshots as immutable pickle bytes plus recursively verified
frozen geometry references. Only trusted in-process results are serialized;
no external pickle is accepted. Geometry classes are frozen dataclasses
containing only verified frozen geometry, tuples and immutable scalars.
Ordinary attribute mutation fails; this is Python's frozen dataclass
contract, not a sandbox against deliberate reflection bypasses. All mutable
receipt fields are materialized independently from immutable bytes on hit,
and store captures them before returning the original miss result. If a
document cannot be proven frozen, serialize it with the remaining result.
No defensive whole-result deepcopy on hits or insertion.

Call-site audit (no changes needed):
- `resolver.py:resolve_psi116` calls source_resolve; path rebinding in
  short_memo uses dataclasses.replace, not mutation of shared geometry.
- `transaction.py:apply_topofix_transaction` is the transaction lookup /
  store caller. The native transaction/short_elements modifies a separate
  parsed XML tree and constructs new receipts. No observed mutation of
  a cached geometry or cached result by the call site.
- `uxml_edit_ops.py:export_edit_ops` and `apply_edit_ops` use uxml_resolve;
  they build operations/validation from result data, independently check
  original sourceRefs and run native transaction/compare. No observed
  mutation of a returned result by these callers.
- `lineage.py` builds/verifies lineage from receipts and its own XML
  trees; its deepcopy of an XML node is not memo deepcopy and is unchanged.
- Public mutable evidence includes Finding.details, FixAction.proposed_changes,
  ResolutionResult.connection_resolutions (findings_payload returns a list
  of those dictionaries), TransactionPolicy request dictionaries/lists,
  AppliedOperation before/after, and ValidationCheck.details.
  The existing test_one_owner_memo_is_exact_and_deep_copied and new T2
  deliberately mutate returned ValidationCheck.details; generic T2 also
  mutates nested lists/dicts after insertion and on hit. These callers get
  independent mutable evidence, not mutable cached state. To preserve
  public type/API behavior, mutable evidence is materialized on each hit,
  not lazily at the first mutation. No full geometry copy on normal hits.
  This is a deliberate compatibility tradeoff; it leaves the residual
  materialization cost reported above.

## Tests and mutations

- New acceptance: `python3 -B -m unittest discover -s tests -p test_short_memo_cheap.py -v`
  **6/6 PASS** in 751.839 s (pinned XCU_UXML_ROOT). T1 full 89-owner ON/OFF
  bytes equal; T2 nested mutation isolation and frozen geometry; T3 actual
  hash counts/exact bytes plus canonical witness, mutable policy/config and
  route; T5 every owner meets both ceilings and all check counts.
- Unchanged targeted Python regression:
  `UXML_SHORT_MEMO_EQUIVALENCE=1 python3 -B -m unittest test_short_elements test_short_length_basis test_short_namespace_replay test_uxml_short_memo -v`
  (PYTHONPATH=tests:converters) **25/26 PASS**, one legacy mutant FAIL below.
  Opt-in five/twenty-owner byte+receipt equivalence PASS; clean-vs-tampered
  UXML refusal, provenance and route mutants PASS. 5-owner ON/OFF
  4.9482/10.0224 s; 20-owner ON/OFF 19.7138/39.8488 s.
- Unchanged `UXML_SHORT_MEMO_STAGE_PROFILE=1 python3 -B -m unittest test_uxml_short_memo_stage_profile test_uxml_short_drop_hub -v`
  (PYTHONPATH=tests:converters): **14/14 PASS**.
- Unchanged `node --test tests/short-memo-*.test.mjs tests/short-bulk*.test.mjs tests/short-direct-apply-*.test.mjs`:
  **51/51 PASS**.
- Formal test total **96/97** (no skips). Extra temporary CRLF+BOM
  full-path five-owner ON/OFF test 1/1 PASS, not included in formal total.
  No full repository suite or browser run attempted.
- M1 replace _snapshot and _restore with identity (store and return mutable
  object): T2 isolation assertion RED. M2 simulate recycled id-only digest
  cache without bytes guard: T3 exact-digest assertion RED. M3 skip lineage
  verification and accept forged receipt: lineage refusal assertion RED.
  Controls GREEN. New mutation checks run as part of the six acceptance
  tests; no mutant retained in product. Original policy, byte, provenance,
  route, session-cleanup mutation tests also retain their RED witnesses.

## DECISIONS (S2, six)

1. Internal immutable byte snapshots with verified frozen geometry sharing,
   preserving mutable public receipt values by independent materialization
   rather than a risky new lazy wrapper API. No ordinary cached mutation.
2. Actual byte-key LRU bounded to 32 / 64 MiB; precompute only the immutable
   default-config digest and require exact equality before reuse. No id-only
   shortcut. Retain all key dimensions and bump code version.
3. Canonical serialization by dataclass fields instead of recursive asdict;
   retain the independent document-digest seam on misses, and distinguish
   SHA computations from serialization and snapshot overhead in the report.
4. Retain the old deepcopy import solely for existing measurement/test
   compatibility; do not fake a vulnerable hit path to make the obsolete
   deepcopy-only mutant green. Leave old tests byte-unchanged; add M1 against
   the actual new custody boundary and report the old test as FAIL.
5. No call-site changes and no alterations to short-drop authority, lineage,
   parity, resolver, reader, publication, tolerance or #34. Audit mutable
   evidence and preserve ordinary public mutation isolation.
6. Compare against historical S1 fixture wall and report independent
   memo-off control. Disclose concurrent measurement, residual cost and
   no S2 Owner/browser timing; do not claim the private-file target met.

## Touched files (S2)

- converters/psi116_topology_resolver/short_memo.py (sole product file)
- tests/test_short_memo_cheap.py (new T1–T5 acceptance/mutation tests)
- tools/speed/REPORT.md (this append; S1 history retained)

## HISTORICAL FAILING (S2 at 55efb090; resolved at fb10b507)

**T4 FAIL**: unchanged
`test_uxml_short_memo.ShortMemoSafety.test_mutant_without_deepcopy_fails_clean_evidence_assertion`
fails with `AssertionError: AssertionError not raised`. Reproduced in more
than three runs. It monkeypatches the now-unused memo.deepcopy to identity
and demands the next hit be poisoned. The new immutable snapshot still
isolates the mutation, so its implementation-specific negative assertion
does not fire. The original functional isolation test passes and the new
M1 mutation of the actual storage/restore boundary is RED. No legacy test
was edited or weakened, and no deliberately vulnerable normal path was
introduced. T4 is not all-green; a separately authorized replacement of the
legacy mutant is required before claiming unchanged suite PASS. S2 delivered
for Owner/Oracle review under the three-tries rule. No other observed
test failure.


### S2 follow-up — Oracle-authorized isolation mutant replacement

Parent: `55efb0908e8e7b4104ad438b41ce8c028a2b2b4c`. The historical T4 failure above is resolved by
the test-only change below; the original measurement and test receipts remain
as historical evidence. No product or harness code changed.

- Retained the name
  `test_uxml_short_memo.ShortMemoSafety.test_mutant_without_deepcopy_fails_clean_evidence_assertion`
  for continuity. It now runs the same clean-evidence assertion against a
  normal memo session (GREEN) and a fresh session whose snapshot **and**
  restore boundaries are replaced with identity (RED). Both paths commit
  and demonstrate at least two actual transaction cache hits. The mutant
  returns mutable shared evidence; poisoning the first hit makes the next
  hit fail the exact `MEMO_CLEAN_EVIDENCE_REQUIRED` assertion. An unrelated
  assertion failure cannot satisfy the expected RED. No deletion or skip.

- Fresh targeted run (pinned reader, default opt-in flags):
  `PYTHONPATH=tests:converters python3 -B -m unittest test_short_memo_cheap.CheapMemoSafety test_uxml_short_memo test_uxml_short_memo_stage_profile -v`.
  12 passed / 14 discovered, 2 skipped, 0 failed; replacement mutant
  GREEN/RED verified. The two full-fixture tests T1 and T5 are unchanged
  (test file blob `2787bd5b7060bdfade1436a235331f1be0030500`,
  product memo blob `c43c67a862e197dd3272209a0bdf654669f1b747`);
  their PASS results are carried forward from the delivered 89-owner
  execution at the parent, also covered by the Oracle run. They were not
  rerun for this test-only change. Combined qualification for the three
  requested files: **14/16 PASS, 2 skipped, 0 FAIL**.

- The two default skips are unchanged opt-in tests:
  1. `test_uxml_short_memo.ShortMemoSafety.test_explicit_five_and_twenty_owner_memo_equivalence`:
     requires `UXML_SHORT_MEMO_EQUIVALENCE=1` and the pinned reader via
     `XCU_UXML_ROOT`. It exercises 5- and 20-owner memo ON/OFF equivalence
     and route/provenance mutants.
  2. `test_uxml_short_memo_stage_profile.MemoStageProfile.test_one_source_660_records_full_direct_export_patch`:
     requires `UXML_SHORT_MEMO_STAGE_PROFILE=1` and the pinned reader via
     `XCU_UXML_ROOT`. It profiles the 660-record full direct/export/patch path.
  Both opt-ins passed at the parent with their flags explicitly enabled;
  neither was rerun here. Their default skip gates were not changed.

- DECISIONS: retain historical test name; require the specific contamination
  assertion under the equivalent mutant; carry forward unchanged long-run
  evidence and explicitly distinguish it from fresh tests.
- Touched files: `tests/test_uxml_short_memo.py`, `tools/speed/REPORT.md`.
- FAILING: none in this follow-up's fresh default tests. The two skips
  remain intentional. No new Owner-file or browser measurement.


---

# L4-S2 round 2 — remove residual memo cost (13 Nov)

Parent: `fb10b507ab259165e9825c20dfcf3354e3ac6ba1`.
Sole product change is `short_memo.py`. No change to parser, analyzer,
transaction validation, lineage, hub parity, source selection, policy,
tolerances, Final/CII authority or #34. This is the last requested round.

## OWNER FILE (Oracle S2 run)

Oracle reported Windows native, S2 `55efb090` versus S1 `a66c7507`:
89/89 EQUAL both, 902.9 → 812.1 s (-10.06%; target ~-30% not met),
10.15 → 9.12 s/owner. Counts/timings only, no Owner data received.

| Stage | S1 s | S2 s | Calls where supplied |
|---|---:|---:|---|
| memo_copy | 161.3 | 0.0 | 15/owner → 0 |
| memo_digest | 113.8 | 3.9 | 51/owner → 446 total (~5/owner) |
| parse | 71.3 | 88.3 | 1336 both |
| model_analyse | 71.2 | 93.4 | 268 both |
| memo_other | 27.7 | 40.8 | 267 both |
| lineage_recheck | 149.7 | 146.0 | unchanged |
| other | 86.0 | 85.7 | unchanged |

The two named memo buckets save 271.2 s, but total wall saves only 90.8 s;
parse/analyse/memo_other rise by 52.3 s together. The other unreported
stages account for the remaining net difference; no guessed breakdown.

## WHERE THE TIME GOES / diagnosis

The existing meter encloses actual parse/analyze calls. Snapshot creation
and mutable-evidence restoration are outside those functions; the direct
memo cost is not literally nested inside those clocks. However the S2
implementation created a new Pickler/Unpickler class per store/hit. These
classes close over `shared`, forming cyclic references retaining the full
geometry after caller references are dropped. A controlled weak-reference
probe with automatic GC temporarily disabled (test only) demonstrated:
parent document alive before explicit full collection, released after;
round 2 document released immediately before collection. This is a real
lifetime defect and a mechanism for GC pauses to be charged to subsequent
parser/analyzer stages. No product GC settings are changed.

The S2 `_document_bytes` also reconstructed the full canonical geometry
JSON on every transaction key request. A five-owner probe on the full
invented fixture showed 35 document serializations in both versions,
2.656 → 1.387 s inclusive document serialization; all JSON serialization
3.248 → 1.646 s; snapshot construction 0.857 → 0.536 s; restore
0.266 → 0.294 s. Probe wall 19.761 → 18.749 s, EQUAL 5/5. This probe
used temporary local wrappers (not product changes); after probe overlapped
other testing. GC time within parse was 0.256 → 0.289 s, within analysis
0.098 → 0.096 s. It does not prove that all of the Windows per-call
increase is caused by GC, or that the private slowdown has been eliminated.

A separate five-owner retention probe forced a full collection outside
each timed owner interval. Mean retained geometry graph identities
7.6 → 4; mean live NodeRecords after collection 14,193.2 → 8,250;
mean forced full-GC wall 0.11228 → 0.11242 s. Both 5/5 EQUAL.
This demonstrates less retained geometry, but not a reduction in full-GC
duration in the small probe. No forced collection in product or in the
89-owner benchmark.

## Implementation

- Module-level codec classes remove the transient class/closure cycles.
  Verified frozen geometry stays shared; mutable policy, findings,
  action, check and operation evidence still materialize independently
  from internally generated immutable pickle bytes. No external pickle input.
- Six-entry weak geometry-projection LRU: certify the entire topology
  graph recursively once per live immutable tuple identity. A weak
  reference must still resolve and all three topology tuple identities
  must match; stale/recycled identity misses and re-verifies. Cache only
  canonical JSON fragments of `branches`, `occurrences`, `spans`;
  namespace and every mutable evidence field are serialized freshly.
  Reconstruct exactly the previous canonical JSON bytes; source bytes,
  source path, route, policy, config, document and UXML provenance retain
  their distinct key dimensions. Digest cache still keyed by exact bytes,
  not object identity. Full 1,654-record witness independently matched
  original asdict-based canonical encoding byte-for-byte (5,417,953 bytes).
- Tighten existing result LRU limits to 2 transaction / 3 source / 1 UXML
  entries for the common serial path; eviction is a fresh computation,
  never a bypass. Fresh fixture retains all original hit/miss counts.
  Geometry certificate weak refs do not prolong live model lifetimes;
  canonical fragments are bounded by entry count, not a new byte budget.
  Other workloads can incur extra cache misses, and memory tradeoffs need
  Owner/Oracle qualification. CODE_VERSION bumped for changed custody.
- No changes to actual parse/analyze implementation, no parse cache,
  no lineage reuse, and no cross-owner merging. The measured residual
  saving is chiefly in the transaction-key construction stages, not
  a guarantee of improved parse/analyse wall on Windows.

## MEASURED — fresh paired invented 89-owner fixture

Fresh parent control uses verified parent memo blob
`c43c67a862e197dd3272209a0bdf654669f1b747` and parent measure blob
`0acb6c285a157db0a0ea60366e02c503aefa2bfd`. Same seed 116, 41 branches,
1,654 records, 89 eligible short GASK owners, pinned reader 7/7, native
same sandbox. The new ON and old ON processes execute one after the other,
each alongside the independent new memo-OFF process; some short tests ran
concurrently. This is a fresh same-host comparison, not a randomized or
isolated timing study. Both ON runs 89/89 EQUAL, no skips. The historical
S2 fixture run is shown separately for transparency. Stage time is exclusive.

- Fresh parent 340.553 s (3.826 s/owner); round 2 301.578 s (3.389 s/owner), 11.44% lower wall.
- Historical S2 334.111 s; round 2 9.74% lower versus that prior run.

| Stage | Historical S2 s | Fresh parent s | Round 2 s | Calls parent → round 2 |
|---|---:|---:|---:|---:|
| `parse` | 24.331 | 24.250 | 23.221 | 1336 → 1336 |
| `model_analyse` | 79.499 | 81.259 | 81.768 | 268 → 268 |
| `resolve` | 6.754 | 7.207 | 6.541 | 623 → 623 |
| `native_transaction_direct` | 24.444 | 27.090 | 17.359 | 89 → 89 |
| `native_transaction_export` | 24.165 | 24.229 | 16.582 | 89 → 89 |
| `native_transaction_validate` | 7.953 | 8.151 | 2.728 | 89 → 89 |
| `native_transaction_apply` | 7.714 | 8.100 | 2.567 | 89 → 89 |
| `native_transaction_replay` | 7.557 | 7.873 | 2.339 | 89 → 89 |
| `native_transaction_nested` | 24.549 | 25.008 | 23.569 | 178 → 178 |
| `uxml_reader` | 20.025 | 20.352 | 20.291 | 89 → 89 |
| `uxml_adapter` | 6.294 | 6.491 | 6.296 | 89 → 89 |
| `canonical_export` | 4.445 | 4.727 | 4.839 | 89 → 89 |
| `canonical_rederivation` | 4.790 | 4.851 | 4.471 | 89 → 89 |
| `patch_back` | 1.001 | 1.045 | 0.998 | 89 → 89 |
| `patch_back_compare` | 0.305 | 0.310 | 0.309 | 89 → 89 |
| `hub_parity` | 4.116 | 4.206 | 4.197 | 178 → 178 |
| `lineage_recheck` | 30.754 | 31.581 | 30.462 | 445 → 445 |
| `memo_digest` | 0.552 | 0.546 | 0.557 | 446 → 446 |
| `memo_copy` | 0.000 | 0.000 | 0.000 | 0 → 0 |
| `memo_other` | 13.560 | 13.781 | 13.479 | 267 → 267 |
| `other` | 41.304 | 39.496 | 39.007 | 89 → 89 |
| TOTAL | 334.111 | 340.553 | 301.578 | — |

Both memo-ON runs preserve 1,336 parses, 268 model analyses, 267 transaction
hits, 178 transaction misses, 445 lineage rechecks and 178 hub comparisons.
Round 2 maximum digest calls per owner 6 (446 total); zero deep-copy calls.
All five outer transaction calls and two nested calls remain per owner,
plus one patch-back comparison. No stage sum drift; exact final output
matches the previously delivered invented output. Fresh independent
memo-OFF 89/89 EQUAL: 758.728 s, 8.525 s/owner, byte-identical to
round-2 memo-ON. No S2 round-2 Owner-file or browser timing is claimed.

Parse improves 1.029 s and memo_other 0.302 s versus fresh parent;
model_analyse increases 0.509 s. The requested elimination of the Owner
per-call slowdown has not been demonstrated. The measured 11.44% overall
fixture saving is real for these runs but should not be extrapolated
to a private model. No claim that the ~7.2 s/owner Owner target is met.

## Local final-byte qualification

The diagnostic CLI now supports actual memo disable (independent of the
measurement toggle) and binary final output. For the Oracle, replace
paths with local private paths; do not send XML back to this lane:

```sh
python3 -B tools/speed/measure.py /local/path/to/model.xml --owners 89 --out /local/path/to/on.json --final-out /local/path/to/on.xml
python3 -B tools/speed/measure.py /local/path/to/model.xml --owners 89 --memo-off --out /local/path/to/off.json --final-out /local/path/to/off.xml
python3 -B -c "from pathlib import Path; assert Path('/local/path/to/on.xml').read_bytes() == Path('/local/path/to/off.xml').read_bytes(); print('BYTE EQUAL')"
```

All files must be new; final output cannot alias source or report, and
is written only after every selected owner applied with EQUAL. No
Final/CII release is authorized. Timing JSON remains counts/timings only.

## Tests (all fresh)

`XCU_UXML_ROOT=<pinned-reader> UXML_SHORT_MEMO_EQUIVALENCE=1 UXML_SHORT_MEMO_STAGE_PROFILE=1 PYTHONPATH=tests:converters python3 -B -m unittest test_short_memo_cheap test_uxml_short_memo test_uxml_short_memo_stage_profile -v`:
**16/16 PASS in 836.056 s, zero skipped, zero failed**. Both formerly
skipped opt-ins explicitly executed. Full 89-owner ON/OFF byte comparison
and per-owner digest/copy/check ceilings PASS. Five/twenty-owner opt-in
ON/OFF times 4.7351/9.8277 s and 17.9622/39.3519 s; 660-record stage
profile ON/OFF 760.004/1688.487 ms, exact receipt and byte equivalence.
The lifetime assertion was added after launching the full suite and was
also executed freshly in the final test-file safety class (4/4 PASS);
the two full-fixture tests and all other definitions were unchanged.
No prior-run test result carried forward.

The historically named
`test_mutant_without_deepcopy_fails_clean_evidence_assertion` **PASS**
in this fresh run; the snapshot/restore identity mutant at fb10b507
produces `MUTANT_RED:shared-result-no-snapshot` and the unmutated
control is GREEN. No skip, no old deepcopy-only assertion.
M1/M2/M3 and independent policy/source/route/provenance/cleanup mutants
RED. Added mutable witness, namespace, changed frozen graph, malformed
mutable geometry, deliberately misdirected identity and snapshot
lifetime assertions PASS.

Additional fresh tests: speed-tools **5/5 PASS** (including new
CRLF+BOM final-out memo ON/OFF exact bytes, source/output collision
refusal and no overwrite); `node --test tests/short-memo-*.test.mjs`
**13/13 PASS**. No browser or private file run.

## DECISIONS (round 2)

- Fix the demonstrated reference lifetime defect, without changing
  product GC settings or moving stage clocks.
- Cache only verified immutable geometry projections, preserve mutable
  evidence recanonicalization and exact-byte digest equality.
- Reduce result retention for the common serial path; accept safe
  recomputation on eviction. Keep the old mutant name and new mechanism.
- Add diagnostic-only local binary output and explicit memo-off; preserve
  default measurement and every independent Worker check.
- Use fresh same-host full fixture comparison plus separate diagnostic
  probes; disclose concurrent load, unproven Owner attribution and the
  small model_analyse regression.

## Touched files (round 2)

- converters/psi116_topology_resolver/short_memo.py (sole product change)
- tests/test_short_memo_cheap.py (additional safety assertions)
- tools/speed/measure.py (CLI options)
- tools/speed/test_speed_tools.py (binary final-output test)
- tools/speed/README.md (Oracle local comparison instructions)
- tools/speed/REPORT.md (this report and historical-status clarification)

## FAILING (round 2)

No test failures or skips. Owner performance remains NOT_RUN for round 2;
the per-call Windows slowdown is not fully explained by the measured
synthetic probes. The model_analyse stage is slightly slower on the
fresh synthetic comparison. No further card or merge authorization.


# L4-S2b — review test gaps and honest custody meter

Base: `8603aa311f7211abbd9247cc69c6c81fb771dda2` (merged PR #38). Owner/Oracle supplied the
post-merge EF-05 results: 902.9 s → 638.7 s memo-on (29.26% lower),
1316.4 s memo-off, byte-identical final output and EQUAL 89/89; fresh
review PASS 88, no correctness defect. These are supplied historical
results, not a new private-file run by this lane.

## Changes

- T3 now inserts a slot containing a dead weak reference and another
  document's stale canonical fragments under a live document's tuple-id
  key. The uncached, freshly recomputed witness must equal the returned
  bytes.
- T3 also constructs a list nested in a BranchRecord's nodes field,
  with the outer branches tuple intact. It must be rejected for geometry
  sharing; the stored result is restored independently, its list cleared,
  and a second restoration must retain the original list. The original
  input must also remain intact.
- The native diagnostic meter wraps both _snapshot and _restore as
  memo_copy, retaining the deepcopy hook. T5 counts real custody work:
  calls must equal the sum of actual memo hits and stores for each owner,
  be positive, and be at most 15. The earlier ceiling of two counted
  only deepcopy and would be invalid for the expanded definition.
  The digest ceiling of six and all transaction, parity, lineage and
  patch-back checks are unchanged. The five-owner speed-tools test
  also checks the custody count against actual counters.
- Product changes are three comments only: session caches are not
  thread-safe (serial callers today); object.__setattr__ on shared frozen
  models is outside the contract; digest compute is a test seam for the
  same SHA-256 operation over exact canonical bytes, not a key dimension.
  No algorithm, cache policy, authority, key or production behavior changed.

## Exact review mutants

Both executed individually against T3 on the final test file, with
only the indicated temporary source mutation. Clean control PASS.
Both runs failed at the intended assertion (exit 1); the clean
product blob was restored and hash-verified before regression runs.

| Mutation | Result | Assertion |
|---|---|---|
| Replace `previous is not None and all(...)` with `previous is None or all(...)` | RED | DEAD_GEOMETRY_SLOT_REUSED_STALE_BYTES |
| Replace `if kind is tuple:` with `if kind in (tuple, list):` in recursive immutability check | RED | NESTED_MUTABLE_GEOMETRY_SHARED |

Neither mutant is committed.

## Fresh test evidence

Exact merged-base files reconstructed from the supplied pre-S1 archive
and verified changed Git blobs; pinned reader verified against all seven
blob hashes (XCU commit 9f51bfcaf98af4041ec0c0615dc67c9c357b0632).
Python 3.13.5, Node 22.16.0; invented fixtures only.

- Python memo: **16/16 PASS**, including full 89-owner byte-identical
  comparison and T5 meter/check ceilings, the T3 clean control, and
  all legacy memo and stage-profile tests. Both opt-ins enabled
  (`UXML_SHORT_MEMO_EQUIVALENCE=1`, `UXML_SHORT_MEMO_STAGE_PROFILE=1`);
  14 non-full-fixture tests also passed independently in 83.641 s.
- Speed-tools: **5/5 PASS** (11.669 s), including CLI counter equality,
  final-out parity, CRLF+BOM and non-overwrite.
- Node memo: **13/13 PASS** (`node --test tests/short-memo-*.test.mjs`).
- **34/34 distinct fresh tests PASS**, no skips; two additional expected
  mutant failures are not counted as clean test failures.

Reproduction from repository root, with the pinned reader environment
set to its local directory:

```sh
XCU_UXML_ROOT=<pinned-reader> UXML_SHORT_MEMO_EQUIVALENCE=1 UXML_SHORT_MEMO_STAGE_PROFILE=1 PYTHONPATH=tests:converters python3 -B -m unittest test_short_memo_cheap test_uxml_short_memo test_uxml_short_memo_stage_profile -v
XCU_UXML_ROOT=<pinned-reader> python3 -B -m unittest discover -s tools/speed -p test_speed_tools.py -v
node --test tests/short-memo-*.test.mjs
```

Fresh invented full-fixture memo-on: 89/89 EQUAL, zero skips,
325.677 s (3.659 s/owner). Memo-off also 89/89 EQUAL, zero skips;
final bytes identical. The newly inclusive custody definition records
1335 calls (exactly 15 each owner), 16.302 s exclusive total; all 89
owners' counts match the hit/store counters. Memo digest: 446 calls,
max six per owner, 0.564 s exclusive total. Lineage rechecks 445,
hub comparisons 178, patch-back comparisons 89. The previous
deepcopy-only zero measurement and this expanded custody measurement
are not directly comparable. Concurrent ON/OFF runs and additional
tests introduce timing contention; these diagnostics do not claim a
new performance gain or regression for the unchanged product.

## DECISIONS (S2b)

1. Extend existing T3 rather than introduce artificial test-only product
   hooks; kill the exact review mutants on temporary source and restore.
2. Expand memo_copy to actual custody and keep T5 meaningful through
   positive per-owner counter equality and the observed 15-call ceiling;
   retain existing six-digest and independent check ceilings.
3. Keep exact byte digest keys unchanged: both internal compute paths
   hash the same bytes with SHA-256. Document the serial/thread and
   frozen-object contracts without changing behavior.
4. Record fresh invented-fixture and supplied Owner results separately;
   do not rerun private Owner data or infer a new speed improvement.

## Touched files (S2b)

- converters/psi116_topology_resolver/short_memo.py (comments only)
- tests/test_short_memo_cheap.py
- tools/speed/measure.py (meter only)
- tools/speed/test_speed_tools.py
- tools/speed/README.md
- tools/speed/REPORT.md

## FAILING (S2b)

None. No browser or private-file rerun; the two requested mutations
are RED by design. No merge or further behavior change authorized.
