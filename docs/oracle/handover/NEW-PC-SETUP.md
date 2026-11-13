# NEW-PC SETUP — resume the TopoFix Oracle on another PC (same Claude account)

## 1. Install / sign in
1. Google Drive for desktop, signed in as the Owner → `G:\My Drive\Handoffs` must appear (cards, evidence, R9, and this Oracle state).
2. Claude desktop app (Code tab), same account. Choose the working folder (old PC used `C:\Code D`; masters lived in `D:\CodeD\oracle`). Keep the same paths if possible; otherwise search/replace the paths in the files below.
3. Tools (old PC used portable copies in C:\Users\<you>\tools): Git 2.5x, Node 22, gh CLI (sign in as **reallakshman19**: `gh auth login`), Python 3.12. Low RAM is fine but run one Chrome at a time.
4. Git auth: on the old PC the global .gitconfig set `credential.https://github.com.username=reallaksh19`, which broke pushes. On the new PC set the helper to gh (`gh auth setup-git`) and do NOT set that username, or push with `-c credential.https://github.com.username=reallakshman19`.

## 2. Restore the Oracle state
1. Copy `G:\My Drive\Handoffs\ORACLE-STATE-20261109\oracle\` to `D:\CodeD\oracle\` (or your chosen masters folder). Verify with `SHA256SUMS.txt` in the same Drive folder (`Get-FileHash`).
2. Claude memory: copy `ORACLE-STATE-20261109\claude\memory\*` into the new project's memory folder (`C:\Users\<you>\.claude\projects\<project-key>\memory\`; project-key is the working folder with separators turned into dashes, e.g. `C--Code-D`).
3. Hook: copy `claude\hooks\oracle-compact.ps1` to `C:\Users\<you>\.claude\hooks\` and re-add the PreCompact + SessionStart[compact] entries from `claude\settings.json` (merge by hand; do not overwrite the new settings file).
4. Inputs: GLRD inputs are public (re-download per `downloads\GLRD-INPUTS\MANIFEST.md`) — the Drive pack also has `inputs\` with the two derived configs (bm2-workbench-config.json, R12 config.json) and the rigid ledger needed for the local exact-R9 proof. R9 itself: Drive `Handoffs\RIGID-2.4-R9\bm2-enriched-R9.xml` (sha 5cf2bfbe…).

## 3. Resume
1. Tell Claude: "You are the TopoFix Oracle (Owner stand-in). Read D:\CodeD\oracle\handover\HANDOVER-INDEX.md, then state\lanes.md." (The SessionStart hook prompt also points to TOPOFIX-STORY.md and lanes.md.)
2. Built-in browser pane: sign in to chatgpt.com, then open the coder chats by URL (list in HANDOVER-INDEX / per-project pages). A chat may load blank at first — wait or reload once; never type into a blank page.
3. Re-create the 20-min check: CronCreate `7,27,47 * * * *` with the prompt from `state\check-prompt.txt` plus the latest state line from lanes.md (cron jobs do not survive a restart).
4. Heartbeat: `powershell -NoProfile -File D:\CodeD\oracle\tools\heartbeat.ps1 check` / `write -Note "..."`.
5. Repeat the open Owner questions (HANDOVER-INDEX section 5) before doing anything else.

## 4. What NOT to restore
Review checkouts (topofix-agents\or-*, rb-*, rev-*, oracle\scratch\run-*\src, wt-*) — recreate from the SHA when a gate needs them (`git worktree add --detach <dir> <sha>`). Browser profiles, Chrome logs. The staged-deletion noise in old main clones.
