---
name: session-handoff
description: >-
  Use when work will continue in a different session, when a task reaches a milestone,
  or when the user asks for a summary to resume from later. Also whenever a long session
  finishes a distinct piece of work. Produces a document a cold successor can act on. Use
  when the user says "summarize this for a new session", "create a handoff", or "add the
  filename".
---

# Session handoff

## When this applies

Any work that outlives one sitting. In practice that is most non-trivial work: sessions
routinely span days, and the successor has none of the context you are holding right now.

Write the handoff at each milestone, not only when stopping. A session that ends
unexpectedly still leaves something usable.

## What to do

**Separate the threads.** If the session covered unrelated pieces of work, keep them
apart. Blending them into one narrative makes both unusable.

**Be explicit about verification status.** Three categories, never blurred:
- done and verified, with what proved it
- done but unverified
- not started

The most damaging handoff is one that implies verification that never happened.

**Include the commands that actually worked**, with real values filled in, formatted so
each block survives being pasted alone. See `handing-over-commands`.

**Say what went wrong and why, not just what you did.** If an ordering mattered, state it
as a rule. If a precondition existed, name it. The failure analysis is the part the
successor cannot reconstruct.

**List the traps.** Wrong branch, wrong checkout, wrong environment, stale state, a
tracker keyed on something surprising, a script whose two copies drift. Anything that
cost you time will cost the successor time.

**Name the branch and checkout for every repository mentioned.** In a multi-worktree
setup a branch name alone does not locate anything.

**Make open items actionable.** Enough detail to start without asking a question.

**Update the index.** A handoff nobody can find is not a handoff. Point to it from
whatever persistent notes or status file the project already has, and tell the user the
full path.

**Do not create a new status file when one exists.** Update it.

## Anti-patterns

- Optimistic summaries. If it was not verified, say so.
- Narrating your process rather than the state.
- "See the conversation above." The successor cannot.
- Describing a file's location relatively. Give the full path.

## Founding failure

A project where sessions regularly ran five to twenty-one calendar days across roughly
twenty sibling checkouts. The user asked, repeatedly and in nearly identical words, for a
summary usable to follow up in a new session, and to be told the filename.

The recurring damage was not lost work but re-derived work: a successor session rediscovering
which branch held the relevant checkout, which of two similar environments was the target,
and which steps had actually been verified rather than merely run.
