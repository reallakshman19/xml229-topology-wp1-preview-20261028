# TopoFix buddy runner: runbook (Owner idea, 31 Oct 2026 20:43)

**What it is:** a cheap local helper (a Sonnet subagent) that runs the checks on an agent's return. It runs at each logical checkpoint, meaning a `work_returned` receipt on #12 or #239. The ChatGPT agents cannot run anything on the Owner's Windows machine or touch the Owner's files. The runner does that for them.

**Order at each checkpoint:**
1. The **runner** re-runs everything below and returns a short fixed result.
2. The **independent reviewer** scores the work (≥92 total, ≥17 per part).
3. The **Oracle** reads both and decides the next step, or asks the Owner.

The Oracle never re-runs a check the runner has already reported.

## Rules
- **Read-only on tracked files.** No commits, pushes or GitHub comments.
- **Always use a git worktree** under the scratchpad. Never switch branches in `topo-a` or `topo-b`: the Owner's trial servers (8765 serves topo-a, 8766 serves topo-b) show whatever is checked out there. Remove each worktree when done.
- **The private benchmark** is `<OWNER_PRIVATE_FILE>`:
  - local use only;
  - outputs go only to the scratchpad;
  - never print its contents, node names, coordinates or hash;
  - report only EQUAL / DIFFERENT, op counts by kind, and error codes.
- **Report NOT_RUN** for anything not run. Never infer a result.

## Paths
- TopoFix: `D:/CodeD/topofix-agents/topo-a` (remote `reallakshman19/xml229-topology-wp1-preview-20261028`).
- XML_Compare_Utilities (XCU): `D:/CodeD/topofix-agents/topo-b`.
- Scratch: `C:/Users/reall/AppData/Local/Temp/claude/D--CodeD-xml229-topology-wp1/013bfede-8ea3-425e-af50-a90b2554f690/scratchpad` (`$S`). It contains `xmldom-rt9`.

## Checkout (both repos)
```
git -C <repo> fetch -q origin pull/<N>/head:rb-<N>
git -C <repo> worktree add "$S/rb-<N>" rb-<N>
```
- Confirm `git -C "$S/rb-<N>" rev-parse --short=8 HEAD` matches the receipt's head.
- The TopoFix pinned XCU commit is the 40-hex SHA in `.github/workflows/uxml-*.yml`. Make an XCU worktree at exactly that SHA: `git -C topo-b worktree add "$S/xcu-pin-<PR>" <sha>`.
- Name every worktree with the PR number (`rb-<PR>`, `xcu-pin-<PR>`). Parallel runners share topo-b; never reuse or remove a worktree you did not create.

## TopoFix checks (run from the worktree root)
1. `python -m unittest discover -s tests -p "test_*.py"`: report OK / FAILED with the skip count.
2. `node --test tests/*.test.mjs`: report pass/fail.
3. Cross-repo: `PYTHONPATH="tests;." XCU_UXML_ROOT="$S/xcu-pin-<PR>" python -m unittest tests.test_uxml_psi116_s1 tests.test_uxml_psi116_s2` (plus any new `test_uxml_*` named in the receipt).
4. Real file, **step 1 (in)**:
   ```
   node "$S/xcu-pin-<PR>/tools/psi116-to-uxml.mjs" "$F" > "$S/owner.uxml.json"
   python -m converters.psi116_topology_resolver.uxml_compare "$F" "$S/owner.uxml.json"
   ```
   Expect EQUAL.
5. Real file, **step 2 (back)**, when `uxml_export_ops.py` exists:
   ```
   python -m converters.psi116_topology_resolver.uxml_export_ops "$F" "$S/owner.ops.json" --uxml "$S/owner.uxml.json"
   python -m converters.psi116_topology_resolver.uxml_patch_psi116 "$F" "$S/owner.ops.json" --uxml "$S/owner.uxml.json" --output "$S/owner.patched.xml" --validation "$S/owner.val.json"
   ```
   Expect EQUAL twice. Report the op count by kind (baseline 31 Oct: 101 × ALIAS_COINCIDENT_NODE).
6. When the receipt touches the browser UI: NOT_RUN locally unless the Oracle asks; quote the CI Chromium result instead.

## XCU checks (run from the worktree root)
1. `node --test` on the test files named in the receipt. Baseline at 9f51bfca: `tests/uxml-psi116-s1*.test.mjs` 10/10 plus `tests/uxml-s1-followup-mutants.test.mjs` 2/2 (12 in all).
2. Workspace tests: on the TOPO-B branches (#241) `tests/inputxml-workspace-*.test.mjs` = 20/20; on main-based branches they are `*.test.js` (6/6 at #244). Use whichever exists.
3. From `prototypes/ciifr-map`: `CIIFR_TEST_RUNTIME="$S/xmldom-rt9" node --test tests/*.test.mjs`. Baseline 61/63; the 2 known main failures are app-startup-ownership and "unlinked physical TARGET". Anything else is new.
4. Step 3 (InputXML) cross-format benchmark: use the commands from the receipt. On a real file, the Owner makes the InputXML through the Workspace. The runner reports NOT_RUN unless that file exists locally.

## Result format (≤200 words)
```
RUNNER · <assignment> · <repo>#<PR> @<head8> · <time>
HEAD MATCH: yes/no
TESTS: python <..> · node <..> · cross-repo <..> · xcu <..> · ciifr-map <..>
REAL FILE: S1 <EQUAL/DIFFERENT/NOT_RUN> · S2 <EQUAL/DIFFERENT/NOT_RUN> (<ops by kind>)
NEW vs BASELINE: <none | list>
NOT_RUN: <list>
CLEANUP: worktrees removed yes/no
```
