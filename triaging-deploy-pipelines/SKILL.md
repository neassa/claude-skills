---
name: triaging-deploy-pipelines
description: >-
  Use when diagnosing a failed deployment in a multi-step release pipeline (a deploy
  orchestrator, CI/CD system, or job scheduler that expands one release into many child
  steps: build, asset build, service deploys, DB migration, host stop/deploy/start, tests).
  Use when asked "why did this deploy fail", "what is broken on staging", or when a step
  shows Failure, a release hangs, or a green release left a site broken.
---

# Triaging deploy pipelines

## When this applies

Any orchestrator where one release fans out into ordered child steps whose pass/fail is
decided by the orchestrator, not by you. The failing row you are shown is rarely the
cause, and a green row is not proof that its step worked.

## The procedure

1. **Read the whole release, upstream first.** Build → asset build → service deploys →
   DB migration → host steps → tests. Read green steps too. The root cause is often in a
   step that reported success.
2. **Find the first real failure, not the current one.** Releases get restarted. The
   Failure row on screen may be a second-round symptom of an earlier failure whose row was
   since rescheduled. Compare run times: a step that ran *before* its predecessor means a
   restart.
3. **Trust the live status over the log header.** Logs record the status when they were
   written. After a restart or a manual status change, the row's current status differs.
   Query it.
4. **Take the first fatal line, then the last cause.** Not the first `error:`. Wrapper
   stacks (framework bean chains, task wrappers) print many lines; the real cause is
   usually the *last* `Caused by`.
5. **Look sideways.** What else ran on the same host, cluster or shared directory in the
   same minutes? Two deploys sharing a node, a `/tmp` path, an NFS checkout or a shared
   config file (`~/.npmrc`, `known_hosts`) break each other, and each log alone looks
   inexplicable.
6. **Read the code at the version that ran.** The branch and commit come from the build
   log, else from the environment's config. The default branch of your clone is not what
   production, staging or beta run. State branch and commit next to every code claim.
7. **Code or data?** Find the same step's successes on other targets, especially the same
   host. If it passed elsewhere, the cause is target-specific data or state.
8. **Classify and hand over:** code · dependency pin · migration code/data · startup ·
   credential · infra service · config · host state · test harness · transient race. Give
   the next read-only check and the owner. Say what only a host or database can settle.

## Sweep for damage no Failure row shows

Do this even when the failure list is empty.

- **Hosts left stopped.** A release stops a host, a later step fails, someone cancels the
  rest: the "start" step never runs. Look for a stop with no later start.
- **Hung steps.** Executing for days with steady keep-alive output = a hung tool whose
  progress output defeats the idle timeout. Executing for hours with *no* output = a hung
  build.
- **Scheduled jobs that stopped firing.** Repeating templates usually skip a run while a
  previous instance is still failed or scheduled, and they skip silently.

## Green steps that lie (check for your orchestrator's equivalents)

| Pattern | Why the green is wrong |
|---|---|
| Verdict = a success string found anywhere in the log | Printed unconditionally, or printed by a sub-step before the part that failed |
| Exit code lost in a wrapper (`run_x.sh` always exits 0) | The failure only shows as text, if at all |
| A step that's a no-op by design ("Not production, exiting") | It can't fail; another step does the real work |
| A cache-purge step that is a stub | Stale content after a "successful" deploy |
| A health check that ignores the state you care about | A "locked" node still passes the load balancer's check and receives traffic |
| Async work after the step returns | The step passes before the thing it started has finished or failed |

## Rules of evidence

- **A shorter failure list does not mean anything cleared.** Check the lister completed,
  then confirm each disappeared row by its own id.
- Logs expire. Note the date you saw each fact.
- A diagnosis copied from notes is a hypothesis until re-checked on the live release.

## Founding failures

- A build step was green, but a build-time source patch had failed and been reverted
  silently. The unpatched artifact then crashed on the backstage server two steps later.
  Hours were lost diffing git branches that were byte-identical; the difference existed
  only at build time. Reading the build log first would have shown it.
- The current Failure row on a release was an SSH key error on a service deploy. The real
  cause was an earlier database-migration step that had crashed on a dependency mismatch
  and been re-queued by a restart. The key error was transient; fixing it would have
  redeployed the bad artifact.
- An agent reported three failures as "cleared" because they were missing from a new
  listing. The listing script had died after 3 of 12 entries and a display filter hid the
  truncation. All three were still failing.
- Five backstage servers stayed down for two days: each release stopped them, failed, and
  was cancelled, so no step ever started them again. No Failure row pointed at it.
