---
name: session-preflight
description: >-
  Use at the start of a session, after any directory change, and before the first
  command that writes, deploys, or touches a remote. Establishes which repository,
  branch, worktree and credential profile you are actually on. Use whenever the user
  says "wrong branch", "wrong env", "which repo are you in", "that's not the right
  one", or names an environment that differs from the one you have been using.
---

# Session preflight

## When this applies

Any workspace with more than one checkout, more than one environment, or more than one
credential profile. The risk is not knowing a fact; it is carrying a stale one.

Specifically: at session start, after `cd`, after `git checkout` or `git switch`, after
the user names an environment, and before the first state-changing command.

## What to do

Run the check and state the result in one line before acting.

```bash
bash scripts/preflight.sh
```

Or inline, if you would rather not ship the script:

```bash
pwd; git rev-parse --abbrev-ref HEAD 2>/dev/null; git status --porcelain 2>/dev/null | wc -l
```

Then, before the first write:

1. **Name the target back to the user.** Repo, branch, and environment, in one line.
   Not a question, a statement they can correct in three words.
2. **Check the branch is the one you should be on.** If it is someone else's ticket
   branch, or `main`, or `master`, say so and ask before editing rather than after.
3. **Check for a linked worktree.** A branch can be checked out in only one worktree.
   `git checkout <branch>` fails with "already checked out at ..." when it lives
   elsewhere. Build in whichever worktree holds it, or pass the path explicitly.
4. **Check the credential profile** if the task touches a cloud or a remote. An expired
   or default profile silently targets the wrong account.
5. **Re-run this after any switch.** See `verify-after-context-switch`.

Say what the check printed. Do not say "we're on the right branch" unless you read it.

## Founding failure

A workspace with about twenty sibling checkouts of the same repository and five
environments. Corrections of the form "not that environment, the other one" and "check
what branch you are in when you work" recurred across months. The cause was never
carelessness; it was that nothing established the target before work began, so a session
resumed after two days inherited whatever directory it happened to start in.

In one instance an agent described a script's supported flags correctly for the branch it
had read, then recommended a checkout of a different branch in the same worktree. The
older script on that branch ignored the flag silently. Two twenty-five minute runs did
nothing, and neither reported an error.
