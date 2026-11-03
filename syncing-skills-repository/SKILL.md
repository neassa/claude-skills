---
name: syncing-skills-repository
description: >-
  Use when adding, editing, removing, or importing files in a local agent-skills
  directory that has a GitHub mirror, especially when the user has asked for
  automatic updates.
---

# Syncing a skills repository

When the user has authorized ongoing updates, syncing is part of finishing any task that changes the local skills directory. A missing request in the current turn does not revoke that standing instruction.

## Procedure

1. Find the configured sync helper and confirm its target repository and branch.
2. Check the target worktree for unrelated changes that the helper could stage or overwrite. Protect them; do not silently include them.
3. After the skill changes are complete, run the helper without asking for routine confirmation.
4. Verify its exit status and repository state. Report a successful push only after confirming it; if there were no changes, report the no-op without treating it as a reason to ask about future syncs.
5. If the helper fails, state the failure and what remains unsynced. Do not claim completion.

Do not set up a background watcher unless the user specifically asks for continuous process-level automation. This skill means automatically syncing at the end of each skill-changing task.

## Quick reference

| Situation | Action |
|---|---|
| Skill files changed and ongoing sync is authorized | Run the configured helper before handoff |
| Helper reports no changes | Report no-op; keep the standing behavior |
| Helper fails or target contains unrelated changes | Protect data and report the blocker |
| No standing authorization or configured mirror | Do not assume a remote push is authorized |

## Common mistake

Offering a command for the user to run, or asking whether to sync after they have already requested automatic updates, makes the user repeat a standing instruction.

## Why this rule exists

On 2026-11-03, after the user requested ongoing updates to the skills repository, the assistant offered a manual sync option instead of making sync the default. The user had to clarify, “do it automatically don't ask for it.” The mistake was reachable because the helper was treated as a one-off command rather than part of completing skill changes. The cheapest check is to look for this trigger whenever changing the local skills directory.
