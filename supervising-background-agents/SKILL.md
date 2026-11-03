---
name: supervising-background-agents
description: >-
  Use when dispatching parallel reader/worker sub-agents in the background, when their
  reports come back, and when one seems slow. Use before relaying a sub-agent's findings
  to the user, and when the user asks "are they still running?" or "did you check that?".
---

# Supervising background agents

## Dispatching

- **The first prompt carries every rule** (read-only, no secrets, no nested helpers unless
  they pass the rules on verbatim), plus exactly what to read first and what NOT to repeat.
  A rule relayed after launch arrives too late.
- **Name the output file and the reply budget** ("write notes/NN-topic.md; reply under
  300 words"). Reports then stay small, and the evidence stays on disk.
- **Give each agent a distinct area**, so two don't read the same files or overwrite each
  other's scratch output.

## When a report arrives

1. **Treat it as a hypothesis.** Pick its two or three load-bearing claims and verify them
   yourself, at the version that runs, before they reach the user or a skill.
2. **Watch for claims that contradict the answer you already had.** Reader agents are good
   at finding new things, and just as confident when they're wrong.
3. **Relay what you checked separately from what the agent said.** "Verified: X.
   Reader's claim, not checked: Y."
4. **Security reports come first.** If an agent says it saw a credential, tell the user
   what and where (never the value), and fix the filter that let it through.

## When one seems stuck

- At roughly twice the time its siblings took, check the agent list **and** whether its
  output or scratch files are still changing. "Running" with no file activity for hours
  means dead or stuck: stop it and relaunch.
- Some harnesses show a tiny transcript file for live agents too; judge by the files the
  agent is supposed to be writing.
- Commands inside agents that list or fetch hundreds of items need progress output and a
  cap. Otherwise a single account-wide listing looks like a hang.

## Paged fetches (API/MCP searches with thousands of results)

- **Split by a range key (e.g. date windows), one agent each, and get each range's exact
  count first.** Then each agent can prove it's complete (total keys == unique keys ==
  count). Ranges by "last updated" are very uneven: 19 / 5 / 4,679 / 655 tickets in
  2026-09. The one big window took ~50 min while the others took ~2.
- **Verify on disk yourself; don't take "matches totalCount" from the report.** Parse every
  saved page, recount keys, and regex-check any hand-written key list.
- **Anything an agent wrote by hand (inline results it couldn't copy as a file) gets a
  structure check** before use, e.g. every record has the expected field count.
- One bad item can time out a whole page every time. The agent should bisect the page size
  down to 1, save that item without the heavy field, and report the gap.

## Scripts agents will run

- `set -o pipefail` + `head` = SIGPIPE (exit 141) kills the script partway through.
  Protect such pipelines, and make listing scripts print a completeness line (`N of N`).
- A shorter list from a script is not evidence that anything went away.

## Founding failures

- A reader started its own helper agent without passing on the no-secrets rule. The helper
  printed a base64 service-account credential from a config file.
- A background tester showed as "running" for 12 hours with no report. Its siblings had
  finished in about 40 minutes. It was only noticed when the user asked to check stale
  agents.
- A failure-listing script died silently after the third of twelve entries: `head`
  closed its pipe under `pipefail`. The agent then reported three still-failing items as
  resolved.
