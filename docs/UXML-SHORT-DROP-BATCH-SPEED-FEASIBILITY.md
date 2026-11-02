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
