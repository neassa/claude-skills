# 02 — platform-tools (`~/scripts` on hosts) as driven by the Deploy Server

Scope: `$LIT_REPOS/platform-tools` (≈1544 files / ≈260k lines), read-only. Only the files the Deploy Server (DS) actually reaches are read; the rest is inventoried.
Method: DS entry points taken from `deployserver/config/actions.xml` and `deployserver/src/.../server/visitor/SshExecuteVisitor.java`, then followed through aliases, `source`, python imports and script calls.
Secrets: never reproduced. Wherever one exists it is written as `<secret at file:line>`. After the "no secret reading" rule arrived, files were read through a filter that masks credential-bearing lines.

Citation convention: `file:line` is relative to `platform-tools/` unless prefixed `DS:` (= `deployserver/src/com/atypon/deployserver/server/`) or `actions.xml:` (= `deployserver/config/actions.xml`).

---

## 0. How the DS talks to these scripts (frames everything below)

- **One interactive shell per action.** The DS opens a JSch `"shell"` channel (DS:`connect/JSchConnector.java:131-132`) and types commands one line at a time. For each line it waits until the output ends with `)<account>]` (DS:`connect/JschConnection.java:62-132`, prompt string at :81). A command's "end" is therefore prompt detection, not process exit.
  - That prompt is **not** what `bashrc/security/bashrc:252` sets: its PS1 ends `\n[\w]>`. Host bashrcs must differ. Unverified here.
- **Aliases and functions come from the login bashrc.** `bashrc/security/bashrc:254-256` sources `functions.sh`, `aliases.sh` and `jira_funcs`. So `setprod`, `rstrt`, `rdply`, `run`, `pwdir` and `gomule` are shell functions or aliases, not files.
  - `rstrt` = `restart.py` (`aliases.sh:300`); `rdply` = `redeploy.py` (`aliases.sh:302`); `rbld` = `rebuild.py` (`aliases.sh:299`).
  - `bashrc:7` (`[ -z "$PS1" ] && return`) means any **non-interactive** script that sources `~/.bashrc` gets nothing from it. `sync_branches.sh:3` and `checkMountPoint.sh:2` re-source `functions.sh` and `aliases.sh` explicitly for that reason.
- **Exit codes are never consulted.** Success is decided later by substring search over the whole captured action log:
  - actions.xml actions: `<validate-txt>` means "any line contains X" (DS:`actions/ValidateResponseTxt.java:19-31`, `actions/ActionSpec.java:26-44`, `DeployDaemonHelper.java:519-525`).
  - visitor actions: hard-coded strings in DS:`visitor/SshExecutedVisitor.java`.
  - Consequences: a script's exit status matters only when the DS line itself chains with `&&` (only ProductBuild does: `actions.xml:1626`). Any matching text anywhere in the log, including from an earlier command in the same session, counts as success.
- **Retries:**
  - SSH connect is retried 5 times, 5 s apart (DS:`connect/AbstractConnector.java:193-236`).
  - A failed action is rescheduled once (`repeatCount==0`) only if the parser set `reschedule` (DS:`DeployDaemonHelper.java:537-541`).
  - ProductPatch sets `reschedule` on the text `restart build`, or on `Unable to delete file` together with `DbAntPatcher.class` (DS:`visitor/SshExecutedVisitor.java:459-464`).

| DS action | Exact command(s) sent | Success test | Where |
|---|---|---|---|
| ProductBuild | `setprod P F` → (git) `git config …; export GIT_PAGER=cat TERM=dumb; sync_branches.sh` / (svn) opstool `SvnSyncBranches` + `. ~/source/sync_svn_branches.sh` → `[[ $? == 0 ]] && rebuild.py [-M] -rbsw -p P -f F --triggeredby U [--jira-ticket-id T]` | any line contains `BUILD SUCCESSFUL` | actions.xml:1603-1629 |
| ProductPatch (non-docker DB) | `setprod P F` → (staging only) `pwdir; rm -f rep*` → `patch.py -p P [--families F] [--allowdropcolumn] [--gradle] --triggeredby U --jira-ticket-id T` | `verifyBuildSuccessful` (see §4.6) | DS:`visitor/SshExecuteVisitor.java:430-470`; DS:`visitor/SshExecutedVisitor.java:404-513` |
| ProductPatch (docker DB) | `ansible-actions -s mssql -n P-F -a start-patch-backup [-e backup_from=…]` (alias `aliases.sh:326`, not in this repo) | `failed=0`; fails on `SSH Error` | DS:`visitor/SshExecuteVisitor.java:458-465`, `SshExecutedVisitor.java:415-430` |
| ProductDBUpgrade | `setprod P F; patch.py -p P --families F -u <mainBranch> --gradle` | any line contains `Patch complete.` | actions.xml:899-905 |
| HostStop | `setprod P F; rstrt -w\|-R\|-b\|-o [-M -q] -q --triggeredby U --jira-ticket-id T` (plain `rstrt …` on cip) | `stopped -server` \| `killing pid` \| `do nothing` \| `Stopping process backoffice` \| (backstage/backoffice type and `Restart:`) | DS:`visitor/SshExecuteVisitor.java:105-133`; DS:`visitor/SshExecutedVisitor.java:77-100` |
| HostDeploy | `setprod P F; rdply -n --no-styleguide -f F --triggeredby U --jira-ticket-id T` | contains `Finished deploying product` and does not contain `Java Result:` | DS:`visitor/SshExecuteVisitor.java:404-408`; DS:`visitor/SshExecutedVisitor.java:391-401` |
| HostStart | `setprod P F; rstrt -s; rstrt -r -w\|-R\|-b\|-r -o\|-r -M […-g -P port] --triggeredby …; rstrt -s` | first line with `err.DeployErr` (fail) or `process is running` (success); cip backstage/backoffice: `BackstageQserverMode`/`Backoffice` + `is running` | DS:`visitor/SshExecuteVisitor.java:135-177`; DS:`visitor/SshExecutedVisitor.java:117-143` |
| HostDeployStyleguide | `setprod P F; ~/scripts/deployStyleguide.py` | `Finished styleguide deployment` | actions.xml:2005-2011 |
| ProductBuildStyleguide | `cd ~/scripts; Build-Deploy-Styleguide.sh -p P -f F -b BR -a ACCT [-g GROUP]` | `BUILD COMPLETED` | actions.xml:2013-2025 |

---

## 1. Coverage

### 1.1 Transitive set reached from the DS deploy chain

Legend:
- **R** = read fully, line by line, by me.
- **R(s)** = read fully by a sub-agent (a fork of me with the same rules). I use its findings with its citations.
- **P** = partially read, reason given.

Core chain:

| File | Lines | Status | Reached from |
|---|---:|---|---|
| bashrc/security/bashrc | 267 | R | login shell of every DS session |
| functions.sh | 2227 | R | bashrc:254; `setprod`, `run`, `rkill`, `checkoutGitRepo*` |
| aliases.sh | 350 | R | bashrc:255; functions.sh:850 |
| sync_branches.sh | 113 | R (lines 37, 66 are `<secret at sync_branches.sh:37>`, `<secret at sync_branches.sh:66>`) | ProductBuild |
| rebuild.py | 1488 | R | ProductBuild |
| patch.py | 537 | R | ProductPatch, ProductDBUpgrade |
| redeploy.py | 1841 | R | HostDeploy |
| restart.py | 2453 | R (secret-bearing lines 1379-1380, 1542, 2028, 2037, 2194 masked; 226 has the default keystore storepass → `<secret at restart.py:226>`) | HostStop, HostStart, redeploy, rebuild, patch |
| deploy.py | 1065 | R | base class of all the above |
| deployconf.py | 2244 | R (the long JVM-flag regex lists 1350-1520 skimmed; they are data) | all |
| env.py | 1277 | R (credential getters masked) | setprod via `get_env_variable` |
| product.py | 751 | R | all |
| commandutil.py | 220 | R | all |
| shmux.py | 169 | R | imported; only cluster options use it |
| process.py | 225 | R | restart |
| tags.py | 134 | R | all |
| filelock.py | 120 | R | rebuild lock |
| temputil.py | 20 | R | /var/tmp output files |
| err.py / debug.py / log.py / resinversion.py / xmlutil.py | 9 / 17 / 15 / 10 / 59 | R | all |
| literatumDeploymentStatisticUtil.py | 158 | R | rebuild, patch, redeploy, restart, styleguide |
| backstage.wrapper.sh | 292 | R | restart (-b/-R/-o) |
| rbackstage.wrapper.sh / backoffice.wrapper.sh | 2 / 2 | R | restart |
| vpenv_quiet.sh | 110 | R | backstage.wrapper.sh:6 |
| checkMountPoint.sh | 119 | R | restart start (`restart.py:1731`) |
| downloadJDK.sh | 62 | R | `deploy.py:649` when a JDK is missing |
| operations/tools/gradle_tool/run_gradle.sh | 267 | R | patch.py (gradle), several actions |
| operations/tools/gradle_tool/{gradle.properties,settings.gradle} | 14 / 7 | R | run_gradle.sh (non-patch) |
| operations/tools/build.gradle | 150 | R | `run_gradle.sh patch` (cd at `run_gradle.sh:226,242`) |
| operations/tools/{settings.gradle,gradle.properties} | 7 / 14 | R | same |
| operations/tools/src/main/java/com/atypon/modules/build/gradle/DbGradlePatcher.java | 109 | R | build.gradle:85 |
| …/gradle/PatchCompletionChecker.java | 65 | R | never invoked by build.gradle |
| operations/tools/patch.xml | 98 | R | `patch.py --ant` only (DS never passes `--ant`) |
| operations/tools/run.sh | 235 | R(s) | `run tool …` (functions.sh:1690-1717), `patch.py --ant`, rebuild Ant path |
| …/ant/DbAntPatcher.java / …/ant/PatchCompletionChecker.java | 218 / 52 | R(s) | Ant patch path |
| patch/common.patch.txt / master.patch.txt / lit-2610.maint.txt / lit-2610.maint.patch.txt | 2614 / 76 / 2663 / 79 | R(s); diff headers checked by me | rebuild.py:688-706 |
| docs/*.man (rebuild 124, redeploy 126, restart 165, patch 134, deploy 91, env 92, list 115, logwatch 92, cluster 12, clusteroptions 11, etcglobaloptions 6, prodfamilyoptions 15, litconf 22, rcmd 25, resindeployconf 29) + docs/{deploy,rebuild,restart,README,DESIGN.TXT} | ~1060 | R(s) for rebuild/redeploy/restart/patch/deploy + includes; others line-count only | `-h` of each script |

Redeploy/restart helper modules (all R(s)):

| File | Lines |
|---|---:|
| resindeployconf.py | 885 |
| tomcatdeployconf.py | 248 |
| solrcloud.py | 248 |
| solrcloudstandalone.py | 349 |
| zookeeper.py | 427 |
| zkcluster.py | 111 |
| zkserver.py | 238 |
| zkkeys.py | 21 |
| idutil.py | 281 |
| metaproxy.py | 442 |
| releaseTracker.py | 263 |
| sanitytest.py | 200 |
| twisted_mail.py | 78 |
| deployPropsDeployconf.py | 254 |
| predeploy.py | 22 |
| postdeploy.py | 48 |
| redeploy_weblogic.py | 192 |
| chkduplicate.py | 309 |
| componentVersionsUtil.py | 78 |
| opsaction.py | 97 |
| otel_agent.py | 81 |
| nr_agent.py | 177 |
| agents/pyroscope_agent.py | 35 |
| kafka/zknodesinfo.py | 52 |

Not read and reached one hop further: `agents/agent_installer.py`, `kafka/clusterconf.py`.

Styleguide chain:

| File | Lines | Status |
|---|---:|---|
| Build-Deploy-Styleguide.sh | 953 | R(s); `<secret at Build-Deploy-Styleguide.sh:864-872>` |
| deployStyleguide.py | 302 | R(s) |
| deployStyleguideNew.py | 241 | R(s) |
| jenkins/styleguide/operations.sh | 23 | R(s) |
| gitBranchCheck.sh | 49 | R(s) |
| jira_funcs | 879 | P: function structure only; `<secret at jira_funcs:56>` |

`platform-tools/deployserver/*` (all R(s)):

| File | Lines |
|---|---:|
| action_stuck_monitor.sh | 49 |
| clean_disk.sh | 4 |
| gitMerge.sh | 38 |
| run-cli.sh | 17 |
| syncconf.sh | 6 |
| updateTestToolRepo.sh | 36 |
| uptimecheck.sh | 5 |
| user_permission_report_compress_upload_jira.sh | 54 |
| test/buildTestTool.sh | 25 |
| test/updateTestToolRepo.sh | 37 (`<secret at deployserver/test/updateTestToolRepo.sh:16,25,33>`) |

Total for the files above: ≈31.9k lines.

Transitive libraries outside platform-tools, read only to explain behaviour:
- `literatum/atypon/literatum/src/java/com/atypon/literatum/util/db/patch/DbPatchSystem.java:100-200,770-930`
- `…/JDBCPatchExecutor.java:60-130`
- `…/literatum/Main.java:441-450`

### 1.2 DS-invoked but NOT read (outside the build/patch/deploy/restart/styleguide chain)

actions.xml calls about 90 other platform-tools scripts. The sub-agent tabulated them and checked each one exists; none was read. Examples:
- `reinitializeConnPool.sh`, `rsyncContent.sh`, `Cip*.sh`, `do_dbflexclone.sh`, `do_clone.sh`
- `alertManagerSilencer.py`, `autoRestartToggleSwitch.sh`, `hbs_detector.sh`, `enable_argo_tunnel.sh`, `installSamlData.sh`
- `reprocess/*`, `host_test.py`, `backstage.sh`, `major_upgrade_post_actions.sh`, `cms/handle_cms_*.sh`, `developer_database/*`

**Missing from the repo but called by DS with a `~/scripts/` path:**
- `deployserver/checkSqlPatchStatement.sh` [SqlPatchCheck]
- `styleguide/styleGuideUpdate.sh` [StyleguideTemplateUpdate]
- `packageStyleguide.py` [GenerateStyleguidePackage]

These fail with "command not found" unless the host's `~/scripts` differs from this checkout.

### 1.3 Rest of the repo (inventory only, not read)

- **Top level:** ≈555 files (293 `.sh`, 149 `.py`), a flat `~/scripts` namespace on `PATH` (`bashrc:118`). Contents: ops one-offs, CIP lifecycle, DB clone/flexclone, alert/silencer/pingdom/catchpoint/cloudflare tools, SAML, the styleguide builders, and the deploy core above.
- **`operations/`** (360 files): `tools/` holds the Ant/Gradle tool runners, `tool.xml` (107 KB), `patch.xml`, Java utilities, zips and target. Also `cron/`, `monitoring/`, `jmeter/`.
- **Large migration/data dirs:** `patchplan/` (major-upgrade patch plans, ~19k lines), `atm/` (~14k), `marlin_migration_scripts/` (~12k), `lancet_migration_scripts/`, `unicode_migration/`, `santaclara/`.
- **Dev/support tooling:** `developer_database/`, `reprocess/`, `grafana_api/`, `elasticsearch/`, `newrelic_scripts/`, `pdfplus/`, `latex/`.
- **Config, templates and binaries:**
  - `conf/`: Tanuki wrapper confs and systemd units
  - `tomcattemplates/`, `resintemplates/`, `weblogic/`
  - `wrapper/`: native Tanuki binaries
  - `lib/`, `lib32/`, `saxon/`, `lexers/`, `cacerts/`
  - `gradle_wrapper/`: the `gradlew` used by run_gradle.sh
- **Small dirs:** `agents/`, `analytics_events/`, `aws/`, `bashrc/`, `docker/`, `gitbot/`, `insightsops/`, `jenkins/`, `kafka/`, `cms/`, `styleguide/`, `solr/`, `unittest/`, and others.

---

## 2. Entry points: options used, control flow, calls, files, strings, exits

### 2.1 `setprod P F` (functions.sh:429-869)

- **Options the DS uses:** positional `P F`. Two args mean product and family (`functions.sh:540-552`).
- **Flow:**
  - `unsetprod` (:440 → :1548-1614) wipes about 50 variables and re-sources aliases.
  - It prints a local-machine banner when not on a `dev*` host and `LOCAL_BASE` is unset (:444-467).
  - It then calls `env.py -p P -f F --getXxx` once per variable through `get_env_variable2` → `get_env_variable` (:1251-1322). Each result is wrapped in `<r>…</r>` (`env.py:892-895`) and parsed with sed (:1324-1374).
  - For git products it rewrites `ATYPON_HOME` to `~/sourcegit/literatum-worktrees/<branch|master>/atypon` (:604-612).
  - Everything is exported (:702-728). Styleguide, solr, kafka, redis and cassandra ports come from `xmllint` on `~/deployconf.xml` (:744-791).
  - `setJavaHomeAndAppServer` (:326-416) picks the JDK:
    - `java21` for master/HEAD/trunk/≥2610
    - `java17` for ≥2410
    - `java11` for ≤2210 (and anything not matched below)
    - `java8` for ≤2010
    - It forces `APPSERVER_TYPE=tomcat` for ≥2210 when deployconf doesn't say, and copies the JDK into the deploy dir on `LOCAL_BASE` hosts (:387-401).
  - Finally it re-sources `aliases.sh` (:850).
- **External calls:** `env.py` (each call re-parses deployconf), `xmllint`, `curl` (inventory API, only with `--source-env`: :523-529, :760-761).
- **Failure strings:** `ERROR running command …, cmd failed` / `…, no result` / `ERROR parsing result from raw env.py script output` (:1298-1315). `env.py` errors include `Nothing found for: P/F`, `You must specify a deploy family…` (`env.py:961,988-994`), and `===> No product found with name %s designated to run on this machine <===` (`env.py:920-922`).
- **Exit/return:** `return 1` on error. **Silent path:** the DS keeps typing the next command anyway (§0). A failed `setprod` leaves an *unset* environment, because `unsetprod` ran first. The next script then fails with its own env error, for example `deploy.py:302-305` "Have you run setprod yet?".

### 2.2 `sync_branches.sh` (ProductBuild, git products)

- **Flow:**
  - Sources `.bash_profile`, `.bashrc` (a no-op, §0), `functions.sh` and `aliases.sh` (:2-5).
  - Requires `ATYPON_HOME` (:11-14). `litBranch=basename(dirname ATYPON_HOME)` (:17). The patch branch is `master` for `lit-NNNN` and `master`, otherwise the same name (:20-24).
  - If there is no worktree: clone literatum master with an embedded credential (`<secret at sync_branches.sh:37>`), then `git worktree add ../<b> <b>` (:28-48).
  - `cd ATYPON_HOME; git reset --hard HEAD && git pull || exit 1` (:51-52).
  - If `$ATYPON_HOME/patch` is not a symlink: clone literatum-patch (`<secret at sync_branches.sh:66>`), add a worktree for the patch branch, and symlink it as `$ATYPON_HOME/patch` (:55-100). A missing patch branch prints `Branch $patchBranch doesn't exist in patch repo` and exits 1 (:93-94).
  - Then `cd $ATYPON_HOME/patch; git reset --hard HEAD && git pull || exit 1` (:104-107). Strings: `Patch updated successfully` (:107); `ERROR: Patch directory is not a valid git repository` exits 1 (:109-112).
- **Exit codes matter here:** actions.xml:1626 runs `[[ $? == 0 ]] && rebuild.py …`.
- **Unchecked:** `git worktree add` failures inside the "not checked out" block, `git pull` at :44 and :75, and `mkdir`.
- **Side effect:** `git reset --hard HEAD` reverts any source patch the previous rebuild left in the tree (see §3.3).

### 2.3 `rebuild.py -rbsw -p P -f F --triggeredby U [--jira-ticket-id T]` (details in §3)

- **Options as parsed by the code:**
  - `-r` sets `IS_REFRESH_CVS` (`rebuild.py:1145`).
  - `-b` sets `IS_BATCH_BUILD` (:1153).
  - `-s` sets `IS_CLEAN_SOURCES` (:1151).
  - `-w` sets `IS_BUILD_WAR` (:1157).
  - `-p` and `-f` are global options (`deploy.py:113-127`). `-f` is regex-matched with `^F$` against declared families (`deploy.py:362-382`).
  - `--triggeredby` and `--jira-ticket-id` only feed LDS statistics (:1211-1214).
- **`-M`** (readonly/rorehearsal, actions.xml:1611): `M` is in the short-option string (:1127), but there is no handler. It prints `unknown option: -M` (:1220) and does nothing.

### 2.4 `patch.py -p P [--families F] [--allowdropcolumn] [--gradle] …` (details in §4)

### 2.5 `redeploy.py -n --no-styleguide -f F …` (details in §5.1)

- **`-n`** sets `IS_NO_RESTARTS`, which skips `stopProcesses` and `startProcesses` (`redeploy.py:1152-1153,673-701`).
- **`--no-styleguide`** only sets `EXCLUDE_STYLEGUIDE`. That flag is used only in the mutual-exclusion check (:1168-1169, :1184-1186), so it is effectively a no-op.
- **`-f F` without `-p`:** `Deploy.autoSelectAllProds` turns on `IS_ALL_PRODUCTS` whenever families are given without products (`deploy.py:291-297`). `rdply -f F` therefore redeploys **every product of family F declared on this host**, not just `$PRODUCT_NAME`. It also removes deploy dirs of family products *not* declared on this host (`redeploy.py:93-105`, "removing residue").
- `-r` for rollback is tested (:1160) but `r` is not in the short options `"nhvtSusPL:"` (:1138); only `--rollback` works.

### 2.6 `restart.py` (`rstrt`) as used by the DS (details in §5.2)

- `-w` adds the `web` and `metaproxy` processes (`restart.py:793-796`). `-b` adds backstage, `-R` rbackstage, `-o` backoffice (:797-808).
- `-q` sets `IS_STOP` (:785). `-s` sets `IS_STATUS` (:809). `-r` sets `IS_START_DEAD` (:824). `-g` sets `IS_DEBUGGER` (:842). `-P` sets `DEBUGGER_PORT` (:856).
- `--generate-dependency-conflict-analysis-reports` is used for cip qaa (DS:`visitor/SshExecuteVisitor.java:152-158`; `restart.py:836-837`).
- **`-M`** (mdcdaemon, DS:`visitor/SshExecuteVisitor.java:125-127,148-149`): `M` is in the short options (:761) but has no handler. It prints `unknown option given to restart.py: -M` (:870). `procs2start` stays empty, so **all processes of the product on the host** are stopped or started (the filter at :281-286 is skipped).
- The constructor always prints `Restart: <datetime>` (:110) and runs a JCE check through `jrunscript`. If the max AES key length is 128 it exits with `ERROR : Java Cryptography Extension is NOT installed…` (:112-118).

### 2.7 `run tool …` / `run_gradle.sh main …` (misc. actions)

- `run` (`functions.sh:1690-1717`) = `pushd ~/scripts/operations/tools; ./run.sh "$@"`, and returns run.sh's exit code.
- `run.sh`: env errors print and do a bare `exit`, which is **0** (run.sh:26,58,65,72,94). Otherwise it runs Ant through `java -Xms8G -Xmx32G … org.apache.tools.ant.launch.Launcher -buildfile tool.xml|patch.xml …` and returns Ant's exit code (run.sh:208-235, per sub-agent).
- `run_gradle.sh`: the same env checks with a bare `exit` (0) (:21-95). `patch` runs from `operations/tools/` (:225-247); everything else runs from `gradle_tool/` (:248-266). **It always exits 0**, see §4.3.

### 2.8 Styleguide (details in §6)

---

## 3. rebuild.py in depth

### 3.1 Control flow for `-rbsw -p P -f F`

1. `Deploy.__init__` → `staticEnvSanityCheck`, which needs `HOST_NAME` (`deploy.py:349-354`), then `DeployConf()`, which raises `Error, ~/deployconf.xml not found` if it is missing (`deployconf.py:51-60`).
2. Options (`rebuild.py:1124-1221`). `IS_CIP_SITE` is set when deployconf has `/literatum/macro/cip-domain` (:1222, `deployconf.py:62-68`). Build metrics are forced off (LIT-657774) (:1228).
3. `getoptPostProcessing` (`deploy.py:267-289`), then `rebuildLocal` → `rebuildProducts([P], [F])` (:1083-1092).
4. With `-b`, `rebuildProducts` makes two passes per product (:127-131): `rebuildProduct(prod, clean=True, onlyClean=True)` followed by `rebuildProduct(prod, False, False)`.
5. `rebuildProduct` (:136-263):
   - If `<rebuildable>false` it prints `Warning: Product %s is set to not be rebuildable…` and returns (:146-148). **No error** is raised, so DS then fails for lack of `BUILD SUCCESSFUL`.
   - **Lock**: `FileLock("<src>/.build")` → `<src>/.build.lock` (with `--parallelbuild`: `<src>/<prod>-build.lock`), timeout **None**, meaning fail immediately (:150-169, `filelock.py:24-69`).
     - The lock file content is `"<prod> is running on <user>. "`.
     - On failure it prints `Failed due to 'Could not acquire lock on <src>/.build'` and `## see LIT-246176 ##`, then raises `DeployErr("Failed to aqcuire build-lock, another build process is running.")`.
   - `self.setprod(prod,"rebuild")` (`deploy.py:584-675`) exports PRODUCT_NAME, JOURNAL_HOME, ATYPON_HOME (= source path), APPSERVER_TYPE, DEPLOY_HOME, DEPLOY_FAMILY and `<exports>`, and picks the JDK:
     - `java21` for master/HEAD/trunk or ≥2610; `java17` for >2210; `java11` for >2010; `java8` otherwise; a deployconf `javahome/rebuild` override wins.
     - In rebuild mode `JAVA_HOME=~/apps64/<jdk>` even on DC hosts (:636-654).
     - If that JDK is missing it runs `~/scripts/downloadJDK.sh <jdk>`. That script fetches from GitHub, Azul or Corretto and supports only java11, java17 and java17.amazon; it prints `FAILED: …` and exits 0 otherwise. `deploy.py:647-651` raises only if the output contains `FAILED`.
   - `-s` → `cleanSourceBuild` deletes the contents of `<src>/build/` (:314-340); `-c` (unused by DS) deletes `DEPLOY_HOME/webapps` (:288-312).
   - `-r` refresh (:186-243):
     - On the Gradle path: `git -C <src> pull` if the path contains `sourcegit` or `VCS==GIT`, else `svn up <src>`, run through `runGetTeeOutput`.
     - Then `git -C <src> log --format="The revision = %H" -n 1` (:236-238), or it scrapes `Updated to revision`/`At revision` for svn (:642-655).
     - With `--parallelbuild` it retries `os.system(cmd)` every 10 s **forever** until it exits 0 (:224-232).
   - Gradle or Ant (§3.2), then `incrementStateTrackers`, then `copyWarFile` (§3.4).
   - It prints `===> Finished building product <prod>-<fam>` (:259), releases the lock (:260), and prints `Releasing build-lock …` (:262).

### 3.2 Branch detection and Ant vs Gradle

- **Branch name used for patching and LDS:** `prod.getBranchRelease()` = the second-to-last component of the source path, for example `lit-2610-maint-250507-1124797`, `master`, or `HEAD` for svn `~/source/HEAD/atypon` (`product.py:325-330`).
  - The source path is `$ATYPON_HOME` when the product and family match the env, otherwise deployconf `<source>` (`product.py:315-323`). setprod's git rewrite (§2.1) therefore decides the tree.
- **Gradle vs Ant:** `runAsGradleBuild` regex-matches `lit-NNNN|head|trunk|master|apg` in the lowercased source path (`rebuild.py:265-279`). Gradle is used when the release is `apg`, `head`, `trunk`, `master`, or `release >= "1830"`. That is a **string** comparison, which is correct only while releases have 4 digits. Unmatched paths also use Gradle. `--forceantbuild` forces Ant.
- **Gradle command** (:668-804): `cd <src>`; `GRADLE_OPTS += -Dorg.gradle.logging.stacktrace=all`, then
  `./gradlew  :product:<P>:war -Dis.production.site=<LOCAL_BASE set> -Dkeep.auto.generated.props.file=false -Dis.cip.site=<…> -Dforce.create.props=<DP matrix> [-Dorg.gradle.java.home=$JAVA_HOME if a javahome override exists]` (target is `war` for apg).
  - The LIT-506053 workaround `-Drootpom.version=2300.0.17` is appended to `cmd_pattern` **after** `cmd` was already built (:777-781), so it is **never passed** (dead code).
- **Ant command** (:567-640): `cd ~/scripts/operations/tools; ./run.sh build <targets> -D…`. The targets come from `XtraTargets` (:933-1031, :1293-1460). With `-rbsw` they are `svn.update` then `war`.
- **Failure detection (both):**
  - The output is captured by `commandutil.runGetTeeOutput(cmd)`, which appends `2>&1 | tee -a /var/tmp/<epoch>.txt` and calls `os.system` (`commandutil.py:134-154`). `/bin/sh` has no `pipefail`, so **the exit status is tee's (0)**. The gradle/ant exit code is lost.
  - The only failure test is the substring `BUILD FAILED` in the output (:632, :791). If it is found, the output is written to `/var/tmp/<epoch>.txt`, the LDS failure is logged, and it raises `DeployErr("Build failed!  Output is in /var/tmp/<epoch>.txt")`.
  - A Gradle client that dies without printing `BUILD FAILED` (wrapper download failure, OOM kill, daemon crash) passes this check. It is then caught only indirectly when `copyWarFile`'s `mv` fails.

### 3.3 Build-time source patch (LIT-656000; `rebuild.py:688-706`)

- **Condition:** `LOCAL_BASE` is non-empty (DC/prod-style hosts) **and** branchRelease is `master` or starts with `lit-2610`.
- **Steps:**
  1. `git reset --hard HEAD && git clean -df --exclude=".build.lock" --exclude="*-build.lock"` in `<src>`.
     - `<src>` is the `atypon/` subdirectory of the worktree.
     - The literatum `.gitignore` lists `/atypon/patch` (checked), and the sub-agent reports `/atypon/build` too. Without `-x`, the patch symlink and the build dir survive.
     - Any other local modification or untracked file is destroyed.
  2. If the branch starts with `lit-2610-` (maint branches): `git apply ~/scripts/patch/common.patch.txt`, print `PATCH common applied OK`; then `git apply ~/scripts/patch/master.patch.txt`, print `PATCH master applied OK`.
  3. Else (`master` or exactly `lit-2610`): `git apply ~/scripts/patch/lit-2610.maint.txt`, print `PATCH for 2610 and master applied OK`.
- **The naming is inverted:** maint branches get "master.patch", and master gets "lit-2610.maint".
- `patch/lit-2610.maint.patch.txt` is **not referenced anywhere** (dead). Per the sub-agent it is the variant whose context matches the maint `performSearch(context, req)` signature.
- **Mechanics:** `commandutil.runCommand` = `os.system`, which raises `Exception("Error, the command: … failed")` on a non-zero exit (`commandutil.py:18-24`). The `~` expands under `/bin/sh`.
  - The patches use `a/atypon/...` paths. `git apply` resolves them from the worktree root and silently ignores paths outside the cwd; everything is under `atypon/`, so it applies. This is git behaviour, not verified on a host.
- **What the patches do** (sub-agent summary):
  - `common.patch.txt` and `lit-2610.maint.txt` contain the same 36-file revert "metrics from OTel back to NewRelic/Prometheus" (commit `3f50be51…`, "LIT-591953: metrics reverted to newrelic/prometheus").
  - They touch `cluster/AwaitMetricsMonitor`, `cluster/PassportClusterMetricsProvider` (replaces `clusterMetrics = null; // TODO revisit after LIT-643926` with `ClusterMetrics.INSTANCE…`), `cluster/SingletonPassportClusterProvider` (uncomments the `cluster/offline` gauges), the newrelic/prometheus metrics stack, `literatum.props.xml`, `SystemMonitorRobot`, and the node.js connection classes.
  - The two differ only in offsets and blob ids. `lit-2610.maint.txt` also contains the `BaseSemanticSearchSupplier` hunk that `master.patch.txt` carries separately (it comments out `semanticSearchMetrics.record*()`).
- **Failure is swallowed.**
  - `except Exception:` prints `LIT-656000: literatum-master patch failed, reverting...` (:704-705), runs reset and clean again (:706), and **carries on building unpatched sources**. The exception is not re-raised and LDS is not told.
  - Gradle then prints `BUILD SUCCESSFUL`, and ProductBuild is marked **Success** (actions.xml:1628).
  - The first patch may apply and the second fail; the revert makes the pair all-or-nothing.
  - If the revert command itself fails, `runCommand` raises out of `runGradleBuildScript`. That exception is unhandled: it produces a traceback and no `BUILD SUCCESSFUL`, so the DS fails.
  - This is the swallowed-failure path behind the null cluster-metrics NPE at startup (LIT-683431): the unpatched source runs with the metrics provider in its "null" state.
- **Not reverted after the build.** The patched working tree stays until the next `sync_branches.sh` (`git reset --hard HEAD`, :52). In the meantime anything reading the worktree sees patched sources, for example `patch.py` legacy mode, which reads `ATYPON_HOME/patch` only (unaffected), or a developer on a DC host.
- **Order vs refresh:** `-r` pulls first (:186-243), then the patch block runs inside `runGradleBuildScript` (:690). A manual `rebuild.py -r` on a tree still patched from the previous build (with no sync in between) runs `git pull` on a dirty tree. If upstream touched those files the pull fails, the failure is masked by tee and a bare `except:` (:242-243), and it **builds the old revision**.

### 3.4 WAR output (`copyWarFile`, :814-877)

- Runs only with `-w`. The drop dir `~/warfiles` is created if missing (:806-812).
- Steps:
  1. Delete the oldest `<P>_<F>_*.old` (one per run) (:830-834).
  2. Rename every current `<P>_<F>_*.war` to `….war.old` (:851-858).
  3. `mv -fv <src>/build/product/<P>/resin/<P>.war ~/warfiles/<P>_<F>_<YYYY-MM-DD_HHMMSS>.war` (:865-875). The path is under `resin/` even for Tomcat. With `--parallelbuild` the source is `<src>/build-<P>/…`.
- If the build left no WAR, the `mv` raises. By then the previous WAR has already been renamed `.old`, so `~/warfiles` holds no `.war` for that product, and the next HostDeploy fails with `No warfile was found for '<P>-<F>', you probably need to rebuild it…` (`redeploy.py:220-222`).
  - This happens after Gradle printed `BUILD SUCCESSFUL`, so **ProductBuild is Success while the product has no deployable WAR**.

### 3.5 Other rebuild notes

- **Stale lock.** `release()` is only called on the success path (:260). On exceptions `FileLock.__del__` (`filelock.py:97-101`) usually cleans up at interpreter exit, but a SIGKILL, or a SIGHUP when the DS SSH session drops, leaves `<src>/.build.lock` behind. The `git clean` excludes it on purpose. Every later build then fails at once with the LIT-246176 message until someone deletes the file.
- The `-b` first pass returns while still holding the lock (:180-181). It is released only by `__del__` when the local goes out of scope (CPython refcount), before the second pass tries to acquire it.
- Long-option typos: `"batchbuild" "classes"` and `"admintool" "runtarget="` are string concatenations (:1128, :1132), so `--batchbuild`, `--classes`, `--admintool` and `--runtarget` don't exist. The DS uses short `-b`.
- `deploy.py:621` calls `int(branch)` before the `branch == ""` check at :625, so a source path without a recognisable branch raises ValueError.

---

## 4. patch.py in depth

### 4.1 Which patches run

- patch.py never picks patches itself; the DS passes no `-f/--patchfile`. It builds `-D` properties (`patch.py:220-304`), and `DbPatchSystem.run()` in the literatum code on the classpath chooses.
  - `DbPatchSystem.java:110-200`: `fillPatchQueues()` loads every pending patch per DB pool from the patch root, compares with the DB version tables, and runs them.
- **Patch root** (`DbPatchSystem.java:924-929`):
  - `-Dlegacymode=True` is set when `-L` is given or the host is not a production site (no `LOCAL_BASE`) (`patch.py:277-278`). Legacy mode uses `$ATYPON_HOME/patch/`, the literatum-patch worktree symlinked by sync_branches.
  - Otherwise, on DC hosts, it uses `$DEPLOY_HOME/webapps/<P>/iapps/patch/`, the patch files **inside the currently deployed WAR**.
  - This is why the DS staging special case runs `pwdir; rm -f rep*` (DS:`visitor/SshExecuteVisitor.java:434-438`, alias `aliases.sh:17`). It deletes report-DB patch files from the deployed webapp so they aren't applied to the read-only production reports DB. That mutation persists until the next redeploy.
- **Classpath = the deployed webapp:** `$DEPLOY_HOME/webapps/<P>/WEB-INF/lib/*.jar`, plus `WEB-INF/classes`, plus `~/scripts/operations/tools/zips` (`operations/tools/build.gradle:21-27,41-44,84`). **The patch VM runs whatever is deployed, not the freshly built WAR.** Patch-before-deploy runs old code.
- `-u <release>` (ProductDBUpgrade) → `-Dupdaterelease=`, which runs `updateRelease()` → `DbReleasePatch` (`DbPatchSystem.java:141-143,627-631`).
- **`-R` release check:** without `-R` or `-u`, `DbPatchSystem.run()` compares the DB release with the build branch. On mismatch it throws `PatchProgram (<P>): DB version X doesn't equal your build version Y you can ignore this check by running patch.py with -R[, or upgrade the DB with -u]` (`DbPatchSystem.java:126-132`).
  - `-R` → `-Ddisabledbrelease=True` (`patch.py:281-282,457-458`) → `setDisableDbRelease` (`DbGradlePatcher.java:64`).
  - The long form `--disabledbrelease` never matches: it is tested as the bare string `"disabledbrelease"` (`patch.py:457`), so it falls to `unknown option`.

### 4.2 Flow of `runBuildScript` (:97-218)

1. `getDeclaredProducts(P)`. If none: `product(s) [...] not found in deployconf.xml (not defined or disabled.)` and **`sys.exit(0)`** (:109-112).
2. `filterProdsByLocalhost` keeps only products declared on this `HOST_NAME` (:114). If none remain it prints `product [...] not found on this machine` and **continues with an empty list** (:115-116). The loop is skipped, and :213 then references the unbound `literatumDeploymentStatisticUtil`, giving an UnboundLocalError traceback after printing `Patched Successfully: ` (empty).
3. **Families:**
   - `--families F` → `familieslist = ^F$` regex matches (:423-426) → `filterProdsByFamily` (:118-126).
   - Without `--families`, a product that exists in more than one family on this host prints `P found in family [...], please add '--families={family name}' to patch` and **`sys.exit(0)`** (:134-143).
   - **Multi-family** (`--families A,B` or a regex): the families are patched **sequentially**. The first failure raises (or exits with `-e`), later families are skipped, and `Patched Successfully: <earlier ones>` is printed (:190-191).
4. Per product:
   - `setprod(prod)` only on production sites (:146-147); elsewhere it relies on the shell's setprod.
   - `envSanityCheck` requires ATYPON_HOME, PRODUCT_NAME, JOURNAL_HOME and DEPLOY_HOME (`env.py:1149-1156`).
   - `overrideJdk(prod,"restart")` picks `java21` for head/trunk/master or >2410, or a deployconf `javahome/restart` (`deploy.py:555-577`). `int(branch[4:8])` crashes on names like `apg`.
5. **Gradle is the default:** when neither `--ant` nor `--gradle` is given, `USE_GRADLE=True` (:493-494). The DS never passes `--ant`, so the Ant/`patch.xml`/`PatchCompletionChecker` path is dead for the DS.
   - `cd ~/scripts/operations/tools/gradle_tool/`, then the command `run_gradle.sh patch runWithJavaExec  -Dproduct=P [-Dupdaterelease=…] [-Dallowdropcolumn=True] [-Ddisabledbrelease=True] [-Dlegacymode=True] -Dfamily=F` (:152, :171-174).
   - `run_gradle.sh` is found through `.` in PATH (`bashrc:124`), because it is invoked without `./`.
6. Output goes through `runGetTeeOutput` (exit code lost, §3.2).
7. **Failure test** (:188): the output contains `FAILED` (anywhere, case-sensitive) **or** `KILLING THE SYSTEM`. Then:
   - write `/var/tmp/<epoch>.txt` and print `Patch failed!  Output is in /var/tmp/<epoch>.txt`
   - log LDS failure
   - with `-e`: `sys.exit(-1)` (exit status 255); otherwise `raise DeployErr("Patch failed!…")` (traceback, exit 1)
8. Success: `Patched Successfully: P[,P2…]` and LDS success (:211-215).

### 4.3 Launching the patch VM (`run_gradle.sh` → `build.gradle` → `DbGradlePatcher`)

- **`run_gradle.sh patch …`:**
  - Env checks: missing JAVA_HOME, DEPLOY_HOME, DEPLOY_HOST, PRODUCT_NAME or ATYPON_HOME prints `ERROR: … not found…` and a bare `exit`, which is **0** (:21-95).
  - It builds `_JVM_ARG` (`-Datypon.home -Dappserver.type -Ddeploy.home -Ddeploy.host -Dhost.name -Ddeploy.family -Dproduct.name -Dscripts.home -Dfile.encoding`, plus `-DjvmArgs=--add-opens…` on JDK≥17, :126-164) and `cd ~/scripts/operations/tools/`.
  - It runs `~/scripts/gradle_wrapper/gradlew "$@" $_JVM_ARG --stacktrace --project-cache-dir ~/scripts/operations/tools/target/<user>/gradle/<P>/ -g ~/.gradle/` (:220-246).
- **Exit status bug (`run_gradle.sh:244-247`):** `finalcmd= eval '${cmd} "$@" …'` runs Gradle through `eval`, with an empty `finalcmd=` prefix. Then `command_exec $finalcmd` executes **nothing** and returns 0, so `_GRADLE_EXIT=$?` is always 0 and the script **always exits 0** (:268). The non-patch branch has the same bug (:262-265). `SUPPRESS_OUTPUT` is never applied to the real Gradle run.
- **`operations/tools/build.gradle`:**
  - `task initialize(){…}` has no `doLast`, so its body runs at **configuration time** on every invocation (:19-39). It deletes and recreates `target/<user>/classes/<P>`, creates `$DEPLOY_HOME/log/<P>/`, and creates `gradle.patch.<yyyy-MM-dd-HHmmss>.log`.
  - `taskCompile` compiles `src/main/java/com/atypon/modules/build/gradle` against the deployed webapp classpath (:52-64).
  - `runWithJavaExec` (JavaExec) runs main `com.atypon.modules.build.gradle.DbGradlePatcher` with cwd = target classes. stdout is teed to the log file and the console (`doFirst` :77-80); **stderr is not teed** to the file. The system properties are listed at :87-144.
  - `'host.name': System.getProperty("hmalabeh")` (:126) is always null, a developer leftover.
  - `gradle.properties` sets `org.gradle.daemon=true`, `org.gradle.parallel=true`, `org.gradle.caching=true` and `unsafe.watch-fs=true`. The daemon and `~/.gradle` are shared between concurrent patch runs for different products on one host, along with the `operations/tools/build/` dir. The per-product parts are the classes dir and project cache.
- **`DbGradlePatcher.main`** (:12-18): `init()` → `new DbPatchSystem(PrintWriter(System.out))`; `verify()` copies the properties (:33-74); `ss()` → `patcher.run()`.
  - An **Exception** → `printStackTrace` → `System.exit(1)` (:20-27) → JavaExec fails → Gradle prints `BUILD FAILED`.
  - Success → `System.exit(0)`.
  - An **Error** (for example `NoClassDefFoundError`, or the `throw new Error("Patch %s is reserved…")` at `DbPatchSystem.java:157-162`) is not caught by `catch (Exception)`. It propagates out of `main`, and the JVM stays alive while any non-daemon thread (akka, cassandra driver) is running. **The patch can hang** instead of failing. If no such thread exists, the JVM exits 1 → `BUILD FAILED`.
  - Exceptions in `verify()` also escape `main` (uncaught → exit 1).
  - `gradle/PatchCompletionChecker` (the `patch pool marker … ends. All patches applied successfully.` check) is **never invoked** on the Gradle path. Only the Ant `patch.xml:96` uses its twin (per sub-agent).

### 4.4 How failure is detected, and what the literatum strings mean

- `PatchProgram (<P>):Patch <name> failed to execute` is `JDBCPatchExecutor.java:119` (`Patch.errosMsgPrefix` = `"PatchProgram (" + product + "):"`, `Patch.java:14`). It is thrown as a RuntimeException that becomes exit 1 → `BUILD FAILED`.
- `Patch complete. tt=<n>s` is printed **after each individual JDBC patch** (`JDBCPatchExecutor.java:84-88`).
- `********** KILLING THE SYSTEM **********` is `Main.abortSystemStartup` (`literatum/Main.java:441-450`), which prints `********** ERROR LOADING PRODUCT <P> **********` and then `System.exit(1)`. It covers DB connection failures during Spring and cluster init.
- patch.py's own verdict is "`FAILED` or `KILLING THE SYSTEM` anywhere in the output". **The DS does not use patch.py's verdict** (next section).

### 4.5 `/var/tmp` output file

- During the run: `/var/tmp/<epoch.micro>.txt` is the tee target, deleted afterwards (`commandutil.py:148-153`; `temputil.py:4-20`, falling back to `/tmp`).
- On failure: another `/var/tmp/<epoch.micro>.txt` holds the full output and is **not** deleted (`patch.py:192-196`).
- The Java-side log is `$DEPLOY_HOME/log/<P>/gradle.patch.<ts>.log` (stdout only; `build.gradle:31,79`). Alias `gopatchlog` points somewhere else, the target classes dir (`aliases.sh:31`).

### 4.6 DS verdict for ProductPatch (`verifyBuildSuccessful`, DS:`visitor/SshExecutedVisitor.java:433-513`)

- It walks the log line by line, starting from Failure:
  - `BUILD FAILED` → Failure, **break**.
  - `PatchProgram … failed to execute` → remembers the 4th-from-last token as the failed patch.
  - `restart build`, or `Unable to delete file` + `DbAntPatcher.class` → reschedule.
  - A line **starting** with `BUILD ` that contains `SUCCESSFUL` → Success, **break**; any other `BUILD ` line → Failure.
- On Failure with a remembered patch name it schedules a `BrokenPatchBlame` action (:492-510).
- **Consequences:**
  - patch.py's `Patch failed!` (a `FAILED` substring without Gradle failing) is ignored if Gradle printed `BUILD SUCCESSFUL`.
  - **Multi-family:** family A's `BUILD SUCCESSFUL` comes first in the log, so the DS marks Success even if family B failed with `BUILD FAILED`.
  - ProductDBUpgrade's `validate-txt "Patch complete."` passes if **any one** patch completed, even if a later one failed. It **fails** if there was nothing to patch.

---

## 5. redeploy.py / restart.py: what "deployed" and "started" really mean

### 5.1 `rdply -n --no-styleguide -f F` (HostDeploy)

Order (`redeploy.py:1135-1222`, `78-208`, `421-447`):

1. `getoptPostProcessing`, then `checkProductsRedeployable` (it returns early because all products are auto-selected; §2.5).
2. `checkAkkaZkVersion(PRODUCT_NAME, DEPLOY_FAMILY, CVS_BRANCH)` runs `~/apps64/ansible/inventory/inventory.py product -j -n P-F | jq …` through `os.popen` (:999-1039).
   - HEAD/master/`lit-2*` need ZooKeeper ≥3.5. Otherwise it raises `Akka Zookeeper version 3.5+ (found X) is required for …`.
   - On inventory errors it prints `Skipping Akka Zookeeper version check. An inventory error has occured.` and continues.
   - A missing `CVS_BRANCH` gives a KeyError.
3. `clusterGlobalPredeployTasks` (prints only), then `redeployall([F])` → local products of F.
4. `globalPredeployTasks`:
   - `checkWarFile` raises `No warfile was found for '<P-F>'…` (:210-240).
   - `stopProcesses` is **skipped by `-n`**.
   - `backupWebapps` is not implemented (`WARN: backupWebapps() method has not been implemented yet`, :716).
   - `genResinDirs` → `SharedResinHelper.main` → **`cleanDeployDirectory`** deletes everything under `DEPLOY_HOME` except `log`, `webapps`, `resin.log`, `EdCom.dtd` and `akka` (:1760-1772).
   - `deployResin` then unzips the app-server zip into `.tmp`, rsyncs it into place, `chmod +x bin/*.sh`, creates `logs → log`, and rsyncs the Tomcat native libs (:1774-1817). For master or lit-2610 Tomcat the zip is `apache-tomcat-10.1.48.zip`, hard-coded at `deployconf.py:191-192`.
   - `genResinConfs` writes `conf/resindeploy.main.conf` (Resin) or `conf/server.xml`, `web.xml` and `context.xml` (Tomcat) (:570-671; `tomcatdeployconf.py:72,183,227`).
5. Per product, `redeployProduct` (:117-208):
   - `predeployTasks` does **`rmtree(DEPLOY_HOME/webapps/<P>)`** and deletes WAR files under DEPLOY_HOME, then `predeploy.run` (:242-267).
   - `extractWarFile`:
     - Picks the lexicographically latest `~/warfiles/<P>_<F>_*.war` (:830-868).
     - `jar -xf` through `runGetTeeOutput`. The comment says "will check exit code", but **it doesn't** (tee). A truncated or corrupt WAR or a full disk still prints `Finished extracting war file` (:875-878).
     - `bugFixes` (chmods via `os.system`, unchecked), then unzip of the ab-testing and cf-recommendations scripts via `runGetOutput`, then `copyTempSaxonLicense` (raises on failure) (:881-884).
   - Dockerized Solr: `SolrCloudStandAlone.updateSolrCloudConfiguration` runs `IS_DEPLOYMENT=true ./run.sh … updateConf` (raises on non-zero). A missing solr-core jar or ZK cluster raises (per sub-agent).
   - `Metaproxy(P).deploy()` (no-op unless configured). `ZkNodesInfo(...).writeinfo()` → `$DEPLOY_HOME/../kafka/$PRODUCT_NAME/zkNode.properties`.
   - `copyJDK` on `LOCAL_BASE` hosts does `rmtree` plus `copytree` of `~/apps64/<jdk>` → `DEPLOY_JAVA_HOME` (`deploy.py:319-336`).
   - `injectHibernate5jars` for trunk, head and 2210 only.
   - `postdeployTasks`:
     - symlinks (publisher, sandbox, webtest, covergifs, sda) through `runCommand`, which raises on failure (:1248-1506)
     - `Log4jMutator` (log4j2.xml level and product.log rename) and `postdeploy.run` (`os.system`, unchecked)
     - `DeployPropsDeployconf.deployProps` XSLTs deployconf into `WEB-INF/deployconf.props.xml`. Consul lookups that fail silently yield empty values (per sub-agent).
     - `isProdStyleguide` prints `>>> Product P uses Styleguide design, if you want to deploy it use [-s] <<<` and does nothing without `-s`.
   - Prints **`===> Finished deploying product P-F`** (:201) and logs LDS success.
6. `globalPostdeployTasks`: `startProcesses` is skipped by `-n`. `clusterGlobalPostdeployTasks` → `makeFiltertex` runs `make > /dev/null` in `~/scripts/lexers` (:799-805). **That happens after the success string**: a make failure is a traceback that the DS ignores.

**"Deployed" means** redeploy.py reached the print at :201, with no python exception before it, and no line containing `Java Result:` (a legacy Ant java-task marker). Nothing checks:
- that the extracted webapp is complete (the `jar -xf` exit code is lost);
- that the WAR is the one just built (redeploy takes the lexicographically latest file with the right prefix, whatever built it);
- that the app server was stopped. `-n` skips the stop, and the files under a live JVM are deleted and replaced: `cleanDeployDirectory` plus the webapp rmtree.

### 5.2 `rstrt` stop / start / status (HostStop, HostStart)

**Stop (`-w -q`)** → `RestartManager.restartProducts` → `restartCurrentProduct` → `stopWebProcess` (`restart.py:454-489`):
- It runs **three** restarters in turn, Resin, Tomcat and Jetty, whatever the app-server type. Each one `pgrep -f -u $USER <identifier>` (`caucho`, `catalina`, `jetty.base`) and keeps only pids whose `/proc/<pid>/environ` has `DEPLOY_HOME=` equal to this deploy home (:1445-1552).
- If nothing is found: `no <resin|tomcat|jetty> web processes found, do nothing` (:1347-1349).
- Otherwise:
  - `Stopping <x> web process nicely`; the stop command (`java -jar lib/resin.jar -conf … stop`, `bin/catalina.sh stop` or `bin/jetty.sh stop`, with `reqSuccess=False`; errors are swallowed as `Could not stop resin nicely`, :1291-1322)
  - `Sleeping for 10 seconds` (prod only)
  - `Stopping web process by killing pid`
  - `killAllPids`: `ps | grep suggest | xargs kill -9`, then `rkill <pid>` / `rkill <pid> -9`. **`rkill` is a bash function** (`functions.sh:1616-1629`) and does not exist in `os.system`'s `/bin/sh`; with output sent to `/dev/null`, those calls silently do nothing (:650-666).
  - `checkProcessesKilled`: `isProcessKilled` runs `kill -0 pid 2>/dev/null` and looks for "no such process" in **stdout**, which never contains it, so it always returns False and `kill -9 pid` is always sent (:626-648). **The net effect is SIGKILL**, and death is never verified.
  - On prod, `akkaStopNode` POSTs "down" to the other cluster nodes through grequests with a 2 s timeout, fire-and-forget (:1376-1420).
- **DS verdict:** Success if the log contains `do nothing` or `killing pid` (DS:`visitor/SshExecutedVisitor.java:82-90`). Because all three restarters run, a Tomcat host always logs `no resin web processes found, do nothing` and `no jetty … do nothing`. **Web HostStop is Success whenever restart.py reaches `stopWebProcess`**, whether or not Tomcat died.
- **Backstage/backoffice/rbackstage stop:** `WrapperRestarter.stop` runs `backstage.wrapper.sh stop >> <proc>.out.log 2>&1` in the log dir (`restart.py:1152-1175`). The output goes to that file, not the DS log.
  - The wrapper tries `kill` twice, then `pkill -9 -P <pid>` (children only, not the wrapper itself), and prints `Failed to stop …` or `Stopped …` into the file (`backstage.wrapper.sh:189-230`).
  - The DS gives backstage/backoffice types Success when the log contains `Restart:` (:95-97). **`Restart: <datetime>` is printed by every restart.py run** (`restart.py:110`), so these stops are **always Success**.
- **mdcdaemon stop** (`rstrt -M -q -q`): `-M` is ignored (§2.6), so it stops every process of the product on the host.

**Start (`-r -w`)** → `restart()` → `isConditionalRestart` (start-dead) → `startIfDead` (:963-971, 1008-1014):
- `isAlive()` = `getPrimaryWebPid()` finds a pid with the right DEPLOY_HOME whose `ps -p` output contains `java` (:1428-1443, 1708-1722). **If one exists, nothing is started.**
- **Resin start** (:1739-1789): `checkResinStatus` (dev only; on `Unexpected resin.home mismatch` it runs `sys.exit(0)`, exit 0 with nothing started), `checkFileSystem`, `inject()` (rewrites `resindeploy.main.conf` JVM args and ports), then `os.system("<java> -jar lib/resin.jar -conf … -server <host> start >> wrapper.log")`. The return code is ignored and `verifyStarted` is commented out (:1791-1792).
- **Tomcat start** (:2120-2189):
  - `EmptyResinTemp` (`find $DEPLOY_HOME/temp -mindepth 1 -delete`), recreate the `logs` symlink, set `CATALINA_OPTS`, then `os.system("bin/catalina.sh [jpda] start")`. The return code is ignored.
  - systemd variant (`isSystemd`: Tomcat and `USER==literatum`, or `systemd="true"`, `product.py:537-552`): clean old `/var/tmp/P-F-*.env` files, write `/var/tmp/<P-F-date-rand>.env` with **the whole environment** (including DB credentials exported by setprod), then `systemctl --user start tomcat@<name>.service`. The return code is ignored.
- **`checkFileSystem`** → `$SCRIPTS_HOME/checkMountPoint.sh P`, which raises `There is a file system mount failed!` on a non-zero exit (:1727-1737).
  - `checkMountPoint.sh` sets `StatusExit=True` inside `echo … | while read` (a subshell), so the flag is lost and it **exits 0 even when a mount or test-file write failed** (:77-119). It exits 1 only when no mount points are found (`failed again`, :65).
  - The `touch` writes to `$writeOnPath/test.txt`. It runs `sudo mount`.
- **Wrapper start** (`-b`, `-R`, `-o`): the DS sends `rstrt -b` without `-r`, which means `stopstart()` (stop, then start).
  - `backstage.wrapper.sh start` backgrounds `exec -a <APP_NAME> wrapper <conf> &` and returns 0 (`backstage.wrapper.sh:153-186`). It exits 1 with `… is already running.` (→ `DeployErr("Failed to execute …")`, `restart.py:1197-1200`).
  - Before that, `exportMemorySetting` prints `***<type> NOT STARTED***` and exits 1 when there are no JVM args (:46-53).
  - After the background launch nothing checks that the JVM stays up (`verifyStarted` is disabled, :1205-1206).
- **APM and profiler side steps** before any start (`restart.py:166-190`): the otel agent copy (errors swallowed; `sys.exit(1)` if `otel_vars.env` is missing), the newrelic agent copytree, pyroscope. Also `opsaction` records an HTTP GET to `support.atypon.com` **with no timeout** (per sub-agent), which can hang rstrt.
- Every JVM gets `-Xbootclasspath/a:/home/<developer>/servers/lit-2410/<developer>/resin/webapps/support/WEB-INF/lib/saxon9ee-9.9.1.3J.jar` whenever **any** arg contains `javaagent` (`restart.py:1601-1602`). That is a developer's personal path, hard-coded into production JVM args.
- JVM arg order is lost: `deployconf.getDeployFamilyJvmArgList` turns the list into a `set` (`deployconf.py:1534,1547`).

**Status (`-s`)** → `showstatus` (:1989-2001): `::<host>:: [pid] Web process is running for family F` or `::<host>:: Web process is NOT running for family F`. For wrappers it is the wrapper's `status` output, `<pid> <APP_NAME> is running` or `<APP_NAME> is not running.`, via runGetTeeOutput (`restart.py:1234-1254`; `backstage.wrapper.sh:232-243`).

**DS verdict for HostStart:** the first line containing `err.DeployErr` fails; the first containing `process is running` succeeds (DS:`visitor/SshExecutedVisitor.java:117-143`).
- The DS sends `rstrt -s` **before** the start (DS:`visitor/SshExecuteVisitor.java:138`). If the old JVM is still alive (for example because HostStop "succeeded" without killing it, see above), the pre-start status line `Web process is running` makes HostStart Success, and `-r` leaves the old JVM running on top of a redeployed directory.
- **"Started" means** at that instant a java process exists whose environ has this `DEPLOY_HOME`. It says nothing about the webapp: Tomcat keeps running with a failed context, as in the LIT-683431 NPE at startup. Real HTTP readiness is left to the later DS actions HostWaitForWebServer and HostWarmupTest (opstool, outside this repo).
- **Non-CIP backstage/backoffice** status prints `<pid> BackstageQserverMode-… is running`. That does not contain `process is running`, and no emitter of that exact phrase exists for wrappers in platform-tools (grep: only `restart.py:1998` for web, plus the unrelated `rebuild.py:168`). By this parser, HostStart for a backstage-only non-CIP host can only succeed if a web status line for the same product appears. This is a DS/script mismatch to confirm against real action logs.
- Tracebacks from `deploy.DeployErr` (restart raises some errors via `err.DeployErr`, others via the duplicate class `deploy.DeployErr`, `deploy.py:1030-1037`) print `deploy.DeployErr:`, not `err.DeployErr`, so they don't trigger the explicit failure branch. They still default to Failure.

---

## 6. Styleguide chain end to end (sub-agent read; key citations re-checked where noted)

**ProductBuildStyleguide** (`Build-Deploy-Styleguide.sh -p -f -b -a [-g]`, validated by `BUILD COMPLETED`).
- **DS wiring:** added by DS:`visitor/CreateActionMacro.java:955-973` when deployconf has a styleguide version. `-b`/`-g` come from `<styleguide><version>`/`<group>`.
- **Setup:**
  - Sources bashrc (no-op), aliases, functions, and `jenkins/styleguide/operations.sh` → `jira_funcs` (:3-6).
  - `main` sets an ERR trap that only logs an LDS failure. There is **no `set -e`** (:894).
  - `checkDataCenterLinks` rsyncs `~/.nvm` to `/local$HOME/.nvm`, then `rm -rf ~/.nvm` and `ln -snf`, all unchecked. A failed rsync loses nvm (:808-818).
  - When `command -v nvm` fails (likely always, since nvm is a function not loaded yet), it **downloads and runs the nvm installer from raw.githubusercontent.com** and runs `nvm install 14.16.0` (:35-46, :910-920).
- **Checkout** `~/sourcegit/ui-products-branches/<b>/ui-products`: `git fetch`, `checkout`, `reset --hard origin/<b>`, `clean -fdx`, `pull`, or `git clone git@github.com:atypon/ui-products.git`. **All unchecked**, so a failed fetch builds stale code (:48-135). `git submodule init/update --remote` is checked (:292-302).
- **Toolchain:**
  - npm prefix, `npm i -g npm@6.14.11`, `nvm use 14.16.0` (checked, :355-382).
  - `loginToAtyponRegistry` writes the npm `_auth`/`_authToken` into `~/.npmrc` (`<secret at Build-Deploy-Styleguide.sh:864-872>`). Those values are also echoed by `printMsg`/`printCMD`, **so they land in DS action logs**.
  - `npm i -g @atypon/utypon-cli@latest` on midtierbeta and staging, else pinned `1.31.11`, unchecked (:387-395).
  - `NODE_ENV=production`, `NODE_OPTIONS=--max-old-space-size=25000`.
- **Build:** `cd <group>|<product>`, `rm -rf node_modules [releasedAssets]`, `utypon build optimized … --threadsCount=10 --ramCount=10`, unchecked (:450-480). Then `checkBuildSuccess` greps `<dir>/build.log` for `All Products Have been Built Successfully`. If absent: `Error - Failed to Build The Product ,,, Exiting - Exit code: 1`, exit 1 (:306-327).
  - A missing product dir prints `PRODUCT MISSING OR NOT FOUND,Please check your script parameters-deployconf for GROUP,PRODUCT NAME` (:472).
- **`releasedAssets`:** writes `styleguide.info` (version, date, git short hash, ui-* versions; `Not Found` when absent) into `~/webdav_directories/<P>/<F>/` and `./releasedAssets/`. `componentVersionsUtil.py` reads it later for LDS (:160-266).
- **`Zip-uploadToAWS`:**
  - `tar -cf ~/sourcegit/styleguide_new_<acct>_<P>_<F>.tar <dir> <dir>/styleguide.info` (including `node_modules`) (:564-613); `ERROR: [<g>] group is missing` / `ERROR: [styleguide.info] is missing` / `ERROR: [<bundle>.tar] is missing` with exit 1.
  - `gzip -f` and `mv` to `~/warfiles/`, both **unchecked** (:616-621). The backup test uses a quoted `"~/warfiles/…"`, which never expands (:618).
  - S3 and FTP upload are **commented out** (:622-647). Nothing in these repos consumes `styleguide_new_*`.
  - **`echo "BUILD COMPLETED"` is unconditional** (:649).
- **Silent success paths:** stale checkout; utypon install failure when an old `build.log` survives (only `clean -fdx` on an existing repo removes it); gzip/mv failure or a full disk. The ERR trap can log both a failure and a success LDS event for one build.
- **Locking:** none in the script. The DS serialises one per host (DS:`scheduler/BlockActions.java:462-476`, per sub-agent).

**HostDeployStyleguide** (`setprod P F; ~/scripts/deployStyleguide.py`, validated by `Finished styleguide deployment`).
- `deployStyleguide.py:300-302`'s `__main__` block only prints `Not Production, Exiting.` and `>>> Finished styleguide deployment`. **The action always succeeds and deploys nothing.**
- The real logic, `DeployStyleguide`/`deployStyleguideNew.py`, is reachable only via `redeploy.py -s` (dev path). It rsyncs `styleguide-templates/<SG_BRANCH>/ui-products/<group>/<P>/` from a pugrenderer node into `WEB-INF/products`, `webapps/products` and `ux3`, then GETs `/action/styleguideDeployed`. That path is dead for the DS and has its own bugs:
  - WAR names `styleguide_<user>_…` vs the built `styleguide_new_<acct>_…`
  - `shutil.rmtree = shutil.rmtree(...)` (`deployStyleguide.py:208`)
  - `status_code != '200'` (int vs str) (`deployStyleguideNew.py:114`)
- In practice DS sites get styleguide from pugrenderer (PugrendererProductDeploy, ansible, outside this repo). HostDeploy wipes the webapp, and nothing here restores `products/` or `ux3/`.

**Related actions:**
- GenerateStyleguidePackage (`packageStyleguide.py`) and StyleguideTemplateUpdate (`styleguide/styleGuideUpdate.sh`): scripts missing from the repo.
- CheckStyleguideMaintBranches (`gitBranchCheck.sh`): has no validator, so it always succeeds. It runs `svn up` on the now-git `.litconfig`.
- SgBranchesCleanup: ansible.

---

## 7. Failure signatures

| Exact text (substring) | Meaning | Emitted at | Likely root-cause class |
|---|---|---|---|
| `Failed to aqcuire build-lock, another build process is running.` / `## see LIT-246176 ##` / `Could not acquire lock on <src>/.build` | `<src>/.build.lock` exists | rebuild.py:164-168; filelock.py:57-59 | Concurrent build, or a **stale lock** from a killed or SIGHUP'd earlier build (§3.5) |
| `LIT-656000: literatum-master patch failed, reverting...` | `git apply` of the build-time patch failed; build **continues unpatched** | rebuild.py:705 | Patch drift vs branch HEAD. Downstream: startup NPE on null cluster metrics (LIT-683431) while ProductBuild shows Success |
| `PATCH common applied OK` / `PATCH master applied OK` / `PATCH for 2610 and master applied OK` | Build-time patch applied | rebuild.py:696,699,703 | Informational; absence on master/2610 LOCAL_BASE hosts means the patch block was skipped or failed |
| `Build failed!  Output is in /var/tmp/<n>.txt` | `BUILD FAILED` seen in gradle/ant output | rebuild.py:637,798 | Compile or test failure |
| `unknown option: -M` | readonly `-M` ignored | rebuild.py:1220 | Benign; shows `-M` has no effect |
| `Warning: Product %s is set to not be rebuildable…` | `<rebuildable>false` | rebuild.py:146 | Config; DS then fails with no `BUILD SUCCESSFUL` |
| `No warfile was found for '<P-F>', you probably need to rebuild it…` / `No warfile was found, you probably need to rebuild it…` | No `~/warfiles/P_F_*.war` | redeploy.py:221, 833 | Previous ProductBuild "succeeded" but `copyWarFile` crashed after renaming the old WAR (§3.4) |
| `Akka Zookeeper version 3.5+ (found X) is required for …` | Inventory ZK version too low for the branch | redeploy.py:1028 | Inventory/config |
| `Skipping Akka Zookeeper version check. An inventory error has occured.` | Inventory lookup failed; check skipped | redeploy.py:1022 | Inventory API or ansible checkout |
| `===> Finished deploying product P-F` | DS HostDeploy success marker | redeploy.py:201 | Printed even when `jar -xf` failed (tee) |
| `Error, you specified mutually exclusive flags --no-styleguide and -s` | Option conflict | redeploy.py:1185 | Caller error |
| `no <resin\|tomcat\|jetty> web processes found, do nothing` | That app-server type has no pid for this DEPLOY_HOME | restart.py:1348 | Normal; also why web HostStop always passes |
| `Stopping web process by killing pid` | About to SIGKILL | restart.py:1360 | Normal; the DS keys on `killing pid` |
| `Could not stop resin nicely` | Nice-stop threw | restart.py:1316 | Missing resin.jar or conf |
| `ERROR : Java Cryptography Extension is NOT installed…` | JCE limited (128) | restart.py:116 | Wrong JDK on host |
| `*****ERROR!!! cfa, trustwave or elsevier's cert not found!…` | cacerts missing required certs (cfa/marlin families, prod) | restart.py:231 | JDK cacerts not updated (`run tool install.cacerts`) |
| `There is a file system mount failed!` | `checkMountPoint.sh` exit≠0 (only when no mount points found) | restart.py:1736; checkMountPoint.sh:65 | fstab / product name mismatch |
| `Failed to execute <wrapper> start…, please check <proc>.out.log for detail` | Wrapper start returned ≠0 (for example `already running`) | restart.py:1199 | Old wrapper still alive |
| `***<type> NOT STARTED***` / `ERROR: deployfamilyinfo/entry/args process="<type>" not defined in deployconf.xml` | No JVM args for the wrapper process (goes to `<proc>.out.log`) | backstage.wrapper.sh:50-51 | deployconf |
| `Failed to stop <APP_LONG_NAME>.` | Wrapper stop failed (in `<proc>.out.log` only) | backstage.wrapper.sh:225 | Hung JVM; `pkill -P` only kills children |
| `::<host>:: [pid] Web process is running for family F` | DS HostStart success marker (`process is running`) | restart.py:1998 | Only proves a JVM pid exists |
| `unknown option given to restart.py: -M` | mdcdaemon flag ignored; acts on all processes | restart.py:870 | DS/script mismatch |
| `Error, specify -a for all products or -p p1,p2 … Have you run setprod yet?` | No product in env | deploy.py:302-305 | `setprod` failed earlier in the session |
| `Error, %s not found ` (deployconf) | `~/deployconf.xml` symlink broken | deployconf.py:59 | Account symlinks (`bashrc:186-223`) |
| `ERROR running command env.py …, cmd failed` / `…no result` | `setprod` sub-lookup failed | functions.sh:1298,1303 | deployconf / product not on host |
| `===> No product found with name %s designated to run on this machine <===` | env.py lookup | env.py:920 | Wrong host or product |
| `ERROR: <X> not found in your environment…` then silence (exit 0) | run_gradle.sh or run.sh env guard | run_gradle.sh:21-95; run.sh:21-94 | setprod not run; **exit 0** |
| `Patch failed!  Output is in /var/tmp/<n>.txt` | patch.py saw `FAILED` or `KILLING THE SYSTEM` | patch.py:196 | See next rows; **the DS may still mark Success** (§4.6) |
| `PatchProgram (<P>):Patch <name> failed to execute` | A JDBC patch threw | literatum JDBCPatchExecutor.java:119 | SQL/data error. The DS parses the name and schedules BrokenPatchBlame |
| `PatchProgram (<P>):DB version X doesn't equal your build version Y you can ignore this check by running patch.py with -R[, or upgrade the DB with -u]` | Release mismatch | DbPatchSystem.java:127-131 | DB not upgraded or wrong branch; use `-u`/`-R` |
| `Patch <name> is reserved, use -F to run reserved patch…` (thrown as `Error`) | Reserved patch requested | DbPatchSystem.java:157-162 | Patch plan; **may hang the JVM** (§4.3) |
| `********** ERROR LOADING PRODUCT <P> **********` / `********** KILLING THE SYSTEM **********` | Literatum init aborted → exit 1 | literatum Main.java:444-450 | DB connectivity, Spring/cluster init |
| `Patch complete. tt=<n>s` | One JDBC patch finished | JDBCPatchExecutor.java:87 | ProductDBUpgrade success marker (weak) |
| `Patched Successfully: <list>` | patch.py's view of success | patch.py:190,211 | An empty list followed by a traceback means product not on host (§4.2) |
| `please add '--families={family name}' to patch` | Ambiguous product (exit 0) | patch.py:141-143 | DS passed no family |
| `product(s) [...] not found in deployconf.xml (not defined or disabled.)` | exit 0 | patch.py:110-112 | deployconf |
| `BUILD FAILED` / `BUILD SUCCESSFUL` | Gradle/Ant verdict; the **only** signal the DS reads for ProductBuild and ProductPatch | gradle/ant | See §3.2 and §4.6 caveats |
| `restart build` ; `Unable to delete file … DbAntPatcher.class` | DS reschedules ProductPatch once | DS:`visitor/SshExecutedVisitor.java:459-464` | Transient build-dir contention |
| `failed=0` / `SSH Error` | Docker-DB patch via ansible | DS:`visitor/SshExecutedVisitor.java:420-427` | ansible |
| `Error - Failed to Build The Product ,,, Exiting - Exit code: 1` | utypon build log lacks `All Products Have been Built Successfully` | Build-Deploy-Styleguide.sh:306-327 (msg via 157/800-804) | UI build failure |
| `PRODUCT MISSING OR NOT FOUND,Please check your script parameters-deployconf for GROUP,PRODUCT NAME` | Product dir missing in ui-products | Build-Deploy-Styleguide.sh:472 | deployconf group/product |
| `BUILD COMPLETED` | DS styleguide success marker (unconditional) | Build-Deploy-Styleguide.sh:649 | — |
| `>>> Finished styleguide deployment` | DS HostDeployStyleguide marker (script is a no-op) | deployStyleguide.py:300-302 | — |
| `FAILED: <jdk> is not supported.` / `FAILED: Error downloading …` | JDK auto-download failed → deploy.py raises | downloadJDK.sh:27,62; deploy.py:650-651 | Unsupported JDK name or no internet |
| `WARNING! Exception while Logging Action Event for …` | LDS stats write failed (swallowed) | literatumDeploymentStatisticUtil.py:106-109 | `/local$HOME/servers/Literatum_Statistics/...` perms or disk |

---

## 8. Bugs and risks (file:line)

**Verification and silent success** (highest impact):
1. `commandutil.runGetTeeOutput` pipes through `tee` under `/bin/sh` with no pipefail, so every exit code is lost (`commandutil.py:149-150`). Callers that rely on it:
   - Gradle/Ant build (`rebuild.py:629,788`)
   - `git pull` (`rebuild.py:234`)
   - `jar -xf` (`redeploy.py:877`, comment wrong)
   - the patch run (`patch.py:180`)
   - wrapper status (`restart.py:1238`)
   - shmux (`shmux.py:35`)
2. `run_gradle.sh:244-247,262-268`: the `finalcmd= eval …; command_exec $finalcmd` pattern always exits 0.
3. Build-time patch failure is swallowed and the build continues unpatched (`rebuild.py:704-706`). ProductBuild still reports Success.
4. `copyWarFile` renames the current WAR to `.old` before the new WAR is confirmed; a failure leaves no deployable WAR after a "successful" build (`rebuild.py:851-875`, DS check actions.xml:1628).
5. The DS ProductPatch parser breaks on the first `BUILD SUCCESSFUL`: in multi-family runs a later failure is masked, and patch.py's own `Patch failed!` is ignored (DS:`visitor/SshExecutedVisitor.java:445-481`).
6. ProductDBUpgrade's `Patch complete.` matches after the first patch (actions.xml:904; JDBCPatchExecutor.java:87).
7. HostStop web always passes (`do nothing` from sibling restarters; restart.py:471-487,1348 + DS:`visitor/SshExecutedVisitor.java:86`). Backstage stop always passes (`Restart:` printed at restart.py:110 + DS :95).
8. HostStart passes on the pre-start `rstrt -s` if the old JVM survived, and `-r` then does nothing (DS:`visitor/SshExecuteVisitor.java:138-141`; restart.py:963-971).
9. `rdply -n` deletes and replaces app-server and webapp files without stopping the JVM (`redeploy.py:1152,676-679,1713,247-248`). It relies entirely on HostStop, which cannot fail (item 7).
10. `deployStyleguide.py` as run by the DS is a no-op that prints the success marker (`deployStyleguide.py:300-302`). `Build-Deploy-Styleguide.sh` prints `BUILD COMPLETED` unconditionally (:649) and ignores git, npm, gzip and mv failures.
11. `checkMountPoint.sh:77-119`: failure flag set in a pipe subshell, so it always exits 0.
12. `run.sh` and `run_gradle.sh` env guards use a bare `exit`, which is 0 (run.sh:26,58,65,72,94; run_gradle.sh:26,58,65,72,94).
13. `sanitytest.main()` is a no-op, so `--test` verifications always pass (sanitytest.py:160, per sub-agent). `restart.py:900` would `raise` a str (TypeError) anyway.

**Hangs and locks:**
14. Stale `<src>/.build.lock` after a killed build blocks all builds; timeout=None and no PID/age check (`rebuild.py:150-169`; `filelock.py:57-59`).
15. `DbGradlePatcher` catches only Exception, so an `Error` can leave a non-daemon-thread JVM hanging (DbGradlePatcher.java:20-27).
16. `--parallelbuild` refresh retries `git pull`/`svn up` forever (`rebuild.py:224-232`).
17. `opsaction` HTTP GET has no timeout (per sub-agent, opsaction.py:43-44).
18. The patch run on a shared Gradle daemon and `~/.gradle` with `org.gradle.parallel` allows cross-product interference on one host (`operations/tools/gradle.properties`; run_gradle.sh:244). The `initialize` task deletes the target classes dir at configuration time (`build.gradle:33`).

**Option parsing** (the code does not match the man pages):
19. `-M` is ignored by both `rebuild.py` (:1127, 1220) and `restart.py` (:761, 870). For mdcdaemon this means "all processes".
20. `patch.py`:
    - `--disabledbrelease` never matches (:457)
    - `--haltonerror` vs the tested `--haltoneerror` (:388)
    - `o in ("--gradle")` is a substring test, so `-g` (debugger) sets USE_GRADLE (:461-462)
    - `--DebugSuspend` vs declared `DebugSespend`, and `--DebugPort` declared without `=` (:349-350, 471-475)
    - `-r` or `-n` combined with Gradle hits an unbound `cmd_pattern` (:166-176)
21. `rebuild.py:1128,1132` and `restart.py:769-770`: missing commas concatenate long options.
22. `redeploy.py:1138`: `-r` rollback is not in the short options.
23. `rebuild.py:780-781`: `-Drootpom.version` appended after the command was built, so it is dead.
24. `Deploy.main` swallows `--backstage`, `--backoffice`, `--web` and `--rbackstage` as `processName` before subclass parsing (`deploy.py:70,150-157`). `rstrt --backstage` therefore never adds the process.

**Process control:**
25. `rkill` is a bash function called from `os.system` (/bin/sh), so it silently fails (`restart.py:660-666`; functions.sh:1616).
26. `isProcessKilled` can never return True (stderr discarded; `restart.py:628-636`). The result is an unconditional `kill -9` without verification.
27. `backstage.wrapper.sh:218` `pkill -9 -P $pid` kills children, not the wrapper. There is no post-start liveness check (restart.py:1205-1206).
28. A hard-coded developer path goes into production JVM args whenever a javaagent is present (`restart.py:1602`).
29. JVM args are deduplicated through `set()`, losing their order (`deployconf.py:1534,1547`).
30. `ResidueKiller` references the commented-out `WebRestarter.WEB_IDENTIFIER`, so `-c` gives an AttributeError (`restart.py:2324` vs :1263).
31. `isUnhealthy` has an early `return`, making the lock-ratio logic unreachable (`restart.py:2050-2077`).
32. The Tomcat systemd env file `/var/tmp/<P-F-…>.env` dumps the whole environment, including DB credentials exported by setprod (`restart.py:2205-2212`; functions.sh:720-724).

**Branch, JDK and environment:**
33. `deploy.py:621`: `int(branch)` before the empty check.
34. `rebuild.py:272`: lexicographic release compare.
35. The two DeployErr classes (`err.py:1-9` vs `deploy.py:1030-1037`) change traceback text that the DS keys on (`err.DeployErr`).
36. `setprod` failure does not stop the DS session; the next command runs in an unset environment (functions.sh:440, DS §0).
37. `redeploy.checkAkkaZkVersion` gives a KeyError if `CVS_BRANCH` is unset (`redeploy.py:1195-1196`).

**Patch VM:**
38. Patches run against the **deployed** webapp classes and, on DC hosts, the **deployed** `iapps/patch` SQL files. Patch-before-deploy uses the old release (`build.gradle:21-27`; DbPatchSystem.java:924-929).
39. Staging `rm -f rep*` mutates the deployed webapp (DS:`visitor/SshExecuteVisitor.java:434-438`).
40. `build.gradle:126` `host.name` is taken from the property `hmalabeh`, so it is always null.
41. The Gradle path has no pool-completion check (only Ant `patch.xml:96` has one).

**Supply chain and secrets:**
42. Embedded GitHub/npm/Jira credentials: `<secret at functions.sh:1975>`, `<secret at functions.sh:2023>`, `<secret at sync_branches.sh:37>`, `<secret at sync_branches.sh:66>`, `<secret at Build-Deploy-Styleguide.sh:864-872>` (also echoed into DS logs), `<secret at jira_funcs:56>`, `<secret at deployserver/test/updateTestToolRepo.sh:16,25,33>`, `<secret at nr_agent.py:107-116>`, `<secret at tomcatdeployconf.py:55-56>`, `<secret at releaseTracker.py:48>`, `<secret at restart.py:226>` (default keystore pass).
43. The styleguide build downloads and executes the nvm installer from the internet on each run and uses `utypon-cli@latest` on midtierbeta and staging (Build-Deploy-Styleguide.sh:35-46,387-395). `downloadJDK.sh` fetches JDKs from the public internet during a build (downloadJDK.sh:14-40).
44. Missing scripts referenced by DS actions: `deployserver/checkSqlPatchStatement.sh`, `styleguide/styleGuideUpdate.sh`, `packageStyleguide.py`.

**DS/host shell contract:**
45. The DS prompt matcher `)<account>]` (DS:`connect/JschConnection.java:81`) does not match `bashrc/security/bashrc:252`'s PS1. The production bashrc must differ; confirm on a host before relying on command-boundary timing.
