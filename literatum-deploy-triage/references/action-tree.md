# Deploy Server action tree, blocking and statuses

Source: `../literatum-platform/references/deep/01-*.md` (full read of atypon/deployserver, 434 files). Line refs are in that file.

## Statuses
`Scheduled, Executing, Executed, Success, Failure, Cancelled` are stored. `RestartWorkflow` / `CancelWorkflow` are UI commands, never stored.
- `Executed` is transient: the log is being validated → Success/Failure.
- `Cancelled` can be automatic: failed HostWarmupTest/Test/HostTestJane/MarlinJaneTest are auto-cancelled next cycle; `cancel_on_fail` rows; types with `cancelOnFailure` config → `canceled_by='auto'`; pre-insert "X is not configured. Ignoring action" rows are inserted as Cancelled; Java actions without a log parser default to Cancelled.

## How a deployment becomes a tree
- ProductRefreshDeploy, ProductDeployNoBuild, ProductRefreshDeployUpgrade, ProductRestart, HostRestart, SwitchToROMode/LiveMode, CanaryDeployment → rewritten to a **ProductRelease** row with `display_action=<original type>` and flags (build/patch/deploy/startNonWeb…).
  - ProductRefreshDeploy: build, patch, deploy, startNonWeb = true.
  - ProductDeployNoBuild: build=false.
  - HostRestart: only stop/start on one host.
- Expansion (PreExecuteVisitor.visitProductRelease) inserts children in this order; each child's `parent_id` = the ProductRelease id; `parent_action` = the display type.
  1. GaiaCompatibilityCheck (prod only), LeanDashboardVersionVerifier (prod, lean products)
  2. ProductBuild (+ ProductBuildStyleguide added automatically when deployconf has a styleguide version and no k8s pugrenderer). ProductBuildStyleguide runs on a tools host (round-robin), not on the site's hosts.
     - HostDeployStyleguide is added next to each **web** host's HostDeploy (type `web` or empty) when deployconf has a styleguide branch and (a pugrenderer cluster or no k8s pugrenderer) — `CreateActionVisitor.java:~183`. **Never on backstage.** Shown in the UI as `HostDeployStyleguide (w)`.
  3. Services, if deploy and deployconf configures them: SolrDeploy → SearchServiceDeploy → ProductConsumerDeploy → ProductAtmDeploy → ProductIngestionDeploy → XseDeploy → GaiaDeploy → PugrendererProductDeploy | K8sPugrendererDeploy
  4. Per host (hosts sorted alphabetically):
     - backstage: HostStop → HostDeploy → ProductPatch → HostStart
     - web: HostLock → Pause1Min → HostStop → HostDeploy (+HostDeployStyleguide) → HostStart (+HostWaitForWebServer) → HostWarmupTest (+HostEssentialTest on prod/readonly) → HostWarmupContent/HostTestJane? → HostUnlock
     - other non-web (rbackstage, backoffice…): HostStop → HostDeploy → HostStart
     - tandf/pericles: backstage → other non-web → web
  5. Tail: PugrendererInvalidateCache + CfInvalidateCache (if pugrenderer), SiteRegressionInteg (plain ProductRelease only), SdApiTest (sd on staging/midtierbeta)…
- With `parallelCount>1` (e.g. prod sage/pericles/tandf/marlin/achs/acm/aaas = 2) non-last web hosts drop their warm-up/unlock steps.

## Ordering and blocking (why siblings wait)
- Children are **not** chained by `wait_for_id`; order = `create_date, sequence_num`. A child waits while an earlier sibling (same account/product/family) is Scheduled.
- Blocking statuses are `Executing, Executed, Failure`. **Any non-Test Failure/Executing row blocks every Scheduled row of the same account+family** (rule 8). A failure therefore freezes the rest of that deployment and any other action on that family.
- Other notable blocks: one ProductBuild / ProductBuildStyleguide per build host; one runOnDeployServer action at a time; DbClone* blocks the target DB's products; `Pause` blocks the account.
- `immediate` actions bypass all blocks except `wait_for_id`.

## Retries
- Parser-requested retry (ProductBuild/ProductPatch on `restart build` / `Unable to delete file … DbAntPatcher.class`) is effectively broken: status ends Failure with `repeat_count=1`.
- HostWarmupTest retried per product test config, then auto-Cancelled.
- UI reschedule (Failure→Scheduled) increments `repeat_count`.
- RestartWorkflow re-runs **all** siblings of the family, including successful ones and the build. CancelWorkflow cancels later siblings regardless of state.
- A DS restart re-runs every Executing action from scratch.

## Logs
- `/info/<id>.txt`: SSH command list block, optional "Ansible commands" summary, then the main log. Main log lines: `[ ddMMM HH:mm.ss - <thread> ] <msg>`; raw SSH output unframed.
- The action header `<id>: <Action> by <user>. Account=…, Status=…, parentId=…, sequenceNum=…` is repeated on each status write; the **last** `Status=` is the final one.
- `cmdparams : {…}` can contain credentials — never print it.
- Where command output begins: `(ssh) <command>`; completion: `DrainResponse tt=…, prompt=true`.

## Read-only endpoints (safe)
`/info/<id>.txt[_N]`, `/actionlogs/<id>.txt`, `/actionlogs/<id>.ssh.txt`, `/testresult/<id>/…`, `/check?key=<rest_id>`, `/hostStats?account=…`, `/build.info`; GWT RPC `search` (with `cron=false`, no `query`), `getActionInfo(id)`.
Avoid even "read" RPCs with side effects: `getStyleguideProducts` (git checkout on the DS), `get*Backups` (SSH to hosts), git-sync lookups, `getAuthenticatedUserDetails`.
Never: `/run`, `/cancel`, `/unlock`, `/jira`, `/email`, uploaders, JSP cluster pages, and all GWT write methods.

## Repeatable (scheduled) deploys

Some releases are created by a **repeatable action**, not by a person (`deployserver …/scheduler/event/EventToActionFactory.java:63-118`, read 2026-09-25):
- The template is a row with `event_json` set that stays `Scheduled` for months. About every `cronFreq` (~2 min) its repeat rule (PST) is evaluated, and when it fires the row is copied into a new action with `parent_event_id` = template. The template's own log gets `CREATED ACTION : <new id>, FROM : <template>`.
- A day is **skipped** if the template is on `action_black_list` for that day, or if an instance is already Scheduled or running (`checkAlreadyScheduled`). Both post a Jira comment on the template's bug. The log still prints `CREATED ACTION`, but no row is created. So after a failure, later nights silently don't deploy.
- Examples (beta, 2026-09-26): informs `44595093…` (~01:01), acm `83aaec20…` (~16:01), mms `5a8eac8a…` (~17:05). Others exist; don't assume the list is complete. **`ds_release_tree.sh` prints `created by repeatable template <id>` when it finds one.** A template can exist while a given release was still started by a person (mms `c25ba892` on 24 Sep 01:18).
- **Triage:** if a failed release has no human submitter context, fetch its parent chain. If the log of `parentId` (or a `FROM :` line) shows a template, say "nightly auto-deploy". Its next runs are blocked until the failure is cleared.

## GaiaCompatibilityCheck (prod gate)

Added only to **prod** (`literatum`) ProductRefreshDeploy (`PreExecuteVisitor.java:2750`). `visitGaiaCompatibilityCheck` (:3137) compares prod vs **staging** deployconf `<gaia bundle_version>` and Gaia image tag and fails on any mismatch, when staging has no Gaia (`Gaia is not configured on Staging`), and also when both values are null (`isMatching` returns false). Log lines: `Mismatch Gaia bundle version between literatum X and Staging Y`. On 2026-09-25 deployconf `ad1c87a`: 61 of 66 prod Gaia products differ from staging (staging ahead in all 61), and nato/chrysalis have no staging Gaia. So this Failure usually means "prod deployconf not yet aligned with the version tested on stag", not a Gaia fault. Check the image tag and per-family values before concluding (only `bundle_version` at product level was compared; ConfHelper jar not in any repo).

## Reading times, attempts and blocking

- **Times:** Deploy Server log lines (`[ 24Sep 03:27.58 - deployd ]`) are **US Pacific** (PDT = UTC−7 in September); repeatable rules use PST. Git commit times are usually UTC, and the tools host's own prompt clock can be minutes off. Convert before comparing a build time with a commit (e.g. 01:19 PDT = 08:19 UTC).
- **Earlier attempts:** a rescheduled ProductBuild keeps older logs as `/info/<id>.txt_1`, `_2`, …; other types lose them. `ds_release_tree.sh` lists them as `[earlier: attempt_N@time]`. A step whose shown time is *earlier* than its predecessor's means the workflow was restarted.
- **Stale status:** the log's last header can be stale (after a restart the row is back to Scheduled). The tree script shows `[now=<status>]` from a live search when it differs. Trust `now`.
- **Empty `/info/<id>.txt`** = the row exists but never ran (Scheduled/blocked).
- **Why did it wait?** Each header carries `blockedId=` / `blockedAction=` (DB columns `blocked_id`, `blocked_action`, see `BlockActions.java`). The tree script shows `[blockedBy=<id>]`; fetch that id's log to see the blocker (usually an earlier Failure on the same account+family).
- **Search results contain more than the matching rows' ids:** `ds_search.py` prints every UUID in the response string table, which includes `parentId` and `blockedId` references. Read each id's header to tell them apart; an empty `/info` log = a row that never ran (Scheduled), identify it with an action-filtered `ds_list.sh`.
- **Cached logs:** the scripts reuse logs already under `${TMPDIR:-/tmp}/ds-triage-$USER/`; `ds_log.sh` prints the copy's time. Delete the file to re-fetch a live row's log.

