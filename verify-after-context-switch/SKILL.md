---
name: verify-after-context-switch
description: >-
  Use immediately after any git checkout, branch switch, worktree change, directory
  change, pull, rebase, dependency install, or environment switch. Re-establishes facts
  that the switch silently invalidated. Use when something that worked stops working
  after a switch, or when a flag, file or symbol you confirmed earlier is suddenly
  missing.
---

# Verify after a context switch

## When this applies

Any operation that changes which bytes are on disk or which environment a command talks
to, after you have already read something from it:

`git checkout` or `switch`, `git pull`, `git rebase`, `git stash`, creating or entering a
different worktree, `cd`, a package install or lockfile change, activating a different
virtualenv or profile, or pointing at a different environment.

## What to do

**Treat every file-derived fact as invalidated.** Not suspect, invalidated. Anything you
read before the switch describes bytes that may no longer be there.

**Re-check only what you are about to rely on.** This is not a full re-read. It is one
grep per claim you are carrying forward.

```bash
grep -n '<the flag or symbol you are relying on>' <the file that will run>
```

**Re-run preflight.** Confirm the branch and worktree are what you think.

**Watch for the silent variants.** These change behaviour without any visible event:
- a script that ignores unknown flags rather than erroring
- a binary resolved from a different path or version
- a lockfile change that swapped a dependency's behaviour
- a config file present on one branch and absent on another

**Before deleting anything, grep for readers and not just importers.** A static analysis
pass sees imports. It does not see a file read at runtime by path, a reference in a CI
script, or a name assembled from a string. Grep the basename across the whole repository,
including scripts and CI configuration.

**Prove the switch landed.** After a push that used an explicit refspec, confirm the local
ref and the remote ref actually match before acting as though the change is live.

## Founding failure

Two separate incidents, same shape.

A flag confirmed on one branch was relied on after a checkout to another, where the older
script silently ignored it. Two long runs no-oped.

A configuration file was deleted after confirming no TypeScript, build or container
configuration referenced it. A build script read it at runtime by constructing the path
from a URL, which no import graph could see. The user's question, "is anything we are
removing used in the code?", surfaced it.

A related failure: a push whose output was truncated to its last line showed only a hint
about fast-forwards. That hint *was* the rejection. Work continued against a commit that
never landed.
