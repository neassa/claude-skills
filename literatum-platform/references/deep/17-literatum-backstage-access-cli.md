# 17 — Literatum backstage robots/mutex (LIT-683431), ingestion, access/read-only, CLI tool JVMs, registry/pool errors

Written 2026-09-25 from read-only code reading. Nothing was built or run. No secret values were read: every props/xml print went through the filter `pass|pwd|token|secret|api_?key|_key|license_?key|private|salt|auth[^o]|credential|://user:pw@`. That filter also hides every line containing `Passport…` (it matches `pass`); those lines were re-read by key name only (class names, not secrets).

**Branch read:** `$LIT_REPOS/literatum-lit-2610` = `lit-2610` @ `9f8eb846e` (2026-09-25 14:58 +0300, shallow clone). Paths are relative to `atypon/` unless prefixed. Other sources:
- `PT/` = `$LIT_REPOS/platform-tools` @ `b00c49f` (2026-09-25 16:25, merge of PR #354 "LIT-591953 revert workaround").
- `LP/` = `$LIT_REPOS/literatum-patch` @ `7077394` (2026-09-24).
- `PC/` = `$LIT_REPOS/platform-passport-cluster` @ `8bd8a50` (master, 2026-09-24). **lit-2610 pins `passportClusterVersion=2110.0.1`** (`literatum/versions.properties:117`). I checked that jar's bytecode with `javap` from `~/.gradle`. PC master already uses OpenTelemetry and differs from 2110.0.1, so PC source is used only where the 2110 bytecode agrees.
- Registry library `com.atypon:registry:1.3.5` (`versions.properties:130`), checked with `javap`.
- Master clone `$LIT_REPOS/literatum` @ `0c62d0157`, used only for comparison.
- GitHub (read-only `gh api`): literatum PRs #14129, #14154 and #14157 (LIT-682969).

Not repeated here: patch system and the aiaa lit32053 analysis (note 04 §8–9), Spring startup, heartbeat, Akka startup and Broadcaster basics (note 12 §2), LIT-656000 build patch mechanics (note 02), and the DS/Jira history (notes 13 and 14).

> **Line-number drift vs note 04.** At `9f8eb846e`, `IdentityImpl.isReadOnly` is at `publish/src/java/com/atypon/iam/identity/internal/IdentityImpl.java:638-661` (note 04 says 612-635). `deleteImpl` is at :259, `cleanImpl` :269 (`deleteLicenses()` :276, `deleteFromGroups()` :279), `deleteLicenses` :917 and `deleteFromGroups` :906. `LicenseImpl.isReadOnly` :616-631 and `getCopy` :1445 still match. Use the numbers here for this commit.

---

## 1. Backstage server: robot manager, workflows, cluster mutex, LIT-683431

### 1.1 Which robot manager and which mutex (per env)
- **Robot manager** is chosen at Spring config-import time by `CoreSpringConfig.DynamicConfigsFromProperties` (`literatum/src/java/com/atypon/literatum/spring/CoreSpringConfig.java:178-208`). The inputs are `cluster/enabled-remote-robots` and `cluster/robots-manager-implementation`:
  - `RobotManager_DbArmi` → `ArmiClusterSpringConfig`
  - `RobotManager_Akka` → `PassportClusterSpringConfig` (`cluster/PassportClusterSpringConfig.java:9-17`: beans `clusterService`, `robotManager`)
  - disabled → `DummyClusterSpringConfig`
  - anything else → `IllegalArgumentException("cluster/robots-manager-implementation value … is not supported")` at startup.
  - Base default: `RobotManager_DbArmi` (`literatum/conf/literatum.props.xml:5830-5835`). IBM prod/stag/beta switch to Akka through `midtier.props.akka-cluster.IBM.xml` (prod) and `midtier.props.akka-cluster.IBM-nonprod.xml:19` (included from `midtier.props.IBM-stag.xml:3` and `midtier.props.IBM-beta.xml:3`).
  - These imports carry **no `@Profile`**, so the patch VM and CLI tool JVMs also get `RobotManager_Akka` on IBM envs.
- **Cluster mutex class**: registry key **`cluster/mutex/clusterMutexClass`**.
  - Base value: `com.atypon.literatum.cluster.RobotClusterMutex` (Ricart-Agrawala over robots; `literatum.props.xml:5883`). Sibling keys: `cluster/mutex/acquire-warning` (5m) and an acquire timeout.
  - **`PassportClusterMutex`** (Akka/ZooKeeper mutex adapter) is set in **`product/midtier/conf/midtier.props.IBM.xml:105`**, **`midtier.props.IBM-stag.xml:191`** and **`midtier.props.IBM-beta.xml:117`**.
  - Dev and product-specific overrides (`midtier.props.devmachine.xml:429`, `achs.props.*`, `tandf.props.<dev>.xml`) set `RobotClusterMutex` back.
  - So **every IBM beta, stag and prod site** uses `PassportClusterMutex`.
- **`DefaultMutexAdapter` does not exist in lit-2610.** The adapter is the library class `com.atypon.cluster.japi.MutexAdapter` (passport-cluster-mutex jar), obtained with `MutexAdapter.get(clusterSystem)` in `PassportClusterMutex.java:18-19`. `ClusterMutexManager.reportExternalLocks()` / `PassportClusterMutex.reportLocks()` go through `mutexAdapter.reportMutexes(2s)`.

### 1.2 Classes (lit-2610)
| Class | file:line | Role / failure text |
|---|---|---|
| `ClusterMutexManager` | `literatum/src/java/com/atypon/literatum/cluster/ClusterMutexManager.java:22,78-105` | **Eager static singleton** (`private static final instance = new ClusterMutexManager()`). The ctor loads `cluster/mutex/clusterMutexClass` and runs a **sanity `newInstance("report","report")`** (:86). Any exception → `Log.fatal(Log.CLUSTER, "[ClusterMutexManager] Failure to load ClusterMutex class from registry cluster/mutex/clusterMutexClass")` + `RuntimeException` (:99-101). It is thrown from `<clinit>`, so the caller gets **`ExceptionInInitializerError`**, and every later use gets **`NoClassDefFoundError: Could not initialize class …ClusterMutexManager` until the JVM restarts**. Per-call failure: `"[ClusterMutexManager] Failed to instatiate ClusterMutex"` (:47-48). Success: `"[ClusterMutexManager] <ctor> successfully loaded"` (cluster.log). |
| `ResourceClusterMutex` | `cluster/ResourceClusterMutex.java:13-64` | Base class. Its static `MUTEX_AWAIT_MONITOR = new AwaitMetricsMonitor(…)` (:17) runs on first class load. |
| `AwaitMetricsMonitor` | `cluster/AwaitMetricsMonitor.java:25-44` | At HEAD it registers gauges on `metrics.newrelic.service.ClusterMetrics.INSTANCE`. In the **unpatched pre-revert source** it did `LegacySingletons.getApplicationContext().getBean(otel ClusterMetrics)` (`PT/patch/common.patch.txt:422-470`). That throws **`LIT-604088: legacy singleton has not been set yet`** whenever a mutex class loads before Spring has set the context (§1.4). |
| `PassportClusterMutex` | `cluster/PassportClusterMutex.java:16-19,54-123` | The ctor calls `SingletonPassportClusterProvider.INSTANCE.getOrCreate()`, which creates the Akka `ClusterSystem` if needed. Errors: `"Failed to acquire|try-acquire|release resource [<r>] due to some transient error. For more info check the akka logs."` (:112-122); `"Failed to fetch lock info from mutex adapter"`. `remoteLockingRequest` is unsupported. |
| `SingletonPassportClusterProvider` | `cluster/SingletonPassportClusterProvider.java:22-23,42-54,70-98` | Static `INSTANCE` is built with `new PassportClusterMetricsProvider()`. Error texts are in note 12 (stderr `Exception initializing cluster, reason:`, `exit(111)`). Registers a ShutdownManager listener at `PRIORITY_CLUSTER_SHUTDOWN` (999) and a separate JVM hook `passport-cluster-shutdown-thread` (`"Shutting down ClusterSystem bypassing ShutdownManager"`). |
| `PassportClusterMetricsProvider` | `cluster/PassportClusterMetricsProvider.java:13-64` | Implements the library `com.atypon.cluster.MetricsProvider`. **Every metric call dereferences `clusterMetrics`** (:25-50). At HEAD, `clusterMetrics = ClusterMetrics.INSTANCE.getPluginMetrics()` (newrelic). |
| `metrics.newrelic.MetricsService` / `MetricsManager` / `service.ClusterMetrics` | `literatum/src/java/com/atypon/literatum/metrics/newrelic/{MetricsService.java:31-34, MetricsManager.java:31-61, service/ClusterMetrics.java:10}` | Restored in git by the revert. `MetricsManager.create` debug-logs the New Relic config **including the API key** (`MetricsManager.java:48-56`). **If `literatum` logger DEBUG is on, `literatum.log` is secret-bearing; filter it.** |
| `CoreSpringConfig` beans | `spring/CoreSpringConfig.java:72-81, 210-228` | `broadcaster` now uses the **OpenTelemetry** `metrics.otel.service.ClusterMetrics` bean. So lit-2610 HEAD carries **two** `ClusterMetrics` classes: otel for Broadcaster, newrelic for the passport provider and mutex monitor. `CoreSpringConfig.LOG` is the logger that prints every `LIT-604088` message (it is only the logger name, not the failing class). |
| `RobotManager` | `cluster/RobotManager.java:55-62,64-75,105-113,115-136` | `start()` (@PostConstruct) sets the static `instance` **then** `init()` exposes `MasterRobot` (`"RobotManager <cls> exposed MasterRobot"`). `stop()` (@PreDestroy) nulls it. `getInstance()` with null → logs and throws NPE **`LIT-604088: legacy singleton has not been set yet`**. |
| `RobotManager_Akka` | `cluster/RobotManager_Akka.java:29-33,36-56,98-118,136-139` | The ctor does `clusterService.provider.getOrCreate()` + `RobotsAdapter.get(clusterSystem)`. Expose logs `"robot exposed - id[..] type[..]"`. Lookups log `"Error during robot lookup by id"` and `"cluster in bad shape, unable to get the robot for id: {}"`. Shutdown: `"Shutting down Passport Cluster Robots service..."` then `RobotsAdapter.remove(cs, 20s).toCompletableFuture().join()` (:138), which **blocks until done**. |
| `RobotsRegistrar` / **`RobotsExposer`** | `spring/RobotsRegistrar.java:30-75, 88-125` | `@Profile("!patch")`. Registers a bean `RobotsRegistrar_<name>` for every class in `server/<server.type>/preload-robots`, **only if `Main.preload` is true**. `Main.preload` is set only by `new Main()` (`Main.java:114-116`), so plain tool mains have no robots. It also registers the bean **`robotsExposer`**, whose `@PostConstruct start()` calls `robotManager.expose(bean)` for each robot (:101-110). |
| `WfRobot` (workflow engines) | `publish/src/java/com/atypon/modules/workflow/engine/WfRobot.java:84,131-136,215-220,386-405` | `BackstageEngine`, `EditorBackstageEngine` etc. extend it. **`afterExpose()` calls `checkNewDef()`** (:136). For every def ball in `WEB-INF/<DEF_DEPLOY_DIR>` it takes `ClusterMutexManager.getInstance().getClusterMutex("workflow.checkNewDef", <file>)` (:397). Exceptions are rethrown as RuntimeException (:215-220). Errors thrown there (`ExceptionInInitializerError`) propagate as they are. |
| `Broadcaster` | `cluster/Broadcaster.java:366-420` | See note 12 §4.3. |

### 1.3 LIT-683431 end to end (`"this.clusterMetrics" is null`)
**Root:** the LIT-643926 / LIT-591953 OpenTelemetry migration left `PassportClusterMetricsProvider` with `clusterMetrics = null; // TODO revisit after LIT-643926` and `getClusterMetrics()` returning `null`. It also commented out the `cluster/offline` gauges in `SingletonPassportClusterProvider`. The hunks are in `PT/patch/common.patch.txt:513-562`, and the master clone still has them at `PassportClusterMetricsProvider.java:18-19,62` and `SingletonPassportClusterProvider.java:79`.

**The workaround and the fix:**
- The LIT-656000 build-time patch (`PT/patch/common.patch.txt` and `lit-2610.maint.txt`, applied by `rebuild.py`, note 02) put back the newrelic `MetricsManager`/`MetricsService`/`ClusterMetrics` and the real provider.
- When `git apply` failed, the build shipped **unpatched**.
- **On `lit-2610` @ `9f8eb846e` the revert is now in git:** there are no `LIT-643926` stubs, and the newrelic classes exist.
- PT PR #354 (`b00c49f`) removed the patch step. `rebuild.py` no longer references `patch/*.txt`.

**Mechanics (bytecode-checked against passport-cluster 2110.0.1):**
1. The library's metric-reporting actors call `provider().timer/counter/gauge/…`. They are the `MetricReporting` / `ActorMetricReporting` traits mixed into, for example, `com.atypon.cluster.internal.mutex.zookeeper.MutexRequestProxyActor` (mutex jar) and robot actors (`DefaultRobotsAdapter`).
2. With a null `clusterMetrics` the provider throws the JDK helpful NPE: **`Cannot invoke "com.atypon.metrics.newrelic.PluginMetrics.timer(String)" because "this.clusterMetrics" is null`** at `PassportClusterMetricsProvider.timer` (or `.counter`/`.gauge` …).
3. Creating the `ClusterSystem` alone does **not** trip it. The Broadcaster creates the cluster in every JVM (note 12), and patch VMs start fine. It trips when a **mutex** or **robot** actor registers a metric.

**Path A, patch VM (`ProductPatch`):**
- `Patch009529` (lit9529, `publish/src/java/com/atypon/modules/migration/Patch009529.java:15`) and `Patch031708Lit` (lit31708, `…/Patch031708Lit.java:30`) call `WfRobot.checkNewDef()`.
- That triggers `ClusterMutexManager.<clinit>` → `Conf.getClass(cluster/mutex/clusterMutexClass)` = `PassportClusterMutex` → sanity `new PassportClusterMutex("report","report")` → `MutexAdapter.get(cluster)` → mutex actor → metrics NPE.
- The NPE becomes `Log.fatal "[ClusterMutexManager] Failure to load ClusterMutex class from registry cluster/mutex/clusterMutexClass"` → `ExceptionInInitializerError` → **`Patch lit31708 failed to execute`** (or lit9529).
- The patch VM itself started fine: `robotsExposer` is `!patch`, so no robots are exposed there.

**Path B, backstage JVM start (`HostStart`/`HostRestart` of bks):**
- Spring refresh → `robotsExposer.start()` → `robotManager.expose(BackstageEngine…)` → `WfRobot.afterExpose` → `checkNewDef` → same `ClusterMutexManager` failure (or the NPE directly from the robots adapter).
- Result: **`BeanCreationException: Error creating bean with name 'robotsExposer': Invocation of init method failed`** → `Cannot initialize Spring` → `ERROR LOADING PRODUCT … KILLING THE SYSTEM` → exit 1.
- During teardown of the half-built context, `RobotManager.stop()` and bean destroy methods run. Legacy callers then hit `RobotManager.getInstance()` / `LegacySingletons.get*()` and log **`LIT-604088: legacy singleton has not been set yet`** (logger `CoreSpringConfig`). That line is a **secondary symptom**. The first `Caused by:` under the `robotsExposer` exception is the real cause.
- Web JVMs have no `WfRobot` in their robot list (note 12 §2.2), so this path mostly kills **backstage**. That fits the utb PROD bks case (LIT-683467).

**Path C, CLI tool JVM:** any tool that takes a `ClusterMutex` (or calls `WfRobot.checkNewDef`) on an IBM env builds the same Akka mutex (§4.2: the tool profiles do **not** include `dummy-mutex`). The pre-revert source also had the `AwaitMetricsMonitor` → `LegacySingletons.getApplicationContext()` → `LIT-604088` NPE on the first mutex class load outside a set context (§1.2). That is the most likely source of the marlin RunCLI `LIT-604088 … (CoreSpringConfig)` failure (note 13 row 89). **Inferred, not proven:** the marlin stack was not available.

**Why "clusterMetrics can be null" now:**
1. A build from source that still has the stubs **and** no build-time patch. After PR #354 that is every **master** build (the master clone at `0c62d0157` still has the stubs) and every **maint/product branch cut from lit-2610 before the revert commit**. Not checked: those branches are not cloned. **This is a model gap to verify.**
2. A build made before 2026-09-25 where the patch failed to apply (note 02: `LIT-656000: literatum-master patch failed, reverting...`).

**What to check next (read-only):**
- In the failing ProductPatch/HostStart log, the first `Caused by:`: `this.clusterMetrics` → this bug; `NoClassDefFoundError: akka/...` → root-pom Akka drift (note 14 §1a); `Exception initializing cluster` → Akka bind or seed problem (note 12).
- `grep -n 'LIT-643926' atypon/literatum/src/java/com/atypon/literatum/cluster/*.java` on the **exact branch and commit the env builds** (take it from the ProductBuild log). A hit means the bug is present.
- ProductBuild log for that release: `LIT-656000: … patch failed` (builds before 2026-09-25).
- `cluster.log` on the bks host for `[ClusterMutexManager] … successfully loaded` (healthy) or `Failure to load ClusterMutex class`.

### 1.4 `LIT-604088: legacy singleton has not been set yet`: exact meaning
A static accessor was called while its Spring bean did not exist (not yet created, or already destroyed). Throw sites:
- `LegacySingletons.getApplicationContext` :124, `getBroadcaster` :181, `getDataSourceManager` :204, `getLiteratumFactory` :227, `getFieldsXmlService` :260, `getCmsUtil` :284
- `RobotManager.getInstance` :57, `RobotService.getRobotService` :42, `Services.getServicesSingleton` :47
- Sibling: `"LIT-604088: legacy singleton is being initialized"` (recursive `getBean`, `LegacySingletons.java:339-340`).

**How to read it:**
- The frame just under `requireNonNull` names the getter.
- The frame under that names the caller that ran too early or too late.
- Right after a `Cannot initialize Spring` it is teardown noise, so read the first cause instead.
- In a CLI JVM it means the tool touched legacy code before `LegacySingletons.getSpringAdapter()` finished, or after `ShutdownManager` closed Spring.

### 1.5 Scheduled jobs on backstage
- Quartz: `bridge/Quartz/{autoStartup,mode}`, with scheduler names in `host.props.{web,backstage}.xml` (note 12).
- `literatum.tool.props.xml` (loaded in every tool JVM, §4.2) sets `bridge/Quartz/autoStartup=false`. `marlin.tool.props.xml` sets `bridge/Quartz/mode=slave` and `bridge/spring-integration/mode=slave`, so tool JVMs do not pick up scheduled work.
- `AuditedJspScriptAction` static-starts a **daemon** single-thread scheduler running `JspScriptScheduleTask` every `audited-jsp-script/check-interrupted-interval` (`literatum/src/java/com/atypon/literatum/jspscript/AuditedJspScriptAction.java:27-32`). PR #14154 (LIT-682969) added the guard `"Database pool not yet initialized, skipping JspScriptScheduleTask"` (`JspScriptScheduleTask.java:39-43`), which is benign.
- Ingestion engines and queues: §2.

---

## 2. Content ingestion pipeline on backstage

Source: a delegated deep read of lit-2610 @ `9f8eb846e`. I spot-checked two claims: `DoIndexProc` has no callers (`git grep` hits only its own file), and `UploadMonitor` ctor → `FileUtil.verifyFolderAccessibility(dir, true)` creates a missing directory (`literatum/src/java/com/atypon/literatum/util/filesystem/UploadMonitor.java:93`, `FileUtil.java:2921-2961`). Tags: **[V]** read in code, **[I]** inferred, **[U]** library behaviour not in the repo.

**Two premise corrections:**
- **`DoIndexProc` is dead code on lit-2610.** For journal ZIP ingestion, the Kafka handoff is `IssuePipeline.buildAndSubmitIntermediateXml()` (`publish/.../backstage/IssuePipeline.java:1402-1430`), which calls `IndexingKafkaAPI.submit` directly. `ArticleDoIndex_1` in MoveArticles is a pass-through. **[V]**
- **A missing incoming-dir mount fails silently.** The monitor creates the directory locally and polls an empty folder (§2.1). **[V]**

### 2.1 Deposit: upload dirs → `QServerForWorkflowRobot`
**Classes:**
- `publish/.../backstage/queue/QServerForWorkflowRobot.java`: a PollingRobot "QServerRobot" with a 30-minute heartbeat (:127-128). It builds one `QServerUploadMonitor` per configured directory (:125-167); `process()` is at :169-194.
- `literatum/.../util/filesystem/UploadMonitor.java`: the generic polling logic.
- Passport CMS overlays (euler, gauss, jacobi, newton, sc-ci-common) use `bridge/.../QServerForPassportCmsWorkflowRobot`. IBM uses the publish class.

**Trigger:**
- Polls every `backstage/incoming_dir_check` (2m).
- Each directory is guarded by `ClusterMutexManager.getClusterMutex("file", <path>)` with a **blocking `acquire()`** (UploadMonitor:119), so one node scans a given directory at a time.
- A file qualifies after 60 s of stable size (:39, :257-281), and only if it is a non-hidden `*.zip` / `*.tar.gz` (:44-46, :136-139).
- With `moveInTransaction=true`, `processFile` (which creates the DB job) and then `renameTo(incomingDir/received/<yyyy>/<m>/)` run in one transaction (:210-243; QServer:257-266). If the rename fails, it falls back to copy + delete (:196-208).

**Keys:**
- `backstage/incomingDir`: mandatory. Base `${macro/publisher-home}/backstage/upload`. The IBM overlay value is `${macro/acs-home-path}/webdav_directories/${macro/product-name}/${server/mode}_upload` (`midtier.props.IBM.xml:122-125`, `IBM-stag.xml:141-146`, `IBM-beta.xml:121-126`).
- Also `backstage/incomingDirHigh|incomingDirLow|legacyIncomingDir` (with `folder`/`priority`/`engine`), `backstage/incoming_dir_check` and `server/backstage/verify-file-system`.

**Logs** (`Lot.LITERATUM` → `log/literatum.log`, log4j2.xml:27, :455-458):
- `file <name> was received - moving` (INFO, the success marker, :212).
- `fail to acquire cluster mutex` (:133).
- `cannot list directory <dir>` (:144).
- `cannot process file <path>(Error code: 161)` (:181). The transaction rolls back and the file stays, so this **repeats every poll**.
- `Cannot move <f> to <dir>. Check if both folders are located on same device…` (:224).
- **`stopped checking upload directory <dir>`** (FATAL, QServer:191). Processed but not deletable, so **this directory is dropped until the JVM restarts**.
- `backstage/incomingDir property is invalid` (ctor, :229). The robot fails to construct, and the backstage JVM startup fails (note 12).

**Missing mount:** `verifyFolderAccessibility(dir, true)` creates the directory (5 tries). The only startup filesystem guard, `Main.java:400-407` (`Failed to verify file system for directory`), checks `server/verification-directory` = `${content/journal-root}`, not the upload directory, and only when `LOCAL_BASE` is set.

**Check next:**
- `grep -E "was received|cannot process file|stopped checking upload|fail to acquire cluster mutex|cannot list directory" log/literatum.log*`
- `ls -la <incomingDir> <incomingDir>/received/$(date +%Y)/$(date +%-m)`
- `findmnt -T <incomingDir>`
- A zip older than 2 poll cycles still in the incoming directory means processFile is failing or the `file.<path>` mutex is held.

### 2.2 Job creation: submission, workflow case, events
- `QServerUploadMonitor.processFile` → `PublishFactory.processUploadedSubmission` (`publish/.../modules/PublishFactory.java:422-506`) routes by zip code. The options are DB pub, split zip, book, exam, poll, discussion, DO, `ProcessZipArticles` (`backstage/zip-preprocessing-workflow/enabled`, default false) or `ProcessArticles`.
- `ProcessArticlesWorkflowCase.create` (:44-84), in one transaction:
  1. Creates the `BACKSTAGE_SUBMISSION_INFO` row.
  2. `WfVersion.find("ProcessArticles", 211)`.
  3. `WfRobot.createWorkflow` (`WF_FIRE` + `WF_EVENT`).
  4. `BACKSTAGE_CASE_MAP`, and `BACKSTAGE_STATUS` STATUS=1 (PROCESSING).
  
  With `passport/enabled` it throws `Article process workflow is not to be executed in passport` (:51-53).
- **Workflow definitions:** `WfRobot.afterExpose → checkNewDef()` (:386-408) loads `WEB-INF/wfdefs/*` under the cluster mutex `workflow.checkNewDef.<file>`. **This is the same call that trips LIT-683431 (§1.3).**
  - `cannot upload type[..] version[..]` (FATAL, workflow.log + literatum.log, :454-455) → RuntimeException → the engine is not exposed.
  - `transit X exists in the database and cannot be updated` (WARN, :484) is normal.
  - A missing definition row → `cannot process file … 161` every 2 min. **[I]**
- **Tables:**
  - `WF_EVENT` (EVENTID, EVENTTYPE, FIREID, CASEID, PRIORITY, QUEUE, LOCKEDBY, LOCKTIME, SUSPENDCOUNT)
  - `WF_FIRE` (FIREID, PARENTID, CASEID, STATE 0 live/1 finished/2 killed, ENGINE, CREATETIME, STARTTIME, ENDTIME)
  - `BACKSTAGE_SUBMISSION_INFO` (SUBMISSIONID, CODE, DESCRIPTION, ERRORLEVEL, ERRORCOUNT, SUBMITTIME, STARTTIME, ENDTIME, KILLED, EXTERNALID)
  - `BACKSTAGE_STATUS` (PUBID, SUBMISSIONID, STATUS)
  - `BACKSTAGE_CASE_MAP` (SUBMISSIONID, CASEID)
  - Queue IDs: 1 Alert, 2 Backstage, 3 Backoffice, 4 EditorBackstage, 5 Reasoner, 20-39 Inplace reprocess (`WfRobot.java:86-93`). Event types: 100 GENERIC, 101 CONTENT_PROCESSING, 107 INDEXING, 108 CDN, 110 DEPOSIT (`TaskType.java`).
- **Check next:**
  - `SELECT TOP 20 SUBMISSIONID, CODE, DESCRIPTION, SUBMITTIME, STARTTIME, ENDTIME, ERRORLEVEL, KILLED FROM BACKSTAGE_SUBMISSION_INFO ORDER BY SUBMITTIME DESC;`
  - `grep "cannot upload type" log/workflow.log*`

### 2.3 Workflow engines: dispatch, locking, recovery
- **Engines:**
  - `BackstageEngine`, `EditorBackstageEngine` (`backstage/useDedicatedEditorEngine`, default true) and `InplaceReprocessEngine` extend `WfRobot`.
  - `beforeExpose()` → `InitBackstage.execute()`, which only precompiles XPaths when `backstage/initialize-xpaths-on-start` is set. **No startup check refuses processing.**
  - `NoBackstageEngine` ("BackofficeEngine") runs the `workflow/init-nobackstage-tasks` hooks. A failure logs `The class X failed on initOnStart() method.` (FATAL) and blocks nothing.
- **Queues:**
  - Keys: `workflow/<Engine>/queueId` and the `q-*` sets (`eventTypes`, `threads`, `minPriority`, `maxPriority`, `pollingFrequency`, `eventLockingBatchSize`, `policy`, `allowedQueueIds`) (WfRobot:140-190; `literatum.props.xml:20699-20896`). BackstageEngine's q-CONTENT_PROCESSING has 5 threads and a 30 s poll.
  - `EventQueue` claims events with `SELECT TOP n … FROM wf_event WITH(UPDLOCK,ROWLOCK,READPAST) WHERE lockedBy IS NULL …` + `UPDATE … SET lockedBy=<robotId>` (:190-210, :689). **Several backstage JVMs can run the same engine safely; there is no single master.**
  - A per-cluster cap (`MaxPerClusterExecutionPolicy`, mutex `workflow.<name>-<i>`, 10 s poll) exists only for crossreflinking (10), caslinking (1) and subsriptionupload (1).
  - Remote engines are pushed new events every 20 s (`ClusterCoordinator.java:171`; `sending thread finished` FATAL if it dies).
- **Failure and retry** (`EventProcessor.java:128-266`):
  - Logs: `start processing event <id>, <type>, fire F, case C`, then `processing of event … finished|failed`, plus `… failed on SQLException error code: N` and `… requested reschedule at <ts>`.
  - A failed event is **suspended**: `lockedBy=-2`, `lockTime=until`, `suspendCount++`. Backoff is 10 min, 1 h, 6 h, then 1 day; a deadlock gets 10 s (`ZombieKiller.java:155-172`). So **a broken step retries forever, at most daily**.
  - Content errors do not suspend the event. They go to `LOG_BACKSTAGE_ERROR` (§2.4).
- **Recovery:**
  - A graceful stop drains the in-memory queue and runs `UPDATE wf_event SET lockedBy=NULL` (EventQueue:537-566).
  - After kill -9 or OOM, rows stay locked by the dead robot's ID until **`ZombieKiller`** ("WfZombieKiller", every 10 min) finds `RobotManager.isRobotAlive(id)` false. It logs `robot N is dead` → `Event E released forcefully`.
  - If the liveness lookup errors (`robotsAdapter.lookupById` **[U]**), it logs `cannot determine if robot N is dead because of internal error, retrying later` and **keeps the lock**.
  - ZombieKiller, AlarmRobot, SchedulerRobot and CleanupRobot are started per JVM **only by an exposed WfRobot** (WfRobot:192-212). **With no engine exposed anywhere, nothing releases locks or starts scheduled cases.**
  - Whether a re-run step is safe to run twice was not checked. **[I]**
- **Check next:**
  - `SELECT QUEUE, EVENTTYPE, CASE WHEN LOCKEDBY IS NULL THEN 'ready' WHEN LOCKEDBY=-2 THEN 'suspended' ELSE 'locked' END st, COUNT(*) FROM WF_EVENT GROUP BY QUEUE, EVENTTYPE, CASE WHEN LOCKEDBY IS NULL THEN 'ready' WHEN LOCKEDBY=-2 THEN 'suspended' ELSE 'locked' END;`
  - `SELECT LOCKEDBY, COUNT(*), MIN(LOCKTIME) FROM WF_EVENT WHERE LOCKEDBY > 0 GROUP BY LOCKEDBY;`
  - `SELECT EVENTID, CASEID, SUSPENDCOUNT, LOCKTIME FROM WF_EVENT WHERE LOCKEDBY=-2 ORDER BY SUSPENDCOUNT DESC;`
  - `grep -E "is dead|released forcefully|cannot determine if robot|Cannot lock events|processing of event .* failed" log/workflow.log*`

### 2.4 Processing steps (unzip, validate, transform, load)
- **ProcessArticles v211** (`workflow/ProcessArticles_211.xml`): ProcessArticles (`ProcessArticlesTransit_1`, CONTENT_PROCESSING) → CalcDeposit/Deposit → CalcLinking/LinkingBlock/CitedBy → CalcCDN/UploadCDN/JoinCDN → SendResultEmail → Join. The case listener is `BackstageCaseListener` → `BackstageSubmission.caseFinished`.
- `ProcessArticlesProc.run3()` (:164-197) runs `IssueZipHandler` (or the class in `backstage/ZipHandler`: extract, analyse, manifest), then `IssuePipeline` (parse, transform, DB load).
  - Errors → `backstageLog(SUBMISSION_FAILED=250 …)` → a `LOG_BACKSTAGE_ERROR` row (ERRORCODEID, LOGMSGPARAMS, WFID, GROUPDOI, AREA, STACKTRACEBLOB) + `Lot.BACKSTAGE` → literatum.log. **The workflow event still completes.**
  - Status goes PROCESSING → CALC_DEPOSITS/CALC_LINKING/CDN (:109-120).
- **Locks:**
  - `IssueZipHandler.createDbIssue` takes the mutex `<AREA>:<issueDoi>.IssueCreate` with a **30 min timeout** (:47, :173).
  - Content `acquireLock()` → `LockedContentException` (AbstractPublicationContent:1302-1320).
  - Under `PassportClusterMutex`, locks held by a dead node are released by the library **[U]**. The error is `Failed to acquire resource [..] due to some transient error…`; see `log/akka/passport-cluster.log` (logger `com.atypon.cluster.internal.mutex`, log4j2.xml:884-887).
- **Virus scan:** `Rescheduling task (reattempt: n) for zip '<z>' due to failed virus scan attempt`, then `Maximum reattempts reached` (AbstractZipHandler:100-130).
- **Email:** `SendResultEmailProc` → `SendProcessingEmail.sendProcessingEmail(…WARN/ERROR/FATAL)` goes to publication admins/typesetters and manifest callback addresses, **only after the CDN join**, so a suspended case sends nothing. Recipient config not traced. **[I]**
- **Check next:**
  - `SELECT TOP 50 ERRORCODEID, WFID, GROUPDOI, WFDATE FROM LOG_BACKSTAGE_ERROR ORDER BY LOGBACKSTAGEERRORID DESC;`
  - `grep -E "Error code: 250|Rescheduling task|Failed to acquire resource" log/literatum.log* log/akka/passport-cluster.log*`

### 2.5 Publish (make-live) and indexing
- **Make-live:** `ProcessArticlesProc` (:430-480) either creates `MoveArticlesWorkflowCase` immediately or a `StartScheduledBackstage` case (SCHEDULED=2).
  - `SchedulerRobot` ("WfSchedulerRobot") polls `wf_schedule` every 5 min and logs `cannot process schedule entry N`.
  - Markers: `CREATE_MAKE_LIVE_FAILED` / `CREATED_MAKE_LIVE`.
- **Indexing:** `IssuePipeline.buildAndSubmitIntermediateXml` (:1402-1430) is gated by the per-submission `DoSearchIndexing` option and `search/collections/defaults/indexing/enabled`. It logs `Creating intermediate xml for indexing.` → `IndexingKafkaAPI.submit` (producer failure modes: note 12 §3.4). `backstage/intermediate-xml/send-to-kafka` is read only by the dead `DoIndexProc` (:163).
- **Check next:** `grep "Creating intermediate xml for indexing" log/literatum.log*`, then `log/kafka/kafka.log`.

### 2.6 Modes, Quartz, read-only
- **Read-only:** `acs/start-in-read-only-mode` / `ReadOnlySiteUtil.assertWriteAllowed()` is enforced only in `ActionController:264`. The JDBC-level checks are commented out, and `server/*/safe-for-read-only-mode` has no callers. **So backstage robots keep ingesting in read-only mode.** **[V]**
- `bridge/spring-integration/mode` is read only by `product/marlin/*`.
- `bridge/Quartz/autoStartup` drives the clustered bridge Quartz scheduler (`bridge-core.xml:11`). The ingestion path uses the WF scheduler, not Quartz.

### 2.7 Admin / monitoring
- `services.props.xml:1230-1234`:
  - `wfengine` (`WfEngineDispatcher`: home, ver, def, fire, graph/svg/png of cases and fires)
  - `adminBackstageWorkflow` (`AdminDispatcher`: cases by active/finished/date/DOI, deposits)
- WAT "Backstage Processing Queue" (`BackstageProcessingQueuePresenterImpl:302-330`) shows the running cases for queues 2 and 4. It asks robots with a 30 s timeout and logs `cannot call method of robot N`. `WfRobot.isQueueRunning` logs `cluster in bad shape, unable to check queue status…` to cluster.log.
- OTEL gauges: `pending_case_start_time`, `events`, `event_suspend_total`.
- URL shape `/action/wfengine?action=home`, `/action/adminBackstageWorkflow?active=on`. **[I]**

### 2.8 Stuck-after-deploy checklist
| Symptom | Likely cause | Next check |
|---|---|---|
| Zips pile up in the upload dir, no log lines | Mount missing (dir auto-created locally), or QServer robot not exposed | `findmnt -T`; `grep "QServerRobot\|was received"` |
| `cannot process file … 161` every 2 min | Job creation throws (missing wfdef, DB) | Exception after the message; `cannot upload type` in workflow.log |
| `stopped checking upload directory` | Source file not deletable (permissions) | Directory ownership. The directory stays dead until restart |
| Submissions exist, WF_EVENT LOCKEDBY NULL, nothing runs | No engine exposed for that queue/event type | WF_EVENT group-by; robot list; `robot exposed` lines in cluster.log |
| WF_EVENT LOCKEDBY>0 for an old robot ID | Crash leftover; ZombieKiller not running or liveness check errors | `is dead` / `cannot determine if robot` in workflow.log |
| LOCKEDBY=-2, high SUSPENDCOUNT | The step keeps throwing; retried up to daily | `processing of event <id>` in workflow.log |
| Step hangs 30 min then errors | IssueCreate/content mutex held by a dead node | `log/akka/passport-cluster.log`, `Failed to acquire resource` |

**Coverage (delegated agent):**
- **Read fully:** BackstageEngine, EditorBackstageEngine, NoBackstageEngine, InplaceReprocessEngine, InitBackstage, QServerForWorkflowRobot, MonitoredFolderConfig, UploadMonitor, UploadMonitorRobot, WfRobot (1-1099), ZombieKiller, ClusterCoordinator, MaxPerClusterExecutionPolicy, ClusterMutexManager, RobotClusterMutex, PassportClusterMutex, TaskType, ProcessArticlesTransit_1, ProcessArticles_211.xml, SendResultEmailTransit_1, BackstageCaseListener.
- **Read in part:**
  - EventQueue (180-215, 530-570, 660-700)
  - EventProcessor (110-270)
  - PublishFactory (410-506)
  - ProcessArticlesWorkflowCase (44-84)
  - ProcessArticlesProc (150-200, 260-300, 440-485)
  - IssuePipeline (1398-1430)
  - IssueZipHandler (165-200)
  - AbstractZipHandler (100-130)
  - SendResultEmailProc (40-100)
  - FileUtil (2913-2961)
  - Main (390-440)
  - ReadOnlySiteUtil (25-80)
  - PollingRobot (260-284)
  - ThreadHeartbeat (100-135)
  - WorkflowMonitoringService (145-200)
  - BackstageProcessingQueuePresenterImpl (295-330)
  - WfEngineDispatcher (746-790)
  - `literatum.props.xml` (20699-20896, 23325-23430, 26020-26090, 26440-26520)
  - `log4j2.xml` (1-60, 453-620, 864-893)
  - `services.props.xml` (1225-1295)
  - midtier IBM* backstage sections
  - `bridge-core.xml` (1-40)
- **Not read:** IssuePipeline bulk, ZipHandler/extractor internals, validators, Deposit/LinkingBlock, SchedulerRobot/AlarmRobot/CleanupRobot bodies, SendProcessingEmail recipients, AdminDispatcher, the bridge Passport CMS QServer, and the `com.atypon.cluster.*` library.

> **Secret-hygiene incident (delegated agent):** one unfiltered print of `product/midtier/conf/midtier.props.IBM.xml` (~lines 225-260) exposed committed base64 Google service-account credential values at `profile-enrichment/google-pubsub-credentials` and `google-pubsub/credentials`. They are not reproduced here. They are **committed in the literatum repo** and should be reviewed and rotated by their owner.

---

## 3. Identity, access, licensing and read-only (adds to note 04 §8–9)

### 3.1 Read-only rules (at `9f8eb846e`)
| Rule | file:line | Notes |
|---|---|---|
| Entity flag | `AbstractDbBasic.saveImpl` :320-322, `deleteImpl` :571; `AbstractDbEnhanced.saveImpl` :50-52, `deleteImpl` :100 | Throws **`new ReadOnlyException()` with no message** when `isReadOnly()`. Cached-entity variants carry a message (:362, :427, :584; Enhanced :114). |
| `IdentityImpl.isReadOnly` | `publish/src/java/com/atypon/iam/identity/internal/IdentityImpl.java:638-661` | Flag → **new (non-persistent) objects are never read-only** (:643-645) → own Fields `ENTITY_ACCESS_RIGHTS == CR` (:649) → **any direct group (`MembershipService.findDirectGroups(id)`) whose `isReadOnly()` is true** (:653-658). Groups are `IdentityImpl`s too, so the group check recurses: a group is read-only if it is CR-marked or sits in a read-only group. |
| `LicenseImpl.isReadOnly` | `publish/src/java/com/atypon/publish/acs/license/LicenseImpl.java:616-631` | Flag → new licenses are never read-only → CR Fields → **`getUserID()!=-1 && getUser().isReadOnly()`**. So a license **inherits read-only from its licensee identity**, and from that identity's groups. |
| `LicenseImpl.getCopy` | `LicenseImpl.java:1445-1461` | The only entity-level `setReadOnly(true)` for licenses. Request-time callers only (note 04). |
| CR marking | `literatum/src/java/com/atypon/literatum/acs/EntityAccessRights.java:25-28` (`markReadOnly`), `:34-38` (`markEditable`: removes the key from the **in-memory** Fields), `:49-54` (`markReadOnlyAndSave`), `:65-75` (`isReadOnly`: true only if **every** Fields is exactly CR) | `IdentityImpl.markReadOnly(boolean)` :1267-1270. Patch functions `--$markReadOnly` / `--$markPersonIdentityWithEmailAsReadOnly` (`literatum/src/java/com/atypon/modules/patch/functions/MarkReadOnlyPatch.java:18`). |
| Site read-only | `ReadOnlySiteUtil` → `WriteDeniedError` | Different mechanism (note 04). |

There is **no registry list of "read-only groups"**: `grep read-?only-?group` in `literatum.props.xml` finds nothing. A group is read-only only through its own CR Fields or its parents.

### 3.2 `AddAtyponIPsToAtyponInstitution` exactly (`publish/src/java/com/atypon/modules/migration/AddAtyponIPsToAtyponInstitution.java`, 240 lines, read fully; identical on master)
1. `main` (:41-72): calls `LegacySingletons.getSpringAdapter()` (**not** `Main.run`, see §4), reads `args[0]` line by line (skips blank and `#` lines; the lines are **not trimmed**), then runs `addIPRangesToAtyponInstitution` → `permanentlyUnblockIpRanges` → `assertZuperAdminAllowsIpRanges`. The last is non-fatal: `>>> WARNING -- …` for IPs not matched by `zuperAdmin/ip-list`. The `finally` prints `Shutting down AddAtyponIPsToAtyponInstitution class` and calls `ShutdownManager.shutdown()` if it has not run yet (PRs #14129/#14157, merged 2026-09-20).
2. `addIPRangesToAtyponInstitution` (:90-143):
   - Finds institutions with description **"Atypon Institution"** (`findByUserTypeDescription(InstitutionUser.TYPE_ID, …)`). If there are duplicates, the non-earliest are **deleted** (:106-113, outside the transaction). None found → `Exception("Could not find an institution with description 'Atypon Institution'")`.
   - Then inside `Transaction.execute`: **`markEditable(inst.getFields())` + `save()`** (:123-124) → removes **all** IP-range memberships (:127-131) → `addIpRangeToInstitution` for each line (:133-135) → **`markReadOnly(inst.getFields())` + `save()`** (:138-139).
3. `findOrCreateIpRangeUser` (:175-190): `IPAddressUtil.normalize` (removes spaces, zero-pads IPv4 to `ddd.ddd.ddd.ddd`) → `Finder.of(IPRangeUser).fromWhere(minIp=…, maxIp=…)` → otherwise a new `IPRangeUser` with description `Atypon Ip <min>-<max>`, then `save()`.

**Why `ReadOnlyException` at `InstitutionUser.saveImpl` (tandf beta):**
- `markEditable` only clears the institution's **own** Fields.
- `IdentityImpl.isReadOnly` is still true if **"Atypon Institution" is a direct member of a read-only group** (:653-658).
- So the first `save()` (:124) throws the bare `ReadOnlyException` from `AbstractDbBasic.saveImpl:322` (`InstitutionUser.saveImpl` :224-233 → super).
- The note 13 stack cites `AddAtyponIPsToAtyponInstitution.java:131`, which is **not** a save line in this source. The tandf beta build is therefore not this commit; take the branch and commit from the RunCLI/ProductBuild log.

**Why `Invalid IP address!` → `DbException: Missing max ip address` (stag):**
- `IPAddressUtil.getCanonicalIP4`/`getCanonicalIP6` log `ERROR ACS "Invalid IP address!"` and return **null** when `InetAddress.getByName` fails (`literatum/src/java/com/atypon/literatum/util/data/IPAddressUtil.java:44-46, 62-64`). `setMaxIP` stores null, and `AbstractIPRangeUser.validate` puts `"Missing max ip address"` (`literatum/src/java/com/atypon/literatum/acs/user/AbstractIPRangeUser.java:170-190`) → DbException on save → the transaction rolls back.
- So a line in the **file the operator passed** did not resolve as an IP. `LP/data/AtyponIPs/atyponIPs.txt` @ `7077394` (added or changed by PR #513, LIT-682973, 2026-09-24) has 81 data lines, all `a - b`. The spaces are harmless (`eliminateSpaces`), no data line lacks a dash, and trailing-whitespace lines are all comments. The **18 Sep file version was not available** (shallow clone), so the bad line is not identified.

**Link to Patch032053 (aiaa lit32053, adds to note 04 §9):**
- `Patch032053` (`publish/src/java/com/atypon/modules/migration/Patch032053.java:10,19-22`) resolves `"104.030.132.204"` (already canonical) and **`delete()`s** that IP user.
- **That IP is not in `LP/data/AtyponIPs/atyponIPs.txt` @ HEAD** (0 matches for `104.0?30.132.`). The file's 104.30.x lines are elsewhere, and I did not print them.
- So the "member of Atypon Institution" explanation in note 04 is **less likely than note 04 assumed**, at least for the current file. The remaining ways the IP user or its licenses are read-only:
  - **RESOLVED 2026-09-28 (LIT-683700):** the DB showed the IP user (1012507) IS a member of group 520 "Atypon Institution" (type 66 = 3) → inherited read-only. Note 04 was right; this note's downgrade from the file was wrong: a repo data file does not show DB membership. Fix: literatum PR #14359 removes the IP from AUTO_TEST_USER instead of deleting it.
  1. The IP user is in some other CR-marked group (`AUTO_TEST_USER` itself, if CR, or a parent of it).
  2. Its own Fields are CR (`--$markReadOnly` or an older run).
  3. It holds or owns a license whose licensee is read-only.

**Check next (read-only, for the user):**
- Find the IP user: `SELECT … FROM IP_RANGE_USER WHERE MINIP='104.030.132.204'`, then its memberships (USER_REL membership rows) and the `ENTITY_ACCESS_RIGHTS` field of each parent group (`FIELDS_VALUE_INFO`).
- Take the frames from `/var/tmp/<epoch>.txt`: `IdentityImpl.deleteLicenses` → license path; `AbstractEntity.deleteImpl` under `IdentityImpl.deleteImpl` → identity path.

### 3.3 IP users and groups (for reading stacks)
- `IPRangeUser` / `AbstractIPRangeUser` (`literatum/src/java/com/atypon/literatum/acs/user/`): `setMinIP`/`setMaxIP` re-normalize, fill `*` with `0`/`255` and set `routingPrefix`. `validate` also reports `Invalid min/max ip address` and `Missing Routing Prefix`.
- Lookups used by patches: `IdentityModule.get().getIpRangeUserService().getFirst(IpRangeResolver.resolve(ip))` (fresh from the DB).
- Group membership: `IdentityRelation.TYPE_MEMBERSHIP` through `getIdentityRelationService()` / `getMembershipService().findDirectGroups`. `isMember`/`addMember` are on the group (`BasicGroupIdentity`).

---

## 4. CLI tool runner (Deploy Server `RunCLI`: `run tool main -Dmain.class=…`)

### 4.1 Process chain
1. **DS `RunCLI`** → `PT/deployserver/run-cli.sh:1-18`: sources `aliases.sh`/`functions.sh`/`jira_funcs`, then ``output=`$command | tee /dev/fd/2` ``. It optionally posts the output to Jira `LIT-<ticket>`. **The script's exit code is the Jira call's, not the command's**, so the DS judges success only by `BUILD SUCCESSFUL` in the output (note 01).
2. `run` (`PT/functions.sh:1690-1717`): `pushd $SCRIPTS_HOME/operations/tools; ./run.sh "$@"`.
3. `PT/operations/tools/run.sh`:
   - Env checks (`JAVA_HOME`, `DEPLOY_HOME`, `DEPLOY_HOST`, `PRODUCT_NAME`, `ATYPON_HOME`) end in a bare `exit`, which is 0. The printed `ERROR: … not found in your environment` is the only sign.
   - It builds `_JVM_ARG` (`-Datypon.home -Dappserver.type -Ddeploy.home -Ddeploy.host -Dhost.name -Ddeploy.family -Dproduct.name -Dscripts.home -Dfile.encoding -Dheadless`; `-Djdk17=yes` on ≥17) and **`export COMMAND_LINE=true` for `tool`/`patch`** (:211-213).
   - It launches Ant in a JVM: `java -Xms8G -Xmx32G -XX:+UseSerialGC … org.apache.tools.ant.launch.Launcher -buildfile tool.xml main -Dmain.class=…` (:229-235) and returns Ant's exit code.
4. `PT/operations/tools/tool.xml` target **`main`** (:927-961):
   - Runs `<java classname="${main.class}" fork="yes" failonerror="true">` on classpath `~/apps64/atypon_libs/zips/*.jar` + `${deploy.home}/webapps/${product.name}/WEB-INF/lib/*` + `WEB-INF/classes`, i.e. the **deployed** webapp, not the fresh build.
   - Sysprops: `acs.home`, `atypon.home`, **`server.type=backstage`**, **`akka.use.ephemeral.port=true`**, `disable-event-transport=true`, **`extra-active-profiles=dummy-event-transport,dummy-crdt,dummy-broadcast`**.
   - JVM args: `-XX:+ExitOnOutOfMemoryError -Xmx4G` + Saxon + `--add-opens` (:37-43).
   - `mainArgs` (:964-976) is the same without `failonerror` (`-Xmx512M`). `inlinemain` (:978-1003) is `fork="no"`, running inside Ant's JVM and classloader.
   - There is **no timeout** attribute.
5. The backstage-tool variant (`bkstg <target>`, e.g. `contentsuppression.index -a`) goes through `PT/backstage.sh:24-110` (`COMMAND_LINE=true`, `-Dserver.type=rbackstage` if `env.py --isonrbackstage`, `mkdir log`) → Ant `PT/conf/backstage.xml` `backstage.base` (:37-75) → `<java fork="yes" dir="${env.PWD}" failonerror="true">` with `server.type`, `acs.home`, `host.name`, `akka.use.ephemeral.port`, `disable-event-transport`, `-Xmx20G`, classpath `deployed.classpath` (:8-26).

### 4.2 What the tool JVM initializes
- **Registry:** first use of `com.atypon.registry.Config` runs its `<clinit>`, which calls `ServiceLoader.load(ConfigInitializer)`. That finds `literatum/src/resources/META-INF/services/com.atypon.registry.spi.ConfigInitializer` → `LiteratumConfigInitializer` → `LiteratumRegistryFactory.createLiteratumRegistry()` (`literatum/src/java/com/atypon/literatum/registry/LiteratumRegistryFactory.java:51-85`). Loaded from `WEB-INF`: `props.files.<DEPLOY_HOST>`, `literatum.props.xml`, `host.props.*`, `midtier.props.host.<server.type>.xml` (so **`backstage` overlays apply to tools**), `deployconf.props.xml`, and, because `COMMAND_LINE=true`, `host.props.<host>.<type>.xml`, **`literatum.tool.props.xml`** and **`<product>.tool.props.xml`** (:158-163).
- **Spring:** tools call `LegacySingletons.getSpringAdapter()` / `SpringAdapter.init()` (`LegacySingletons.java:56-68`). That builds and refreshes the **full component context** (same `components/` list as a server, note 12 §2.2) and registers `SpringAdapter.close` at `PRIORITY_SPRING`. What differs from a server:
  - **No `Main.run`/`initialize()`**: no `ManagementService`, no `configureLogging` (unless the tool calls it), no `system/properties`, no preload, no `SearchConfigurationLoader` (unless called), and **no `DbConf.start()`**. **DB `REGISTRYVALUE` overrides are therefore NOT applied in tool JVMs** (`DbConf.java:45-49`; the resolver returns an empty map while `enabled=false`, :162-169). A tool can see different config than the running backstage.
  - **No robots**: `Main.preload` is false, so `RobotsRegistrar` registers nothing and there is no `robotsExposer`.
  - `robotManager` (`RobotManager_Akka` on IBM) **is** created, so the tool JVM joins the env's Akka cluster on an ephemeral port. passport-cluster reads `-Dextra-active-profiles` and `-Ddisable-event-transport` (2110.0.1 `ClusterConfig` bytecode; PC `ClusterConfig.scala:330-355`). **`dummy-mutex` and `dummy-robots` are not in the list**, so cluster mutexes and robots in a tool are real.
- **Logging:** if the tool never calls `LogConfiguration.configureLogging()` (AddAtyponIPs does not), log4j stays on **`log4j2-boot.xml` → Console only** (`literatum/src/resources/log4j2-boot.xml:9-17`). That is why `ERROR ACS - Invalid IP address!` appears in the DS RunCLI log. If it does call it, `log.dir` defaults to **`./log/<product>/`** relative to the JVM's cwd (`LogConfiguration.java:68-73`): for `run tool` that is `$SCRIPTS_HOME/operations/tools/log/<product>/literatum.log`; for `bkstg` it is the operator's `$PWD/log/<product>/`. **It is not the server's log dir.**

### 4.3 ShutdownManager and why a tool JVM can fail to exit (LIT-682969)
- `ShutdownManager` (`literatum/src/java/com/atypon/literatum/acs/ShutdownManager.java`, read fully):
  - It is a `LiteratumThread` **registered as a JVM shutdown hook in its constructor** (:127-132).
  - `shutdown()` (:64-78) is one-shot. A second call throws `IllegalStateException("Shutdown has already been invoked!")`, which is why PR #14157 added the `hasShutdownTriggered()` guard.
  - Listeners run **sorted by ascending priority** (reverse, then stable sort, :140-153): `PRIORITY_DEFAULT` 0 → metrics 990 → **cluster 999** → `PRIORITY_LOG_MANAGER` 1000 → **Spring 2000** → log4j MAX. The Akka `ClusterSystem` is therefore shut down **before** the Spring context closes, and Spring's `RobotManager_Akka.shutdown()` then calls `RobotsAdapter.remove(…, 20s).join()` against an already terminated cluster.
  - Each listener prints `ShutdownManager: invoking shutdown hook <class>`. Errors print `Exception performing shutdown cleanup for object …`. The end prints `ShutdownManager: Shutdown finished`.
- **`shutdown()` never calls `System.exit`.** The JVM exits only when `main` has returned **and no non-daemon thread is alive**. `LiteratumThread` never sets daemon (`literatum/src/java/com/atypon/literatum/util/thread/LiteratumThread.java`: no `setDaemon`), so any `LiteratumThread` started from `main` is non-daemon, and so are Akka dispatcher threads unless the actor system terminated. Some tools end with an explicit `System.exit(0)` on the success path only (e.g. `ContentSuppressionIndexer.main` :158; the usage path :144). **An exception in `main` skips that exit.**
- **So an exception in `main` produces one of two states:**
  1. The main thread blocks **inside a listener**. The last line is `ShutdownManager: invoking shutdown hook <X>` with no `Shutdown finished`. `X` is the stuck listener: typically the cluster listener (`clusterSystem.shutDown().get()` has no timeout, `SingletonPassportClusterProvider.java:114-125`) or Spring close (`RobotManager_Akka.shutdown` `.join()`, `RobotManager_Akka.java:138`).
  2. `Shutdown finished` is printed, `Exception in thread "main" …` follows, and the process stays up because a non-daemon thread survives.
  
  In both states Ant's `<java fork>` waits forever, `BUILD FAILED` is never printed, and the DS RunCLI sits in `Executing`. It ends only at the connection idle TTL (`Force connection close, connid=`, default 1 h / `timeout.RunCLI`, note 01) or a manual cancel. **Which exact thread or listener held the LIT-682969 JVMs is Unverified.** The PRs so far only added tracing (#14129), the double-shutdown guard (#14157) and the JspScript guard (#14154).
- **Log markers of the hung state (in the DS RunCLI log, since tool output is stdout):** the exception text (`ERROR ACS - Invalid IP address!`, `DbException: Missing max ip address`, `ReadOnlyException`), then `Shutting down AddAtyponIPsToAtyponInstitution class`, `ShutdownManager: Shutdown begins...`, a series of `ShutdownManager: invoking shutdown hook …`, then **silence**, then `Force connection close`. Also possible after shutdown: `Database pool not yet initialized, skipping JspScriptScheduleTask` and `Pool jdbc is not configured` (DB used after Spring closed the pools, §5.2), and `Shutting down ClusterSystem bypassing ShutdownManager` / `IllegalStateException: Shutdown has already been invoked!` from the JVM hooks if the process is finally killed with SIGTERM.
- **What to check next (read-only):**
  - The last `ShutdownManager: invoking shutdown hook` line before the silence.
  - Whether `Shutdown finished` and `Exception in thread "main"` were printed.
  - Whether the java process is still alive on the host (`pgrep -af 'Dmain.class=com.atypon.modules.migration.AddAtyponIPsToAtyponInstitution'`). If so, `jstack <pid>` (read-only) shows the non-daemon threads. That is the evidence LIT-682969 needs.

---

## 5. Registry / DbConf / `Registry is not yet initialized` / `Pool jdbc is not configured`

### 5.1 `RegistryException: Registry is not yet initialized, please create and install registry`
- Library `com.atypon.registry.Config` 1.3.5 (javap): `getRegistryInstance()` returns the thread-local registry, else static `INSTANCE`. If `INSTANCE` is null it throws that exact message. `INSTANCE` is set **only in `Config.<clinit>`** from the **first** `ConfigInitializer` found by `ServiceLoader.load(ConfigInitializer.class)`, which uses the **thread context classloader**, or later by an explicit `setRegistryInstance`. A second set warns `"Attempt to override Registry instance"`.
- **So the message means one of three things:**
  1. **`Config` was first touched on a thread whose context classloader cannot see `META-INF/services/com.atypon.registry.spi.ConfigInitializer`.** Ant in-process (`fork="no"`, e.g. `tool.xml inlinemain`, or the patch Ant task) is the known case. `DbPatchSystem.run` works around it with `withContextClassLoader(LiteratumConfigInitializer.class)` (`literatum/src/java/com/atypon/literatum/util/db/patch/DbPatchSystem.java:112-118`). Otherwise the classpath lacks the literatum classes or resources: a wrong `acs.home`/`DEPLOY_HOME`/`PRODUCT_NAME`, or a missing `webapps/<product>`. Because `<clinit>` runs once, **the JVM never recovers**.
  2. **Re-entrant use during `Config.<clinit>`**: code inside `LiteratumRegistryFactory.createLiteratumRegistry()` touches `Config` on the same thread. That is wrapped as `LiteratumException("failed to build")`, and `Failed to parse registry: …` is mailed when `LOCAL_BASE` is set (:79-84).
  3. Something called `Config.clearThreadLocalInstance` / thread-local juggling. Not seen in lit-2610 tool paths.
- **Contrast:** a registry that **fails to build** gives `LiteratumException: failed to build` / `Error loading property file from system property: <f> : Killing server` (:121) and then `NoClassDefFoundError: Could not initialize class com.atypon.registry.Config`, **not** "not yet initialized". A missing `acs.home` prints `Error in loading initial XML configuration files: the system property "acs.home" is not found` and **`System.exit(1)`** (:230-235). A missing `DEPLOY_HOST` prints `Error: failed to get DEPLOY_HOST` + `exit(1)` (:214-219).
- **pnas `contentsuppression.index -a` (note 13 row 88):** `ContentSuppressionIndexer.main` calls `configureLogging()` then `SpringAdapter.init()` (`publish/src/java/com/atypon/publish/search/collections/contentsuppression/index/creation/prepare/ContentSuppressionIndexer.java:121-159`). It ends with `System.exit(0)` only on success, so after the `RegistryException` → `Pool jdbc` errors it **stayed alive until the idle TTL**, which matches the `Force connection close` at 06:01. Which cause (1–2) applied is Unverified without the full stack. The first frame under `Config.getRegistryInstance` shows who touched `Config` first, and on which thread.

### 5.2 `IllegalStateException: Pool <name> is not configured`
- Thrown by `DataSourceManager.getDS(dsName)` when the pool map has no entry for that name (`literatum/src/java/com/atypon/literatum/persistence/DataSourceManager.java:350-360`). The pools are built by `newDataSourceManager` from `database/dbPoolName` (first must be `jdbc`) plus `database/obfuscatedDbPool/*` (:75-123). The key sets under `database/<pool>/*` were not opened.
- **Most important cause:** `DataSourceManager.close()` (`@PreDestroy`, :133-139) **removes every pool**, but the static `LegacySingletons.dataSourceManager` is **not cleared**. Any DB access after the Spring context closed therefore gets **`Pool jdbc is not configured`**. That happens after `ShutdownManager` runs (Spring at priority 2000), after a failed refresh tore the context down, and in daemon schedulers like `JspScriptScheduleTask` (hence PR #14154).
- A genuinely missing pool config instead fails **at startup** with `No database pools are defined` or ``default pool name must be `jdbc` ``.
- So `Registry is not yet initialized` followed by `Pool jdbc is not configured` (pnas) reads as: startup failed → Spring closed or never finished → some thread still hit the DB → the JVM did not exit.
- **What to check next (read-only):**
  - Order of events in the RunCLI log: was there a `Cannot initialize Spring` or `ShutdownManager: Shutdown begins...` before the first `Pool jdbc` line?
  - On the host, `ls $DEPLOY_HOME/webapps/$PRODUCT_NAME/WEB-INF/classes/META-INF/services/` and `…/WEB-INF/props.files.$DEPLOY_HOST` (file names only).
  - `echo $DEPLOY_HOME $PRODUCT_NAME $DEPLOY_HOST` in the DS user's shell (run.sh prints them in its `Your JAVA_HOME is …` banner; check the RunCLI log header).

### 5.3 DbConf
- `DbConf.start()` (`literatum/src/java/com/atypon/literatum/registry/DbConf.java:45-49`) enables the `database` registry source, backed by all `DbRegistryValue` rows (`Finder.of(DbRegistryValue).all()`, :181-188), and registers a `DbChangeEvent` listener that invalidates it (:192-197). It is called only at the end of `Main.run` (`Main.java:142-144`), after Spring and search config.
- **Consequences:**
  - During Spring startup, DB overrides are **not** visible yet (every bean reads file-based config).
  - **CLI tools never enable DbConf** (§4.2).
  - `DbConf.start` itself needs the Broadcaster (`getBroadcaster()` → LIT-604088 if called outside Spring) and the `jdbc` pool (the first query happens on the next `Conf.invalidate("database")` resolve).
- Failure in `DbConf.start` goes to `ERROR LOADING PRODUCT … KILLING THE SYSTEM` (note 12).

---

## 6. Failure signatures (log text → meaning → next check)

| Log text | Where | Meaning | Next check (read-only) |
|---|---|---|---|
| `Cannot invoke "…PluginMetrics.timer(String)" because "this.clusterMetrics" is null` | patch output, literatum.log, stderr | LIT-683431: build from source with the LIT-643926 stubs (no build-time patch) | `grep LIT-643926` in `cluster/*.java` at the env's build branch+commit; ProductBuild log for `LIT-656000 … patch failed` |
| `[ClusterMutexManager] Failure to load ClusterMutex class from registry cluster/mutex/clusterMutexClass` → `ExceptionInInitializerError` | cluster.log (FATAL), patch output | Constructing `PassportClusterMutex` failed (usually the NPE above; else Akka/ZK) | First `Caused by`; `cluster/mutex/clusterMutexClass` value for that env (midtier.props.IBM*.xml) |
| `NoClassDefFoundError: Could not initialize class com.atypon.literatum.cluster.ClusterMutexManager` | any | Same, second and later use in the same JVM | Look further up for the first failure; the JVM needs a restart |
| `Error creating bean with name 'robotsExposer': Invocation of init method failed` | stderr / catalina / bks log → KILLING | Robot expose failed at startup; for WfRobot engines it runs `checkNewDef` → ClusterMutex | First `Caused by`: clusterMetrics (LIT-683431), Akka `NoClassDefFound` (root-pom), `Exception initializing cluster` |
| `LIT-604088: legacy singleton has not been set yet` (logger CoreSpringConfig) | literatum.log / stdout | Static accessor used before Spring set it or after Spring closed it; secondary after a failed refresh | Frame under `requireNonNull` = getter, next frame = caller; in tools, pre-revert `AwaitMetricsMonitor` |
| `LIT-604088: legacy singleton is being initialized` | same | Recursive `getBean` during init | Caller frames |
| `Failed to acquire resource [<r>] due to some transient error. For more info check the akka logs.` | literatum.log | Akka/ZK mutex adapter timeout | cluster.log, ZK health |
| `cluster/robots-manager-implementation value X is not supported` | startup → KILLING | Bad robot manager class | props chain |
| `Could not find an institution with description 'Atypon Institution'` | RunCLI | Data: no such institution on that site | Institution list in admin UI |
| `ReadOnlyException` (no message) at `InstitutionUser.saveImpl` ← AddAtyponIPs | RunCLI | "Atypon Institution" is in a read-only group (own CR is cleared by `markEditable`) | Parent groups of the institution and their `ENTITY_ACCESS_RIGHTS` |
| `ERROR ACS - Invalid IP address!` → `DbException … Missing max ip address` | RunCLI stdout | A line in the passed IP file does not resolve (`InetAddress.getByName`) | The `-Dargs` file used; line format `min-max`, no inline comments |
| `>>> WARNING -- …IP <x> is not white listed in zuperAdmin config!!` | RunCLI | Non-fatal; `zuperAdmin/ip-list` does not cover the IP | props `zuperAdmin/ip-list` (key only) |
| `ShutdownManager: invoking shutdown hook <X>` and then silence | RunCLI | Main thread blocked in listener X (cluster/Spring) | jstack of the tool pid |
| `ShutdownManager: Shutdown finished` + `Exception in thread "main"` and then silence | RunCLI | A non-daemon thread keeps the JVM alive (LIT-682969) | jstack; the idle TTL will end the DS step |
| `Force connection close, connid=` | DS log | DS idle TTL killed a hung command → Failure | See the two rows above |
| `IllegalStateException: Shutdown has already been invoked!` | stderr | Second `shutdown()` (pre-#14157 tool, or the JVM hook after an explicit shutdown) | Benign by itself |
| `Registry is not yet initialized, please create and install registry` | tool/patch stdout | `Config` found no ConfigInitializer (wrong TCCL/classpath), or re-entrant `<clinit>` | First frame under `getRegistryInstance`; fork vs in-process Ant target; `WEB-INF/classes/META-INF/services` |
| `failed to build` / `Error loading property file from system property: … : Killing server` | stdout | Props parse or include failure | The named props file |
| `Error in loading initial XML configuration files: the system property "acs.home" is not found` / `Error: failed to get DEPLOY_HOST` | stdout, exit 1 | Tool env not set | run.sh banner `Your … is` lines |
| `ERROR: DEPLOY_HOME not found in your environment.` (run.sh) | RunCLI | Env missing, run.sh `exit` = 0 | DS user env; `setprod` |
| `Pool jdbc is not configured` | tool/server | DB used after Spring closed the pools (or pools never built) | Was `Shutdown begins` / `Cannot initialize Spring` earlier? |
| `No database pools are defined` / ``default pool name must be `jdbc` `` | startup | Config chain lacks `database/dbPoolName` | props chain / deployconf |
| `Database pool not yet initialized, skipping JspScriptScheduleTask` | literatum.log | Benign guard (PR #14154) | none |
| `Loaded New Relic metrics config: … Api key: …` | literatum.log (DEBUG) | **Secret-bearing line** | Filter before sharing |

---

## 7. Coverage

**Read fully by me (lit-2610 @ `9f8eb846e`):**
- `ClusterMutexManager`, `ClusterMutex`, `PassportClusterMutex`, `PassportClusterMetricsProvider`, `SingletonPassportClusterProvider`, `RobotManager`, `RobotManager_Akka`, `PassportClusterSpringConfig`, `RobotsRegistrar`
- `LegacySingletons`, `ShutdownManager`, `AddAtyponIPsToAtyponInstitution`, `Patch032053`, `Patch009529`
- `metrics/newrelic/{MetricsService,MetricsManager,MetricsFactory,service/ClusterMetrics}`
- `CoreSpringConfig`, `Main`, `LiteratumConfigInitializer`, `DbConf`, `LiteratumRegistryFactory` (secret-filtered)
- PT `deployserver/run-cli.sh`, `operations/tools/run.sh`, `backstage.sh` (to :110)

**Read in part:**
- `WfRobot` (84-220, 380-425)
- `IdentityImpl` (600-668, 1260-1275, plus method-line grep)
- `LicenseImpl` (616-636, getCopy grep)
- `EntityAccessRights` (25-75)
- `AbstractDbBasic` (289-335, 955-975, grep of ReadOnlyException)
- `AbstractDbEnhanced` (45-56, grep)
- `TableDef` (1520-1560)
- `InstitutionUser` (grep, 224-239)
- `AbstractIPRangeUser` (60-190)
- `IPAddressUtil` (30-75, 255-310)
- `DataSourceManager` (60-140, 330-400)
- `ResourceClusterMutex` (13-64, grep), `AwaitMetricsMonitor` (grep), `Broadcaster` (366-420 grep)
- `JspScriptScheduleTask` (25-70), `AuditedJspScriptAction` (1-45)
- `ContentSuppressionIndexer` (115-160)
- `LogConfiguration` (40-110), `log4j2.xml` (appender grep), `log4j2-boot.xml` (grep)
- `SpringAdapter` (288-300)
- `literatum.props.xml` (5830-5886, 26042-26087)
- `midtier.props.IBM*.xml` / `akka-cluster.IBM-nonprod.xml` / `evans.xml` cluster blocks
- `literatum.tool.props.xml`, `marlin.tool.props.xml`
- PT `tool.xml` (1-51, 920-1010), `conf/backstage.xml` (8-75, 974-1003), `functions.sh` (1680-1717), `patch/common.patch.txt` (hunks 422-562, 1685-1935)
- LP `lit31708.sql`, `lit9529.sql` headers; `data/AtyponIPs/atyponIPs.txt` checked for **format and one IP prefix only; no IPs printed**
- passport-cluster 2110.0.1 jars (javap: `MetricReporting`, `MutexRequestProxyActor`, `DefaultRobotsAdapter`, `Metrics`; string grep of `ClusterConfig`); PC master `ClusterAdapter.scala`, `ClusterSystem.scala` 100-200, `ClusterConfig.scala` grep
- registry 1.3.5 `Config` (javap)
- GitHub PR #14129/#14154/#14157 diffs.

**Section 2** was read by a delegated agent (its coverage list is in §2). I did not re-read those files.

**Not read:**
- Library sources for passport-cluster 2110.0.1 (only bytecode signatures) and the metrics-newrelic lib (`SharedMetricsBootstrap`, `forPlugin`).
- `ArmiClusterSpringConfig` / `RobotManager_DbArmi` / `RicartAgrawala`.
- `IpRangeResolver`, `MembershipService` internals, `Transaction`.
- Maint and product branches (not cloned).
- Any real log of the failures in notes 13 and 14.

**Key Unverified items:**
1. Which non-daemon thread or listener keeps LIT-682969 tool JVMs alive (needs jstack).
2. The marlin `LIT-604088` RunCLI root (the pre-revert `AwaitMetricsMonitor` hypothesis).
3. Which invalid line broke the 18 Sep stag AddAtyponIPs runs.
4. Why aiaa's `104.030.132.204` user is read-only (it is not in the current atyponIPs.txt).
5. Whether maint/product branches cut before the lit-2610 revert still carry the `LIT-643926` null stubs. Now that PT #354 removed the build-time patch, they would fail again.

> **Correction (2026-09-26, eval loop 4, verified):** §5 "Pool jdbc is not configured" example (pnas): the cause is a post-shutdown DB call in `ContentSuppressionIndexer.main:153` after `SearchConfigurationLoader.loadAndRun` → `ShutdownManager.shutdown()` (:267), not a startup/registry problem. Paths in this note omit the `atypon/` prefix: e.g. `atypon/literatum/src/java/com/atypon/literatum/...`, `atypon/publish/src/java/...`, `atypon/product/midtier/conf/...`.
