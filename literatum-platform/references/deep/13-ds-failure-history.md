# 13 — Deploy Server failure history, beta + stag (2026-09-10 → 2026-09-25)


> **Correction (2026-09-25, checked by hand):** `patch-package: not found` is **not** the cause of the ProductBuildStyleguide failures below. The utypon-cli install still completes; the real failure is a utypon product build (e.g. `marlin/cell` failed in 898 ms) whose error is only in `~<acct>/logs/<acct>/<p>/UI/build.tgz` on the tools host. Also: `Bean 'clusterMetrics' … BeanPostProcessorChecker` WARN lines are harmless, not the LIT-683431 NPE.

Built 2026-09-25 from read-only Deploy Server calls only: `ds_search.py` (search RPC, cron=false/query=null) and `GET /info/<id>.txt`. Accounts: `midtierbeta` (beta), `staging` (stag). 396 log fetches in total, sequential. Logs are kept privately under `${TMPDIR:-/tmp}/ds-triage-$USER/history/` (not in this repo). Every quoted line below was passed through the secret filter and shortened.

## How the data was found (and what it can't see)

- **`Status=Failure` search = only failures nobody has touched.** It returned 5 beta child rows and 1 stag row (plus parent ids). A failure that was rescheduled, restarted or cancelled has a different status now.
- **Most past failures now show up as `Cancelled`.** A row whose log header ends in `Status=Failure` (or one that ran, hung, and was then cancelled) is a real failure. The header's `canceledBy=` is always `null`, because the header is written before the cancel happens. So **`canceledBy=auto` can't be read from the log**, and I counted "ran and failed, now Cancelled" as a failure whoever cancelled it.
- **A `Cancelled` row with an empty log (2 bytes) never ran.** That's a later sibling cancelled by CancelWorkflow or auto-cancel: **collateral** by definition.
- The search's `Cancelled` result mixes children and parents. I treated an id that appears in more than one per-action search as a parent.
- **What wasn't fetched (budget):** HostWarmupTest (≈300 beta / ≈600 stag ids, 7 sampled), HostTestJane (40/26, 6 sampled), stag RunCLI (83, 13 sampled), HostStart (39/47, 30 sampled, all never-ran), and host-lock/stop/unlock/invalidate steps (3 sampled each, all never-ran). Build, patch, service-deploy, HostDeploy and HostWaitForWebServer were fetched **completely**.

## (a) Counts: failures (ran and failed) by account × class × action

55 failed executions in total (beta 23, stag 32). Collapsed to 37 root-failure rows in (b) (same site + signature + re-run batch counted once).

| Account | Class | Action | Failed runs |
|---|---|---|---|
| beta | code/compile | ProductBuild | 1 (marlin) |
| beta | dependency pin | ProductBuild | 1 (was, KNOWN ADVISER) |
| beta | dependency (npm tooling) | ProductBuildStyleguide | 1 (marlin) |
| beta | code (silent upstream, LIT-683431) | ProductPatch | 2 (hope, acm) |
| beta | patch code | ProductPatch | 3 (mms Patch032053 CNF; physio ×2 DbVersionCheck NPE) |
| beta | patch data | ProductPatch | 2 (aiaa lit32053 ×2) |
| beta | patch-VM startup / Cassandra | ProductPatch | 1 (informs) |
| beta | patch data (CLI) | RunCLI | 2 (tandf AddAtyponIPs ReadOnly ×2) |
| beta | infra service (Solr) | SolrDeploy | 2 (sage, tandf) |
| beta | host/process | SolrDeploy | 1 (cabi unreachable) |
| beta | host/process | GaiaDeploy | 2 (asha host key, uchicago /tmp/start.sh) |
| beta | infra credential | GaiaDeploy | 1 (mms publickey) |
| beta | infra service (external IdP) | HostWarmupTest | 1 (marlin) |
| beta | unknown | HostWarmupTest | 1 (ux3) |
| beta | deployconf/test config | HostTestJane | 1 (marlin 403) |
| beta | transient (operator kill) | ProductBuildStyleguide | 1 (physio) |
| stag | code/compile | ProductBuild | 2 (utoronto, asha; LIT-656000 patch vs maint branch) |
| stag | deployconf/branch | ProductBuild | 1 (gsl missing props file) |
| stag | dependency (npm tooling) | ProductBuildStyleguide | 4 (marlin ×2, app ×2) |
| stag | patch code | ProductPatch | 4 (aami, hanser, app, asmj: Patch032053 CNF) |
| stag | code (silent upstream, LIT-683431) | ProductPatch | 1 (marlin) |
| stag | patch-VM startup | ProductPatch | 1 (hope missing xercesImpl jar) |
| stag | host/process | ProductPatch | 1 (np platform-tools build dir) |
| stag | host/process | ProductConsumerDeploy | 1 (asmj fallback version 10.0) |
| stag | infra service / code | ProductConsumerDeploy | 1 (was topics json) |
| stag | patch data + code (CLI) | RunCLI | 10 (AddAtyponIPs invalid IP: aps, asmj, eup, pericles, utb Failure + apha, arrs, physio, wspc, apharma hung → cancelled 25 Sep) |
| stag | code (CLI) | RunCLI | 1 (marlin LIT-604088) |
| stag | host/process (CLI env) | RunCLI | 1 (pnas registry/jdbc) |
| stag | deployconf/test config | HostTestJane | 3 (marlin 403) |
| stag | unknown (warm-up assertion) | HostWarmupTest | 1 (guilford) |

**Collateral:** 309 of the 383 fetched Cancelled ids had no log at all (never ran). Every HostWaitForWebServer (46), HostStart (30), HostDeploy (29 of 31) and PugrendererProductDeploy (24 of 26) row fetched was collateral.

## (b) Root failures

Date = when it ran (DS server time). K = KNOWN in failure-signatures.md / SKILL.md; N = NEW.

| Date | Acct | Product-Fam | Action | Signature (redacted) | Class | K/N |
|---|---|---|---|---|---|---|
| 13 Sep 04:16 | beta | cabi-B32 | SolrDeploy | `fatal: [cabi-beta-solr1]: UNREACHABLE! … Make sure this host can be reached over ssh: Connection timed out` | host/process | N |
| 13 Sep 12:30 | beta | hope-A39 | ProductPatch | `ClusterMutexManager … NullPointerException … "this.clusterMetrics" is null` → `Patch lit31708 failed to execute` | code (silent upstream) | K (earlier than the documented 23–25 Sep window) |
| 13 Sep 16:30 | beta | marlin-F | ProductBuildStyleguide | `sh: 1: patch-package: not found` → `Error - Failed to Build The Product` | dependency (npm tooling) | N |
| 13 Sep 20:41, 14 Sep 20:45 | beta | physio-C8 | ProductPatch | `error with version checking db_version (lit32046): Cannot invoke "Patch.getMetadata()" because "patch" is null` at `DbVersionCheck.checkVersion:154` | patch code | N |
| 15 Sep 04:40 | beta | physio-C8 | ProductBuildStyleguide (standalone) | `Force connection close` 29 s into `git submodule update`, branch `physio-pcms-maint-260706-d44d4230` | transient (operator kill) | K (pattern) |
| 16 Sep 17:22 | beta | marlin-F | HostTestJane | `FAILED,…,expected:<200> but was:<403>` (all WS tests) + `File 'wsconf/marlin/wsresources/registration.xml' does not exist` | deployconf/test config | N |
| 16 Sep 20:14 | beta | tandf-D | SolrDeploy | `Ensure node is alive and all cores are active` 1440 attempts, solr1 404 → `COMPLETED FAILURE` | infra service (Solr) | K |
| 17 Sep 00:30 | beta | sage-B39 | SolrDeploy | `'cols' is undefined` / 404 probes, then `Ensure node is alive…` on solr2 (982 retries) → `COMPLETED FAILURE` | infra service (Solr) | K |
| 18 Sep 07:13, 09:10 | beta | tandf-D | RunCLI AddAtyponIPsToAtyponInstitution | `Exception in thread "main" ReadOnlyException` at `InstitutionUser.saveImpl` ← `AddAtyponIPsToAtyponInstitution.java:131` | patch data | N |
| 19 Sep 08:48 | beta | ux3-C19 | HostWarmupTest | `***Test Is Failed***`, `status : 8` after 3 s, no detail | unknown | N |
| 19 Sep 19:29 | beta | marlin-F | HostWarmupTest | `Exception during impersonation login: Connect to loadrc-id.elsevier.com:443 … Connection refused` | infra service (external IdP) | N |
| 20 Sep 22:23 | beta | asha-B2 | GaiaDeploy | `Verify bundle versions exist remotely` → `Failed to connect to the host via ssh: WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED` (beta-gaia-2) | host/process (host key) | N |
| 20 Sep 23:40 | beta | uchicago-B38 | GaiaDeploy | `Copy files from Ansible master … (item=start.sh) msg: file (/tmp/start.sh) is absent, cannot continue` | host/process | N |
| 21 Sep 07:37 | beta | marlin-F | ProductBuild (lit-2610 `0e012486`) | `MarlinGenerateMultiplePdfsCompressedFile.java:145: error: cannot find symbol issue.getItemCount()` → `:product:marlin:compileJava FAILED` | code/compile | N |
| 21 Sep 09:50 | beta | mms-E | ProductPatch | `ClassNotFoundException: com.atypon.patch.Patch032053` → `Patch lit32053 failed to execute` | patch code | K |
| 23 Sep 02:05, 24 Sep 01:14 | beta | aiaa-A22 | ProductPatch | `Patch lit32053 failed to execute` ← `ReadOnlyException` | patch data | K |
| 24 Sep 00:35 | beta | was-W | ProductBuild (master `c3e9ae86`) | `ContributorsIndexingUtil.java:210: cannot find symbol ADVISER` (+ `LIT-656000 … patch failed, reverting`) | dependency pin | K |
| 24 Sep 01:17 | beta | informs-A28 | ProductPatch | `ERROR LOADING PRODUCT informs` … `GaiaFeBeans getOutputCacheFactory` ← `InvalidQueryException: table table_index does not exist` | patch-VM / Cassandra | K |
| 24 Sep 07:26 | beta | mms-E | GaiaDeploy | `Error [52] while pulling repository` + `Permission denied (publickey)` | infra credential | K |
| 24 Sep 16:49 | beta | acm-J | ProductPatch | `"this.clusterMetrics" is null` → `Patch lit31708 failed to execute` | code (silent upstream) | K |
| 10 Sep 09:41, 10 Sep 17:30, 13 Sep 03:45 | stag | marlin-F | HostTestJane | same 403 / `registration.xml does not exist` signature as beta | deployconf/test config | N |
| 12 Sep 12:05 | stag | utoronto-B36 | ProductBuild (lit-2610-maint-260901 `0b80c873`) | `LIT-656000 PATCH OK1/OK2`, then `ConnectedProductsRestApiAction.java:13: constructor RestApiAction … cannot be applied` | code/compile (build-time patch vs branch) | N |
| 13 Sep 16:30, 14 Sep 16:13 | stag | marlin-F | ProductBuildStyleguide | `sh: 1: patch-package: not found` → `Failed to Build The Product` | dependency (npm tooling) | N |
| 14 Sep 05:02 | stag | gsl-B21 | ProductBuild (lit-2610-maint-260804 `dcdcd486`) | `:product:gsl:copyProperties FAILED` ← `FileNotFoundException …/product/midtier/conf/midtier.props.cf-non-prod.xml` | deployconf/branch | N |
| 14 Sep 16:04 | stag | np-C16 | ProductPatch | `:compileJava FAILED` ← `NoSuchFileException …/sourcegit.nfs/platform-tools/operations/tools/build/generated/sources/annotationProcessor/java/main` | host/process | N |
| 15 Sep 06:35 | stag | asha-B11 | ProductBuild (lit-2610-maint-260901 `6e1332b2`) | `LIT-656000 PATCH OK1`, then `BaseSemanticSearchSupplier.java:46: cannot find symbol semanticSearchMetrics.recordApiCallDuration` | code/compile (build-time patch vs branch) | N |
| 15 Sep 12:27 | stag | hope-C9 | ProductPatch | `ERROR LOADING PRODUCT Health Affairs` ← `DocumentBuilderFactory cannot be created` ← `NoSuchFileException …/webapps/hope/WEB-INF/lib/xercesImpl-2.12.2.jar` → `KILLING THE SYSTEM` | patch-VM startup | N |
| 17 Sep 04:48 | stag | pnas-B17 | RunCLI `contentsuppression.index -a` | `RegistryException: Registry is not yet initialized` → `IllegalStateException: Pool jdbc is not configured` → idle `Force connection close` 06:01 | host/process (CLI env) | N |
| 18 Sep 07:03 | stag | marlin-F | RunCLI AddAtyponIPs | `NullPointerException: LIT-604088: legacy singleton has not been set yet` (CoreSpringConfig) → `BUILD FAILED` | code (CLI) | N |
| 18 Sep 07:04–07:14 | stag | aps, asmj, eup, pericles, utb (+ apha, arrs, physio, wspc, apharma hung) | RunCLI AddAtyponIPs | `ERROR ACS - Invalid IP address!` → `DbException: Missing max ip address`; the JVM then hangs (LIT-682969), closed by idle TTL or cancelled on 25 Sep ~07:05 | patch data + code | K |
| 20 Sep 08:37 | stag | guilford-B30 | HostWarmupTest | `AssertionError: Warm Up Test (TOC page) has been failed: …/toc/pedi/0/0` | unknown (warm-up) | K (generic) |
| 22 Sep 06:19, 06:36 | stag | hanser-B25, aami-B27 | ProductPatch | `ClassNotFoundException: com.atypon.patch.Patch032053` | patch code | K |
| 22 Sep 08:26 → 09:12 | stag | app-A28 (release `aeca31f4`) | ProductBuildStyleguide, then ProductPatch | `patch-package: not found`, then `Patch032053` CNF (two independent roots in one release) | dependency / patch code | N / K |
| 22 Sep 19:36 | stag | was-W | ProductConsumerDeploy | `Get topics-was.json for profile production` → `'dict object' has no attribute 'status_code'` (stag-consumer-2) | infra service / playbook code | N |
| 23 Sep 00:48 | stag | app-A28 (release `cfe4fc96`) | ProductBuildStyleguide | `patch-package: not found` | dependency (npm tooling) | N |
| 23 Sep 02:28 | stag | marlin-F | ProductPatch | `"this.clusterMetrics" is null` → `Patch lit9529 failed to execute` | code (silent upstream) | K |
| 23 Sep 03:28 → 04:33 | stag | asmj-A32 (release `4e307262`) | ProductPatch, then ProductConsumerDeploy (re-run) | `Patch032053` CNF; then `NO deploy_version … for '2610-maint-260901-…', fallback '10.0'` → `Error [52] … no such ref 'refs/heads/10.0' was fetched` | patch code / host-process | K / N (variant) |

**Grouping by parentId.** Only two releases had more than one failed child. app `aeca31f4`: the styleguide failed and the patch failed on its own later. asmj `4e307262`: the patch failed first, then the consumer failed on the second round, after a restart. All other failures are the only failed child of their release. Everything after them in the same release never ran (collateral, the empty-log Cancelled rows).

## (c) NEW signatures (proposed meaning; evidence = log id)

1. **`sh: 1: patch-package: not found` → `Failed to Build The Product`** (ProductBuildStyleguide). The ui-products postinstall calls `patch-package`, which isn't installed on the tools host (tools-5/7/8/11). Same family as the known `utypon: command not found`. Class: DEP/tooling. It happened 5 times: marlin beta+stag daily 16:01 runs, and app stag ×2. Evidence: `3d1d3fed`, `e966368f`, `eccd088a`, `06bd188f`, `0896f2ce`.
2. **`error with version checking db_version (litN): Cannot invoke Patch.getMetadata() because "patch" is null` (DbVersionCheck:154).** The site DB records a patch (lit32046) that has no patch file on this build's literatum-patch branch, i.e. the DB is ahead of the branch (physio is on a `physio-pcms` maint branch). This is inferred and should be checked against the literatum-patch branch. Class: PATCH-CODE. Evidence: `21be0f5f`, `7138c203`.
3. **LIT-656000 build-time patch reports `PATCH OK`, then compile fails on metrics code** (`RestApiAction` constructor, `semanticSearchMetrics.*`) on `lit-2610-maint-260901`. The patch strips metrics from base classes that newer maint code still uses, so here it breaks the compile instead of silently reverting. Class: CODE (build-time patch vs branch). Evidence: `79aaed30` (12 Sep), `39fa7102` (15 Sep).
4. **Missing props file in `copyProperties`** (`midtier.props.cf-non-prod.xml`) on the older `lit-2610-maint-260804`. The product/deployconf asks for a props variant that this maint branch doesn't have. Class: CONF/branch. Evidence: `98d3b74b`.
5. **Patch VM can't find a jar in the deployed webapp** (`WEB-INF/lib/xercesImpl-2.12.2.jar` NoSuchFile → DocumentBuilderFactory → KILLING THE SYSTEM). The patch classpath was built from a different WAR than the one on disk (the webapp changed underneath). Class: PATCH-VM/HOST. Evidence: `9d5fc7bc`.
6. **platform-tools gradle NoSuchFile on `sourcegit.nfs/platform-tools/…/generated/sources/annotationProcessor`** at ProductPatch `:compileJava`. The shared NFS build dir was probably being cleaned or built at the same moment. Class: HOST (likely transient). Evidence: `aa6084bb`.
7. **HostTestJane (marlin) all WS calls return 403, plus `wsconf/marlin/wsresources/registration.xml does not exist`.** Recurring on beta and stag. Test config or WS access for the test client is broken, not the deploy. Class: CONF/test. Evidence: `59ff193d`, `e7958476`, `7a62b01c`, `71b5aaef`.
8. **Warm-up impersonation login refused (`loadrc-id.elsevier.com:443`).** An external IdP dependency of the marlin warm-up was down. Class: SVC (external)/transient. Evidence: `81a607db`.
9. **Ansible `UNREACHABLE! … Connection timed out`** (solr host). Class: HOST/transient. Evidence: `c178a35a`.
10. **Gaia `REMOTE HOST IDENTIFICATION HAS CHANGED`** (beta-gaia-2, tools-1 known_hosts). The host was rebuilt or re-keyed. Class: HOST/CRED. Evidence: `52e58c73`.
11. **Gaia `file (/tmp/start.sh) is absent, cannot continue`.** A temp file on the ansible master was missing, probably from two concurrent Gaia deploys (asha 22:23, uchicago 23:40) sharing `/tmp`. Inferred. Class: HOST. Evidence: `4721fd03`.
12. **Consumer `Get topics-<p>.json …` → `'dict object' has no attribute 'status_code'`.** The uri call failed without an HTTP status (connection error or timeout), and the playbook's condition assumes one exists. Class: SVC + playbook bug. Evidence: `b63282e2`.
13. **Consumer fallback deploy version `10.0` has no branch** (`no such ref 'refs/heads/10.0'`, Error [52] without auth). The maint identifier has no `deploy_version`, and the fallback isn't a branch. This is a more specific form of the known "Error [52] without auth". Class: CONF/HOST. Evidence: `3ab051ad`.
14. **RunCLI AddAtyponIPsToAtyponInstitution `ReadOnlyException` at `InstitutionUser.saveImpl` (line 131).** The Atypon institution user is read-only on tandf beta. This is a data variant of the known invalid-IP case. Class: PATCH-DATA. Evidence: `032e29dd`, `ebfb888f` (the second one hung until 20 Sep).
15. **RunCLI `LIT-604088: legacy singleton has not been set yet` (CoreSpringConfig NPE).** The CLI's Spring bootstrap on marlin stag is broken. Class: CODE. Evidence: `70885467`.
16. **RunCLI `Registry is not yet initialized` → `Pool jdbc is not configured`** (pnas `contentsuppression.index`). The CLI started without registry/DB config, then was closed by the idle TTL. Class: HOST/CONF. Evidence: `3a234861`.
17. **Warm-up `status : 8` with no failure detail** (ux3). The log has nothing to act on. Evidence: `102126bc`.

## (d) Recurring products / branches

- **Patch032053 stub missing (`com.atypon.patch.Patch032053`):** 4 stag sites (aami, hanser, app, asmj on 22–23 Sep) and mms beta (21 Sep). **lit32053 ReadOnly:** aiaa beta ×2. So lit32053 caused 7 of the 15 ProductPatch failures.
- **clusterMetrics null (LIT-683431):** hope beta **13 Sep**, marlin stag 23 Sep, acm beta 24 Sep. hope on 13 Sep predates the documented 23–25 Sep LIT-656000 window. Worth checking which branch hope-A39 builds from.
- **`lit-2610-maint-260901`:** 2 compile failures after the LIT-656000 build-time patch (utoronto, asha stag), and asmj's consumer had no deploy_version for it.
- **marlin-F (beta+stag):** 11 failures across styleguide, HostTestJane, warm-up, ProductBuild and patch. The daily 16:01 scheduled release fails almost every day.
- **AddAtyponIPsToAtyponInstitution (LIT-682963, run by one operator 18 Sep):** at least 13 failed runs (11 stag, 2 beta). Only 13 of the 83 stag RunCLI ids were sampled, so there are probably more.
- **physio-C8 beta:** DbVersionCheck ×2, plus a killed styleguide build.
- **Solr beta:** sage, tandf (node-alive timeout) and cabi (unreachable).

## (e) Coverage

- Search ids: Failure beta 12 / stag 1 (includes parents; 5+1 real failure rows). Cancelled (page 3000) beta 824 / stag 1375. Per-action searches: 33 action types × 2 accounts.
- Logs fetched: **396** (13 Failure-search + 383 Cancelled). Final header status: 49 Failure, 14 last `Scheduled`, 24 `Success`, and 309 with no log (never ran). Of the 14 `Scheduled`, 6 are real failures (5 hung RunCLI, 1 was consumer); the rest are parents or never-ran rows. The 24 `Success` are mostly parents plus steps that passed before a later cancel.
- Missing/purged: no HTTP errors. Empty logs = never ran, not purged. Retention limits the window to about 10–25 Sep. Earlier attempts of rescheduled steps (other than ProductBuild `_N`) are deleted, so a step that failed and then passed on reschedule is **invisible** here (e.g. mms's first Akka ProductPatch failure from SKILL.md isn't in this set).
- **Not covered (sampled only):** HostWarmupTest (7 of ~900 ids; most sampled rows that ran had failed, so auto-cancelled warm-ups are the largest uncatalogued group), HostTestJane (6 of 66), stag RunCLI (13 of 83), HostStart (30 of 86), and stop/lock/unlock/invalidate steps (3 each). Next pass, if wanted: a dedicated warm-up sweep with its own fetch budget.

> **Correction (2026-09-25, verified):** physio lit32046 `"patch" is null` is NOT "DB ahead of branch". It is the pre-LIT-677519 reserved-dependency bug (fix `523433c4b1` on lit-2610-physio-pcms-260706, 2026-09-15). See notes/25.

> **Corrections (2026-09-26, eval loop 2, verified):** uchicago 20 Sep GaiaDeploy `/tmp/start.sh is absent`: the race is on the **Gaia node** (beta-gaia-1), not the Ansible master. authorea GaiaDeploy on the same dc-beta cluster started at 23:40.00, uchicago at 23:40.06; known open bug LIT-656679. hope 15 Sep `xercesImpl-2.12.2.jar NoSuchFile`: NOT a different WAR / dependency. The same revision patched fine at 11:25 and 15:40 on the same host; the jar disappeared during the patch VM start. Cause needs the host (`/var/tmp/<epoch>.txt`).

> **Correction (2026-09-26, eval loop 4, verified):** pnas 17 Sep RunCLI is NOT "CLI env/startup failed": the tool completed 38/38 batches, then `updateLogSetting` ran after `loadAndRun` had shut the DB pools down (`ContentSuppressionIndexer.java:152-153`, `SearchConfigurationLoader.java:267`) → `Pool jdbc is not configured` → JVM hang → idle-TTL force-close. Code bug. Also: the 18 Sep AddAtyponIPs batch was 79 stag products, not 10-11.
