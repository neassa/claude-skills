# 05 — Literatum build, config bootstrap, Gaia FE cache, and the `was` ADVISER failure

Repo: `$LIT_REPOS/literatum` (clone is grafted at master `9f11c5a17`, "Merge PR #14294"). Gradle root is `atypon/`.
All paths below are relative to `atypon/` unless they start with `docs/`, `gaia:` (GitHub `atypon/gaia`, master), `platform-tools/` or `ansible-cassandra/` (sibling repos in `$LIT_REPOS`).
Nothing was built or run. The only writes were this file and scratch files. No secret values were read: props files were read through `grep -viE 'pass|token|secret|api_?key|credential|auth'`. The filtered lines are listed as "secret-bearing/filtered line at file:line".

---

## Coverage

| Area | Read fully | Skimmed / grep only |
|---|---|---|
| Build scripts | `settings.gradle`, `build.gradle`, `gradle.properties`, `literatum/build.gradle` (all 1408 lines), `literatum/vaadin.gradle`, `patch-build/build.gradle`, `bridge/build.gradle`, `bridge/nlm-common/build.gradle`, `product/{product-common,product-bridge,product-nlm-common,product-simple,parent-product-common,parent-product-bridge-common}.gradle`, `product/{was,acropolis,aiaa,informs,mms}/build.gradle` | — |
| `buildSrc` (154 files) | `build.gradle`; Groovy/Java: `LiteratumPlugin`, `LiteratumPluginExtension`, `LiteratumEssentialsPlugin`, `AbstractProductPlugin`, `ProductPlugin` (1397 lines), `ProductPluginExtension`, `ParentProductPlugin`, `Util`, `AtyponGcpPlugin`, `CustomDependencyMetadataPlugin/Extension`, `DependenciesExclusionPlugin`, `DependencyExclusionsExtension`, `rules/*`, `repos/LocalMavenSettingsLoader`, `MavenSettingsPluginExtension`, `LiteratumDeployClassesPlugin`, `AspectJPlugin`, `BridgeAspectsPlugin`, `JFlexPlugin`, `AnnotationProcessingPlugin`, `VfsPlugin`, `WorkflowExtension`, and the tasks `CopyProps`, `ExecutePatch`, `BuildInfo`, `RevisionInfo`, `BranchInfo`, `BomQuery`, `DependencyBomRestrictionReport`, `DependencyVersion`, `SetVersionProperty`, `CopyTemplates`, `XSLCustomizeNew`, `ExtractXslConstants`, `DeployJawr`, `CTagCustomize`, `SchematronCompile`, `JFlexCompile`, `Wsdl2Java`, `WorkflowCompile`, `ClassDiscoveryDat`, `xsl/CxCompiler`, `CxVerifier`, `CxConstant`, `CxXslConstants` | `CompareWarsPlugin` (apply section only), `UnitTestRunnerPlugin`, `TestPlugin`, `TestPluginExtension`, `TestSummaryHelper`, `TestCategoriesSupport`, `MarkSlowFastTests`, `ReportDuplicateClasses*`, `CompareWarCompiledXsl`, `CompileJavaChanged`, `AntJavaCompile`, `RenameDatabase`, `DockerCommitImage`, `InspectContainer`, `DependencyGraphBomRestrictionReport`, `AsciiDependencyReportRenderer`, `VaadinUtil` (lines 1-120), `VersionNumber`, `CTags*`, `xsl/{CxOptimizer,CxGraph,CxFileHandler,CxCompilationUnit,XslDocument}`, `agent/TestIsolationAgent`. These are test/diagnostic/XSL internals and none of them is on the `war` dependency path except the XSL compiler. About 100 of the 154 files are vendored Talaiot 2.2.2 plugin artifacts (jar/pom/module/asc) under `src/main/resources/io/github/cdsap/`. They are binary and were not read. |
| Versions / BOM | `literatum/versions.properties` (master + lit-2610 via `gh api`), `atypon/root-pom` `pom.xml` @master (2611.0.5-SNAPSHOT) via `gh api` | — |
| Docs | `docs/architecture/01,02,03,18,20,21` fully | — |
| Config / bootstrap | `LiteratumConfigInitializer`, `LiteratumRegistryFactory`, `SpringAdapter`, `ComponentRegistry`, `Main.java` 60-300, `DbPatchSystem` 225-260 / 395-460 / 910-925; `literatum.props.xml` `macro` (76-130), frontend-cache cassandra (11180-11215), metrics gaia (16395-16440), `cf-recommendations` (19940-19990), `components` (25823-25930); `product/midtier/conf/midtier.props.gaia-fe{,.base,-non-pb}.xml` (filtered); `midtier.props.{IBM,IBM-stag,IBM-beta}.xml` build/mode | The rest of `literatum.props.xml` (28,646 lines) was not read. |
| Gaia FE (45 files) | `GaiaFeBeans`, `cache/RefOutputCacheFactory`, `TransformationContextFactory`, `LiteratumTransformationSource`, `LiteratumTransformationTemplateLocator`, `action/*` (4), `events/*` (2), `remote/RemoteCache`; `conf/spring/gaia-fe-base.xml`, `conf/spring/frontend/gaia-fe.xml`, `gaia-fe-pcms.xml` | `replacer/*` (19), `metrics/*` (3), `tracing/*` (7), `remote/{RemoteGaia,RemoteGaiaFe,RemoteTransformation}`: grep for cache/Config use only. None of them touches Cassandra. |
| Gaia library (external) | `gaia:registry/.../CassandraOutputCacheFactory.java`, `gaia:core/.../VersionedCassandraOutputCache.java` (master = 1.7.4); pinned 1.7.3 checked with `javap` on `~/.gradle/caches/.../gaia-{core,registry}-1.7.3.jar` | `CassandraOutputCache` (non-versioned), `TypedOutputCacheFactory` |
| Section D | `gh api`: literatum commits `0b07e5a7c6df`, `bbf1b365f573`, PRs #14215 and #14261, `versions.properties` history; cms-root PRs #499 and #501, tags, `CmsContributorRole.java` at 4 refs; id-core `Contributor.java` | Jira LIT-682047 and LIT-681676 were **not** read, because Jira reads fall outside the allowed read-only scope. Their relation below is inferred. |

---

## A. Build

### A1. Project composition (`settings.gradle`)
- Always includes `literatum`, `bridge:nlm-common` (which implicitly creates `:bridge`), `patch` (dir `patch-build`), `product:unittest` and `unittest-agent`, plus products (`settings.gradle:25-27`).
- Product whitelist precedence: env `PRODUCT_NAME`, then `-Dproduct=`, then `products.whitelist` (`settings.gradle:195-217`). The parent is found by a one-level regex on `parent = '...'` (`:147-169`). For `was` this pulls in `acropolis` (`product/was/build.gradle:6-8`).
- The root project name comes from the parent dir of `atypon/`, with `lit-` stripped (`:234-246`).

### A2. What `./gradlew :product:<p>:war -Dis.production.site=…` actually does
1. **`-Dis.production.site` is ignored by Gradle.** It appears nowhere in `buildSrc`, any `*.gradle` file or `literatum/`. It is emitted by `platform-tools/rebuild.py:597-600,740-743`, together with `-Ddeploy.hosts` and `-Dcheck.duplicate.props`, which Gradle also never reads. Gradle reads only singular `deploy.host`/`DEPLOY_HOST` (`buildSrc/.../Util.groovy:70-79`). The flags Gradle does honour are `include.props.file`, `keep.auto.generated.props.file`, `is.cip.site` and `force.create.props` (`ProductPlugin.groovy:490-495`); `DEPLOY_FAMILY`, `DP_SOURCE`, `DP_MATRIX`, `LEANWORKFLOWVERSION` and `DEPLOY_HOME` (`Util.groovy:81-127`, `ProductPluginExtension.groovy:61-80`); plus `omit-workflow` and `recompile`.
2. `war` is **not** Gradle's War plugin. It is a custom task: `project.ant.jar(jarfile: $buildRoot/product/<p>/resin/<p>.war, basedir: deployRootDir, compress:false)` (`ProductPlugin.groovy:1338-1358`). It depends on `deployWeb` and `buildInfo`.
3. `deployWeb` is a placeholder that depends on about 30 tasks (`ProductPlugin.groovy:94-165`):
   - `deployInit`, which depends on `jar`, which depends on `compileJava` of the product. Via `implementation project(':literatum')` and `:patch` (`product/product-common.gradle:18-22`), plus `:bridge`, `:bridge:nlm-common` and the parent (`product-bridge.gradle:11-14`, `product-nlm-common.gradle:8-19`, `AbstractProductPlugin.groovy:47-55`), this forces **`:literatum:compileJava`**. That task compiles `literatum/src/java`, `publish/src/java` and `tools/search-tools` together (`literatum/build.gradle:112-126`), after `litInit` (JFlex/javacc/WSDL codegen, `:1027-1037,1261-1289`) and AspectJ weaving (`AspectJPlugin.groovy:57-80`).
   - `unzipLibWars`/`copyLibWars` explode every `wars`-configuration war (pb2-ui, file-browser, yaeger, nlm-content-admin, …; `literatum/build.gradle:937-953,1011`) into `deployRootDir` (`ProductPlugin.groovy:337-386`).
   - `copyArtifactsAndDeps` copies the resolved `runtimeClasspath` into `WEB-INF/lib`, with regex exclusions (`:305-335`).
   - `copyProperties` (`CopyProps`) builds `WEB-INF/props.files.<deployHost>` and copies the props chain. When no `<p>.props.<host>.xml` exists, it **auto-generates** one, and adds `midtier.props.gaia-fe.xml` when `DP_MATRIX` contains `gaia` (`CopyProps.groovy:337-361,495-552`; `Util.groovy:100-118`). It then **verifies the registry parses** (`RegistryVerifier.verify`, `CopyProps.groovy:458-462`).
   - `copyFilesGen` copies spring XMLs, `host.props.*`, `midtier.props.host.*`, `web/services/registry.props.xml` and the rest (`:911-1201`).
   - `customizeXsl` does XSL compilation in forked workers (`:1248-1274`; `XSLCustomizeNew`). `workflowCompile` runs WfBuilder in a forked worker (`:1290-1314`). `deployJawr` runs only if `conf/jawr.properties` exists (`:1276-1288`).
   - `revisionInfo` runs `git log`; a failure writes `-1`, not an error (`RevisionInfo.groovy:22-33`). `buildInfo` writes `build.info.properties` (product, branch = parent dir name, host, family) (`BuildInfo.groovy:40-61`). The runtime later reads this for `macro/product-name` and `CVS_BRANCH` (`LiteratumRegistryFactory.java:163-176`).
4. `copyWar` (not part of `war`) copies to `$HOME/warfiles/<p>_<branch>_<ts>.war` (`ProductPlugin.groovy:1364-1383`).
5. Vaadin: `:literatum` applies `com.vaadin` 24.8.3 with `productionMode=true`. It uses a content-addressed cache when `LOCAL_BASE` is unset and plain execution on servers (`literatum/vaadin.gradle:26-34,368-397`).
6. Repositories come only from `~/.m2/settings.xml` active profiles + credentials + `mavenLocal()`, added in `afterEvaluate` (`AtyponGcpPlugin.groovy:36-53,89-127`). No repository is hardcoded for the main build.

### A3. Dependency version resolution
- `literatum/versions.properties` is loaded **only for `:literatum`** into `ext.versions` (`LiteratumPlugin.groovy:46-58`) and used as `versions['cmsapisVersion']` (`literatum/build.gradle:495`). `buildSrc` reads `registryVersion` from it separately (`buildSrc/build.gradle:84-111`).
- `enforcedPlatform("com.atypon:atypon-root-pom:${parentPomVersion}")` is applied to `api`, `testImplementation`, `wars` and `aspectsourcesCompile` (`literatum/build.gradle:241-245`), and to `aspectjtools`/`aspectjrt` (`AspectJPlugin.groovy:48-49`). `parentPomVersion = "2611.0.5-SNAPSHOT"` on master and `2610.0.7` on lit-2610 (`build.gradle:372-375`). Note that `docs/architecture/02:40` says `2611.0.4`, which is stale.
- **Precedence:** an enforced platform *forces* its managed versions over explicit ones, so the BOM wins where it declares a module. But `root-pom@master` (2611.0.5-SNAPSHOT) manages only **one** `com.atypon` artifact, `com.atypon:registry:1.3.5` (`root-pom/pom.xml:1877-1881`). It manages no `cms-apis`, `gaia-*` or `cassandra`. So for cms-apis, gaia and the rest, **versions.properties decides**. Confirmed for the root-pom *source* at master. The published SNAPSHOT could differ, but that is unlikely.
- Other overrides: `strictly` for `event-broker-si`, `jffi` and `xml-apis` (`literatum/build.gradle:528-532,956-965`); `force` for soap/saaj (`:89-94`); `force spring-context-support:5.3.39` on all configurations of every subproject (`CustomDependencyMetadataPlugin.groovy:58-60`); capability and `replacedBy` rules (`:24-119`); global exclusions (`build.gradle:385-510`, applied in `afterEvaluate` by `DependenciesExclusionPlugin`).
- Diagnostics: `:literatum:retrieveVersions --dependencies g:a` prints resolved `compileClasspath` versions (`DependencyVersion.groovy`, `literatum/build.gradle:1408`).

### A4. How a compile failure surfaces
- `:literatum:compileJava` is forked javac (`options.fork=true`, 6g, `-Xmaxerrs 5000`; `literatum/build.gradle:1261-1289`). A missing symbol prints `…/publish/src/java/…/X.java:NNN: error: cannot find symbol`, then `> Task :literatum:compileJava FAILED`, "Compilation failed; see the compiler error output for details", and BUILD FAILED. `deployInit` never runs, so no war is produced and nothing under `deployRootDir` changes.
- Because `publish/` is a source root of `:literatum`, a `publish/` compile error breaks **every product**, not just the one named on the command line.
- `rebuild.py` wraps this as `./run.sh build …`. How it reports the non-zero exit was not traced here.
- Non-failing traps: `RevisionInfo` swallows git errors (`-1`). `ExecutePatch` (used only by the `unittest` `TestPlugin`, `TestPlugin.groovy:189,217`) catches **all** exceptions and writes them to `$ATYPON_HOME/dout.log` without failing the task (`ExecutePatch.groovy:318-322`).

---

## B. Config / bootstrap

- **Registry layering** (`LiteratumRegistryFactory.java:127-161,178-252`):
  1. `SystemSource` comes first.
  2. The props list is either `-Dprops.file`'s includes or `WEB-INF/props.files.<DEPLOY_HOST>`. The latter is written by `CopyProps` at build time.
  3. Then `literatum.props.xml`, `host.props.<hostname>.xml`, `midtier.props.host.<serverType>.xml`, `midtier.props.host.<host>.<serverType>.xml`, `host.props.<serverType>.xml` and the host/FQDN variants, then `deployconf.props.xml`.
  4. Then the `COMMAND_LINE` and `CLEANUP_COMMAND` overlays, then `test.props.xml`.
  5. `web.props.xml`, `services.props.xml`, `ExternalSourceResolver` sources and `registry.props.xml` are ordered after `literatum.props.xml`.
  6. `-Dpatch.database.*` overrides the `macro/database/*` connection values as the last source. The mapping includes a credential property name; its value was not looked at (`:141-153`).

  A parse failure throws `LiteratumException("failed to build")` and notifies when `LOCAL_BASE` is set (`:155-160`). The registry is wrapped in a `HierarchicalRegistry` with `DbConf` and `WebsiteSourceResolver` (`LiteratumConfigInitializer.java:53-60`).
- **Role overlays that exist in the repo:** `literatum/conf/host.props.{web,backstage}.xml` and `midtier.props.host.{backoffice,backstage,fork,rbackstage,IBM-beta.backstage}.xml`. There is **no `host.props.patch.xml` / `midtier.props.host.patch.xml`**, so the patch VM gets the same component list as web, minus the `server-type` filter.
- **Spring from `components/`:**
  - `Main.initialize()` calls `newSpringAdapterFromConfig()` (`Main.java:224-234`), which calls `ComponentRegistry.Builder.build(getRegistry("components"))` (`ComponentRegistry.java:61-99`).
  - A `config-file` is included unless `enabled=false` or `server-type` does not match `System.getProperty("server.type")` (`:120-145`).
  - One `LiteratumApplicationContext` is built per context node, and all nodes are refreshed eagerly (`SpringAdapter.java:157-189`). Any bean exception becomes `Error("Cannot initialize Spring")` (`:138-141`).
  - Base list: `literatum.props.xml:25823-25928`. Examples: `workflow-monitoring` with `server-type` `backstage` (`:25914`), and `product` at order 1010.
- **Main**: static init reads `Conf` (`Main.java:85-97`). `SearchConfigurationLoader` is skipped when `server.type=patch` (`:242-249`).
- **Patch VM**: `DbPatchSystem.setupVM()` sets `server.type=patch`, `CacheUtils.ENABLED=false`, `remoteBroadcastEnabled=false`, `preload=false`, profile `patch`, then `main.run()`. That is **full config-driven Spring** (`DbPatchSystem.java:413-428`). `setDisableSpring` is a no-op (`:912-918`).
- Relevant `literatum.props.xml` sections:
  - `macro/product-name` DEFINE_ME and `macro/build/mode` = `dev` (`:85,102-106`).
  - The legacy frontend HTML cache keyspace `${macro/product-name}_${macro/build/mode}_frontend_html` with `implementation` default `none` (`:11180-11205`).
  - Gaia OTel metrics enabled (`:16405-16409`).
  - `server/mode = ${macro/build/mode}` (`:25934`).

---

## C. Gaia front-end and the Cassandra output cache

### C1. Where the code lives
- In-repo: `literatum/src/java/com/atypon/literatum/gaia/**` (45 files). `GaiaFeBeans` is a `@Configuration` with no `@Profile` and no `@Lazy` (`GaiaFeBeans.java:52-54`). It is wired by `conf/spring/gaia-fe-base.xml:6` (bean `gaiaConfig`).
- **`OutputCacheFactory`, `TypedOutputCacheFactory` and `CassandraOutputCacheFactory` (package `com.atypon.gaia.registry.cache`) are external.** They come from artifact `com.atypon.gaia:gaia-registry:1.7.3`. `VersionedCassandraOutputCache` is in `com.atypon.gaia:gaia-core:1.7.3` (`literatum/build.gradle:298-309`; `versions.properties:49-52`, the same on master and lit-2610). No `package com.atypon.gaia.registry` source exists in the repo. Source is GitHub `atypon/gaia`. Its master is at 1.7.4 and there is no 1.7.3 tag, so behaviour was verified against the cached 1.7.3 jars with `javap`: `TableIndexStatements` has the `table_index` literal, isTableExists, createTable.ifNotExists and prepare; the constructor does `new StatementManager()`; the factory does `createKeyspaceIfNotExists`.
- The Gaia cache uses the DataStax **OSS 4.x** driver (`com.datastax.oss…CqlSession`). The local Gradle cache holds `java-driver-core 4.13.0`; the exact resolved version is **Unconfirmed**. This is separate from the `cassandra-driver-core 3.11.5` that Literatum pins directly (`literatum/build.gradle:588`).

### C2. Wiring (props)
- `midtier.props.gaia-fe.base.xml` adds component `gaia-fe-base` at order 275, with no `server-type` (`:3-8`). It sets `gaia/id=${macro/CVS_BRANCH}`, `endpoint=http://127.0.0.1:8080`, `scope=${macro/product-name}`, `number-of-previous-caches-for-look-up=2`, and empty `caches`/`transformations` (`:26-49`).
- `midtier.props.gaia-fe.xml` includes the base, adds `gaia-fe` (280) and `gaia-fe-pcms` (281) (`:3-14`), and defines `gaia/caches/cassandra` (`:25-35`):
  - `nodes` = `ref cassandra/nodes`
  - **`keyspace = gaia_${macro/product-name}_${macro/build/mode}`** (`:30`)
  - `replication-factor 3`
  - `versioned = ${gaia/cache-versioning-enabled}` = true (`:17,33`)
  - `number-of-stale-cache-tables-for-look-up = 2`

  Every transformation uses `cache type=ref -> cassandra` (`:52-54` and the others). Secret-bearing/filtered lines: `midtier.props.gaia-fe.xml:10`, `:22`.
- `-non-pb` clears only the `gaia-fe`/`gaia-fe-pcms` files. `gaia-fe-base`, and so `GaiaFeBeans`, stays (`midtier.props.gaia-fe-non-pb.xml:4-11`).
- 64 product `*.props.xml` files include `midtier.props.gaia-fe.xml`, for example `acc`, `aan`, `aasm`. **`was` does not include it** (`product/was/conf/was.props.xml` has 0 `gaia` matches; `was.props.IBM*.xml` include lines 3). The one exception is `DP_MATRIX=gaia` with an auto-generated host props file (`CopyProps.groovy:504-508,534-538`).
- **Keyspace per environment**, from `macro/build/mode`:
  - dev machines → `dev` (`literatum.props.xml:104` and most `midtier.props.<host>.xml`)
  - `IBM-qa` → `qa`
  - **`IBM-stag` → `beta`** (`midtier.props.IBM-stag.xml:34-36`)
  - **`IBM-beta` → `beta`** (`midtier.props.IBM-beta.xml:17-19`)
  - `IBM-performance`/`IBM-migration` → `beta`
  - `IBM-lts` → `lts`
  - `cip` → `cip`
  - `IBM` → `live` (`midtier.props.IBM.xml:21-23`)

  So staging and beta of the same product use the same keyspace **name** `gaia_<product>_beta` (confirmed from props) — **but on each env's own Cassandra cluster** (deployconf `<cassandra cassandra_cluster_name>`; e.g. informs beta `beta-cassandra-literatum3` vs stag `cassandra-stag-lit3`, checked 2026-09-25), so data is only shared if the clusters coincide. `product-name` comes from `build.info.properties`, which the build writes.

### C3. Exactly when `table_index` is touched (gaia 1.7.3; line refs are gaia master, equivalent per javap)
1. **At Spring refresh, eagerly.** `GaiaFeBeans.getOutputCacheFactory()` (`GaiaFeBeans.java:116-134`) iterates **every** child of `gaia/caches` and calls `factory.produce()`. For `cassandra`, `CassandraOutputCacheFactory.produce` (`gaia:registry/.../CassandraOutputCacheFactory.java:27-66`) does the following:
   - builds a `CqlSession` against `nodes`, with local DC defaulting to `datacenter1`;
   - runs `CREATE KEYSPACE IF NOT EXISTS <ks>` with SimpleStrategy and the configured RF (`:73-78`);
   - constructs `VersionedCassandraOutputCache`. Its constructor builds `StatementManager` and then `TableIndexStatements` (`VersionedCassandraOutputCache.java:53-62,190-198,319-327`).

   `TableIndexStatements` checks the **driver schema metadata** `isTableExists("table_index")` (`:155-157`) and, if absent, runs `CREATE TABLE IF NOT EXISTS <ks>.table_index (id text PK, name text)`. It then **prepares three statements**: selectAll, `select name where id=?`, and `insert … IF NOT EXISTS`, all at QUORUM.

   Note that the `enabled` and `strategy` keys in props are **not read** by the factory, so `enabled=false` does not disable the cache (**Confirmed** from factory source and javap string constants).
2. **On first use of each template version in each JVM.** `getTableName()` runs `SELECT name FROM table_index WHERE id='<template>_<scope…>_<timestamp>'` (`:262-296`). The id format comes from `LiteratumTransformationTemplateLocator.java:244-262`.
   - On a hit, it prepares select/insert/delete against the named table.
   - On a miss, it creates `<template>_<scope>_<random10>`, inserts the index row with LWT, and on a lost race drops its own table.

   The result is cached in `entryStatementCache` **for the JVM's lifetime, never invalidated** (`:186,231-233`).
3. **On a primary-table miss, for stale lookup.** `selectAll` over `table_index` runs once per template per hour, through a Guava cache with expireAfterWrite 1h (`:193-197,206-218,242-260`). Errors there are caught and logged (`:103-105`).

### C4. What happens if the table is missing
- **`table_index` missing at startup:** it is recreated (IF NOT EXISTS). The creation is decided by a possibly stale metadata check, but IF NOT EXISTS makes the create itself safe.
- **`table_index` dropped after startup:** the prepared statements fail at request time (`InvalidQueryException`, unconfigured table).
- **Cassandra unreachable, or DDL/prepare failing:** the exception propagates out of the `@Bean`. `refresh()` fails, then `Error("Cannot initialize Spring")` (`SpringAdapter.java:138-141`), and web, backstage **and the patch VM** fail to start.
- **Index row present but its cache table dropped (stale `table_index`):** `new CacheEntryStatements(table)` → `session.prepare(...)` throws, surfacing on the first request for that template version. Nothing in this path handles it (`:236-239,305-309`). Fresh JVMs hit it on first request. Old JVMs that had already prepared against the dropped table keep failing until restart.

### C5. Is the bean created in the patch VM (`server.type=patch`)?
**Yes, for any product whose props chain includes `midtier.props.gaia-fe.xml`.** Confirmed from code:
- the patch VM runs full config-driven Spring (`DbPatchSystem.java:413-428`, `Main.java:224-231`);
- `gaia-fe-base` has no `server-type` (`midtier.props.gaia-fe.base.xml:4-7`);
- `GaiaFeBeans` has no `@Profile("!patch")`;
- there is no lazy init;
- there is no patch role overlay in the repo.

So `patch.py`/`DbPatchSystem` opens a CqlSession, runs `CREATE KEYSPACE IF NOT EXISTS`, and creates/prepares against `table_index` before any JDBC patch runs. A Cassandra problem therefore surfaces as a patch/deploy failure. This matches the `literatum-patch-cassandra-failures` pattern. **Unconfirmed:** whether a deploy-time `deployconf.props.xml`/`host.props.<host>.patch.xml` outside git disables it.

### C6. Relation to LIT-682047 / LIT-681676 (inferred; Jira not read)
The cleanup job `ansible-cassandra/roles/cleanup/tasks/cleaner.yml` works per keyspace:
- `SELECT * FROM table_index` (`:1-6`);
- keeps the newest 2 ids per template, using a lexicographic `sort -r | tail -n+3` (`:36-43`);
- **first** `DROP TABLE IF EXISTS` for the old tables (`:67-76`);
- **then** `DELETE FROM table_index WHERE id IN (…)` (`:78-85`);
- then `rm -rf` the data dirs and `nodetool cleanup`.

That gives the following race windows:
- **(a)** Between DROP and DELETE, or permanently if the DELETE step fails, `table_index` points at dropped tables. That matches "stale table_index after Cassandra cleanup race" (LIT-682047). Any JVM that starts or first-renders that template then fails at `prepare` (C4).
- **(b)** Long-running JVMs cache prepared statements per template version with no invalidation (C3.2). If a JVM still serves a template version older than the newest 2, its table is dropped under it. (Correction 2026-09-25: stag and beta normally use different Cassandra clusters, so the same-named keyspace does not add cross-env churn unless the clusters coincide.)
- **(c)** Cleanup deletes index rows by id prefix match (`grep {{item}}`). The patch VM or web startup running `CREATE TABLE IF NOT EXISTS table_index` concurrently with a cleanup is benign.

LIT-681676 could not be tied to specific code without reading the ticket, so it is **Unconfirmed**.

---

## D. `was` build failure: `ContributorsIndexingUtil.java:210 cannot find symbol ADVISER`

| Fact | Evidence | Status |
|---|---|---|
| Failing line `case ADVISER -> Contributor.ContribType.adviser.name();` is in `publish/src/java/com/atypon/publish/search/solr/content/utils/ContributorsIndexingUtil.java:210`, which is compiled by **`:literatum:compileJava`**. It therefore breaks every product, not just `was`. | local file; `literatum/build.gradle:115-119` | Confirmed |
| master `cmsapisVersion=4.0.0.28`; lit-2610 `cmsapisVersion=3.0.18.2` | `gh api …/versions.properties?ref=` (line 29 on both) | Confirmed |
| `ADVISER` first landed on lit-2610 as `bbf1b365f573` (PR #14261 "Lit 682919", base lit-2610, merged 2026-09-23T13:22Z). It was forward cherry-picked to master as `0b07e5a7c6df` by github-actions at 14:08Z (+1 line). It is an ancestor of current master. | `gh api commits/0b07e5a7c6df`, `compare/0b07e5a7c6df...master` = ahead 28 / behind 0 | Confirmed |
| PR atypon/literatum#14215 (LIT-683120, base lit-2610, merged 09:39Z) added `ADVISOR`/`ADVISER` to `PublicationContributorMap` and `literatum.props.xml`, and links cms-root#499 and cms-passport-root#9070. It did **not** touch `versions.properties`. | `gh api pulls/14215/files` | Confirmed |
| cms-root#499 (base **lit-2610**, merged 09:39:56Z, merge `b3d8e23a`) adds `ADVISOR`/`ADVISER` to `CmsContributorRole`. Tag **`cms-apis-3.0.18.2` = `b3d8e23a`**, and `3.0.18.1` lacks it. | `gh api pulls/499/files`; tags; file @ tags | Confirmed: **3.0.18.2 introduced ADVISER on the 3.0.18 line** |
| On cms-root **master**, ADVISER came via #501 (`3118cf4d`, merged `401f9d50` at 10:12Z). Tag `cms-apis-4.0.0.28` = `735e98c8` (05:52Z) **predates** it and lacks ADVISER. **No `cms-apis-4.0.0.29`+ tag exists** (all 1649 tags scanned). | file @ `cms-apis-4.0.0.28` vs `master`; tag list | Confirmed |
| master's pin moved 4.0.0.27 → 4.0.0.28 in `f81980625fb2` ("Cms-apis released module", 06:26Z), *before* #501. It has not moved since (`2233047f` at 10:13Z left it at .28). | `gh api commits?path=versions.properties` | Confirmed |
| The root BOM does not override cms-apis, so versions.properties is authoritative. | `root-pom/pom.xml` manages only `com.atypon:registry` | Confirmed (root-pom source @master) |
| `Contributor.ContribType.adviser` exists in id-core `core-2710.0.5`, so that half of line 210 resolves. | `gh api id-core …Contributor.java?ref=core-2710.0.5` | Confirmed at that tag. The exact id-core version resolved transitively via `searchVersion=2710.0.5` is Unconfirmed. |

**Conclusion (Confirmed):**
- **lit-2610 compiles**: 3.0.18.2 contains ADVISER.
- **master does not**: 4.0.0.28 lacks ADVISER, and the forward cherry-pick of #14261 brought the code but no cms-apis bump.
- Fix: release cms-apis 4.0.0.29 or later from cms-root master (≥ `401f9d50`) and bump `cmsapisVersion` on literatum master. The alternative is reverting `0b07e5a7` on master.
- Caveat: if the failing `was` build was of a **lit-2610** checkout, the cause is something else. Candidates are a stale cms-apis 3.0.18.x in `mavenLocal()` (added last in `AtyponGcpPlugin.groovy:51`) or a build-time patched tree (see memory: "lit-2610 builds ≠ git source"). That case is **Unconfirmed**.

---

## FAILURE SIGNATURE table

| Signature (what you see) | Where it comes from | Root cause / meaning |
|---|---|---|
| `ContributorsIndexingUtil.java:210: error: cannot find symbol … symbol: variable ADVISER location: class CmsContributorRole` then `> Task :literatum:compileJava FAILED` | `publish/…/ContributorsIndexingUtil.java:210`; `literatum/build.gradle:495` | master pins `cms-apis 4.0.0.28` (no ADVISER); fix needs cms-apis ≥ a tag containing cms-root `401f9d50` |
| `Compilation failed; see the compiler error output` on **any** product | `:literatum:compileJava` (shared by all products) | `publish/` is a source root of `:literatum` |
| War is not rebuilt although the rebuild.py flags changed | `-Dis.production.site`, `-Ddeploy.hosts` and `-Dcheck.duplicate.props` are not read by Gradle | Flags are ignored (`rebuild.py:597-600`) |
| `GradleException … props.test-default.xml does not exist` / `No Deploy Hosts Provided` / RegistryVerifier error during `copyProperties` | `ProductPlugin.groovy:449-454`; `CopyProps.groovy:323-326,458-462` | Props chain missing or unparsable at build time |
| `Error loading property file from system property … Killing server` / `failed to build` | `LiteratumRegistryFactory.java:197,159` | Bad `-Dprops.file` or registry parse failure at runtime |
| `Cannot initialize Spring` wrapping `GaiaException: Missing nodes` / `keyspace not defined for Cassandra cache …` / `Cache <x> not found` / `ref not defined for ref cache` | `CassandraOutputCacheFactory.java:30,51`; `RefOutputCacheFactory.java:236,242`; `SpringAdapter.java:138-141` | Gaia cache props incomplete; happens in web, backstage **and patch VM** |
| Driver `AllNodesFailedException` / `NoNodeAvailableException` inside `getOutputCacheFactory` at startup or patch | `GaiaFeBeans.java:116-134` → `CqlSession.builder().build()` | Cassandra unreachable; the Gaia bean is eager and not patch-profiled |
| `InvalidQueryException: unconfigured table <tmpl>_<scope>_<rand10>` on first Gaia render of a template version | `VersionedCassandraOutputCache.java:236-239,305-309` | Stale `table_index` row → dropped table (cleanup `cleaner.yml:67-85` DROP-before-DELETE); LIT-682047 (inferred) |
| Same error persisting on a long-lived JVM until restart | `entryStatementCache` never invalidated (`:186,231-233`) | Cleanup dropped a table still in use by that JVM's template version |
| `[!] Error in Retrieving Stale Cache Version for …` (logged, request continues) | `VersionedCassandraOutputCache.java:103-105` | `table_index` / stale table query failed during the stale lookup |
| Patch/test DB task "succeeds" but nothing was patched; stacktrace appears in `$ATYPON_HOME/dout.log` | `ExecutePatch.groovy:318-322` | Exceptions swallowed (only unittest `TestPlugin` uses it) |
| `svn.revision=-1` in `build.info.properties` | `RevisionInfo.groovy:22-33` | `git log` failed during build (non-fatal) |
