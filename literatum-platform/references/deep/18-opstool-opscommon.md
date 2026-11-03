# 18 — opstool + opscommon: what the Deploy Server's opstool commands actually check

Written 2026-09-25 from read-only code reading. Nothing was built or run.

**Repos and commits read**
- `OT/` = `$LIT_REPOS/opstool`, `master` @ `4562351` (grafted clone, so no file history).
- `OC/` = `$LIT_REPOS/opscommon`, `master` @ `7d5d1ac` (pom `3.0.31-SNAPSHOT`).
- `DS/` = `$LIT_REPOS/deployserver` @ `b726c83`. `PT/` = `$LIT_REPOS/platform-tools` @ `b00c49f`.
- Pinned versions: DS depends on opscommon **3.0.29** (`DS/pom.xml:74`). opstool depends on opscommon **3.0.24** (`OT/pom.xml:46`). Master is 3.0.31-SNAPSHOT. The classes read here (`ServerInstance`, `UrlFetch`, `ConfHelper`, `StyleguideConf`) could differ in those pinned jars. That is **Unverified**; the logic looks old and stable.

**Secrets.** Output was filtered with the standard regex, plus extra patterns for quoted-credential argument lists and bcrypt hashes. The filter missed some lines, so I saw them. Their values are **not** reproduced here:
- `OT/src/com/atypon/opstool/dbidx/DbIdxCollector.java:126`: a hard-coded Jira username and password passed to `Jira.Factory.getInstance(...)`. **Security finding: a credential committed in source. It should be rotated and moved out of the code.**
- `OT/src/com/atypon/opstool/schema/SchemaCli.java:68-95`: hard-coded DB credentials in dev sample command strings. Most are commented out; line 95 is live code but is overwritten by `-help` on line 98.
- `DS/src/.../visitor/SshExecuteVisitor.java` about lines 978-981: bcrypt hash literals in the mms cleanup SQL.
- `DS/config/actions.xml:620` and `PT/functions.sh:1822`: a `-tP` DB password literal on the SchemaCli restore command line.
- Lines dropped by the filter and never viewed: `RundeckApiService.java:73` (client construction), the `AwsS3.java` credential options and client construction (`:56-57,68-70,77-86,106-108`), `SvnSyncBranches.java:51,57,82,95,143-145`, and the DS Rundeck, SvnSyncBranches and NonVisualRegressionTest command lines. For those I printed option **letters** only.

---

## 1. How DS runs opstool

- Visitor path: `SshExecuteVisitor.runOpstool()` (`DS/.../SshExecuteVisitor.java:67-72`) sends `cd ~/apps64/opstool`, then `$HOME/apps64/java11/bin/java -classpath ./lib/*:./lib/opstool.jar <class> <args>`, then `exit`.
- Template path: `$util.opsTool(cls,args)` (`DS/.../actions/ActionHelper.java:37-38`) expands to the same line, prefixed with `cd ~/apps64/opstool;`. **Anything after it in the template runs in `~/apps64/opstool`** (this matters for ChangeGaiaVersion, see §3.6).
- Validation: `CompletedActionValidator.checkSuccessText` (`DS/.../CompletedActionValidator.java:18-35`) is a substring match on any line of `actionlogs/<id>.txt`. With `rescheduleOnFailure` a miss means **Scheduled** (poll again); otherwise it means Failure.
- **No opstool command's exit code is ever checked by DS.** Only the text is.

## 2. Command table

| DS action (source) | opstool command | What it checks or does | Pass text / DS rule | Fail text |
|---|---|---|---|---|
| **HostWaitForWebServer** (`S:81-85`, validated `SshExecutedVisitor.java:614-622`) | `DeployFamilyAction -f <fam> -t serverup -v` | For **every product of the family on this host** (per `~/deployconf.xml`): `GET http://localhost:<httpPort>/heartbeat?bg=1`. Passes on HTTP **200 with an entity; the body is ignored**. | `RESULT:SUCCESS`; a miss is rescheduled until `timeout.HostWaitForWebServer` | `RESULT:FAILURE`, plus a per-product `status=false` or `DeployFamilyAction.ERROR>` line |
| **HostUnlock** (`S:93-96`, validated `SshExecutedVisitor.java:556-557`) | `DeployFamilyAction -f <fam> -t unlock -v -p <prod>` (**`-p` ignored**) | `GET /heartbeat?id=unlock&bg=1` for every product of the family on the host. The body must start with `Unlocked`. Stops at the first failure. | `RESULT:SUCCESS`; no reschedule | `RESULT:FAILURE` |
| **HostWaitForHearbeat** (`S:88-90`, validated `:624-631`) | `DeployFamilyAction -f <fam> -t lock -v` | **It locks the node.** `GET /heartbeat?id=lock&bg=1`; the body must start with `Locked`. Its doc string says "polls … if heartbeat is unlocked" (`DS/config/actions-config.xml:915`), which is wrong. | `RESULT:SUCCESS`; rescheduled until timeout | `RESULT:FAILURE` |
| **HostLock** (template `X:1462-1466`; the visitor versions are commented out at `S:97-102` and `SshExecutedVisitor.java:606-609`) | `DeployFamilyAction -f <fam> -t lock -v` | Same as above | **no validator, so always Success** | (ignored) |
| Test / HostTest (visitor `runTest`, `S:640-760`) | `com.atypon.testdriver.DeployTestDriver … -C <xml> -t SiteTest|MultiSiteTest -b https://<host>.localhost.literatumonline.com:<ssl>` | Selenium suite. It writes `results/<id>/testresult.html` with `<h5>NN% (p/total) pass</h5>` (`OT/.../testdriver/common/TestResult.java:136-140,269`) | `testresult.html` contains `<h5>100%` (`S:779`) | anything below 100% |
| HostWarmupTest / HostEssentialTest | **not opstool**: `triggerDockerTEST` (docker `qaa`, note 12) | — | `***Test Is Succeeded***` (`S:708-716`) | `***Test Is Failed***` |
| HostWarmupContent (`S:627-639`, multi-site only) | `HitUrlsCli -b <baseUrl> -C <xml> -m -t 10` | Fetches a URL list | **always Success** (`SshExecutedVisitor.java:634-636`) | — |
| HostTestJane (`S:906-924`) | `com.atypon.testdriver.JaneTestDriver -t All` | Jane tests (sampled only) | via RemoteExecutor | — |
| ProductCleanupPostClone (`S:951-992`) | `ExecSqlCli` (pre-SQL), `TruncateTableCli`, `ExecSqlCli` (post-SQL, mms, done-marker) | Cleanup SQL | any `ExecSQL SUCCESS` line **and** no `java.sql.SQLException` line (`SshExecutedVisitor.java:665-682`) | `java.sql.SQLException` |
| ProductChangeBranch (`S:1035-1058`) / ConfigEditBranches (`S:1061-1090`) | `ChangeProductBranch -a -f -p -b [-s] [-g]` | XPath edit of `~/.litconfig/deployconf.<acct>.xml`, then `git commit`/`git push` | no `error: ` / `fatal: ` line (`SshExecutedVisitor.java:859-872`); triggers ConfigRefreshDeploy | `error: ` / `fatal: ` |
| CloneProductBranch (`X:1539-1550`) | `ChangeProductBranch -a <trg> -f -p -b -s` (**no `-g`**) | Same | invalid-txt `error: ` | `error: ` |
| ChangeGaiaVersion (`X:2762-2768`) | `ChangeGaiaVersion -a <acct> -g <ver>` | Rewrites `bundle_version=` on the tier-2 product `<gaia>` lines | **no validator, so always Success** | — |
| ProductBuild, svn branch (`X:1603-1629`) | `SvnSyncBranches` (flags `-a -r -u -p -o`) | Generates a shell script; `rebuild.py` is gated on `$?` | `BUILD SUCCESSFUL` (from rebuild.py) | — |
| DbProductBackupOrig (`X:590-631`) | `schema.SchemaCli` (up to 4 runs) + `AwsS3Put -b atydb` | Schema dump, backup, restore; S3 upload | `SchemaToolRunCompleted` | a missing line |
| DbIdxReportsCollector (`X:1588-1594`) | `dbidx.DbIdxCollector -a -j …` | Missing-index report per LITERATUMDB; attached to Jira | `Finished successfully` | a stack trace, no line |
| ToolCheckBackstageStuck (`X:724-731`) | `CheckBackstageStuck -o … -e … -np …` | Stuck workflows, suspended events, old uploads | **no validator, so always Success** | (it prints `CheckBackstageStuck FAILED - …` and DS ignores it) |
| RevisionReporter (`S:1509-1515`, validated `SshExecutedVisitor.java:1075-1096`) | `revision_reporters.Main svn|git since until bug [repo]` | CSV of revisions, attached to Jira | `Report generated successfully ` or `Build Successfully` | the loop stops at `Build Failed:` |
| NonVisualRegressionTest (`S:510-520`) | `jenkins.NonVisualRegressionTest` (flags `-d -u -j -P -a -c`) | Triggers a Jenkins job | `testresult.html` contains `pass completely`; otherwise **Cancelled** (`SshExecutedVisitor.java:946-956`). That string is **not in opstool**, so its producer is unknown. | — |
| UpdateStatusPage, ConsulPopulate, MountFS, GaiaDeploy, GaiaClusterDeploy, GaiaBuild, K8sPugrenderer{Deploy,Destroy,Build}, GaiaFeTagRelease, DestroyGaiaCluster, Audit{Deploy,Destroy,Backup,Restore} (`X:237…1675`) | `rundeck.RundeckApiService -a <acct> -i <jobId> [-o "…"] [-p <project> -w]` | Starts a Rundeck job (or JobWrapper `3e22a01d-…`) and streams its log | the job's own log lines: `COMPLETED SUCCESS`, `gaiadeploy execution success`, `<X> execution success`. **opstool never prints these**; they come from the Rundeck jobs, which are not in these repos. | an `ERROR: …` line, a stack trace |
| ToolOpstoolInstall (`X:1818`) | `build_opstool.sh -r` (see note 09) | — | `Finished Successfully` | — |

PT callers (not DS): `AwsS3Put` (`buildStyleguide.sh:176`, `Build-Deploy-Styleguide-test.sh:521`), `AwsS3Get` (`functions.sh:1774`, `getStyleguide.py:41`), `SchemaCli` (`functions.sh:1822`, `dbRestoreWithProdCleanUpPostClone.sh`), `DbIdxCli` (`dbidx:9`, which checks `$?`), `UptimeCheck` (`deployserver/uptimecheck.sh:5`). `aliases.sh:235-242` has interactive shortcuts (`SqlCli`, `FkIndexCli`, `JStackCli`, `JMapCli`, `ExecSqlCli`, `ChangeProductBranch`). `DeployFamilyAction` appears in PT only as a comment (`hostRefreshDeply.sh:61`); PT uses `lock.py` instead.

---

## 3. Per-command detail

### 3.1 `DeployFamilyAction` (`OT/src/com/atypon/opstool/DeployFamilyAction.java`, 152 lines, read fully)

- **Options** (`:38-42`): `-f` family (required), `-p` product, `-t` one of `Lock|Unlock|Heartbeat|ServerUp` (case-insensitive, `:72-77`), `-c` connect and read timeout in seconds (default **3**, `:79-80`), `-v` verbose.
  - With no args it defaults to `-f A -t Heartbeat` (`:34-36`).
  - With a missing `-f` or an unknown `-t` it prints help titled "UptimeCheck" and returns: **no RESULT line, exit 0** (`:45-49`).
- **Product bug** (`:70`): `this.product = cmd.hasOption('p') ? null : cmd.getOptionValue('p');`. With `-p` the product is `null`. Without `-p`, `getOptionValue` also returns `null`. **So the product is always null.**
- **Which instances** (`getProducts`, `:82-108`):
  - Host = `InetAddress.getLocalHost().getHostName()`, cut at the first `.`.
  - It reads **`~/deployconf.xml` on the target host**: the host's local copy, not DS's copy.
  - `new ServerInstance(family, null, host, null).findMatches(file)` matches on family (case-insensitive) and machine name (case-insensitive).
  - Then it de-duplicates by `family.product.host`, **preferring the `web` instance, otherwise the first instance found** (for example backstage).
- **Actions** (`:111`):
  - `Lock("/heartbeat?id=lock&bg=1","Locked",checkResp=false)`
  - `Unlock("/heartbeat?id=unlock&bg=1","Unlocked",true)`
  - `Heartbeat("/heartbeat?bg=1","0",true)`. **DS never uses this one**, though it is the only real readiness check.
  - `ServerUp("/heartbeat?bg=1","",true)`
- **runEx** (`:136-150`): `new UrlFetch(hc, plain=true, "localhost", si.httpPort, uri, debug, null)`.
  - If `!fetch.success`, it returns `checkResp ? false : null`.
  - If the expected response is empty, it returns **true**.
  - Otherwise it checks `body.trim().startsWith(response)`.
- **run** (`:122-135`) prints one of:
  - `DeployFamilyAction.<Action> for <fam> - <prod> - <host>:<port>. status=<true|false>`
  - `DeployFamilyAction.ERROR> <Action> for … , err:<exception>` for any throwable, such as connection refused or a socket timeout.
- **"FailSkip" never skips.** When runEx returns `null` (Lock with a failed fetch or wrong body), `:126` prints `… FailSkip` and then `return ok;` unboxes `null`. That throws an NPE, which the catch turns into `DeployFamilyAction.ERROR> … err:java.lang.NullPointerException` and `false`. **Lock fails; it does not skip.**
- **main loop** (`:51-60`): `ok=true`; for each instance, `ok = run(...)`, and it `break`s on the first false. Then it prints `RESULT:SUCCESS` or `RESULT:FAILURE`.
  - **If no instance matches, it prints `RESULT:SUCCESS` with no per-product lines** (vacuous success).
  - It never calls `System.exit`, so the exit code is 0 unless `getProducts()` throws (bad or missing `~/deployconf.xml`, a JAXB error, an unknown host). Then there is a stack trace, exit 1, and **no RESULT line**. WaitForWebServer and WaitForHearbeat reschedule and then time out; HostUnlock fails.
- **Verbose line** (from `UrlFetch`, `OC/.../utils/UrlFetch.java:62-64`): `http://localhost:<port>/heartbeat?bg=1, resp=<code>, success=<bool>, body=[<body>]`. **This is the best triage line in a failed HostWaitForWebServer log.**

### 3.2 `UrlFetch` (`OC/src/main/java/com/atypon/ops/common/utils/UrlFetch.java`, 157 lines, read fully)

This is the lib that note 12 said was "not found anywhere locally". It is in opscommon.
- `success = (respCode == 200 && entity != null)` (`:53`). **Only HTTP 200 counts.** 404, 500 and 503 all give `success=false` and `body=""`.
- Transport exceptions (connection refused, timeout) are **thrown** from the constructor (`:49`) and caught by `DeployFamilyAction.run`.
- `getClient(timeout)` (`:67-73`) is an Apache `DefaultHttpClient` with connect and SO timeout both set to `-c` × 1000 (3 s by default).
  - It uses the default redirect strategy, so a GET **follows 301/302/303/307**, and a redirect that ends at a 200 page passes.
  - (That redirect behaviour is Apache HttpClient 4.x default behaviour, not visible in this code; **Unverified** for the pinned version.)
- On the Literatum side, `/heartbeat?bg=1` goes to `checkDatabase(response)`, which **always writes 200 text/plain**: `0` or `1` (`literatum-lit-2610 …/HeartBeatServlet.java:152-157`). `sendUnlock` writes `Unlocked` (`:373-381`). `sendLock` writes `Locked` only for private or loopback callers; otherwise it writes an **empty 200** (`:383-395`).

### 3.3 `ServerInstance` (`OC/.../confutils/ServerInstance.java`, 470 lines, read fully)

- `findMatches(Collection)` (`:119-140`): a null or empty filter field means "any". Family, product, host and type use `equalsIgnoreCase`. Source matches `getBranch()`.
  - It **skips `solr-docker`** unless `type="solr-docker"` is asked for.
  - The 4-arg constructor sets `category=""`, so category is not filtered.
- `FindFromOM.execute` (`:182-307`):
  - Skips products with `enabled="false"` (`:211`).
  - Ports come from `<server><port><web|ssl|proxy>` (first value) plus a per-process-type offset from `<processes>`. A family override comes from `<deployfamilyinfo>` (`:153-181`, `:290-299`).
  - Skips machine processes `dummy`, `alert`, `*wrapper*` and `*metaproxy*`. An empty process name counts as `web` (`:274-289`).
  - With no `<port>`, `httpPort` = −1 + offset. With `new URL("http","localhost",-1,…)` that is the default port 80. **Unverified** what that does in practice; it probably fails.

### 3.4 `RundeckApiService` (`OT/.../rundeck/RundeckApiService.java`, 167 lines, read fully except the filtered `:73`)

- **Options**: `-a` account (`*-cip` selects the CIP Rundeck, anything else the DATACENTER one), `-i` job id, `-o` options, `-w` wrapper (requires `-p` project).
- A missing option prints a message and returns: **exit 0**, no job run.
- `runJob`, when the start is refused, prints `ERROR: <body>` and returns null, then prints `Couldn't run the job on Rundeck` to stderr: **exit 0**.
- `followLogs` prints each job log line until `execCompleted && completed`.
  - It retries up to 3 times on 503/504; any other error `break`s silently: **exit 0, and the log is truncated**.
  - It **never reads the job's final status**.
  - Parse, IO and other exceptions: `System.exit(1)`.
- So every Rundeck-backed DS action's pass or fail depends entirely on the **job printing its own marker text**.

### 3.5 `ChangeProductBranch` (`OT/.../ChangeProductBranch.java`, 153 lines, read fully)

- `-f` is matched **exactly** in XPath (`/literatum/product[@name='%s' and @deployfamily='%s']`), even though the help text says "regex is allowed" (`:41`, `:88`).
- `-b` is written as `$HOME/sourcegit/literatum-worktrees/<b>/atypon` with `-g`, or `$HOME/source/<b>/atypon` without it (`:30-31`, `:113-117`). The old value goes to `<previous_source_branch>`.
- `-s` updates `<styleguide><version>` **only if that node already exists** (`:141`); otherwise it silently does nothing.
- A missing product or `<source>` node **throws `java.lang.Exception: Product node for [p-f] doesn't exist`** (`:100`, `:108`). The remaining products or families in the loop are skipped.
- Prints: `Updated branch and prev source branch for <p> - <f>` and `Updated SG branch for <p> - <f>`.

### 3.6 `ChangeGaiaVersion` (`OT/.../ChangeGaiaVersion.java`, 75 lines, read fully)

- Rewrites `bundle_version="…"` on `<gaia …>` lines, **only inside `<product>` blocks that contain `<product-tier>2`** (in either order), in `DeployConf.getDeployConfFile(acct)` = `~/.litconfig/deployconf.<acct>.xml`, falling back to `~/sourcegit/deployconf/…` (`OC/.../literatum/DeployConf.java:147-158`).
- It substrings up to the next space after `bundle_version` (`:44`, `:58`). If `bundle_version` is the last attribute (`…"/>` with no following space), `indexOf` returns −1, so a **StringIndexOutOfBoundsException** is thrown and the file is not written.
- It prints nothing on success.

### 3.7 `SchemaCli` / `SchemaTool` (`OT/.../schema/SchemaCli.java` 253 lines, read fully; `SchemaTool.java` backup and restore sections read, `:129-180` and `:227-350`)

- Modes: `-od` dump the schema to a dir, `-db` data backup, `-dr` data restore, `-drs`/`-pdrs` schema restore, `-dt` threads (default 5), `-dd` data dir.
- It prints `SchemaToolRunCompleted. timeTaken=…` (`:251`) whenever no exception reaches `main`.
- **Per-table failures are swallowed.** Backup workers log `<thread> - Failed to backup - <table>, err=…` (`SchemaTool.java:342-345`); restore workers log `Failed to restore - <table>` (`:164-167`). The run still prints `SchemaToolRunCompleted`.

### 3.8 `AwsS3Put` / `AwsS3Get` / `AwsS3` (`OT/.../AwsS3*.java`, read fully except the filtered credential lines)

- **Options**: `-b` bucket, `-s` source, `-t` target, plus two credential options (filtered).
- `S3Action.doIt` catches **every** throwable, prints a stack trace, then prints `SUCCESS, tt=…` or `FAILURE, tt=…` (`:224-242`). **Exit code 0 either way.** Only an exception from `getClient()` escapes.
- `get()` skips the download if a local file with the **same size** already exists (`:134-139`).

### 3.9 `DbIdxCollector` / `DbIdxCli` (read fully)

- `DbIdxCollector`: one Worker thread per LITERATUMDB database (from `~/.litconfig/deployconf.<acct>.xml`).
  - A worker exception is a `RuntimeException` in that thread only. `main` still `join`s all threads, calls `zipAndAttach` (whose Jira errors are swallowed at `:128-130`), and prints **`Finished successfully`** (`:110`).
  - `-l` is documented as defaulting to foreign-key, but the code defaults to `all` (`:73`).
- `DbIdxCli`: a single DB; PT's `dbidx` wrapper checks `$?`.

### 3.10 `ExecSqlCli` (103 lines, read fully) / `TruncateTableCli` (output paths sampled)

- `ExecSqlCli` runs each SQL statement in its own transaction (`DbUtils.executeUpdate(...,true,stats)`).
  - Its `finally` prints `ExecSQL SUCCESS stat=…` or `ExecSQL FAILURE stat=…`. On failure the driver exception then propagates: `org.postgresql.util.PSQLException` or `com.microsoft.sqlserver.jdbc.SQLServerException`, **not the literal `java.sql.SQLException`**. That is a class-name inference from the driver jars; **Unverified** against a real log.
  - File-mode bug (`:49-54`): for a line with a trailing `-- comment`, `str.substring(idx)` keeps **the comment** instead of the SQL.
- `TruncateTableCli` logs `sql failed - <exception.toString()>` and continues (`:117-121`).

### 3.11 `CheckBackstageStuck` (404 lines, read fully)

- Reads `~/deployconf.xml`, then per LITERATUMDB runs T-SQL counts of `suspendCount > 1` events and events locked for longer than `-wt` (12 h), and checks `~/webdav_directories/<p>/live_upload` for zips older than `-ut` (3 h).
- It writes a CSV, emails `-e` when anything failed, and prints `CheckBackstageStuck SUCCESS` or `CheckBackstageStuck FAILED - <products>`.
- Per-product exceptions become `testFailureReason`, which marks the product failed. The queries are MSSQL syntax (`top`, `ISNULL`, `DATEDIFF`, `GETDATE`), so **Postgres products will always report failed** (inferred from the SQL; not run).

### 3.12 `SvnSyncBranches` (220 lines, read fully except the filtered lines)

- It generates a script (default `~/sync_svn_branches.sh`, or `-o`) that `rm -rf`s every `~/source/lit*` dir not referenced by the `-r` accounts' deployconf, then runs `svn cleanup`/`svn up` (`|| exit 1`) or a checkout per branch, and links `atypon/patch` to a `literatum-patch-worktrees` git worktree.
- The Java itself prints nothing unless `-c` is given. A missing account deployconf makes JAXB throw **before** the new script is written, so the caller would source the **previous** script. That is Unverified; it depends on the DS/PT wrapper, see note 02.

### 3.13 `revision_reporters.Main` (101 lines, read fully; `ReportHelper` sampled)

- Prints `Report generated successfully [<file>]` (`integ/ReportHelper.java:30`) **before** the Jira attach, then `Build Successfully` (`Main.java:55`).
- `Build Failed: …` is thrown for a bad VCS value or a missing `setprod` (`Main.java:53`, `integ/GitClient.java:97`).

### 3.14 `DeployTestDriver` / `TestResult` (options and the report writer read; the Selenium logic was not read)

- The percent is `pass*100/(pass+fail+timeout)`, truncated (`TestResult.java:136-140`). `fail` and `timeout` are **not reset** between calls of `getChildPassInfo()`, which is called from both `toString` and the HTML writer. Double-counting can only lower the percent, so there is no false 100%.
- No children gives `<h5></h5>`, which fails.

---

## 4. opscommon: how deployconf is parsed (`ConfHelper` 1211 lines, read fully; `StyleguideConf` 67 lines, read fully)

**Source exists.** `OC/src/main/java/com/atypon/ops/common/confutils/ConfHelper.java` and `StyleguideConf.java`. This **closes the gap recorded in notes 06:22, 06:706, 15:27 and 15:275**. There is no `DeployConfHelper` class in any repo; note 11:363 means `DeployConfUtils.getConfHelper`.
- DS builds a **fresh `ConfHelper` on every call** (`DS/.../DeployConfUtils.java:410-417`: `new ConfHelper(Utils.getConfigFile("deployconf.<acct>.xml"))`, parsed with JAXB).
- **`getProduct(name, family)`** (`:335-346`) is the basis of almost every lookup.
  - It returns the **first `<product>` in document order** whose `name` **equals (case-sensitive)** and whose family equals, or where the family is empty.
  - It **does not skip `enabled="false"`**. `ServerInstance`, `getProductWebPortMap`, `getFamilyProductHostMap` and `getFamilyProductDatabase` do skip disabled products, so the two paths can disagree.
- **`getFamilyForProduct(p)`** (`:326-333`) is `getProduct(p, null).getDeployfamily()`: the **first** family in the file for that name, disabled or not. It returns null if the product is absent.
  - DS uses it for the staging family (`SshExecuteVisitor.java:1324`, `DeployServiceImpl.java:2460`, `CipHelper.java:138`, `PreExecuteVisitor.java:318,432,765,1490,2682`).
- **`getGaia(p,f)`** (`:498-510`) returns the product's first `<gaia>` child element, or null.
  - `Gaia` (`OC/.../deployconf/Gaia.java:62-160`) has attributes `cpu`, `memory`, `service_cluster`, `storage_size`, **`bundle_version`**, plus children `<cluster name k8s_cluster image_tag>`.
  - `getBundleVersion()` is the raw `bundle_version` attribute string, or null if it is absent.
- **`isGaiaConfigured`** (`:558-561`) is simply `getGaia != null`.
- **`getGaiaImageTag(p,f)`** (`:1199-1210`) takes the product's `<gaia service_cluster=X>`, then finds the first top-level `<gaia><cluster name=X>` and returns its **`image_tag`**. It **NPEs if the product has no `<gaia>`**, and returns null if no cluster name matches.
  - This settles the note 15:100 guess: the tag is the service cluster's `image_tag`.
- **`isPreProd(p,f)`** (`:396-402`) is `Product.isPreProd()`: the `pre-prod` attribute, default false (`Product.java:128-129,311-316`). A missing product gives false. `isOnGit` is the `git` attribute, likewise.
- **`getStyleguide(p,f)`** delegates to `StyleguideConf.getInstance`: the first product matching name and family **case-insensitively** (a null family means any, `:41-56`), then its first `<styleguide>`.
  - It returns `branch = version`, `group`, and **either** `pugrendererCluster` **or** `nodeVersion`: if `pugrenderer_cluster` is set, `nodeVersion` is dropped (`:30-38`).
  - It does not skip disabled products.
- Other traps:
  - `getChild()` (`:279-286`) has an `&&` that should be `||`, so an empty list gives an IndexOutOfBoundsException.
  - `getProductBranch`, `isK8sPugrendererConfigured` and `getProductsVolums` NPE on an unknown product (`:1100-1151`).
  - `getDefaultCassandraCluster` NPEs or throws IOOBE when there is no `<cassandra>` element (`:1132-1135`).
  - `getProductTier` reads the `product-tier` element (`:1081-1098`).
- **DS consequence (CheckGaiaVersion, `SshExecuteVisitor.java:1316-1330`):** if the product is not in staging, `getFamilyForProduct` returns null. If staging then has no `<gaia>` for it, DS logs `Gaia is not configured on Staging` and **still calls `getGaia(...).getBundleVersion()`, which NPEs**.

---

## 5. Verdicts on the note 12 claims

| Claim (note 12 §1.6) | Verdict | Evidence |
|---|---|---|
| serverup expects an empty string and passes on any fetch | **Partly true.** The expected string is empty, so the **body is ignored**: `0`, `1` (DB down or not yet unlocked), or empty all pass. But the fetch must be **HTTP 200 with an entity**. A non-200 status, a refused connection or a >3 s timeout fails. | `DeployFamilyAction.java:111,138-143`; `UrlFetch.java:53` |
| opstool ignores `-p`, so HostUnlock unlocks every product of the family on the host | **Confirmed**, with two additions. (a) The product is null whether or not `-p` is passed. (b) It stops at the **first** failing product, so later products stay locked and the action fails. "Every product" means every enabled product of that family whose `<machine>` is this host in the host's `~/deployconf.xml`, one instance each (web preferred). | `DeployFamilyAction.java:53-58,70,86-107`; `ServerInstance.java:129-131,211` |
| Does a Tomcat 404 count as success? | **No.** Only 200 passes. A 404 (context not deployed) gives `success=false` and ServerUp returns false, so the log shows `RESULT:FAILURE` and the action is rescheduled until timeout. A redirect that lands on a 200 would pass (HttpClient default; Unverified). | `UrlFetch.java:53`; `DeployFamilyAction.java:138-140` |
| (note 12:8) "UrlFetch … not found anywhere locally" | **Refuted.** It is in opscommon. | `OC/.../utils/UrlFetch.java` |
| HostWaitForHearbeat = opstool `-t lock`, body starts with `Locked` | **Confirmed.** Worth adding: this action **locks** the node (`unlocked=false`); it does not wait for the heartbeat. | `S:88-90`; `DeployFamilyAction.java:111`; `HeartBeatServlet.java:383-395` |

## 6. False-success list (Success reported, but the thing is not done or not healthy)

1. **HostWaitForWebServer passes while the webapp is unhealthy.** Any 200 from `/heartbeat?bg=1` passes, including `1` (DB unreachable, not released). The unused `Heartbeat` action (expects `0`) would be the real check. `DeployFamilyAction.java:111`.
2. **Vacuous `RESULT:SUCCESS`** when no instance matches. Causes: the family is not on this host in the host's `~/deployconf.xml` (stale local copy), a short hostname different from the `<machine name>`, or the product disabled. This affects ServerUp, Unlock and Lock. Triage marker: `RESULT:SUCCESS` with **no** `DeployFamilyAction.<Action> for …` line. `DeployFamilyAction.java:51-60,83-89`.
3. **Cross-product coupling** (a false *failure*): the per-product HostWaitForWebServer and HostUnlock check the **whole family on the host**. A broken sibling product fails or blocks this product's action, and the first failure stops later products from being unlocked.
4. **HostLock is always Success** (no validator), even when the output is `RESULT:FAILURE`. And Lock can never "FailSkip": the NPE turns it into a failure. `X:1462-1466`; `DeployFamilyAction.java:124-133`.
5. **ChangeGaiaVersion**: no validator. The `git commit`/`git push` run in `~/apps64/opstool`, because `$util.opsTool` does `cd ~/apps64/opstool;` and the template never `cd`s to `~/.litconfig`. The deployconf edit is therefore never committed or pushed, and the action is still Success. An exception from the last-attribute `bundle_version` bug is also Success. `X:2762-2768`; `ActionHelper.java:38`; `ChangeGaiaVersion.java:44,58`.
6. **ProductChangeBranch / ConfigEditBranches / CloneProductBranch**: a missing product or `<source>` throws `java.lang.Exception: Product node … doesn't exist`, which contains no `error: ` or `fatal: `. git then reports nothing to commit, and the action is **Success** (and ProductChangeBranch fires ConfigRefreshDeploy). A `-s` against a missing `<styleguide><version>` is silently a no-op. `ChangeProductBranch.java:99-109,141`; `SshExecutedVisitor.java:859-872`.
7. **CloneProductBranch writes the SVN-style path** because it passes no `-g`: `$HOME/source/<b>/atypon`, even for git products. `X:1544`; `ChangeProductBranch.java:113-117`.
8. **DbProductBackupOrig**: per-table backup or restore failures are swallowed and `SchemaToolRunCompleted` still prints. With up to 4 SchemaCli runs plus AwsS3Put in one log, one completion line passes even if the S3 upload printed `FAILURE`. `SchemaTool.java:164-167,342-345`; `AwsS3.java:224-242`.
9. **AwsS3Put/Get always exit 0**, so PT `$?` checks never fire (`buildStyleguide.sh:176-180`). That block's `return $?` also returns the `echo`'s 0. `functions.sh:1774` does not check at all and goes straight to gunzip. A `get` into a same-size existing file skips the download.
10. **DbIdxReportsCollector**: worker-thread exceptions and Jira-attach errors are swallowed, and it still prints `Finished successfully`. `DbIdxCollector.java:103-110,128-130,182-184`.
11. **ProductCleanupPostClone**: Success needs any `ExecSQL SUCCESS` and no literal `java.sql.SQLException`. Postgres and MSSQL driver exceptions print their own class names, and `ExecSQL FAILURE` is not checked. So one good pre-SQL plus a failed truncate or post-SQL is still Success (driver class names inferred). `SshExecutedVisitor.java:665-682`.
12. **All Rundeck-backed actions**: RundeckApiService exits 0 on a refused start or a non-retryable log-API error, and never reads the job status. The pass text comes from the job. A job whose shell echoes its marker unconditionally would pass (job source not available; Unverified). `RundeckApiService.java:83-92,148-158`.
13. **RevisionReporter**: `Report generated successfully ` prints before the Jira attach, and svn success followed by git `Build Failed:` stays Success (the loop `break`s but keeps the earlier status). `SshExecutedVisitor.java:1075-1096`.
14. **ToolCheckBackstageStuck, HostWarmupContent**: always Success by design, whatever the opstool output.

## 7. Coverage

- **Read fully:** `DeployFamilyAction`, `RundeckApiService`, `ChangeProductBranch`, `ChangeGaiaVersion`, `AwsS3Put`, `AwsS3Get`, `AwsS3` (except the filtered credential lines), `SchemaCli`, `ExecSqlCli`, `CheckBackstageStuck`, `SvnSyncBranches` (except the filtered lines), `DbIdxCollector`, `DbIdxCli`, `revision_reporters/Main`.
  - opscommon: `UrlFetch`, `ServerInstance`, `ConfHelper`, `StyleguideConf`, `literatum/DeployConf`, `deployconf/Gaia`.
  - DS: `CompletedActionValidator`; `SshExecuteVisitor` 55-110, 500-720, 940-1095, 1310-1330; `SshExecutedVisitor` 545-690, 855-881, 946-956, 1075-1096.
- **Sampled** (sections, outputs, options, catch blocks): `SchemaTool` (restore and backup), `TruncateTableCli` (prints and catches), `HitUrlsCli` (options and prints), `NonVisualRegressionTest` (options and prints), `DeployTestDriver` (options and prints), `TestResult` (percent and HTML header), `ReportHelper` (`:15-40`), `DbUtils.executeUpdate`/`UpdateStat`, `Product.java` (the pre-prod, git and enabled getters), `HeartBeatServlet` dispatch and lock/unlock (lit-2610), PT `getStyleguide.py` and `commandutil.runCommand`. `getStyleguide.py main()` never calls `pullSG()`, so it never downloads.
- **Not read:** `JaneTestDriver`, `UptimeCheck`, `SqlCli`, `FkIndexCli`, `JMapCli`, `JStackCli`, the `DbIdxFinder`/`DbIdxReportGenerator` internals, `GitClient`/`SvnClient`, the rest of `SchemaTool`, and the Selenium test classes.
- **Not available:** the Rundeck job definitions that emit the `… execution success` / `COMPLETED SUCCESS` markers, the producer of `pass completely` for NonVisualRegressionTest, and the pinned opscommon 3.0.24/3.0.29 jars (master was read).
