# 14 — How LIT Jira tickets resolved Deploy Server failures (last ~12 months)

Mined 2026-09-25, read-only (JQL/CQL search + read only; nothing created, edited or commented). People are named by role only. Secret-bearing lines were filtered out before reading (grep for pass/token/secret/credential/…); no secret values copied.

**What was read, and how much.** About 190 tickets were pulled with description + comments. For each one I read a digest: summary/status/resolution, the **first 700 chars** of the description (stack-frame lines stripped), and the **first comment + last 4 comments** (550 chars each). Long threads (20+ comments: LIT-656000, 660575, 670168, 678526, 669506, 682051, 591953) were **sampled, not read fully**. The resolution text is usually in the last comments, so root cause/fix is well covered. Mid-thread investigation may be missing. "Stated" = the ticket says so. "Inferred" = my reading.

Owner shorthand: **LIT-dev** = the literatum committer of the breaking change (Ops files the ticket with "the last change on this file was <commit>, @author please check"). **LRE** = release/build engineering (platform-tools, root-pom). **Ops** = deploy/ops engineer. **SRE** = infra (Cassandra/ZK/Solr/ansible).

---

## 1. Signature → root cause → fix → tickets

### 1a. ProductPatch — patch VM won't start (`ERROR LOADING PRODUCT … KILLING THE SYSTEM`). No patch ran.
The largest group, recurring every release/maint-branch week. Almost always a **code regression on the branch being built**. The Spring bean in the first `Error creating bean with name '<x>'` line points to the commit.

| Signature (short) | Root cause (as stated) | Fix / action | Tickets | Recurs? |
|---|---|---|---|---|
| `BeanCreationException … 'robotsExposer': Invocation of init method failed` (+ `LIT-604088: legacy singleton has not been set yet` in literatum.log) | Wrapper around the **`this.clusterMetrics` is null** NPE (`PluginMetrics.timer`). Same root as LIT-683431 (LIT-643926 metrics work; the LIT-656000 build-time patch is the workaround) | **Rebuild + redeploy** so the build carries the patched/reverted code ("they just need to rebuild and redeploy") | LIT-661094 (Feb, 25 beta sites), LIT-663247 (Mar), LIT-682051 (tandf-test Sep), LIT-683467 (**utb PROD** bks, Sep 23), LIT-658229 | Yes: Jan→Sep, every time the workaround broke |
| `[ClusterMutexManager] Failure to load ClusterMutex class from registry cluster/mutex/clusterMutexClass` → `ExceptionInInitializerError` inside `Executing patch lit31708` / `lit9529` | Same cluster-metrics root (LIT-643926 / LIT-591953) | Workaround patch applied at build time; maint branches needed **a different patch file** (`lit-2610.maint.txt`) (LIT-663639). marlin MR1 got a branch-specific special case in `rebuild.py` (LIT-683320). Final fix 2026-09-25: revert committed to git on 2610 branches, workaround removed (platform-tools PR #354) | LIT-656000, 658138, 661342, 663639, 682395, 681972, 683320 | Yes, many times |
| `NoClassDefFoundError: akka/actor/typed/scaladsl/adapter/package$UntypedActorSystemOps$` at `RobotManager_Akka` | Root-pom bump brought in a newer Akka; passport-cluster jars were built for the older one | **Revert the root-pom version** on the branch, then rebuild. **April:** root-pom `2610.0.4` reverted (PR #9662, LIT-664827). **Sept:** `2610.0.6` → `2610.0.7` (LIT-683538). A dev comment suggested using `DummyClusterSpringConfig` in the patch profile; left for LRE to decide | LIT-664827 (Apr 1), LIT-683538 (Sep 24) | **Yes: twice in 6 months, same class, same fix** |
| `CannotLoadBeanClassException: Cannot find class [<X>Impl] for bean '<y>'` in `<product>.spring.xml` | Product spring XML references a class whose release commit **was never pushed** (protected-branch push rejected, GH006) / not merged to the branch | Push/merge the missing release commit; redeploy | LIT-679733 (utoronto), LIT-682856 (acm, PR #14141) | Occasional |
| `Could not resolve placeholder '<prop>'` in `page-builder-2.xml` (`BeanDefinitionStoreException`) | "Another missing merge": a prop default was not merged into the maint branch | PR to the maint branch; reschedule | LIT-673061 (all stag on `lit-2610-maint-260609-…`) | Yes (missing-merge class) |
| `Failed to instantiate [OpenUrlBookFields]: Is it an abstract class?` | Bad commit (`fd9c6db8`) on 2410/2610 | Fix PR #11852, or revert (PR #11873). Reschedule the deployment workflows | LIT-673076, 673065, 673109 (lean-cip) | Once, many sites |
| `ClassNotFoundException … CmsPublicationsHandler` in `restApiService` | Class moved package; the prop value was not updated | Fix the class name in props (PR #9956) | LIT-665726 | — |
| `restApiService … CmsPublicationContributorsHandler … No qualifying bean of type PublicationService` | **PCMS-only REST handlers enabled on an LCMS site** (`api/rest/handlers/cms/subhandlers/{contributors,publications,customproperties}`) | Disable those props for LCMS (PR #14253); remove from `<product>.props.xml` | LIT-683233 (aiaa CIP), LIT-683407 (aiaa test, open) | Open Sep 2026 |
| `'productConfigurationService' … bridge-cms.xml … Constructor threw exception` | Props pair `string-based-versions-enabled` must match across files (both true or both false) | Change the prop (PR #12395), redeploy | LIT-674839 | — |
| `No qualifying bean … UrlService` in `readerConfigService`; `Relationship` init failures (`internalLiteratumCmsMoveEventDao` → `bridgeMetadataPopulationService`) | Beans excluded from the **`patch` Spring profile** break the dependents that remain. `Relationship` init swallows the real error ("look for 'failed to instantiate relationship' in the log files") | Dummy beans added to the `patch` profile (LIT-665205); code fix `f7fbae74` (LIT-667452) | LIT-665205, 667452/667462, 670926 | Patch-profile regressions recur |
| `semanticSearchMetrics … Could not resolve matching constructor` (ai.spring.xml) | **Side effect of the LIT-656000 build-time patch**: Java classes were patched but `ai.spring.xml`/`ai.spring.lcms.xml` were not | Patch file updated | LIT-656501, 661535 | Tied to the workaround |
| `payPalTransactionStatusUpdateRobot.Wrapper … Constructor threw exception` (NPE `LIT-604088 legacy singleton`) | Bean does work in its constructor before legacy singletons are set | Code fix | LIT-662389, 671390 | Twice |
| `'auditRetentionJob': Injection of persistence dependencies failed` | db-query-console change; LIT-CMS products only | PR #11547, merged to maint | LIT-671873 | — |
| `'queryConsolePoolRegistry' … Cannot get a connection using jdbc…` (CIP, newRelic pool) | Code: query console pool built for a pool that doesn't exist on CIP | Code fix, merged to maint `11ab1e47` | LIT-669506, 672323 | — |
| `'doFieldsLoader' … Constructor threw exception` | Unclosed XML tag in a DO fields file | PR #11235 | LIT-670681 | — |
| `'disqusController' / 'disqusService' … Constructor threw exception / null` | Code change (`00fe5cef`); LCMS needed a second fix | PR #11903 + #11923; maint merges | LIT-673096, 674391 (ARRS **prod**) | — |
| `'pdfInstructionService' … DefaultPdfInstructionService` | Site lacks `midtier.props.pdf.xml` after a PDF change | PR #11638 / #13476 adds the props | LIT-671949, 679270 | Twice |
| `'pdfService' … internalCmsXmlProcessor: Injection of resource dependencies failed`, deeper `Cassandra timeout during read query at consistency LOCAL_ONE` | **Cassandra**, not the bean (the real cause is far down the stack) | Restart / remove + redeploy that Cassandra cluster, rerun the patch | LIT-664113 (aami stag), LIT-677305 (sage test) | Yes |
| `frontendHtmlBlobStorage` (`bridge-blob-cassandra.xml`): `No node was available to execute the query` | Cassandra unreachable | (no stated fix) | LIT-671035 | — |
| `Cannot get a connection using jdbc:sqlserver://…` (patch VM) | (a) transient DB connectivity; (b) `Login failed for user '<site>'`: the DB login is missing on that SQL instance | (a) restart the deployment (LIT-683116); (b) DBA added the user (LIT-668876) | LIT-683116, 668876 | Occasional |
| `Initialization has timed out at 180000ms` | Misplaced `logging/dbUrl` inside the `dbPoolName` props | Props fix injected, deployment resumed | LIT-666178 (aha RO) | — |
| `RegistryException: Cannot find path: 'workflow/WfRobot/queueId'` (bks dies within 1 min) | Wrong WfRobot config in site props | Remove the bad config | LIT-665480 | — |

### 1b. ProductPatch — a patch ran and failed (`PatchProgram (<P>):Patch <litN> failed to execute`)

| Signature | Root cause | Fix / action | Tickets |
|---|---|---|---|
| `Error trying to initialize patch: ClassNotFoundException: com.atypon.patch.Patch0NNNNN` | Stub missing in **literatum-patch**, or present on master but **not merged to each maint branch**: all stag sites failed until it was | Add the stub (literatum-patch PR #512); merge to every `lit-2610-maint-*` / `lit-2410-maint-*` in use | LIT-683278, 683279, 683350 (lit32053), 671636 (lit32009) |
| `DbException: com.atypon.modules.migration.Patch0NNNNN` / `ClassNotFoundException` at `loadDynamicPatch` | Three stated variants: (1) Java class never added to the literatum branch (LIT-671636, PR #11562); (2) **host built from an outdated checkout** → re-schedule the workflow (LIT-671420); (3) **stale deployed dir**: class exists in git but is not in `patch.jar` → removed the deployed webapp dir on bks and re-ran (LIT-659138) | see cause | LIT-671636, 671420, 659138 |
| `IllegalAccessException … Patch031991 with modifiers "protected"` | Patch class constructor not public | Code fix (`82932b46`) | LIT-667486, 667482, 667548 |
| `Check Version: Missing prerequiste patch` | Dependency header missing / wrong | Fix the patch header (literatum-patch PR #296), or apply the prerequisite first | LIT-659331 |
| `ReadOnlyException` (no message) | Patch saves/deletes a read-only entity. lit30622: `Patch030501` saved a license with a read-only group as userID → code fix: `isReadOnly()` is false for new (non-persistent) licenses (PR #11788). lit31969: code fix PR #8635 | Interim: skip the patch, run the full patching, fix code later | LIT-671570, 661680, **lit31650: LIT-672294 (Jun, "Fixed"), LIT-660575 (CIP aua), LIT-683499 (wspc, open Sep 24)** |
| `NotFoundException: No data available` | Site data does not have what the patch expects (duplicate user already gone; DO group) | **Skip the patch** (LIT-673527), or start the bks and run just that patch, then the full patching (`patch.py -p <P> --families <F> -f <litN> -v`) (LIT-681536) | LIT-673527, 681536, 656501 |
| `There is already an object named 'dim_article' / 'user_tag'` (lit31783 dimension copy) | Earlier partial run / timeout left tables | Admin JSP running `Patch031783` with `setOverwrite(true)` for the remaining tables, then **mark the patch as applied in `db_version`** and continue | LIT-666241 (Thieme live), 668153 (ux3/lean prod), 671527 (pericles prod), 671791 (was prod) |
| `Cannot find the object "dim_person_user"` (lit32030) | Dim tables never created on nonprod | Create them via JSP (LIT-675757); then the patch got a table-exists check (literatum-patch PR #455) | LIT-675757, 676025 |
| `Invalid column name 'propertyuri'` / `'propertyUri'` | Column dropped by an earlier patch (replaced by `propertyId`) | Fix the patch (PR #463); merge to the physio migration branch | LIT-677585, 677711, 677618 |
| `Invalid column name 'FACTORYID'` (lit32009) | lit32010 (drops the column) ran before lit32009 on that env: ordering problem | Open (reopened) | LIT-678891, 672293, 672674 |
| SQL syntax: `Incorrect syntax near …` / `sp_rename … ambiguous` / duplicate index name / FK conflict | Patch SQL bug (stray semicolon; copy-paste index name; FK) | Patch fix PRs (literatum-patch #351/352, #420, #422) | LIT-679196, 678526, 666040, 674834 |
| `Invalid object name 'LINK_RECORD_USER'` | Feature disabled on the site → the creating patch never ran | Add `--@boolean_property_parm="features/identity/enable-LinkRecord"` gate to the patch (PR #290) | LIT-658321 |
| `Taxonomy with code legacy-categories is not found` | Site-data prerequisite missing | Mark lit31986/31987 **reserved** (PR #353); skip on that site | LIT-666394, 671635 |
| `ReasonerWriteFailureException … NotFoundException` (lit9430) | Needed the running bks | Start the bks, run the single patch, then full patching | LIT-681536 |

### 1c. ProductBuild

| Signature | Root cause | Fix | Tickets |
|---|---|---|---|
| `compileJava FAILED` after a **forward merge 2410→2610** (`javax.persistence does not exist`, `javax.annotation.CheckForNull`, `getLock()`, `package …dodeprecated does not exist`, ctor arg mismatch) | Change valid on 2410 but not on 2610 (jakarta vs javax, removed APIs) | Revert or fix PR on 2610 (PR #13298, #13094, #12014, #12365) | LIT-679022, 678988, 678015, 673585, 673748, 675013, 679265 |
| `constructor RestApiAction … required: RestApiService found: RestApiService,RestMetrics` | **Build-time patch (`platform-tools/patch/common.patch.txt`) changes the `RestApiAction` signature**; product subclasses (Pericles) break only on the tools host, not locally | Add the product file to `common.patch.txt` (platform-tools PR #318) | LIT-676391, 681472 |
| Same ctor error on **all stag + beta** (Sep 13) | PR #13938 (LIT-682051 metrics work) | Fix per branch; on 2610 revert #13938 | LIT-682252 |
| `LIT-656000: applying literatum-master patch file ~/scripts/patch/master.patch.txt` → **Python Traceback in `rebuild.py`** (build fails, not silent) | Patch file no longer applies (Feb 2026 variant of the workaround) | Patch file fixed (LIT-659896) | LIT-659896, 659952, 659956 |
| `GaiaMetricsService.getInstance()` cannot find symbol | Patch was checked in for master only, not lit-2610 | Check the patch into lit-2610 too | LIT-660354 |
| Divergent `sourcegit` checkout (`hint: Pulling without specifying…`) on CIP | Local drift on tools host | `git reset --hard HEAD; git clean -df` in the worktree (LIT-659896) | LIT-659896 |
| "Local changes" in `literatum-worktrees` on tools | **Expected**: `rebuild.py` applies `common.patch.txt` (2610+). Resolved "Expected Behavior" | none | LIT-676465 |
| Flaky `ant:iajc` warnings then failure | Transient | "ran successfully after multiple schedules" | LIT-676454 |
| `cannot find symbol ADVISER` (was beta, master) | Dependency pin (already in SKILL.md) | open | LIT-683506 |

### 1d. ProductBuildStyleguide

| Signature | Root cause | Fix | Tickets |
|---|---|---|---|
| Status table row `'<…>/ui-products/<p>' │ 'inProgress' │ 'NA ms'` (the most common SG ticket text) | Often **transient**, sometimes a real SCSS/webpack error hidden above the table | **Re-run once**; several closed as "fixed after rerun" / "build succeeded when rechecked". A reporter recommended deploying SG twice before filing. Real cases: SCSS `@extend .text-reset` target removed by the ui-theme v2.8.79 bump (aha, LIT-674619); per-product fixes merged to the `maint-*` ui-products branch (LIT-674621, 681106) | LIT-674543/674549/674619/674621/674623/675056/675057/675754/677959/678352/673336/673867/674267/674268/673370 |
| `Build Failed For The Following Products - [app]` | App-specific UI change | Fix merged to `maint-260901-581e6c66` | LIT-683350, 683436 (open) |
| `Failed to run post install script … bash ./postinstall.sh: No such file or directory` / `Error Installing Package @types/styleguide … mv node_modules` | Package/versioning change in ui-products | "versioning issue … resolved; please redeploy" | LIT-672963, 672895 |
| Marlin stag/test repeated failures | utypon-cli version on CIP/stag outdated | Change so CIP uses the latest utypon-cli | LIT-681645 (open), 680822, 673347 |

### 1e. Service deploys (ansible-actions)

| Step / signature | Root cause | Fix | Tickets |
|---|---|---|---|
| Pugrenderer: `Error [52] while pulling repository` + `hint: Pulling without…` / `refusing to merge unrelated histories` | Local ansible checkout on the tools host **diverged** from origin (12 local vs 360 remote commits on `4.1`) | On the tools host: `git reset --hard origin/4.1` in `~/apps64/ansible/pugrenderer/4.1`, restart deployment | LIT-646362, 647949 |
| ProductIngestionDeploy: git error, reschedule not enough | Checkout of `~/apps64/ansible/ingestion/main` left on a **deleted feature branch** (`LIT-656618`) | Delete the branch, switch to `main` | LIT-661926 |
| SolrDeploy: `Error [53] while running dynamic inventory … No JSON object could be decoded` | **deployconf typo** | deployconf fix (PR #2890) | LIT-682553, 675880 |
| SolrDeploy: `Fail if term-synonyms folder is missing` (`/publisher/common/journals/lucene/termSynonyms_*`) | Broken `lucene` symlink | Copy from `/na101/home/literatum/publisher/common/.snapshot/hourly.<ts>/` | LIT-674295 (beta+stag) |
| SolrDeploy: `pull Solr image (remote)` fails after lock wait; Solr/ZK bootstrap errors on 2610 | ansible-solr `19.0` = Solr 9.1.1, but 2610 ID code needs Solr 9.10.1 | `-e deploy_version=19.1`; deployconf sets `deploy_version=19.1` for 2610+ sites (PR #2787, #2798) | LIT-673210, 673358, 673650 |
| SolrDeploy: `cannot verify download.indexdata.com's certificate` (docker build) | CA certs in the image | `update-ca-certificates` added to the 19.0 Dockerfile | LIT-673326 |
| SolrDeploy: `ServiceConfigurationError … Lucene94Codec could not be instantiated` | Lucene version mismatch (CIP) | (duplicate, no detail) | LIT-674567, 675000 |
| SolrDeploy: `list object has no element -1` in `run_consumer_handlers` conditional | Publisher FS missing after the MR branch update | Recreate the FS | LIT-681656 |
| HostDeploy on master CIP after a `searchVersion` bump | root-pom Solr/Lucene versions not aligned with 9.10.1 | root-pom PR #74, new root-pom release | LIT-663949 |
| ProductConsumerDeploy (LTS): validate step fails | **Kafka cluster pointed at a ZK 3.7.1 cluster (prod uses 3.5.8)** | Remove the Kafka cluster, switch to the right ZK, redeploy | LIT-681222 |
| Proxy-solr build fails | `proxy_solr_version` must be `core-2610.0.11` for 2610 | Workaround deploy version `4.1_test_4` in ansible-proxysolr | LIT-673235 |
| ZK node down (alert) / ZK deploy fails | Node container down | `ansible-actions -s zookeeper -n <cluster> -a deploy` | LIT-674304, 677512 |
| GaiaDeploy blocks stag | not stated | open | LIT-683468 (HOPE, open, no comments) |

### 1f. Cassandra (bks/web start and patch-VM)

| Signature | Root cause | Fix | Tickets |
|---|---|---|---|
| Web/bks fail at `getOutputCacheFactory` + `prepare`; cassandra restart fails `Validate node is up` (`SELECT bootstrapped FROM system.local`) | **Pericles prod `gaia_pericles_live` had 22k→45k tables** (a tool created cache tables concurrently). Schema DDL conflicts → gossip schema drift → cluster unusable | Disable the cache in that tool; the cluster was not responding, so SRE **backed up PIM data, recreated the cluster, restored PIM** | LIT-670168, 671012, 670279 |
| Stag deployments failing; `stag-cassandra-1-1` unreachable | Too many tables (`asmj_beta_frontend_html` 8.9k, etc.) | Remove + redeploy the stag Cassandra clusters; ask for the prod cleanup job + monitoring on stag | LIT-678350 |
| `InvalidQueryException: table abstract_<p>_<id> does not exist` floods logs (700k+) | Gaia cleaner cron (tools-6, `/tmp/literatum_gaia_cleaner.<date>.log`) failed mid-run; tables/snapshot mismatch | ansible-cassandra 5.1.3: `DROP TABLE IF EXISTS` (PR #169) | LIT-681676, 682047 (open) |

**Relevance to the informs `table_index does not exist` case (inferred):** in the tickets, "does not exist" / schema problems on Gaia keyspaces go together with **very high table counts and schema-version drift**. The next read-only check is the table count in `gaia_informs_beta` plus `nodetool describecluster`.

### 1g. HostStart / HostDeploy / HostWaitForWebServer

| Signature | Root cause | Fix | Tickets |
|---|---|---|---|
| HostWaitForWebServer: `SQLGrammarException … Invalid column name 'PAGE_REMOVED' / 'DROPZONE_ORDER'` | **DB not patched** (lit31745, lit31595 missing), not a PB code bug | Run the missing patches, restart | LIT-666058 (many stag); LIT-678414 (beta: fine after a normal restart) |
| `Null value was assigned to … MoveWidgetJpa.implicit` | Site edited with the old code while the table-consolidation patch ran | Data fix by the PB team | LIT-664072 (gsl stag) |
| `Failed to find mapped publication by revision N and WebArea 1. Try to load by PII` | Wrong collection mapping in the data | `backstage.sh process.marlin.mapOrPopulateMeta -C <collections.txt>` (collection code from `cms_object_rev.ObjectUri`); repeat per new revision | LIT-671401 |
| Web stuck after `Rdf2Go Bootstrap completed` (no error) | `CmsCacheWarmup` deadlock during Spring startup (PCMS sites) | Code fix; redeploy | LIT-659811, 659871, 660091 |
| `ERROR LOADING PRODUCT` at web start, same bean errors as 1a | same as ProductPatch | same | LIT-660383 → 660388 |
| HostStart: `Error copying jar … atypon-pyroscope-agent-latest.jar` → `restart.py` Traceback | Agent jar/symlink missing on the host | SRE added the agent dir on all cipsc VMs | LIT-657818 |
| HostStart hangs/fails (CIP) | `-XX:+ShowMessageBoxOnError` in deployconf web JVM args → JVM waits for input on a headless server | Remove it (deployconf PR #2864) | LIT-675386 |
| HostStart fails on all RO sites | `systemd="true"` in RO deployconf | Remove it (deployconf PR #2499) | LIT-664700 |
| HostStart RO: `checkMountPoint.sh … Permission denied` / `is busy or already mounted` | Missing tomcat web server in deployconf + outdated otel agent | deployconf PR #2597 | LIT-667606 |
| HostDeploy: `UnsupportedClassVersionError … class file version 65.0 … up to 61.0` | 2610 needs Java 21; platform-tools `JAVA_HOME` still pointed at java17 | platform-tools PR #222/#223 | LIT-655908 |
| HostWaitForWebServer on CIP, all sites | AUTH-1202 (auth regression) | Fixed in AUTH | LIT-652368, 652440 |

### 1h. ProductDBUpgrade / RunCLI

| Signature | Root cause | Fix | Tickets |
|---|---|---|---|
| ProductDBUpgrade fails at **1 h timeout** (liquibase `Column names … specified more than once` is logged but `failOnError=false`, so it is not the cause) | Long upgrade on a loaded SQL server | Restart the SQL server, **remove the upgrade lock file**, reschedule (took 49 min) | LIT-683096 (pericles 26.1) |
| ProductDBUpgrade stuck at `Initializing Server`, then force-failed by the DS | Spring startup hang; fix commit missing from the freshly cut 2610 branch | Back-port to lit-2610 (PR #6720) | LIT-656200 |
| RunCLI `AddAtyponIPsToAtyponInstitution` fails / hangs after `ShutdownManager` | Tool bug on 2410 and 2610; the 2610 part was fixed in July (PR #12756) but it failed again in Aug/Sep | Fix in progress (LIT-682969, In Progress Sep 24) | LIT-676602 (open), 682969 |

---

## 2. Not yet in `failure-signatures.md`

1. **`Error creating bean with name 'robotsExposer'` / `LIT-604088: legacy singleton has not been set yet`** hides the `clusterMetrics` null NPE (LIT-683431 family). It showed on **utb PROD bks on 2026-09-23** (LIT-683467). Fix = rebuild + redeploy.
2. **`[ClusterMutexManager] Failure to load ClusterMutex class …` inside an `Executing patch` block (lit31708, lit9529)**: the same root, surfacing as a patch failure rather than a VM-start failure.
3. **The Akka NoClassDefFound recurs**: root-pom `2610.0.4` in April (LIT-664827) and `2610.0.6` in Sept (LIT-683538). Fix both times = revert the root pom. Worth a "check root-pom bumps in the last 48 h" step.
4. **History of LIT-656000 workaround failure modes**: (a) Python Traceback in `rebuild.py` = hard ProductBuild failure (Feb); (b) compile errors *caused by* `common.patch.txt` (RestApiAction ctor in product subclasses; `GaiaMetricsService.getInstance`), reproducible only on tools hosts; (c) partial patching (Java patched, `ai.spring.xml` not) → `semanticSearchMetrics` bean error; (d) maint branches need a different patch file; (e) local diffs in tools `literatum-worktrees` are expected. All moot after PR #354, but relevant for builds made before 2026-09-25.
5. **"Cassandra hidden under a bean error"**: `pdfService … internalCmsXmlProcessor: Injection of resource dependencies failed` → scroll to `ReadTimeoutException … LOCAL_ONE`. Fix = redeploy that Cassandra cluster, rerun the patch.
6. **Gaia keyspace table explosion** (22k–45k tables) → schema drift, cluster unusable, `Validate node is up` fails. Fix = recreate the cluster + restore PIM. Stag has the same risk (`*_beta_frontend_html`).
7. **Patch-VM DB login**: `Cannot get a connection …` → transient (restart) vs `Login failed for user '<site>'` (missing DB login, DBA).
8. **Patch-VM Spring-bean regression list** (1a table): missing merge / unpushed release commit (`CannotLoadBeanClassException`, `Could not resolve placeholder`), PCMS-only REST handler props on LCMS sites, `patch`-profile bean exclusions, and the literatum.log hint for swallowed `Relationship` errors.
9. **Three variants of `ClassNotFoundException: com.atypon.modules.migration.PatchN`** (not in branch / outdated host checkout → reschedule / stale deployed dir → remove the deployed webapp dir). **Stub missing on a maint branch** takes down *all* stag sites until merged.
10. **Patch SQL failure catalogue**: `already an object named` (partial earlier run → JSP overwrite + mark applied in `db_version`), missing nonprod tables, dropped-column references, ordering (lit32009/lit32010), feature-gated tables (`boolean_property_parm`), site-data `NotFoundException` → skip the patch.
11. **Ops workarounds used on patches**: skip the failing patch then run the full patching; run one patch with `patch.py -p P --families F -f litN -v`; mark reserved; mark as applied in `db_version`. These need a patch-owner OK, so hand them over as recommendations.
12. **`IllegalAccessException … modifiers "protected"`** on a migration patch (non-public ctor).
13. **Styleguide `'inProgress' 'NA ms'` status row** is the common SG failure text. Re-run once before diagnosing; real causes are SCSS (`@extend` target removed by a ui-theme bump), `postinstall.sh` missing, utypon-cli version.
14. **Ansible local checkout drift** variants: diverged branch (`git reset --hard origin/<ver>`), checkout on a deleted feature branch (ingestion).
15. **Solr on 2610 needs `deploy_version=19.1`** (Solr 9.10.1); symptoms: image pull / ZK bootstrap errors, `Lucene94Codec` ServiceConfigurationError. Also: term-synonyms broken symlink (restore from `.snapshot`); docker CA certs; publisher FS missing → `list object has no element -1`.
16. **ConsumerDeploy on LTS: Kafka on the wrong ZK version** (3.7.1 vs 3.5.8).
17. **HostWaitForWebServer `Invalid column name 'PAGE_REMOVED'/'DROPZONE_ORDER'` = unpatched DB** (check `db_version` before blaming code). Also `mapOrPopulateMeta` for "Failed to find mapped publication by revision".
18. **Web stuck after `Rdf2Go Bootstrap completed`** = CmsCacheWarmup deadlock (take a thread dump).
19. **HostStart deployconf JVM-arg traps**: `-XX:+ShowMessageBoxOnError`, `systemd="true"` (RO), missing tomcat/otel agent; pyroscope agent jar missing → `restart.py` Traceback.
20. **HostDeploy `UnsupportedClassVersionError` 65 vs 61** = wrong JAVA_HOME for the branch (java17 vs 21).
21. **ProductDBUpgrade 1 h timeout** → SQL restart + remove the lock file + reschedule. Liquibase "failed, but failOnError was false" lines are noise.
22. **Owner-finding convention** in these tickets: Ops opens the ticket, names the last commit on the failing file (from the first project frame in the stack), and assigns its author. Resolution = PR on the branch + "please redeploy/reschedule". The skill could emit that line directly.

Open / unresolved as of 2026-09-25: LIT-683499 (lit31650 ReadOnlyException, wspc), LIT-683468 (HOPE GaiaDeploy), LIT-683407/683233 (aiaa PCMS REST props), LIT-683436 (app-stag SG), LIT-681645 (marlin SG), LIT-678891 (lit32009 ordering), LIT-682969/676602 (AddAtyponIPs tool), LIT-682047 (missing Gaia tables log flood), LIT-683431 (reopened), LIT-683506 (was ADVISER).

---

## 3. Confluence runbook links (read-only search)

No current, dedicated "Deploy Server failure runbook" was found. What exists:
- DeployServer Deployments and Essential Tests (DevOps, 2019). HostWarmupTest fails on a scenario timeout (default 20 s, 1 retry). Override in the warmup test file with `<warm-up retry="0"/>` / `<warm-up timeout="90"/>` (LIT-280388). HostEssentialTest is prod-only and must be cancelled manually on failure: https://atypon.atlassian.net/wiki/spaces/DevOps/pages/62134329
- Deploying CIP Environments (AM): https://atypon.atlassian.net/wiki/spaces/AM/pages/73083508
- QAA automation [Runbook] (DevOps, CIP DS actions): https://atypon.atlassian.net/wiki/spaces/DevOps/pages/62139205
- Troubleshoot deployment (QAA, 2018, CI Solr/Consumer → Service-Recreate): https://atypon.atlassian.net/wiki/spaces/QAA/pages/69317132
- Runbook to restore dockerized services after a server replacement/failure (DevOps): https://atypon.atlassian.net/wiki/spaces/DevOps/pages/62144783
- Deploy Server - Merging revisions (TF): https://atypon.atlassian.net/wiki/spaces/TF/pages/79152754
- Rundeck-Deployserver integration (DevOps): https://atypon.atlassian.net/wiki/spaces/DevOps/pages/62144081
- 2020-07-21 deployment-failures meeting notes (DevOps): https://atypon.atlassian.net/wiki/spaces/DevOps/pages/62144977
- Referenced from tickets (not opened): Link Records Migration Instructions (Mig space, page 64358045); "26.1 Bringing up Deployments of Midtierbeta sites for 26.1 incremental features" (LEN space, page 370344879).

---

## 4. Coverage: queries run and hit counts

All JQL used `project = LIT AND created >= -365d`. "50+" = first page full (hasNextPage=true); only page 1 was listed.

| # | Query (text / summary) | Hits | Signal |
|---|---|---|---|
| J1 | text "KILLING THE SYSTEM" | 50+ | high |
| J2 | text "failed to execute" AND patch | 50+ | high |
| J3 | text "ERROR LOADING PRODUCT" | 50+ | high |
| J4 | text "BUILD FAILED" | 50+ | high (mixed) |
| J5 | "No warfile" OR "LIT-656000" OR "patch failed, reverting" | 25 | high. **No ticket about `No warfile` itself** |
| J6 | ProductBuildStyleguide / PugrendererProductDeploy / HostDeployStyleguide | 50+ | noisy (release-plan tickets) |
| J7 | GaiaDeploy / GaiaCompatibilityCheck | 50+ | **noise**: only LIT-683468 is a failure ticket |
| J8 | SolrDeploy OR (zookeeper AND deploy) | 50+ | medium |
| J9 | ProductConsumerDeploy / ConsumerDeploy / kafka+"deploy failed" | 50+ | noisy, 1 real (LIT-681222) |
| J10 | table_index / cassandra+"does not exist" / summary cassandra+deploy/patch/schema | 50+ | noisy, ~6 real |
| J11 | "Error [51..54]" OR "Permission denied (publickey)" | 6 | **no publickey resolution ticket found** |
| J12 | summary HostStart/HostWaitForWebServer/Warmup/HostDeploy/HostStop/EssentialTest | 20 | high |
| J13 | "Force connection close" OR summary RunCLI OR RunCLI+hang | 6 | low (no RunCLI-hang ticket besides LIT-682969/676602) |
| J14 | NoClassDefFoundError AND (patch/backstage/deploy) | 24 | 1 relevant (LIT-664827) |
| J15 | ReadOnlyException | 25 | ~6 relevant |
| J16 | summary gaia/consumer/kafka/pugrenderer/"zookeeper deploy" + fail/down/error | 40+ | mostly monitoring alerts |
| — | Detail fetch: 8 `key in (…)` batches, ~190 tickets | — | digest read as described at top |
| C1 | Confluence: title "deploy server"/deployserver or text URL, AND failed/troubleshoot/runbook | 6 | 2 useful |
| C2 | Confluence: text ProductPatch/ProductBuildStyleguide/HostWaitForWebServer/ansible-actions/KILLING THE SYSTEM/patch.py (since 2024) | 39 | noise (meeting notes, reports) |
| C3 | Confluence: title troubleshoot/runbook/failure/how to fix + deploy + patch/backstage/styleguide/ansible | 30 | mostly client onboarding runbooks; 3 useful |

Gaps: nothing found in Jira on how `Permission denied (publickey)` / `Error [52]` with an auth error was resolved; nothing on HostWarmupTest failures beyond the 2019 page; GaiaCompatibilityCheck has no failure ticket. Tickets in other projects (AUTH, LEAN, DOC) and in `jira.prod.atypon.com` links were not followed.
