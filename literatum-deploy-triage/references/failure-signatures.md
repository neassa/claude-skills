# Failure signatures by layer

Sources (in `../literatum-platform/references/deep/`): notes 02 (platform-tools), 03 (ansible), 04 (patch system), 05 (build/Gaia), 06 (deployconf/ui-products). Each note has the full table with file:line. Classes: CODE, DEP (dependency pin), PATCH-CODE, PATCH-DATA, PATCH-VM (startup), CRED (keys/tokens), SVC (infra service health), CONF (deployconf), HOST (process/host), TRANSIENT.

## How to find the real error
- Read after the last `(ssh) <command>` line. Skip `warning:` lines and git `hint:` lines.
- Build/patch: use the `* What went wrong:` block and the first `: error:` under `compileJava`, or the first `Caused by:` under `Executing patch <name>`. Not the first line containing `error:`.
- Ansible: the last `fatal:`/`msg:` before `COMPLETED FAILURE`, plus the wrapper's `Error [5x]` line.

## ProductBuild (platform-tools `setprod` → `sync_branches.sh` → `rebuild.py` → gradle)
| Signature | Meaning | Class |
|---|---|---|
| `: error: cannot find symbol` … `> Task :literatum:compileJava FAILED` / `BUILD FAILED` / `Build failed!  Output is in /var/tmp/…` | compile failure — check the last commits on the file and the dependency pins | CODE or DEP |
| `Branch <X> doesn't exist in patch repo` | non-plain lit branch without a same-named literatum-patch branch | CONF |
| `ERROR: Patch directory is not a valid git repository` | broken `$ATYPON_HOME/patch` symlink | HOST |
| `Failed to aqcuire build-lock` / `see LIT-246176` | concurrent build or stale `.build.lock` left by a killed build | HOST |
| `LIT-656000: literatum-master patch failed, reverting...` (2026-09-23→25: every lit-2610 build, after `b441c1f0` LIT-683070 changed ActionController/RestApiAction; fixed in git by `3b5d53c2` 2026-09-25) | build-time source patch failed; **build continues unpatched and can show Success** → later startup NPE (LIT-683431) | CODE (silent) |
| `No warfile was found for '<P-F>'` (in the later HostDeploy) | build "succeeded" but the WAR copy failed after renaming the old one | HOST |

**Status 2026-09-25 13:25 UTC:** platform-tools PR #354 removed the LIT-656000 workaround from `rebuild.py` (no more build-time patch, no more `LIT-656000:` lines). The metrics revert is in git on `lit-2610` and on every stag/prod maint branch in use (commits 2026-09-25 12:32–13:08 UTC). **It is NOT on `master`, `lit-2610-acc-260705` or `lit-2610-physio-pcms-260706`**: they still have `clusterMetrics = null; // TODO revisit after LIT-643926` in `PassportClusterMetricsProvider`, and beta's `midtier.props.IBM-beta.xml` selects `PassportClusterMutex`, so their next builds are exposed to the LIT-683431 startup NPE (beta was-W, acc-A32, physio-C8; not yet observed). To re-check a branch: grep that file at `?ref=<branch>`.

## ProductBuildStyleguide / HostDeployStyleguide (ui-products via `Build-Deploy-Styleguide.sh`)
| Signature | Meaning | Class |
|---|---|---|
| `Error - Failed to Build The Product ,,, Exiting - Exit code: 1` | utypon build log lacks `All Products Have been Built Successfully` | CODE |
| `PRODUCT MISSING OR NOT FOUND,Please check your script parameters-deployconf for GROUP,PRODUCT NAME` | product dir missing in ui-products | CONF |
| `ERROR: [<g>] group is missing` / `[styleguide.info] is missing` / `[<bundle>.tar] is missing` | packaging failed | CODE/HOST |
| `utypon: command not found` → `Failed to Build` | global utypon install failed (`@latest` on beta/stag) | TRANSIENT/DEP |
| `BUILD COMPLETED` | printed unconditionally — not proof | — |

## PugrendererProductDeploy (**delivers the styleguide**; `ansible-actions -s pugrenderer` → atypon/ansible-pugrenderer 4.0/4.1) — details in notes 07
| Signature | Meaning | Class |
|---|---|---|
| `Object styleguide_new<USER>_<P>_<F>.tar.gz is not found in FTP Server or Defined Path. releasedAssets deployment … has failed` | no tarball in `~/warfiles` → look at ProductBuildStyleguide (its mv is unchecked) | CODE/HOST upstream |
| `create-paths : Invalidate styleguide caches` non-200 | renderer node/container down | SVC |
| `validate : Validate service is up (TCP Check)` timeout | container not listening | SVC |
| `released-assets : Validate Released Assets` fails (10×60 s) | renderer can't serve `css/build.css` / `c=payment` for the SG branch | CODE/SVC |
| `released-assets : Update product map` non-200 | `/refreshProducts` rejected | SVC |
| Deploy Success but site shows old/missing styleguide | renderer caches (no TTL, incl. cached 404s) not invalidated on some node, product not discovered (no `scss/build.scss` in the tarball), or wrong branch dir. Evidence: `GET http://<node>:<port>/info?p=<P>&v=<SG branch>` shows the served build's git hash (renderer = atypon/styleguide-render-pug, notes 08). App logs are in `docker logs <cluster>-<port>`. | SVC/CODE |
| Styleguide renders wrong / 404 only on rmit or aaas (V2.4.0 clusters) | older renderer: no amps/life-core/ui-base inheritance, no nested widget paths, no gql templates | CODE (renderer version) |
| Cluster-level `pugrenderer` deploy fails at `Checkout git@github.com:atypon/styleguide-render-pug.git` for `staging-pr-amps` | deployconf asks for `UI-Renderer-V2.7.0`, which does not exist | CONF |

## ProductPatch (platform-tools `patch.py` → `run_gradle.sh` → patch VM `DbGradlePatcher` → `DbPatchSystem`)
| Signature | Meaning | Class |
|---|---|---|
| `ERROR LOADING PRODUCT <p>` … `KILLING THE SYSTEM` with `BeanCreationException … getOutputCacheFactory … GaiaFeBeans` + `AllNodesFailedException` / `InvalidQueryException … table_index` | Gaia Cassandra cache built eagerly at patch-VM Spring startup; Cassandra unreachable / node wedged / schema disagreement. **No patch ran.** | PATCH-VM / SVC |
| `KILLING THE SYSTEM` with DB-pool / Akka / Kafka cause | other eager bean failed | PATCH-VM / SVC |
| `Error trying to initialize patch: java.lang.ClassNotFoundException: com.atypon.patch.PatchN` | stub missing in literatum-patch (e.g. LIT-683278) | PATCH-CODE |
| `NoClassDefFoundError: akka/actor/typed/scaladsl/adapter/package$UntypedActorSystemOps$` at `RobotManager_Akka` → `KILLING THE SYSTEM` | Akka runtime ≠ what passport-cluster jars were built for — check `parentPomVersion` (root-pom akka.version) vs `passportClusterVersion` in the build's revision (root-pom 2610.0.6 = Akka 2.6, 2610.0.7 reverted) | DEP |
| `ClassNotFoundException: com.atypon.modules.migration.PatchN` at `DbPatch.loadDynamicPatch` | target class missing from that branch's literatum build | PATCH-CODE |
| `PatchProgram (<P>):Patch <litN> failed to execute` + a `Caused by:` | a patch threw; the DS schedules BrokenPatchBlame | PATCH-CODE / PATCH-DATA |
| `ReadOnlyException` (no message) in a Java patch | entity read-only: CR-marked fields, or member of a read-only group, or holder is. Not site RO mode (that's `WriteDeniedError`). | PATCH-DATA |
| `ReadOnlyException: cannot delete cache entity` | patch modified a cached entity | PATCH-CODE |
| `DB version X doesn't equal your build version Y … -R` | release gate; run DB upgrade or `-R` | CONF |
| `Check Version: Missing prerequiste patch` | dependency not applied | PATCH-CODE |
| `java.lang.Error: Invalid patch parameter: <key>` | header typo in any patch file; kills the whole run | PATCH-CODE |
| `Patch <n> is reserved, use -F` | reserved patch requested (may hang the JVM) | CONF |
| `****** Core Content Bootstrapping FAILED ******` | passport content fix failed before patches | PATCH-DATA |
| `please add '--families={family name}' to patch` / `not found in deployconf.xml` | patch.py exited 0 without patching | CONF (silent) |
| `Patch failed!  Output is in /var/tmp/<epoch>.txt` | patch.py saw `FAILED`/`KILLING THE SYSTEM`; full output is that file on the backstage host | — |

## HostDeploy / HostStop / HostStart (platform-tools `redeploy.py` / `restart.py`)
| Signature | Meaning | Class |
|---|---|---|
| `No warfile was found for '<P-F>'` | no WAR in `~/warfiles` | HOST (from build) |
| `Akka Zookeeper version 3.5+ (found X) is required` | inventory ZK too old for the branch | CONF |
| `Java Result:` present / `Finished deploying product` absent | deploy failed | HOST |
| `err.DeployErr` in HostStart | start failed | HOST |
| `There is a file system mount failed!` | no mount points found | HOST |
| `Failed to execute <wrapper> start…` | backstage wrapper already running | HOST |
| `***<type> NOT STARTED***` (in `<proc>.out.log`) | no JVM args for the process in deployconf | CONF |
| `ERROR : Java Cryptography Extension is NOT installed` / cert not found | wrong JDK / cacerts | HOST |
| HostWaitForWebServer timeout / HostWarmupTest failure | app did not come up even though HostStart passed | CODE/CONF/SVC |

## Service deploys (`ansible-actions -s <svc>` → `atypon/ansible-<svc>`)
| Signature | Meaning | Class |
|---|---|---|
| `Error [51] while cloning repository.` | branch `deploy_version` missing, empty version, or SSH key | CRED/CONF |
| `Error [52] while pulling repository` + `Permission denied (publickey)` | tools-host account SSH key can't read the repo | CRED |
| `Error [52]` without auth error | dirty/diverged checkout or tag checkout | HOST |
| `WARN [Skipping updating the repo.]` | concurrent pull → **stale playbooks ran** | TRANSIENT (silent) |
| `Error [53] while running dynamic inventory.` | deployconf unreadable/invalid | CONF |
| `Error [54] … atypon_lifecycle.json` / `NameError` traceback | GitHub token/network | CRED/TRANSIENT |
| `argument -n/-p: invalid choice` (exit 2) | product silently dropped from inventory (swallowed exception, missing cluster ref) | CONF |
| solr: `Zookeeper cluster is not available` / `… version … mismatch` / `ERROR: Bootstrap action failed` / `FAILED - RETRYING: Ensure node is alive and all cores are active` (up to 2 h) / `Wrong number of nodes` / lock timeout | ZK or Solr health; consumers may stay **paused** | SVC |
| consumer: `Consumer and Searchservice share the same ports` / `FAILED - RETRYING: Get ping status` / `Task failed and lock file cleanup completed` | port conflict / app didn't start / image build failed | CONF/SVC |
| cassandra: `Validate node is up` retries / `Not allowed to run this action for a product` | node not joining / wrong target | SVC/CONF |
| redis: `Error on cluster create` / `is not ready yet to accept operations` | cluster create / load | SVC |
| gaia: `'force_recreate' is undefined` / `version_check.status != 200` / `could not locate … puppet-gcp-key.json` / `No such container` | missing extra var / bundle not published / key missing on tools host / docker socket | CONF/HOST |

## deployconf-side (can break any step)
- PR gate only checks well-formedness; the XSD check runs after merge and always prints success; auto-update workflow pushes straight to `main`.
- Silent inventory drops (missing `<solr>` for consumer, misspelt `kakfa_cluster_name` is the one that works, undefined cluster names).
- Known anomalies: prod chrysalis → undefined pugrenderer cluster; prod `was` family `w` (vs `W`); prod cassandra-pim-literatum3 lists a literatum4 node.

## Seen live 2026-09-25 (beta/stag)
| Signature | Meaning | Class |
|---|---|---|
| ProductPatch: `NullPointerException: Cannot invoke "…PluginMetrics.timer(String)" because "this.clusterMetrics" is null` in `ClusterMutexManager` (`Failure to load ClusterMutex class from registry cluster/mutex/clusterMutexClass`) | **LIT-683431 crash** caused by an **unpatched build** (ProductBuild green with `LIT-656000 … patch failed, reverting`). acm beta, build `lit-2610` `f2f5130a` (before the in-git revert 2026-09-25 09:00 UTC). Fix: fresh build from a branch that has the revert. | CODE (silent upstream) |
| SolrDeploy `fatal: … FAILED!` followed by `...ignoring` | probe tasks (container running/remove checks) — **not** a failure | — |
| RunCLI `AddAtyponIPsToAtyponInstitution`: `ERROR ACS [main] - Invalid IP address!` (×N), then `ShutdownManager: Shutdown begins`, then `Exception in thread "main" … DbException: Missing max ip address` (thrown **after** shutdown began), then days of background-thread logging (`DefaultPublicationEventProcessor … Read timed out`), ends `Force connection close` → Failure | An IP in the operator's input file that `InetAddress.getByName` can't parse → `IPAddressUtil.getCanonicalIP4/6` logs "Invalid IP address!" and returns null → max=null → DbException. The whole run is one `Transaction.execute`, so nothing was added. The JVM then never finishes shutdown (known **LIT-682969**, ShutdownManager/JDBC-pool timing). The action sits **Executing for days** and only appears in a Failure search once the DS closes it. The close is the **idle TTL**: every SSH read resets `lastLive` (JschConnection → `ConnectionCleanup.connectionLive`), and `DeployDaemon` → `cleanupConnections()` force-closes when `now - lastLive > getActionTimeout(type)` (default `connection.idle.ttl`=1h unless `timeout.<Type>` is set). Stag pericles 2026-09-25: last output ~03:06, closed 04:06:51. It was one batch: on 2026-09-18 07:03 the same RunCLI was created for **79 stag products** (counted 2026-09-26 from all kept RunCLI rows; an earlier sampled count said 11, which was wrong). Most hit `Missing max ip address` (the same input file); marlin failed differently. The `Bean 'clusterMetrics' … BeanPostProcessorChecker` WARN in these logs is harmless (not the LIT-683431 NPE). A manual kill (`killAction`) writes the same line; tell them apart by the gap (≈TTL = idle) or the DS server log (`ending stale:`). Check the operator's file against `literatum-patch/data/AtyponIPs/atyponIPs.txt` (`min - max` per line, all valid). | DATA + CODE |

## Styleguide build (seen 2026-09-13 → 25, checked by hand)

| Signature | Meaning | Class |
|---|---|---|
| `> patch-package && bash ./.npm/postinstall` → `sh: 1: patch-package: not found` during `npm i -g @atypon/utypon-cli@latest` | **Not fatal by itself.** Beta/stag install `utypon-cli@latest` (`Build-Deploy-Styleguide.sh:387-395`; was 1.31.17 on 13 Sep, 1.31.19 on stag later), prod installs pinned 1.31.10/11. The install still completes (`+ @atypon/utypon-cli@1.31.x`). Don't report it as the cause. | noise (tool drift) |
| utypon status table row `'<…>/ui-products/<p>/<sub>' │ 'failed' │ '<N> ms'` → `Build Failed For The Following Products` → `Error - Failed to Build The Product ,,, Exiting - Exit code: 1` | A product (or sub-product, e.g. `marlin/cell`) failed in utypon. The action log **doesn't contain the real error**: it's in `~<account>/logs/<account>/<product>/UI/build.tgz` on the tools host (the log prints the `scp` line). Ask the user for it. Seen on marlin (beta + stag) and app (stag). A very short time (<1 s) means it failed before compiling (config/dependency), not a SCSS/JS error. | code/dependency (needs build.log) |
| marlin: one sub-product `'failed' | ~900 ms`, **a different one on different days** (cell 09-13 beta+stag, ha 09-14 stag; healthy ones take 523–644 s) | **Likely a race in `@atypon/ui-bundle-generator`** (pinned `"latest"` in styleguide-bundle-configurations `package.json:26`). Since generator 1.3.0, loading the module runs it in the product root, so all parallel workers write the same `marlin/node_modules/@atypon/<gen>` folder, and the loser throws at config load. LIT-646682 fixed one EEXIST case of this. Confirm in `build.log`: `getConfigsForProduct Error: ENOENT … node_modules/@atypon/…` or `TypeError: error.toString(...).include is not a function`. A rerun often passes. Not yet confirmed (no build.log). | code (tool race), notes/24 |

## Cluster / Akka / CLI (checked 2026-09-25)

| Signature | Meaning | Class |
|---|---|---|
| `NoClassDefFoundError: akka/actor/typed/scaladsl/adapter/package$UntypedActorSystemOps$` | root-pom forced Akka 2.6.21 over passport-cluster 2110.0.1 jars (built for 2.5; 2.6 renamed `Untyped*` to `Classic*`). Seen with root-pom 2610.0.4 (LIT-664827) and 2610.0.6 (mms) (tags `atypon-root-pom-2610.0.X`); fixed each time by reverting root-pom. **Literatum master pins root-pom `2611.0.5-SNAPSHOT` (`atypon/build.gradle:78`, re-checked live 2026-09-26) whose pom has Akka 2.6.21, plus passport 2110.0.1: the same bad pair. The released tag `atypon-root-pom-2611.0.4` still has 2.5.31, but master does not pin it.** **Settled 2026-09-27: the snapshot was never published**, so master builds now fail earlier, at dependency resolution (see the next section). | dependency pin |
| `Failure to load ClusterMutex class` → `ExceptionInInitializerError`, then `NoClassDefFoundError` for every later use in the same JVM (patch VM: lit9529, lit31708) | same root as LIT-683431 (null `clusterMetrics` → NPE in `DefaultMutexAdapter` building the Akka mutex). IBM (prod), IBM-beta and IBM-stag props all select `PassportClusterMutex` (`atypon/product/midtier/conf/midtier.props.IBM*.xml` :105/:117/:191). | code (unpatched build) |
| `LIT-604088 legacy singleton` (logger `CoreSpringConfig`) | a static getter hit after Spring was torn down, or before it was set. It follows another failure; don't report it as the cause. | noise |
| `Registry is not yet initialized` (tool/patch startup) | `ServiceLoader` found no registry initializer (wrong thread classloader/classpath); the JVM can't recover. | code/classpath |
| `Pool jdbc is not configured` | DB access after Spring closed the pools (static reference kept) — usually during/after shutdown. | follow-on |
| RunCLI stays Executing after `Exception in thread "main"` | `run tool main` forks a backstage-type JVM (joins the Akka cluster); `ShutdownManager.shutdown()` never calls `System.exit` and `LiteratumThread` is non-daemon, so the JVM hangs until the DS idle TTL force-closes it (LIT-682969; the thread holding it is not yet identified: jstack on the host). | code |

## Patch planning (checked 2026-09-25)

| Signature | Meaning | Class |
|---|---|---|
| ProductPatch: `db_version (litNNNNN) … "patch" is null` at `DbVersionCheck:154` / NPE in `checkAllowDropColumn` | Before **LIT-677519** ("Skip reserved patch dependencies"), plan dependencies skipped the reserved check, so a reserved Java dependency went into the queue as null. **The patch named in the message is only the last one the loop saw, not the culprit.** Seen: physio beta 13 + 14 Sep (lit32046). The fix landed on `lit-2610-physio-pcms-260706` at `523433c4b1` (2026-09-15), so rebuild and redeploy. That branch still lacks the clusterMetrics revert (LIT-683431 risk on its next build). Confirm which dependency was null with a `db_version` query (DB, the user runs it). | code (patch system) |
| `NoSuchMethodException … setTargetDatabase` | Dailypatch-backend's `--target-database` run against a branch without that method (e.g. physio). It comes from the nightly office rehearsal, not the DS; its bugs are titled `Dailypatch: Failed Patch Dev.DB : …`. | tooling |

## Search / REST / DB (checked 2026-09-25, notes/28)

| Signature | Meaning | Class |
|---|---|---|
| SolrDeploy Success but search results/fields wrong after a deploy | configsets come from solr-plugins + literatum.props.xml baked into a shared image; containers are only recreated on image change / forced recreate; the commit step doesn't reload. Check the image tag in the SolrDeploy log vs the previous one. | deploy gap |
| `SolrIndexSync` (`index.sync -s mes`) | **writes:** reindexes and deletes index docs not in the DB. Not a read-only check. | note |
| DigitalObjectReprocess never ends / Success after an error | the script exits 0 on error and loops with no time limit while `[PROCESSING]` > 0 (reader) | false success |
| `Invalid column name 'X'` (SQLServerException, or Hibernate `SQLGrammarException` for PageBuilder) on web start / HostWaitForWebServer | every non-static field of a TableDef row class is a column and entity loads name them all: **the DB is behind the code** (patch not applied). PageBuilder columns come from Liquibase changesets in patches (e.g. lit31595, lit31745). | DB not patched |
| HTTP 500 `No handler for path` on REST | top-level REST handler disabled; a handler class missing on the branch instead kills the JVM at startup (handler tree built once at Spring start) | config/code |

## Branch / merge-order and host-side races (eval loop 2, verified 2026-09-26)

| Signature | Meaning | Class |
|---|---|---|
| ProductBuild: `:product:<p>:copyProperties FAILED` ← `FileNotFoundException …/product/midtier/conf/midtier.props.<x>.xml` | The product's props `<include files=…>` names a midtier props file that doesn't exist **on that branch**: a merge-order gap on a maint branch (gsl stag, `lit-2610-maint-260804`: include landed 10 Sep via PR #13656, the file only 16 Sep via PR #13649; build `dcdcd486` on 13 Sep fell between). Check `gh api "repos/atypon/literatum/contents/<path>?ref=<branch>"` for both files at the build commit. Fix: merge the missing PR to the branch, or move the product to a branch that has it (gsl moved to 260901 on 15 Sep, deployconf `c298f24`). | deployconf/branch |
| ProductPatch (patch VM): `ERROR LOADING PRODUCT` ← `DocumentBuilderFactory cannot be created` / `NoSuchFileException …/webapps/<p>/WEB-INF/lib/<jar>` → `KILLING THE SYSTEM` | A jar the deployed webapp's classpath lists is missing from `WEB-INF/lib` at patch-VM start. If the same revision patched fine before and after on the same host (hope stag 15 Sep: OK at 11:25 and 15:40, failed 12:27), it's not code: something removed or hadn't finished writing the jar (HostDeploy unpack vs a concurrent process). Only the host can settle it (`/var/tmp/<epoch>.txt`, file mtimes). | host/process |
| GaiaDeploy: `Copy files from Ansible master … (item=start.sh) msg: file (/tmp/start.sh) is absent, cannot continue` | Two GaiaDeploys on the **same Gaia cluster** overlapped: the other one's cleanup removed `/tmp/start.sh` on the Gaia node (uchicago vs authorea, 20 Sep 23:40.00 / 23:40.06, dc-beta). Known open bug **LIT-656679**. Harmless if the other deploy shipped the same config; re-run. Find the overlap with `ds_list.sh <acct> "" GaiaDeploy "" 300 '<time>'`. | transient (race) |

## Build-time patch skew, branch breaks, shared-checkout races (eval loop 3, verified 2026-09-26)

| Signature | Meaning | Class |
|---|---|---|
| ProductBuild: `PATCH OK1` / `PATCH OK2` (or `PATCH … applied OK`) then `error: constructor RestApiAction in class RestApiAction cannot be applied to given types` at `ConnectedProductsRestApiAction.java:13` (also aea, marlin, utoronto, asha, stag, 11–13 Sep) | **Build-time patch skew:** platform-tools `patch/common.patch.txt` rewrites RestApiAction (metrics revert) and must also patch every caller. Commit `6e6a049` (11 Sep 15:36Z) dropped the ConnectedProductsRestApiAction hunk; `6176797` (13 Sep 08:13Z, "Refactor ConnectedProductsRestApiAction constructor") restored it. Nothing in literatum changed. Only reproducible on tools hosts (CI compiles unpatched source). Since 25 Sep the revert is in git and PR #354 removed the workaround, so this class of error is gone unless the patch mechanism returns. Check platform-tools `git log -- patch/` around the build time. | build-time patch |
| ProductBuild (3 attempts, nightly): `error: getApplicationContext() has private access in SpringAdapter` ×4 in Gateway*Workflow | lit-2610 broken by a merge from lit-2410 (PR #13940 `a007e7b6`, LIT-672614, 11 Sep 22:40Z: 2410-only no-arg constructors); fixed by `885ab2dfba` (13 Sep 10:02Z). Every lit-2610 product built in that window failed (cabi beta). Find the fix: `gh api "repos/atypon/literatum/commits?sha=lit-2610&path=<file>"`. **Note:** the old `SECRET_RE` (`private`) hid this error; fixed to `private[_ -]?(key|token)`. | code (branch break) |
| ansible step: `NO deploy_version is found for identifier '<branch>', will use the fallback deploy version: 'X'` | Normal, not an error: the service's `atypon_lifecycle.json` has no entry for that Literatum branch, so the fallback branch is used (consumer 10.0, atm 9.0, ingestion main). | info |
| ansible step: `Error [52] while pulling repository` + git `hint: … divergent branches` + `from the remote, but no such ref was fetched` | **Concurrent-pull race** in the NFS-shared checkout `~/apps64/ansible/<svc>/<ver>` (asmj stag: 5 consumer deploys within 41 s on tools-3, one lost). Distinct from `Permission denied (publickey)` (credential). Transient: re-run. Look for other `<svc>` deploys in the same minute with `ds_list.sh <acct> "" <Action> "" 300 '<time>'`. | transient (race) |
| ProductPatch: `ClassNotFoundException: com.atypon.patch.PatchNNNNN` on a **maint** branch right after a new patch | The stub was added to literatum-patch on another branch first and reached the maint branch later (lit32053: `ca562089c7` on `lit-2610-maint-260901…` at 23 Sep 08:16Z; WARs built before that fail on stag: asmj, aami, hanser, app). Check `gh api "repos/atypon/literatum-patch/commits?sha=<PATCH BRANCH>&path=java/src/com/atypon/patch/PatchNNNNN.java"` against the build time. | patch code (branch lag) |
| Release cancelled after a bks ProductPatch failure | **The backstage stays stopped:** HostStop ran, HostStart never did, and cancelling the rest doesn't start it. Check `ds_list.sh <acct> <product> HostStart` for a later start; if none, the bks JVM may be down since the failure (asmj stag `literatum7-stag-bks1` since 23 Sep 03:26 unless started by hand). Say so explicitly. | operational |

## CLI tools, shared-file races (eval loop 4, verified 2026-09-26)

| Signature | Meaning | Class |
|---|---|---|
| RunCLI `backstage.sh contentsuppression.index -a`: `Finished processing 38/38 content slice batches` … then `Exception in thread "main" java.lang.IllegalStateException: Pool jdbc is not configured` at `ContentSuppressionIndexer.main:153`, KeepAlives, `Force connection close` ~1 h later | **Code bug, work already done.** `ContentSuppressionIndexer.java:152` runs the indexing inside `SearchConfigurationLoader.loadAndRun(...)`, which calls `ShutdownManager.getInstance().shutdown()` when the task ends (`SearchConfigurationLoader.java:267`, closes the DB pools); line 153 then calls `ContentSuppressionIndexUtils.updateLogSetting(LOGKEY_LAST_RUN)`, which needs the DB → exception → `System.exit(0)` at :158 skipped → non-daemon threads keep the JVM alive → DS idle TTL force-close → Failure. Same code on lit-2610 (pnas stag 17 Sep). The index itself was written. The `Registry is not yet initialized` lines earlier are log4j-resolver noise. Owner: search team (move the log-setting update inside the task or before shutdown). | code (CLI) |
| GaiaDeploy / any ansible step: `REMOTE HOST IDENTIFICATION HAS CHANGED` … `~<acct>/.ssh/known_hosts:<line>` → `Failed to connect to the host via ssh` → `fatal: UNREACHABLE` → COMPLETED FAILURE | ssh host-key mismatch for one node (asha beta 20 Sep 22:23, `beta-gaia-2`). If the same play reached that node seconds later/earlier from the same tools host (wspc 22:17, aaas 22:40 passed), the node wasn't reimaged: most likely the **NFS-shared known_hosts being rewritten by concurrent deploys** (inferred, LIT ticket unknown). Re-run. If it persists for everyone, the node's key really changed: known_hosts refresh (tools-host ops). | transient (host) |
| ProductPatch (bks): `> Task :compileJava FAILED` in `~/scripts/operations/tools` (= `sourcegit.nfs/platform-tools/operations/tools`) with `Cannot access output property 'options.generatedSourceOutputDirectory'` / `NoSuchFileException …/build/generated/sources/annotationProcessor/java/main`, within seconds, before any patch runs | `run_gradle.sh` first compiles platform-tools' own patch runner (DbGradlePatcher) in the **NFS-shared** checkout; its `build/` dir vanished or was unreadable mid-compile (another host's patch run or cleanup). Not Literatum code: same command/host/branch passed the day before and after (np stag 14 Sep). Re-run. Fix for good: per-user/product Gradle build dir (platform-tools owners). **Check HostStart afterwards**: np's bks stayed stopped 14 Sep 16:03 → 16 Sep 01:45. | host/process (race) |

## Shared-home races and hung tools (eval loop 5, verified 2026-09-26)

| Signature | Meaning | Class |
|---|---|---|
| ProductBuildStyleguide: `npm ERR! 404 Not Found - GET https://registry.npmjs.org/@atypon%2f<pkg>` → `'@atypon/<pkg>@x.y.z' is not in the npm registry` → `Error Installing Package @atypon/<pkg>` → `Error: Cannot find module '@atypon/<pkg>'` from `<product>/bundler.config.js:1` | The `@atypon` scope must resolve to `npm.pkg.github.com`; `Build-Deploy-Styleguide.sh` writes that (`npm config delete _authToken`, `npm set @atypon:registry …`, `npm config set //npm.pkg.github.com/:_auth…`) into the **NFS-shared `~<acct>/.npmrc`** on every build. When several styleguide builds run in the same minute on different tools hosts (nightly 01:00: 9 builds), one can read the file mid-rewrite and fall back to the public registry (utoronto C18 beta, 26 Sep 01:11, tools-7; the other 8 passed; same utypon-cli 1.31.19). Inferred mechanism, strongly supported. Re-run passes. Real fix: per-build `NPM_CONFIG_USERCONFIG` (platform-tools owners). The DS log also prints the registry `_auth`/`_authToken` set commands (secret-bearing). | transient (shared-home race) |
| DeleteEmployee / CreateNewEmployee stuck **Executing for days**, `Sent KeepAlive. count=<thousands>`, `Cannot initialize Spring` earlier in the log | The tool failed to start its Spring context but gradle's progress output keeps the SSH session alive, so the idle TTL never closes it. Later employee rows queue behind it (scheduler rule 23) but deploys aren't blocked (`blockIgnore=true`). Needs a manual kill (operator). Seen: stag ascb since 16 Sep, stag wspc since 20 Sep, beta rmit since 17 Sep. | hung tool |

## Hung builds (seen 2026-09-27)

| Signature | Meaning | Class |
|---|---|---|
| ProductBuild **Executing for hours**, log stops mid-Gradle (e.g. after `> Task :literatum:vaadinPrepareFrontend` / `VfsPlugin, creating a Vfs.DummyDir …`), **no `Sent KeepAlive` lines at all** | The build JVM on the tools host stopped producing output (hung Gradle: frontend/npm download, dependency resolution, or a stuck daemon). KeepAlives are only written when bytes arrive, so none = nothing received. rmit R beta: started 26 Sep 14:01 on tools-13, silent since 14:01:54, still Executing 10 h later. It holds the release and the family. Check: `ds_search.py <acct> Executing "" 50` then `ds_log.sh <id> 'KeepAlive|Task :' \| tail`. Only the host can show why (gradle daemon, `jstack`); an operator must kill it. Why the idle TTL didn't close it: `timeout.ProductBuild` in deployserver.properties is longer than the default 1 h (value not read: secret-bearing file). | hung build (host) |

## Page / widget layer after a deploy (notes/34, key claims verified 2026-09-27)

| Symptom | Meaning | Check |
|---|---|---|
| Old widget HTML after a styleguide-only deploy, until a JVM restart | `ux3OutputCache` key = widget key + product + view context: **no styleguide version, no TTL**, and no deploy event clears it. | `?ux3Cache=false` on the page shows the fresh render. Restart (HostStart) clears it. |
| 404 on fingerprinted CSS/JS after PugrendererProductDeploy | Literatum's styleguide manifest is fetched lazily and refreshed only by `StyleguideDeployedEvent`, which **nothing in the DS path fires** (only `deployStyleguideNew.py:110` calls `/action/styleguideDeployed`, and the DS never runs it). ansible's `rsync --delete-after` removes the old fingerprinted files → stale names → 404, logged nowhere (`HttpCacheFilter.java:225-227`). | `/action/pugrendererInfo`; renderer `/releases`, `/info?p=&v=`. Fix: restart the web JVM. |
| Every PageBuilder page 500 (even `500.jsp`) right after a deploy, `Invalid column name PAGE_REMOVED` / `DROPZONE_ORDER` | pb2-core 8.x columns come from Liquibase changesets applied **only by DB patches** (lit31595, lit31745, gated by a boolean property); the auto-updater is wired only in the dev profile. WAR ahead of DB = the patch didn't run (see ProductPatch failure). | `db_version` for lit31595/lit31745 (DB); the ProductPatch log of the same release. |
| One widget shows an error box; or the literal `<!-- pb/async #id/view -->` stays in the page | Sync widget render failed (`Failed to render widget {} of type {}`) or async render failed (`Failed to render widget async: <id>`). Renderer answered non-2xx: `Service replied with error… Status Code: 404|500`, never retried. Often a styleguide/branch mismatch: `p=<product-name>&v=<styleguide/version>` must equal the renderer's `styleguide-templates/<branch>`. | `?showJson`, `?ux3AsyncRender=false`; renderer `/templates?c=`; compare deployconf `<styleguide><version>` with the PugrendererProductDeploy log. |

## Styleguide dependency drift and the Dailypatch signal (notes/36, reader-verified 2026-09-27)

| Signature / question | Meaning | Class |
|---|---|---|
| ProductBuildStyleguide fails for a product whose ui-products dir hasn't changed | Theme/core pins are git tags resolved by npm at build (`ui-theme-classic#v2.8.84` → nested ui-core/ui-base pins); `ux3/*` submodules and aea, nato, rsc, mms-nextgen float on `#develop`, and `git submodule update --remote` makes **every** build depend on four develop tips. A theme/core develop push can break builds on all envs at once. Check `ui-theme-*` / `ui-core` develop commits around the build time. Install errors are swallowed (`Error Installing Package …` precedes the real webpack error). | dependency drift |
| "Will tonight's prod ProductPatch fail?" | The Dailypatch rehearsal runs staging/beta office DB copies nightly, never prod; a **staging failure for the same product/patch is a leading indicator**, a clean run is not a green light. Its Jira signal is dead (no `patching`-label bugs since 2025-04); read the backend API (`GET /api/v1/products/{stats,failed}` on patch-dc-1.int.atypon.com:6767) or the React dashboard (cipsc-services-3.atypon.com:3000). The two dashboards in git (dailyPatchDashboard 2022, Dailypatch-frontend 2023) are stale; the JSP one renders DB credentials into HTML and has an unauthenticated Rerun button: don't open it. | signal |

## Identity / license deletion (notes/32, verified 2026-09-27)

| Signature | Meaning | Class |
|---|---|---|
| `ReadOnlyException` at `AbstractDbEnhanced.deleteImpl` ← `LicenseImpl.deleteImpl` ← `IdentityImpl.deleteLicenses:9xx` while a patch/tool deletes a user | The user holds or owns a **CR-marked license** (its own FIELD_VALUE_INFO type-66 mark, or a CR-marked parent group of the licensee) and `deleteLicenses` deletes without `markReadOnly(false)` (unlike `SyntheticLicense.deleteImpl`). Site-specific data decides who hits it. `ReadOnlyException` *after* `deleteFromGroups` = the identity's own CR field. Not site read-only mode (`WriteDeniedError`). | patch code + data |
| `EndLicensesForUser` ends far more than expected; `CleanupIPRange` removes nothing | reader-reported hazards: the first SQL has no user join; the second's orphan predicate is always true. Not re-checked by hand. | tool hazard |

## Branch sync and unresolvable parent POM (cold-start test, verified 2026-09-27)

| Signature | Meaning | Class |
|---|---|---|
| ProductBuild: `error: The following untracked working tree files would be overwritten by merge:` … `Aborting` (right after `LIT BRANCH :`) | `platform-tools/sync_branches.sh:52` runs `git reset --hard && git pull` in the shared worktree `~/sourcegit/literatum-worktrees/<branch>`; `reset --hard` doesn't remove **untracked** files, so files left by an old build-time patch (`common.patch.txt`, which *created* them on 20 Sep) block a pull that now adds the same paths in git (`ee993c976c`, 25 Sep). Every product building that branch on that tools host fails until cleaned. sage B39 beta (lit-2610-maint-260901, tools-1, 27 Sep 02:30); all stag sites: **LIT-683683** (open). Fix: `git clean -fd` in that worktree on each tools host (operator), then rebuild; long term `sync_branches.sh` should clean before pulling (platform-tools). | host state (after build-time patch) |
| ProductBuild: `Could not resolve all artifacts …` → `Could not find <group>:<artifact>:.` (**empty version**) … `Could not resolve com.atypon:atypon-root-pom:2611.0.5-SNAPSHOT` / `Unable to load Maven meta-data …` | Literatum master's `atypon/build.gradle:78` pins root-pom `2611.0.5-SNAPSHOT` (commit `4fd894cf`, 24 Sep), which was never published: every version the root-pom manages resolves to empty. `PKIX path building failed` lines nearby are noise. **LIT-683697** (open, "Build failure on master branch (ex, WSPC, ASCE and UX3)"). Fix: pin back to released `2611.0.4` (owner: literatum build / root-pom). Do not publish the current snapshot: it carries Akka 2.6.21 with passport-cluster 2110.0.1, the pair that crashed mms. After the fix, expect the earlier ADVISER compile error (cms-apis pin) to return. | dependency pin |

