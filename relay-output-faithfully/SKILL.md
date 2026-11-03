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

## Never put two ratios side by side without their denominators

Settled 2026-09-23, FOCUS sponsor logos. An upload of 193 files succeeded; a verification script printed
`objects=193 ... sponsor logos present=86/90` per bucket. Laith read the second number as a failed upload and
asked twice why only some files went, the second time angrily. Both numbers were true and they counted different
things: files in the archive, and logo keys the seed asks for. Four of those keys had no file in the archive at all.

- **Name what each number counts, in the same line.** "193 of 193 files uploaded" and "86 of the 90 logo keys the
  seed needs are now present; the other 4 are not in the archive" — never a bare `86/90` next to a bare `193`.
- **Lead with the question the person actually has.** They want to know whether their command worked. Answer that
  first, then any secondary count.
- **A verification script is output the user reads.** Word its lines as carefully as a chat reply; a terse label
  that makes sense to you while writing it will be read cold, hours later, as a verdict.

## A count is only as wide as the query that produced it

2026-09-25: asked how widespread a duplicated tag was, I ran a query scoped to one taxonomy, got 3 entries, and
reported "3 items, cosmetic". The unscoped count was 264, and the cause was different too. Nobody could have caught
that from my sentence, because the scope was in the SQL and not in the claim.

- **Say what the number counted** when the query narrowed anything: "3 entries where the duplicate is within the
  subject taxonomy" is honest, "3 entries" is not.
- **Before calling something rare or cosmetic, widen the query once.** The cheap version of that sentence is one more
  `GROUP BY` without the filter.
- **Re-read your own artifact before shipping it.** Reading the generated workbook back found two fields marked
  "filled by the import" that are written empty — a classifier bug invisible while writing the code.

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
