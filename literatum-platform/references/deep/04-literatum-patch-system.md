# 04 — Literatum DB patch system, end to end

Written 2026-09-25 from read-only code reading. I ran nothing: no gradle, no scripts, no DB, no network.
I read no secrets. Props files were read with password/token/secret lines filtered out, and I read nothing under `literatum-patch/data/`.

## Path abbreviations

| Abbrev | Path |
|---|---|
| `P/` | `$LIT_REPOS/literatum/atypon/literatum/src/java/com/atypon/literatum/util/db/patch/` |
| `L/` | `$LIT_REPOS/literatum/atypon/literatum/src/java/com/atypon/literatum/` |
| `PUB/` | `$LIT_REPOS/literatum/atypon/publish/src/java/com/atypon/` |
| `MP/` | `$LIT_REPOS/literatum/atypon/literatum/src/java/com/atypon/modules/patch/` |
| `CONF/` | `$LIT_REPOS/literatum/atypon/literatum/conf/` |
| `MID/` | `$LIT_REPOS/literatum/atypon/product/midtier/conf/` |
| `PT/` | `$LIT_REPOS/platform-tools/` |
| `OT/` | `$LIT_REPOS/platform-tools/operations/tools/` |
| `LP/` | `$LIT_REPOS/literatum-patch/` |
| `DS/` | `$LIT_REPOS/deployserver/` |

---

## 1. Coverage (what I actually read)

**Read in full, line by line:**
- All 38 files in `P/`: AbstractPatchSequenceHandler, BufferedPrintWriter, CleanWorkflowPatch, CrawlerDbPatchUtil, DatabaseType, DbAbstractSqlPatch, DbJavaPatchWrapper, DbPatchCreatorHelper, DbPatchCreator, DbPatcher, DbPatch, DbPatchSystem, DbPatchUtil, DbReleasePatch, DbSqlLoader, DbSqlPatch, DbVersionCheck, FilePatchMetadata, JDBCPatchExecutor, PatchCapturedSequence, PatchCaptureSequenceHandler, PatchCompletionCheckerConstant, PatchExecutor, Patch, PatchLexer.jflex, PatchLoader, PatchMetadata, PatchParseException, PatchParser, PatchReplaySequenceHandler, PatchsAppliedCheckerTool, PatchSystemState, PatchType, PatchVersionChecker, PoolPatchList, RawPatchMetadata, TestRollbackException, VersionCheckException.
- `L/util/db/version/`: DbInfo, DbInfoColumns, DbVersion (header plus table definition), DbVersionColumns, DbVersionChecker, VersionCheckException, VersionCheckFailed.
- The launcher chain:
  - `PT/patch.py`
  - `PT/commandutil.py` (only `runGetTeeOutput`) and `PT/temputil.py`
  - `OT/gradle_tool/run_gradle.sh`, `OT/build.gradle`, `OT/settings.gradle`, `OT/gradle_tool/{settings.gradle,gradle.properties}`
  - `OT/src/main/java/com/atypon/modules/build/gradle/{DbGradlePatcher,PatchCompletionChecker}.java`
  - `OT/patch.xml` (the legacy Ant path)
- The build side:
  - `atypon/patch-build/build.gradle`
  - `atypon/settings.gradle` (the `:patch` project)
  - `atypon/product/product-common.gradle` (it depends on `:patch`)
  - `buildSrc/.../ProductPlugin.groovy` (`copyPatchesToDeployRoot`, `copyArtifactsAndDeps`)
  - `buildSrc/.../tasks/ExecutePatch.groovy` (the unit-test DB path)
- `MP/`, read in full: Patcher, PatchSteps, PatchTable, PatchSchemaDump, DataDump, `functions/PatchFunctionExecutor`, `IPatchFunction`, `PatchNotFoundException`, `PatchExecutionException`, `ExecuteInLineJavaPatch`, `MarkReadOnlyPatch`, `MarkPersonIdentityWithEmailAsReadOnlyPatch`.
  - Only the file list and the head of `AdPatchHelper` for the other ~50 `functions/*`. They are leaf `IPatchFunction`s.
- Patch VM bootstrap:
  - `L/Main.java` (all of it), `L/spring/SpringAdapter.java` (all of it)
  - `L/ComponentRegistry.java`, `L/Component.java`, `L/server/ServerType.java`
  - `L/util/LegacySingletons.java` (the Spring and singleton accessors)
  - `L/spring/CoreSpringConfig.java` (all of it)
  - The `@Profile("patch" / "!patch")` sites in `CustomizationSpringConfig`, `WebSpringConfig`, `RobotsRegistrar`, `CmsSpringConfig`
  - `CONF/literatum.props.xml`: the `components` set (lines 25823-25927), `server/*` (25930-26110), `patch` (20509-20516), read-only flags (2294-2295)
- Gaia:
  - `L/gaia/GaiaFeBeans.java` (all of it), `L/gaia/cache/RefOutputCacheFactory.java`
  - `CONF/spring/gaia-fe-base.xml`, `CONF/spring/frontend/gaia-fe.xml`, `gaia-fe-pcms.xml`
  - `MID/midtier.props.gaia-fe.xml` (lines 1-122, filtered), `MID/midtier.props.gaia-fe.base.xml`
  - `javap -c` of `CassandraOutputCacheFactory`, `VersionedCassandraOutputCache` and its `$StatementManager` and `$TableIndexStatements` classes, from `~/.gradle/.../com.atypon.gaia/*/1.7.3/*.jar`. Version 1.7.3 is pinned in `atypon/literatum/versions.properties:49-52`.
- Persistence and read-only:
  - `L/persistence/AbstractDbBasic.java` (all 1016 lines), `AbstractDbEnhanced.java`, `AbstractEntity.java`, `ReadOnlyException.java`, `ReadOnlySiteUtil.java`
  - `L/acs/EntityAccessRights.java` (lines 60-85)
  - `L/persistence/LiteratumDS.java:90-140`, `L/persistence/Transaction.java` (signatures)
  - `PUB/publish/acs/license/LicenseImpl.java:595-640, 1370-1520`
  - `PUB/publish/acs/license/LicenseServiceImpl.java:125-207`
  - `PUB/iam/identity/internal/IdentityImpl.java:240-310, 600-650, 870-910`
  - `IpRangeUserServiceImpl.java:85-135`, `IdentityMembershipServiceImpl.java:60-130`, `IdentityRelationServiceImpl.java` (relation methods)
  - `L/acs/user/IPRangeUser.java` (all of it)
  - `PUB/modules/migration/{Patch032053,Patch032035,AddAtyponIPsToAtyponInstitution(1-190),Patch003665,Patch031129,Patch031923}.java`
  - `PUB/publish/acs/metadata/Issue.java:1975-2010`
  - A codebase-wide grep for `setReadOnly(true)`, which gave 226 hits.
- `LP/`:
  - README.md, build.gradle, update-release-level.sh, .gitignore, .classpath, `.github/workflows/reservedPatchAutoMerge.yml`
  - `mssql/{literatum,report}/getNextAvailablePatchName.sh`, `mssql/literatum/{lit_patch_template.sql,lit_new_employee_template.sql,patch_system_v3.sql}`
  - The directory structure
  - 35 consecutive SQL patches, lit32020 to lit32054 (headers and bodies), plus lit5639, lit8632, lit9639, lit31762, lit31763
  - 13 Java stubs, including Patch032021/25/27/28/32/34/35/46/48/53 and Patch0316958, plus the two "Atypon institution" non-stub classes
  - A scripted scan of all 2373 stub `.java` files and all SQL headers, with the stats in section 7
- Deploy-server consumer of the output:
  - `DS/src/.../SshExecuteVisitor.java:425-470`
  - `DS/src/.../SshExecutedVisitor.java:400-505`
  - `DS/src/.../DeployDaemonHelper.java:55-105, 530-560`
  - `DS/config/actions.xml:899-905`
- Docs: `literatum/docs/architecture/04-core-infrastructure.md`, `05-persistence.md`, `19-testing-and-quality.md`, all read in full. Corrections are in section 11.

**Not read and not verifiable here:**
- The DataStax driver internals.
- The Passport `LiteratumFactory.fixCoreContent` override. The base class only throws, at `L/../modules/LiteratumFactory.java:172-174`.
- Any real aiaa log or stack. None exists locally; I checked local downloads for `ReadOnlyException` and found nothing.
- `LP/data/AtyponIPs/atyponIPs.txt`. It is off-limits under the data rule, and it matters for section 9.

---

## 2. Lifecycle, top to bottom

### 2.1 Deploy server → `patch.py`
- **ProductPatch** (`DS/.../SshExecuteVisitor.java:430-470`) builds:

  ```
  patch.py -p <product> [--families <f>] [--allowdropcolumn] [--gradle] --triggeredby <u> --jira-ticket-id <bug>
  ```

  The command is built at :447-460. When the product DB runs in Docker it uses `ansible-actions … start-patch-backup` instead (:461-468).
- **ProductDBUpgrade** (`DS/config/actions.xml:899-905`) runs:

  ```
  patch.py -p … --families … -u <mainBranch> --gradle
  ```

  It validates on the text `Patch complete.`.

### 2.2 `patch.py` → `run_gradle.sh`
- Gradle is the default when neither `--gradle` nor `--ant` is given (`PT/patch.py:493-494`).
- The command is `run_gradle.sh patch runWithJavaExec <targets>` (:172-174). The targets are `-D…` flags from `getXtraTargets` (:220-304).
- Flag mapping:

  | patch.py flag | JVM property | Line |
  |---|---|---|
  | `-f` | `-Dpatch=` | :229 |
  | `-e` | `-Dignoreerror=false` | :250 |
  | `-c` | `-Dcontinueonerror=true` | :256 |
  | `-F` | `-Dforcerunreserved=true` | :272 |
  | `-R` | `-Ddisabledbrelease=True` | :282 |
  | `-u` | `-Dupdaterelease=` | :248 |
  | `--patchplan` | `-Denablepatchplan=true -Dpatchplan=` | :262-264 |

- `-Dlegacymode=True` is added when `-L` is given **or the host is not a production site** (:277-278). "Not a production site" means `LOCAL_BASE` is not set (`PT/deploy.py:186-196`).
- The output is captured by `commandutil.runGetTeeOutput` (`PT/commandutil.py:134-154`): `cmd 2>&1 | tee -a /var/tmp/<epoch>.txt`, which is read back and then deleted.
- `run_gradle.sh patch`:
  - It `cd`s to `$HOME/scripts/operations/tools/` (`OT/gradle_tool/run_gradle.sh:225-226`).
  - It runs `gradlew runWithJavaExec … -Datypon.home=… -Dproduct.name=… --stacktrace` through `eval` (:244).
  - **The script never exits with Gradle's status.** `finalcmd= eval …` then `command_exec $finalcmd` runs an empty command, and the file ends with no `exit $_GRADLE_EXIT` (:244-247, EOF at 267).
  - So success or failure is decided only by text matching in `patch.py` (section 4).

### 2.3 Gradle task `runWithJavaExec` → `DbGradlePatcher`
- The task is defined at `OT/build.gradle:66-150`. It depends on `initialize` (:19-39) and `taskCompile` (:52-64).
- The classpath is `$DEPLOY_HOME/webapps/$PRODUCT/WEB-INF/lib/*` plus `WEB-INF/classes` plus `operations/tools/zips` (:27, :84). **So the patch VM runs the deployed webapp's jars**, including `patch.jar` (the `com.atypon.patch.*` stubs) and `literatum.jar` (`com.atypon.modules.migration.*`).
- The main class is `com.atypon.modules.build.gradle.DbGradlePatcher` (:85).
- The system properties are copied through at :87-144. Hard-wired extras:
  - `akkauseephemeralport=true`
  - `disableeventtransport=true`
  - `clusteractiveprofiles=dummy-event-transport,dummy-crdt,dummy-broadcast` (:113-115)
- The patch VM's **stdout** goes to both the console and `$DEPLOY_HOME/log/$PRODUCT/gradle.patch.<yyyy-MM-dd-HHmmss>.log` (:31, :79). **stderr is not teed into that log.** It only reaches the patch.py temp file.
- Not forwarded:
  - `-Dexcludedpatches` and `-Denablepatchplan` are **not** forwarded. They are no-ops on the Gradle path.
  - `DbGradlePatcher` never calls `setIgnoreJava`, so the `--skipJavaPatches` family is dead.
- `DbGradlePatcher.main` (`OT/src/main/java/com/atypon/modules/build/gradle/DbGradlePatcher.java:12-18`):
  - `init()` creates `new DbPatchSystem(new PrintWriter(System.out))` (:29-31).
  - `verify()` maps the system properties onto setters (:33-74).
    - `parseAntArgument` turns unset or `${…}` values into null (:82-108).
    - It sets `acs.home`, `akka.use.ephemeral.port`, `disable-event-transport` and `extra-active-profiles` (:67-71).
  - `ss()` runs `patcher.run()`. On any **Exception** it calls `printStackTrace` and **`System.exit(1)`** (:20-27). A `java.lang.Error` is not caught here and escapes `main`, which is still a nonzero exit.
  - On success it calls `System.exit(0)` (:17).
- `PatchCompletionChecker.java`, which checks for begin/end markers, sits in the same source directory but **no Gradle task calls it**. Only the Ant path invokes it (`OT/patch.xml:56, :96`).

### 2.4 `DbPatchSystem.run()` (`P/DbPatchSystem.java:110-205`)

1. **Constructor** (:96-103). It routes output through `BufferedPrintWriter` into `PatchSystemState` and defaults `continueOnError=true`. `DbGradlePatcher` then overrides that with `Boolean.parseBoolean(prop)`, which is **false unless `-c`** (DbGradlePatcher:55).
2. **`setup()`** (:227-276):
   - `sanityChecks` (:378-407)
   - **`setupVM()`** when Spring and `Main` are not yet initialized (:236-238). This boots the whole Literatum runtime (section 5).
   - `setupSinglePatch` for `-f` (:433-446)
   - `setupAtyponHome` (:451-466)
   - **`loadDatabases()`** (:473-490). Internal mode creates one `PoolPatchList` per `DatabaseType` whose pool exists (`P/PoolPatchList.java:38-48`, standard pool).
   - **`loadPatchPlan()`** (:278-332). `enablePatchPlan` is always true (:78) because there is no setter for it.
3. **DB release gate** (:125-132). `db_info.release` must equal `macro/build/branch` unless `-R` or `-u` is given (section 4 has the exact message).
4. **`PatchFunctionExecutor`** is built from the Spring bean factory (:134-135). It discovers every `IPatchFunction` (`MP/functions/PatchFunctionExecutor.java:23-44`).
5. **Mode selection:**
   - No `-f`: optionally `cleanWorkflow` (:137-139) and `-u` → `updateRelease()`. With `-u` the queue is only a `DbReleasePatch`, with `excludeAdditionalPatches=true` (:627-635).
   - `-f a,b`: explicit files, each parsed with `FilePatchMetadata` and `createPatch`. Reserved and Activiti patches raise an `Error` (:157-165). Then `excludeAdditionalPatches=true` (:170).
6. **`initializePatchers()`** (:710-754):
   - It uses `DbVersionCheck` (auto-discovery) when version checking is on and extra patches are not excluded. Otherwise it uses a plain `DbPatcher` (:714-720).
   - `continueOnError`, `reThrowToSystem = !ignoreError`, the patch plan, the parser and `ignoreJava` are set (:722-727).
   - A connection is dry-run opened and closed, and a pool that fails is removed after `handleException` (:733-753).
7. **`fillPatchQueues()`** (:756-772) → `DbPatcher.fillPatchQueue` (`P/DbPatcher.java:158-165`) → `DbVersionCheck.checkVersion` plus the drop, sequence and unicode guards (section 3).
8. **`runBeforeContentFixRunnerPatchers()`** (:696-708) → patches marked `before_content_fix_runner='T'` (`P/DbPatcher.java:195-233`).
9. **`fixCoreContent()`** (:957-975). It runs only if `passport/enabled` is set and `--skipcontentfix` was not given. On failure it throws `****** Core Content Bootstrapping FAILED ******`.
10. **`runPatchers()`** (:682-694) → `DbPatcher.patch()` per pool (`P/DbPatcher.java:178-193`):
    - It prints `patch pool marker for '<pool>' begins.` (`P/PatchCompletionCheckerConstant.java:4-14`).
    - `patchImpl` drains the queue (:235-242).
    - It prints `…' ends. All patches applied successfully.` only if nothing threw.
11. Any exception is printed and rethrown (:197-199). `functionExecutor.close()` runs in `finally` (:200-204).

### 2.5 Per patch: `DbPatcher.executeQueuedPatch` → `JDBCPatchExecutor`
- `DbPatcher.java:248-269` creates a new `JDBCPatchExecutor` for each patch and opens an `AuditSessionManager` session as the PATCHING_SYSTEM user named `Patch: <name>` (:252-257).
- `JDBCPatchExecutor.executePatch` (`P/JDBCPatchExecutor.java:24-55`):
  - `resetBuffer()` means the buffer that becomes `db_version.message` holds **only this patch's output** (:27; `P/BufferedPrintWriter.java:121-147`).
  - It prints `Executing patch <name>` (:28).
  - It re-checks at **execution** time with `isExecutablePatch(meta, false)`, which throws on failure (:32). This is where `dependson` is enforced. See 3.4.
  - If `isTransactionEnabled()`, it calls `Transaction.execute(handler)`. Otherwise it calls `handler.handle()` (:36-43).
  - The handler (:57-82) calls `patch.patch()` and then `updateLogsAndDbVer`. That writes the db_version row **inside the same transaction** and prints `Patch complete. tt=<n>s` (:84-88). In `-t` test mode it then throws `TestRollbackException`, which forces a rollback (:71-74).
  - On any Throwable, `handlePatchError` runs (:97-126):
    - It prints the stack.
    - When version checking applies, `updateVersion(status=1, message=<buffer>+"\n"+throwable.getMessage())` runs after the transaction has already rolled back, so the failure row persists. `'` is replaced by `"` (:244-251).
    - If that write fails, it logs `Could not save message:` (:113).
    - It then throws `RuntimeException("PatchProgram (<product>):Patch <name> failed to execute", cause)` (:119).
- `updateVersion` (:136-222) UPDATEs an existing `status!=0` row, which is how a retry reuses the row (:155). Otherwise it INSERTs. The columns are listed in `L/util/db/version/DbVersionColumns.java:5-17`. On a SQL error it throws `VersionCheckException("Updating the Db Version table failed!")` (:216).

### 2.6 What each patch type actually executes
- **`PatchLoader.createPatch`** (`P/PatchLoader.java:11-45`):

  | Type | Resulting patch | Note |
  |---|---|---|
  | UNKNOWN | `DbSqlPatch` | Allowed because `patch/allowLegacyPatches=true`, `CONF/literatum.props.xml:20511`. |
  | DDL / DML | `DbSqlPatch` | |
  | DDLDML | `DbSqlPatch` | Allowed because `allow-DDL-DML-mixed-patches=true`, :20513. |
  | DMLLOADER | `DbSqlLoader` | |
  | JAVA | `DbJavaPatchWrapper` | Only if not truly reserved. **Only the class name is stored. No class is loaded yet.** |

- The type comes from `type_parm`. Blank plus a `java_patch_parm` means JAVA (`P/FilePatchMetadata.java:104-122`). The flags per type are in `P/PatchType.java:10-16`:
  - JAVA: versionCheck=T, tx=T.
  - DMLLOADER: versionCheck=F, tx=F.
  - RAW (release and clean-workflow patches): versionCheck=F, tx=T.
- **SQL** (`P/DbSqlPatch.java:89-172`):
  - Lines starting `--$` are inline functions. Other `--` lines are comments.
  - A line reading `go` ends a batch. On non-Oracle DBs a trailing `;` ends a statement.
  - `ON DELETE CASCADE` is rejected (:174-190).
  - Each statement goes through `runSingleSql` (`P/DbAbstractSqlPatch.java:27-87`). That first asks `PatchFunctionExecutor.execute(line)`, which fails with `Patch function not found: X` (`MP/functions/PatchFunctionExecutor.java:73-75`) and is wrapped as `SQLException("Error trying to execute patch function")` (DbAbstractSqlPatch:42-44). Otherwise it runs `stmt.execute` and prints result sets and `N rows are affected`.
- **JAVA** (`P/DbJavaPatchWrapper.java:25-30`) → `PatchLoader.initializeJavaPatch` (`P/PatchLoader.java:56-74`):
  - `Class.forName(stub)` (:59). A CCE gives `Java patch X does not implement Patch` (:60-61). Any other exception gives `RuntimeException("PatchProgram (<p>):Error trying to initialize patch: " + e)` (:62-63).
  - The stub is instantiated as a Spring bean with `newBean` and metadata injected (:65-70), and then `.patch()` is called.
- **Stub delegation** (`LP/java/src/com/atypon/patch/Patch032053.java:7-12`):
  - The stub's `patch(Connection)` calls `loadDynamicPatch("com.atypon.modules.migration.Patch032053", conn)`.
  - `DbPatch.loadDynamicPatch` (`P/DbPatch.java:61-74`) does `Class.forName(target)` **uncaught** (:63), then `newBean` (:64). It tries a public no-arg `patch()` first (:67-68) and falls back to `patch(Connection)` (:70-71).
  - The stub's inherited no-arg `DbPatch.patch()` (:33-45) is what gets the connection and calls `patch(conn)`.
- **`DbReleasePatch`** (`P/DbReleasePatch.java:28-66`): when `-u X > db.release` and `X == build branch`, it sets `db_info.previous_release=old` and `release=X`. Otherwise it prints one of the two "Cannot upgrade…/Cannot updated…" messages. **With `-u`, no numbered patches run**, because the pool uses a plain `DbPatcher` with the extra patches excluded.

### 2.7 Where the files come from
- **The SQL root** is `PatchSystemState.patchRoot + <vendor> + <dirName>` (`P/DbPatchSystem.java:774-780`):
  - Legacy mode: `$ATYPON_HOME/patch/`, i.e. the live literatum-patch checkout (:924-927).
  - Otherwise: `$DEPLOY_HOME/webapps/<product>/iapps/patch/` (:928).
- **The directory for each pool** comes from `P/DatabaseType.java:18-21`:

  | DatabaseType | Pool | Directory | Prefix |
  |---|---|---|---|
  | LITERATUMDB | jdbc | literatum | lit |
  | REPORTDB | report | report | rep |
  | ARCHIVEDB | archive | archive | arc |
  | COMMONDB | common | common | com |

  `LP/mssql/mdclog` has no DatabaseType, so it is **never run** by this system.
- **`iapps/patch`** is filled at build time by `copyPatchesToDeployRoot`. It copies from `$ATYPON_HOME/patch` and excludes `create/`, `old/`, `java/`, `out/` and `build.gradle` (`buildSrc/.../ProductPlugin.groovy:1316-1336`), and only when `LOCAL_BASE` is set.
- **The stub classes** are compiled by the `:patch` project:
  - `atypon/settings.gradle:25-27` sets `projectDir = patch-build`.
  - `atypon/patch-build/build.gradle:16-27` compiles `srcDirs '../patch/java/src'`, i.e. literatum-patch cloned at `atypon/patch`.
  - `product-common.gradle:20` pulls it in with `implementation project(':patch')`.
  - `copyArtifactsAndDeps` puts it into `WEB-INF/lib` (`ProductPlugin.groovy:305-333`).
- **The migration targets** (`com.atypon.modules.migration.*` and friends) live in `literatum.jar`, which is built from the literatum repo.

---

## 3. Ordering, gating, reserved, retry

### 3.1 Discovery and ordering (`P/DbVersionCheck.java:79-156`)
1. The file list is every file in the directory matching `<prefix>[0-9]{4,5}?\.sql$` (:162-178). The list is sorted lexicographically.
   - **A 6-digit patch number would be silently ignored.** The highest today is lit32054.
2. `db_version` rows with `status=0` are read in `ORDER BY patchname` (:185-198). `trimPatchList` is a lexicographic merge that removes names already applied (:207-247). `status=1` (failed) rows are **not** removed, so failed patches are re-queued on every run.
3. The result is sorted by **numeric suffix** (:91-100). Release-based ordering is commented out (:112-113).
4. For each metadata: skip if `isTrulyReserved` (:120), then `isExecutablePatch(meta, true)` (:123), then `createPatch` (:124). With a patch plan active, `checkPatchDependency` depth-first inserts the plan dependencies first (:127, :249-263).
5. **`run_ddl_patches_first='T'` moves the patch to the END of the queue** (:136-147). The name is inverted relative to what it does. It is forbidden on DDL patches (`P/FilePatchMetadata.java:327-329`).
6. **`before_content_fix_runner='T'`** patches are pulled out and run before `fixCoreContent`. They may not also use `dependson` or `run_ddl_patches_first` (`FilePatchMetadata.java:314-326`).

### 3.2 Guards applied to the whole queue (`P/DbPatcher.java`)
These throw for the whole pool.
- **Drop column/table on a non-trunk DB** without `--allowdropcolumn` → `...dropping tables or columns on a live branch is not allowed (LIT-45620 and LIT-149317)...` (:110-156). The deploy server adds `--allowdropcolumn` for some accounts (SshExecuteVisitor:452-454).
- **A sequence table or `nextval`** when `db_info.use_native_sequence=true` (:68-91).
- **Non-Unicode CHAR/VARCHAR/TEXT** in a `CREATE/ALTER TABLE` (:49-67, regex at `P/DbSqlPatch.java:228`).

### 3.3 Header gates (`P/FilePatchMetadata.java`)
- Headers are `--@key='value'`, taken from the first 100 lines only (:250-286, regex at :262). **An unknown key throws `java.lang.Error: Invalid patch parameter: <key>`** (:273). That is an Error, so it escapes every `catch(Exception)`.
- Defaults are at :288-309:
  - transaction = true, reserved = false
  - server_mode = all modes, activiti = F
  - `release_parm` is required (:313)
- Gates in `PatchVersionChecker.isExecutablePatch` (`P/PatchVersionChecker.java:37-100`):

  | Gate | Lines | Behaviour |
  |---|---|---|
  | Product | :47-50, :107-162 | `product_parm` include list or `product_exemption_parm` exclude list against `db_info.product`, not both. |
  | Release | :52-55 | `release_parm <= db_info.release`. This is a lowercase string compare, so `'trunk'` sorts after any digits and trunk patches only run on trunk DBs. |
  | Max release | :57-60 | `max_release_parm >= db release`. |
  | Already applied | :62-65 | A `status=0` row exists. |
  | Dependency | :66-72 | `dependson_parm` must be applied. **Checked only when `noException=false`, i.e. at execution time, not at queue-build time.** |
  | Server mode | :74-76 | `server_mode_parm` against `ServerMode.getServerMode()`. |
  | Property | :78-80; FilePatchMetadata:191-243 | `boolean_property_parm`: one prop, or `p1,and|or,p2`. A property that is missing counts as disabled. |
  | Activiti | :82-85 | Throws `Error`. |

### 3.4 Reserved patches
- `isTrulyReserved = reserved && !testMode && !(forceRunReserved && name ∈ forceRunReservedSet)` (`P/FilePatchMetadata.java:172-174`).
- `forceRunReservedSet` is filled only from the patch plan XML `plan[@name=<branch>]/forceRunReserved/conditional-reserved-patch` (`P/DbPatchSystem.java:320-323`).
- The patch plan file is `$SCRIPTS_HOME/patchplan/patchdependency_<build-branch>.xml` (:271-282). The branch comes from `--patchplan` or `db_info.previous_release` (:287-289, :359-374).
- **`-F` on its own does nothing** unless the patch is in that plan set.
- In auto mode a reserved patch is silently skipped (DbVersionCheck:120, :257).
- In `-f` mode it throws:

  ```
  Error: Patch X is reserved, use -F to run reserved patch. Make sure it is in patch plan…
  ```

  (DbPatchSystem:157-162)
- A reserved JAVA patch never gets a `DbJavaPatchWrapper`, so **a missing stub for a reserved patch is harmless** until someone flips `reserved_parm` to `F`.
- Reserving a number in the repo: add a valid `.sql` with `--@reserved_parm='T'` and label the PR `reserved-sql-automerge` (`LP/README.md:9-18`). The workflow auto-merges only PRs that add `.sql` files and nothing else, and at least one added file must contain `--@reserved_parm='[Tt]'` (`LP/.github/workflows/reservedPatchAutoMerge.yml:31-124`).

### 3.5 Error, continue and retry semantics
- **Default Gradle path, without `-c`:**
  - `continueOnError=false` means the first failing patch rethrows out of `executeQueuedPatch` (`P/DbPatcher.java:260-268`).
  - `handleException` logs, prints `ex.getMessage()`, mails the system operator and rethrows, because `ignoreerror` is always false on this path (:384-404).
  - `runPatchers` stops. The remaining pools and patches do not run. The JVM exits 1.
- **With `-c`:** a failing patch's exception is **swallowed** (DbPatcher:260-268). Its stack trace is printed (JDBCPatchExecutor:101) and `db_version` gets `status=1`, but the `…failed to execute` RuntimeException is never printed. The pool finishes, prints the "ends" marker and exits 0. **patch.py may then report success**, unless the word `FAILED` happens to appear in the printed stack.
- **No automatic retry exists in the framework.**
  - Re-running is the retry. A failed patch has `status=1`, so it is re-discovered (DbVersionCheck:189) and its row is UPDATEd (JDBCPatchExecutor:155).
  - A failed patch's work was rolled back only if it ran in a transaction. `transaction_parm='F'` patches can leave partial work behind.
  - The deploy server reschedules a failed ProductPatch once, and only if the log contains `restart build` or `Unable to delete file … DbAntPatcher.class` (`DS/.../SshExecutedVisitor.java:459-466`, `DeployDaemonHelper.java:539-540`).
- **Test mode `-t`:** every patch is rolled back through `TestRollbackException` (JDBCPatchExecutor:71-74; DbPatchSystem:687-688 prints `Test completed successfully, rolling back patch.`). Test mode also makes reserved patches runnable (FilePatchMetadata:173).

---

## 4. Where errors surface, and "Patch failed! Output is in"

**The layers, from the patch outward:**
1. **The patch.** An exception is caught by `JDBCPatchExecutor.handlePatchError`:
   - It prints the stack to stdout, which reaches both the log and the console.
   - It writes a `db_version` row with `status=1`, `message=<patch output>\n<throwable.getMessage()>`.
   - It throws `PatchProgram (<product>):Patch <litNNNN> failed to execute` (`P/JDBCPatchExecutor.java:97-126`).
2. **The pool.** `DbPatcher.handleException` prints `ex.getMessage()`, e.g. the line above, and mails the operator (`P/DbPatcher.java:384-404`).
3. **The system.** `DbPatchSystem.run` prints the stack again (`P/DbPatchSystem.java:197-199`).
4. **The VM.** `DbGradlePatcher.ss` prints the stack a third time, to stderr, and calls `System.exit(1)` (DbGradlePatcher:20-27).
5. **Gradle.** `> Task :runWithJavaExec FAILED`, `Process '…java' finished with non-zero exit value 1`, `BUILD FAILED in …`.
6. **patch.py** (`PT/patch.py:186-206`):
   - It checks the whole captured text for `FAILED` or `KILLING THE SYSTEM`. On a match it prints `Patched Successfully: <list>`.
   - It writes the full capture to a new temp file, `/var/tmp/<time.time() as %f>.txt` (`PT/temputil.py:5-20`), and prints **`Patch failed!  Output is in /var/tmp/<epoch>.txt`** (two spaces after `!`).
   - It logs FAILURE to LDS. With `-e` it exits −1; otherwise it raises `DeployErr` with the same text.
7. **The deploy server** parses the action log (`DS/.../SshExecutedVisitor.java:432-505`):
   - `BUILD FAILED` means failure.
   - A line containing `PatchProgram` and `failed to execute` has token `[len-4]` taken as the failed patch name, e.g. `lit32053`, which schedules a **BrokenPatchBlame** action (:451-456, :489-505).
   - `BUILD … SUCCESSFUL` means success.
   - ProductDBUpgrade also requires `Patch complete.`.

**What "Patch failed! Output is in X" corresponds to:**
- X is simply the whole captured console of that `run_gradle.sh` run: stdout and stderr of Gradle and of the patch VM. It **includes** stderr (`KILLING THE SYSTEM`, the DbGradlePatcher stack), which `$DEPLOY_HOME/log/<product>/gradle.patch.<ts>.log` does not have.
- The trigger is a plain substring match. That means:
  - Any patch output containing `FAILED` (e.g. a result-set value) also trips it.
  - A Spring or bootstrap death trips it through `KILLING THE SYSTEM` even though no patch ran.
- To find the real cause, read X for the **first** `Caused by:` under `Executing patch <name>`, or the Spring stack before `KILLING THE SYSTEM`.

**Exact messages worth grepping.** `P` below is the prefix `PatchProgram (<product>):`, from `P/Patch.java:14`.

| Message | Source |
|---|---|
| `P DB version <db> doesn't equal your build version <build> you can ignore this check by running patch.py with -R` (+ `, or upgrade the DB with -u` when build > db) | DbPatchSystem:126-131 |
| `P Cannot fetch release level from database` | :644, DbReleasePatch:40 |
| `Warning!!! Patch plan not loaded. Possible causes: …` | :292, :295 |
| `Cannot load patch plan …` | :327 |
| `P Database Pool setup failed.` (preceded by `Failed to initialize database pool for patching: …`) | DbPatcher:300-301 |
| `P Database type mismatch: expecting <vendor>, found <class>` | DbPatcher:310-312 |
| `P error with version checking db_version (<file>):\nPOOL URL: <url>\n<msg>` | DbVersionCheck:153-154 |
| `P Cannot find patches in directory: <dir>` | DbVersionCheck:171 |
| `P Invalid patch file: <f>, please check its @release_parm setting` | FilePatchMetadata:313 |
| `java.lang.Error: Invalid patch parameter: <key>` | FilePatchMetadata:273 |
| `P Patch <n> is of an unknown type` / `… contain DDL and DML SQL; which is not allowed!` | PatchLoader:17, :27 |
| `P [DbSqlPatch] Patch contains illegal SQL:…` | DbSqlPatch:177 |
| `Patch function not found: <name>` → `Error trying to execute patch function` | PatchFunctionExecutor:75, DbAbstractSqlPatch:42 |
| `P Check Version: Missing prerequiste patch` (typo is in the code) / `… Patch already applied` / `… Incorrect release level` / `… Incorrect product` / `… Server mode X not configured for this patch` / `… Property is undefined or set to false` | PatchVersionChecker:49-80 |
| `P Error trying to initialize patch: java.lang.ClassNotFoundException: com.atypon.patch.PatchNNNNNN` | PatchLoader:62-63 |
| `P Patch <litNNNN> failed to execute` | JDBCPatchExecutor:119 |
| `P Updating the Db Version table failed!` | JDBCPatchExecutor:216 |
| `patch pool marker for '<pool>' begins.` / `… ends. All patches applied successfully.` | PatchCompletionCheckerConstant:4-6 |
| `****** Core Content Bootstrapping FAILED ******` | DbPatchSystem:973 |
| `Cannot initialize Spring` (log) → `********** ERROR LOADING PRODUCT <p> **********` … `********** KILLING THE SYSTEM **********` | SpringAdapter:139; Main:444-449 |

---

## 5. Patch-VM Spring startup, and why a Gaia/Cassandra bean kills the run

**The bootstrap path:** `DbPatchSystem.setupVM` (`P/DbPatchSystem.java:414-428`):
- It sets `server.type=patch` (:416), `CacheUtils.ENABLED=false` (:420) and `literatum.remoteBroadcastEnabled=false` (:421).
- `new Main()` gets `setPreload(false)` (:425) and `addSpringProfile("patch")` (:426), then `main.run()` (:427).

**`Main.run`** (`L/Main.java:126-162`) starts the ManagementService and calls `initialize()` (:211-267):
- Logging, locale, system properties, XslConstants and `verifyFileSystem` run first. `server/patch/verify-file-system=false` (`CONF/literatum.props.xml:26102`).
- **`newSpringAdapterFromConfig()`** (:224-234) → `setSpringAdapter(adapter)`, which **refreshes the context immediately** (`L/util/LegacySingletons.java:76-85`).
- `SearchConfigurationLoader` is skipped for the patch type (:242-249).
- Then `DbConf.start()` runs (:142-144).
- **Any Throwable → `abortSystemStartup` → prints `ERROR LOADING PRODUCT` / stack / `KILLING THE SYSTEM` → `System.exit(1)`** (:146-154, :442-451).

**What the context contains:**
- `SpringAdapter.newContextFromProperties` → `ComponentRegistry` from the `components` registry set (`L/spring/SpringAdapter.java:157-181`; `L/ComponentRegistry.java:61-99`).
- Every `config-file` is included unless `enabled=false` or its `server-type` excludes `patch` (ComponentRegistry:120-145).
- In the base props only `workflow-monitoring` and `paypal-tx-status-updater` are `server-type=backstage` (`CONF/literatum.props.xml:25909-25920`).
- **So the patch VM loads essentially the full web context:** core, cms, acs, ecommerce, frontend, bridge, analytics, search, kafka if enabled, cil, jwt, product, workflow-common, plus product-added components such as `gaia-fe-base` (order 275) and `gaia-fe` (280) from `MID/midtier.props.gaia-fe*.xml`.
- The `patch` profile removes only a few Java-config beans:
  - `robotService`, `deploymentVerifier`, `coreLegacySingletons` (`L/spring/CoreSpringConfig.java:66-126`)
  - `WebSpringConfig` (:18), `RobotsRegistrar` (:30), `CmsSpringConfig` (`PUB/publish/cms/CmsSpringConfig.java:10`)
  - Customization/urlService/services are swapped for patch dummies (`L/customization/CustomizationSpringConfig.java:32-91`). The code comment there says so directly: *"It is not easy to modify existing XML files to exclude beans that are not needed"* (:66-68).
- **The robots list for `server/patch` is empty** (`CONF/literatum.props.xml:26104`). Robots don't start. All singleton beans still do.

**The Gaia/Cassandra chain:**
- `CONF/spring/gaia-fe-base.xml:6` declares `<bean class="com.atypon.literatum.gaia.GaiaFeBeans"/>`. It has no profile, so all its `@Bean` methods are eager singletons.
- **`GaiaFeBeans.getOutputCacheFactory()`** (`L/gaia/GaiaFeBeans.java:116-134`) iterates **every** child of `gaia/caches` and calls `factory.produce(name, node)` during refresh.
  - `getTransformationRepository` depends on it (:79-84).
- `MID/midtier.props.gaia-fe.xml:15-36` defines a `cassandra` cache with keyspace `gaia_${product}_${mode}` and `versioned=${gaia/cache-versioning-enabled}=true`. aiaa staging includes this file (`atypon/product/aiaa/conf/aiaa.props.IBM-stag.xml:3`); base `aiaa.props.xml` does not.
- The gaia-registry 1.7.3 bytecode shows `CassandraOutputCacheFactory.produce`:
  1. `CqlSession.builder().withLocalDatacenter(<datacenter|datacenter1>).addContactPoint(nodes…).build()` — a live connection.
  2. `createKeyspaceIfNotExists` (SimpleStrategy, RF).
  3. For a versioned cache, `new VersionedCassandraOutputCache(name, session, ks, n)`. Its `StatementManager` ctor builds `TableIndexStatements`, which does `isTableExists("table_index")`, then `CREATE TABLE IF NOT EXISTS <ks>.table_index (id, name)`, then **`session.prepare(SELECT id,name FROM <ks>.table_index …)`** plus two more `prepare`s.
- **So bean creation itself does I/O against Cassandra.** Any of these throws out of the `@Bean` method:
  - Unreachable contact points (`AllNodesFailedException`).
  - A wedged node answering `InvalidQueryException: … table_index does not exist`.
  - Schema disagreement right after the CREATE.
  - A driver/Guava classpath clash.
- That surfaces as `BeanCreationException: Error creating bean with name 'getOutputCacheFactory' defined in com.atypon.literatum.gaia.GaiaFeBeans…`. Refresh fails, `SpringAdapter` logs `Cannot initialize Spring` and rethrows as `Error` (`L/spring/SpringAdapter.java:138-141`), and `Main.run` aborts the JVM. **Before any patch or pool marker is printed.**
- `table_index` is the index table that `ansible-cassandra/roles/cleanup/tasks/cleaner.yml:1-85` reads and deletes IDs from, and that `OT/GaiaVersionedCacheChecker.java:38, :231` queries. Cleanup or keyspace-drop activity on the gaia keyspace is the other realistic trigger.
- **The fix is on the Cassandra side, or in making the bean lazy or `@Profile("!patch")`.** Nothing in the patch set can work around it.
- the `literatum-patch-cassandra-failures` skill covers the node-health diagnosis sequence. I read it; it matches this analysis.

Other Spring-startup killers follow the same path: DB pool creation (`DataSourceManager`), the Akka/cluster config under `DynamicConfigsFromProperties` (`CoreSpringConfig.java:178-208`), Kafka when `index/kafka/enabled`, and any XML-declared bean that connects at init. The `LiteratumDS` latest-patch check is skipped for the patch type (`L/persistence/LiteratumDS.java:105-125`).

---

## 6. `db_info` and `db_version` tracking

**`DB_INFO`** (`L/util/db/version/DbInfo.java:17-36`) holds name/value rows.

| Name | Used for | Where |
|---|---|---|
| `release` | The release gate | DbPatchSystem:640-657; PatchVersionChecker:202 |
| `previous_release` | Patch plan branch | :362-363 |
| `product` | The product gate | PatchVersionChecker:237 |
| `use_native_sequence` | The sequence guard | DbPatcher:94 |
| `patch system` = `v3` | Historical marker | `LP/mssql/literatum/patch_system_v3.sql:136` |

`-u` updates `release` and `previous_release` (DbReleasePatch:44-57).

**`DB_VERSION`** (`L/util/db/version/DbVersion.java:20-37`, `DbVersionColumns.java:5-17`):
- Columns: VERSIONID (seq `VERSIONID_SEQ`, allocated lazily by `FilePatchMetadata.getVersionId` :152-165), PATCHNAME, DEPENDSON, DATEAPPLIED, REQUIRESCODECHANGE, AFFECTEDTABLES, STATUS (0=ok, 1=failed), RELEASE, DESCRIPTION, MESSAGE, TIMEINSECONDS.
- Only `status=0` counts as applied (DbVersionCheck:189; PatchVersionChecker:176-184).
- `requirescodechange` feeds the webapp startup check `DbVersionChecker` against `database/<pool>/latestPatch`. That check is skipped for `server.type=patch` (`LiteratumDS.java:105-116`).
- The old stored procedures `check_version2` and `update_version3` in `patch_system_v3.sql` are **not** used by the Java executor. It builds its own SQL.

---

## 7. literatum-patch repo facts

- **Layout:**
  - `mssql/{literatum 3059, report 487, archive 24, common 14, mdclog 2}` files
  - `java/src/com/atypon/patch/` (2373 `.java`), `java/old/` (167, excluded from compile)
  - `data/` (patch input files, which I did not read)
  - `build.gradle`: legacy, used for lit-2010 and earlier branches only. Trunk and newer branches use `atypon/patch-build/build.gradle` (`LP/build.gradle:12-17`).
  - `update-release-level.sh`: an SVN-era tool that rewrites `release_parm='trunk'` to a branch.
  - `getNextAvailablePatchName.sh`: `ls -va | tail -1` plus 1.
- **Numbering:** `lit1050`…`lit32054` (1353 four-digit, 1700 five-digit). The loader regex caps at 5 digits (DbVersionCheck:167).
- **Headers:**
  - The template is `mssql/literatum/lit_patch_template.sql:1-19`.
  - 1532 of 3053 literatum patches are Java (`java_patch_parm`). 473 are `reserved='T'`.
  - Explicit `type_parm` values: DDL 83, DML 39, JAVA 30, DDLDML 7. The rest are blank (UNKNOWN), so legacy SQL or JAVA by class.
  - `java_patch_parm` targets: 1536 `com.atypon.patch.*` stubs. A few point straight at a non-stub class (e.g. lit32038 → `com.atypon.modules.migration.Patch0316959`; 21 point at `com.atypon.bridge.patch.*`), which skips the stub layer.
- **Stub targets** (count of `loadDynamicPatch` targets): 1458 `modules.migration`, 378 `bridge.patch`, 302 `marlin.patch`, 108 `pericles.patch`, and a long tail.
  - Stubs are not always 1:1 with number. lit32036 → `Patch0316958`; lit32049 reuses `Patch032025`; lit8632 and lit8775 → `Patch007133`.
- **Inline functions:** the top ones are `--$deleteEmployee` 876, `CreateSuperAdminRole` 492, `createNewEmployee` 491, `pagebuilderConfig` 334, `dropIndexIfExists` 207. The function name is the class simple name without `Patch`, lowercased (PatchFunctionExecutor:29-36).
- **Missing stubs in this checkout** (non-reserved SQL whose `com.atypon.patch.X` has no `.java`): only lit5639 and lit8656 (`Patch005639`, rsna) and lit8632 and lit8775 (`Patch007133`, esspp). All are 2010s-era. All other missing stubs belong to reserved patches (e.g. lit32051 → `Patch032051`), which is harmless until someone unreserves them.

### 7.1 How a stub `ClassNotFoundException` happens (LIT-683278 shape)
- **Missing stub:** the `.sql` names `com.atypon.patch.PatchNNNNNN` but the stub `.java` is not in literatum-patch at the commit the build compiled into `patch.jar`.
  1. The queue builds fine, because JAVA only records the name (PatchLoader:36-41).
  2. Earlier patches run and commit.
  3. At its turn, `initializeJavaPatch` → `Class.forName` throws, giving `P Error trying to initialize patch: java.lang.ClassNotFoundException: com.atypon.patch.PatchNNNNNN` (PatchLoader:59-63).
  4. That leads to `db_version status=1` and `P Patch litNNNNN failed to execute`, the run stops, and patch.py prints `Patch failed!  Output is in …`. The deploy server blames `litNNNNN`.
- **Missing target:** the stub exists but its target (e.g. `com.atypon.modules.migration.PatchNNNNNN`) is not in the deployed `literatum.jar`.
  - `DbPatch.loadDynamicPatch:63` throws a **raw** `java.lang.ClassNotFoundException: com.atypon.modules.migration.PatchNNNNNN` (stack frame `DbPatch.loadDynamicPatch`), without the "Error trying to initialize patch" wrapper.
  - This is a literatum-branch problem, not a literatum-patch one.
- **Skew between SQL and jar:** on non-production hosts, legacy mode reads SQL live from `$ATYPON_HOME/patch/`, which can be `git pull`ed to a newer commit than the one compiled into the deployed `patch.jar`. That gives the same CNFE with no repo bug. On `LOCAL_BASE` hosts the SQL comes from `iapps/patch`, copied in the same build as the jar, so skew can only come from the repo itself.

---

## 8. Persistence read-only semantics

**Three mechanisms. Don't conflate them.**

1. **Entity flag** `AbstractDbBasic.readOnly` (`L/persistence/AbstractDbBasic.java:60, 75-83`; setter is protected).
   - `saveImpl` and `deleteImpl` throw **`new ReadOnlyException()` with no message** when `isReadOnly()` (:327-329, :576-578; `AbstractDbEnhanced.java:51-53, :99-101`).
   - **`isReadOnly()` is overridden dynamically** by:
     - `IdentityImpl` (`PUB/iam/identity/internal/IdentityImpl.java:612-635`): true if the flag is set, or the persisted identity's Fields have access rights == CR (`EntityAccessRights.isReadOnly`, `L/acs/EntityAccessRights.java:65-75`), **or any direct group it belongs to is read-only**.
     - `LicenseImpl` (`PUB/publish/acs/license/LicenseImpl.java:616-631`): true if the flag is set, or the persisted license's Fields are CR, **or its licensee user `isReadOnly()`**.
2. **Cached-entity version** (`version<0`). This throws `ReadOnlyException` **with a message**:
   - `cannot insert cache entity` (AbstractDbBasic:368)
   - `attempt to save cached entity. this version: N` (:433)
   - `cannot delete cache entity` (:590; AbstractDbEnhanced:114)
3. **Site read-only mode** (`L/persistence/ReadOnlySiteUtil.java:61-103`, driven by `acs/start-in-read-only-mode`; aiaa sets it true only in `aiaa.props.IBM-ro.xml:6`). This throws **`ReadOnlySiteUtil.WriteDeniedError`** (an `Error`), **not** `ReadOnlyException`.

**Who sets the flag to true** (grep of 226 `setReadOnly(true)` hits; almost all are Vaadin UI fields in `/wat/` or JDBC `Connection`):
- Entity-level: only `LicenseImpl.getCopy` (`LicenseImpl.java:1445-1458`, `that.setReadOnly(true)` at :1451) and `Issue.newReadOnlyIssue` (`PUB/publish/acs/metadata/Issue.java:1986-2009`).
- Field-level CR marking comes from `EntityAccessRights.markReadOnly`. Callers include the `--$markReadOnly(code…)` and `--$markPersonIdentityWithEmailAsReadOnly` patch functions (`MP/functions/MarkReadOnlyPatch.java:41-51`, `MarkPersonIdentityWithEmailAsReadOnlyPatch.java:62-80`) and **`AddAtyponIPsToAtyponInstitution`**, which marks "Atypon Institution" CR (`PUB/modules/migration/AddAtyponIPsToAtyponInstitution.java:123, :138`).
- `getCopy` callers are all request-time code: `SessionData.java:2879, :3565`, `DefaultCartService.java:1188`, `SubscriptionInfoBuilder.java:204`, `SubscriptionBean.java:383, :406, :440`. **None is on a patch or identity-delete path.**

**The license lookups the delete path uses return fresh objects, not copies:**
- `findByUser(id, false)`: `useCache=false` skips `LicenseCache`, and the `DbColMatchCache` lookup with `useCache=false` reads the DB (`LicenseServiceImpl.java:138-149`).
- `findByOwner` is a plain `Finder…fromWhereFastSubclasses` (:200-202).
- `IpRangeUserServiceImpl.getFirst` is `Finder.of(IPRangeUser).fromWhere` (`IpRangeUserServiceImpl.java:97-109`), also fresh.

---

## 9. The aiaa `ReadOnlyException` in Patch032053

**The patch:**
- `LP/mssql/literatum/lit32053.sql:1-8` has release 2410, all products, no gates, `reserved='F'`, and `java_patch_parm='com.atypon.patch.Patch032053'`. It is JAVA with the default `transaction_parm`, so it runs inside `Transaction.execute`.
- The stub `LP/java/src/com/atypon/patch/Patch032053.java:10-12` delegates to `PUB/modules/migration/Patch032053.java`.
- That class:
  - Looks up group `AUTO_TEST_USER` (:16-17).
  - Looks up the IP range user for the **old CF WARP IP `104.030.132.204`** and, if present, **`oldIpRangeUser.delete()`** (:19-22).
  - Then creates or finds 104.30.180.202 and .203 and adds them to the group (:24-42).
- The old IP was added by `Patch032035` (lit32035, identical description) with `new IPRangeUser(…).save()` plus `qaTestGroup.addMember` (`PUB/modules/migration/Patch032035.java`).

**Call path of the delete:**

```
IPRangeUser.delete()                        → AbstractDbBasic.delete (tx exists) → deleteImpl()   [AbstractDbBasic.java:523-536]
  IdentityImpl.deleteImpl → clean() FIRST, then super.deleteImpl()                                 [IdentityImpl.java:251-254]
    cleanImpl: … deleteLicenses() (:268) … deleteFromGroups() (:271) …                           [IdentityImpl.java:261-309]
      deleteLicenses: for L in findByUser(id,false) + findByOwner(id): L.delete()                 [IdentityImpl.java:891-908]
        LicenseImpl.deleteImpl → … super.deleteImpl → AbstractEntity.deleteImpl                   [LicenseImpl.java:1476-1484; AbstractEntity.java:44-47]
          AbstractDbEnhanced.deleteImpl: if (isReadOnly()) throw new ReadOnlyException()          [AbstractDbEnhanced.java:99-101]
            LicenseImpl.isReadOnly → CR fields, or getUser().isReadOnly()                          [LicenseImpl.java:616-631]
              IdentityImpl.isReadOnly → CR fields, or member of a read-only group                  [IdentityImpl.java:612-635]
    super.deleteImpl → AbstractEntity → AbstractDbEnhanced.deleteImpl: isReadOnly() (the IP user) [AbstractDbEnhanced.java:99-101]
```

**Verdict: no, it is not a read-only license copy.**
- The only way to get a flag-read-only license is `LicenseImpl.getCopy`, and it is never called on this path.
- Every license this path deletes is freshly loaded from the DB. The `ReadOnlyException()` (no message) comes from the **dynamic** `isReadOnly()` rules.

**Most likely cause:** the old IP range user is a **member of a CR-marked group**, and "Atypon Institution" is the prime suspect.
  - **RESOLVED 2026-09-28 (LIT-683700):** the DB showed the IP user (1012507) IS a member of group 520 "Atypon Institution" (type 66 = 3) → inherited read-only. Note 04 was right; this note's downgrade from the file was wrong: a repo data file does not show DB membership. Fix: literatum PR #14359 removes the IP from AUTO_TEST_USER instead of deleting it.
- `AddAtyponIPsToAtyponInstitution` loads corporate IP ranges from `data/AtyponIPs/atyponIPs.txt` into that institution. It creates them with description `Atypon Ip <min>-<max>`, then `EntityAccessRights.markReadOnly(inst.getFields())` (:138).
- That makes every member IP user read-only (`IdentityImpl.java:627-632`), and every license held by that IP user read-only too (`LicenseImpl.java:630`).

**Which check fires depends on the data:**
- **If the IP user holds or owns any license**, the throw happens inside `deleteLicenses`. That is before `deleteFromGroups`, so the membership is still there, and the stack runs through `IdentityImpl.deleteLicenses` → `LicenseImpl.deleteImpl`.
- **If it holds no license**, the identity's own check runs after `deleteFromGroups` has removed its memberships. Two sub-cases:
  - It throws only if the IP user's own Fields are CR, or if `findDirectGroups` (relation lookup with `useCache=true`, `IdentityRelationServiceImpl.java:90-93`) returns the pre-delete membership. The stack then ends at `AbstractEntity.deleteImpl` right under `IdentityImpl.deleteImpl`.
  - If the IP user is only in `AUTO_TEST_USER` and nothing is CR, the delete succeeds.
- **aiaa specifics:**
  - Site read-only mode is ruled out. It throws `WriteDeniedError`, not `ReadOnlyException`.
  - The cached-version flavour would carry a message. A bare `ReadOnlyException` with a null message fits mechanism 1.

**How to confirm (for the operator to run; read-only):**
- Pull the failure row:

  ```sql
  SELECT patchname, status, dateapplied, message FROM db_version WHERE patchname = 'lit32053';
  ```

  The message holds the patch output plus the exception message. For the frames, use the `Patch failed!  Output is in /var/tmp/<epoch>.txt` file.
  - Frames include `IdentityImpl.deleteLicenses` and `LicenseImpl.deleteImpl` → **license path**.
  - Frames end at `AbstractEntity.deleteImpl` under `IdentityImpl.deleteImpl` → **identity path**.
- Check whether `104.30.132.204` appears in `LP/data/AtyponIPs/atyponIPs.txt`, and whether the IP user is a member of "Atypon Institution" (`USER_REL` membership rows). I didn't look, because of the data rule.

**Fix options** (pick one; this is code in the literatum branch):
- In `Patch032053`, skip the delete when `oldIpRangeUser.isReadOnly()`, or just remove it from `AUTO_TEST_USER` instead of deleting it.
- Temporarily `markEditable` the read-only group, the same way `AddAtyponIPsToAtyponInstitution.java:123-139` does.

**Separate risk:** on a product without group `AUTO_TEST_USER`, `qaTestGroup` is null. `isMember` then throws an NPE at `Patch032053.java:30`, because nothing gates the patch.

---

## 10. FAILURE SIGNATURE table

| What you see (in `/var/tmp/<epoch>.txt`) | Meaning / root | Stage | Code |
|---|---|---|---|
| `ERROR LOADING PRODUCT <p>` … `KILLING THE SYSTEM`, with `Cannot initialize Spring` / `BeanCreationException … 'getOutputCacheFactory' … GaiaFeBeans` and a DataStax `AllNodesFailedException` or `InvalidQueryException … table_index` | Gaia Cassandra cache built eagerly at patch-VM Spring refresh. Cassandra unreachable, node wedged, or `table_index` missing. **No patch ran, no db_version rows.** | Spring startup | GaiaFeBeans.java:116-134; Main.java:146-154, 442-451; SpringAdapter.java:138-141 |
| `KILLING THE SYSTEM` with a DB, pool, Akka or Kafka cause | Another eager bean failed | Spring startup | same |
| `DB version X doesn't equal your build version Y … -R` | Release gate. Run `-u` first (ProductDBUpgrade) or pass `-R` | pre-queue | DbPatchSystem.java:125-132 |
| `Database Pool setup failed.` / `Database type mismatch` | Pool or DB vendor problem; the pool is dropped | initializePatchers | DbPatcher.java:283-314 |
| `error with version checking db_version (<file>): POOL URL: …` | Metadata or DB error while building the queue. **The cause's own stack is lost**: only `e.getCause()` is kept | fillPatchQueue | DbVersionCheck.java:150-155 |
| `java.lang.Error: Invalid patch parameter: <key>` (`Exception in thread "main"`) | A typo in a `--@header` of any patch in the directory. Kills the run before anything executes | fillPatchQueue | FilePatchMetadata.java:273 |
| `…dropping tables or columns on a live branch is not allowed` | Drop in a patch on a non-trunk DB without `--allowdropcolumn` | fillPatchQueue | DbPatcher.java:110-156 |
| `…using sequence tables or nextval procedure is not allowed` / `…Non-Unicode Data types…` | Native-sequence and unicode guards | fillPatchQueue | DbPatcher.java:49-91 |
| `Patch X is reserved, use -F …` | `-f` on a reserved patch that isn't in the plan's forceRunReserved set | pre-queue | DbPatchSystem.java:157-162 |
| `Error trying to initialize patch: java.lang.ClassNotFoundException: com.atypon.patch.PatchN` → `Patch litN failed to execute` | **Stub missing** from literatum-patch or from the deployed `patch.jar` (LIT-683278), or SQL/jar skew in legacy mode | execute | PatchLoader.java:59-63 |
| `java.lang.ClassNotFoundException: com.atypon.modules.migration.PatchN` at `DbPatch.loadDynamicPatch` → `failed to execute` | The stub is fine; the **target class is missing** from `literatum.jar` on this branch | execute | DbPatch.java:61-64 |
| `Check Version: Missing prerequiste patch` → `failed to execute` | `dependson_parm` not applied. The dependency is enforced only at execution | execute | PatchVersionChecker.java:66-72 |
| `Patch function not found: X` / `Error trying to execute patch function` | Unknown `--$func` in the SQL, or a function bean failed to instantiate (logged and skipped at startup) | execute | PatchFunctionExecutor.java:38-41, 73-75; DbAbstractSqlPatch.java:42 |
| `ReadOnlyException` (no message) inside a Java patch | Dynamic read-only: CR-marked Fields, a user in a read-only group, or a `getCopy` license (not a patch path). See §8 and §9 | execute | AbstractDbEnhanced.java:99-101 |
| `ReadOnlyException: cannot delete cache entity` / `attempt to save cached entity` | The patch modified a cached (`version<0`) entity; load it fresh with Finder | execute | AbstractDbBasic.java:368, 433, 590 |
| `ReadOnlySiteUtil$WriteDeniedError` | The site started in read-only mode (e.g. `*.props.IBM-ro.xml`) | execute | ReadOnlySiteUtil.java:95-103 |
| `****** Core Content Bootstrapping FAILED ******` | Passport `fixCoreContent` failed (before the main patches). Skip with `--skipcontentfix` | post-before-content-fix | DbPatchSystem.java:957-975 |
| Run "succeeds" but `db_version.status=1` rows exist | Run with `-c`: per-patch errors are swallowed and never printed as `failed to execute` | execute | DbPatcher.java:260-268 |
| `Patch failed!` but every patch line shows `Patch complete.` | Some output merely contains the text `FAILED` | patch.py | patch.py:188 |
| Begin marker printed, no end marker (Ant path) | `PatchCompletionChecker` fails. It is not used on the Gradle path | Ant only | OT/patch.xml:96 |

---

## 11. Corrections to `literatum/docs/architecture`

- **04 §Schema patching** says `Patcher` "…then executes ordered steps" and that it "Run[s] with `server.type=patch`". This is wrong:
  - `Patcher.executeActions` is empty (`MP/Patcher.java:120-123`), and `main` forces a dry run (:242).
  - `server.type=patch` is set by `DbPatchSystem.setupVM` (`P/DbPatchSystem.java:416`). The live migration system is `DbPatchSystem`. Only `PatchFunctionExecutor` and `functions/*` from `modules/patch` are used by it.
- **05** says "Applied patches are tracked in `DbInfo` and `DbVersion` tables". Only `DB_VERSION` tracks patches. `DB_INFO` holds `release`, `previous_release`, `product` and `use_native_sequence`.
- **05** says `modules.migration` classes "are invoked as standalone programs, **not automatically on startup**". Most of them (1458) are invoked **automatically by the patch system** through `com.atypon.patch.*` stubs and `loadDynamicPatch`.
- **19** says "`patchDB` runs the schema migration ([05])". `ExecutePatch` runs `DbPatchSystem.run()` by reflection in a Gradle worker (`buildSrc/.../tasks/ExecutePatch.groovy:325-364`), not the `Patcher` diff engine. Note also that its `catch` writes errors to `$ATYPON_HOME/dout.log` and does not fail the task (:318-322).

---

## 12. Other flag behaviour worth knowing

- `-e`/`--haltonerror`:
  - The long form never matches, because the code compares against `--haltoneerror` (`PT/patch.py:388`). `getopt` accepts `--haltonerror` but the `if` falls through to "unknown option".
  - `-e` only changes `sys.exit(-1)` versus raising `DeployErr`. The Java side always rethrows anyway.
- `--skipJavaPatches`, `--ignoreAlreadyAppliedPatches`, `--disablePatchFunctions=` are accepted by `getopt` but unhandled (they print `unknown option`).
- `-D`/`--disablespring` → `setDisableSpring`, which is a deprecated no-op (`P/DbPatchSystem.java:916-918`).
- The patch VM output buffer that becomes `db_version.message` is per-patch (`JDBCPatchExecutor.java:27`). The full run history only exists in the `/var/tmp` capture and in `gradle.patch.<ts>.log` (stdout only).
