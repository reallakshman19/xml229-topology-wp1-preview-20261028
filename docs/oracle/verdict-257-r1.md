## [OTM] Oracle verdict · XCU PR #257 Lane B STEP 1.1 repair round 1 @`08fb8b11` · **REPAIR** (81/100) · stand-in · round limit reached, next round needs the Owner

**Scores (new fresh independent reviewer):** intent 18 · correctness 15 · safety/holds 14 · tests 17 · code 17. The bar is ≥92 total and ≥17 in every category.

**Runner:** SUPPORTS the RETURN.
- Forward commits only.
- Probes: 36/36 B1 witness spellings refuse, and 42/42 delta-only pairs refuse.
- The real coincident pair is accepted.
- Existing suites are the same at base and head.

The runner's probes did not cover the two new cases below. Its untested-guard notes are carried as non-blocking:
- comment/CDATA blanking;
- `port.coordinateFrame`;
- `Number.isSafeInteger`.

**Every item the previous round required is present and verified:**
- numeric node witness (`:55-61`);
- coincidence proof (`:152-176`);
- mutation-killing tests, 27/27, each with a green control;
- UNACCOUNTED removed, with the reason given;
- multi-op, width-change byteRange, BOM/multibyte/quote and public-sample tests;
- the comment now matches the code.

Main suite 47/47. Regression suites 377/377.

### Blocking
**B-1. The coincidence check compares against an anchor, not pairwise, so it widens the reader's tolerance up to 2x** (`uxml/UxmlEditOpsPatchBack.js:172-175`).
- Every occurrence is compared only to `absorbed[0]`.
- Repro (synthetic, anchored): the owner at x−0.0009 and the two absorbed spellings at x and x+0.0009. The alias returns ok:true, and node 20 ends up with two positions 0.0018 apart, which is more than the delta tolerance.
- S3 doesn't catch it because the per-spelling formatting ("20" vs "20.000000") makes S3 see two separate nodes.
- **Fix:** require every occurrence pair (or all pairs) to be within tolerance. Alternatively, refuse when an id has more than one raw spelling or position. Add the repro as a test plus a mutant.

**B-2. The stranded-reference scan is incomplete** (`checkStranded`, `:124-151`). Each of the following passes S3, and alias 40→20 returns ok:true with node 40 still referenced:
- a character reference `NODE="&#52;0"` or `&#x34;0` inside a PIPINGELEMENT;
- the element text `<NODE>40</NODE>`;
- a node attribute on a sibling outside PIPINGELEMENT (under PIPINGMODEL or CAESARII).

**Fix:** decode character references before the numeric compare, or refuse any `&#`. Scan or refuse non-whitespace descendant text. Scan or refuse node-like attributes outside PIPINGELEMENT. Add a test for each.

### Required in the same round
- Parse decimals exactly in `finiteNode`: today "40.0000000000000001" is read as 40, which contradicts the "without rounding" comment.
- Patched occurrences take the owner's exact raw spelling, or the patch refuses when spellings are mixed. This keeps S3 and CAESAR topology the same after the patch.

### Non-blocking
- Real-file over-refusal through lossContract property values: safe, but document it. The same applies to commented-out content.
- Misleading codes: an unparseable endpoint gives `RENUMBER_SELF_LOOP_REFUSED`, and an unknown source node gives COINCIDENCE.
- `need(count>0)` at `:266` can never fail; remove it or cover it.

### Independent reviewer (ChatGPT ir-257, OnBoard-IR, Stage 1 cold, then Stage 2 on this head)
- **Exposure:** none before Stage 1. Earlier reviews were withheld from Stage 2.
- **Verdict:** NO-GO for Apply at this head.
- **It independently found both blockers above:**
  - B-1, pairwise coincidence (its P8/B4);
  - B-2, character-reference stranding (its P4/B1).
- **It promotes these to blocking:**
  - P6: exact decimal node identity (`40.000000000000000001` must refuse);
  - P7: patched tokens must use the owner's exact raw spelling, otherwise S3 and CAESAR see different topology;
  - P11: the post-patch oracle must check every numeric node reference, not only the endpoints.
- **It marks as required:**
  - P5: known child carriers (BEND NODE1-3, SIF NODE/BRANCHNODE, RESTRAINT/HANGER NODE/CNODE, DISPLACEMENTS NODE_NUM) are refused today, never patched;
  - B6: `BEND RADIUS="40"` is falsely refused through the generic loss-number scan.
- **It recommends a different design:**
  - a typed allow-list inventory over the whole document;
  - unknown carriers refuse;
  - XML character references decoded;
  - exact decimal identity;
  - owner raw spelling;
  - all-pairs proof under the existing 0.001 mm;
  - a full numeric re-read oracle.

  The full spec is held by the Oracle.

**Owner decision (5 Nov):** a FINAL repair round 2, built on the IR's R1-R6 spec (typed whole-document node-carrier inventory, unknown carriers refuse, XML character-reference decoding, exact decimal identity, owner raw spelling, all-pairs coincidence under the existing 0.001 mm, full numeric re-read oracle). It applies on the SAME branch with forward commits only; no tolerance or policy change. If it fails, the step stops for a rethink. The PR stays DRAFT. Agents never merge.
