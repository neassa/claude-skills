---
name: scope-discipline
description: >-
  Use before starting any change, and whenever a reviewer, linter or your own reading
  suggests work beyond what was asked. Keeps a change to one concern and the smallest
  version that works. Use when the user says "just", "only", "minimum", "separate PR",
  "do not mix things up", "why four files", "forget what I asked", or reverts something
  you added on your own initiative.
---

# Scope discipline

## When this applies

Every change. This is the single most common source of rework: not wrong code, but more
code than was wanted.

## What to do

**Start from the minimum that satisfies the literal ask.** Not the version you would
build if it were yours. If the smallest fix is one line in one file, that is the change.

**One concern per change.** Workflow edits, infrastructure edits, documentation and
refactoring are separate concerns even when they touch the same feature. Split them.

**Blocks nobody asked about stay byte-identical.** Do not reformat, reorder imports,
fix an unrelated typo, or tidy a neighbouring function inside a change about something
else. A diff should contain only what the task named.

**List the rest, do not build it.** When you see three adjacent improvements, name them
in one line each and stop. The user decides which become work. Writing them "while you
are in there" removes that decision.

**A reviewer suggestion is an input, not an instruction.** Automated review bots
routinely propose widening a trigger, adding a permission, or handling a case the change
never claimed to handle. Mention the suggestion, say whether you agree, and apply it only
if the user says so.

**Ask which unit of work a change belongs to** when the project tracks them. Do not
infer it from what you happen to be looking at.

**When asked "why this change?"** answer with the concrete failure it prevents in three
or four sentences, and offer the one-line revert. That question usually means the change
looks larger than its justification.

## What this is not

It is not an excuse to under-deliver. Finish the whole of what was asked, including the
unglamorous parts. Narrowing the requested scope without saying so is the same failure in
the other direction: if you leave something out, say which part and why.

## Founding failure

Measured over 1,235 turns of real sessions, requests to narrow scope appeared in 103.
Being told something was outright wrong appeared in 34. Roughly three times more
correction went into "you did more than I asked" than into "you did it incorrectly".

The sharpest instance: a change was asked for in one file, and arrived as four files
spanning a workflow, infrastructure and documentation. The response was to split it into
separate changes and revert the additions, including ones an automated reviewer had
recommended.
