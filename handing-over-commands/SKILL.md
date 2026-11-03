---
name: handing-over-commands
description: >-
  Use when a task needs privileged, credentialed, state-changing or production commands,
  and whenever the user asks for "the command", "the steps", or pastes terminal output
  back to you. Covers both when to hand over rather than execute, and how to format a
  block so it survives being pasted alone into a fresh terminal.
---

# Handing over commands

## Part one: when to hand over rather than run

Some people drive their own infrastructure. They have the credentials, the audit trail,
and the responsibility. For them the deliverable is a correct command, not a completed
action.

**Signals that this is the mode you are in:**
- the user pastes terminal output back to you rather than asking you to run things
- they ask for "the command" or "the steps" rather than an outcome
- they interrupt a tool call with "I just need the command"
- the target is production, shared, or billed

**Default to handing over for:** infrastructure provisioning and teardown, deploys,
database writes, anything using the user's stored credentials or tokens, and anything
whose blast radius you cannot fully enumerate.

**Ask once, then honour the answer for the session.** Whether read-only inspection
counts is a real question with different answers for different people. Some are fine
with read-only calls; others want those handed over too, because the credential is
theirs. Ask, record the answer, and do not re-litigate it.

**What stays fine to run yourself:** reading files in the repository, local search,
inspecting git history, and anything using only your own tools against non-privileged
targets.

**Offer to interpret.** The useful division of labour is that they run it and you read
the result. Say what output to paste back and what you will do with it.

## Part two: how to format the block

**Every block must work pasted alone into a fresh terminal.** Assume no variable, no
export, and no tunnel survives from an earlier block or session.

- Define variables at the top of the same block that uses them
- Prefer literal paths over variables when the block is short
- One fenced block per action, not one per recipe
- Prefer idempotent forms: `nc -z localhost 5433 || ssh -f -N -L ...`
- After any command that can half-fail, include the one-line check that proves it worked
- Fill in real values discovered from context. Never leave a placeholder that looks like
  a real value

**Say what to expect.** One line on the expected output makes a wrong result obvious
immediately rather than three steps later.

**Diagnose empty-variable symptoms first.** When pasted output shows a path missing its
prefix, or a command that ran against the wrong target, suspect an unset variable from a
split block before suspecting the remote system.

## Founding failure

An agent was asked to prepare a plan for an infrastructure change. It copied the files
and ran the initialisation and planning steps itself. The user interrupted: "why are you
running the init? I just need the copy command and the plan command."

Separately, on the same day, two format failures. A two-block recipe set a variable in
the first block; the second was pasted alone, the variable was empty, and the resulting
rooted path failed with a missing-module error that looked like a dependency problem. And
a tunnel command documented as "run once per session" was re-pasted while the old tunnel
was still alive, producing bind errors that looked like failures.
