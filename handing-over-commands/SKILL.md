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

**Do not edit a script you handed over while the user may be running it.** Bash reads a script by byte offset as it runs, so rewriting it in place (`cat > file`, `sed -i`) makes the running copy execute garbage. 2026-10-09: a UAT seed `--update` died mid-poll with `syntax error near unexpected token ')'` after its remote command had already been sent, so the result had to be recovered by hand. Write to a temp file and `mv` it over (the running bash keeps the old inode), or ask first.

**Offer to interpret.** The useful division of labour is that they run it and you read
the result. Say what output to paste back and what you will do with it.

## Part two: how to format the block

**Every block must work pasted alone into a fresh terminal.** Assume no variable, no
export, and no tunnel survives from an earlier block or session.

- Define variables at the top of the same block that uses them
- **`VAR=x && cmd` does not pass `VAR` to `cmd`.** It sets an unexported shell variable. Write `export VAR=x && cmd`, or the prefix form `VAR=x cmd`. When the user retypes a block and drops the `export`, point at that first: the symptom looks like a permissions error (e.g. terraform `S3 HeadObject 403` because it fell back to default creds).
- Prefer literal paths over variables when the block is short
- One fenced block per action, not one per recipe
- Prefer idempotent forms: `nc -z localhost 5433 || ssh -f -N -L ...`
- After any command that can half-fail, include the one-line check that proves it worked
- Fill in real values discovered from context. Never leave a placeholder that looks like
  a real value
- **A `<placeholder>` is a broken command, not a template.** `<cluster>` and
  `<paste-arn-here>` are shell metacharacters: pasted as-is they die with
  `bash: syntax error near unexpected token` or `bash: cluster: No such file or
  directory`, and the user has to stop and ask what to substitute. When you do not yet
  know the value, write a block that DISCOVERS it — assign it from the query in the same
  block, and guard the action on getting exactly one result:
  ```bash
  CLUSTER=focus-poc-node-nonprod-focus
  SERVICES=$(aws ecs list-services --cluster "$CLUSTER" --query 'serviceArns[]' --output text)
  [ "$(echo "$SERVICES" | wc -w)" -eq 1 ] && aws ecs update-service --service "$SERVICES" ... \
    || echo "got $(echo "$SERVICES" | wc -w) services - paste the list back"
  ```
  A discovery round-trip that returns a real value is the other acceptable option. A
  placeholder is never one.

**Keep each line short; no 300-character `&&` chains.** A long one-liner can come back from the paste broken into
several lines: 2026-10-11 a `dates-poc-check.py sql && cd … && ./focus-node-db-iam.sh -f <path> > … && cd <path> && …`
chain broke after `-f` and after `cd`, giving `psql: option requires an argument -- 'f'`, then
`<file>: Permission denied` and `<dir>: Is a directory` as the shell ran the paths as commands. The script's PAM hint
printed after it was a red herring. Put each command on its own line, with paths in short variables set at the top
of the same block.

**A single long command breaks too, not only `&&` chains (2026-10-20).** A 150-character
`TD=$(aws ecs describe-services ... --query 'services[0].taskDefinition' --output text)` line came back wrapped after
`--query`, so the next line ran as a command (`services[0].taskDefinition: command not found`) and the variable ended up
empty. Keep every line under about 100 characters; put long `--query` strings and ARNs in short variables set earlier in
the same block (`Q='...'`, `TG=arn:...`). The retry with short lines worked first time.

**Never let prose share a line with a command.** Explanation goes outside the fence, or on
its own `#` line inside it. A sentence appended to a command line is not read as a note —
it becomes arguments. The signature of this having happened is a set of files named after
the consecutive words of your sentence: found 2026-09-27 in
`aida-emdash-poc/custom/infra/terraform/envs/nonprod/10-foundation/` — twelve identical
32,830-byte copies of a terraform plan's output, named `2.`, `CF`, `token`, `is`, `no`,
`needed:`, `drop`, `them`, `from`, `state`, `so`, `terraform`, left by a `tee` that
swallowed the step's own description on 2026-09-01. Harmless there; the same shape against
`rm`, `git add` or `terraform state rm` is not.

**When someone else will run it, no fixed values from your session.** 2026-10-13 a UAT reload went out with 13 slugs
pasted inline (`S=curated-collection-100513,...`) because the list file lived only in my local folder; Laith: "not like
this, too much fixed values". The other person has different paths, a different profile name and none of my scratch
files. So:
- Select with the tool's own options (`--types ko,web`), or a list file that is committed in the repo, never a list
  copied out of a local file.
- Before building a new option to avoid a list, ask what the run is FOR: "gated" was already the default, and the real
  plan (fix one content type, add another) needed only `--types`.
- Name every variable in a table: what it is, the flag it feeds, where they get it (P = their SSO profile and what it
  must be allowed to do, R = their built checkout at the env's build, Z = data not in the repo, and who gives it).
- List what is NOT in the repo (an export folder, a credential, a tool version) as prerequisites, with who provides it.

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

2026-09-24, the placeholder version of the same mistake: an ECS recycle was handed over as
three blocks, two of them containing literal `<paste-cluster-arn-or-name>` and `<cluster>`.
Both failed on paste with bash syntax errors before reaching AWS. The first block, which
contained only real values, had already returned the three cluster names — so the correct
value was on screen and could have been substituted.
