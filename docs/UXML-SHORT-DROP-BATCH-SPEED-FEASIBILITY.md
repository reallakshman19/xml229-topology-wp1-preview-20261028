# UXML Short-Drop Batch Speed — baseline and architecture HOLD

**Task:** UXML-SHORT-DROP-BATCH-SPEED · Lane A · TopoFix issue #12 · draft PR #33  
**Base:** main `86f119bddb72e97d7518ab9d9ffb8b20faaa8cc8`  
**Source custody:** Public synthetic fixtures ONLY; no Owner-source data.
**Status:** Baseline measured; batch writer **NOT_STARTED / HOLD** on an architectural conflict requiring an Owner choice. No engine behavior or eligibility modified.

## Measured baseline before modifying the product

Run the pinned exact-branch CI measurement with:

```bash
python3 -B -m unittest discover -s tests -v
node --test tests/*.test.mjs
bash tools/fetch-uxml-reader.sh dist
XCU_UXML_ROOT=dist/vendor/uxml UXML_BATCH_BASELINE=1 \
  python3 -B -m unittest discover -s tests -p test_uxml_short_drop_batch_baseline.py -v
# Existing actual Worker/Pyodide test on pinned immutable runtime:
node --test tests/uxml-bulk-speed.browser.mjs
```

### Native Python — one owner, 60 interconnected TEE branches, 660 records

| Stage | Wall time (ms) | Scope |
|---|---:|---|
| Initial full-source resolve | 151.581 | Separate baseline source load |
| Eligibility for all 60 | 10.743 | Source owner witnesses |
| Pinned XCU CLI UXML read | 120.533 | One process invocation |
| Direct native short transaction | **1064.243** | Full remove/reconnect/revalidate |
| ↳ native XML parse | 6.271 | Included above |
| ↳ native XML serialize | 64.472 | Included above |
| ↳ post-removal resolve | 372.154 | Included above |
| ↳ nested closure transaction | 506.598 | Included above |
| ↳ post-closure resolve | 370.316 | **Included in** nested closure transaction |
| Canonical `export_edit_ops` | **613.185** | Rebuilds native authority |
| Original-file `apply_edit_ops` | **1237.982** | Rebuilds canonical authority and applies native |
| Direct/patch parity comparison | 3.643 | Exact sidecars + XML byte parity |
| Write validated output | 0.208 | New file only |
| **Measured full one-owner flow** | **3202.118** | No Owner source |

Profile (direct native only) top cumulative functions: `apply_short_element` 1.064s; `resolve_psi116` 2 calls 0.742s; `analyze_document` 2 calls 0.526s; `_analyze_connection_gaps` 2 calls 0.315s; `read_psi116_xml` 2 calls 0.216s; `build_topofix_source_lineage` 0.098s. **Nested rows overlap, do not sum them**.

This measurement is a one-owner stage probe. The existing five-owner sequential benchmark on the same 60-TEE geometry measured 23.30676s total, also only synthetic.

### Browser Worker / Pyodide — one owner, separate 339-record fixture

| Stage | Time (ms) |
|---|---:|
| Initial hub analysis | 1775.0 |
| Total one-item browser Apply | **1573.8** |
| Worker round trip | 1203.0 |
| Worker source SHA-256 | 0.6 |
| Load verified pinned reader | 24.8 |
| XCU UXML read / conversion | 15.2 |
| Pyodide engine | **1161.9** |
| ↳ Python topology | 1138.0 |
| ↳ parity | 53.4 |
| ↳ canonical patch compare | 577.3 |
| ↳ resolve | 42.1 |
| ↳ transaction | 175.9 |
| ↳ validation recheck | 275.1 |
| UI publish + recheck | 291.4 |

Exact evidence: [native CI #41415778483](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/actions/runs/41415778483) and [browser CI #41415778496](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/actions/runs/41415778496). Both completed SUCCESS at initial benchmark head `e58ebb41`. **Different fixture sizes and overlapping phases must not be compared directly or summed**.

The Owner's reported private source (~8,767 records, 89 selected) takes about **24 seconds per element in Pyodide** and **2.2 seconds per element natively**. Those figures are Owner-reported, **not reproduced here**. Achieving 89 in under 120 seconds means under **1.35s per element**, a roughly **17.8×** improvement over that Owner browser rate. This benchmark does not demonstrate that speedup.

## Structural blocker — exactly one request at every authority boundary

1. `short_elements.py:apply_short_element` refuses `len(policy.short_element_requests) != 1` with `Select one source-bound short element per atomic transaction.`
2. `transaction.py:apply_topofix_transaction` directs any nonempty short-request tuple to that single-owner routine.
3. `uxml_edit_ops.py:_short_canonical_operation` demands exactly one selected ID and one request (`UXML_SHORT_EXACT_ONE_REQUEST_REQUIRED`) before native-witness derivation, sourceRefs, loss contract and removedWithRecord handling.
4. `uxml_edit_ops.py:_validate_ops` requires exactly one canonical short operation; `apply_edit_ops` independently repeats the native transaction and original-source sourceRef checks.
5. `short-bulk.mjs` sends one `topologyShortElementRequests:[request]` and requires exactly one `editOps` receipt per committed item.

The baseline harness now probes **two different source-qualified short owners** on the same original interconnected source. Both the native and canonical interfaces reject multi-owner policies by design. This is a contract incompatibility, not an undocumented opportunity to pass an array. **Bypassing either guard would discard existing source-bound loss/authority protections**.

### Equivalence-runtime and speed conflict

The requested runtime equivalence gate says the multi-owner batch must be byte-identical to **actual serial native application of K requests** and bisect to singles on mismatch. If it recomputes that full serial baseline for every candidate in production, the gate itself incurs the cost of the old K native transactions (before the candidate's cost). Simply wrapping K single-element calls in one Worker invocation therefore cannot approach the under-two-minute Owner goal. To remove that cost safely requires a new formally specified source-order and independence witness and an Owner decision about **which runtime equivalence evidence is sufficient**, while retaining full actual serial byte equality for every synthetic K=2/5/20 test and public GRE/PLB314 test with matching eligible records.

## Owner decision requested (do not implement an unsafe fast path)

**A — recommended: Authorize a bounded batch-contract redesign with a structural runtime equivalence gate.** Extend native transaction, canonical UXML export, patch-side sourceRefs and loss checks together. First prove local independence of deletion sets, closure-owned records and global NodeNumber/graph effects; refuse and bisect overlaps. Runtime gate checks source-byte digest, deterministic write-set, per-owner witness, and full validation of the final combined candidate; CI must also compare actual serial native output bytes and per-owner refusal codes for K=2/5/20 + public fixtures. Keep K=16 disabled until these tests prove the contract. This changes the requested runtime gate from executing a full serial replay into a source-bound constructive proof; require explicit Owner authorization.

**B — keep exact online serial byte comparison** for every batch; accept that it preserves the old serial cost and is **not a credible under-two-minute solution** on the private model unless an additional deep serial-engine rewrite is authorized.

**C — retain serial Apply and authorize a separate shared-state cache/analysis performance spike** (reuse parsed source, canonical sourceRefs and UXML reader state) without changing write authority. Measure improvement first; do not claim the 89-owner target.

No product writer, native short-drop engine, workflow Apply, CLOS, policy/tolerance, loss contract, review-only Apply or Lane B files were changed on this measurement-only branch. Keep draft PR #33 HOLD. Oracle/Owner controls the next decision and private original-file timing.

## NOT_RUN

- K=2/5/20 batched native output (batch implementation not authorized yet by the existing authority interfaces).
- Public GRE/PLB314 batch equivalence (no batch implementation).
- Private Owner-source 89-item timing (private only, Oracle operator).
- No Writer/Worker batch path, no K=16 toggle or bisection (intentionally NOT_IMPLEMENTED).
- Independent non-author review / merge / release.


## Option C B1 · independent route custody and memo safety (2 Nov 2026, PR #33 repair)

**Historical caution:** The earlier measured option-C implementation indexed the
native transaction solely by original `sourceText`, policy, config and source
path. But the UXML adapter constructs records, geometry, weights, types,
findings and fix actions from UXML JSON; those records may differ even while
the embedded source text and SHA agree. Reusing a *direct-source* transaction
for UXML therefore made direct/patch comparison circular (B1 independent
review, 71/100). This is a safety defect, not an acceptable performance trade.

The repaired transaction key separates **all** of these inputs:

| Memo entry | Complete identity and input handling | Safety decision |
|---|---|---|
| `transaction` | Code-version tag, transaction kind, exact original UTF-8 source bytes SHA-256, every policy field, resolver-config digest, source path, **explicit `native` or `uxml` route**, plus digest of all analyzed document records, raw node fragments, occurrences/spans, findings, proposed actions/blockers and connection resolutions | Separate native and UXML misses are mandatory. Canonical export, canonical re-validation and patch application of the **same** unchanged UXML witness can reuse a UXML-route transaction; independent sourceRef/loss/policy validation still runs |
| `source_resolve` | Code version, exact current raw input bytes, config; parser/analyzer function fixed. The source path affects only receipt metadata and is rebound on an isolated cache copy | Independent source hash must differ when any input byte differs; no cached value may carry a stale returned source path. Note the cached path skips the parser's process-global `ET.register_namespace` side effect; callers must never rely on the cache miss to set serializer registry state |
| `uxml_resolve` | Code version, UXML `sourceText` bytes, complete canonical UXML JSON SHA-256 (including sourceRefs, raw fields and ports), config and source name. Noncanonical/injected resolver functions are **never cached** | A modified UXML field or adapter-injected function cannot reuse earlier analyzed evidence |
| `analyze_document` | **Not separately memoized**: it runs inside the two exact-input resolver entries above | No naked analysis-result cache lacking document/config provenance |

**Lifetime and clears:** A per-selection in-memory memo uses bounded deep-copy
stores, never disk or persistent state. Python `memo_session` restores its
previous state in `finally`; individual jobs clear in
`topology-integration.js` `finally`, engine ERROR clears in its `catch`;
normal bulk termination sends `SHORT_MEMO_CLEAR` through Worker queue to
`clearXml229ShortMemo`, and Cancel/model load terminates the Worker, losing
the entire Python heap. Tests explicitly execute these actual clear points and
kill mutants deleting their dispatch/cleanup.

The expected per-owner pattern on an untampered hub source is now **2 real
native short transactions + 2 memo hits**: one direct, one independent UXML,
then two repeat UXML calls. This deliberately sacrifices some of the old
unsafe memo's speed. A forged retained weight, position or type in UXML must
refuse ON with the same code as OFF; exact original XML bytes, sourceRefs and
independent validation remain binding. No unsafe shortcut is authorized.

**Timing ledger, synthetic only, before B1 repair:** 5 sequential synthetic
owners OFF 8.808s / ON 5.579s (1.58x); 20 OFF 35.600s / ON
24.957s (1.43x). One 660-record stage OFF 1,443ms / ON 904ms (1.60x);
single-item browser/Pyodide OFF 1,127ms / ON 697ms (1.62x). These
measurements represent the prior B1-defective memo and are NOT an approval
of its parity behavior. New exact-head timing must be taken after the
route-separated implementation and independently reviewed.

**Oracle Owner-model observation (ratio only, private data excluded):**
prior memo ON was **2.41x** OFF for the same local five-step session, with
fixed XML equality; this predates the B1 safety repair and is not a claim for
the new head. No Owner data or identifying source facts are recorded here.

**Still NOT_DONE:** item (4), skipping intermediate serialize/re-parse work,
and any multi-owner batching or structural shortcut. No CLOS, tolerance,
loss-contract, eligibility, review-only or one-owner policy changes.


### Post-B1 safety repair · measured synthetic ON/OFF at the route-separated implementation

Source-bound [Topology validation #41463916361](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/actions/runs/41463916361) and [browser #41463916282](https://github.com/reallakshman19/xml229-topology-wp1-preview-20261028/actions/runs/41463916282)
are **after** the route/document-digest safety change. The test-only circular-clear
cleanup that followed did not change product behavior. These measurements supersede
the earlier unsafe memo timing for any performance claim.

| Synthetic fixture / scope | Memo OFF | Memo ON | OFF / ON |
|---|---:|---:|---:|
| Interconnected 60-TEE, 5 sequential short owners, full sourceRef/canonical authority | 13.4294s | 10.4572s | 1.28x |
| Same 60-TEE, 20 owners, full sourceRef/canonical authority | 53.2981s | 42.7504s | 1.25x |
| One owner, same 660-record original, native full staged direct/export/patch | 2234.054ms | 1652.880ms | 1.35x |
| Genuine Chromium/Pyodide, separate 339-record fixture, one owner | 1485.9ms | 1348.8ms | 1.10x |

All synthetic ON/OFF corrected XML and required transaction/validation/ops/
refusal evidence were byte-for-byte equal. In the dedicated independent-route
two-transaction proof, the memo records **2 real transaction misses and 2
same-UXML hits**. The full browser job records **2 real misses and 3 hits**,
because its complete workflow repeats one additional already validated check;
this is not a third independent authority run.

Native same-source sub-stages (ms), OFF → ON: direct 410.432 → 620.494;
canonical export 559.470 → 589.301; canonical apply 1133.288 → 308.935;
original source resolve 135.969 → 163.878; pinned UXML reader CLI
114.999 → 114.017; final parity comparison 3.978 → 3.822. These are
nonadditive measurements subject to runner variance, not proof that the
native/direct analysis itself became faster.

**Why below 4x:** each route must independently perform one complete native
transaction. The canonical/sourceRef and loss checks, full original-XML
validation, changed-source parser/analyzer work, Worker mapping and UI
refresh also still run. The old 4-hits/one-real behavior was circular and is
prohibited. The earlier Oracle Owner-only **2.41x ratio** predates the repair;
new Owner original-file timing and any subsequent 89-owner estimate remain
**NOT_RUN** by the coder. Intermediate serialize/re-parse elimination is
**NOT_DONE** and is not covered by option C.
