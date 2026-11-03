---
name: literatum-deploy-triage
description: Use when triaging failed Literatum deployment actions on the Atypon Deploy Server (deployserver.literatumonline.com) — finding failed actions for beta (midtierbeta) / stag (staging), walking a ProductRelease / ProductRefreshDeploy tree to the failing child, reading its log, and mapping the failure to the repo, branch and root-cause class (build, styleguide, patch, host deploy/start, solr, consumer, gaia, cassandra, redis, deployconf). Strictly read-only.
---

# Literatum deploy triage (read-only)

Load `literatum-platform` first for the map of repos, runtime and deploy pipeline.

**Paths:** `scripts/` and `references/` are relative to this skill's folder. Wherever the skill is installed (`~/.claude/skills/`, `~/.cursor/skills/`, `.cursor/skills/`, …), run scripts by that full path, e.g. `bash <skill-dir>/scripts/ds_failures.sh midtierbeta`. Set `LIT_REPOS` to your folder of read-only clones and `TMPDIR` to a private scratch folder first (setup: `../literatum-platform/SETUP.md`).

## Hard rules

1. **Read-only.** Never create, cancel, reschedule, restart, kill or unlock an action. Never call `/run`, `/cancel`, `/unlock` or GWT write methods (`addAction`, `execute`, `createAction`, `updateStatus`, `killAction`, `cancelChildActions`). Never touch the UI **Status dropdown**: it is a live control. Never send `cron=true` in a search (it deletes from `action_black_list`).
2. **No DB access** (Deploy Server Postgres or site DBs) and no code changes. Say what only the DB can settle and ask the user.
3. **Never read secret values.** Logs, deployconf, scripts and props hold credentials, often as bare literals no keyword filter catches. Read repo files through `scripts/safe_view.py FILE [START [END]]` / `scripts/safe_view.py --grep RE PATH`, which masks them. Exception: parsing deployconf with `python3 xml.etree` is allowed when you print only attribute **names** plus values of plainly non-secret keys (host, port, version, branch, cluster, path) and skip anything whose name looks secret. Filter logs with the scripts' `SECRET_RE` plus the case-sensitive `CLI_SECRET_RE` (don't add bare words like `private` or `auth` to them: they hide javac `private access` errors and `author`). Never open `deployserver.properties`, `.env`, keys or vault files. Report "secret-bearing line at file:line". Sub-agents get these rules word for word in their first prompt.
4. **No page JavaScript or UI clicks** without the user's OK for that exact action.
5. **Verify, don't assume.** Mark each claim *checked* (log / code at commit / live search) or *inferred*, and keep checking until only host/DB items remain. Say "not in my clones" until you've searched all of github.com/atypon.

## The model

- **Env = account:** beta `midtierbeta`, stag `staging`, prod `literatum`. Site = `product` + `family`.
- Every step is a `deploy_action` row. A ProductRefreshDeploy etc. becomes a **ProductRelease** whose children run in `create_date, sequence_num` order. The parent is `Success` as soon as it expands, so **judge only the children**.
- A failed child **blocks** the account+family. Later siblings stay Scheduled. Test and `cancelOnFailure` steps become Cancelled (`canceled_by=auto`), but the log header's `canceledBy` is ~always `null`, so treat a Cancelled step that ran as a possible failure.
- **Pass/fail = text match on the log.** Failure is reliable; Success often isn't → `references/false-successes.md`.
- Some releases are **nightly auto-deploys** from a repeatable template (the tree script says so; for ProductRefreshDeploy-type templates it matches by creation minute, because the created row is converted into a ProductRelease with a new id). A failure silently stops later nights → `references/action-tree.md`.
- Chain, statuses, retries, repeatable actions, the prod Gaia gate → `references/action-tree.md`.

## Procedure

1. **List failures:** `scripts/ds_failures.sh <midtierbeta|staging>` (current Failure rows only). **A failure that was cancelled or rescheduled is invisible there**: use `scripts/ds_list.sh <acct> <product> [action] [status] [pageSize] [regex]` to list a product's actions with run time, host, log status, live status and parent, sorted by time (e.g. `ds_list.sh staging hope`, or `ds_list.sh midtierbeta "" GaiaDeploy "" 300 '20Sep 23:'` for everything that ran in that hour on any product). It must end with `COMPLETENESS: N of N`; if not, re-run. **A shorter list never means something cleared:** confirm by a product-filtered `scripts/ds_search.py <acct> <status> <action> 500 <product>`. `//EX` = GWT hashes changed after a DS redeploy: re-read them from `deployserver.nocache.js`, don't guess.
2. **Read the whole release, upstream first:** `scripts/ds_release_tree.sh <acct> <product> <releaseId>`. It shows the live status (`now=`), earlier build attempts, `blockedBy=` and the creating template. Times are US Pacific. Read build → styleguide build → service deploys → bks → web, green steps too. *Founding case (LIT-683431):* ProductBuild green, build-time patch reverted, bks crashed later. Watch for **re-runs**: the first failure is the root and the current Failure row may be a second-round symptom (mms). **After a bks failure + cancel, check whether HostStart ever ran**: if not, the backstage is still stopped, say so.
3. **First fatal line** of the root failure, after the last `(ssh)` command. **Then look sideways:** what else ran on the same host/cluster in the same minutes (`ds_list.sh <acct> "" <Action> "" 300 '<time>'`)? Two deploys sharing a node or a `/tmp` path can break each other (uchicago/authorea GaiaDeploy, 6 s apart). Not the first `error:`. Match it in `references/failure-signatures.md`. Wrapper stacks (Spring bean chains) hide the cause in the last `Caused by`.
4. **Repo + branch:** from the log (`LIT BRANCH :`, `The revision =`, `SYNC [...]`), else deployconf for that env, parsed with an XML parser, never grep. Update clones and read code **at that branch**; state branch + commit. See `references/repos-and-branches.md`.
5. **Code or data?** Find the same step's successes (`ds_search.py <acct> Success <Action>`) and check whether it passed elsewhere, especially on the same host.
6. **Classify:** code · dependency pin · patch code/data · patch-VM startup · infra credential · infra service · deployconf · host/process · test harness · transient. Give the next read-only check and the owner.
7. **Sweep for damage no Failure row shows** (do this even when an account has zero failures):
   - **Stopped backstages:** for each product with a failed/cancelled bks step, `scripts/ds_list.sh <acct> <product> "" "" 200 'HostStop|HostStart' | grep bks`. A `HostStop` with no later `HostStart` = the bks JVM is down unless started by hand (2026-09-26: 4 beta + 1 stag bks in that state for 2 days). Say it plainly; only the host can confirm.
   - **Hung actions:** `scripts/ds_search.py <acct> Executing "" 100` then `ds_log.sh <id> 'KeepAlive|Task :' | tail -3`: thousands of keep-alives over days = hung tool; **zero keep-alives and a log that stopped hours ago = hung build** (rmit beta 26 Sep) (DeleteEmployee ×3 on 2026-09-26; gradle progress output keeps the SSH session alive, so the idle TTL never fires). They queue later Create/DeleteEmployee rows but don't block deploys (`blockIgnore=true`).
   - **Nightly templates skipping:** the tree script names the template; its log's last `CREATED ACTION` date tells you how long it has been skipping.
8. **Check Jira** (read-only JQL on `atypon.atlassian.net`, see `references/repos-and-branches.md`) for the exact signature before concluding. Also `../literatum-platform/references/deep/14-jira-resolutions.md`.

## Logs

- `GET https://deployserver.literatumonline.com/info/<id>.txt` (older ProductBuild attempts: `.txt_N`). Logs purged after **15 days**. Success/Cancelled rows are purged too; Failure rows are kept.
- Full patch output is on the backstage host (`/var/tmp/<epoch>.txt`), and styleguide `build.log` is on the tools host (`~<acct>/logs/<acct>/<p>/UI/build.tgz`). Ask the user for both.

## References

- `references/false-successes.md`: green steps that lie (HostDeployStyleguide no-op, CfInvalidateCache stub, warm-up verdicts, GaiaDeploy, HostUnlock `-p` bug, …).
- `references/failure-signatures.md`: signature → meaning → class, per layer (build, patch, Cassandra, Akka/cluster, styleguide, search/REST/DB, CLI).
- `references/action-tree.md`: release expansion, blocking, retries, repeatable (nightly) deploys, GaiaCompatibilityCheck.
- `references/repos-and-branches.md`: step → repo/script and how to find the branch per env.
- `references/worked-examples.md`: full diagnoses (was, mms, aiaa, informs) as patterns.
- `scripts/`: `ds_failures.sh`, `ds_release_tree.sh`, `ds_list.sh`, `ds_log.sh <id> [regex] [ctx]` (one log, masked, with retries), `ds_search.py`, `safe_view.py` (all read-only). `git show <ref>:<path> | scripts/safe_view.py -` reads a file at any git ref, masked.
- Deep notes with file:line: `../literatum-platform/references/deep/01..30-*.md`. Clones: `$LIT_REPOS/`. Related: `literatum-ansible` (any step that runs `ansible-actions`: error codes, branch selection, per-service false successes), `literatum-patch-cassandra-failures`.
