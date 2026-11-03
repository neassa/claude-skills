---
name: capture-lessons
description: >-
  Use immediately whenever the user corrects you (any correction, even trivial), when a
  fact took more than two attempts to establish, when you build a reusable script or
  workflow, or when a skill or note turns out to be stale or wrong. Use again at every
  task wrap-up as a confirmation pass. Use when the user says "remember this", "how do we
  avoid this next time", "update your skills", or asks what went wrong.
---

# Capture lessons, twice

The conversation dies; files survive. Capture at **two** points: immediately when the
lesson happens, and again at wrap-up as confirmation.

Long sessions get compacted and may never end cleanly, so a lesson deferred to "the end"
is a lesson lost.

**If the user has to ask "did you update your skills?", this skill already failed.**

## Pass 1 — capture at the moment

The instant a correction lands, a fix contradicts your assumption, a fact takes more than
two attempts, or a loaded skill proves stale: route it, write it now, then continue the
task. Do not finish the task first.

A trivial correction is still a one-line edit. Trivial to save, expensive to relearn.

| Lesson | Where it goes |
|---|---|
| Reusable technique, gotcha or workflow | A new skill |
| New quirk in an area an existing skill covers | Edit that skill. Search descriptions first; updating beats duplicating |
| Project state, decisions, constraints | Persistent project notes, plus an index line so it is findable |
| A preference about how you should work | Persistent notes, with **why** and **how to apply** |
| Re-derivable by one command you just ran | Save the command, not the fact |
| One-off trivia, secrets, credentials | Nothing |

## Pass 2 — confirm at wrap-up

At every task wrap-up, not only at session end, over **the captures written since the
last wrap-up**. That set is small and is the only one likely to have drifted.

1. Re-scan the window: every correction, mistake and fix, hard-won fact, reusable
   artifact. Confirm each has a capture on disk by opening it. Capture anything missed.
2. Re-verify those captures are still true. Paths, commands and decisions may have moved
   since pass 1. Fix stale text. Delete anything the task later disproved.
3. Commit with scoped paths, never a blanket add. A blanket add sweeps in half-written
   files from concurrent work and stray scratch files.
4. Tell the user what was saved, one line each.

## Write the failure, not just the rule

A rule without its founding incident is advice, and advice gets applied inconsistently.
Every capture includes:

- what you did or claimed
- what was actually true
- why the mistake was reachable, in one sentence
- the cheapest check that would have caught it

Be specific about time and place. Convert "recently" to a date. Name the file, branch,
flag or command rather than describing it.

## Every skill evolves, including this one

- **On every load of any skill**: if reality differs from what it says, fix it in the
  same session. A stale skill is worse than no skill, because it is trusted.
- **On every use of this skill**: a lesson that does not fit the routing table extends
  the table.
- A skill untouched for months is not stable, it is unverified. Re-verify its facts
  before relying on them. `scripts/skills-health.py` names the stale ones.
- **Check for contradictions.** Two notes that disagree are worse than either alone.
  When you find a pair, say so and ask which holds. Do not silently pick one.

## Rationalizations — every one of these means stop and capture now

| Excuse | Reality |
|---|---|
| "Too trivial to save" | Pass 1 explicitly includes trivial corrections. One line, now. |
| "I'll batch it at wrap-up" | Long sessions compact. Wrap-up is the confirm pass, not the capture pass. |
| "The user didn't ask me to save anything" | Capturing is the job, not a feature request. |
| "The conversation is the record" | Context compacts and sessions end. Files survive. |
| "It's derivable from the repo" | It took you several attempts. Derivable is not discoverable. Save the search path. |
| "The existing skill roughly covers this" | "Roughly" means stale. Update it to exactly. |
| "It's obvious in hindsight" | It cost real time once. It will again. |
| "The session is ending, just wrap up" | Wrap-up requires pass 2, which means opening the captures. |

## Red flags

- A correction acknowledged in chat with no file written in the next few tool calls
- A wrap-up summary delivered without opening the captures to confirm them
- Loading a skill, noticing it is outdated, and not editing it
- A blanket `git add -A` in a wrap-up commit
- Saying "worth remembering" or "for next time" in chat only

## Health check

```bash
python3 scripts/skills-health.py ~/.cursor/skills    # or your skills directory
```

Reports skills untouched for a long time, frontmatter that fails to parse, and
descriptions too vague to trigger reliably.

## Related

Writing a genuinely good new skill is its own discipline. If you have the Superpowers
library installed, use its `writing-skills` skill for that, and its
`verification-before-completion` skill before declaring a capture done. See
`scripts/add-superpowers.sh` in this repo.

## Founding failure

A user working in multi-day sessions stated plainly that context compacts over long runs,
and that anything deferred to session end can be lost because session end may never
arrive. The baseline incident: three days of lessons from one task were captured only
after the user explicitly asked whether the skills had been updated.

Separately, a note recorded on one day said read-only inspection commands were fine to
run. Another note recorded weeks later said the opposite, citing a specific rejected
command. Both were true when written. Neither was updated when the other was added, and
they lived in different directories, so which one applied depended on where the session
happened to start.
