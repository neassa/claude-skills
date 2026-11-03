---
name: self-learning
description: Use immediately whenever the user corrects you (any correction, even trivial), when a fact took several attempts to discover, when you built a reusable script/workflow, when a loaded skill or memory turns out stale or wrong, when the user says "remember this", "how do we avoid this", or asks for a summary of mistakes — and again at every task wrap-up as a confirmation pass. Sessions here run long and multi-day; do not wait for the end.
---

# Self-learning: capture every lesson, twice

The conversation dies; files survive. Lessons are captured at TWO points: **immediately** when they happen, and **re-confirmed** at wrap-up. Sessions here run for days — a lesson deferred to wrap-up is a lesson lost to compaction.

**The user asking "update your skills?" means this skill already failed.** Baseline (2026-09-03): three days of AIDAFOCUS-362 lessons were captured only after the user explicitly asked.

Mechanical backstops (hooks in `~/.claude/settings.json`, scripts in this directory): `session-status.py` prints stale-skill names, weekly capture count, and a memory-versioning drift alarm at every session start; `prompt-hook.sh` nudges pass 1 when a prompt looks like a correction. The hooks remind — the capture is still on you.

## Pass 1 — capture at the moment (EVERY correction, even trivial)

The instant a correction lands, a fix contradicts your assumption, a fact takes >2 attempts, or a loaded skill/memory proves stale: route it and write it NOW, then continue the task. A trivial correction ("use commas not semicolons", "name files like X") is still a one-line memory or skill edit — trivial to save, expensive to relearn.

| Lesson | Destination |
|---|---|
| Reusable technique, gotcha, or workflow | New skill in `~/.claude/skills/` — follow superpowers:writing-skills; verify routing with a few cold subagent scenarios at creation |
| New quirk/fix in an area an existing skill covers | Update that skill (grep skill descriptions first — update beats duplicate) |
| Project state, decisions, constraints | Memory file + MEMORY.md index line |
| User preference or correction on how you work | Memory, type `feedback`/`user`, with **Why** and **How to apply** |
| Re-derivable with ONE command you just ran | Capture the COMMAND (in the relevant skill/memory), not the fact |
| One-off trivia, secrets, credentials | Nothing |

## Pass 2 — double-confirm at wrap-up

At every task wrap-up (not only session end), over **the captures written since the last wrap-up** (not the whole session — that set is small and the only one likely to have drifted):

1. Re-scan this task window: every correction, mistake+fix, hard-won fact, reusable artifact — confirm each has a capture ON DISK (open it); capture anything missed now.
2. Re-verify those captures are still true: paths, commands, decisions may have changed since pass 1. Fix stale text; delete captures the task later disproved.
3. Commit with scoped paths — never `git add -A`:
   `cd ~/.claude && git add skills/<name> projects/<slug>/memory && git commit -m "<what was learned>"`
   (Scoping keeps concurrent sessions' half-written files and stray scratch files out of the commit.)
   If the commit touched `skills/`, also push the skills — ONLY the skills, memories never leave this machine — to the private backup repo:
   `git push skills $(git subtree split --prefix=skills):main`
   (remote `skills` = https://github.com/ljanaideh/claude-skills, private, set up 2026-09-09; the subtree split is deterministic and incremental, so the push fast-forwards.)
4. Tell the user what was saved/updated, one line each.

## Every skill evolves — including this one

- **On every load**: if reality differs from the skill (moved path, renamed flag, better method, wrong fact), update the skill in the same session.
- **On every use of THIS skill**: a lesson that doesn't fit the routing table, or an excuse not countered below, extends the table — that's this skill learning.
- Structural check (frontmatter, duplicate names, vague descriptions, staleness):
  `python3 ~/Downloads/projects/agent-start-kit/skills/capture-lessons/scripts/skills-health.py ~/.claude/skills`
  — it skips nested collections like `synced/`. The 5 flagged aws-* descriptions are vendored, not ours.
- A skill untouched for months isn't stable, it's unverified — `session-status.py` names >90-day personal skills at session start; re-verify their facts before relying on them.

## Maintaining the captures (not just writing them)

- **Never archive or delete by topic keyword.** Verified 2026-09-20: a plan to archive "the 27 D1-era memories" did not survive inspection — scanning for SELF-DECLARED dead markers (`dead code`, `DESTROYED`, `retired`, `superseded`, `no longer exists`, `never worked`) found exactly ONE genuinely dead file. The rest used those words to describe something *inside* a still-current memory. Nothing was archived. Scan the text, don't infer from the title.
- **Completeness beats smallness.** The same pass found 20 entries stranded in satellite cwd-keyed dirs — the behavioural ones (`never-run-terraform`, `give-commands-dont-execute`, `laith-writing-style`) — invisible from the main dir. Consolidating grew the always-loaded index 64 → 85 lines. That is the right trade. See [[memory-dirs-are-cwd-keyed]].
- **Two notes that disagree are worse than either alone.** When you find a contradicting pair, flag BOTH files with a `**CONFLICT FLAGGED <date>**` block naming the other and the conservative default, then ask. Do not silently pick one. Live example: [[never-run-terraform]] vs [[aws-commands-not-execute]] on read-only AWS calls.
- **Before calling anything clutter, check what it is.** `~/.claude/skills/synced/` looked like junk and is in fact the managed directory delivering account-level skills. See [[check-before-assuming]].

## Rationalizations — all mean STOP and capture now

| Excuse | Reality |
|---|---|
| "Too trivial to save" | Pass 1 explicitly includes trivial corrections. One line, now. |
| "I'll batch it at wrap-up" | Long sessions compact; wrap-up is the CONFIRM pass, not the capture pass. |
| "The user didn't ask me to save anything" | Capturing is your job, not a request feature. |
| "The conversation/summary is the record" | Context compacts and sessions end. Files survive. |
| "It's derivable from the repo" | It took you N attempts — derivable ≠ discoverable. Capture the search path (the command), not nothing. |
| "The skill already covers roughly this" | "Roughly" = stale. Update it to exactly. |
| "It's obvious in hindsight" | It cost real time once. It will again. |
| "Session is ending, just wrap up" | Wrap-up REQUIRES pass 2 — confirming captures on disk. |
| "I'll generalize it later for sharing" | Generalizing drops the enforcement tables unless you do it deliberately — see `generalizing-skills-for-sharing`. |

## Red flags

- A correction acknowledged in chat ("got it, will do") with no file written in the next few tool calls
- The prompt-hook nudge fired and the turn ends with nothing new on disk
- A wrap-up summary delivered without opening the captures to confirm them
- Loading a skill, noticing it's outdated, and not editing it
- `git add -A` in a wrap-up commit
- Saying "worth remembering" / "for next time" in chat only
