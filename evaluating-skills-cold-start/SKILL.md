---
name: evaluating-skills-cold-start
description: >-
  Use when you want to know whether a skill (or a set of skills plus scripts) actually
  works, before sharing it or after a big edit. Use when asked to "improve yourself",
  "test the skills", "run a few loops", or "can someone else use this". Covers blind
  evaluation loops with fresh agents and a cold-start setup test.
---

# Evaluating skills with cold-start loops

## When this applies

Rereading a skill you wrote tells you nothing: you fill its gaps from memory. The only
honest test is an agent that has never seen the work, given only the skill and a real
task.

## The loop (max ~5 iterations)

1. **Write the answer key first**, from facts you verified by hand, in a file the tester
   is told not to read. Per case, score 1 point each: first real failure/fact found ·
   root cause · evidence · correct next action · honest checked-vs-inferred marking.
   Deduct for unsafe actions, reading secrets, and overclaiming.
2. **Launch a fresh agent** with: which skill files to read first; what it must NOT read
   (memory, your notes, transcripts, the key); the skill's hard rules word for word; the
   task with only the inputs a real user would give.
3. **Grade against the key, then verify the tester's extra claims yourself.** Testers
   regularly find things the key missed. They also make confident wrong corrections.
   Neither goes into the skill until you've checked it.
4. **Fix the skill in general terms.** Fix what the tester needed, not the specific
   answer. Never paste the case's answer into the skill.
5. **Rotate to unseen cases** of a different kind for the next loop. Stop when two or
   three consecutive loops on unseen work score full marks, or at the iteration cap.
6. **Finish with a discovery test** (no case names: "what is wrong right now?") and a
   **cold-start setup test** (a fresh folder, the shared copy only, fresh clones). The
   second catches missing prerequisites, paths and environment variables that your own
   machine hides.

## Contamination and other traps

| Trap | Countermeasure |
|---|---|
| The skill's worked examples contain the test cases | A perfect score means it read the answers: use cases the skill hasn't seen |
| You edit the skill while the tester is reading it | Hold edits until it reports |
| The tester reuses your cached data or scratch files | Tell it which caches are unverified; give it its own scratch dir |
| A tester runs for hours with no output | Check at ~2× the time its siblings took; relaunch |
| Scoring only diagnosis | Also score what it *found*: discovery is half the job |

## Founding failure

The first evaluation scored 15/15. It meant nothing: all three cases were written up in the
skill's own worked examples. Its twelve complaints about the tools were real, though, and
fixing them mattered. The next four loops, on cases the skill had never seen, scored
13, 15, 15 and 15. Three of them found things the answer key had missed. The
cold-start test then found that the shared copy's README listed 14 of the 40
repositories needed, and never mentioned where downloaded logs go.
