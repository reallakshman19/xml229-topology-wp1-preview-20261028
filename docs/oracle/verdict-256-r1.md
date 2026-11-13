## [OTM] Oracle verdict · XCU PR #256 UXML-B8-LEFTOVERS R1 @`b24d23d4` · **PASS** (92/100)

**Scores (fresh independent reviewer):** intent 18 · correctness 19 · safety/holds 20 · tests 18 · code 17. The bar is ≥92 total and ≥17 in every category: met, at the minimum.

**Runner (independent, Node 22, exact head):** SUPPORTS. Every receipt count matched locally:
- b8 tests: 200/200; mutants LF/CRLF 34/34
- fast: 20/20
- r2-carry: 35/35
- b7: 21/21; mutants 9/9
- s42: 50/50 and 52/52, plus mutants
- s41: 64/64
- s3: 22/22
- s4-0: 86/86
- admission: 20/20
- witness: 171 attempts, 0 mismatches
- mirrors: 10/10 byte-identical, longest 212 lines

CI: 8/8 green at the exact head.

**R0 blocker fixed:**
- The RegExp deps are destructured directly again, and the hidden-markup guard is live.
- Hidden comment/CDATA/SIF edits refuse with `S42_SHARED_EXTERNAL_EDIT_REFUSED` and write no bytes.
- Removing that guard now turns the tests RED (reviewer mutant).
- Head and base give the same accept/refuse decision on 182 synthetic probes (LF and CRLF).

**Non-blocking (follow-ups, not part of this PR):**
1. Snapshot-route refusals still show line, viewRow and fileRow as null. This is the same as base.
2. A duplicated-Element refusal reports a viewRow past the baseline rows (`min+1`).
3. Two split functions are still ~145 and ~160 lines.
4. A mutant on the moved S4.0 exact-block identity check survives. The code is identical to base, so this is an old gap.
5. The witness script uses symlinkSync, which fails with EPERM on Windows. It also replays only the public samples.
6. The A/B/A test is LF only, and UI row columns are covered only by Playwright.
7. The `0x10`/`0b11` numeric hints are debatable.

**Not run locally:** editability-public and Playwright. CI runs both.

**Next:** this PR stays DRAFT. Agents do not merge. The Owner merges only after a prototype on real inputs.
