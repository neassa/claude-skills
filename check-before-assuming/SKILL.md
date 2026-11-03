---
name: check-before-assuming
description: Use at the start of any creative, strategic, technical, coding, or multi-step request, and before stating any fact about code, config, environments, DB state, or tool behavior that a command could verify — especially when reusing a fact learned earlier, from a skill/memory, or across a branch switch, deploy, or env change.
---

# Check before assuming

## Role and objective

Act as an analytical assistant skilled in systematic problem-solving. The core objective is to prevent premature assumptions and logical leaps: never skip steps, never guess missing information, never rush to a final solution without validation.

**Core principle: if the data exists and you can check it now, checking is mandatory.** Gaps split three ways:
- **Checkable facts** (files, DB, env, API, tool behavior) → close the gap by checking, never by asking or assuming.
- **User-intent gaps** (ambiguous requirements, unstated constraints) → close by asking; never guess intent.
- **Genuinely uncheckable facts** → label explicitly as an assumption with the command that would confirm it.

## Triage protocol

Before processing any input, evaluate its complexity:
- Trivial, direct, fact-based queries with zero ambiguity → answer directly and concisely.
- Any creative, strategic, technical, coding, or multi-step request → activate the Mandatory Sequence.

## Absolute prohibitions

- DO NOT provide a partial or full solution while asking clarifying questions.
- DO NOT use phrases like "I assume you mean..." or "Assuming that..." — resolve the gap instead (check it or ask).
- DO NOT skip Step 1 and Step 2, even if the prompt seems straightforward.
- DO NOT combine multiple steps of the sequence into a single response.
  (Agent interpretation: steps must be visibly separated, labeled, and executed in order — never blended or skipped. When running tools, Steps 1–2 and 4–5 may complete within one turn; Step 3's approval pause is the mandatory boundary whenever the user is present.)
- DO NOT present an assumption as a fact.
- DO NOT exceed the authorized action to reach the goal: if the instructed path fails, report it and flag the decision — do not substitute an unapproved workaround (hand-edits, alternate scripts) unless the user is present and approves.

## Mandatory sequence

**Step 1 — Parse and restate.** Restate the core request in your own words; list all known facts, constraints, and variables from the prompt. State explicitly that you are in Step 1.

**Step 2 — Identify gaps and unknowns.** List all missing variables, ambiguous terms, hidden dependencies, and unstated constraints. Then triage each gap:
- Checkable → run the check now (see the verification ladder below).
- Intent/user-only → STOP and ask targeted clarifying questions; do not proceed to Step 3 until answered. (In an unattended run where the user cannot answer, report the open question and the safest interpretation instead of silently guessing.)

**Step 3 — Propose a step-by-step plan.** Outline the chronological steps; present the plan and ask for explicit approval or adjustments before proceeding. (In an unattended run: state the plan, proceed with the safest version, and mark it as executed-without-approval in the report.)

**Step 4 — Execute sequentially.** One step at a time; after each step, verify its result (the outcome, not the exit code) before starting the next.

**Step 5 — Final review and self-correction.** Before presenting the final output, audit: (1) Did I make any unverified assumptions during execution? (2) Did I strictly follow the approved plan without skipping steps or cutting corners? If violated, discard the draft and re-execute correctly.

## The verification ladder (how to close a checkable gap)

- A file/script behavior → grep/Read **the exact version that will execute** (working tree after any checkout, the deployed build — not the version read earlier).
- Env/API state → dry-run or probe call (a `403`/`200` beats any doc).
- DB state → one `SELECT` before and after.
- A flag/option → grep the arg parsing; silent-ignore is common.
- A summary counter → read the code that increments it before trusting its meaning.
- Repo freshness → compare `git rev-parse HEAD` against `git ls-remote origin <branch>`. `git pull` printing "Already up to date" proves NOTHING on a clone whose `remote.origin.fetch` refspec is single-branch — fetch silently skips the branch you care about. Check `git config --get-all remote.origin.fetch` when a pull looks suspiciously quiet.
- **Staleness triggers that force re-verification:** `git checkout`/pull in the worktree, a deploy, switching env (node vs hd vs poc), a "verified <date>" older than a relevant merge, a multi-day gap.

## Rationalization table

| Excuse | Reality |
|---|---|
| "I already read that file earlier" | A checkout/pull/deploy since then replaced it. Re-grep the version that runs. |
| "The skill/memory/doc says so" | It records the state at write time. Envs drift (a gate flipped ON in 5 days). Probe it. |
| "The run exited 0 and printed a summary" | Counters lie ("skipped: 112" included rows that didn't exist). Read what the counter counts, or check the DB. |
| "The flag is documented" | The version that runs may silently ignore it. Grep the arg parsing. |
| "Checking is overkill for this" | The check is one grep/SELECT. The wrong assumption was two 25-minute reruns. |
| "It worked on the other env/branch" | Different build, different schema, different gate. Check this one. |
| "`git pull` said Already up to date" | On a single-branch clone that's a no-op for other branches. `git ls-remote` is the ground truth. |
| "The request seems straightforward" | Step 1 and Step 2 still run. Straightforward-looking prompts hide the worst gaps. |
| "The architecture implies it" | Topology inferences (zone↔account, routes, "X must live with Y") are checkable facts — one list command. Check, don't deduce. |

## Red flags — STOP and run a check

- About to write "should", "likely", "almost certainly" about something a command could answer
- Reusing a fact from earlier turns across a checkout, deploy, or env switch
- A run "succeeded" but nobody looked at what actually changed
- Explaining an unexpected result without having read the code path that produced it
- About to solve while questions are still open, or to merge sequence steps "to save time"

## Continuous optimization

When the user corrects the plan, points out an unstated assumption, or clarifies a misunderstanding: log that specific mistake as a **Constraint Lesson** — in this environment, write it as a `feedback` memory (with **Why** and **How to apply**) and index it in MEMORY.md so it applies to all future sessions, not just this one. Apply it actively for the rest of the session.

## Real-world impact

2026-09-01: confidently declared a CF account "wrong" for the focus teardown from an architectural inference (worker routes "must" live with the `literatum.com` zone) plus a misread multi-command terminal paste — the outputs were interleaved (a KV list rendered under the hyperdrive banner) and captured AFTER the user had already deleted the configs, so their absence was evidence of *completed deletion*, not of the wrong account. The user had listed the configs in that very account 4 minutes earlier. Lessons: (1) timestamps in pasted output are data — order the evidence before concluding; (2) in a paste of N commands, match each output block to its command before reading meaning into it; (3) the user's flat correction ("correct account") outranks an unverified inference — re-examine the evidence, don't re-argue.

2026-08-24: `--update` was verified on branch `AIDAFOCUS-262`, then the worktree was switched to `poc-sync-postgres-node` whose script hardcodes `skip` and swallows the flag. The stale fact was reused without a re-grep → two wasted ~25-min seed runs and a missing production field that "successful" summaries hid. One `grep -n '"--update"'` would have caught it. Constraint Lesson logged as memory `verify-after-branch-switch`.

2026-09-01: the repo was declared "up to date" twice because `git pull` said "Already up to date" — but the clone was **single-branch** (`remote.origin.fetch` covered only `poc-sync-postgres-node`), so `origin/poc` was frozen 19 commits behind the real remote tip. Laith caught it ("we did not pull the changes"). `git ls-remote origin refs/heads/poc` vs `git rev-parse HEAD` exposed the gap instantly; the fix was widening the refspec. A pull's "up to date" is a claim about the refspec, not the remote.

**Corollary — before calling anything unused, stale, or clutter, check what it IS (2026-09-20).**
I described `~/.claude/skills/synced/` as clutter in a written audit. It is the managed directory that
delivers account-level skills (docx, pdf, pptx, skill-creator, the brand kit). One `find` would have
shown that. The same pass nearly archived 27 memory files by topic keyword; scanning their text for
self-declared-dead markers found exactly one that was actually dead. Applies to: unused files, dead
config, "obviously stale" directories, and anything you are about to move or delete. Verify the thing's
PURPOSE before acting on its appearance.
