## [OTM] Oracle verdict · TopoFix PR #35 Lane A STEP 2.A repair round 1 @`824f569b` · **REPAIR** (84/100) · stand-in · round limit reached, next round needs the Owner

**Scores (new fresh independent reviewer):** intent 17 · correctness 18 · safety/holds 18 · tests 14 · code 17. The bar is ≥92 total and ≥17 in every category.

**Runner:** SUPPORTS.
- 8 forward commits. The parser.py and transaction.py hunks only add refusals.
- Python goes from 150 to 170 tests, all OK, with the same 4 skips. Node is 112/112.
- **R1:** `apply_topofix_transaction` refuses `INPUT_XML_APPLY_NOT_ENABLED` for a hub result, a raw Path, a str path and raw text. Before this round, all four returned a result.
- **R2:** the API and CLI refuse.
- A PSI116 apply gives byte-identical fixed XML at base and head.

**Every item the previous round required is present.** The M04–M18 guards are each killed by their own exact-code test, and so are the R1 and R2 guards. The real code fails closed on every probe, including a BOM prefix, format-name variants, the preview and the CLI.

### Blocking
**B1. The mixed anchored + unanchored hub has no test.** This guard protects the hold that unanchored runs are never proximity-joined.
- Two weakening mutants survive the full suite:
  - `uxml_adapter.py:249` with `any`→`all`;
  - `uxml_compare.py:104` with `all`→`any`.
- Both public fixtures are uniform, so no test ever uses a mixed hub.
- Head itself behaves correctly. Repro: the public `workspace.input` with the FROM/TO absolute coordinates stripped from PIPINGELEMENT[5] gives RUN-0000 anchored and RUN-0001 unanchored. Both resolve and cross-format compare refuse, but no test pins that.
- **Fix:** add exact-code tests built from this mixed fixture.

**B2. 17 more named guards survive deletion,** 3 of them against the full suite.
- In `uxml_adapter.py`:
  - COORDINATE_FRAME_MISMATCH;
  - CAESAR_ROOT_REQUIRED, which the native apply guard relies on;
  - NOT_TOPOLOGY_FULL, ORIGINAL_TEXT_REQUIRED, SOURCE_SHA256_REQUIRED and PORTS_PER_ELEMENT_MISMATCH;
  - the run-frame, identity, index and coverage guards;
  - RAW_RECORD_ID, NESTED_SOURCE_EVIDENCE, PORT_FRAME, DELTA_PATH, BEND_TYPE, ROUTE_CONTINUITY and RUN_RESOLUTION_FORMAT.
- In `uxml_compare.py`: CROSS_FORMAT_INPUT_XML_SOURCE_REQUIRED and CROSS_FORMAT_HUB_FRAME_UNVERIFIED.
- **Fix:** add one exact-code test per guard, or delete a guard shown to be unreachable, with the reason.

**B3. The two edit-ops CLIs (`uxml_export_ops`, `uxml_patch_psi116`) do work before refusing when given a raw InputXML path.** They fail closed and write nothing, but with an unrelated code.
- **Fix:** at the start of `main()`, probe the root by reusing `transaction._refuse_inputxml_native_apply`, so they refuse `INPUT_XML_APPLY_NOT_ENABLED` first. Add a CLI test for each.

### Non-blocking
- The resolver CLI prints a traceback instead of a clean message.
- `short_elements.apply_short_element` can be called directly and bypasses the front-door guard. No write happens.
- `inputXml` non-dict raises `AttributeError`.
- The S3 tests skip locally when `XCU_UXML_ROOT` is missing. CI's grep covers this.

**Owner decision (5 Nov):** a FINAL repair round 2 fixing B1, B2 and B3, on the SAME branch with forward commits only. The PR stays DRAFT. Agents never merge.
