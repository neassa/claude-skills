---
name: relay-output-faithfully
description: >-
  Use whenever reporting what a command, script, test run, status check or CI job
  produced. Prevents adding specifics the output does not contain and prevents drawing a
  verdict from output you did not read. Use when the user says "that's not what it said",
  "did you read it", "where does it say that", or corrects a summary you gave.
---

# Relay output faithfully

## When this applies

Every time you report a result you did not compute yourself: a script's summary line, a
test count, a status check, a deploy log, a linter's verdict.

## What to do

**Read the output before characterising it.** Including output from a script you wrote.
Knowing what a script is supposed to measure is not knowing what it printed.

**State only what it prints.** A count is a count. Adding what the count includes
("including today's changes"), or what it implies ("so we're clean"), is a separate
claim that needs its own evidence.

**Verify before adding any specific.** If you want to say a number includes a particular
item, run the command that shows that item. Phrases like "all good", "nothing needs
attention" and "including X" are the ones that go wrong.

**Know what the fields mean.** A status line's label is often narrower than it sounds.
If you are unsure what a field counts, say the raw value and say you are unsure, or read
the script.

**Do not truncate output that can carry a failure.** Tailing to the last line hides
rejections, warnings and errors that appear above it. Grep the whole output for failure
markers instead, and report loudly when one appears.

**Guard against vacuous success.** A comparison of two empty captures passes while
proving nothing. Before comparing, assert both values are non-empty and print them. When
a result is unexpectedly empty, show the raw tail rather than trusting the verdict.

**When a run fails, say so with the output.** Do not summarise a failure as a partial
success, and do not report a step as done when it was skipped.

## Founding failure

An agent read a status script's line reporting five lessons committed in the last seven
days and told the user this included that day's work and that nothing needed attention.
Both were false. The five commits were infrastructure, that day's work had never been
committed as a lesson, and two files were sitting uncommitted.

Separately, a push command's output was piped to show only its final line. That line was
a hint about fast-forwards, which meant the push had been rejected. The agent read past
it and went on to update a description for a commit that was never pushed.

Separately again, a comparison script compared two captured values that were both empty
because the run had failed early. The equality check passed and reported the two sides
identical.
