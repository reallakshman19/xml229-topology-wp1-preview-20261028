# PC-change handover plan — 9 Nov 2026 (TopoFix Oracle, Owner stand-in)

Goal: every project stops at a clean checkpoint, nothing that exists only on this PC is lost, and a new Oracle on the new PC can resume each lane from one page.

## 0. What the inventory found (02:40Z 9 Nov)

| Kind | Where | Status |
|---|---|---|
| Product code of all 5 projects | GitHub | **Safe.** Every gated head is on GitHub (PR branches or main). |
| ~45 review checkouts (or-*, rb-*, rev-*, run-*\src, wt-head) | D:\CodeD\topofix-agents, oracle\scratch | Detached at pushed SHAs. **Disposable**; recreate from SHA when needed. |
| Huge "dirty" counts in 3dc-v05a (4758), topofix (138), xcu (8819) | main clones | All staged **deletions** left by sparse-checkout/worktree setup. **Not work. Do not commit.** |
| **Local-only commits** | v0.4 repo | `d40a6db` fix(xml-cii): PSI116 reducer internal edge (branch fix/xml-cii-reducer-internal-edge-r1.4, 6 Nov). `06ab1c4` fix(deploy): Pages sync 20 min (branch codex/pages-deploy-timeout-20261107, 7 Nov). |
| **Uncommitted work** | see list in section 3 | 7 items, mostly Codex-coordinator WIP plus one rigid prototype from 4 Nov. |
| **Oracle state** | D:\CodeD\oracle (1.26 GB, of which scratch 1.2 GB) | **Not in git at all.** lanes.md, story, cards, protocol, WBS, gate reports, probe scripts, tools. |
| Oracle memory, hooks, settings | C:\Users\reall\.claude\ (memory, hooks\oracle-compact.ps1, settings.json) | Local only. |
| GLRD inputs | D:\CodeD\downloads (131 MB) | Public (re-downloadable) except the derived configs: GLRD-INPUTS\derived\bm2-workbench-config.json and scratchpad\run-perf-r10\fx\config.json (R12 Oracle config). |
| Owner files (R9 XML etc.) | G:\My Drive\Handoffs | Already in Drive, syncs to the new PC. Stay out of GitHub. |

All GitHub repos are **public**, so Oracle state (which quotes Owner data paths, chat ids and R9 details) goes to **Drive**, not GitHub. Only the redacted docs already published through PR #27 go to GitHub.

## 1. Checkpoint per project

| Project | Checkpoint to reach before the move | Effort | Handover state |
|---|---|---|---|
| **A** TopoFix #36 (coder-a6) | Already clean: PR #36 merged 7 Nov. | none | "Idle. Next: A4 follow-up card (Owner OK needed)." |
| **B** XML Compare (coder-b8) | Already clean: #258 (7dc17dee) and #259 (e09c81d1) merged; main = e09c81d1. | none | "Idle. Optional follow-up card from reviewer notes (0.001 mm boundary, row-0 near-sentinel, FROM_/TO_ case, units)." |
| **C** (coder-c1) | Not opened. | none | "Not started; Owner: later." |
| **Perf** v0.5a (perf-coder-2) | **Recommended: finish the 1.R15 gate** (resume the stopped runner; it already finished mutants and part of the Chrome timings). Fallback: freeze as "RETURN at b66b29c1, gate pending, partial runner data in scratch\run-perf-r15". | ~1-2 h | Gate verdict + next card (or REPAIR card drafted) recorded. |
| **Rigid** PR #406 (rigid-coder-3) | **Recommended: read the S2-R2 RETURN and gate it** (head 461c0d1d; Drive evidence present). Must confirm the R9-derived fixture is gone from the head. Fallback: freeze as "RETURN in, gate pending". | ~45-60 min | Gate verdict recorded; release stays BLOCKED. |
| Side bug | BM2 UI Run fails in the converter (REDUCERS/PSI116) at every version. Note: the local-only commit d40a6db ("PSI116 reducer internal edge", v0.4) may be related — push it so it is not lost. | — | Listed as an open Owner item. |

Rule while finishing: no new cards are sent after the gates; coders are left idle at a RETURN or with a drafted (unsent) card, so nothing is mid-flight during the move.

## 2. Handover pack (one file per project + index)

Written to D:\CodeD\oracle\handover\ and copied to Drive:
- `HANDOVER-INDEX.md` — the 5 projects in one table, open Owner questions, rules (R-LT9/R-LT10, never merge without Owner word per PR, ask before cards/pushes/posts, at most 3 agents), how to restart the 20-min check.
- `HANDOVER-A.md`, `-B.md`, `-C.md`, `-PERF.md`, `-RIGID.md`, each with: repo + branch + head SHA + PR; last gate and its reports; next step; coder chat URL and role; card history (file, size, sha, Drive folder); open questions; exact commands to recreate the review checkout; known traps (e.g. 3D_Converters needs `git -c core.protectNTFS=false`; never commit R9 or derived copies; DOM.disable before perf timing).
- `NEW-PC-SETUP.md` — tools (portable Git, Node 22, gh signed in, Python 3.12), Google Drive for desktop with G:\My Drive\Handoffs, restore D:\CodeD\oracle from Drive, restore memory/hooks/settings, re-create the cron from state\check-prompt.txt, sign in to ChatGPT in the browser pane, reopen the coder chats by URL.

## 3. What goes where

**A. GitHub — push as new backup branches only** (no PR, no main, no force-push). Needs your OK per item:
1. v0.4 `fix/xml-cii-reducer-internal-edge-r1.4` (commit d40a6db) + its uncommitted workreport → push branch.
2. v0.4 `codex/pages-deploy-timeout-20261107` (06ab1c4) → push branch.
3. v0.4 worktree wt-codex-pr3-integration: staged, uncommitted per-build-cache work (Codex) → commit to `wip/handover-20261109/pr3-per-build-cache`, push.
4. v0.4 worktree wt-codex-pr56-weight-fix: untracked workreports → commit to its branch (or wip/…), push.
5. v0.4 main clone: modified split-rigid-weight-propagation.js → commit to `wip/handover-20261109/split-rigid-weight`, push.
6. v0.5a rigid-verify worktree: uncommitted rigid_mass_assignment.py + 2 tests + 2 modified converters (4 Nov) → commit to `wip/handover-20261109/rigid-mass-verify`, push. **Earlier Owner rule: "rigid commits are local-only, never pushed" — needs your explicit override, or this goes to Drive instead.**
7. Common repo clone: PROTOCOL.md edit (+50 lines) on branch oracle-continuity/convergence-discipline-20261106 → commit, push branch.

**B. Google Drive (private, syncs to the new PC):** `G:\My Drive\Handoffs\ORACLE-STATE-20261109\`
- D:\CodeD\oracle without bulky scratch checkouts (keep every *.md report, probe/tool scripts, mutants JSON; drop src\, wt-*\, r9\ copies, ui-* profile dirs) — estimate ~70-100 MB.
- memory dir, hooks\oracle-compact.ps1, settings.json (no secrets inside — checked before copy), the two derived configs.
- A ZIP plus SHA256SUMS so the new PC can verify.

**C. GitHub docs (public, redacted):** refresh PR #27 docs/oracle via sync-oracle-docs.ps1 (privacy gate must be clean; update its memory path to C--Code-D first). Optional — Drive already has the full copy.

**D. Leave behind (disposable):** all detached review checkouts, run-* worktrees, the sparse-checkout deletion noise, browser profiles.

## Owner decisions (9 Nov)
- Gates: **finish both (perf 1.R15, rigid S2-R2) first** = the checkpoint.
- Pushes: **after the checkpoint**, not now ("no hurry to pack up; plan for a checkpoint and then push"). Push list in 3A to be confirmed at that point.
- Oracle state: **Drive + redacted docs** (3B and 3C).

## 4. Order of work

1. (now) Reopen coder chats; read S2-R2 RETURN; resume perf runner. [needs nothing new]
2. Gate S2-R2 and 1.R15; record verdicts; draft (not send) any repair card.
3. On your OK: pushes in section 3A, each verified on GitHub (branch exists, SHA matches).
4. Write the handover pack (section 2).
5. Copy Oracle state to Drive (3B); verify hashes on the Drive copy.
6. Final lanes.md entry "HANDOVER CHECKPOINT 9 Nov", heartbeat, stop the cron.
7. On the new PC: follow NEW-PC-SETUP.md; first action = read HANDOVER-INDEX.md, then lanes.md.
