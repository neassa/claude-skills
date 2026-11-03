# Atypon Deploy Server — full read notes

Repo: `$LIT_REPOS/deployserver` @ `b726c83` (Merge PR #422 LIT-680178-2). `git ls-files` = **434** files (task estimate said 417), ~100.4k lines.
Read-only review; no builds/scripts/network/DB run. Secrets are never reproduced: they are cited as `<secret at file:line>`.
All paths below are relative to repo root; `S/` = `src/com/atypon/deployserver/`.

Method: I read the core engine myself (daemon, scheduler, blocking, SQL, visitors PreExecute/SshExecute/SshExecuted/ProductReleaseConverter/ReleaseType, DeployUtils/DeployConfUtils/DeployActionSql/DeployServiceImpl/ServiceImpl, connect core, shared/). Three parallel readers read in full: (A) all of `S/client/**`; (B) peripheral server packages, war/, web.xml, scripts/, migrations, config (non-action), build files; (C) ActionType, actions.xml, actions-config.xml(+xsd), server/config, server/actions, CreateAction*, explode, ExplodeCmdHelper, PostExecute, PreQueued. Their findings are merged below.

---

## 1. Coverage table

| Directory | Files | Read fully? | By |
|---|---|---|---|
| (root) AGENTS.md, README.md, pom.xml, build.xml, .gitignore | 5 | yes | B |
| config/ (actions.xml, actions-config.xml/.xsd, *.properties, csv, xml, vm, yml, tmpl, json) | 27 | yes; `.properties`/`insights-gcp.json`/`newrelic.json` → key names/line numbers only | C (actions*), B (rest) |
| config/jiraalert/config | 2 | yes (secret line skipped) | B |
| config/override | 17 | key names only | B |
| config/prom-rules | 1 | yes | B |
| release-pipeline | 1 | yes | B |
| resources/db/migration | 3 | yes | B |
| scripts | 23 | yes (secret lines cited only) | B |
| .settings | 4 | yes | B |
| src (client_secret.json, 0 lines/397 bytes, no newline) | 1 | **not opened** (credential file, per rule) | — |
| S/ (Deployserver.gwt.xml) | 1 | yes | A |
| S/client | 39 | yes (ServiceAsyncWrapper: pattern-verified by script beyond l.120) | A |
| S/client/args | 2 | yes | A |
| S/client/renderer | 52 | yes (near-duplicate pairs read via diff) | A |
| S/client/renderer/event | 4 | yes | A |
| S/client/visitor | 3 | yes (IActionVisitor 4799 lines: l.1-1000 read, rest script-verified — mechanical) | A |
| S/client/widgets | 1 | yes | A |
| S/model (Task.txt) | 1 | yes (dead design note) | A |
| S/monitor | 5 | yes | B |
| S/newrelic | 9 | yes | B |
| S/server (top-level) | 28 | yes | me + B |
| S/server/actions | 12 | yes | me + C |
| S/server/actions/model | 22 | yes | C |
| S/server/config | 2 | yes | C |
| S/server/config/model | 9 | yes | C |
| S/server/connect | 15 | yes | me + B |
| S/server/filter | 2 | yes | B |
| S/server/integ | 3 | yes | B |
| S/server/prodmon | 5 | yes | B |
| S/server/ReleaseSetToReleaseConverter/java | 1 | yes | B |
| S/server/rest | 10 | yes | B |
| S/server/scheduler | 3 | yes | me |
| S/server/scheduler/event | 2 | yes | me |
| S/server/service | 5 | yes | B |
| S/server/servlet | 10 | yes | B (+me InfoServlet/ActionLogServlet) |
| S/server/strategy/** | 3 | yes | B |
| S/server/uptime | 7 | yes | B |
| S/server/utils | 15 | yes | B (+me SqlQualifier) |
| S/server/visitor | 11 | yes | me + C |
| S/server/visitor/explode | 2 | yes | C |
| S/shared (+model, releasemanager) | 11 | yes | me (+C ActionConfig/IActionConfig/ActionTags) |
| src-test | 1 | yes | B |
| testdir (f1,f2 empty) | 2 | yes | B |
| war (jsp/html/css/images) | 29 | yes; images skipped | B |
| war/insights_files | 14 | own `main.js` read; vendor minified libs noted only | B |
| war/treecss | 6 | css read, pngs skipped | B |
| war/WEB-INF (web.xml, .gitignore, png) | 3 | yes | B |
| **Total** | **434** | all except src/client_secret.json, binaries, vendor-minified js/css | |

---

## 2. Architecture and state machine

### 2.1 Process layout
- `ServerMain` (Jetty :8080, war `./war`; `--patchdb` runs Flyway) starts Spring/Hikari (`AppConfig`), `UptimeParseThread`, `HousekeepingThread` (git-sync deployconf every 10s, Jira updates, merge dashboard), and `DeployDaemon.init()`. `ServiceImpl.init()` (GWT RPC servlet) also calls `DeployDaemon.init()` (ServiceImpl.java:116-123; idempotent via static `instance`).
- One Postgres DB; the whole engine is the table **`deploy_action`** (V1__base_schema.sql:1-51). Columns that matter: `id` (UUID), `sequence_num` (serial, insertion order), `parent_id`, `parent_action`, `action`, `display_action`, `status`, `repeat_count`, `immediate`, `background`, `cancel_on_fail`, `cancel_flag`, `canceled_by`, `wait_for_id`, `blocked_id`, `blocked_action`, `block_ignore`, `blocks_id`, `block_updated`, `expand_pending`, `event_json` (cron template rows), `parent_event_id`, `args`, `bug_id`, `rest_id`, `host`, `host_type`, `thread_id`, `time_taken`, `queued_time`, `solr_error`.
- Status enum (shared/CmdIO.java:100-101): `Scheduled, Executing, Executed, Success, Failure, Cancelled, RestartWorkflow, CancelWorkflow`. The last two are *commands* from the UI only; they are never stored.

### 2.2 Request → deploy_action row
Entry points that create rows (all call `DeployActionSql.createAction`):
- GWT RPC `addAction` / `execute` / `createAction` (DeployServiceImpl.java:154, 337, 2352).
- REST `GET /run?action=&account=&product=&family=&host=&type=&user=&bugId=&args=` → `createRestApiAction` (DeployActionSql.java:48-112): case-insensitive action lookup, `rest_id`=new UUID (returned as `key`), default user `opsmail`; ConsulPopulate dedup per account; HostRestart refused if HostUnlock running/scheduled or ProductRelease scheduled for the product.
- Internal: visitors, listeners, cron (`EventToActionFactory`), `DeployDaemonHelper` explosions.

`createAction(AddRequest)` (DeployActionSql.java:148-185): builds ActionInfo (status Scheduled), `id=UUID`; *sync* actions (config `sync`) get `create_date=now+5min` and are **run inline in the RPC thread** (`runSyncAction`, :187-199), optionally with their children (`syncChildren`).
`createAction(ActionInfo, delta, runTests, expandMacro, expandMultiSelect)` (:374-706):
1. `expandMultiSelect` (:298-319): comma-separated products → one row per product-family (Insights args types instead pack products into args, :321-368).
2. Pre-insert auto-cancel checks: `requires solrDocker/dbDocker/xse/searchService(unless parent LTF)/atm/ingestion/cassandra/gaia/k8sPugrenderer/consumer` not configured in deployconf → `status=Cancelled` (row still inserted) (:385-444); Pugrenderer/CfInvalidateCache without pugrenderer cluster; DbProductBackup/LocalDbCloneAndRestore/LocalAndCipT1DbRemove on `literatum` → Cancelled; LeanDashboardVersionVerifier only on literatum.
3. Host: `runOnBks` → product backstage; RunPuppet host from args; empty host + `run-on-host` list → random pick (round-robin `buildIndex` for ProductBuild/ProductBuildStyleguide; lts+acm hard-coded `tools-14`) (:497-514).
4. `HostEssentialTest` with no parent → immediate (:515).
5. `event_json` set (cron template) → no macro expansion.
6. **Macro expansion**: `ProductReleaseConverter.convert` (if `newimpl.<Type>=true`, rewrite to a ProductRelease row, see §4) else `CreateActionVisitor` (macros in CreateActionMacro); if it consumed the row, stop.
7. `runOnDeployServer` → `account='deployserver'`.
8. INSERT (:540-597): host blanked unless config `resolveHost`; `expand_pending = expandPending || deferredExpand`; `immediate = ai.immediate ?? config.execImmediately`; `cancel_on_fail = ai.cancelOnFail || action==Test`; `block_ignore = config.blockIgnore || ai.blockIgnore`; `pst_day` yyMMdd PST.
9. Side-effects: ProductRelease on literatum (non pre-prod) → deployment notification email; literatum pericles/amps with build → **JSM CHG ticket** created (:607-658); `updateBugWhenScheduled` → Jira comment (:660-705).

### 2.3 DeployDaemon loop (DeployDaemon.java:51-212)
- On start: `update deploy_action set status='Scheduled' where status='Executing'` (rescheduleOnStart, :215-233) — every in-flight action is **re-run from scratch** after a restart (also `Executed` rows are then picked up by processExecuted).
- Thread `deployd`: ThreadPoolExecutor with `capacity.total` threads (prop 120). Every `pollnext.pause` (prop value `10`, unit-less) ms:
  - `purgeOldDeployActions` every `dbcleanup.freq` (4h): delete rows older than `dbcleanup.maxdays.deployaction` (15) days that are non-cron or Success/Cancelled (:154-167). **Failure rows older than 15 days are kept; Success/Cancelled rows vanish (and their log files are deleted by `scripts/clean_disk.sh` after 15 days).**
  - `ConnectionCleanup.cleanupConnections` every `connection.idle.check.freq`.
  - Only if the executor queue is empty: `createTask()`:
    1. `DeployConfUtils.refreshDeployConf()` (reload deployconf.*.xml if mtime changed).
    2. `DeployDaemonHelper.processExecuted(false)`: rows `status='Executed' and update_date > 10s ago` (max 100) → validate (see 2.6).
    3. `rescheduleFailedActions()` — see retries 2.7.
    4. `rescheduleFailedTests()`, `cancelFailedTests()`, `cancelFailedActions()`.
    5. `Scheduler.getNext()` (2.4). If a row is returned: `updateQueuedTime`, `PreQueuedActionVisitor` (may complete/expand the action itself, e.g. ConfigRefreshDeploy = local SyncDeployConf + Success, Proxy/ToolOpstoolInstall/Cassandra restore fan-out), and if still Scheduled → `updateStatus(Executing)` → new `RunAction` submitted.

### 2.4 Scheduler.getNext (scheduler/Scheduler.java:50-266)
1. `EventToActionFactory.createActions` — cron rows (event_json not null, status Scheduled, not checked in 5 min). `s_lastCheckTime` is never assigned, so the `cron.freq` throttle is dead and it runs every cycle (EventToActionFactory.java:32-37). Due events clone the template into a normal row (`parent_event_id`=template id); skipped (row Cancelled/not inserted, Jira comment) if the day is black-listed or a prior instance is Scheduled/Executing/**Failure** (:125-141 — a failed instance blocks every future run until it is cancelled).
2. `refreshBlocks()` — 25 SQL passes rewriting `blocked_id/blocked_action` on Scheduled rows (2.5).
3. Candidate selection, in order:
   a. `getNextScheduledExecuteImmediateAction` (FindActions.java:323-352): `status=Scheduled, create_date<now, event_json null, (wait_for_id null or wait_for_id row in Success/Cancelled), (immediate='t' or action in execImmediately-types), block_updated='t'` ordered by `create_date, sequence_num`. **Ignores `blocked_id` entirely** — immediate actions bypass every block rule except wait_for_id.
   b. else literatum/readonly/gcp-rehearsal non-background rows first, then all accounts incl. background; within each, `priority.high.products` (pericles, marlin, mms, acm, tandf, catalyst, sage, aip, esspp, achs, rmit, aaas) first. Filter: `blocked_id is null and blocked_action is null and action not in ('PauseOthers','Pause') and block_updated='t'`, order `create_date, sequence_num` (:213-266).
   c. A candidate whose parent is Tier1EnvironmentRebuild/ProductTermination/MajorReleaseUpgrade/EnvironmentRebuild is discarded in the high-priority pass and re-queried without the product filter (:203-209); when `priority.high.products` is empty it would never run via this path (prop is non-empty in prod).
4. Checks on the chosen row (:104-167):
   - `cancel_flag` set (UI cancel of a Scheduled row) → status Cancelled, pick the next one (only once).
   - `isAtExecutingCapacityLimit` (Executing count per account ≥ `capacity.account` 70, or per account+host ≥ `capacity.host` 35; immediate non-Test rows exempt) → skip that account.
   - `isAllowed`: `opsOnly` display-type actions by a non-ops user at top level → **Failure** ("User is not allowed…").
   - **Log reset**: `DeployUtils.getActionLogFile(ai, true)` (2.8/§5).
   - `isDeployConfRefresh` actions (not SvnRefreshScripts, no wait_for_id): find or create an `SvnRefreshScripts` row for the account and set `wait_for_id` on this row; re-pick.
   - `expandAction` (FindActions.java:354-429): SyncDeployConf if deployconf-refresh; `explodeProductStopAll`, `explodeDbClone` (DbCloneBackup→Copy→Restore→DbCleanupPostClone chained by wait_for_id), `explodeDbCleanupPostClone` (ProductCleanupPostClone per product on the target DB), or `deferredExpand` (deploy types via `expandDeployAction` → legacy DeployWithParams chains; others via `ExplodeCmdHelper.explodeSingleAction` + `combineActionsToParallelize`) → parent **Success**, children inserted.
5. `blockForPrevScheduledActions` (BlockActions.java:501-562) — sibling ordering (2.5.2). If blocked → null this cycle.

### 2.5 Blocking rules (BlockActions.java, run every cycle in this order, Scheduler.java:74-102)
"Blocking status" = `Executing, Executed, Failure` (SqlQualifier.java:32-40). **A Failure row blocks exactly like a running one until it is Cancelled, rescheduled or Success.**

| # | Rule | Effect |
|---|---|---|
| 1 | clearBlocks (:94-103) | clear self-blocks; clear ProductBuild/ProductBuildStyleguide blocked by a *failed* build of the same action; clear any block whose blocker is Success/Cancelled/Scheduled |
| 2 | updateBlock (:115) | `block_updated 'f'→'t'` (rows just (re)scheduled are held back one cycle) |
| 3 | setBlocksId (:120-141) | honour `blocks_id` of non-finished rows; **wait_for_id** → `blocked_id=wait_for_id` when blocker not Success/Cancelled and both rows non-immediate |
| 4 | blockDeployServerActions (:479) | only one `runOnDeployServer` action at a time; the oldest blocking-status one blocks all other Scheduled deploy-server actions (a *failed* one blocks them all) |
| 5 | blockedByCloneActions (:175-210) | running/failed/scheduled DbClone*/DbFlexClone/DbOptimize/DbCloneRemove block later Scheduled actions of every product on that target DB (except rebuild/termination children) |
| 6 | blockAccountActions (:430) | a Scheduled `Pause` blocks everything created after it in the account (Pause itself is never picked: must be cancelled) |
| 7 | blockAccountScopedActions (:143) | first blocking-status AccountLevel-scope action (non block_ignore; clone types excluded) blocks all Scheduled rows of the account |
| 8 | blockProductScopedActions (:212-248) | first blocking ProductLevel action per account-family blocks all Scheduled rows of account+family; plus a join: **any** non-Test, non-block_ignore row in Failure/Executed/Executing blocks every Scheduled row with the same account+family (RO/Live switch children excepted) |
| 9 | blockSwitchProductActions / blockDueToSwitchProductActions (:250-316) | SwitchToROMode/SwitchToLiveMode children serialize per product across literatum/readonly and block other actions on the product |
| 10 | blockUserScopedActions | commented out (PauseOthers dead) |
| 11 | blockDueToProductFlexClone (:389) | running/failed ProductFlexClone blocks the whole account (only unblocked rows) |
| 12 | blockSerializeActions (:565) | `serialize` types: one at a time globally (execImmediately ones: per account, and also set wait_for_id) |
| 13 | blockByUser (:601) | `serializeByUser` types: one at a time per user; also blocks later **Failure** rows and sets wait_for_id |
| 14 | PB2backup ↔ DbClone rules (:750-785) | PB2backup running/failed blocks DbClone*; DbClone* blocks PB2restore |
| 15 | clearSelfBlocks | again |
| 16 | blockBuildHostActions / blockBuildSGHostActions (:445-477) | one ProductBuild (resp. ProductBuildStyleguide) per build host |
| 17 | blockActionsWithExecutionLimit (:665) | `action.execution.limit.X` global cap → sets `blocked_id=id` (self-block, cleared next cycle) |
| 18 | blockActionsPerAccountLimit (:726) | `actions.account.execution.limit.X` per account (e.g. SolrDeploy 10, DbProductRestore 2, PB2backup 5) |
| 19 | blockMergeActions (:637) | DryMerge/GitMergeRev/GitMerge fully serialized (sets wait_for_id too) |
| 20 | blockingCloneActions (:159) | one clone-family action per account |
| 21 | blockHostActions (:411) | one HostEssentialTest per account+host+product |
| 22 | blockSGCleanup / blockBySGCleanup (:698-724) | SgBranchesCleanup vs ProductRelease/PugrendererProductDeploy |
| 23 | blockCreateDeleteEmployee (:788) | CreateNewEmployee/DeleteEmployee per product |

#### 2.5.2 Sibling ordering (blockForPrevScheduledActions, :501-562)
Children are **not** chained by wait_for_id (ProductRelease uses `createActions(trg,false)`); order comes from `create_date` (children copy the parent's) + `sequence_num` (insertion order). Before starting a non-immediate child, look for an earlier sibling (same `parent_id`, `(create_date, sequence_num)` smaller):
- parent SwitchToROMode/SwitchToLiveMode: earlier **Scheduled** siblings with same product+family in literatum/readonly;
- parent EnvironmentRebuild/Tier1EnvironmentRebuild/ProductTermination (not HostStop): earlier siblings Scheduled **or Executing** in same account (strict serial);
- parent MajorReleaseUpgrade (not HostStop): earlier Scheduled/Executing siblings (any account);
- otherwise (ProductRelease etc.): earlier **Scheduled** siblings with same account, product, family.
The earliest is written as `blocked_id`. In the default case "previous sibling still Executing" is not checked here — it is enforced by rule 8 (same account+family, blocking status) unless the running sibling has `block_ignore` (parallelization, §4.5) or is a `Test`.

### 2.6 RunAction → visitors → status
`RunAction.run` (RunAction.java:23-80, thread name → `deploy_action.thread_id`):
1. `RemoteExecutor.Factory.getInstance(account).runAction(ai)` = `JSchConnector` → `AbstractConnector.runAction` (connect/AbstractConnector.java:96-195):
   - write `runAction> <ai>`; **PreExecuteVisitor**. If it `markDone(status)` (writes status + runs PostExecuteVisitor) → return; no SSH. (Java-only actions: ProductRelease, rebuild macros, deployconf edits, release manager, REST relays…)
   - resolve host: `runOnDeployServer` → `prod-acdeploy.in.atypon.com` (or `cip-acdeploy.in.atypon.com` on the CIP DS) as account `literatum`; empty host → any host of account (account hostResolveScope) or product/family (product scope). Log `SELECTED HOST.2: <host>`.
   - `runRemoteCmdImpl`: up to 5 connect attempts, 5 s apart; login user = `resolveAliasAccount(account)`; key `~/.ssh/id_rsa_deployserver` (`~/CloudBuild.pem` for insights); ProxyJump for `proxy.accounts`; `gcp*` → `<host>.gcp.atypon.com`, `cip` → `<host>.int.atypon.com`; `StrictHostKeyChecking=no`; opens an interactive **shell** channel.
   - Inside: `Action.Factory.inst(ai)` — if `config/actions.xml` has `<action name=Type>` → **CreateAction/template path** (`ActionImpl.runAction`: ActionModelVisitor model; invalid model → return **Cancelled**; Velocity render; one `runCmd` per line; `exit`); else **SshExecuteVisitor** (Java-built commands).
   - Executor returns null → status **Executed**. Any exception after connect → **Failure** (JSchConnector.java:143-149). All 5 connects failed → Failure.
2. RunAction writes the new status (`Executed`), then immediately `DeployDaemonHelper.processExecuted(ai)` in the same thread (guarded by `currentlyInExecuteProcessing` map so the daemon's scan does not double-process):
   - template action → `ActionSpec.validator.isValid` (validate-txt/or/invalid chain on `actionlogs/<id>.txt`) → Success/Failure (always Success with `debug.ignorecmds`);
   - Java/SSH action → **SshExecutedVisitor** parses the log. **Default verdict is `Cancelled`** (SshExecutedVisitor.java:42) for any type without an override. Test types (Test, HostWarmupTest, HostEssentialTest, HostTest, MarlinJaneTest, HostTestJane) call `runAction(ai, this)` again — a second SSH session in "collect" mode that scp's results and sets the verdict (SshExecuteVisitor.java:683-827).
   - `solr_error` flag set if configured Solr error strings appear.
   - If Failure and `repeat_count==0` and parser asked for reschedule → `rescheduleAction` (Scheduled, repeat_count+1). Test + "SeleniumException: Timed out" → also rescheduled.
   - `PostExecuteVisitor.accept(ai, newStatus)` (skipped for NonVisualRegressionTest): `cancelWorkflowOnFailure` config (set on no action ⇒ dead) would cancel all siblings in account+family; **`cancelOnFailure` config → the Failure becomes `Cancelled` with `canceled_by='auto'`** + Jira comment; otherwise per-type follow-ups (spawn children, Jira/email, schedule future actions).
3. RunAction then writes the returned status; if still `Executed` → Failure ("failed to convert from executed state"). Finally `time_taken += elapsed` (and: ProductPatch ≥ 30 min staging / 60 min others (non-literatum) → **creates a LIT Jira P2 ticket** with the log attached; ProductFlexClone ≥ 15 min → email).

Other status writers: `HostWaitForWebServer/HostWaitForHearbeat` return `Scheduled` from `CompletedActionValidator` until `time_taken ≥ timeout.<Action>` (polling loop); `ConnectionCleanup` force-closes connections idle > `connection.idle.ttl` (1h) or `timeout.<Action>` and sets **Failure** (ConnectionCleanup.java:70-87); `JiraHelper.updateFailedActions` turns failed GitMerge/GitMergeRev into **Cancelled** (JiraHelper.java:156-157).

### 2.7 Retries (`repeat_count`)
| Mechanism | Where | Rule |
|---|---|---|
| Parser-requested | DeployDaemonHelper.java:539-541, 570-594 | Failure + `repeat_count==0` + SshExecutedVisitor `reschedule` (ProductBuild/ProductPatch with "restart build" or "Unable to delete file…DbAntPatcher.class"; Check/SubmitPassport/Check/DigitalObject reprocess & GenerateDbIndexReport when neither success nor explicit failure text) → Scheduled, repeat_count+1. **Template (actions.xml) actions never auto-retry.** *See bug B1: in the RunAction path this Scheduled is overwritten by Failure.* |
| Test timeout | :552-569 | `Test` with "SeleniumException: Timed out", repeat_count 0 → reschedule |
| ProductCleanupPostClone | :81-105 | every cycle, failed rows with repeat_count<2 → Scheduled |
| HostRestart children | :85-93 | failed child with parent_action=HostRestart, >90 min since update, repeat<3 → **all rows with that parent_id** set Scheduled (incl. already-successful siblings) |
| HostWarmupTest | :52-80 | retry count = `xmllint` of `~/source/HEAD/atypon/tool/qa/testconf/hostwarmup/hostwarmup.<product>.test.xml @retry` on the DS (fallback `selenium.test.retry`=1); reschedules all failed HostWarmupTest children of that product/family/account with repeat_count<retry |
| then cancelFailedTests | :114-123 | any remaining Failure of HostWarmupTest/Test/HostTestJane/MarlinJaneTest → **Cancelled** (so failed warm-up tests never block a deploy; they turn Cancelled within one cycle) |
| cancelFailedActions | :106-112 | `cancel_on_fail='t'` and Failure → Cancelled (Test always has it; UI cancelling one HostWarmupTest sets it on all HostWarmupTest siblings of the product, DeployServiceImpl.java:440-447) |
| Manual reschedule | DeployServiceImpl.updateStatus :449-456 | UI/RPC Failure→Scheduled increments repeat_count |
| Cron | EventToActionFactory | new row each run (no repeat_count) |

`repeat_count` also indexes rotated log files `.txt_N` for `actions.logs.multipleFilesActions` (§5).

### 2.8 UI/RPC status commands (DeployServiceImpl.updateStatus, :386-458)
`updateStatus(loggedInUser, actionId, currentStatus, newStatus)` — acts only if the row is still in `currentStatus`. `loggedInUser` is client-supplied (no server check).
- `Cancelled` → sets `cancel_flag='t', canceled_by=user` first (Scheduler turns a Scheduled flagged row Cancelled when picked) and then writes status Cancelled directly (`updateStatus(actionId, Cancelled)`, block_updated='f'). For Executing rows this does **not** kill the SSH session (use `killAction` → `ConnectionCleanup.cleanupConnection` → force close → Failure).
- `Scheduled` (reschedule) → status Scheduled, block_updated='f'; from Failure also repeat_count+1; HostWaitFor* resets time_taken.
- **`CancelWorkflow`** (requires row family non-empty): `update … set status='Cancelled', canceled_by=user where parent_id=<row.parent_id> and family=<row.family> and sequence_num >= <row.sequence_num>` (family filter dropped when parent_action=ProductRefreshDeploy). No status filter: later siblings are cancelled whatever their state (including Executing ones — the running thread will later overwrite with its own result).
- **`RestartWorkflow`**: `update … set status='Scheduled' where parent_id=<row.parent_id> and family=<row.family>` (family filter dropped for ProductRefreshDeploy parent). **All siblings including already-Successful ones and the build are re-run from the beginning**, repeat_count untouched, block_updated untouched; logs of non-multi-log types are wiped at re-pick.
- UI only offers Restart/CancelWorkflow on Failure rows whose parent type has `workflowStatus` config and family set (GridResultVisitor.java:280-287). `cancelChildActions(actionId,user)` (UI "CancelWorkflow" on a Success parent) cancels children in Scheduled/Failure (DeployServiceImpl.java:1679-1682).

### 2.9 What happens to the children when one fails (ProductRelease default)
1. The failed child stays `Failure`; with blocking status it blocks every Scheduled row in the same **account + family** (rule 8) — i.e. the rest of this deployment *and any other action on that family* (other deploys, restarts) queue behind it indefinitely. The UI shows them "BlockedBy" the failed row.
2. Exceptions: failed warm-up/test types are auto-Cancelled next cycle (so the chain continues); `cancel_on_fail` rows auto-Cancelled; types with `cancelOnFailure` config auto-Cancelled (→ next sibling runs). *Implication for triage: a Cancelled child with `canceled_by='auto'` was a failure.*
3. Operator choices: reschedule the failed row (Failure→Scheduled), Cancel it (block released → **the next sibling runs** — cancelling skips the step), CancelWorkflow (cancel it and all later siblings in the family), RestartWorkflow (re-run the whole family's children from the top).
4. The parent ProductRelease row is already `Success` from the moment it expanded (PreExecuteVisitor.java:2952-2953) — **parent status does not reflect children**. Use children (`parent_id`) to judge a deployment; REST `/check?key=` does exactly this (failed if any child failed; completed if all children Success/Cancelled).

---

## 3. Catalog of every ActionType

**Totals:** `ActionType.java:17-2285` has **441** constants (DB stores `name()`; no numeric id). All 441 have an `actions-config.xml` entry (missing entry would throw, ActionConfigHelper.java:321). **304** have an `actions.xml` template (305 names; `DbProductBackupOrig` X:590 is not a type); 137 are Java-handled.
Alias quirks: `BigQueryTransferJobsSetup`/`BigQueryTransferJobsOnDemand` dispatch `visitBqFilesToSync` (ActionType.java:161,166), `IamRedisCacheLoader` → `visitDSConfigRefresh` (:1961), `TestKiller` → `visitKillTestAction`: every visitor (args, model, Pre/Post/Ssh) treats them as the other type.

### 3.1 How templates work
- Selection: `Action.Factory.inst(ai)` looks up `actions.xml` `<action name="<ActionType.name()>">` (Action.java:25-37, cached parse). `<library>` blocks (actions.xml:2783-2810) are callable via `$util.call(...)`.
- Rendering: Apache Velocity (`Utils.evaluateVMTemplate`, ActionUtils.java:37). Variables: every public field of the type's `ActionArgs` class; `$util` (ActionHelper: product/family/account/host/id/ticketId/user, `getBranch()`, `getMainBranch()` (lit-XXXX→XXXX, master→trunk), `getProductTier()`, `getProductUrl()`, `isGit()`, `opsTool(cls,args)`, `createBug`, `sendEmail`, `ansibleCheckExitCode`, `gitPull`, `getJenkinsApiToken()`, `getGithubApiToken()`); `$action` (ActionInfo); `IActionModel` fields from `ActionModelVisitor` (e.g. `$zkClusterName`, `$backupName`, `$kafkaCluster`, `$revisionId/$branch/$repoDir`).
- Execution: blank lines dropped, trailing `\` joins; each line = one shell command (ActionUtils.java:43-69). The template, `cmdparams : {…}` map and rendered `CMD n $ …` list are written to the action log (:20, 36, 61).
- Validation (ActionSpec.java:191-222): in document order, `validate-txt` = AND(prev, contains), `or-validate-txt` = OR(prev, contains), `invalid-txt` = AND(prev, NOT contains); no elements ⇒ always Success ({} below). "contains" = substring on any line of `actionlogs/<id>.txt` (ValidateResponseTxt.java:19-32) — **that file also contains the template/rendered commands and every `(ssh) <cmd>` line**, so a validate string that appears in a command matches trivially.
- `actions-config.xml` controls: scope / hostResolveScope, visible/opsOnly/multiSelect, deferredExpand, execImmediately, serialize/serializeByUser/serializePerHost, blockIgnore, sync/syncChildren, changesDeployconf (→SvnRefreshScripts wait), updateBug*, workflowStatus, cancelChildren, allowKill, cancelOnFailure, cancelWorkflowOnFailure (unused), ticketRequiredForOps, accountFilter (substring match, ActionConfig.java:463), resolveHost, run-on-host, runOnDeployServer, runOnBks, ansible (InfoServlet summary), requires*, restrictStatusUpdate, tags (:828-863), docs (:864-1172).

### 3.2 Legend
Source: `X:n` actions.xml line; `S:n` SshExecuteVisitor; `P:n` PreExecuteVisitor; `C:n` CreateActionVisitor/CreateActionMacro; `Q:n` PreQueuedActionVisitor; `F` FindActions/ExplodeCmdHelper/DeployDaemonHelper. Validators: `v:` validate-txt, `o:` or-validate-txt, `i:` invalid-txt, `{}` none (always Success). Host: `T` = run-on-host tools-1..10 (DC) / gcptools; `TB` build tools; `DS` deployserver itself; `AI` AWS Insights host; `H` action's own instance host; `AnyA/AnyP` any host of account/product; `BKS` product backstage; `local` Java only. PR column: `Y <PreExecuteVisitor line>` = direct ProductRelease child; `DWP:n` = created by DeployWithParams per-host chain; `PR²` = grandchild created on insert by CreateActionVisitor; `alias` = rewritten into ProductRelease.
"ansible-actions" = `aa`/ansible-actions wrapper on tools hosts; "opstool" = `~/apps64/opstool` java CLI; "Rundeck" = opstool RundeckApiService; "GH Actions" = GitHub workflow dispatch curl.

### 3.3 Deploy
| Type | Purpose | Source | Host | Validators / verdict | Deps | PR |
|---|---|---|---|---|---|---|
| ProductRelease | master deploy workflow; expands to children | P:2692 | local | markDone Success (:2953) | deployconf | parent |
| ProductRefreshDeploy / ProductDeployNoBuild / ProductRefreshDeployUpgrade / ProductRestart | rewritten to ProductRelease with display_action | ProductReleaseConverter:102/116/125/91 | — | — | `newimpl.*` props | alias |
| ProductBuild | sync branches then `rebuild.py -rbsw -p <p> -f <f>` (`-M` on readonly/rorehearsal); C:943 adds ProductBuildStyleguide | X:1603 | TB round-robin | v:"BUILD SUCCESSFUL" | rebuild.py, sync_branches / opstool SvnSyncBranches | Y 2757 |
| ProductRebuild | staging rebuild chain (SolrRemove, CassandraRemove, CassandraRestoreVos, CassandraProductBackup, Consumer/Atm remove, ProductRelease, EnableRevisionDeletion, PB2restore; or DbCleanupLocalBackup if disabled) | P:651 | local | markDone | — | child of (Tier1)EnvironmentRebuild |
| ProductStop | legacy expand → HostStop per instance | F ExplodeCmdHelper:307 | — | — | — | N |
| ProductStopAll | HostStop for all T2 instances in allowed families | F DDH:396 | — | — | productStopAll* props | N |
| UpgradePatchProduct | deferred expand: HostStop, HostDeploy, ProductDBUpgrade, ProductPatch on first backstage | F / DeployUtils:637-650 | — | — | patch.py | N |
| SwitchToROMode / SwitchToLiveMode | ProductRelease with switchAccount | converter:134/141 | — | — | — | alias |
| HostDeploy | `rdply -n --no-styleguide -f <fam> --triggeredby --jira-ticket-id`; C:171 adds HostDeployStyleguide | S:404 | H | "Finished deploying product" and not "Java Result:" (SEV:397) | rdply | Y 2817 (cip), DWP:61 |
| HostDeployStyleguide | `deployStyleguide.py` | X:2005 | H | v:"Finished styleguide deployment" | ~/scripts | PR² CAV:186 |

### 3.4 Solr
| Type | Purpose | Source | Host | Validators | Deps | PR |
|---|---|---|---|---|---|---|
| SolrDeploy | `ansible-actions -s solr -a deploy` | X:1762 | T | v:"COMPLETED SUCCESS" | ansible-actions | Y 2770 |
| SolrStop | solr stop | X:1769 | T | same | same | N |
| SolrBackup | backup (+GCP upload); failure → SolrLockCleanup (PostEV:920) | X:1776 | T | same | same | N |
| SolrRemove | remove force | X:1783 | T | same | same | N |
| SolrRestore | restore `$backupName` (latest via TunnelHelper); failure → SolrLockCleanup | X:1797 | T | same | same | N |
| SolrRestoreLatest | restore latest-literatum; success (parent≠LTF) → SolrIndexSync | X:1804 | T | same | same | Y 2775 (only parent ProductRebuild + restoreSolr) |
| SetupSolr | deployconf `<solr>` edit + commit | P:2315 | local | markDone | deployconf git | N |
| SolrIndexSync | `backstage.sh index.sync` | X:1389 | BKS | v:"BUILD SUCCESSFUL" | backstage.sh | post-child |
| SolrRestart | solr restart | X:1343 | T | v:"COMPLETED SUCCESS" | ansible-actions | N |
| SolrLockCleanup | solr cleanup + consumer unpause | X:1746 | T | v:"COMPLETED SUCCESS" | same | post-child |
| ImmediateSolrBackup | backup, unpause, cleanup | X:1737 | T | v:"COMPLETED SUCCESS" (checked before last 2 cmds) | same | N |

### 3.5 Cip
| Type | Purpose | Source | Host | Validators | PR |
|---|---|---|---|---|---|
| CipProductAdd | deployconf+props add, Jira audit, chained children SvnRefreshScripts→CipProductCreateFS→SetupStyleguide?→CipDbProductRestore+ProductRefreshDeployUpgrade?→BuildDockerDatabaseImage(FromBackup)?→DbProductBackup?→CloudFlareRecordAdd | P:1626 | local | markDone | N |
| CipDomainFixup | gradle CreateCipDomain | X:113 | AnyP | v:"BUILD SUCCESSFUL" | PR² CAV:72 |
| CipProductCreateFS | create.publisher.cip + rsyncContent.sh | X:132 | AnyP | v:"Copied Successfully" | N |
| CipProductRemove | deployconf/props removal; PostEV SvnRefresh + CloudFlareRecordRemove | P:2239 | local | markDone | N |
| CipProductRemoveDbAndFs | cipRemoveDbAndFs.sh | X:142 | AnyP | v:"Removing FS" | N |
| CipProductTermination | macro: ProductStop, CipRemoveFileSystem, CipRemoveDeployedDirectory, CipRemoveBackstageLogs, DbContainerRemove/CipRemoveDatabase, SolrRemove, ProductConsumerRemove, CipProductRemove | C:1052 | — | — | N |
| CipExpiryCheck | lease expiry email/Jira | P:2172 | local | markDone | N |
| CipProductDbEdit | change LITERATUMDB name | P:100 | local | markDone only if modified | N |
| CipProductLeaseEdit | expiry/owner/comment | P:137 | local | markDone | N |
| CipDbProductRestore | macro: DbProductRestore → ProductCleanupPostClone | C:89 | — | — | N |
| CipGenerateProfile / CipRemoveProfile / CipRestartTraefik | ansible-traefik | X:982/991/1000 | AnyA | v:"COMPLETED SUCCESS" | N |
| CipLocalDbRestore / CipLocalTier1DbRestore | schemeRestore.sh (Tier1 fans out Q:154) | X:1164/1138 | AnyA | v:"finished successfully" | N |
| CipRemoveFileSystem / CipRemoveDeployedDirectory / CipRemoveBackstageLogs | CipRemove*.sh | X:148/155/162 | AnyP | v:"Removed successfully" o:"nothing to delete" | N |
| CipRemoveDatabase | CipRemoveDatabase.sh | X:169 | AnyP | v:"Db removed successfully" | N |
| CipCleanupLocalDbBackup | cleanupBackupAndDatabaseOnDevDBServer.sh | X:2220 | AnyA | v:"Cleanup Database on Dev DB completed successfully" | N |
| CipLocalDBIndividualExpiryCheck / CipLocalReportDBIndividualExpiryCheck | email/Jira | P:1996/1930 | local | markDone | N |
| CipLocalDBIndividualRemove / CipLocalReportDBIndividualRemove | deployconf removal; PostEV → *RemoveProcess | P:2063/2099 | local | markDone | N |
| CipLocalDBIndividualRemoveProcess / CipLocalReportDBIndividualRemoveProcess | cleanupBackupAndDatabaseOnDevDBServer.sh -i/-R | X:1838/1846 | AnyA | v:"Cleanup Database on Dev DB completed successfully" | N |
| CipLocalRestoreIndividualDBProcess / …ReportDBProcess | schemeRestore.sh -i/-R | X:1824/1831 | AnyA | v:"database finished successfully" / v:"finished successfully" | N |
| CipLocalDBIndividualRestore / CipLocalReportDBIndividualRestore | **no handler → always Cancelled**, so PostEV (Success-only) never chains the Process child | — | — | Cancelled | N |
| CipLocalDBIndividualLeaseEdit / CipLocalReportDBIndividualLeaseEdit | **no handler → Cancelled** | — | — | Cancelled | N |
| CallCipLocalReportDBIndividualRestoreOnCip | REST `/run` relay to CIP DS | P:2135 | local | markDone on HTTP 200 | N |
| CallDbCleanupLocalBackupOnFTPOnMainDS / CallDbReportCleanupLocalBackupOnFTPOnMainDS | REST relay to main DS | P:1334/1301 | local | markDone on 200 | N |
| CallDbCleanupLocalBackupOnCip | **no handler → Cancelled** | — | — | — | N |
| DbCleanupLocalBackup | macro: DbCleanupLocalBackupOnFTP → CallDbCleanupLocalBackupOnCip | C:460 | — | — | N |
| DbCleanupLocalBackupOnFTP / DbReportCleanupLocalBackupOnFTP | cleanupBackupOnFTP.sh | X:2200/2212 | AnyP | v:"Cleanup backup on FTP completed successfully" | N |
| CleanupLocalOrphanDbs | echoes its own validate string | X:2232 | AnyA | v:"Cleanup Database on Dev DB completed successfully" (always true) | N |

### 3.6 Gaia / GCP / Tools / Test
| Type | Purpose | Source | Host | Validators | PR |
|---|---|---|---|---|---|
| GaiaDeploy | DC: ansible-actions; else Rundeck via opstool | X:1188 | T | v:"gaiadeploy execution success" o:"COMPLETED SUCCESS" | Y 2797 (not readonly/rorehearsal) |
| GaiaBuild | Rundeck | X:1361 | AnyA | v:"gaiabuild execution success" | N |
| GaiaProductSetAxelVersion | deployconf bundle_version; PostEV ConsulPopulate→GaiaDeploy | P:2539 | local | markDone | N |
| GaiaGenerateProfile | ansible-traefik gaia_cluster | X:1703 | AnyA | v:"COMPLETED SUCCESS" | N |
| GaiaClusterDeploy / GaiaFeTagRelease / DestroyGaiaCluster | Rundeck | X:1350/1455/1644 | AnyP/AnyA | v:"gaia cluster deploy execution success"/"gaiadeploy execution success"/"gaiadestroy execution success" | N |
| GaiaDC | ansible-actions gaia `-a ${at}` | X:1679 | T | v:"COMPLETED SUCCESS" | N |
| GaiaCompatibilityCheck | compare bundle+image tag with staging | P:3137 | local | markDone (Cancelled if pre-prod / no gaia) | Y 2751 (literatum, not RO switch, display null/ProductRefreshDeploy) |
| CheckGaiaVersion | compare bundle_version with staging | S:1315 | AnyP | match/skip lines | N |
| ChangeGaiaVersion | opstool ChangeGaiaVersion, git commit/push (no cd) | X:2762 | AnyA | {} | N |
| AxelVersionAutomationWorkflow | commit Axel version on midtierbeta | P:2554 | local | markDone | N |
| GCPProdStatusInquiry / GCPProdDeploy / GCPProdDestroy / GCPVmAction / GCPProdAction | `terraform-infra/deploy_dr.sh -a …` | X:459/470/481/492/503 | gcptools | v:"INFO : succeed" | N |
| ToolAnnounceMinorRelease | ~12 Jira tickets, psql, CodeFreeze email; PostEV future MergeFreezeAnnouncement | X:85 | DS | {} | N |
| ToolMajorReleaseCreateTickets | ~70 Jira tickets | X:6 | AnyA | {} | N |
| ToolCheckBackstageStuck | opstool CheckBackstageStuck | X:724 | AnyA | {} | N |
| ToolOpstoolInstall | build_opstool.sh -r (CIP fan-out Q:364) | X:1818 | tools-5 | v:"Finished Successfully" | N |
| ToolOpstoolInstallAcbuild | fan-out to build hosts; host list empty → no-op | C:259 | — | — | N |
| ToolMarlinSingleCert | MarlinUnionDomains | X:1989 | AnyP | {} | post-child of ProductCleanupPostClone (marlin) |
| RunImageOptimizerTool | image_optimizer.sh | X:976 | AnyP | v:"Finished at" | N |
| HostExtraTest | macro: HostWarmupContent / HostTestJane (row itself not inserted) | C:1405 | — | — | Y DWP:78 |
| HostWarmupTest | `host_test.py -t warmup` (docker); +HostEssentialTest on literatum/readonly non-preprod | S:485/843, C:130 | H | log "***Test Is Succeeded***" (collect phase) | Y DWP:77 |
| HostEssentialTest | `host_test.py -t essential`, Allure zip | S:491 | H | "***Test Is Succeeded/Failed***" | PR² CAV:143 |
| HostTestJane | marlin JaneTestDriver | S:869 | H | report.csv no "FAILED" | PR² |
| HostWarmupContent | opstool HitUrlsCli/DeployTestDriver warmup | S:499 | H | always Success | PR² |
| HostTest | host_test.py -t <group> | S:503 | H | "***Test Is Succeeded***" | N |
| Test | opstool DeployTestDriver selenium; cancel_on_fail forced | S:478 | H | testresult.html "<h5>100%" | N |
| TestAsync | chain HostWarmupTest, HostWarmupContent?, HostTestJane?, HostUnlock | P:2519 | local | markDone | N (REST /unlock) |
| TestKiller / NonVisualRegressionTestKiller | kill -9 | X:833/839 | H / DS | {} | N |
| MarlinJaneTest | JaneTestDriver | S:897 | AnyA | report.csv | N |
| TestGroup / TestEssentialGroup | macro: Test / HostEssentialTest per product | C:1202/1234 | — | — | N |
| NonVisualRegressionTest | opstool Jenkins NonVisualRegressionTest (token on cmdline) | S:509 | AnyP | "pass completely" else Cancelled; PostEV skipped | N |
| VictorFIntegrationTests | empty body | S:560 | — | always Cancelled | N |
| QaaIntegrationTests | GH Actions qa-automation-lit | X:1754 | AnyP | v:"http_status=200" o:201 o:204 | spawned by GatherFacts |
| GatherFactsForJenkinsJob | RegistryQueryCli passport/enabled → QaaIntegrationTests | S:548 | H | "system:" (always Success) | spawned by HostUnlock (cip QAA) |
| SiteMobileRegression / SiteVisualRegression / SitePerformanceTest | GH Actions qa-automation-xml | X:229/1498/268 | AnyP | v:"http_status=200" o:201 o:204 | SitePerformanceTest Y 2904 |
| SiteRegressionInteg | GH Actions (runOnGA forced for PR children) or Jenkins | X:208 | AnyP | same | Y 2898 |
| SdApiTest | Jenkins SD_API_Tests | X:548 | AnyP | v:"http_status=200" o:201 | Y 2929 |
| RunLocustTests | ltf ansible-playbook | X:1506 | T | v:"COMPLETED SUCCESS" | N |
| JenkinsTestypon | testypon_jenkins.sh | X:350 | DS | v:"task finished successfully" | N |
| DependencyReportChecker | `echo "skip"` | X:1712 | web host | {} | Y 2920 (cip qaa) |

### 3.7 Host / product lifecycle (untagged)
| Type | Purpose | Source | Host | Verdict | PR |
|---|---|---|---|---|---|
| HostLockStop | macro chain HostLock → Pause1Min → HostStop (row not inserted) | C:78 | — | — | Y DWP:56 (web) |
| HostLock | opstool DeployFamilyAction -t lock | X:1462 | H | {} | PR² |
| HostStop | `setprod p f; rstrt -w/-R/-b/-o/-M -q --triggeredby --jira-ticket-id` | S:104 | H | "stopped -server"/"killing pid"/"do nothing"/"Stopping process backoffice"/(backstage) "Restart:" | Y 2816, DWP:56 |
| HostStart | `rstrt -s; rstrt -r -w/-R/-b/-o/-M [+debug port][qaa flag]; rstrt -s`; C:160 adds HostWaitForWebServer | S:135 | H | "process is running" (cip: BackstageQserverMode/Backoffice…is running); line starting "err.DeployErr" = Failure | Y DWP:76/81 |
| HostRestart | ProductRelease limitToHost, no build/patch/deploy | converter:148 | — | — | alias |
| HostWaitForWebServer | sleep webserverCheckFreq, opstool `-t serverup` | S:81 | H | "RESULT:SUCCESS"; Scheduled until timeout | PR² |
| HostWaitForHearbeat | opstool `-t lock` | S:88 | H | "RESULT:SUCCESS", poll | N |
| HostUnlock | opstool `-t unlock -p` | S:93 | H | "RESULT:SUCCESS"; cip QAA → GatherFactsForJenkinsJob | Y DWP:79 |
| ProductPatch | `patch.py -p <p> --families <f> [--allowdropcolumn][--gradle]`; docker DB → `ansible-actions -s mssql … start-patch-backup` | S:429 | H (backstage only — DeployUtils.java:368) | lines starting "BUILD " SUCCESSFUL, or "failed=0" (docker); failure w/ "PatchProgram … failed to execute" → BrokenPatchBlame child | Y DWP:66 |
| ProductDBUpgrade | `patch.py … -u <main> --gradle` | X:899 | H | v:"Patch complete." | Y 2878 (patchUpgrade) |
| BrokenPatchBlame | git log of patch file on literatum-patch → email/Jira | S:1176 | DS | always Success | child of ProductPatch |
| ProductStart | legacy HostStart per instance | F ExplodeCmdHelper:311 | — | — | N |
| AllStopBackstages / AllStartBackstages | HostStop/HostStart per backstage | F :422/451 | — | — | N |
| FullGC / KillJDBCConnections | reinitializeConnPool.sh | X:122/127 | H | {} | N |
| LiteratumQuarantine | macro HostLock, Pause1Min, FullGC, KillJDBCConnections, HostUnlock | C:1147 | — | — | N |
| LiteratumQuarantineEnable/Disable, AutoRestartEnable/Disable | autoRestartToggleSwitch.sh | X:396/389, X:362/380 | AnyP | v:"task finished successfully" i:"task finished unsuccessfully" | N |
| Pause | blocks all later actions in the account until cancelled | — | — | never runs | N |
| Pause1Min / Pause10Min / Pause30Min | sleep | X:1570/1558/1450 | — | {} | PR² / Y 2895,2918 / (EnvironmentRebuild) |
| EnableArgoTunnel | enable_argo_tunnel.sh | X:1575 | H | {} | N |
| PyroscopeProfile | pyroscopeProfile.sh | X:2811 | H | v:"PROFILING_TRIGGERED" i:"ERROR:" | N |
| RunCLI | `run-cli.sh "$command"` (arbitrary) | X:693 | BKS/any | v:"BUILD SUCCESSFUL" | PR² (canary) |
| RunJavaCodeOnAll | run tool crossSiteCodeExecutor | X:1551 | AnyP | v:"Execution is done successfully" | N |
| RunPuppet | sudo puppetagent.sh | X:1254 | args.host | v:"Ran successfully" | N |
| CanaryDeployment | ProductRelease canaryHosts/duration | converter:159 | — | — | alias |
| CreateEphemeralLiteratumRoute / DeleteEphemeralLiteratumRoute | macro RunCLI manageArgoTunnelSecondaryDomain + ConfigureEphemeralLitRoute (+HostRestart top-level) | C:258/311 | — | — | Create Y 2860 (canary) |
| ConfigureEphemeralLitRoute | scripts/tf_argo_tunnel.sh (terraform, -auto-approve); PostEV future Delete | X:1292 | DS | v:"Apply complete!" o:"Destroy complete!" | PR² |
| Create/DeleteArgoTunnelSecondaryDomain | run tool manageArgoTunnelSecondaryDomain | X:1300/1311 | H | v:"Done" | N |
| EnvironmentRebuild | PB2backup, DisableRevisionDeletion, Pause30Min, ProductStop, DbAndFsFlexClone, ConfigEditBranches, ConfigRefreshDeploy, KafkaRestart, ProductRebuild | P:248 | local | markDone first | N |
| Tier1EnvironmentRebuild | HostStop, PB2backup, DbAndFsFlexClone, ConfigEditBranches, ConfigRefreshDeploy, CfVideosCleanup, ProductRebuild | P:442 | local | markDone first | N |
| MajorReleaseUpgrade | HostStop non-web, DbAndFsFlexClone on readonly, ProductUpgrade | P:1021 | local | markDone | N |
| ProductUpgrade | SwitchToROMode, SolrRemove, ConsumerRemove, SolrDeploy, SolrRestore, UpgradePatchProduct, HostStart | P:1116 | — | **no markDone → parent ends Cancelled** | N |
| ProductTermination | HostStop, DbAndFsFlexClone RemoveOnly?, SolrRemove, ConsumerRemove, AtmRemove, RemoveDeployedDirectory, StopDisableProducts | P:1196 | — | **no markDone → Cancelled** | N |
| StopDisableProducts | HostStop per host → DisableExecludedProducts | P:196 | — | no markDone → Cancelled | N |
| DisableExecludedProducts / EnableProducts | flip deployconf `enabled` in PreQueued | Q:237/289 | — | ends Cancelled | N |
| RemoveDeployedDirectory | CipRemoveDeployedDirectory.sh | X:1563 | AnyP | v:"Removed successfully" o:"nothing to delete" | N |
| AddNonWebInstance | add_remove_Non_web_instance.py -a add; rewrites host of sibling rows / adds ConfigRefreshDeploy | S:389 | AnyP | "The rbackstage server[...]"; any "ERROR"/"error" = Failure | N |
| LeanDashboardVersionVerifier | compare prod vs staging lean version | P:1479 | local | markDone | Y 2754 |
| UpdateActionParams | **raw `UPDATE deploy_action SET … WHERE <user text>`** | P:1508 | local | markDone | N |
| UpdateRecorderTag | edit+commit deployserver.properties recorder tag | S:1386 | DS | "replaced with new inject" | N |
| UpdateYaegerVersion | updateYaegerOnLiteratumBranches.sh | S:410 | T | **always Cancelled** (no parser) | N |
| RBookTool | Jira tickets from RBookToolJira.xml | P:3040 | local | markDone | N |
| DevProductRunOptions | deployconf debug attr | P:175 | local | markDone | N |
| RefreshDbDashboard | DbOfficesService refresh | P:1779 | local | markDone Failure then Success (bug) | N |

### 3.8 Database / PB2 / Cassandra / Xse / services
| Type | Purpose | Source | Host | Validators | PR |
|---|---|---|---|---|---|
| DbFlexClone | do_kill.sh? + do_dbflexclone.sh; PostEV DbCleanupPostClone (unless RemoveOnly) | X:845 | T | v:"Congratulations!" | N |
| DbArchiveFlexClone / DbReportFlexClone | do_dbflexclone.sh | X:854/860 | AnyA | v:"Congratulations!" | N |
| DbAndFsFlexClone | children DbFlexClone (or DbClone if byteClone) then FsFlexClone | P:566 | local | markDone | N |
| FsFlexClone | macro ProductFlexClone per volume | C:1330 | — | — | N |
| ProductFlexClone | sudo /root/ansible-fc/fc.py (Q fan-out per volume) | X:1467 | T | v:"COMPLETED SUCCESS" | N |
| ListProductClones | fc.py -a fc-date | X:335 | AnyP | v:"COMPLETED SUCCESS" | N |
| DbClone | deferred: DbCloneBackup→Copy→Restore→DbCleanupPostClone | F DDH:329 | — | — | N |
| DbCloneBackup/Copy/Restore/Remove | do_clone.sh -o backup_only/copy_only/restore_only/remove_only | S:1138/1113/1118/1123 | T | "Backup was done successfully"/"Copy Was successful"/"RESTORE DATABASE successfully processed"/"REMOVE_DataBase has done successfully" | N |
| DbCleanupPostClone | deferred ProductCleanupPostClone per product | F DDH:355 | — | — | N |
| ProductCleanupPostClone | opstool ExecSqlCli/TruncateTableCli with deployconf DB creds; mms password reset (<secret at S/server/visitor/SshExecuteVisitor.java:978-979>) | S:951 | AnyP | "ExecSQL SUCCESS" and no SQLException; auto-retry ×2 | N |
| DbOptimize | macro HostStop backstages→self→HostStart; do_optimize.sh | C:67+S:1128 | T | "DB optimization completed successfully" | N |
| DbProductBackup | schemeBackup.sh (Cancelled on literatum) | X:559 | T | v:"finished successfully" | N |
| DbReportProductBackup | schemeBackup.sh -R; PostEV CallCipLocalReport…OnCip | X:582 | T | v:"database finished successfully" | N |
| DbProductRestore | schemeCloneRestore.sh / tier1flexClone.sh -c | X:191 | AnyP | v:"Restoring database finished successfully" | N |
| LocalDbCloneAndRestore | schemeCloneRestore.sh / tier1flexClone.sh (Cancelled on literatum) | X:287 | T | v:"Restoring database finished successfully" | Y 2925 (runDbBackup) |
| LocalAndCipT1DbRemove | tier1flexClone.sh -r | X:314 | T | v:"Database removal finished successfully" | N |
| DbContainerRemove | ansible-actions mssql remove | X:1790 | T | v:"COMPLETED SUCCESS" | N |
| DbAdminsList | sql-audit SQLscript.sh | X:540 | T | v:"" (always true) | N |
| DbIdxReportsCollector | opstool DbIdxCollector | X:1588 | AnyA | v:"Finished successfully" | N |
| GenerateDbIndexReport | `dbidx` with DB password on cmdline | S:1280 | AnyP | "DBIDX: Run successfully"; retry | N |
| SqlPatchCheck | checkSqlPatchStatement.sh | X:1175 | AnyA | v:"finished successfully" | N |
| CreateDockerDatabase | deployconf DB server; PostEV SvnRefresh→BuildDockerDatabaseImage | P:2342 | local | markDone | N |
| BuildDockerDatabaseImage / …FromBackup / UpdateDockerDatabaseFromBackup | build_docker_db_wrapper.sh | X:802/813/820 | AnyA/P | v:"DONE SUCCESSFULLY" | N |
| UpgradeDockerDatabase / UpdateProductDockerDatabaseFromBackup | deployconf rename / HostStop+Update+ProductRelease | P:1875/1794 | local | markDone | N |
| UpdateDockerProductDomain | docker exec sqlcmd -P '$dbPass' (password in log) | X:827 | AnyP | v:"rows affected" | N |
| PB2backup / PB2restore / PB2restoreLast | BackupPB.sh / RestorePB.sh | X:735/741/747 | — | v:"Backup has been successfully done" / v:"Restore has been successfully done" | N (rebuild children) |
| CassandraDeploy/Stop/Start/Restart/Remove/RestoreVos/BackupVos | ansible-actions cassandra | X:1009/1023/1030/1037/1044/1051/1095 | T | v:"COMPLETED SUCCESS" | N |
| CassandraProductBackup / CassandraProductRestore | cassandraBackup.sh / cassandraRestore.sh (Q fan-out) | X:1069/1062 | T/AnyA | v:"Cassandra finished successfully" | N |
| XseDeploy/Restart/Backup/Restore/Remove/CreateIndex | ansible-actions xse | X:920/927/934/941/948/955 | T | v:"COMPLETED SUCCESS" | XseDeploy Y 2793 |
| ProductConsumerDeploy / ProductConsumerRemove | ansible consumer | X:2100/2107 | T | v:"COMPLETED SUCCESS" | Deploy Y 2780 |
| SetupConsumer | deployconf `<consumer>` | P:2361 | local | markDone | N |
| ProductAtmDeploy / ProductAtmRemove | ansible atm | X:969/1443 | T | v:"COMPLETED SUCCESS" | Deploy Y 2784 |
| AtmTrainingProduct / AtmTraining | macro AddNonWebInstance+AtmTraining / AutomateATM.sh | C:977 / X:2129 | — / AnyP | — / v:"ATM has been finished successfully" | N |
| ProductIngestionDeploy | ansible ingestion | X:1216 | T | v:"COMPLETED SUCCESS" | Y 2788 |
| SearchServiceDeploy | ansible searchservice | X:962 | T | v:"COMPLETED SUCCESS" | Y 2772 |
| SetupSearchService / RemoveSearchService | deployconf `<searchservice>` | P:1581/1604 | local | markDone | N |
| LTF | Setup/RemoveSearchService, ConfigRefreshDeploy, SearchServiceDeploy, SolrDeploy, HostDeploy per web, SolrRestoreLatest, RunLocustTests | P:1366 | local | markDone | N |
| PugrendererClusterDeploy / PugrendererProductDeploy | ansible pugrenderer | X:2115/2122 | T | v:"COMPLETED SUCCESS" | Product Y 2802/2804 |
| PugrendererInvalidateCache / CfInvalidateCache | ansible invalidatecaches / InvalidateCloudflareCache.py | X:403/410 | T/AnyP | v:"COMPLETED SUCCESS" / v:"Finished Invalidating Cloudflare Cache" | Y 2908/2909 |
| K8sPugrendererDeploy / Destroy / Build | Rundeck | X:1368/1375/1382 | AnyP | v:"<Name> execution success" | Deploy Y 2808 |
| InjectUIWidgets | ansible pugrenderer inject_widgets | X:1730 | T | v:"COMPLETED SUCCESS" | N |
| SgBranchesCleanup | aa pugrenderer cleanup_styleguide | X:452 | AnyA | v:"COMPLETED SUCCESS" | N |
| RedisDeploy / RedisRestart | ansible redis | X:906/913 | T | v:"COMPLETED SUCCESS" | N |
| IamRedisCacheLoader | pericles_culp_resync.sh (dispatch alias bug) | X:1927 | AnyA | {} | N |
| ZkDeploy | ansible zookeeper | X:1811 | T | v:"COMPLETED SUCCESS" | N |
| KafkaRestart / KafkaClusterDeploy | aa kafka / ansible kafka | X:1532/2769 | AnyA/T | v:"COMPLETED SUCCESS" | N |
| MuleStart / MuleStop | gomule; bin/activemq start/stop (copy-paste) | X:881/887 | — | {} | N |
| ActiveMQStart / ActiveMQStop | activemq | X:869/875 | — | {} | N |
| SetupMongoDb | deployconf `<mongodb>` | P:3007 | local | markDone | N |
| ProxyBuild / ProxyConfigRefresh / ProxyMDDeploy / ProxyMDFullDeploy / ProxyMDStart / ProxyMDStop | proxy shell functions (MD* fan-out per host Q:340) | X:1854/1860/1865/1870/1879/1884 | — | Build/FullDeploy v:"BUILD SUCCESSFUL", others {} | N |
| ProxySolrDeploy | ansible proxysolr | X:1016 | T | v:"COMPLETED SUCCESS" | N |
| ElkFilebeatDeploy / ElkKibanaBackup / ElkLogstashDeploy / ElkRotateIndices | ansible elk | X:1110/1117/1124/1131 | — | v:"COMPLETED SUCCESS" | N |
| AuditDeploy / Destroy / Backup / Restore | Rundeck | X:1651/1658/1665/1672 | — | v:"COMPLETED SUCCESS" | N |
| MountFS | Rundeck | X:1181 | AnyA | v:"MountFS execution success" | N |
| UpdateStatusPage | ansible status-page / Rundeck | X:237 | T | v:"COMPLETED SUCCESS" | N |
| AnalyticsSyncEvents | ansible analytics_events | X:893 | AnyA | {} | N |

### 3.9 Config / VCS / Release / Reprocess / Alerts / Styleguide / Utility
| Type | Purpose | Source | Host | Validators | PR |
|---|---|---|---|---|---|
| ProductChangeBranch | cd ~/.litconfig; git reset/clean/pull; opstool ChangeProductBranch; git commit+push deployconf; success → immediate ConfigRefreshDeploy | S:1034 | — | "error: "/"fatal: " = Failure | N |
| ConfigEditBranches | same per product + scp ~/deployconf.xml back | S:1061 | — | same (empty list → Success) | EnvironmentRebuild children |
| ConfigRefreshDeploy | local SyncDeployConf + Success (never SSH) | Q:50 | local | — | many |
| CloneProductBranch | opstool ChangeProductBranch across accounts | X:1539 | DS | i:"error: " | N |
| SvnRefreshScripts | git reset/pull ~/.litconfig & ~/scripts; ansible over CIP hosts | X:175 | AnyA | {} | auto-created wait_for for changesDeployconf actions |
| DeployConfValidation | deployConfValidation.sh | X:2146 | AnyA | v:"Validation has been completed" | N |
| DSBuild / DSConfigRefresh | ant bundle / copy config into ~/deployserver/config | X:1906/1889 | DS | v:"BUILD SUCCESSFUL" / {} | N |
| GitMergeRequest | record MR (Success), Jira table | C:728-817 | local | — | N |
| GitMerge | macro one child per revision; child scripts/gitMerge.sh | X:2186 (+explode) | DS | v:"MERGE SUCCESS" | N |
| GitMergeRev | gitMerge.sh $branch $revision | X:1697 | DS | v:"MERGE SUCCESS" (failure later turned Cancelled by JiraHelper) | N |
| DryMerge | gitDryMerge.sh (psql updates revisions) | X:1396 | DS | v:"Simulation finished, reverting changes" | N |
| GitBranchCreate | scripts/gitBranchCreate.sh / handle_cms_cut_branch.sh; PostEV fan-out (UpdateAtyponLifecycle, AddBranchToRelease, CallUpdateQAANewBranchOnCip, SetPatchRelease, MajorUpdateLiteratumProps, CreatePatchPlan, Jenkins jobs…) | X:2026 | DS | v:"Done successfully" | N |
| GitBranchRemove | scripts/gitRemoveBranch.sh | X:1104 | DS | v:"Branch removed successfully" | N |
| UpdateAtyponLifecycle / AddBranchToRelease | updateMjrBranchesList.sh / psql insert release_branch | X:1686/1692 | AnyA/DS | v:"Updated MJR_BRANCHES_LIST" / {} | GitBranchCreate post |
| SetPatchRelease / MajorUpdateLiteratumProps / CreatePatchPlan | major_upgrade_post_actions.sh ($releaseNum never set → bug) | X:1223/1229/1235 | tools-11..13 | v:"COMPLETED SUCCESS" | GitBranchCreate post |
| CreateCmsJenkinsPipelineFromTemplate / CheckoutMajorBranchByJenkins / TriggerRootPomReleaseJenkinsJob / CreateCmsReleaseByJenkins | handle_cms_jenkins.sh / checkoutMajorBranchByJenkins.sh / handleRootPomReleaseJenkins.sh | X:2043/2063/2069/2075 | DS | v:"Done successfully" | GitBranchCreate post |
| CreateJenkinsPipeline / BuildLeanWorkflow | Jenkins curl (token on cmdline) | S:524 / X:445 | AnyA | "Created new job build" / v:"http_status=200" o:201 | N |
| CallUpdateQAANewBranchOnCip / UpdateQAANewBranch / UpgradeQAAProduct | REST relay / macros | S:1007 / C:482 / C:632 | DS | count "response_code: 200" | N |
| SyncGitWithSvn / SyncWebdavSaml | svn_to_git_setup.sh / webdav_dr_saml_sync.sh | X:1718/1724 | DS/AnyA | {} / v:"All syncs completed at " | N |
| MissingMerges / CollectMissingTickets | MissingMergeDetector.py / missingMrMerges.sh | X:2742/1402 | AnyA/DS | v:"Done successfully" / v:"DONE" | N |
| AddGitbotFeature | addGitbotFeature.py | X:2776 | DS | {} | N |
| RevisionReporter | opstool revision_reporters | S:1501 | T | "Report generated successfully"/"Build Successfully" | N |
| CreateRelease / DeleteRelease / CollectRevisions / ExportRelease / GenerateReleaseNotes / ArchiveRelease | release table / dashboard / mr-archive commits (GenerateReleaseNotes returns without markDone if no tickets) | P:893/937/814/946/820 / C:1364 | local/DS | markDone | N |
| MergeFreezeAnnouncement | $util.sendEmail | X:1490 | DS | v:"Email Sent" (always) | N |
| ReprocessProduct / CustomReprocessProduct / PassportReprocessing | macros (AddNonWebInstance, ConfigRefreshDeploy, HostDeploy, HostStart, Submit, Check, Finalize, ConfigRefreshDeploy) | C:888 / C:123+X:1941 / C:1265 | — | Custom: v:"CustomReprocess done successfully" | N |
| SubmitReprocess / CheckReprocess | submit_reprocess.sh / check_reprocess.sh | S:329/364 | BKS/new rbackstage | "Submitting is done." / success lines + retry | N |
| FinalizeReprocess | rstrt -q + remove non-web instance | X:1950 | — | v:"Removing the rbackstage done successfully" | N |
| SubmitPassportReprocess / CheckPassportReprocess / DigitalObjectReprocess / PassportDigitalObjectReprocess | passport_content_reprocess.sh / digital_object_reprocess.sh | S:204/240/273/295 | BKS | BUILD SUCCESSFUL/FAILED (+retry) | N |
| ReportEscapedRevisions | escaped_revisions_cron.sh | X:1933 | BKS | v:"ReportEscapedRevisions done successfully" | N |
| AlertInternalEnable / AlertExternalEnable / AlertExternalDisable / AlertInternalDisable | EmailAlertStarter.sh / pingdomApi.sh+catchpointApi.py | X:780/772/787/795 | — | v:"unpausing" / "pausing" | N |
| ProductAlertsSilence / MultiTenantAlertsSilence / DbAlertsSilence / DockerAlertsSilence | alertManagerSilencer.py | X:416/422/428/438 | — | v:"Alert silencer finished successfully" | N |
| PagerDutyShifts | pd_shift.py | X:1205 | AnyA | v:"Successfully created" | N |
| SetupStyleguide | deployconf `<styleguide>` | P:2279 | local | markDone | N |
| CheckStyleguideMaintBranches / GenerateStyleguidePackage / StyleguideTemplateUpdate | gitBranchCheck.sh / packageStyleguide.py / styleGuideUpdate.sh | X:719/2192/713 | AnyA/DS/AnyA | {} / v:"package has been pushed to Styleguide S3 successfully" / v:"Finished correctly" | N |
| ProductBuildStyleguide | Build-Deploy-Styleguide.sh | X:2013 | TB | v:"BUILD COMPLETED" | PR² C:966 |
| CreateNewEmployee / CreateNewEmployeeNew / DeleteEmployee | run tool createNewEmployee / deleteEmployee per product | X:632 (C:844, C:1019) / X:681 | AnyP | v:"BUILD SUCCESSFUL" | N |
| CreateInfraNewEmployee / DeleteInfraNewEmployee | infrauto do_createnewemployee.sh (<secret at config/actions.xml:669>, <secret at config/actions.xml:676>); PostEV emails password, REA/LIT tickets | X:667/674 | DS | v:"Operation was done successfully" | N |
| GrantIndividualPermission / AddToPermissionGroup / RevokeDsPermissions | appendToPermissionFile.sh / updateDsConfFile.sh / revokeDsPerm.sh | X:706/528/534 | DS | v:"Successfully injected permission file" / "Successfully injected the change" / "Permissions were revoked" | N |
| DeleteUserHomeDir | mv /home/$username | X:1336 | tools-1 | v:"COMPLETED SUCCESS" | N |
| SftpAccountSettings | `sudo $cmd` (user supplied) | X:369 | T | v:"COMPLETED SUCCESS" | N |
| ValidateWebOnROMode | ValidateReadOnly | X:1918 | H | v:"Is ReadOnly: Yes" | PR² (readonly HostUnlock) |
| HttpsSwitcher | httpsSwitcher.sh | X:700 | — | {} | N |
| WorkFlowSetter / DtsGetter / DtsSetter | backstage.sh / dtsGetter.sh / dtsSetter.sh | X:753/760/766 | AnyP | v:"has been updated to new value" / "disabling the DTS for" / "BUILD SUCCESSFUL" | N |
| SiteConfigBackup / SiteConfigRestore | run tool backUp/restoreSiteConfig (Velocity `if (` bug) | X:2135/2176 | AnyP | v:"The xml config for all sites are backedup succussfully" / {} | N |
| GatherProductWidgets / AnalyzeWidgets | widget scripts | X:343/356 | AnyP | v:"Product csv file created" / "Excel Sheet Created" | N |
| CfVideosCleanup | stream_bulk_delete.py --access-token $token | X:1408 | AnyP | v:"Videos cleanup Completed" | Tier1 rebuild child |
| EnableRevisionDeletion / DisableRevisionDeletion | bridgeRevisionRemovalController | X:1421/1432 | AnyP | v:"Enable/Disable process completed successfully" | rebuild children |
| VideoCodec / ReportUserPermission / GenerateSmartExpansions / HBSDetector / VIndex | scripts | X:261/280/1521/1595/1241 | AnyP/BKS | "Task finished successfully" / "BUILD SUCCESSFUL" / "BUILD SUCCESSFUL" / "EXECUTION SUCCESS" o:"File is empty or contains Headers row only" / "Ran successfully" | N |
| LBPoolConfig | sudo /root/lb/do_managelbpools.sh | X:518 | prod102 | v:"INFO : succeed" | N |
| FirewallsReport / ReloadSamlData / InstallSamlData / LiteratumPropsChange | scripts | X:1478/1484/1630/1077 | AnyA/AnyP/tools-9 | "Report generated" / "Done successfully" / "Workflow finished successfully" | N |
| CloudFlareRecordAdd / CloudFlareRecordRemove | cloudflare-dns.sh | X:2152/2158 | DS | v:"DNS record added/deleted successfully" | CipProductAdd/Remove children |
| CheckWebsiteAdminConfig / CheckConfGets | checkWebSiteAdminConfig.sh | X:2164/2170 | AnyP | v:"BUILD SUCCESSFUL" | N |
| CloudflareVideoAnalytics / CloudflareVideosData | python --key $key | X:2748/2755 | AnyP | v:"Result generated under" | N |
| CreateDevVM / DestroyDevVm | macros ConfigureCfZt+PrepareVM / DestroyVm+ConfigureCfZt | C:173/218 | — | — | N |
| PrepareVM / DestroyVm / RestartDevVm / ConfigureCfZt | scripts/tf_vm_ops.sh / tf_cf_zt.sh (terraform -auto-approve, Proxmox API) | X:1267/1322/1329/1284 | DS | "Apply complete!" / "Destroy complete!" / "Reboot task submitted" | N |

### 3.10 Insights (tag `Insights`, `Insights-CLI`, and untagged ETL; nearly all on AI/ta1, execImmediately+blockIgnore)
| Type(s) | Source | Validators |
|---|---|---|
| InsightsTest (generateTets.py, scp to acdeploy) | X:2279 | i:"cannot scp. TEST_FAILURE" |
| InsightsTestDeploy | X:2385 | {} |
| InsightsSanityTestRun | X:2354 | i:"cannot stat ?testresult.htm?: No such file or directory" (literal ?) |
| InsightsSanityTestBatchRun / BatchSummary | X:2324/2348 | v:"Spreadsheet updating completed" / "Summary Spreadsheet updating completed" |
| InsightsSanityTestDeploy (token clone <secret at config/actions.xml:2320>) | X:2318 | i:"fatal: Could not read from remote repository." |
| InsightsS3Download / S3DownloadCleanup / InitDb / ProcessEvents / S3Upload / LoadDb | X:2391/2436/2424/2407/2442/2454 | {} |
| InsightsS3ToDbMacro | C:83 | — |
| addInsightsPremiumClient / addInsightsStandardClient (<secret at config/actions.xml:2519-2521,2528-2530>) | X:2526/2517 | v:"Adding New Insights Client Completed..." |
| AclBqProduct / AclCloudSqlIP (pulumi; <secret at config/actions.xml:2300,2310>) | X:2298/2308 | i:"error" |
| DynamoDbRefreshDatasets / DynamoDbRefreshCache / DynamoUpgradeToPremium | X:2238/2244/2274 | {} |
| InsightsDataDump | X:2511 | i:"Exception" |
| ArtMetricsEtl / ArtMetricsSummarize | X:2542/2549 | i:"FAILURE" |
| UpdateCounterRobotsList (AnyA) | X:661 | v:"UpdateCounterRobotsList patch had been committed to git OR there is nothing to commit" |
| SuspectedBotsScoring / InsightsDatasetDocCount / InsightsInitTestProduct / InsightsIndexHealth / InsightsFeRefreshCache / BigQueryTransferJobsSetup / BigQueryTransferJobsOnDemand | X:2259/2493/2502/2535/1977/2249/2264 | {} |
| BqFinalizeViews / BqNewTableVersion / BqC5LoadAggregateData / BqC4LoadAggregateData / BqInitProduct / BqInitViews / UserInterests / UserInterestsInit / BQAddNewField / InsightsAlertsCheck / DimSyncProd (PostEV → InsightsFeRefreshCache) / DimAkkaJoin / DimSyncDev | X:2621/2615/2602/2596/2609/2704/2722/2728/2734/2710/2555/2679/2685 | i:"FAILURE" |
| BqFilesToSync / LookActivityReport / K8sJavaEtlBuild / K8sJavaEtlCleanup | X:2567/2590/2692/2698 | i:"Exception" |
| ActivateNonprodPipelines | X:2578 | i:"An error occurred" |
| BqLoadDatasets / BqLoadDimTables | X:2561/2584 | i:"BigQueryError" |
| BqClearMismatch / BqCounterBackup / BqCounterRestore / BqInitProductsSchemaEvolution | S:1207/1229/1240/1261 | no "Exception" / "BqBackup.Done" / "BqRestore.Done" / "DONE stat=" |
| InsightsToolsDeploy / DimSyncDeploy | X:2476/2468 | v:"BUILD SUCCESSFUL" |
| ScheduleReportsProd/Staging/Test/BigQuery/BQProd | X:2627/2638/2649/2659/2669 | validators commented out ⇒ always Success |
| InsightsGCRCleanup | X:2716 | v:"GCR Cleaning finished" |

(Any type not named above is covered by one of the grouped rows; the fork-C enumeration totals 441, all mapped.)

---

## 4. ProductRelease expansion in detail

### 4.1 How a ProductRelease row is created
- Directly (UI/REST action `ProductRelease`, `ProductReleaseArgs` 22-field CSV, ActionArgs.java:7398-7442: `skipSiteRegressionInteg, skipSdApiTest, runQaaTests, build, deploy, patch, patchDropColumn, patchUpgrade, pause, startNonWeb, delayBackstageStart, parallelCount, switchAccount(ordinal 0 None/1 SwitchToReadonly/2 SwitchToLive), limitToHost, excludeHosts("h1|h2|"), runDbBackup, mobileTest, performanceTest, restoreSolr, deployServices, canaryHosts, duration`).
- Via `ProductReleaseConverter` for `newimpl.X=true` types (deployserver.properties: ProductRestart, ProductRefreshDeploy, ProductDeployNoBuild, ProductRefreshDeployUpgrade, SwitchToROMode, SwitchToLiveMode, HostRestart, CanaryDeployment) (ProductReleaseConverter.java:23-82): clones src as ProductRelease, `display_action = <src type>`, `parallelCount = parallel.execution.<acct>.<prod>` (default 1; e.g. literatum sage/pericles/tandf/marlin/achs/acm/aaas = 2), `pause = (account=='literatum')`, sets `wait_for_id` to a (found or new) SvnRefreshScripts row if the type is a deployconf-refresh type; per-type flags:
  - ProductRestart: build/patch/patchUpgrade/deploy=false; startNonWeb, delayBackstageStart, excludeHosts from ProductRestartArgs.
  - ProductRefreshDeploy: build, patch, deploy, startNonWeb=true; patchUpgrade = account in `upgrade.with.patch.accounts` (cip); runQaaTests=false.
  - ProductDeployNoBuild: build=false, patch, deploy, startNonWeb=true.
  - ProductRefreshDeployUpgrade: build, patch, patchUpgrade, deploy, startNonWeb=true.
  - SwitchToROMode / SwitchToLiveMode: build=false, deploy=true, pause=true, patch=false, switchAccount set.
  - HostRestart: limitToHost=src.host, all of build/patch/patchDropColumn/patchUpgrade/pause/deploy=false, startNonWeb=true, parallelCount=1.
  - CanaryDeployment: build/patch/deploy/startNonWeb=true, canaryHosts, parallelCount=2, duration.
- UI defaults (client ProductReleaseArgsRenderer, from fork A): build, deploy, patch, startNonWeb, deployServices checked; pause hidden but **true on literatum**; parallelCount 1 (2 for Tier1); patchDropColumn/delayBackstageStart/runDbBackup/mobileTest/restoreSolr/canaryHosts/duration never set by UI.
- Other creators: `deployAffectedProducts` (release manager → staging ProductRelease per affected product, user = `release.assignee.<type>`), ProductRebuild, UpdateProductDockerDatabaseFromBackup.

### 4.2 visitProductRelease (PreExecuteVisitor.java:2692-2957) — argument normalisation
1. `ai.waitForId=null`.
2. switchAccount ≠ None → parallelCount=1; RO/Live → patch, patchUpgrade, startNonWeb=false (:2696-2708).
3. !patch → patchUpgrade=false; limitToHost set → parallelCount=1; !deploy → patch=patchUpgrade=false (:2709-2718).
4. `hosts` = all ServerInstances in `deployconf.<account>.xml` for product+family (`matcher.findMatches`), minus `excludeHosts` (split on `|`) (:2719-2729).
5. Canary: first `canaryHosts*2` web hosts become `canaryHosts` list (:2731-2741).
6. `hosts = reduceToSingleType(hosts, true)` — one entry per family.product.host, backstage preferred, then other non-web, then web (DeployUtils.java:309-345). Empty → markDone(Success), return.

### 4.3 Ordered child list (`trg`)
Order = insertion order = execution order (each has same create_date; sequence_num increases). Conditions:

1. **GaiaCompatibilityCheck** — account `literatum`, not SwitchToReadonly, display_action null or ProductRefreshDeploy (:2750-2752).
2. **LeanDashboardVersionVerifier** — literatum, lean dashboard workflow configured for product, display null/ProductRefreshDeploy/ProductRefreshDeployUpgrade (:2753-2755).
3. **ProductBuild** — `build` (account `readonly` when SwitchToReadonly) (:2756-2762). On insert CreateActionVisitor adds **ProductBuildStyleguide** (PR²).
4. Services — only if `deploy` and (`build` or display null or ProductDeployNoBuild), and (`excludeHosts` and `limitToHost` both empty, or `deployServices`) (:2766-2812); each additionally "not SwitchToReadonly":
   a. **SolrDeploy** if `<solr>` configured; then **SearchServiceDeploy** if searchservice configured; then **SolrRestoreLatest** if parent is ProductRebuild and restoreSolr.
   b. **ProductConsumerDeploy** if consumer configured.
   c. **ProductAtmDeploy** if atm configured.
   d. **ProductIngestionDeploy** if ingestion configured.
   e. **XseDeploy** if xse configured (sets `ai.args = product|family` on the *parent* object → inherited by all later children: minor bug).
   f. **GaiaDeploy** if gaia configured and account not readonly/rorehearsal.
   g. **PugrendererProductDeploy** if styleguide has pugrenderer cluster (account `readonly` for SwitchToReadonly — allowed there).
   h. **K8sPugrendererDeploy** if k8s pugrenderer configured and styleguide has no pugrenderer cluster.
5. CIP pre-step — account ends with `cip`, deploy, and patch||patchUpgrade: **HostStop** + **HostDeploy** on *any host of the family* with no type (:2813-2818) (patching needs deployed code; CIP typed Stop/LockStop/Deploy children are later removed, see 4.4).
6. **Per-host chains** via `DeployUtils.deployProduct` (DeployUtils.java:538-592) using `DeployWithParams.createFamilyDeployActions` (hosts grouped into a TreeMap by host name → **alphabetical host order**; one Stop/Start per host, Deploy(+Patch) per product instance):
   - `ignoreNonWeb = !deploy && !startNonWeb`; `startStopNonWebNonBackstageTogether` is hard-coded `true`.
   - Default products (not in `startstop.NonWebNonBackstageTogether.products` = tandf, pericles):
     1. **backstage** hosts (skipped for RO/Live switch or ignoreNonWeb): `HostStop` → `HostDeploy` (if deploy) → `ProductPatch` (first instance of each product, if deploy; `ProductDBUpgrade` inserted before it only if parent type is ProductRefreshDeployUpgrade — dead because parent is always ProductRelease) → `HostStart` (unless delayBackstageStart).
     2. **web** hosts: `HostLockStop` (macro → HostLock, Pause1Min, HostStop) → `HostDeploy` (if deploy) → [`ProductPatch` only if product not yet patched — normally already done on backstage; also `addAction` drops ProductPatch unless type=="backstage", DeployUtils.java:368] → if start: `HostStart` (PR² HostWaitForWebServer) → `HostWarmupTest` (PR² HostEssentialTest on literatum/readonly non-preprod) → `HostExtraTest` (macro → HostWarmupContent / HostTestJane per props) → `HostUnlock` (PR² ValidateWebOnROMode on readonly).
     3. if `delayBackstageStart` and not ignoreNonWeb: backstage `HostStart`.
     4. **other non-web** (rbackstage, backoffice, mdcdaemon…), if not ignoreNonWeb: `HostStop` → `HostDeploy` (if deploy) → `HostStart` (always start=true here).
   - tandf/pericles: backstage chain → other non-web chain → web chain → delayed backstage start.
   - SwitchToReadonly: `deployProduct(account→"readonly")`: stop actions keep the live account, deploy/start/tests/unlock use account `readonly`; backstage skipped; rbackstage children removed later.
   - SwitchToLive: stops in `readonly`, deploys/starts in live account.
7. Filter pass (:2827-2868), applied when `!pause || !patch || limitToHost set || canaryHosts>1` (i.e. skipped only for a paused, patching, full, non-canary release — then Pause1Min and ProductPatch stay as generated):
   - CIP with deploy/patch: drop typed HostStop/HostLockStop/HostDeploy (the step-5 untyped pair replaces them).
   - SwitchToReadonly: drop `rbackstage` children.
   - Canary: keep only canary web hosts; odd-indexed canary hosts lose HostDeploy; after the first canary HostDeploy insert **CreateEphemeralLiteratumRoute** (duration).
   - `!pause` → drop `Pause1Min` (note: Pause1Min is actually created later by the HostLockStop macro on insert, so this filter matches nothing; the macro's Pause1Min always runs).
   - `!patch` → drop ProductPatch.
   - limitToHost → keep only children with empty host or matching host **and same type as the parent row's type** (HostRestart passes the host type).
8. Upgrade (:2870-2886): if patch and product DB is not a docker DB server and `patchUpgrade` → insert **ProductDBUpgrade** before each ProductPatch.
9. Tail actions:
   - **Pause10Min** (non-literatum) + **SiteRegressionInteg** (args runOnGA=true) — only when row is a plain ProductRelease (display null), build && deploy, !skipSiteRegressionInteg, and `SiteRegressionInteg.account.*` config allows account/product (tier1/tier2 selectors) (:2888-2901).
   - **SitePerformanceTest** if performanceTest.
   - **PugrendererInvalidateCache** + **CfInvalidateCache** if build && deploy && pugrenderer cluster (:2906-2910).
   - account exactly `cip`, build && deploy, product category `qaa` → **Pause10Min** (if not already) + **DependencyReportChecker** on first web host (:2911-2923).
   - **LocalDbCloneAndRestore** if runDbBackup (auto-Cancelled on literatum).
   - staging/midtierbeta, plain ProductRelease, build && deploy, product `sd`, !skipSdApiTest → **SdApiTest**.
10. `parallelizeDeployActions(trg, parallelCount)` (:2960-3004): for parallelCount>1, web hosts are grouped; for every web host except the last in each group of `parallelCount`, its `HostStart` gets `block_ignore=true` and all later actions on that host (warm-up, extra test, unlock) are **dropped** — the next host's chain may start while this one warms up, and its warm-up/unlock is never run by the workflow (comment says "TestAsync takes over in the background", but nothing here creates a TestAsync; `/unlock` REST or HostStart-side scripts must do it).
11. If `display_action` set (converted row): every child gets `display_action=null`, `parent_action=<display type>` (e.g. children of a ProductRestart show parent `ProductRestart`, parent_id = the ProductRelease row id) (:2937-2942). Otherwise `parent_action='ProductRelease'` (from `DeployUtils.getAction`, :399-402). `parent_id` = ProductRelease row id always.
12. Log children list (`PreExecuteVisitor created child actions :` + numbered `ai.toString()`), mark parent **Success** (markDone → PostExecuteVisitor), then `DeployActionSql.createActions(trg, false)` — each child goes through full `createAction` (multi-select, auto-cancel checks, macro expansion on insert, INSERT). **Children are not chained with wait_for_id**; ordering relies on §2.5.2.

### 4.4 Summary of the canonical literatum ProductRefreshDeploy chain (single family, parallel 1)
GaiaCompatibilityCheck → LeanDashboardVersionVerifier? → ProductBuild → ProductBuildStyleguide? → SolrDeploy? → SearchServiceDeploy? → ProductConsumerDeploy? → ProductAtmDeploy? → ProductIngestionDeploy? → XseDeploy? → GaiaDeploy? → PugrendererProductDeploy|K8sPugrendererDeploy? → [backstage host] HostStop → HostDeploy → [ProductDBUpgrade] → ProductPatch (+CipDomainFixup on cip) → HostStart (+HostWaitForWebServer) → [per web host, alphabetical] HostLock → Pause1Min → HostStop → HostDeploy (+HostDeployStyleguide) → HostStart (+HostWaitForWebServer) → HostWarmupTest (+HostEssentialTest) → HostWarmupContent?/HostTestJane? → HostUnlock → [rbackstage/backoffice] HostStop → HostDeploy → HostStart → PugrendererInvalidateCache? → CfInvalidateCache? (SiteRegressionInteg not for converted rows).
**Correction (2026-09-25, confirmed by the operator + CreateActionVisitor.java:~183 + live rmit logs):** HostDeployStyleguide is created only for `web` (or untyped) hosts, never on backstage (bks). ProductBuildStyleguide builds the styleguide on a tools host; HostDeployStyleguide runs on each web host.
Where "?" = conditional as in §4.3; the exact position of the PR² grandchildren is right after their creator (inserted during that child's createAction).

---

## 5. Log production

### 5.1 Files (content root `content.root.dir=/ssd2/deployserver`, DeployUtils.java:54-94)
| File | Writer | Content |
|---|---|---|
| `actionlogs/<id>.txt` | `DeployUtils.writeActionLog` (text) and raw SSH bytes (JschConnection.java:108 → DeployUtils.java:201-248) | main log; see 5.2 |
| `actionlogs/<id>.ssh.txt` | `DeployUtils.writeSshRequest` (:128-140) | one line per command: `[ <account>@<host> - ddMMM HH:mm.ss ] <cmd>` (account = row account, host via `getHostName`) — also duplicated into `<id>.txt` as `(ssh) <cmd>` and into logger `sshreq` |
| `actionlogs/<id>.txt_N` | reset on re-pick (DeployUtils.java:274-295) | only for types in `actions.logs.multipleFilesActions` = `ProductBuild,ProductBuildStyleGuide` — the second name does not match the enum `ProductBuildStyleguide` (case), so effectively only ProductBuild rotates: on re-pick while Scheduled, `.txt`→`.txt_1`, `.txt_i`→`.txt_{i+1}` (up to repeat_count). **All other types: the previous `<id>.txt` is deleted when the row is re-picked** (Scheduler.java:139). |
| `actionlogs/<id>.brokenpatch.txt` | BrokenPatchBlame (git log of the patch file) | |
| `cmdtrace/<cmdId>.txt` | AgentUploadCmdOutputServlet (agent) | agent command output |
| `testresult/<id>/…`, `testresult/<id>.zip`, `testresult/<id>.lastsvn.txt` | test collect phase (SshExecuteVisitor.java:683-827), BranchInfo | `testresult.html` / `testresult.csv` / Allure `index.html` |
| `testreport/<account>/<family>/<product>/<host>/` | latest test report copy per host | |
| `restapiresult/<id>.zip` | REST test results (`report.csv`) | |
| `upload/`, `uptime/`, `report/` | uploaders / uptime CSVs / reports | |
| app logs `logs/` (→ `/ssd2/deployserver/logs`) | log4j2.xml | deployd, deploydinfo, scheduler(err), cron, sshreq, jira, uptime, literatum_unlock, release, stat, sqlupdate, debug/info/warn/error, warnsys, jetty.log |
Retention: `scripts/clean_disk.sh` deletes testresult dirs >7 d and **every file under /ssd2/deployserver >15 d** (incl. actionlogs); DB rows Success/Cancelled >15 d purged.

### 5.2 Anatomy of `<id>.txt`
- Every text entry: `\r\n[ ddMMM HH:mm.ss - <threadName> ] <msg>\r\n`, PST (DeployUtils.java:48-52,175). Thread name distinguishes daemon (`deployd`), executor pool threads (`thread_id` column) and RPC threads (`qtp…`).
- Raw SSH output is appended unframed (no timestamp).
- Typical sequence and meaning:
  1. `<ai.toString()>` lines on every status update — `id: Action by user. Account=, Product=, Family=, Host=, Type=, Status=, Thread=, tt=, immediate=, cancelOnFail=, args=, bugId=, eventJson=, canceledBy=, parentId=, createDate=, sequenceNum=, waitForId=, blockedId=, blockedAction=, blockIgnore=[, NOBLOCK]` (CmdIO.java:359-368). The `Status=` value in the first of these shows the status *before* that write.
  2. `<ai>, blocked by : [<blocker ai>]` (wait_for set by scheduler), `Update host/args/product-family : […]`.
  3. `runAction> <ai>` (AbstractConnector.java:98) — execution start.
  4. PreExecute messages (e.g. ProductRelease: `PreExecuteVisitor : orig args/modified args`, `PreExecuteVisitor created child actions :` + numbered children).
  5. `runAction.execute> <ai>` — SSH connected. `SELECTED HOST.2: <host>`. `failed to connect : acct@host. Attempt=N…` on retries.
  6. Template actions: `cmdTemplate : …`, `cmdparams : {map}` (includes args and model fields — may include credentials), `commands : CMD n $ …`.
  7. `(ssh) export PS1='[${HOST_NAME}:\w (\t)${USER}] '` — first command on each connection (ExectuteCmdImpl.java:40-43); then `(ssh) <cmd>` for each command followed by the raw terminal output (the shell echoes the command too).
  8. `DrainResponse tt=<friendly>, bytes=<n>, prompt=<true|false> (ssh) <cmd>` after each command (JschConnection.java:133). `prompt=true` = the prompt `(HH:MM:SS)<login>]` was seen (command finished); `prompt=false` = EOF/closed channel. Commands containing the substring `exit` are not drained (JschConnection.java:64-66).
  9. `Sent KeepAlive. count=N` every 5 min of a long command (nothing is actually sent). `Invalid connection` if ConnectionCleanup forgot the connection. `Force connection close, connid=` = idle-TTL kill → Failure.
  10. `FAILED: <id> > <Action>, a=, h=, p=, ERROR: …` / `ssh:<login>@<host> failed to execute - …` on exceptions.
  11. `Trying processExecuted.` then parse-side messages (`Rescheduling : …`, `SshExecutedVisitor - RESHEDULING`, test collect: `Trying to copy results … Got results in … Wrote test result output to dir`), `Cancelled automatically`, `failed to convert from executed state. Marking as failure`.
  12. final `<ai>` with `tt=` (time taken).
- Status of the action is **not** printed as a verdict line; infer it from the last `Status=` in ai lines + the validators in §3.

### 5.3 InfoServlet `/info/<id>.txt[_N]` (InfoServlet.java:78-101)
text/plain. `id` = last path segment, suffix `_N` → reads `<id>.txt_N`. Output:
```
-------------------------------------------------------------------------------   (79 dashes)
SSH
-------------------------------------------------------------------------------
<blank>
<all lines of <id>.ssh.txt>
<blank>
-------------------------------------------------------------------------------
<blank>
[if action config ansible=true:]
Ansible commands
-------------------------------------------------------------------------------
<TASK … lines without '*'> / [ddMMM HH:mm:ss - host] <cmd>   (parsed from "ok: [host] => {json}")
-------------------------------------------------------------------------------
<all lines of <id>.txt[_N]>
```
The SSH banner block is absent when `.ssh.txt` does not exist (Java-only actions). The main block is fetched with a DB lookup by id (SQL concatenation); if the row is gone (purged) the servlet NPEs (:47) → HTTP 500 although the file may still exist — use `/actionlogs/<id>.txt` (StaticContentServlet) instead.
`/actionlog.html?id=&reload=` (frameset, auto refresh, running actions), `/actionLogFilesListFrame.html?id=&log=N` (retry picker), `/actionlogs/<id>.txt` and `/actionlogs/<id>.ssh.txt` (raw).

---

## 6. Endpoints for a triage agent

**There is no server-side authentication anywhere** (no security-constraint in web.xml; `RootForwardingFilter` only adds cache headers; `isAgentAccessAllowed()` returns true, DeployServerConfig.java:796-798; GWT RPC trusts client-supplied user ids). Hosts: prod `https://deployserver.literatumonline.com`, CIP `https://cip-deployserver.literatumonline.com`.

### 6.1 Read-only (safe)
| Endpoint | Semantics |
|---|---|
| `GET /info/<id>.txt` , `/info/<id>.txt_N` | combined ssh + main log (5.3) |
| `GET /actionlogs/<id>.txt`, `/actionlogs/<id>.ssh.txt`, `/actionlogs/<id>.txt_N`, `/actionlogs/<id>.brokenpatch.txt` | raw files (StaticContentServlet; 404 "Console output is not available…") |
| `GET /testresult/<id>/testresult.html|index.html|testresult.csv`, `/testreport/<acct>/<fam>/<prod>/<host>/…`, `/report/*`, `/reprocessreport/*`, `/testdashboard/*` | raw result files |
| `GET /actionlog.html?id=&reload=`, `/actionLogReloadFrame.html`, `/actionLogFilesListFrame.html?id=&log=` | HTML wrappers (id unescaped → reflected XSS) |
| `GET /check?key=<rest_id>` | JSON `{status: "failed"|"completed"|"in progress", message}` computed over **children** of the row with that rest_id: failed if any child Failure; completed if ≥1 child and all Success/Cancelled; otherwise in progress (a childless/Java-only action reports "in progress" forever; unknown key → NPE, empty body) (RestApiCheck.java:35-85) |
| `GET /hostStats?account=&family=&products=a,b&host=&branch=` | JSON uptime: `{stats:[{product,family,instances:[{host,type,status,buildBranch,buildDate,buildRevision}]}]}`; account required else 400 |
| `GET /build.info` | DS build time/host/branch/revision + start/stop history |
| `ActionHelp.jsp`, `DeployServerLog.jsp`, `reloadfreq.jsp`, `InsightsProducts.jsp` | read-only pages |
| `/release/add?ticket=&release=` | effectively read-only (update commented out) but writes Jira ticket cache and says "added" |

GWT RPC (`POST /deployserver/deploy`, GWT-RPC serialization; `Service.java`) read methods most useful for triage:
- `getActionInfo(id)` → full ActionInfo row.
- `search(SearchRequest)` → rows (15 cols) + status counts; filters account/action (matches action or display_action)/user/start/end/product/family/host/status(csv)/hideCompleted/showBackground/showTest/cron; `query` = raw WHERE (injection; avoid). **Side effect when `cron=true`: deletes `action_black_list` rows older than today.**
- `getActionFilters`, `getSearchOptions`, `getActionTypeConfig`, `getMultipleLogFilesActions`, `expandDeployAction(AddRequest)` (dry-run of legacy deploy expansion, deploy types only), `getProductsHostsMap(account)`, `getProductHosts`, `getProductBranches`, `getDeployHosts`, `getUptimeStatus/Details`, `getSlaStatus/Details`, `getProductDb`, `getDbCloneOptions`, `getReleases/getReleaseBranches/getReleaseMerges`, `getDashboardPermissions`, cluster-name lookups, product lists.
- Read-but-remote-side-effecting (avoid in automation): `getSolrBackups/getPbBackups/getXseBackups/getSiteConfigBackups/getCassandraBackups` (SSH to hosts), `getGitBranches/Tags/…` (JGit fetch), `getStyleguideProducts` (**runs `git checkout <branch>` in the DS's ~/sourcegit/styleguide**), `getGitRevisions(…, refresh=true)`/`getNoPrefixGitModuleRevisions(…, true)`/`getGitLatestRevision` (git sync), `isValidTicket`, Jira/Tempo lookups, `getInsights*` (GCS/CloudSQL), `getAuthenticatedUserDetails` (Google call; sets session user), `refreshDeployOptions` (mutates session).

Direct DB (if an agent has read-only SQL): `ResultSetToActionInfoConverter.SELECT_FROM_SQL` (ResultSetToActionInfoConverter.java:15) is the canonical projection. Useful queries: children of a deploy `where parent_id='<ProductRelease id>' order by create_date, sequence_num`; why blocked: `blocked_id, blocked_action`; retries: `repeat_count`; auto-cancel: `canceled_by='auto'`.

### 6.2 Writes (avoid)
- REST: `GET /run` (creates any action; GET!), `GET /cancel?key=&user=` (cancels Failure actions of `user` matching parent/action names in key — see bug list), `GET /unlock` (TestAsync), `GET /cipproductleaseedit` (+7 days lease), `GET /jira` (posts Jira comment, credentials in query), `GET /email`, `GET /test` (dead), `/agent` (fetch marks commands sent), `POST /agentlog`, `POST /uptime` (file write, unsanitised name), `POST /upload` (echo), `POST /reprocess/*`, `/testupload/*` (svn commit of test xml), `/rbookuploader/*`, `InsightTestResult.jsp?id=` (unzips/renames), `ClusterInfo*.jsp?cluster=` / `DatasetsMapping*.jsp` (exec shell scripts — command injection).
- GWT RPC writes: `addAction`, `execute`, `createAction`, `updateStatus` (reschedule/cancel/RestartWorkflow/CancelWorkflow), `killAction` (force-close SSH → Failure), `cancelChildActions`, `addExcludeDay`/`removeExcludeDay`, `updateRevisionStatus`, `deployAffectedProducts` (schedules staging deploys), `addTicketToRelease`, `mergeRevisions` (creates GitMergeRev), `refreshDeployOptions`, and the git-sync/checkout readers above. Sync actions submitted via `addAction` execute inside the RPC call.
- Background writers (not endpoints): HousekeepingThread (git sync of deployconf into config, Jira comments, bug_updated, GitMerge Failure→Cancelled), listeners (CIP termination/expiry/cleanup actions), UptimeParseThread, ConnectionCleanup.

---

## 7. Surprises, bugs and risks

### 7.1 Engine semantics (most relevant for triage)
- **B1 Reschedule-on-failure is overwritten in the executor thread.** `processExecuted` calls `rescheduleAction` (status Scheduled, repeat_count+1) and then still returns `Failure` (DeployDaemonHelper.java:536-546); `RunAction` then writes `Failure` (RunAction.java:59-60). Net: repeat_count incremented but status Failure (race: the daemon may start it in between). Expect rows with `repeat_count=1, status=Failure` for ProductBuild/ProductPatch "restart build" cases. Only the daemon's own `processExecuted(false)` path (rows left in Executed) keeps the reschedule. Also PostExecuteVisitor still runs with Failure (Jira/auto-cancel on a rescheduled row).
- **B2 Parent ProductRelease is `Success` as soon as it expands** (PreExecuteVisitor.java:2952); deployment health must be read from children.
- **B3 A Failure blocks the whole account+family** (BlockActions.java:233-247) and, for deploy-server actions, *all* deploy-server actions (:479-499) until someone acts. Failed test types are silently auto-Cancelled (DeployDaemonHelper.java:114-123) and `cancelOnFailure` types become `Cancelled`/`canceled_by='auto'` (PostExecuteVisitor.java:1096-1107) — "Cancelled" does not mean a human cancelled it.
- **B4 Default verdict for Java/SSH actions without a parser is `Cancelled`** (SshExecutedVisitor.java:42): UpdateYaegerVersion, VictorFIntegrationTests, CipLocal(Report)DBIndividualLeaseEdit/Restore, CallDbCleanupLocalBackupOnCip, Disable/EnableProducts, and macro parents without markDone (ProductUpgrade, ProductTermination, StopDisableProducts) always end Cancelled; the CipLocal*Restore pair therefore never chains its Process step.
- **B5 Validators are substring matches over a log that contains the commands themselves** (`(ssh) <cmd>` + `commands :` block). Always-true examples: DbAdminsList `v:""`, CleanupLocalOrphanDbs echoes its own string, MergeFreezeAnnouncement logs "Email Sent" on failure, ScheduleReports* validators commented out, HostWarmupContent/BrokenPatchBlame/GatherFacts always Success; ImmediateSolrBackup checked before its last commands.
- **B6 Logs of earlier attempts are deleted on reschedule** for all types except ProductBuild (DeployUtils.java:283-293; `ProductBuildStyleGuide` property typo vs enum `ProductBuildStyleguide`, deployserver.properties:185). RestartWorkflow wipes every sibling's previous log.
- **B7 RestartWorkflow re-schedules every sibling in the family incl. Success ones and the build** (DeployServiceImpl.java:424-428); CancelWorkflow cancels later siblings regardless of status incl. Executing (:414-418); rescheduleFailedActions for HostRestart children re-schedules all rows of that parent_id incl. successes (DeployDaemonHelper.java:85-93).
- **B8 Immediate actions bypass all blocking** except wait_for_id (FindActions.java:323-352); HostEssentialTest with no parent is forced immediate (DeployActionSql.java:515).
- **B9 Parallel web deploys drop warm-up/unlock of non-last hosts** (PreExecuteVisitor.java:2960-3004); nothing in this code schedules the promised background TestAsync.
- **B10 Pause filter is dead**: `Pause1Min` is added by the HostLockStop macro at insert time, after the `!args.pause` filter (PreExecuteVisitor.java:2845), so every web stop pauses 1 min regardless of `pause`.
- **B11 `ProductDBUpgrade` in DeployWithParams is dead** (checks parent == ProductRefreshDeployUpgrade, DeployWithParams.java:63); XseDeploy branch mutates the *parent* `ai.args` (PreExecuteVisitor.java:2792) so every later child inherits args `product|family`.
- **B12 Host ordering uses `reduceToSingleType` HashMap** (DeployUtils.java:310, 342-344) but `DeployWithParams` re-sorts by host name (TreeMap) — web hosts deploy in alphabetical order, not deployconf order.
- **B13 RO-mode sibling block update is malformed**: `String.format` gets 6 args for 5 `%s`, writing `blocked_action=<parentId>` and `where id='<ActionTypeName>'` → no row updated (BlockActions.java:545-551). The block holds only for the current cycle.
- **B14 Restart of the server re-runs every Executing action from scratch** (DeployDaemon.java:215-233) — e.g. a half-done ProductPatch or DB clone is re-launched.
- **B15 No per-command SSH timeout**; completion = prompt suffix `)<login>]` with "office"→"ofice" (JschConnection.java:79-82); any command containing "exit" is not awaited (:64); idle TTL (1h default, `timeout.<Action>`) forces Failure (ConnectionCleanup.java:70-87). "Sent KeepAlive" sends nothing.
- **B16 Cron throttle dead** (`s_lastCheckTime` never set, EventToActionFactory.java:32-37); a Failure of a previous cron instance suppresses all future runs (:125-141).
- **B17 `DeployActionSql.getActionStatus` builds `"where parent_id=%s"` without formatting** → invalid SQL (DeployActionSql.java:248-249). `cancelActions(key,user)` (`/cancel`) scans all rows of the user and cancels by `key.contains(parentActionType name)` — the REST key is a UUID so it effectively cancels nothing, or anything whose type name happens to be in the string (:201-231).
- **B18 Pre-insert auto-cancel still inserts the row as Cancelled** (DeployActionSql.java:385-444) — visible as "Cancelled" with a log line "… is not configured. Ignoring action".
- **B19 Multiple static caches in DeployConfUtils mutated from many threads without synchronization** (`hostMap` reassigned by every `getAnyHostForFamily`, DeployConfUtils.java:203-236). `getAnyHostFor*` picks from a HashSet (non-deterministic host).
- **B20 ProductPatch Jira ticket auto-creation** when patch ≥ 30/60 min (DeployDaemonHelper.java:135-165) and ProductRelease on literatum pericles/amps with build creates a **JSM CHG ticket** at insert time (DeployActionSql.java:615-657; description has malformed URL `https://https://jira.prod.atypon.com//browse/`).
- **B21 `RefreshDbDashboard`** marks Failure then Success (PreExecuteVisitor.java:1787-1790); `GenerateReleaseNotes` returns without markDone when no tickets (:845-847) → Cancelled.
- **B22 JiraHelper turns failed GitMerge/GitMergeRev into Cancelled** (JiraHelper.java:156-157).

### 7.2 Security
- No authn/authz server side (see §6); identities are RPC parameters; opsOnly enforced only at scheduling for top-level rows (Scheduler.java:168-179) and in the browser.
- Arbitrary SQL by design: `search(query)` raw WHERE (DeployServiceImpl.java:163-166), `UpdateActionParams` raw UPDATE WHERE (PreExecuteVisitor.java:1523-1574); widespread string-concatenated SQL (RestApiCheck, InfoServlet:42, BlockActions, DeployActionSql, TestAsyncServlet, Dictionary, AgentCmdInfo).
- Command injection: ClusterInfo*.jsp `cluster` param into `Runtime.exec`; `RunCLI`/`run-cli.sh`/`SftpAccountSettings` run user text; Velocity templates interpolate args unescaped into shell lines.
- Path traversal: StaticContentServlet (`contentRoot + URI`), UptimeStatusUploadServlet filename, uploaders' path-info, InsightTestResult.jsp.
- Secrets in logs readable via unauthenticated `/info` and `/actionlogs`: DB passwords (ProductCleanupPostClone, GenerateDbIndexReport — SshExecuteVisitor.java:963, 1294), Jenkins/GitHub tokens (SshExecuteVisitor.java:515, 542; `$util.getGithubApiToken()` templates), `cmdparams` dumps of model credentials, UpdateDockerProductDomain `-P '$dbPass'`, CfVideosCleanup/Cloudflare keys. Employee passwords emailed (PostExecuteVisitor.java:112) and generated passwords stored in `args` (client ActionArgs.java:2469).
- Hard-coded credentials (values not reproduced): <secret at config/actions.xml:669>, <secret at config/actions.xml:676>, <secret at config/actions.xml:2300,2310,2320,2519-2521,2528-2530>, <secret at S/server/visitor/SshExecuteVisitor.java:978-979>, <secret at S/server/DeployServerConfig.java:444>, <secret at S/server/DeployServerConfig.java:484>, <secret at S/server/integ/GitClientImpl.java:69>, <secret at S/server/strategy/teststrategy/util/TestUtils.java:47>, <secret at S/server/service/DbOfficesService.java:42>, secret-bearing lines in config/deployserver.properties:36, 61, 95, 96, 193, 217, 248-264, 291, 317, 361, 367 (plaintext AWS access/secret keys at 248-264), config/override/* bugzilla lines, config/config.yml:3, config/insights-gcp.json:4-5 (service-account private key), config/newrelic.json:2, config/jiraalert/config/jiralert.yml:7, config/deployconf-add-*.vm:2, scripts/addSvnPerm.sh:30, checkoutMajorBranchByJenkins.sh:12, handleRootPomReleaseJenkins.sh:11, gitBranchCreate.sh:174,176, gitRemoveBranch.sh:20, profile:16,19; `src/client_secret.json` (unopened). **Recommend rotation of all of these.**
- `StrictHostKeyChecking=no` for all SSH (JSchConnector.java:86, TunnelHelper).
- Scripts with destructive side effects: `addSvnPerm.sh` force-push; `gitBranchCreate.sh:121` writes `deploy_action.args` via psql; terraform `-auto-approve` in tf_*.sh; `clean_disk.sh` deletes all content >15 d.

### 7.3 Other bugs (from readers, abbreviated)
- REST `/run` swallows exceptions and returns empty 200 (RemoteActionServlet.java:42-45); `/check` NPE on unknown key (RestApiCheck.java:54-62).
- InfoServlet NPE when row purged (InfoServlet.java:47).
- `CheckFailureActions` select missing comma (ResultActionsFailure.java:13) → listener fails every hour; `RemoveCipProductListener` never sets `ai.id` (:81-90).
- Flyway `V3_update_branches_table.sql` (single underscore) not picked up by default naming while code uses `release_branch.repo`; `agent_filetransfer` indexes created on `agent_cmd` (V1:280-281).
- `officeAccounts` static list grows on every config reload (DeployServerConfig.java:187, 506).
- `rescheduleFailedTests` shells out to `xmllint` on the DS for every failed HostWarmupTest every loop iteration (DeployDaemonHelper.java:52-80); dead `boolean prod` (:67).
- `DeployActionSql.createAction` `host` local var always null (:381-384 dead).
- Client: TestGroup args serialize with literal `\|` (ActionArgs.java:3474,3507); BqNewTableVersionArgs NPE; SLA reload timer NPE; refresh intervals ×10 s not minutes; mostly client-side-only permission checks; GWT client imports server classes.
- Template bugs: SiteConfigBackup/Restore Velocity `if (` (actions.xml:2138,2179); Mule actions run activemq (:884,:890); DSConfigRefresh copies non-existent log4j.xml (:1899); SetPatchRelease/MajorUpdateLiteratumProps/CreatePatchPlan `$releaseNum` never populated (PostExecuteVisitor.java:494-513); ChangeGaiaVersion commits without cd (:2765).
- Config drift: duplicate InsightsToolsDeploy/InsightsIndexHealth/InsightsFeRefreshCache entries; `MarlinJaneQA` configured but not a type; tags reference non-existent SolrCloneIndexes/DevDbLeaseEdit; `accountFilter="cip,cip"`; enum dispatch aliases (§3).
- Macros that never insert their parent row (AtmTrainingProduct, TestGroup, HostExtraTest, DbCleanupLocalBackup, CipProductTermination) leave children pointing at a non-existent `parent_id` — joins on parent fail.
- `pollnext.pause=10` has no unit (DeployServerConfig.java:486 `toTimeMillis`) — likely 10 ms busy polling.

### 7.4 Process notes (this review)
- Before the no-secrets rule arrived, I had viewed a few secret-bearing lines of `config/deployserver.properties` (AWS key lines ~248-254) and reader B had printed the `insights-gcp.json` private key into its own session transcript. None of these values are written here; the session transcripts under `/tmp/claude-1000/.../tasks/` may contain them and can be deleted.
