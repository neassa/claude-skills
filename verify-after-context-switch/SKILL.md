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
ref and the remote ref actually match before acting as though the change is live. Two
mechanics make them drift: `git push origin HEAD:<branch>` from a detached worktree moves
the remote but leaves the local `<branch>` ref where it was, so the next worktree made from
it diverges; and a clone whose fetch refspec tracks one branch never creates
`origin/<other>` — `git fetch origin <other>` writes only `FETCH_HEAD`. Fetch with an
explicit `+refs/heads/<b>:refs/remotes/origin/<b>` and compare `git rev-parse` of both
sides; never judge a push by its last output line.

## A resume or compaction is a context switch too

A conversation summary is a frozen snapshot of what was true when it was written, and two
things drift under it:

- **The clock.** Sessions here run for days. 2026-09-27: a resumed summary carried the
  date 2026-09-17 and I answered as though ten days had not passed.
- **The files.** Parallel and later sessions edit the same skills and memories. The same
  resume: the summary said `--deliver` was "not yet live-run" and a jump-host
  `TargetNotConnected` looked unexplained, while `focus-node-db-access/SKILL.md` on disk
  already recorded the failed first live run of 2026-09-18 and the jump host's daily
  agent restart / Sunday reboot schedule.

**On resume, before repeating any conclusion the summary hands you:** check today's date,
and re-open the skill or memory the claim came from. One read, not a re-derivation.

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
