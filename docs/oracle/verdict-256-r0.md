## [OTM] Oracle verdict · XCU PR #256 UXML-B8-LEFTOVERS @`3f5fd395` · **REPAIR** (64/100)

**Scores (fresh independent reviewer):** intent 15 · correctness 12 · safety/holds 10 · tests 14 · code 13 = **64**. Bar is ≥92 total and ≥17 in every category.
**Runner:** SUPPORTS. Every count in the work_returned receipt (comment 6610390265) re-ran locally at the exact head (Node 22): B8 coverage 200/200, leftovers-fast 10/10, r2-carry 35/35, B8 mutants LF 30/30 + CRLF 30/30, B7 21/21 (+ mutants 9/9 each), S4.2 50/50 + 52/52 (+ mutants), S4.1 64/64, S3 22/22, S4.0 86/86, S1 12/12, admission 20/20. Witness 171 attempts / 0 mismatches. Mirrors 10/10 identical, all <300 lines. NOT_RUN locally: editability-public (CI 4/4), Playwright (CI).

### Blocking (breaks the hold "no change to what is accepted or refused")
1. **A guard moved by the refactor is dead, so an edit the base refuses is now accepted and written.**
   - `uxml/UxmlCategorizedPatchBackSourceIntegrity.js:5` (and its `docs/uxml/` mirror) wraps `harvestLookalike` and `commentOrCdata` as functions: `(...a)=>deps.X(...a)`. Both are RegExp values in `UxmlCategorizedPatchBackSourceModel.js:172-173`.
   - Line 9 then runs `text.matchAll(commentOrCdata)`, which builds a regex from the wrapper's source text. It never matches, so `MUTATION_GUARD_S40_HIDDEN_MARKUP` never fires.
   - **Repro (synthetic):** a RESTRAINT TYPE edit on one row, with `<RESTRAINT NODE="99">` hidden in a comment or CDATA (or a commented `<SIF>`) in another row.
     - base `ddd3ebc7`: `S42_SHARED_EXTERNAL_EDIT_REFUSED`, 3/3 cases
     - head `3f5fd395`: `ok:true` with output bytes, 3/3 cases
     - Reproduced by the reviewer and again by the Oracle.
   - **Oracle check of the fix:** `const {harvestLookalike,commentOrCdata}=deps;` restores the base refusal, 3/3 cases.
   - **Why CI stayed green:** no fast suite, mutant suite or the witness covers this guard. Disabling it survives at base too (an old coverage gap), and the refactor made it a real regression.

### Also required in the repair (task items 2 and 4 not fully met)
2. **Numeric repair text can suggest a refused value** (`UxmlCategorizedPatchBackCarry.js:16-20`, `String(Number(v))`): `1e-7` → "type 1e-7" and `1E21` → "type 1e+21" are themselves non-canonical; `0x10` → "type 16". The suggestion must pass the same canonical check, else fall back to the generic message.
3. **Interleaved-row tests are partly vacuous:** `tests/uxml-b8-leftovers-fast.test.mjs:107-112` passes with an empty inheritedRows array, and the carry-refusal `fileRow`-dropped mutant survives because view and file rows are equal in that test. Pin interleaved A/B/A rows for inheritedRows and carry refusals in a fast Node test.

### Non-blocking (record; may fold in if trivial)
- The element-count refusal row is always min+1 (`UxmlCategorizedPatchBackPreflight.js:25`); duplicating the first element reports viewRow 4. The count text is correct.
- `UxmlCategorizedPatchBackProvenance.js:49-51`: when the view lookup fails (ambiguous repeated rows), the old `row` is not used as a fallback, so the UI shows "—". Line-only refusals are given the first row of the Line.
- The witness cannot see carry guards: the public samples have no cross-Line cases. `symlinkSync` fails with EPERM on Windows accounts without symlink rights.
- Moved guards whose mutants survive: nested-harvest (also at base), Writer projectionOnlyEquivalent, slice1 item count.

**Passed probes (synthetic, LF+CRLF):** interleaved same-Line inheritance accepted with correct, unswapped view/file rows; cross-Line carry refused (classifier non-editable); element add/remove refusal carries counts; AllowableStress still not editable. On these probes, head equals base apart from the new fields.

Draft stays draft. One repair round on the same branch `fix/uxml-b8-leftovers-20261103`. Merge is the Owner's.
