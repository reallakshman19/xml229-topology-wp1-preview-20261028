## [OTM] Oracle verdict · TopoFix PR #35 Lane A STEP 2.A (InputXML read-only into TopoFix) @`fde0fbc6` · **REPAIR** (86/100) · stand-in

**Scores (fresh independent reviewer):** intent 18 · correctness 18 · safety/holds 17 · tests 16 · code 17. The bar is ≥92 total and ≥17 in every category. Repair round 1 of 1.

**Runner:** SUPPORTS.

**What is good (reviewer, executed):**
- The engine is untouched (parser/resolver/analysis/models/transaction have an empty diff). No CLOS, tolerance or 240.6 mm change. Nothing from #23 leaked in.
- The workflow pin to XCU `ddd3ebc7`: all 17 blob hashes match, the checks fail closed, skips are refused, and exactly 13 differences are asserted.
- Python 150 run OK (base 134), with the same 4 skips. Node 112/112. PSI116 behaviour unchanged.
- Every export/apply/compare/preview/CLI path on an InputXML hub refuses `INPUT_XML_APPLY_NOT_ENABLED`, and no file is written. Mixed, mislabelled and tampered hubs refuse with named codes.
- The 13 differences stay UNEXPLAINED. A mutant that adds an allow-list is caught.

### Blocking
**B1. The guards behind the holds can be deleted with every test still green.** 13 of 18 mutants survive:
- M04: the refusal checks only the first source instead of any;
- M05: unanchored cross-run proximity-join refusal (`uxml_adapter.py:241-244`);
- M06: InputXML SHA-to-text check (~:392);
- M07: delta provenance;
- M09: delta sum;
- M10: absolute anchor;
- M11: false-anchored run;
- M12: cross-format unanchored refusal (`uxml_compare.py:~102`);
- M13: cross-format PSI116-source check;
- M15: port sourceRef;
- M16: physical provenance;
- M17: SIF type conflict;
- M18: unauthorized refNo.

The cause is that the tamper test (`tests/test_uxml_s3_caesar.py:95`) accepts any exception, so overlapping checks hide each deletion.

**Fix:** add a test asserting the **exact code** for each guard, so that each mutant above goes RED on its own test. Include:
- all runs unanchored, in both resolve and cross-format compare;
- `sourceText` edited with the hash unchanged;
- the read-only guard tests on a real public XCU InputXML hub, not a `{"sources":[...]}` stub;
- a multi-source hub where InputXML is not first.

Report a mutant table (each mutant → the test that kills it).

### Required in the same round (stand-in decision: fail-closed, no policy change)
- **Native Apply on InputXML must refuse with the named code.**
  - `apply_topofix_transaction` on an InputXML-derived model raises a generic `ValueError`.
  - On a raw InputXML path it returns `committed=True` with reserialized XML in memory. The writer later refuses, but the attempt itself must refuse first.
  - Make both refuse `INPUT_XML_APPLY_NOT_ENABLED` before any work, and add tests.
- **The native resolver CLI on an InputXML file must not report a clean result.** Today it prints "0 findings, 0 blocking" with exit 0. It must refuse with a named code and a nonzero exit; add a test.

### Non-blocking (may be done now or later)
- The adapter ignores XCU `validation.ready=false`. Acceptable for read-only use; disclose it in the work report.
- The workflow path filter covers only 7 paths. Add the engine paths so that an engine change reruns S3.
- Cosmetic issues:
  - stale "all 12 Git blobs" comment (there are 17);
  - duplicate `mkdir`;
  - count check `>=before+15` while the actual delta is 16;
  - non-dict `sources[0]` raises `AttributeError`.

**Next:** coder-a6 repairs on the SAME branch with forward commits only. The PR stays DRAFT. Agents never merge; the Owner merges only after a prototype on real inputs.
