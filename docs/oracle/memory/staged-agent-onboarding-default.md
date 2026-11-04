---
name: staged-agent-onboarding-default
description: "Owner rule (1 Nov 2026) - onboard every new or replacement agent in Oracle mode with 3-5 short staged prompts, each ending in a check, before the task; never one bulk prompt."
metadata:
  node_type: memory
  type: feedback
  originSessionId: 013bfede-8ea3-425e-af50-a90b2554f690
  modified: 2026-10-31T23:53:58.866Z
---

When I bring in a new agent, or replace one whose chat is full, I onboard it in 3 to 5 short prompts, each ending in a check question. I send the next prompt only after a correct answer, and the task comes last. This is the default in Oracle mode, especially when there is no buddy-runner or checkpoint handover. The Owner said to add it to the coordinator-protocol skill later; I wait for the Owner's go before editing the skill.

**Why:** On 1 Nov 2026 both TopoFix coders hit their chat limits. The Owner said: "Do not provide since bulk prompt to new agent but help them construct with min 3 -5 prompt then provide task", and then "this '5 step on board of new agents' approach should be default in Oracle mode. add to skill later." It worked: both replacements passed every check, and one of them found unreported work (PR #22) from its checkpoint.

**How to apply:** The template is D:/CodeD/xml229-topology-wp1/handover/TOPOFIX-NEW-CODER-ONBOARDING.md:
1. Who you work for, and the rules. Check: a five-line playback.
2. The Owner's intent in the Owner's words, the decisions, the holds, and what's done. Check: three one-line answers.
3. The exact files to read for this agent. Check: file:line answers.
4. How to work and return. Check: its base head and return issue.
5. The task.

Fix a wrong answer with a one-line correction, never a resend. See [[agent-links-with-names]] and [[topofix-owner-stand-in]].
