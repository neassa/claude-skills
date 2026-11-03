---
name: check-before-assuming
description: >-
  Use before stating any fact about code, configuration, environment state, database
  contents, a file's existence, or a tool's behaviour that a command could verify.
  Also at the start of any multi-step or technical task. Use when the user asks "did you
  check", "are you sure", "why did you assume", or corrects a confident claim you made.
---

# Check before assuming

## When this applies

Before any assertion of fact. Especially one you are reusing from earlier in the
session, from a skill, from a memory, or from training.

The rule is not "verify everything". It is: **if a command could settle it and you did
not run one, do not state it as fact.**

## What to do

**Rank your evidence.** In descending order:

1. Output of a read-only command you just ran, in the working tree that will actually run
2. The file itself, read now
3. Official documentation for the exact version in use
4. A note you wrote earlier this session
5. A skill or memory written on another day
6. Recollection

Levels 4 through 6 are hypotheses. Say so, or promote them by checking.

**Verify the specific thing, not the neighbourhood.** "The script supports this flag"
needs a grep for that flag in that file, not a reading of the script's purpose.

**Check the version that will run.** A flag documented upstream, present on another
branch, or installed globally is not necessarily the one your command will invoke.

**Silence is not confirmation.** Many tools ignore unknown flags without error. A command
that exits zero having done nothing looks identical to success. When a summary says
everything was skipped or nothing changed, read the code path before believing it.

**Say what you did not check.** One line naming the gap is worth more than a confident
sentence that turns out to be wrong.

## Cheap checks that settle most questions

```bash
grep -n '<the exact flag or symbol>' <the exact file>   # does it support it
git rev-parse --abbrev-ref HEAD                          # which branch will run
<tool> --version                                         # which version will run
ls -la <path>                                            # does it exist, and when did it change
```

## Founding failure

An agent stated that a script supported a particular flag. That was true on the branch it
had read. It then recommended checking out a different branch in the same working tree,
where an older copy of the script hardcoded the opposite behaviour and ignored unknown
flags without complaint.

Two runs of roughly twenty-five minutes each completed successfully and changed nothing.
The user's question afterwards was "why did you not check before you assume?"

The lesson is not that the agent lacked knowledge. It had read the correct file. The
lesson is that a `git checkout` invalidated the reading and nothing re-established it.
