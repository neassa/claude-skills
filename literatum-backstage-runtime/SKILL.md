---
name: literatum-backstage-runtime
description: Use for the Literatum backstage/web JVM runtime after a deploy — startup failures (`ERROR LOADING PRODUCT`, `KILLING THE SYSTEM`), the cluster mutex / Akka / passport-cluster (LIT-683431 `clusterMetrics is null`, `NoClassDefFoundError … UntypedActorSystemOps`, root-pom Akka pins), robots and scheduled workflows, ingestion/publish stalls, RunCLI tools that hang (`Pool jdbc is not configured`, `Missing max ip address`, `Force connection close`), and identity/license read-only rules. Strictly read-only.
---

# Literatum backstage and JVM runtime (read-only)

**Paths:** relative to this skill's folder (`../literatum-platform/references/deep/`); repos under `$LIT_REPOS`. Read files only through `../literatum-deploy-triage/scripts/safe_view.py`.

## Startup: what can kill a JVM (web, backstage, patch VM, CLI)

`Main.run` builds the Spring context from the registry `components/`. Any Throwable prints `ERROR LOADING PRODUCT <p>` / `KILLING THE SYSTEM` → exit 1. Eager beans with external I/O: MSSQL pools, the Akka cluster (the Broadcaster always starts it; IBM, IBM-stag and IBM-beta props use `RobotManager_Akka`), the Gaia Cassandra cache, an empty `frontend/nodejs/address`, the content mount, a missing primary domain, and Redis for rdf-cache products. **Solr, ZK and Kafka are not checked at startup.**

## Cluster mutex and Akka (two recurring crashes)

| Signature | Mechanism | Fix |
|---|---|---|
| NPE `Cannot invoke "…PluginMetrics.timer(String)" because "this.clusterMetrics" is null` (ClusterMutexManager / DefaultMutexAdapter), `Error creating bean 'robotsExposer'`, in patches `Failure to load ClusterMutex class` | OTel migration left `PassportClusterMetricsProvider.clusterMetrics = null`; passport-cluster 2110.0.1 stores the provider and `DefaultMutexAdapter.<init>` calls `timer` on it. Only envs selecting `cluster/mutex/clusterMutexClass=PassportClusterMutex`: `atypon/product/midtier/conf/midtier.props.IBM*.xml` (:105 prod, :117 beta, :191 stag). A build-time patch in platform-tools used to revert it; when that patch failed it was swallowed (`LIT-656000 … patch failed, reverting`) and shipped unpatched. | Build from a branch with `3b5d53c2` (revert in git on lit-2610 and maint, 25 Sep). `master`, `lit-2610-acc-260705`, `lit-2610-physio-pcms-260706` still lacked it. LIT-683431 (Reopened). |
| `NoClassDefFoundError: akka/actor/typed/scaladsl/adapter/package$UntypedActorSystemOps$` in `RobotManager_Akka` | root-pom forced Akka 2.6.21 over passport-cluster 2110.0.1 jars built for 2.5 (2.6 renamed `Untyped*` → `Classic*`): root-pom 2610.0.4 (LIT-664827) and 2610.0.6 (24 Sep 08:06–15:59 UTC). | Fresh build with 2610.0.7. Master pins `2611.0.5-SNAPSHOT` (Akka 2.6.21, never published → master can't build: LIT-683697). The real fix (Literatum #9376 / LIT-643926) waits for a passport-cluster 2610.x release. |
| `LIT-604088 legacy singleton` | a static getter hit after Spring teardown | noise, follows another failure |
| `Registry is not yet initialized` | log4j resolver lookup before the registry exists | usually noise in CLI tools |

## Robots, workflows, ingestion

- Make-live scheduling, sitemaps, the nightly embargo mover, deposit waits and suspended-event release all need `SchedulerRobot`/`AlarmRobot`, which exist only in a JVM with an exposed `WfRobot`. With the backstage down or its robots dead: `wf_schedule.tasktime` and `WF_ALARM.endTime` fall in the past, and `LOCKEDBY=-2` events are never released.
- **No dead-letter:** failed events retry 10 m → 1 h → 6 h → 1 d forever (`ZombieKiller.computeSuspendTimestamp`). A class removed by a code change shows as `processing of event … failed` with a CNFE and a climbing `SUSPENDCOUNT`.
- Intake lands in `backstage/incomingDir` → `webdav_directories/<product>/<mode>_upload`. Ingestion does not call Gaia. Publish flips area bits, moves folders, rewrites `.info`/TOC, and sends Kafka delete + submit. There is no cluster broadcast.
- **After a failed release is cancelled, check the backstage was started again** (HostStop with no later HostStart = down).

## RunCLI tools

- `run tool main -Dmain.class=…` forks a backstage-type JVM that joins the Akka cluster. `backstage.sh <tool>` is the other form.
- `ShutdownManager.shutdown()` never calls `System.exit`, and `LiteratumThread` is non-daemon. **An exception in `main` leaves the JVM hung** until the Deploy Server idle TTL (1 h without output) force-closes it (`Force connection close`). If background threads keep logging, it can take days (LIT-682969).
- `AddAtyponIPsToAtyponInstitution`: `Invalid IP address!` → `Missing max ip address`. A bad line in the operator's input file; the whole run is one transaction, so nothing is written. 18 Sep batch: 79 stag products.
- `contentsuppression.index`: finished 38/38, then `ContentSuppressionIndexer.main:153 updateLogSetting` ran after `SearchConfigurationLoader.loadAndRun` had shut the DB pools down (:267) → `Pool jdbc is not configured` → hang. Code bug; the index was written.
- DeleteEmployee / CreateNewEmployee stuck Executing for days with thousands of keep-alives: `Cannot initialize Spring`, and gradle progress keeps the session alive. Needs a manual kill.

## Identity and licenses (read-only rules)

- **Site read-only mode** (`WriteDeniedError`) and **entity read-only** (bare `ReadOnlyException`) are different.
- Licenses are CR-marked in their own right often (subscription, synthetic children, product licenses; gated only by `license/disable-read-only`).
- `IdentityImpl.deleteLicenses:917-934` deletes held/owned licenses **without unmarking**; `SyntheticLicense.deleteImpl` unmarks first. So deleting an IP user who holds a CR license throws (aiaa lit32053). Which license needs the DB: LICENSE by USERID/OWNERID → FIELD_VALUE_INFO type 66, or CR parent groups (USER_REL 1000).
- **Read-only is inherited from groups.** An identity in a group whose access-right field (FIELD_VALUE_INFO type 66) is 3 is read-only, and so are its licenses. aiaa lit32053 (LIT-683700): the IP user was in group 520 "Atypon Institution" (value 3). The fix was to remove the user from AUTO_TEST_USER instead of deleting it (PR #14359).
- **A repo data file does not prove DB membership.** `literatum-patch/data/AtyponIPs/atyponIPs.txt` not listing an IP does not mean the IP user is outside Atypon Institution on a site. Group membership can only be settled in the DB (USER_REL RELATIONID=1000). Mark it DB-only; don't call it refuted.

## Deep notes

`17-literatum-backstage-access-cli.md`, `21-passport-rootpom-idsearch.md`, `31-literatum-ingestion-publish.md`, `32-literatum-access-licensing.md`, `12-literatum-runtime.md`, `05-literatum-build-config-gaia.md`, `02-platform-tools.md` §3.3 (build-time patch).

## Founding failure

ProductBuild was green, but its build-time source patch had failed and been reverted silently. The backstage then crashed at startup with `clusterMetrics is null`. The git branches being compared were byte-identical; the difference existed only at build time.
