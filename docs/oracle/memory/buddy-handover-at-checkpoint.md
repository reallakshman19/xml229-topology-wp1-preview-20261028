---
name: buddy-handover-at-checkpoint
description: "Owner rule (1 Nov 2026) - when a coder chat nears its message limit, plan the handover at a checkpoint; the successor (\"buddy\") completes one mini task together with the outgoing agent before it retires."
metadata:
  node_type: memory
  type: feedback
  originSessionId: d2448049-7a1c-40aa-9cb7-82f273120f0b
  modified: 2026-11-01T15:30:42.723Z
---

When a coder's chat is close to its message limit, I don't let it run until it breaks. At the next checkpoint (a returned receipt, never mid-task), I open a successor chat (the "buddy") and the buddy completes one small, well-specified task while the outgoing agent is still available. The outgoing agent spends at most two messages: (1) writing a handover checkpoint to GitHub, (2) checking the buddy's diff against its own intent (CONFIRM or up to 3 misses). The normal runner and fresh independent reviewer still run on the buddy's work; the outgoing agent's check is not the independent review.

**Why:** On 1 Nov 2026 the Owner said coder-a2 and coder-b2 were "at the verge of message limit, so plan for buddy runner at a check point. buddy runner should complete one mini task with outgoing agent". Earlier the same day, coder-a's chat filled mid-task and unreported work (PR #22) was only found later from its checkpoint.

**How to apply:** Combine with the staged onboarding in the xml229 project memory (staged-agent-onboarding-default): the buddy's prompt 3 becomes "read the outgoing agent's handover file and PR". Good mini tasks are small and precisely specified, like a test-only repair round with file:line items. Opening new chats on the Owner's accounts still needs the Owner's yes. The Owner's word "buddy runner" here means the successor chat, not the Sonnet test-runner subagent from the runbook. See [[vertical-split-coders]].
