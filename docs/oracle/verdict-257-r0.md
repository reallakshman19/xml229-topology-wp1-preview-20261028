## [OTM] Oracle verdict · XCU PR #257 Lane B STEP 1.1 (edit-ops v1 + InputXML ALIAS) @`783a8643` · **REPAIR** (76/100) · stand-in

**Scores (fresh independent reviewer):** intent 17 · correctness 14 · safety/holds 15 · tests 14 · code 16. The bar is ≥92 total and ≥17 in every category. Repair round 1 of 1.

**Runner:** SUPPORTS.
- The diff is exactly the 5 new paths.
- New tests: 24/24 and 12/12.
- Existing suites S3 30, S4.1+S4.2 116, B7+B8 221 and S1 10 show the same counts at base and head: no regressions.
- CI 3/3.

**What is good (reviewer probes, LF and CRLF):**
- 3-way SHA, exact keys, unwidenable policy.
- Full target set and duplicate refusals.
- Stranded NODE/NODE1/CNODE, SIF and loss-contract refusals.
- No substring bleed (10 vs 100).
- Quoting, BOM and multibyte handled.
- Bytes outside the ledger byte ranges are identical, and no refusal ever returns bytes.
- PSI116 and every other kind refuse NOT_IMPLEMENTED.

### Blocking
**B1. The stranded-reference guard is weaker than #23.**
- `UxmlEditOpsPatchBack.js:51-56` (`finiteNode`, used at :131 and :143) does not match node values such as `40.` or `4.0E1`.
- Strict S3 accepts them and they mean node 40.
- Repro: a synthetic fixture plus `<RESTRAINT NODE="40." …/>`, alias 40→20. The result is `ok:true` with the restraint still on node 40. #23 (Decimal) refuses this.
- **Fix:** compare node witnesses numerically, Decimal-equivalent, or refuse any non-canonical node witness. Add a test per form.

**B2. ALIAS_COINCIDENT_NODE is accepted without coincidence evidence.**
- `:189-201` requires neither that `canonicalNode` exists nor that the two nodes coincide.
- Repros:
  - alias 40→999 (999 not in the model) gives `ok:true`, a pure renumber;
  - on the public delta-only fixture `uxml-s3-synthetic.workspace.delta-only.input.xml`, 16 joins across disconnected runs give `ok:true` (e.g. 10→100; in the absolute twin those nodes are 1000 units apart).
- This breaks the hold "a questioned connection is never auto-joined".
- **Fix (no tolerance change):** refuse unless
  - (a) `canonicalNode` is an existing original endpoint, and
  - (b) coincidence is proven from the original. Both nodes must have resolved absolute positions in the same S3-anchored frame that are equal under the reader's existing comparison.
  - Otherwise refuse with a named code (e.g. `INPUT_XML_ALIAS_COINCIDENCE_NOT_PROVEN`).
  - Delta-only runs that are not anchored to each other therefore refuse.
  - Tests: owner absent, cross-run delta-only, and absolute non-coincident must all refuse; a true coincident pair is accepted.

### Required in the same round
- **Mutants:** these guards must each be killed by a test:
  - byte-parity call (:263);
  - re-read endpoint and count checks (:258-262);
  - field-conflict, overlap and chained-id checks (:191-192, :209, :223, :243);
  - the locate duplicate and raw-equality checks.
  - `UNACCOUNTED` (:229): delete it if it is unreachable, otherwise kill it with a test.
- **Tests:**
  - a multi-op envelope (two independent aliases);
  - a different-length replacement (`"40"`→`"999"`-style lexical width change, with the ledger byteRange correct);
  - BOM, multibyte and quoting cases moved into the committed suite;
  - one real public sample that goes past the kind gate.
- **Comment at :120-121:** it must match the code; comment and CDATA text is blanked, not refused.

### Non-blocking (may be done now or later)
- `applyUxmlEditOps` is about 105 lines; split it.
- The catch-all at :267 maps every exception to SCHEMA; use an INTERNAL code.
- Endpoint whitespace and non-canonical endpoints report misleading codes.
- Add `agents/PR257_workreport.md`.
- The new workflow file is authorized by the Oracle stand-in for this PR.

**Next:** coder-b7 repairs on the SAME branch with forward commits only. The PR stays DRAFT. Agents never merge; the Owner merges only after a prototype on real inputs.
