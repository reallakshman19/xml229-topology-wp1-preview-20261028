# XCU #257 · Local test-run plan (Oracle, 5 Nov)

Purpose: turn the final-round blockers into a fixed local acceptance run on this PC. Any rethought design must pass it before it reaches a reviewer. Nothing is pushed or posted; Owner files stay local, and only counts and EQUAL/DIFFERENT are reported outside this PC.

## Setup
- Worktree `D:\CodeD\topofix-agents\rev-257r2` detached at `d4ccec7c` (new worktree; no branch switches).
- Node: `C:\Users\reall\tools\node`. Git: `C:\Users\reall\tools\git\cmd`.
- Suite folder: `D:\CodeD\oracle\localtests\xcu257\`, outside the repo. It holds:
  - the reviewer probes `p1`–`p4` and `realscan`, plus `lib.mjs`, promoted from scratch `r2x`;
  - the runner's 55 R1–R6 probes;
  - `run-all.ps1`, which takes a worktree path as its parameter.
- Output: one table per run (case, expected, actual, PASS/FAIL), saved to `oracle-docs\xcu257-local-<head>.md`.

## Cases
| ID | Case | Expected (correct behaviour) | At d4ccec7c (Oracle run 5 Nov) |
|---|---|---|---|
| LT-1 | Two ops with the same owner, A and C 0.0018 mm apart (40->20 + 80->20) | refuse ALIAS_COINCIDENCE_NOT_PROVEN, no bytes | RED: OK, ledger 2, bytes |
| LT-2 | Hidden absolute anchor spelled `from_X` / `From_X` | refuse (same as `FROM_X`) | RED: OK, ledger 2, bytes |
| LT-3a | RESTRAINT NODE=20 CNODE=40, alias 40->20 | refuse, child record would self-connect | RED: OK, `NODE="20" CNODE="20"` |
| LT-3b | HANGER NODE=40 CNODE=20 | refuse | RED: OK, `NODE="20" CNODE="20"` |
| LT-3c | SIF NODE=20 BRANCHNODE=40 | refuse | RED: OK |
| LT-3d | BEND NODE1=40 on an element ending at 20 | refuse | RED: OK |
| LT-4a | Public GREInputxml.xml through the inventory | inventory passes; reaches the coincidence step | RED: UNKNOWN_NODE_CARRIER on HYDRO_PRESSURE (8 ordinary fields block) |
| LT-4b | Public PLB314Inputxml.xml through the inventory | same | RED: blocked on 25 ordinary fields (TEMPERATURE1-16, SY, ...) |
| LT-4c | Public-derived anchored coincident pair | OK, byte parity, strict S3 re-read EQUAL | not reachable (blocked by LT-4a/b) |
| LT-5 | Controls: the runner's 55 R1–R6 probes; single-op 80->40 refuses; true coincident pair OK; unanchored pairs refuse; chained and duplicate ops refuse | unchanged | GREEN: 54/55, with 1 probe bug since fixed |
| LT-6 | Owner real InputXML files (local only) through the inventory | list of the field names that block, plus counts; this becomes the real-schema allow-list input | NOT_RUN: needs the Owner's file location |
| LT-7 | Mutants: one per new guard (group all-pairs, case-insensitive witness, child self-connect, schema allow-list) | each turns its LT case RED | after a fix only |

## Gate
- At d4ccec7c: LT-1 to LT-4 RED (confirmed), LT-5 GREEN. This is the baseline that proves the suite detects the defects.
- A future attempt is admitted to review only if LT-1 to LT-5 are all GREEN, LT-6 shows 0 blocking ordinary fields on the Owner files, and LT-7 kills every new guard.
- Run time: about 5 min for LT-1 to LT-5. LT-6 depends on the Owner files.

## Not in scope
No coder card and no third round. Per the Owner rule, the final round failed, so this is a rethink. The plan only fixes how we test.
