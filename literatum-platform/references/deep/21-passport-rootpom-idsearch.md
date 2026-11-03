# 21 — platform-passport-cluster, root-pom, id-search: how they feed Literatum and how they fail

Written 2026-09-25. Read-only: no builds, no runs, no fetches into the clones. The only writes were this note and scratch files (a GitHub tarball of `passport-cluster-2110.0.1`, API JSON dumps) in the session scratchpad.
Status tags: **Confirmed** (read in code, bytecode or git), **Inferred** (reasoned from code, not seen in a log), **Unconfirmed** (not checkable here).

---

## 0. Coverage (commits read)

| Repo / source | Ref (commit) | Read fully | Sampled / grep only |
|---|---|---|---|
| platform-passport-cluster (local, shallow, 1 commit) | master `8bd8a50` (2026-09-24, merge of PR #174) | `readme.md`, root `pom.xml` (filtered), `core/.../japi/ClusterSystem.java`, `core/.../Otel.scala`, remoting and downing sections of `core/.../passport-cluster.conf` | the rest of the 308 files (grep for adapter APIs and metrics only) |
| platform-passport-cluster @ `passport-cluster-2110.0.1` (GitHub tarball, `875af8c54f`, 2020-09-18) | the version Literatum consumes | `core/.../ClusterSystem.scala:195-216`, `core/.../internal/metrics/MetricReporting.scala`, `mutex/.../MutexAdapter.scala:35-59, 300-345`, `robots/.../RobotsAdapter.scala:42-49` | grep across all modules for `toTyped`/`toUntyped`/`ActorMaterializer`/`MetricsProvider` |
| passport-cluster 2110.0.1 **jars** in `~/.gradle/caches` (all 6 modules) | the published artifacts | constant-pool scan (`unzip -p … \| strings`) of every class | — |
| akka/akka on GitHub @ `v2.6.21` | `akka-actor-typed/.../scaladsl/adapter/package.scala` | implicit class list | — |
| akka-actor-typed 2.5.31 jar (gradle cache) | — | class listing of `scaladsl/adapter/package$*` | — |
| GitHub API: passport-cluster | PR #174 metadata and body; tags; the last 30 master commits; `compare 2110.0.1...2110.0.2`; `pom.xml` at 2110.0.1 and 2110.0.2 | — | — |
| literatum-lit-2610 (local, shallow) | origin/lit-2610 `9f8eb846e`, origin/master `0c62d0157` (both 2026-09-25) | `PassportClusterMutex.java`, `ClusterMutexManager.java`, `RobotsRegistrar.RobotsExposer`, `Main.abortSystemStartup`, `PassportClusterMetricsProvider.java` (lit-2610 and master), `SingletonPassportClusterProvider.java:18-90` (master), `versions.properties` and `build.gradle:78` on both refs | Akka import census (10 files); `clusterMutexClass` / `robots-manager-implementation` props census |
| GitHub API: literatum | commit `3b5d53c2` (file list + patches for the two cluster files); PR #9376 (metadata, file list, version pins) | — | — |
| root-pom (local shallow master `528af5b`, plus GitHub API) | tags `atypon-root-pom-2610.0.2 … 0.7`; master `528af5b041` and both of its parents; `lit-2610` head | `compare` 0.2…0.3, 0.3…0.4, 0.4…0.5, 0.5…0.6, 0.6…0.7, 0.5…0.7 (full patches); the list of managed artifacts per changed property (parsed from master `pom.xml`) | the rest of `pom.xml` |
| id-search (local shallow master `5b508a4`, 2026-07-28) | + GitHub `pom.xml` at `search-2610.0.25` (`ea971f3df8`) and `search-2710.0.5` (`ffa595d42e`) | README, root `pom.xml` head, `SearchCollection.java`, `SearchServiceProxy.java`, `CoreApiManager.java:1-80` | the rest of the client (config-key grep), interceptors (grep) |
| id-core (local, `afce084`) | `core-2610.0.11` and `core-2710.0.5` are **byte-identical to master** under `id-solr/.../solr/` and `SolrCoreModel.java` (`git diff --quiet` = 0) | `CloudSolrJClientFactory.java`, `SolrConfHelper.java`, `SolrCoreModel.java`, `LitSolrClient.java:40-110, 425-496` | `ZkUtils`, `ZkStateFactory` (names only) |
| deployconf (local `ad1c87a`) | `xslconfig/deployconf.xsl:1535-1590` | the `index/solr/zookeeper-connection` templates | — |

---

## 1. platform-passport-cluster

### 1.1 Architecture (Confirmed)
- It is Atypon's Akka-cluster middleware for Literatum. The entry point is `ClusterSystem`, and adapters are got with `XAdapter.get(clusterSystem)`. Maven modules: `core` (bootstrap, config, downing, ZK join), `broadcast` (pub/sub over an Akka-stream TCP pipeline), `mutex` (ZooKeeper locks via Curator `LockInternals`), `event-transport` (LevelDB-persisted events with S3, file and consumer sinks), `crdt` (distributed-data replicator), `robots` (cluster-singleton "robots" plus an ID generator), `mutex-cleanup-tool` and `event-transport-flush-tool`.
- Remoting is Artery at both 2110.0.1 and master. Downing uses the custom `com.atypon.cluster.downing.MajorityLeaderAutoDownLogging` with `akka-cluster-custom-downing_2.12:0.0.12`.
- **Metrics at 2110.0.1** (the version Literatum runs): the host passes a `MetricsProvider` (Codahale-style counter, gauge, histogram, meter and timer, plus optional Prometheus) to `japi.ClusterSystem(ClusterConfig, MetricsProvider)`. `ClusterSystem.apply` stores it in the `Metrics(actorSystem).provider` extension (`ClusterSystem.scala:206-209`). Every adapter gets its metrics through `MetricReporting.provider` (`MetricReporting.scala:15, 49-65`).
- **Metrics at master** (after PR #174 and the LIT-643926 commits `459e632c90` and `da801d6deb`): `MetricsProvider` is gone. The constructor is now `japi.ClusterSystem(ClusterConfig, OpenTelemetry)` (`japi/ClusterSystem.java:21-22`), and the `Otel` extension falls back to `OpenTelemetry.noop()` when no setup is given (`Otel.scala`). So master is **not API-compatible** with Literatum's `PassportClusterMetricsProvider`. That is why Literatum PR #9376 deletes the class.

### 1.2 Akka API usage: proof that 2110.0.1 breaks on Akka 2.6 (Confirmed)
- In Akka 2.5.31 the implicit classes in `akka.actor.typed.scaladsl.adapter` are `UntypedActorSystemOps`, `UntypedActorContextOps` and `UntypedActorRefOps` (plus the `Typed*` ones). This was checked in the cached 2.5.31 jar.
- In Akka **2.6.21** they are renamed `ClassicActorSystemOps`, `ClassicActorContextOps` and `ClassicActorRefOps` (`package.scala:39, 93, 154` at tag `v2.6.21`). No `Untyped*` class remains.
- The published **2110.0.1 jars** reference the removed classes directly in bytecode (constant-pool scan):
  - `passport-cluster-robots`: `com/atypon/cluster/DefaultRobotsAdapter.class` and `robots/RobotsSupervisorActor.class` reference `akka/actor/typed/scaladsl/adapter/package$UntypedActorSystemOps$`.
    - Source: `RobotsAdapter.scala:49` `untypedSystem.toTyped`; `RobotsSupervisorActor.scala:76` `ClusterSingleton(context.system.toTyped)`.
  - `passport-cluster-crdt`: `DefaultMultiMapReplicator.class` references `UntypedActorSystemOps$` (source `MultiMapReplicator.scala:66`). `DataReplicationSupervisorActor.class` references `UntypedActorRefOps$` / `toUntyped$extension`, and `internal/crdt/package$TypedActorFactoryImpl$.class` references `UntypedActorContextOps$`.
  - `core`, `mutex`, `broadcast` and `event-transport` have no `Untyped*` references. They do use `ActorMaterializer`, which Akka 2.6 deprecates but still ships.
- So with Akka 2.6.21 on the classpath, the first `RobotsAdapter` (or `MultiMapReplicator` / data-replication) use throws **`java.lang.NoClassDefFoundError: akka/actor/typed/scaladsl/adapter/package$UntypedActorSystemOps$`**. That is the 2610.0.6 / 2610.0.4 signature. In Literatum this is reached through `RobotManager_Akka.java:32` `RobotsAdapter.get(clusterSystem)`. `RobotManager_Akka` is selected by `midtier.props.akka-cluster.IBM(-nonprod).xml` (`robots-manager-implementation`), and `RobotsExposer` (`RobotsRegistrar.java:88-110`) needs the RobotManager bean.
- Master passport-cluster has 0 `toUntyped` / `UntypedActor*` / `ActorMaterializer` hits in main code and uses `toClassic`. It is fixed at source but **not released** (see 1.4).
- Other 2.5-era dependencies in 2110.0.1 that could break under 2.6 (**Inferred**): `com.github.romix.akka:akka-kryo-serialization_2.12:0.5.2` and `akka-cluster-custom-downing 0.0.12`. The NoClassDefFoundError is deterministic and comes first.

### 1.3 Versions consumed by Literatum (Confirmed)
| Literatum ref | `passportClusterVersion` (`atypon/literatum/versions.properties:117`) | modules (`literatum/build.gradle:533-538`) |
|---|---|---|
| lit-2610 `9f8eb846e` | **2110.0.1** | broadcast, core, crdt, event-transport, mutex, robots |
| master `0c62d0157` | **2110.0.1** | same |

- 2110.0.1 = `875af8c54f`, released 2020-09-18 with parent root-pom `2110.0.2` (Akka 2.5 era). 2110.0.2 (2021-03-01) exists but is unused.
- PR #9376 (the LIT-643926 Literatum side) moves it to `2610.0.2-SNAPSHOT` together with `parentPomVersion 2610.0.6-SNAPSHOT`.

### 1.4 PR #174 (Confirmed, `gh api …/pulls/174`)
- "Upgrade Akka from 2.5.31 to 2.6.21", by `nvrs`, opened 2026-01-12. **Merged 2026-09-24T07:13:06Z** into master as merge `8bd8a5075a` (head `da801d6deb`). 23 commits, 106 files, +1214 / −1368.
- Changes: Akka 2.6.21, Akka HTTP 10.2.10, Alpakka S3 3.0.4, akka-kryo-serialization `io.altoo` 2.4.3, Kryo 5.3.0, AWS SDK v1→v2. `ActorMaterializer` became `Materializer` in 19 files, and `toUntyped` became `toClassic`. The branch also carries the LIT-643926 OTel migration.
- Unchecked test-plan items in the PR: integration tests (`mvn verify`), staging deploy, multi-node cluster formation.
- **There is no release yet.** The tag list has nothing after `passport-cluster-2110.0.2`. `22894a0022` "prepare release passport-cluster-2610.0.1" (2026-04-03) is in history, but `git/refs/tags/passport-cluster-2610.0.1` returns 404. Master pom is `2610.0.2-SNAPSHOT` with parent root-pom `2610.0.4`.
- So the memory line "LIT-643926 blocked on platform-passport-cluster #174" is **stale**. #174 is merged. What is missing now is a released passport-cluster 2610.0.x, plus Literatum #9376 (open, base `lit-2610`, last updated 2026-09-01) pinning it.

### 1.5 Why `clusterMetrics` is null without the LIT-656000 patch (Confirmed)
Literatum side:
- LIT-591953 moved Literatum metrics to OTel and removed `com.atypon.literatum.metrics.newrelic.service.ClusterMetrics`. Passport-cluster 2110.0.1 still needs a Codahale `MetricsProvider`, so the provider was stubbed until LIT-643926. The code on **master `0c62d0157`**, `PassportClusterMetricsProvider.java`:
  - `:17-20` constructor: `clusterMetrics = null; // TODO revisit after LIT-643926` and `prometheusClusterMetrics = null;`
  - `:22-45`: every method dereferences it, e.g. `:43-44` `timer(...) { return convert(clusterMetrics.timer(metricName)); }`
  - `:61-62`: `getClusterMetrics() { return /*clusterMetrics*/ null; }`
  - `SingletonPassportClusterProvider.java:22-23` builds `new PassportClusterMetricsProvider()`. `:77` is `new ClusterSystem(clusterConfig, metricsProvider)`. `:79-85` comments out the two `cluster/offline` gauges, so the null does not blow up there.
- The rebuild.py patch (`master.patch.txt` / `lit-2610.maint.txt`) put back the newrelic `ClusterMetrics` and the constructor `clusterMetrics = ClusterMetrics.INSTANCE.getPluginMetrics()`.
  - That same change is now in git as `3b5d53c2` (authored 2026-09-14, 36 files). Its hunk on this file replaces the two `= null` lines and the `getClusterMetrics` return, and un-comments `SingletonPassportClusterProvider:79-85`.
  - lit-2610 `9f8eb846e` has it: its `PassportClusterMetricsProvider.java:18-20` uses `ClusterMetrics.INSTANCE`.

Passport-cluster side (2110.0.1):
1. `japi.ClusterSystem.java:21-22` → `ClusterSystem.apply(config, Option(metricsProvider))`, then `ClusterSystem.scala:206-207` `Metrics(actorSystem).provider = mp`. The provider object is non-null; only its field is null.
2. `PassportClusterMutex.java:18` `MutexAdapter.get(SingletonPassportClusterProvider.INSTANCE.getOrCreate())` → `MutexAdapter.scala:326-328` `new DefaultMutexAdapter(…, new MetricReporting { provider = Metrics(clusterSystem.actorSystem).provider }, …)`.
3. `DefaultMutexAdapter` field initialisers `MutexAdapter.scala:51-59` start with `metricReporting.timer("cluster/mutex/acquire/latency")` → `MetricReporting.scala:58-59` `provider.timer(name)._2` → `PassportClusterMetricsProvider.timer` → `clusterMetrics.timer(...)` on null → **NullPointerException** inside `DefaultMutexAdapter.<init>`.
4. `ClusterMutexManager` constructor (`ClusterMutexManager.java:81-89`) runs a sanity `getClusterMutexWithException(REPORT_LOCK, REPORT_LOCK)`. The NPE comes back wrapped in `InvocationTargetException`, and `:97-101` logs `Log.fatal` "[ClusterMutexManager] Failure to load ClusterMutex class from registry cluster/mutex/clusterMutexClass" and rethrows `RuntimeException`.
5. From the incident (not traced bean-by-bean here): a robot bean created in `RobotsExposer.start()` (`RobotsRegistrar.java:101-110`) uses the mutex, Spring init fails, and `Main.abortSystemStartup` (`Main.java:441-450`) prints `********** ERROR LOADING PRODUCT <p> **********` … `********** KILLING THE SYSTEM **********` and calls `System.exit(1)`.
- This only happens where `cluster/mutex/clusterMutexClass` = `PassportClusterMutex`: `midtier.props.IBM-beta.xml:117`, `midtier.props.IBM-stag.xml:191`, `midtier.props.IBM.xml:105`. The default is `RobotClusterMutex` (`literatum.props.xml:5883`).

### 1.6 Current exposure (Confirmed from git, runtime Unconfirmed)
- **Literatum master** carries both defects:
  - (a) the null provider, with no build-time patch since platform-tools #354;
  - (b) root-pom `2611.0.5-SNAPSHOT`, whose master `pom.xml` has **Akka 2.6.21** (see 2.3), alongside passport-cluster 2110.0.1.
- A master build that resolves that SNAPSHOT would get the `UntypedActorSystemOps` NoClassDefFoundError wherever `RobotManager_Akka` or CRDT is used, and the NPE wherever `PassportClusterMutex` is used. Whether the SNAPSHOT is published with 2.6.21 content is **Unconfirmed**. Check it with `:literatum:retrieveVersions --dependencies com.typesafe.akka:akka-actor-typed_2.12` or the build log.

---

## 2. root-pom (`com.atypon:atypon-root-pom`)

### 2.1 How Literatum consumes it (Confirmed; see note 15 §4.1)
- `atypon/build.gradle:78` sets `parentPomVersion`: lit-2610 `"2610.0.7"`, master `"2611.0.5-SNAPSHOT"`.
- `enforcedPlatform("com.atypon:atypon-root-pom:<v>")` is applied to `api`, `testImplementation`, `wars` and `aspectsourcesCompile` (`literatum/build.gradle:242-245`) and to aspectj (`AspectJPlugin.groovy:48-49`).
- Enforced means it **overrides** transitive and even explicit versions. For example `testImplementation akka-stream-testkit_2.12:2.5.31` (`literatum/build.gradle:206`) and passport-cluster's own Akka 2.5 deps are forced to the root-pom's `akka.version`. That is how a pom-only release can break a runtime jar Literatum never rebuilt.

### 2.2 Version-by-version diff (Confirmed, `gh api compare`; only `pom.xml` changes in each)
Every artifact whose managed version moved is listed; `<version>`/`<tag>` bumps are left out.

| Step | Commits (root-pom) | Property change | Managed artifacts affected |
|---|---|---|---|
| 2610.0.2 → **0.3** (`6ded837a67`, 2026-03-24) | `3403579ba8` LIT-661923 (PR #71) | `axis2.version 1.5 → 2.0.0`; `axis2-transport-http` `1.5-atypon` → `${axis2.version}` (2.0.0); **new** managed `axis2-xmlbeans` `${axis2.version}` | `org.apache.axis2:axis2`, `axis2-adb`, `axis2-kernel`, `axis2-transport-local` (via property), `axis2-transport-http`, `axis2-xmlbeans` → 2.0.0 |
| 0.3 → **0.4** (`3cb2a5cd7d`, 03-31T15:15Z) | `bb5befb9d8` LIT-643926 "AKKA related libraries updated…" | `scala.version 2.12.8 → 2.12.21`; `akka.version 2.5.31 → 2.6.21`; `alpakka.version 1.0.2 → 3.0.4`; `akka-http.version` unchanged 10.1.12 | scala: `scala-library`, `scala-reflect`. akka (14): `akka-actor`, `-actor-typed`, `-cluster`, `-cluster-typed`, `-cluster-tools`, `-stream`, `-distributed-data`, `-coordination`, `-cluster-metrics`, `-slf4j`, `-remote`, `-protobuf`, `-persistence`, `-persistence-query` (`_2.12`). alpakka: `akka-stream-alpakka-s3_2.12`, `akka-stream-alpakka-kinesis_2.12` |
| 0.4 → **0.5** (`b407c51996`, 06-23) | `003f7c9dea` revert of `bb5befb9d8` (04-20); `da04351fe3` LIT-673028 (PR #75) | Akka/Scala/Alpakka **back** to 2.5.31 / 2.12.8 / 1.0.2; `lucene-solr.version 9.1.1 → 9.10.1`; `lucene-core.version 9.3.0 → 9.12.3` | the 18 artifacts above reverted; `solr-core`, `solr-solrj`, `solr-ltr` → 9.10.1; `lucene-core`, `-queryparser`, `-highlighter`, `-analysis-kuromoji`, `-analysis-common`, `-analysis-icu` → 9.12.3 |
| 0.5 → **0.6** (`527351ec0c`, 09-24T08:05Z) | `9bd073af4c` "Reapply LIT-643926" (09-01), merged as PR #76 `LIT-683155_akka_upgrade` (`7f0f21eb5a`, 08:01Z) | same as 0.3→0.4: Scala 2.12.21, **Akka 2.6.21**, Alpakka 3.0.4 | same 18 artifacts |
| 0.6 → **0.7** (`32686fbf9b`, 09-24T15:58Z) | `9a863f0517` revert (15:55Z) | back to 2.12.8 / 2.5.31 / 1.0.2 | same 18 artifacts |
| 0.5 vs 0.7 | — | none (only `<version>`/`<tag>`) | 0.7 ≡ 0.5 in content |

- Literatum lit-2610 pins (from note 15): 0.6 at `5b65a1f45c` (08:06Z), 0.7 at `00eaa17329` (15:59Z). For 0.4 the pin was reverted on 04-02 (`a17c9ac76d`).
- **Root cause of both Akka incidents (Confirmed by bytecode, 1.2):** root-pom enforced Akka 2.6.21, but Literatum still ships passport-cluster **2110.0.1**, compiled against Akka 2.5 and referencing `package$UntypedActorSystemOps$`, which is gone in 2.6.
  - The root-pom bump was meant to ship together with the passport-cluster 2610.0.x bump (PR #9376 pins both). The pom went out alone, twice.
  - Note 15's "2.5↔2.6 rolling-join" theory is not needed to explain the NoClassDefFoundError.
  - The timing fits: PR #174 merged at 07:13Z and the root-pom was released at 08:05Z the same morning, but no passport-cluster release followed.

### 2.3 Branch state today (Confirmed)
- root-pom `lit-2610` head: `2610.0.8-SNAPSHOT`, `akka.version 2.5.31`.
- root-pom **master** `528af5b041` (09-24T08:50Z, "Merge branch 'lit-2610' into master"): `2611.0.5-SNAPSHOT`, **Akka 2.6.21, Scala 2.12.21, Alpakka 3.0.4**.
  - Its first parent `73ca34f8da` (2026-04-20) re-applied the Akka change on master the same day lit-2610 reverted it. So master root-pom has had Akka 2.6 since April.
  - The merge happened between the 0.6 release and the 0.7 revert, and the revert was never merged to master.

---

## 3. id-search (`com.atypon.id:search`)

### 3.1 What Literatum uses (Confirmed)
- Declared in `literatum/build.gradle`: `federated-search` (jar + `metaproxy-config` zip + `metaproxy-executable` zip, `:344-350`), `id-search-client` (`:412`) and `id-search-core` (`:446`), all at `${searchVersion}`. 561 Literatum Java files import `com.atypon.id.search.*`, mostly `common.results`, `client.api`, `client.configurator` and `common.faceted`.
- **Two execution paths** in `id-search-client`:
  - **Remote gRPC service** when `search/service/enabled=true`: `SearchServiceProxy.java:35-84`. Nodes come from `search/service/nodes` (host/port list). The channel is round-robin via `SearchNameResolverProvider`, uses plaintext, and has `DeadlineInterceptor` (`search/service/deadline` default 20000 ms, `large-search-deadline` 180000 ms) and `CircuitBreakerClientInterceptor`. The latter counts `DEADLINE_EXCEEDED`/`UNAVAILABLE`… as failures of `SearchCircuitBreaker.SEARCH_SERVICE`.
  - **In-JVM ("direct")**, the default: `CoreApiManager` (`@Deprecated`) reflectively loads `com.atypon.id.search.core.api.{SearchCollectionCoreApi, SearchCoreApi, ScoreModelCoreApi, HighlighterCoreApi, IndexStateCoreApi, LicenseCacheApi, RecommendationsCoreApi}` in a static block (`:58-71`). A missing class gives `DirectApiCallException`.
- **Solr client (id-core `id-solr`, identical in core-2610.0.11, core-2710.0.5 and master):**
  - `SearchCollection` (`id-search-core/.../SearchCollection.java:58-94, 235-236`): one per `search/collections/<name>` registry entry. The core is `SolrCoreModel.findByName(solr-collection-name | name)`. `zkHost` is the collection's own `zkHost` if set, else `SolrConfHelper.getZkHost()`. It calls `LitSolrClient.newInstance(core.getCollectionName(), zkHost)`.
  - `SolrConfHelper`: ZK = `index/solr/zookeeper-connection` (or the runtime override set by `resetSolrJClients`). Solr is on only if `index/solr/enabled`. Enabled cores = `search/collections/defaults/enabled` ∩ the `search/collections/*` entries. The static `init()` runs at class load.
  - `CloudSolrJClientFactory`: one `CloudLegacySolrClient` per `cloud-<collection>-<zkHost>-<searchType>`, built from the ZK host list plus chroot, with `LitLBHttpSolrClient`, binary request/response, and parallel updates.
    - Timeouts come from `index/solr/zookeeper-timeout` and `index/solr/indexing-http-connection-timeout`, which are **required** (`Config.getDuration`), and from `index/solr/large-indexing-http-connection-timeout` (default 180 s).
    - The ZK string must match `(\S)+:(\d)+/(\S)+`, which requires a chroot.
  - Literatum defaults (`literatum.props.xml:13254-13260`): `zookeeper-connection` empty, `zookeeper-timeout` 5s, `indexing-http-connection-timeout` 30s. Deployconf fills it in (`deployconf.xsl:1560-1564`) as `<zk hosts:port,…>/<name_prefix><prod>[-<family>]`, or for `solr-wrapper` products `…/configs/solr/<prod>-<family>-v2` (`:1567-1582`).
- **Core names** (`SolrCoreModel`; the collection name is the lower-cased enum name): `jb` (default target), `contribautocomplete`, `caption`, `do`, `dbpubs`, `related`, `ctg`, `titleautocomplete`, `institutionautocomplete`, `topicautocomplete`, `contentsuppression`, `custompage`, `affiliation`, `publisher`, `entityrelation`, `offer`, `price`, `discount`, `campaigns`, `entitylinking`, `licensecache`, `recommendations`, `chunks`, plus `NOT_AVAILABLE`.
  - `findByName` strips a `_<timestamp>` suffix and a `<prefix>-` overload prefix, and returns **null** for unknown names.

### 3.2 Versions (Confirmed)
| Literatum ref | `searchVersion` | id-search tag commit | id-core | solr-plugins | parent |
|---|---|---|---|---|---|
| lit-2610 `9f8eb846e` (`versions.properties:136`) | **2610.0.25** | `ea971f3df8` 2026-08-02 | 2610.0.11 | 2610.0.16 | information-discovery-parent 2610.0.6 |
| master `0c62d0157` (`:138`) | **2710.0.5** | `ffa595d42e` 2026-06-23 | 2710.0.5 | 2710.0.5 | information-discovery-parent 2710.0.4 |
| id-search master `5b508a4` | 2710.0.7-SNAPSHOT | — | 2710.0.5 | 2710.0.5 | 2710.0.4 |

- Literatum master pins an id-search release **six weeks older** than lit-2610's. Fixes made on the 2610 line after 06-23 are not on master unless they were forward-ported. Which fixes those are was not checked.
- Solr server/client jars (`solr-solrj` etc.) are forced by the root-pom enforcedPlatform: 9.10.1 since root-pom 2610.0.5.

### 3.3 Failure modes (Inferred from code unless noted)
- Startup/config:
  - A missing `index/solr/zookeeper-timeout` or `indexing-http-connection-timeout` makes `CloudSolrJClientFactory` class init fail: `ExceptionInInitializerError`, then `NoClassDefFoundError: Could not initialize class com.atypon.id.core.solr.client.CloudSolrJClientFactory` on later calls.
  - `SolrConfHelper` static `init()` failing on a bad `search/collections` registry gives the same pattern for `SolrConfHelper`.
- An empty or chroot-less ZK string logs `ERROR <zk> is not a valid Zookeeper host. A valid zookeeper host has the following format : <host>:<port>,<host>:<port>/<chroot>. …`.
  - `getClient` returns null. Because `computeIfAbsent` does not cache null, every call retries.
  - Callers then get `LitSolrClientException: Error creating client for collection:<c> , zkHost:<zk> , searchType<t>` (`LitSolrClient.getSolrClient`). The same message appears when the collection name is not a `SolrCoreModel` (solrCore null).
- If ZK is reachable but the client cannot connect, the log shows `Failed to initialize CloudSolrClient.` with the stack trace, then the same `Error creating client…`.
- Collection missing in ZK or Solr: messages containing `Collection not found` / `Could not load collection from ZK` → `resetSolrJClients()` (log `Reset Solr clients for all collections zkHost:<zk>`) → `SolrOutdatedException`.
- Atomic update on a missing doc or version conflict (`version is not high enough` / `Document not found for update`) → `SolrInvalidVersionException`.
- A non-zero response status gives `LitSolrClientException: Failed to operate on core:<CORE>, error-code:<code>`.
- Circuit breaker: after repeated failures, `LitSolrClientException: Circuit-breaker is open` (`LitSolrClient.java` `CIRCUIT_BREAKER_IS_OPEN`). For the gRPC service, stdout shows `Circuit Breaker open`.
- `maxDoc` failure logs `Failed to get the # of docs from Solr. Defaulting to 10M`. The health ping fails silently (`Metrics: Cannot connect to Solr: …` at DEBUG).
- gRPC service mode:
  - `search/service/enabled=true` with an empty `nodes` list → `IllegalStateException: Search-service list is empty.` in the `SearchServiceProxy.LazyHolder` init. That gives `ExceptionInInitializerError`, then `NoClassDefFoundError … SearchServiceProxy$LazyHolder` on the first search.
  - A slow or unreachable service gives `io.grpc.StatusRuntimeException: DEADLINE_EXCEEDED` / `UNAVAILABLE`.
- Direct mode on a classpath without `id-search-core` → `DirectApiCallException: com.atypon.id.search.core.api.<X>` from `CoreApiManager` static init.
- Build: a `searchVersion` bump moves id-core. Renamed `IndexField` constants then give `cannot find symbol` in `:literatum:compileJava` (note 15 §3.3).

---

## 4. Failure-signature table

| Signature (log text) | Where | Meaning / root cause | Status |
|---|---|---|---|
| `java.lang.NoClassDefFoundError: akka/actor/typed/scaladsl/adapter/package$UntypedActorSystemOps$` (at `com.atypon.cluster.DefaultRobotsAdapter` / `RobotsSupervisorActor` / `DefaultMultiMapReplicator`) | runtime, first `RobotsAdapter.get` (`RobotManager_Akka:32`) or CRDT use | root-pom with `akka.version 2.6.21` (2610.0.4, 2610.0.6, **master 2611.0.5-SNAPSHOT**) enforced over passport-cluster **2110.0.1** (compiled for 2.5) | Confirmed (bytecode + Akka source); log text as reported in the incident |
| same with `…$UntypedActorRefOps$` / `…$UntypedActorContextOps$` | `DataReplicationSupervisorActor`, crdt `TypedActorFactoryImpl` | same | Confirmed (bytecode) |
| `NullPointerException` at `PassportClusterMetricsProvider.timer` ← `MetricReporting.timer` ← `DefaultMutexAdapter.<init>` (`MutexAdapter.scala:51`) | startup, `ClusterMutexManager` sanity mutex | unpatched build: `clusterMetrics = null` (LIT-591953 stub, master `PassportClusterMetricsProvider.java:18`); only with `clusterMutexClass=PassportClusterMutex` (midtier IBM, IBM-beta, IBM-stag) | Confirmed (code); LIT-683431 |
| `[ClusterMutexManager] Failure to load ClusterMutex class from registry cluster/mutex/clusterMutexClass` (FATAL) | `ClusterMutexManager.java:98-100` | wrapper of the NPE above | Confirmed (code) |
| `********** ERROR LOADING PRODUCT <p> **********` … `********** KILLING THE SYSTEM **********` | `Main.abortSystemStartup` | Spring init failed (e.g. `robotsExposer`) → `System.exit(1)` | Confirmed (code) |
| `LIT-656000: literatum-master patch failed, reverting...` in the build log | platform-tools `rebuild.py:704-706` (before #354) | predictor of the NPE row | Confirmed (note 02, memory) |
| Build resolves `atypon-root-pom:2611.0.5-SNAPSHOT` with Akka 2.6.21 | Literatum master build | master is exposed to the NoClassDefFoundError row | Inferred (SNAPSHOT publish state Unconfirmed) |
| `<zk> is not a valid Zookeeper host. A valid zookeeper host has the following format : …` | `CloudSolrJClientFactory.getClient` | empty or chroot-less `index/solr/zookeeper-connection` | Confirmed (code) |
| `LitSolrClientException: Error creating client for collection:<c> , zkHost:<zk> , searchType<t>` | `LitSolrClient.getSolrClient` | null client (bad ZK, connect failure) or unknown core name | Confirmed (code) |
| `Failed to initialize CloudSolrClient.` | `CloudSolrJClientFactory.getClient` | CloudLegacySolrClient build failure | Confirmed (code) |
| `Reset Solr clients for all collections zkHost:<zk>` + `SolrOutdatedException` | `LitSolrClient.handleException` | `Collection not found` / `Could not load collection from ZK` | Confirmed (code) |
| `SolrInvalidVersionException` (`version is not high enough` / `Document not found for update`) | indexing | optimistic-concurrency conflict | Confirmed (code) |
| `LitSolrClientException: Failed to operate on core:<CORE>, error-code:<code>` | `handleResponse` | Solr returned a non-zero status | Confirmed (code) |
| `LitSolrClientException: Circuit-breaker is open` / stdout `Circuit Breaker open` | LitSolrClient / gRPC interceptor | repeated Solr or search-service failures | Confirmed (code) |
| `IllegalStateException: Search-service list is empty.` → later `NoClassDefFoundError … SearchServiceProxy$LazyHolder` | id-search-client | `search/service/enabled=true` with empty `search/service/nodes` | Inferred |
| `StatusRuntimeException: DEADLINE_EXCEEDED` / `UNAVAILABLE` | gRPC search-service | service slow (> 20 s / 180 s) or down | Inferred |
| `NoClassDefFoundError: Could not initialize class …CloudSolrJClientFactory` / `…SolrConfHelper` | first index or search | required `index/solr/*` duration or `search/collections` config missing or bad | Inferred |
| `DirectApiCallException: com.atypon.id.search.core.api.<X>` | `CoreApiManager` static init | id-search-core missing or mismatched on the classpath | Inferred |

---

## 5. Open items
- Is a passport-cluster 2610.0.x release (with #174) planned? None exists today. The `2610.0.1` prepare commit has no tag.
- Is root-pom `2611.0.5-SNAPSHOT` published with Akka 2.6.21, and do Literatum master builds resolve it? Check a beta `was` build's dependency report or runtime log for `UntypedActorSystemOps`.
- Master Literatum still has the null metrics stub and has no build-time patch. Beta IBM-beta runs on master, so its next build is doubly exposed.
- The `RobotsExposer` → mutex bean chain is taken from the LIT-683431 description and was not traced bean by bean.
