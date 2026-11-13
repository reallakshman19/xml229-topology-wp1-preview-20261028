# Lanes A / B / C: TopoFix on UXML, edits back to XML, transfer to CII

4 Nov 2026 · TopoFix Oracle · draft for the Owner. This follows the method in `STEP-BY-STEP-WBS-TEMPLATE.md`: one card at a time, a gate after each step, and a prototype on real inputs before any merge.

## Owner's split (4 Nov)

| Lane | Coder | Owns |
|---|---|---|
| **A** | coder-a6 (chat `6aeb3e9a`) | **TopoFix on XML/UXML.** It finds problems and produces fixes as edit operations on the hub. |
| **B** | coder-b7 (chat `6aeb2e0a`) | **XML → UXML, and its edit.** Readers, plus a patch-back that writes edits into the original XML. It hands a patched XML and an edit ledger to lane C. |
| **C** | coder-c1 (new chat, needs Owner yes) | **Transfer to CII.** It takes lane B's output and carries the edits into a CAESAR II `.cii`. |

Chain: `XML (PSI116 / InputXML / Categorized) → UXML → TopoFix (A) → edit ops → patch original XML (B) → CII (C)`

## What exists today (Oracle read, 4 Nov)

- **XCU main `ddd3ebc7`** (lane B's base):
  - readers: PSI116, strict InputXML (S3), Categorized (S4.0/S4.1);
  - patch-backs of the original InputXML: S4.2, B7 and B8 (Categorized-view value edits);
  - B8 leftovers PR #256 PASS 92, waiting for the Owner's prototype and merge;
  - a CII toolkit: `converters/xml-cii2019-core/*` and a CII **Writer2**, which mutates an existing CII and keeps the other bytes, with a frozen benchmark ladder (`ciibenchmarkroadmap.md`).
- **TopoFix main `f4509b5a`** (lane A's base):
  - PSI116 only, by direct route or hub route: findings, short drop, Autofix and the memo speed-up.
  - **Not in main:**
    - InputXML into TopoFix: draft #18, PASS 94, 29 commits behind.
    - InputXML patch-back: draft #23, PASS 93, 47 commits behind.
- **CII is blocked by design in TopoFix:**
  - `useTopoFixForCii:false` and `nativeCiiReleaseAuthorized:false` everywhere.
  - The worker refuses CII jobs.
  - The vendored engine can switch CII input to the committed TopoFix XML (`topology-integration.js:415`), but it is never enabled.
  - Native CII release needs engineering acceptance (README: 3D_Converters PR #346).
- **Overlap warning:** rigid Task 2 is changing the 3D_Converters `xml_to_cii2019*.py` converter. Lane C must not edit those files while Task 2 is open.

## Interfaces (the reason for one shared contract)

1. **A → B, edit ops:** TopoFix's `uxml_edit_ops.py` ops (op kind, `sourceRefs {format, fileSha256, recordKey}`, before and after values).
2. **B → C, hand-off package:**
   - the patched original XML;
   - an **edit ledger** (per edit: record, field, before, after, and op kind);
   - parity EQUAL, meaning the patched XML is re-read and only the ledgered records differ.

## WBS

Labels: **DISCOVER_FIRST** is read-only, and reports facts before any design. Evidence: L0 read, L1 coder harness, L2 Oracle runner on a real checkout, L3 browser, L4 Owner trial.

### Stage 0: learn (in parallel, read-only, no PRs)
| Step | Lane | What | Expected outcome | Evidence |
|---|---|---|---|---|
| **A0** | A | Map TopoFix main: Analyze → findings → fix plan → `uxml_edit_ops` → Apply. List every op kind TopoFix emits, with file:line. Say whether #18 and #23 still apply cleanly to `f4509b5a`. | Op-kind table; a rebase estimate for #18/#23 | L0 |
| **B0** | B | Inventory XCU readers and patch-backs. For each format (PSI116, InputXML, Categorized): which edit kinds it can patch back (value edit, delete element, merge or close nodes), refusal codes, and tests. | Format × edit-kind matrix; gaps against A0's op kinds | L0 |
| **C0** | C | Inventory the CII routes:<br>(i) **Writer2**, patching the existing CII;<br>(ii) **regenerate** the CII from the patched XML (xml-cii2019-core or 3D_Converters);<br>(iii) the Owner imports the patched InputXML in CAESAR II.<br>For each: inputs, what is kept byte-identical, benchmarks, and blockers. | A route table with a recommendation | L0 |
| **0.D** | Owner | **DECIDE the CII route** from C0. The Oracle suggests (i) Writer2 patch, which follows D2 ("patch, not rebuild"), unless C0 shows a blocker. | Route chosen | — |

### Stage 1: contract
| Step | Lane | What | Expected outcome | Evidence |
|---|---|---|---|---|
| **1.1** | B (+Oracle) | Write `docs/uxml-edit-ops-contract.md` in XCU: a versioned op format, the edit-ledger format, and refusal codes. Synthetic fixtures for each op kind. | Contract + fixtures + a schema test | L1→L2 |
| **1.2** | A | TopoFix's emitted ops validate against the contract on public samples. Adapter only; no engine or policy change. | Every A0 op kind passes the schema test | L1→L2 |

### Stage 2: XML edit round trip (no CII yet)
| Step | Lane | What | Expected outcome | Evidence |
|---|---|---|---|---|
| **2.A** | A | Reconcile #18 (InputXML into TopoFix) onto main. PSI116 behaviour stays unchanged. | InputXML findings match PSI116 (13 known UNEXPLAINED kept); PSI116 suites green | L2 |
| **2.B** | B | Patch-back of contract ops for PSI116 and InputXML, reusing the #23 code. Bytes outside edited records are identical; the result is re-read; ledger emitted. | Byte-identity + re-read tests; mutants RED | L2 |
| **2.P** | Owner | **Prototype 1:** real file → TopoFix fix → patched XML + ledger. The Owner opens it in the usual tools. | Owner verdict recorded | L4 |

### Stage 3: CII transfer (route from 0.D)
| Step | Lane | What | Expected outcome | Evidence |
|---|---|---|---|---|
| **3.1** | C | Map ledger entries to CII coordinates (ELEMENTS FROM/TO, node numbers, deltas, auxiliary records). Read-only CII diff tool: original against new, listing only the expected sections. | Mapping table + diff tool with tests | L1→L2 |
| **3.2** | C | Transfer **value edits** first (for example diameter and wall from B8), the smallest case. | Parsed back: only ledgered fields differ | L2 |
| **3.3** | C | Transfer **topology edits** (short drop / node close: element removed, FROM/TO renumbered, pointers fixed). | Element count and connectivity checks; untouched blocks byte-identical | L2 |
| **3.P** | Owner | **Prototype 2:** real file through the whole chain to a `.cii`. The Owner opens it in CAESAR II. | Owner verdict; no merge before this | L4 |

### Stage 4: review and merge
Each lane's draft PR goes through runner + fresh reviewer (≥92 and ≥17 per category, one repair round). The Owner merges only after 2.P or 3.P passes for that lane.

## Rules for all three coders
- Drafts only; the Owner merges.
- No Owner data on GitHub: counts and EQUAL/DIFFERENT only.
- NOT_RUN where not run.
- STOP with 2–4 options when blocked.
- A CODER-CHECKPOINT after every push: lane A on TopoFix #12, lanes B and C on XCU #239.
- Lanes never edit each other's files: A in TopoFix `converters/psi116_topology_resolver` + `tabs/topology-workspace`, B in XCU `uxml/`, C in the CII modules chosen at 0.D.

## First cards (drafts; send only on Owner yes)

**A0 → coder-a6:**
> STEP A0 · DISCOVER_FIRST · read-only, no branch, no PR. Repo xml229-topology-wp1-preview-20261028, main f4509b5a.
> 1. Trace the fix flow with file:line: Analyze → findings → fix plan → `uxml_edit_ops.py` → Apply / publish.
> 2. Table every edit-op kind TopoFix emits: name, fields, sourceRefs used, and which UI action produces it.
> 3. Drafts #18 (InputXML in) and #23 (InputXML patch-back): conflicts against main, by file, and a rebase-effort estimate.
>
> RETURN · STEP A0 in the template format, then STOP.

**B0 → coder-b7:**
> STEP B0 · DISCOVER_FIRST · read-only. XCU main ddd3ebc7.
> For each format (PSI116, InputXML, Categorized), list:
> - its reader and patch-back modules (file:line);
> - which edit kinds it patches back (value, delete element, node merge/close);
> - its refusal codes and test files.
>
> Mark every gap as a format × edit kind with no patch-back.
>
> RETURN · STEP B0, then STOP.

**C0 → coder-c1 (after onboarding):**
> STEP C0 · DISCOVER_FIRST · read-only. XCU main ddd3ebc7 (+ 3D_Converters, read only).
> For each CII route:
> (i) Writer2 patch of the existing CII;
> (ii) regenerate from the patched XML;
> (iii) CAESAR II InputXML import.
>
> Give: entry points (file:line), inputs, what stays byte-identical, existing benchmarks/tests, blockers. Recommend one route with a reason.
>
> RETURN · STEP C0, then STOP.

## Ledger
- 4 Nov · plan drafted from the Owner's split. Nothing has been sent.
- 4 Nov · Owner 'start ax and bx only, cx later': A0 sent to coder-a6 (6aeb3e9a) and B0 sent to coder-b7 (6aeb2e0a, told #256 PASS and no more commits there); both verified delivered and working (read-only). C0 / coder-c1 deferred.
- 4 Nov · A0 RETURN (coder-a6): flow trace + 6 emitted op kinds (ALIAS_COINCIDENT_NODE, CONTRACT_PRESERVE_OWNER, SAFE_DROP_PIPE_GEOMETRY, REMOVE_FALSE_RIGID, CLOSE_PORT_CONNECTION, DROP_SHORT_ELEMENT; CLOSE_CONFIRMED_* refused), envelope uxml-edit-ops/v1, targets = recordKeys. KEY FINDING: Apply re-serialises the whole PSI116 tree (transaction.py:180-181 ET.indent + ET.tostring) -> unedited bytes NOT guaranteed identical (D2 gap). #18 medium, #23 large (ownership). Oracle spot-check at L0: ET lines, op table, refusals all CONFIRMED. GATE: NEXT.
- 4 Nov · B0 RETURN (coder-b7): XCU main has readers for PSI116/InputXML/Categorized; only patch-back = S4.2 (Categorized baseline vs edited -> original InputXML value edits; delete/merge/add REFUSED). PSI116 patch-back ABSENT; no edit-ops entry point in XCU. #23 = ALIAS_COINCIDENT_NODE only on InputXML, pinned to old XCU 980f3253. Oracle spot-check: S4.2 signature :937, no PSI116 writer, #23 pin CONFIRMED. GATE: NEXT.
- Both coders independently suggest: XCU (lane B) is the single original-file writer; TopoFix emits uxml-edit-ops/v1; #23 is a reference to port, not rebased as a TopoFix writer. Owner decisions pending before 1.1/2.A cards.
- 4 Nov · OWNER DECISION 'ok agree': XCU is the only original-file writer; TopoFix emits uxml-edit-ops/v1; #23 ported by lane B; first kind InputXML ALIAS_COINCIDENT_NODE; PSI116 patch-back next. Sent STEP 1.1 (contract + applyUxmlEditOps + alias port, draft PR off XCU ddd3ebc7) to coder-b7 and STEP 2.A (InputXML into TopoFix main read-only, XCU pin ddd3ebc7, Apply refused, draft PR off f4509b5a) to coder-a6. Both verified delivered and working.
- 4 Nov · STEP 1.1 RETURN (coder-b7): XCU DRAFT PR #257 @783a8643 (5 new paths; applyUxmlEditOps + contract; only INPUT_XML ALIAS implemented; 413/413 in CI, 12/12 mutants; CI 3/3 green; receipt #239 6636831437). Author notes: v1 cannot certify the op was really selected by TopoFix (no signed attestation). STAND-IN: runner (Sonnet) + fresh reviewer (Opus) launched. STEP 2.A (coder-a6): TopoFix DRAFT PR #35 @fde0fbc6, 7 files, CI 3 pass + 1 pending; no RETURN yet.
- 4 Nov · #257 RUNNER SUPPORTS @783a8643: diff = exactly 5 added paths; head 24/24 + 12/12 new, S3 30/30, S4.1+S4.2 116/116, B7+B8 221/221, S1 10/10 = base counts (0 new failures); CI 3/3. NOT_RUN: editability-public, Playwright. Waiting fresh reviewer.
- 4 Nov · #257 FRESH REVIEW FAIL 76 (17/14/15/14/16). B1 node witness '40.'/'4.0E1' missed (stranded restraint, ok:true); B2 alias without coincidence evidence (40->999 ok:true; 16 cross-run joins on delta-only fixture) - Oracle confirmed in probe-out. STAND-IN VERDICT: REPAIR round 1 of 1, posted #239 comment 6637187736 (oracle-docs/verdict-257-r0.md). Repair card 1.1-R1 sent to coder-b7 (B1 Decimal-equivalent, B2 existing endpoint + proven coincidence in S3-anchored frame else INPUT_XML_ALIAS_COINCIDENCE_NOT_PROVEN, kill listed mutants, multi-op/width/BOM/real-sample tests).
- 4 Nov · STEP 2.A RETURN (coder-a6): TopoFix #35 @fde0fbc6, 7 files, Python 150 pass/4 skip (main 134/4), node 112, CI 4/4; findings counts equal PSI116 vs InputXML on the public pair, 13 UNEXPLAINED kept. STAND-IN: runner + fresh reviewer launched.
- 4 Nov · #35 RUNNER SUPPORTS @fde0fbc6: 7 files, transaction.py + tabs untouched; Python head 150 / base 134 run, same 5 Windows-only BOM/SHA failures at both (S1/S2 byte-exact, env artefact), 4 skips both; S3 5+8+3 OK; node 112 = base; INPUT_XML_APPLY_NOT_ENABLED at export+apply, tested; CI 4/4. Waiting fresh reviewer.
- 4 Nov · #35 (2.A) fresh reviewer: 86 (18/18/17/16/17), 13/18 guard mutants survive. STAND-IN: REPAIR round 1 posted (#12 comment 6637838004, verdict-35-r0.md); adds fail-closed R1 (native apply on InputXML -> INPUT_XML_APPLY_NOT_ENABLED) and R2 (resolver CLI no false clean). Repair card sent to coder-a6 (working). 2nd repair needs Owner.
- 4 Nov · #35 repair R1 returned @824f569b, CI 4/4. STAND-IN: L2 runner + NEW fresh reviewer launched. IR257 (ChatGPT ir-257, 6aeb74c7): Stage 1 recorded (oracle-docs/ir257-stage1.md), Stage 2 sent.
- 5 Nov · #35 R1 runner @824f569b: SUPPORTS. 8 forward commits; parser.py/transaction.py hunks add refusals only (CAESARII root -> INPUT_XML_NATIVE_PSI116_RESOLVER_NOT_ENABLED / INPUT_XML_APPLY_NOT_ENABLED first statement). Python 150->170 OK (4 skips same), Node 112/112. R1 all 4 forms refuse (base returned results), R2 API+CLI refuse (CLI exit 1 but traceback, not clean message). PSI116 apply fixed_xml identical base/head. Mutants M03-M18 + R1/R2 all KILLED. Runner's own M01/M02/M14 labels differ from reviewer's (orig M01/M02 = export/apply guards = runner's M04 'refusal removed', KILLED; orig M14 allow-list not rerun). New coverage gaps: INPUT_XML_COORDINATE_FRAME_MISMATCH and INPUT_XML_PORT_FRAME_MISMATCH guards untested. Waiting fresh reviewer.
- 5 Nov · #35 R2 RETURN head d196e345 (final round). L2 runner (rb-35r2 vs rb-35r2-base 824f569b) + NEW fresh reviewer (rev-35r2, Opus) launched. Fail -> stop and rethink (no 3rd round).
- 5 Nov · #257 R2 RETURN (final round) head d4ccec7c (4 fwd commits, 6 files incl. new UxmlEditOpsTypedInventory.js; CI 3/3 SUCCESS, coder claims 459/459 + 21 mutant kills + 6 seeded post-patch adversaries; receipt #239 6645705383). Launched: L2 runner (rb-257r2 vs rb-257r2-base 08fb8b11), NEW fresh reviewer (rev-257r2, Opus), IR ir-257 delta check IR257-D1 (tab-6, embargoed from runner/reviewer). Fail -> stop and rethink.
- 5 Nov · #35 R2 RUNNER @d196e345: SUPPORTS. 5 files +295/-6, 6 fwd commits, no engine files. py 170->196 OK (4 same skips), node 112/112; CI 4/4 SUCCESS (S3 baseline main 134 -> head 196, 0 new skips). Mixed-hub probes give both exact codes; B3 CLIs exit 1 INPUT_XML_APPLY_NOT_ENABLED before XCU load, no files written; R1/R2 still refuse; PSI116 apply identical to base. Mutants: B1 x2, B3 x2, R1, R2, M04 KILLED; every card B2 guard KILLED by own test; older M05-M18 still killed. ROUTE_CONTINUITY removal argument holds (by reading). Residual non-blocking: ~23 off-card S3 guards + 17 UXML_* codes not pinned by the S3 set (likely masked by the strict reader; not on the card). Waiting for the fresh reviewer.
- 5 Nov · #257 R2 FRESH REVIEWER @d4ccec7c: REPAIR 76 (16/15/14/15/16). Sound: byte parity, no bytes on refusal, SHA, BigInt identity, entity decoding, DTD/CDATA, unknown carriers, owner spelling, LF/CRLF/BOM. BLOCKING: B1 two ops sharing owner B join A and C 0.0018 mm apart (all-pairs per op only, :132-141/:186-189); B2 lower/mixed-case from_X hides the raw absolute witness (:119-121) -> 0.0018 mm join; B3 child RESTRAINT/HANGER/SIF/BEND become self-connected (NODE=CNODE) after mapping; B4 BOTH real public files refuse UNKNOWN_NODE_CARRIER on ordinary fields (HYDRO_PRESSURE, TEMPERATURE1-16 ...), real-file test only asserts not KIND/SCHEMA -> path cannot run on real CAESAR II output. Many guards untested (verifyS3Candidate, policy widening, CDATA). FINAL ROUND FAILED at reviewer -> per Owner rule STOP AND RETHINK (no 3rd round). Waiting runner + IR257-D1 to reconcile.
- 5 Nov · #257 R2 RUNNER: SUPPORTS on the R1-R6 spec probes (459/459, 55 probes, mutants killed), but it did not probe the reviewer cases. ORACLE L2 REPRO @d4ccec7c (rev-257r2 recreated): reviewer B1 multi-op shared owner OK+bytes (RED), B2 from_X/From_X hidden anchor OK+bytes (RED), B3 RESTRAINT/HANGER/SIF/BEND self-connect OK+bytes (RED), B4 GRE + PLB314 refuse UNKNOWN_NODE_CARRIER on 8/25 ordinary fields (RED). All 4 blockers CONFIRMED -> FINAL ROUND FAILED -> STOP AND RETHINK. Owner asked for a local test-run plan: plans/XCU257-LOCAL-TEST-PLAN.md (LT-1..LT-7). IR257-D1 still pending.
- 5 Nov · IR257-D1 RETURN (Drive SHA 1c8ab7e6... MATCH chat; oracle-docs/ir257-d1.md). Embargoed from runner/reviewer. NO-GO for Apply @d4ccec7c: independently found N1 = multi-op aggregate per-owner pairwise missing (= reviewer B1) and N2 = case-insensitive coordinate lookup missing in raw witness (= reviewer B2); both executed in memory, bytes returned with a pair > 0.001 mm. Most R1-R6 mechanisms implemented. RECONCILED: reviewer REPAIR 76 + IR NO-GO + Oracle repro of B1-B4 vs runner SUPPORTS (spec probes only) -> FINAL ROUND FAILED. STOP AND RETHINK (Owner). Verdict on #239 not posted.
- 5 Nov · ORACLE rerun of the local harness (localtests/xcu257, run-all.ps1) @d4ccec7c: reproduces LT-1..4 RED, LT-5 GREEN. Root causes CONFIRMED in source (oracle-docs/xcu257-root-causes.md): LT-1 per-op coincidence (PatchBack :186-188); LT-2 exact-case raw witness lookup (:119-123); LT-3 self-loop guard edges only (:225-229); LT-4 value-based unknown-carrier heuristic + hand-written non-node list (Inventory :31-39, :118-130). Process causes: per-op spec, duplicated parsing, edge-only oracle, no real-input gate, coder-seeded mutants. HARNESS GAPS: H1 LT-4c auto-PASS when reachable (run-suite.mjs:197-199); H2 LT-3 any-refusal passes; H3 no positive multi-op control; H4 hard-coded actual text; H5 case variants incomplete.
- 5 Nov · #35 R2 FRESH REVIEWER @d196e345: REPAIR 77 (17/16/14/14/16). Holds: every write path + both CLIs refuse INPUT_XML_APPLY_NOT_ENABLED before work (plain/BOM/CRLF/decl variants), resolver/compare refuse, ROUTE_CONTINUITY removal valid, 196 tests. BLOCKING: B1 inputXml.runs membership taken from the hub, never rebuilt from source FROM/TO connectivity -> forged run partition defeats the proximity-join and cross-format unanchored refusals (repros p2_forge_run.py, p3_mixed_merge.py on public fixtures). B2 16 reachable guards + 4 compare checks deletable with full suite green (RUN_ID_NOT_FOUND gives a false clean result; INVALID_NODE_NUMBER silently truncates 100.5 -> 100). Runner SUPPORTS covered card items only (E2 again). Oracle repro of B1 pending before verdict.
- 5 Nov · ORACLE L2 REPRO #35 B1 @d196e345 (public fixtures, reviewer scripts p2/p3): forged single-run delta-only hub ACCEPTED (honest 2-run hub refused) -> NEAR_MISS_BRANCH_ENDS across two separate frames; forged all-anchored mixed hub: resolve ACCEPTED and cross-format compare ACCEPTED with 20 diffs from fabricated absolute coords (honest mixed hub refused by both). CONFIRMED. Scope note: needs a hand-edited hub (XCU pinned reader would not emit it); the adapter re-derives components from source but trusts the hub run partition. FINAL ROUND FAILED (reviewer 77 + Oracle repro; runner covered card items only). STOP AND RETHINK. B1 fix is narrow (rebuild run components from source FROM/TO; anchored flag = component has a literal anchor) + B2 exact-code tests.
- 5 Nov · OWNER REDEFINES LANE C: "Transfer of CII data like specific Node name, Properties like Pressure 1 from one CII to another CII via enriched XML. Process: Source CII/Target CII > enriched xmls -> Map them -> Edit in XML (Code B) -> Export as Target CII." Also: perf, rigid and lanes A/B/C are inter-related (one programme). Lane C overlap: ciifr page M10 node map + M11 Authorized mapped transfer (WBS 5.2/5.3) -> COORDINATION_REQUIRED before any lane C card. See PROGRAMME-MAP.md.

- 5 Nov 05:33Z · OWNER 'ok proceed' -> #257 INVARIANT-FIRST (new step 1.2), #35 NARROW FIX (new step 2.B); no round 3. IR-INV-257 card sent to ir-257 (Drive Handoffs/IR-INV-257, 4851 B, sha 9330340d...); waiting RETURN. INV-35 invariant review (fresh local reviewer): NEEDS_CHANGES -> all adopted in plans/cards/INV-35.md (I-A1/I-A2/I-A4 reworded to mirror the reader partition; NEW I-A5 node-literal alias). ORACLE REPRO I-A5 @d196e345 on public fixture: '30' vs '30.000000' -> 2 anchored runs, resolve + compare ACCEPTED (18 diffs). CONFIRMED. INV-35 READY_FOR_CARD; step 2.B card needs Owner yes.
- 5 Nov 05:33Z · HARNESS v2 localtests/xcu257/run-suite.mjs (v1 kept as run-suite.v1.mjs): H1-H5 closed (named codes, LT-1p/LT-3e/LT-3f positive controls, LT-2 10 variants, real counts, real LT-4c with ledger replay). Baseline @d4ccec7c: LT-1, LT-2 (8/8 variants), LT-3a-d, LT-4a (8 fields), LT-4b (25 fields) RED; LT-1p, LT-3e, LT-3f, LT-5 GREEN; LT-4c not reachable (self-test path: 1 ledger, replay EQUAL, S3 OK, edges EQUAL). Report oracle-docs/xcu257-local-d4ccec7c.md.
- 5 Nov 05:34Z · RETURN IR-INV-257 (ir-257, card SHA MATCH): NEEDS_CHANGES -> all adopted in plans/cards/IR-INV-257.md (I-1 chains refused + every occurrence + COORDINATE_UNPROVEN; I-2 one shared source-field API; I-3 newly-introduced equalities only; I-4 three-class registry incl. FORCESMOMENTS/USERDEFINED_NOZZLE/DISPLACEMENTS; I-5 independent verifier; NEW I-7 action provenance = release dependency at the TopoFix boundary). READY_FOR_CARD step 1.2; needs Owner yes.
- 5 Nov 05:37Z · Owner 'Yes, send both'. STEP 1.2 card -> coder-b7 (Drive Handoffs/STEP-1.2-B7, 7828 B, sha 9cdcfc4f...; plans/cards/STEP-1.2-B7.md). STEP 2.B card -> coder-a6 (Drive Handoffs/STEP-2.B-A6, 6598 B, sha fea66128...; plans/cards/STEP-2.B-A6.md). New branches + new draft PRs; #257/#35 stay as history. Both acknowledged. Gate on return: runner (carried-forward blockers) + fresh reviewer + harness v2 (xcu257) / forged-hub + I-A5 repro (35).
- 5 Nov 06:03Z · STEP 2.B RETURN (TopoFix #12 comment 6650913058, 05:56Z): NEW DRAFT PR #36 head c6b3e9d3 from d196e345; 14 fwd commits; 5 files +493/-23 (adapter, compare, 2 test files, workflow), no engine files; #35 untouched; CI 3/4 SUCCESS (full Chromium/Pyodide in progress). Claims py 134->214 (4 skips), node 112/112, 16+4 guards pinned. ORACLE REPRO base d196e345 vs head: single-run delta-only forgery ACCEPTED -> RUN_PARTITION_MISMATCH; all-anchored mixed merge resolve+compare ACCEPTED (20 diffs) -> RUN_PARTITION_MISMATCH in both; node-literal alias 30 vs 30.000000 ACCEPTED -> NODE_LITERAL_ALIAS; honest mixed hub refusals unchanged. L2 runner + fresh Opus reviewer launched (worktrees rb-36, rb-36-base, rev-36).
- 5 Nov 06:31Z · #36 FRESH REVIEWER @c6b3e9d3: REPAIR 87 (19/15/18/17/18). Sound: honest parity identical to base (hash-equal outputs), partition from source only, all forged/alias/run-id/node-number probes refuse with named codes, holds intact. BLOCKING B1: recursive union-find (uxml_adapter.py:338-344) -> RecursionError on honest reverse-ordered run > ~1000 elements. ORACLE REPRO: N=1200 base OK/OK, head RecursionError on doc+resolve; N=900 identical. CONFIRMED. Surviving mutants A7/A13/A14 (honest acceptance unpinned). Repair card 2.B-R1 drafted (plans/cards/STEP-2.B-R1-A6.md), round 1 of 2; waiting runner, then Owner yes.
- 5 Nov 06:36Z · #36 L2 RUNNER @c6b3e9d3: SUPPORTS. 196->214 at fork (+18; coder's 134 is vs main), 0 new fails/skips; node 112/112; all probes correct, no forged hub accepted; card-named real mutants killed; survivors M06/M16/M20/M23/M24 equivalent or redundant, M15 (firstNode on late anchor) unpinned = reviewer A7. RECONCILED GATE: REPAIR (reviewer 87 < 92, correctness 15 < 17; B1 recursion CONFIRMED by Oracle). Repair card 2.B-R1 ready (round 1 of 2); needs Owner yes.
- 5 Nov 06:36Z · GLRD INPUTS RECEIVED (Owner links, public 3D_Converters): 6 files downloaded to downloads/GLRD-INPUTS with SHA-256 (MANIFEST.md). CORRECTION: 3D_Converters main = 3377b7f4, so the 'commit on no remote' claim was wrong. Page PR #109 pins them in fixtures.inputs. Unblocks R-LT3..8 and P-LT3..7.
- 5 Nov 06:46Z · Owner 'Yes, send repair'. Repair card 2.B-R1 (round 1 of 2) -> coder-a6 (Drive Handoffs/STEP-2.B-R1-A6, 4218 B, sha 388f8dda...). Gate on return: carried blocker B1 (reverse-run 1200 and 5000, base vs head) + T1a-c/T2 mutants + new fresh reviewer.
- 2026-11-05 07:05Z · lane B · RESUME nudge sent to coder-b7 (Owner "Yes, send nudge"): continue from PR #258 head 778b7f83, no restart, RETURN · STEP 1.2 on #239 + chat. Delivered; chat busy.

- 2026-11-05 07:25Z · RETURNs in: lane A 2.B-R1 @46a7023f (07:13Z) and lane B 1.2 @778b7f83 (07:14Z). Scope verified (A 10 fwd/6 files; B 10 fwd/20 files). Oracle repro: A 5/5 PASS (B1 N1200/N5000 hashes equal fork, forgeries + alias refuse); B harness v2 LT-1..LT-4c GREEN, LT-5 0 unsafe accepts. Runners + fresh reviewers launched for both. Notes: localtests/ORACLE-REPRO-20261105-0730.md

- 2026-11-05 08:20Z · lane B fresh reviewer: REPAIR 85 (intent 18, corr 18, safety 18, tests 15, code 16). No unsafe accept. Blockers: B1 element-text/CDATA guard unpinned (maintenance edit weakened its mutant), B2 BEND-vs-parent self-connection rule unpinned in both layers, B3 most independent-verifier guards unpinned. Oracle repro: with text guard + BEND-parent rule removed, a numeric-text RESTRAINT alias returns OK with stranded '>40<' text and a BEND NODE1=20 vs FROM 40->20 alias returns OK (head refuses both). CONFIRMED consequences; suite-green-on-mutant check rerunning. Session restart 07:3xZ stopped 3 agents; resumed 08:19Z.

- 2026-11-05 10:45Z · GATES: lane A 2.B-R1 @46a7023f REPAIR (fresh reviewer 89; Oracle CONFIRMED B1 AttributeError on non-dict sourceRefs/rawAttributes, B2 len(runs) guard unpinned: 91/91 S3 green on mutant, extra empty run accepted). Lane B 1.2 @778b7f83 REPAIR (reviewer 85, runner PARTIAL; Oracle CONFIRMED b7/b8 mutant harnesses 0/34 at head ERR_MODULE_NOT_FOUND hidden by path filters; text guard + BEND-parent rule removable with suites green and unsafe OK; verifier SELF removable 146/146 green). Cards drafted: STEP-1.2-R1-B7.md, STEP-2.B-R2-A6.md (final). Awaiting Owner yes. Lane A runner still running.

- 2026-11-05 10:55Z · Owner "Yes, send both". Lane B card STEP-1.2-R1 sent to coder-b7 (Drive Handoffs/STEP-1.2-R1-B7/, 5674 B, sha256 d320cfb321de2092715b1e097518a3cc12b09eb8d27e97e6bfad89e13c4bbd2c); delivered, chat busy. Lane A card STEP-2.B-R2 approved; held until the lane A L2 runner report is folded in.

- 2026-11-05 11:02Z · Owner "ok proceed" on #109: Oracle merge denied again by the permission classifier (Merge Without Review); not worked around; #109 unchanged (draft, fb701f2b, green). Owner "Yes, start both": rigid 2.5 runner (R-LT3..R-LT8 on BM2) and perf P-LT3..P-LT7 runner launched in background.

- 2026-11-05 11:09Z Â· LANE A L2 RUNNER 2.B-R1 @46a7023f: SUPPORTS. Scope 6 files +441/-8 as claimed; tests d196 196/4 skip, c6 214/4, head 225/4, 0 failures; Node 112/112. B1 N=1200/5000 head == d196 hashes; no recursion left (AST scan); 100000 direct 1.2 s. T1a-c accepted equal; T2 bool/float/int-subclass refuse. Carried blockers all refuse with named codes; honest hubs identical to d196. Mutants: M1-M6 RED; M3b (edgeCount int check removed) SURVIVES -> added to 2.B-R2 card as B3; M7 N2 equivalent/unreachable (note: _caesar_int raises a ValueError subclass that compare's except would swallow). CI 4/4 incl. Chromium/Pyodide success. Combined gate 2.B-R1: REPAIR (reviewer 89). Card 2.B-R2 final.
- 2026-11-05 11:11Z · Lane A card STEP-2.B-R2 (FINAL round 2 of 2; B1 AttributeError sweep + type-fuzz, B2 run-count guard test, B3 edgeCount int test from runner M3b, N1-N4) SENT to coder-a6 (Drive Handoffs/STEP-2.B-R2-A6/, 4819 B, sha256 a5bfb661289c158dc06c4e03de538f8ed3211f82a275a5b071c68c220ef346f1); first click timed out and did not send (verified: no message, composer full), second click sent; chat busy.
- 2026-11-05 11:37Z Â· LANE B RETURN Â· STEP 1.2-R1 (#239 11:15Z) head 99f055aa: 2 fwd commits from 778b7f83, 10 files +297/-33 (verifier production +76/-33, REMAIN removed; b7/b8 workflows + clone lists). CI 13/13 pass. ORACLE REPRO (worktree or-258r1): R1 B7/B8 mutant suites 34/34 pass (were 0/34); R2 text guard removed -> 8 committed tests RED; R3 BEND-parent removed in planner only -> RED, in verifier only -> RED; R4 verifier SELF removed -> RED; skipping the verifier call is caught by the seeded behavioural mutant R1_VERIFIER_CALL_BEHAVIOUR (plain suites cannot see it without a planner fault: accepted design). Committed mutant suites 55/55. Harness v2 LT-1..LT-4c all GREEN (LT-5 = known harness parse issue). All 4 blockers CLOSED per Oracle. L2 runner + NEW fresh reviewer running.

- 2026-11-05 11:53Z · LANE B fresh reviewer 1.2-R1 @99f055aa: REPAIR 80 (17/17/16/14/16). No unsafe accept found. Blockers: B1 node-like element text ('NODE 40', '40,') ACCEPTED in PIPINGELEMENT, CDATA refuses (ORACLE REPRO CONFIRMED); B2 five mutant-harness workflows lack SourceFields.js / uxml/** filters (ORACLE CONFIRMED), edit-ops workflow lacks DeltaGraph/SourceStructure; B3 verifier call sites text/owner/S3-point unpinned (ORACLE: :224 and :242 removed -> 130/130 green) + ~20 redundant-layer single-guard survivors. Card STEP-1.2-R2-B7.md (FINAL round 2 of 2) drafted; awaiting runner + Owner yes.

- 2026-11-05 15:22Z Â· LANE A RETURN Â· STEP 2.B-R2 (FINAL) posted #12 11:25Z, head 1419676530f2 (MISSED by the 11:59Z+ checks: their since-filter started after it; found 15:19Z). 7 fwd commits from 46a7023f, 5 files +287/-9; CI 4/4 pass. ORACLE REPRO (worktree or-36r2): F20 sourceRefs str -> PORT_SOURCE_REF_MISMATCH, rawAttributes str / inputXml list -> RAW_RECORD_ID_MISMATCH (were AttributeError), extra empty run -> RUN_PARTITION_MISMATCH; B1 reverse N=1200/5000 hashes == d196e345; forged single-run and all-anchored merge refuse PARTITION_MISMATCH, honest hubs refused by the cross-unanchored rules as before; alias refuses NODE_LITERAL_ALIAS. All 3 round-2 blockers CLOSED per Oracle; carried blockers hold. L2 runner + NEW fresh reviewer running.
- PROTOCOL NOTE: every check's ?since= must start at the PREVIOUS check's since (or last heartbeat minus 10 min), never later; I lost 4 h on lane A by moving it forward past an unread comment.
- 2026-11-05 15:44Z Â· LANE B L2 runner 1.2-R1 @99f055aa: PARTIAL (R1-R3 MET; 86 probes, no new accept; b7/b8 34/34; CI 13/13 incl. B8 exhaustive; 24 mutants, 6 survive: verifier anchored V03, literal witness V04, FROM/TO SELF pair V07, text-parity call V12, S3-point call V15, NODE_REF b.key===mapped V16). Combined gate 1.2-R1: REPAIR. Folded V07/V16, dead C.REMAIN and the B8 trigger for b7-controller test into STEP-1.2-R2-B7.md. SENT (Owner "Yes, all of it") to coder-b7: Drive Handoffs/STEP-1.2-R2-B7/, 6681 B, sha256 51b2decf6842911671effe7fd25d44bbd612fc1c80d42552665c14e2c28d4bc5; delivered, working. FINAL round 2 of 2.

- 2026-11-05 16:35Z Â· LANE A fresh reviewer 2.B-R2 FINAL @1419676: REPAIR 88 (18/17/19/16/18). Holds: 200 random honest XCU-read models accepted (0 mismatches, 0 unnamed); all forgeries/aliases/bad run ids refuse named; N=6000 OK; holds intact. Blockers: B1 sourceRefs[0].endpoint list -> unnamed TypeError (adapter:665); B2 rawAttributes.inputXml.sourceAttributes=True -> compare AttributeError (compare:200); B3 5000-digit node literal (XCU exit 0) -> unnamed ValueError (adapter:266 _caesar_int); B4 unpinned guards M24 componentType str, M27 compare frame dict, M28 PSI sources dict, M31 elementIndices field (indices-only swap accepted when removed). All three pre-exist at base. ORACLE REPRO: B1, B2, B3 CONFIRMED; indices-only forgery refused at head (M31 = test gap only). Round 2 was FINAL: no round 3 without the Owner. OWNER Q22.

- 2026-11-05 16:46Z · LANE A L2 runner 2.B-R2 FINAL @1419676: PARTIAL. Every card item fixed and pinned (B1a-c, B2, B3, N1, N2, N4); carried checks hold (N1200/5000 == d196; forgeries/alias/run ids refuse; T1/T2; public hubs == d196; 180 random honest hubs 0 diffs, 0 exc); suites 196/225/239 OK, 4 skips; CI 4/4 incl. Chromium PASS. Full hub type fuzz (37,832 cases): unnamed 792 (d196) -> 750 (46a7023f) -> 126 (head), all in 2 classes = reviewer B1 (endpoint list/dict, adapter:665) and B2 (sourceAttributes non-dict, compare:200). Unpinned guards: R4 componentType str, R12 compare frame, R13 compare sources[0], R14 compare psi sources. Combined gate 2.B-R2: REPAIR (reviewer 88 + runner PARTIAL, Oracle CONFIRMED B1-B3). Closure card STEP-2.B-R3-A6.md (C1-C5) drafted for OWNER Q22.

- 2026-11-05 17:03Z Â· Owner "Yes, all four": (1) lane B RESUME sent to coder-b7 (continue from 3096e891, no Retry, short reply); (2) PERF 1.R9 sent to perf-coder (Drive Handoffs/PERF-1.R9, 3734 B, sha 5c93de3088bafb204e0248873e087182f2b25362c261bd6fba0f848da55dd4a8); (3) RIGID 2.3e incl. Owner facing ruling R1 sent to rigid-coder (Handoffs/RIGID-2.3e, 3902 B, sha 2b901574b749188580d2407dd82cb34cdbb6040573cdbc065af15a2b04900a57); (4) lane A CLOSURE 2.B-R3 sent to coder-a6 (Handoffs/STEP-2.B-R3-A6, 3428 B, sha 7a4938320ea80be903b531910c65cdac5c44e9b1d6a68b220ba31a22bf93cf25; first tab never hydrated, nothing sent there; second fresh tab sent once). All four delivered, chats busy.

- 2026-11-05 20:2xZ · lane A RETURN 2.B-R3 closure 17:16Z head faf72e82 (gate pending); lane B RETURN 1.2-R2 final 16:57Z head 3096e891 (gate running; Oracle: text bypass closed, V12 unpinned).

- 2026-11-05 20:29Z · LANE B fresh reviewer 1.2-R2 FINAL @3096e891: REPAIR 79 (17/15/16/15/16). B1 UNSAFE ACCEPT: a RESTRAINT/BEND inside an XML comment or PI in a PIPINGELEMENT is skipped by the inventory (TypedInventory.js:554-563) but read by the strict S3 reader's loose finder (SchemaMapper.js:1757-1782); alias 40->20 ACCEPTED and S3 still shows a restraint at NODE 40 (stranded). ORACLE REPRO CONFIRMED (commentRestraint, piRestraint, commentBend all ACCEPT, S3 contains NODE 40). B2 verifier child-family SELF list unpinned and the only independent layer for RESTRAINT/HANGER/SIF (planner+verifier removed -> writes RESTRAINT NODE=20 CNODE=20). B3 13 more guards survive deletion, neither pinned nor documented COVERED-BY. Committed suites all green incl. b7/b8. Final round failed: no round 3 without the Owner. OWNER Q25.

- 2026-11-05 21:35Z · LANE B L2 runner 1.2-R2 FINAL @3096e891: PARTIAL. R1 (12 text/CDATA variants refuse; GRE/PLB314 admitted), R2 (committed trigger check 10/10 and falsified on copies; whole-file scan clean for the five + B8 + edit-ops), R4 (18 reviewer survivors: 12 PINNED, 5 COVERED-BY spot-checked, 1 REMOVED) MET. All previously named verifier survivors RED (via verifier-live suite). New survivors: O08 verifier literal value not compared (planner still refuses, production safe), O13 verifier intra-child pairs, O09/O11/O12/O14 equivalent or seam-only; old outside-model text guard T01/T02. Suites base 1040/1040, head 1103/1103; CI 13/13. Combined gate 1.2-R2: REPAIR (reviewer 79 incl. UNSAFE comment/PI case, Oracle CONFIRMED). Closure card STEP-1.2-R3-B7.md (C1-C4 + N1) drafted for OWNER Q25.

- 2026-11-05 21:47Z · LANE A fresh reviewer 2.B-R3 CLOSURE @faf72e8: REPAIR 90 (18/18/19/17/18; every category >= 17). Verified: 16 honest variants incl. two 5,880-element models all accepted (digests = base where base accepted; base wrongly refused lowercase/mixed-case anchors); 17 forgeries refused named in all 4 entry points (9 accepted at base); InputXML hub type fuzz 6,213 + 6,201 paths x 16 values: 0 unnamed; source fuzz 1,320: 0 unnamed; 46 MUTANT_RED. B1: hand-edited PSI116 hub -> unnamed AttributeError/KeyError in compare_cross_format_uxml (51 distinct over 1,104 PSI paths; same at base; CLI catches no AttributeError). ORACLE STAND-IN RULING: B1 is OUTSIDE step 2.B (scope = InputXML read-only partition; PSI116 hub branch borders the PSI116 parser hold; pre-existing) -> recorded as follow-up FU-A1 'PSI116 hub shape checks in compare + CLI AttributeError'. Remaining in scope: test gaps A20 (honest closed loop nodeCount) and A25 (TO-only anchor), head behaves correctly on both. Waiting for the L2 runner before the Owner decision.

- 2026-11-05 22:07Z · LANE A L2 runner 2.B-R3 @faf72e8: SUPPORTS (minor gap: exact 9-digit node bound unpinned; <=10 / <=4300 survive but refusals stay named). Suites 196/239/250 OK, 4 skips; +11 tests; C1 30/30 named (was 25 unnamed), C2 named (was 54 unnamed), C3 >9 digits named / honest up to 999999999 work, C4 all named, C5 committed fuzz 1427 cases 0 unnamed; full type fuzz workspace 126 -> 0, delta-only 96 -> 0 unnamed; carried all equal; CI 4/4. ORACLE REPRO @faf72e8 (or-36r3): endpoint list -> PORT_SOURCE_REF_MISMATCH; sourceAttributes True -> CROSS_FORMAT_SOURCE_ATTRIBUTES_INVALID; 5000-digit node -> INVALID_NODE_NUMBER; indices-only swap -> PARTITION_MISMATCH; N1200/N5000 hashes == d196. COMBINED: reviewer 90 (all >= 17; its only blocker ruled out of scope as FU-A1), runner SUPPORTS, Oracle repro PASS. Not a formal 92 PASS. OWNER Q27.

- 2026-11-06 07:29Z Â· Owner "Yes, all three": Q27 lane A step 2.B ACCEPTED with listed limits (FU-A1 PSI116 hub shape checks; tests for TO-only anchor, closed loop, 9-digit bound) -> Owner prototype L4: oracle-docs/LANE-A-PROTOTYPE-HOWTO.md + tools/lane-a-prototype.ps1 (tested on the public workspace fixture: 2 anchored runs accepted). Q25 lane B closure card STEP-1.2-R3-B7 approved (Drive Handoffs/STEP-1.2-R3-B7, 4355 B, sha be8512cb...). Q26 rigid 2.3f approved (Drive Handoffs/RIGID-2.3f, 1835 B, sha 7bf5fb0e...). NOT SENT YET: the built-in browser is signed out of ChatGPT; ready-to-paste messages + full chat URLs recorded in HANDOVER-20261106.md sections 8-9 (Owner request: save coder ids with full URLs).
