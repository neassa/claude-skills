# 25 — The four "patching" side repos, and the physio lit32046 NPE

Written 2026-09-25 from read-only code reading. I ran nothing: no gradle, no scripts, no DB, no SQL.
Every repo file went through `tools/safe_view.py`, so credential-looking values show up masked.
Secret-bearing lines are cited by file:line only. I reproduced no customer rows from the creation-script SQL.
I read only headers, the `db_info` rows and counts of `db_version` rows.

Clones and commits:

| Repo | Commit | Notes |
|---|---|---|
| daily-patching | `380389e`, 2022-05-16 | shallow |
| Dailypatch-backend | master `e4c1526`, 2024-07-27 | The live branch is `refactor/simplify-architecture` `31a881e0`, 2026-08-02. I read it through `gh api` (README + PatchWrapper.sh only). |
| literatum-patch-creation-scripts | main `0ce716a`, 2026-03-02 | LFS content present |
| literatum-deployment-info | `60f98a3`, 2019-01-03 | |
| literatum-patch | `7077394`, 2026-09-24 | |
| platform-tools | `b00c49f`, 2026-09-25 | |
| deployserver | `b726c83`, 2026-09-24 | |
| literatum-lit-2610 | `9f8eb846e`, 2026-09-25 | |
| literatum master | `0c62d0157` | |
| literatum `lit-2610-physio-pcms-260706` | `b5fdf684`, 2026-09-23 | Read through `gh api`. This is physio beta's branch, per `deployconf.midtierbeta.xml:7413`. |

## 1. Verdict per repo

| Repo | Used today by DS / platform-tools? | What it is |
|---|---|---|
| **literatum-patch-creation-scripts** | **Yes, indirectly.** DS action (CIP "create docker DB", `actions.xml:802-826`) → `platform-tools/docker/build_docker_db_wrapper.sh` → `ansible-actions -a prepare-product-mssql` → `ansible-mssql/roles/prepare-new-product`. That role clones the repo into `~/sourcegit/literatum-patch-creation-scripts` (`tasks/main.yml:44-60`). It then `docker cp`s `literatum[/passport]/creation-scripts-<product_version>/<ver>-{passport-creation-scripts,schema-and-data}.sql` (`defaults/main.yml:23-25`, `group_vars/all:6,34`), runs `sed s/minimepb2/<product>/g`, and applies it with sqlcmd. Then it runs `daily-patch` → `backup`. The DS also carries a release-ticket template "Generate $release DB creation scripts" (`deployserver/config/jira.xml:620-625`). | Seed schema+data dumps for **new dockerized product DBs** (CIP/dev). It does not create or number patches. |
| **Dailypatch-backend** | **Not by the DS or platform-tools.** Nothing in `deployserver/`, `platform-tools/`, `ansible-inventory` calls it. It runs standalone as a Docker Spring Boot service on office patch VMs (`patch-jo01/02`, `patch-gr*`; README:30-31). **Active:** the rewrite branch was pushed 2026-08-02. platform-tools already has hooks for it: `functions.sh:746-747` (`patch-dc-*` hosts), and `patch.py --external --type --target-database*` (IT-24311, 2026-08-11). The rewrite's `PatchWrapper.sh:90-97` uses those flags. The rewrite README says "Deployserver can start a patch-only run… `POST /api/v1/patch/database`", but **no DS code calls that endpoint yet** (I grepped `deployserver/src` and `config`). | "Daily patching" = a nightly (01:00 GMT+3, `DailyPatchService.java:303`) **rehearsal on office DB copies** (`<env>_<product>` / `cip_<family>_<product>`, `XmlParser.java:160-166`, `DbUtilities.java:23-27`), **not production**. For every enabled product in `deployconf.{migration,lts,office-santaclara-cip,staging,midtierbeta}.xml` (`application.properties:9`) it runs `rebuild.py -cswr` → `redeploy.py -nv` → `patch.py -p P --allowdropcolumn` (`PatchWrapper.sh:32-41`). It greps for `BUILD SUCCESSFUL` / `Finished deploying` (`*Stage.java`). It opens or updates LIT Jira bugs titled **`Dailypatch: Failed Patch Dev.DB : …`**, labelled `patching`, `<dbserver>`, `<env>_<product>` (`TicketManager.java:276-295`, `JiraErrorReporter.java:242-246`). It auto-resolves them by label when the product next patches cleanly (`Validator.java:42-47`). It classifies failures with `yaml/issue-types.yml`. It first runs a "pilot" set (hope, wb on lit-2210 staging) before fanning out (`PatchingLoop.java:106-122`). There is a small dashboard in `Dailypatch-frontend` (pushed 2023-07) and `dailyPatchDashboard` (2022-08). **Both are unlisted repos**, and I did not read either. |
| **daily-patching** | No. | **Stale** (2022-05, 1 commit). It holds 3 identical Jenkins pipelines (agents `patchjo`/`patchgr`/`patchsc`) that ran `~/dailypatch/make-todo-jenkins.sh` / `run-todo-jenkins.sh <release>` with a 48 h timeout. On failure they open a P1 LIT bug, "Dailypatching Build Timeout". The scripts themselves are **not** in the repo. This is the predecessor of Dailypatch-backend. |
| **literatum-deployment-info** | No. | **Stale** (2019). A Java library ("deployconf schema for external modules": Product/Environment/DB/Cassandra/Kafka models, SVN deployconf download). Its code was later copied into `classification-inference-learning/knowledge-base` (org search). It has nothing to do with patching. |

Related live code I found on the way. This is not in the four repos:
- `ansible-mssql/roles/daily-patch` is the **live** "daily patch" for dockerized DBs. `start-patch-backup.yml:10-19` is exactly what DS ProductPatch runs for a docker DB (`SshExecuteVisitor.java:461-463`).
  - The role runs `setprod P F && patch.py -p P --families=F --allowdropcolumn`.
  - Its success test is **`"patch pool marker for 'jdbc' ends. All patches applied successfully."` in stdout** (`tasks/main.yml:15-25`). A failure in the report/archive pool alone passes.
  - It takes a backup only if `select top 1 patchname from db_version order by dateapplied DESC` changed (`start-patch-backup.yml:19`).
- `prepare-new-product/tasks/fake-failing-patches.yml` sets `lit6024` to `status=0, description='Execution of this patch is faked'` (`defaults/main.yml:20-21`).
- `platform-tools/cleanupOldPatches.sh` is the SVN-era archiver that moves old patches out of `mssql/literatum`. It uses `svn-master`, so it is **stale**. It explains why old DBs carry `db_version` rows for patches that no longer exist as files.

Secret-bearing lines (not read):
- `Dailypatch-backend/src/main/resources/application.properties:17-18, 27-28, 33-34`
- `ansible-mssql/roles/prepare-product-database-from-backup/tasks/main.yml:9-10`
- `deployconf.*.xml` `<database … pass=…>` lines, e.g. `deployconf.midtierbeta.xml:7430`

## 2. How each one touches ProductPatch / DB_VERSION / stubs

- **Creation scripts → DB_VERSION / DB_INFO seed.** Every script inserts `db_info` and a frozen `db_version` history:

  | Script | `db_info` release / previous / product | `db_version` rows | Newest lit patch recorded |
  |---|---|---|---|
  | `literatum/creation-scripts-2020` and `-2210` | 2020→2210 / 2020 / minimepb2 | 4028 | ≈ lit308xx |
  | `literatum/creation-scripts-trunk` | trunk / 2020 / minimepb2 | 4028 | ≈ lit308xx |
  | `passport/creation-scripts-2410` | 2410 / 2210 / **bpl** | 4422 | ≈ lit3121x |
  | `passport/creation-scripts-2610` | 2610 / 2410 / minimepb2 | 4422 | ≈ lit3121x |

  - Evidence: `db_info` rows are at `2610-passport-creation-scripts.sql:93430-93439` and `trunk-schema-and-data.sql:47487-47496`.
  - The max-patch values come from counting `INSERT [db_version]` rows by name prefix. `safe_view` masks the names, so they are ranges, not exact values.
  - The files are relabelled copies:
    - 2210 = 2020 except `db_info` lines 47492/47494.
    - trunk = 2210 except line 47494.
    - 2610 = 2410 except 662 changed lines. These are data-row renames (wf_token_value, LOG_EMAIL, DOMAIN_INFO, …) plus `db_info`, with **no new `db_version` rows and no new DDL**.
  - Consequence: a DB built from the "2610" script is a ~lit3121x schema labelled `release=2610`. Its first `daily-patch` runs **every pending patch from ≈lit3122x to lit32054, several hundred of them**, with plan `2410` from `platform-tools/patchplan/patchdependency_2610.xml:1751`.
- **Stubs:** none of these repos compile or ship `com.atypon.patch.*`. Missing stubs or targets still come only from literatum-patch and the literatum branch (note 04 §7.1). Dailypatch simply surfaces them first, on office copies, as `Dailypatch: Failed Patch Dev.DB : patch litN`.
- **Numbering / ordering:** none of these repos numbers patches. Dailypatch-backend master still assumes SVN:
  - `svn up ~/source/HEAD/atypon/patch` (`SvnInitWrapper.sh:14-18`)
  - `svn log` to find the patch committer to assign the ticket to (`FileUtilities.java:122-145`)
  - `patchparser.sh`

  On today's git checkouts those commands fail silently (exit codes are ignored), so the assignee falls back to `ops`. The rewrite replaces them with `GitInitWrapper.sh`.

## 3. The physio lit32046 case: explained from code

**Symptom** (note 13, beta physio-C8 ProductPatch, 13 Sep 20:41 and 14 Sep 20:45):

```
error with version checking db_version (lit32046): Cannot invoke "Patch.getMetadata()" because "patch" is null
```

at `DbVersionCheck.checkVersion:154`.

**Chain** (the lit-2610 and physio-branch code is identical in `DbVersionCheck`/`DbPatcher`/`PatchLoader` today):
1. `DbVersionCheck.checkVersion` builds the queue. Because the patch plan is always enabled, every executable patch goes through `checkPatchDependency` (`DbVersionCheck.java:127`). That method recurses into the plan's `<dependent-patch>` entries (:249-256).
2. **Before LIT-677519**, that recursion did `if (newPatchTable.containsKey(dep)) { createPatch(meta); if (isExecutablePatch(meta,true)) patchQueue.addLast(dbPatch); }`. It had **no reserved check.**
3. `PatchLoader.createPatch` returns **null** for a truly-reserved JAVA patch (`PatchLoader.java:36-41`). `isExecutablePatch` does not look at `reserved` (`PatchVersionChecker.java:37-100`). So **`null` is queued.**
4. `checkAllowDropColumn()` (`DbVersionCheck.java:133`) iterates `for (Patch patch : patchQueue) patch.getMetadata()` (`DbPatcher.java:115-116`) and throws the NPE. `DbPatcher.java:152-154` rewraps it as `PatchProgram (physio):<msg>`. `DbVersionCheck.java:150-154` wraps it again as `error with version checking db_version (<currentPatchName>)`.
5. **`currentPatchName` is just the last pending file seen in the metadata loop** (:118). lit32046 is the physio-only, beta-only patch (`--@product_parm='physio'`, `--@server_mode_parm='beta'`, release 2610). **It is the reporter, not the culprit.** Note 13's "DB ahead of branch" guess is wrong.

**Fix and timing:**
- `bcad46d544` "LIT-677519 Skip reserved patch dependencies" landed on lit-2610 on 2026-08-24 (master `af6e5221`). It adds `metadata != null && !metadata.isTrulyReserved()`.
- It reached `lit-2610-physio-pcms-260706` only as `523433c4b1` on **2026-09-15 11:28 UTC**, which is after both failures and consistent with them. Only DbVersionCheck commits were checked. The first physio ProductPatch after 15 Sep would confirm it, and I did not look at that.

**Likely null candidate:** in `patchdependency_2610.xml`, the only reserved JAVA dependency is **lit7209** (`reserved='T'`, java). It is a dependent of lit7204 in plans 1820, 1830, 2020, 2210 and 2410. It fires when the physio DB has neither lit7204 nor lit7209 at `status=0`. I have not verified that, because it needs the DB. For the user to run on the physio beta DB:

```
select patchname,status from db_version where patchname in ('lit7204','lit7209');
select name,value from db_info where name in ('release','previous_release','product');
```

**Side effect of the old code:** reserved **SQL** dependencies were queued and **executed** despite `reserved='T'`. Example: lit31028, a dependent of lit31092 in plans 2210 and 2410.

**Next hazard for lit32046:** its stub → `com.atypon.modules.migration.Patch032046` exists **only** on the physio branch (`atypon/publish/src/java/com/atypon/modules/migration/Patch032046.java`). It is absent on lit-2610 and on master. It is harmless elsewhere, because of the product and server-mode gates. But if physio beta moves to a branch without it, the result is a raw `ClassNotFoundException` at `DbPatch.loadDynamicPatch`.

## 4. Failure-signature table

| Signature | Source repo / code | Meaning / cause | Action |
|---|---|---|---|
| `error with version checking db_version (litN): … "patch" is null` (DbVersionCheck:154) | literatum patch system, pre-LIT-677519 | A reserved JAVA plan dependency queued as null. litN is only the last pending file. | Build from a branch with `bcad46d544` (or a cherry-pick of it). Check `db_version` for lit7204/lit7209. |
| Reserved SQL patch runs although `reserved='T'` (old branches) | same | Plan dependency path skipped the reserved check | Same fix |
| `NoSuchMethodException … DbPatchSystem.setTargetDatabase` | platform-tools `DbGradlePatcher.java:46-51` (reflection) + Dailypatch rewrite `--target-database` | Literatum branch forked before IT-24311 (e.g. the physio branch lacks it: `DbPatchSystem` diff) | Only for Dailypatch/external runs. The DS never passes the flag. |
| `Dailypatch: Failed Patch Dev.DB : <desc> [litN] in <env>` (LIT bug, label `patching`) | Dailypatch-backend `TicketManager` | Office-copy rehearsal failure. Classified by `issue-types.yml`: `:Patch lit… failed to execute`, `Missing prerequiste patch`, `doesn't equal your build version`, `Error creating bean with name`, `Cannot get a connection using`, `Cannot updated product`, `timedout`, … | Not a DS failure. Same root causes as ProductPatch, found earlier. Auto-resolves when the product next patches cleanly. |
| `Dailypatch: DB Existence in <env>` | Dailypatch `BuildStage.checkDbExistence` | Office DB `<env>_<product>` missing or unreadable | Clone the DB to the office (DS template "Clone the staging $release DB to the local offices", `jira.xml:626-631`) |
| `Dailypatching Build Timeout [Job…]` P1 | daily-patching Jenkins (stale) | 48 h Jenkins timeout | Historical only |
| ansible `daily-patch` task fails: `grep_for not in daily_patch_result.stdout` | ansible-mssql `roles/daily-patch` | The jdbc pool did not print its "ends" marker (any jdbc patch failure, or a Spring death) | Read the patch.py output. Report-pool-only failures do **not** fail this task. |
| Docker DB has `db_info.product='bpl'` | creation-scripts `2410-passport` (`:93436`) + `replace_minimepb2_with_product.sh.j2` (only rewrites `minimepb2`) | A new 2410 passport docker DB gets the wrong product. The `product_parm` gates evaluate against bpl. | Use the 2610 script, or fix `db_info` |
| `docker cp …/creation-scripts-2610/2610-schema-and-data.sql` no such file | prepare-new-product + creation-scripts layout | Non-passport scripts exist only for 2020/2210/trunk | Set `passport=true` or `mssql_creation_scripts_version` |
| First patch of a fresh docker DB runs hundreds of patches; `There is already an object named…` / `Cannot find the object "dim_…"` / `Invalid column name` | Creation-script snapshot ≈lit3121x vs literatum-patch lit32054 | Seed history is far behind. A patch assuming a live-site state fails (see note 14 catalogue). | Fake the row in `db_version` (the `fake-failing-patches.yml` pattern) or fix the patch |
| `Execution of this patch is faked` in `db_version.description` | ansible-mssql `fake-failing-patches.yml` | lit6024 (and any `failing_patches`) was marked applied without running | Expected on docker DBs |

## 5. Coverage

**Read in full:**
- daily-patching (all 4 files; the 3 pipelines differ only in agent label)
- Dailypatch-backend master:
  - README, Dockerfile, starter.sh, build.gradle
  - application.properties/yml and all 3 yaml files
  - all 9 scripts
  - DailyPatchService, PatchingLoop, PatchingChain, BuildStage, DeployStage, PatchStage, DbUtilities, XmlParser, Validator, TicketManager
  - FileUtilities (to line 164)
- ansible-mssql:
  - `roles/daily-patch`, `roles/prepare-new-product` (tasks/defaults/templates), `roles/prepare-product-database-from-backup` (tasks/defaults)
  - start-patch*.yml, daily-patch.yml, readme.md:34-115
- platform-tools: `docker/build_docker_db_wrapper.sh`, and `DbGradlePatcher.java:36-62`
- literatum-lit-2610:
  - `DbVersionCheck.java` (all), `PatchLoader.java` (all), `PatchType.java` (all), `PoolPatchList.java` (all)
  - `DbPatcher.java:40-195`, `PatchVersionChecker.java:30-260`
  - `DbPatchSystem.java:108-210, 270-380, 620-775`
  - `FilePatchMetadata.java:95-180`
- Physio branch: the 5 patch-system files diffed against lit-2610, and the LIT-677519 commit diff
- `patchdependency_2610.xml`: plan list; plan 2410 (lines 1751-1961) read; all plans scripted for reserved dependencies. Older plans whose `name = "…"` has spaces were only partly parsed.

**Sampled:**
- Dailypatch-backend JiraErrorReporter (grep only), controllers and SshClient (endpoint and timeout grep)
- The rewrite branch: README:1-80, `PatchWrapper.sh` grep, and the commit file list
- literatum-deployment-info: pom and a grep
- cleanupOldPatches.sh:1-60, 280-325
- Creation SQL: first 25 lines, `db_info` rows, `db_version` counts by regex, and 2410↔2610 / 2020↔2210↔trunk diffs by line number and statement type only

**Not read:**
- Dailypatch-frontend and dailyPatchDashboard (unlisted repos)
- The rest of the Dailypatch observers, worker and pilot classes
- The physio DS logs themselves (I relied on note 13)
- Any DB state
