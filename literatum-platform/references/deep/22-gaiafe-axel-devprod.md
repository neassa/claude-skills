# 22 — gaia-fe, axel, developer_productivity: how they work and how they fail

Written 2026-09-25. Read-only. The only writes were this note, scratch files, and `git fetch` into local clones: ansible-gaia `origin/2.0`, and axel branches `b-2.2.85.1`/`b-2.2.88.1` plus tags (the fetch pulled all axel tags).
Secrets: every config/script print was filtered. Lines that carry credentials are listed as "secret-bearing line at file:line", and their values were not copied here.
**One filter miss:** `developer_productivity/cassandraBackup.sh:85` has a hard-coded SFTP user and password in plain text inside an lftp heredoc. It showed up in my output once. It is not reproduced here. Rotate it and move it out of git.
Status tags: **Confirmed** (read in code), **Inferred** (reasoned from code, not seen in a log), **Unconfirmed** (not checkable here).

---

## 0. Coverage

| Repo | Ref (commit) | Read fully | Sampled / grep only |
|---|---|---|---|
| gaia-fe | `57ca328` = tag **`gaia-fe-1.6.7`** (HEAD is the tag, so no extra fetch was needed) | all 8 main classes (`App`, `Beans`, `MultipleBundleDeployment`, `SingleBundleDeployment`, `TransformationTemplateScanner`, `GaiaFeTransformationTemplateLocator`, `GaiaFeTagsProvider`, `api/ConfigFileApi`); `application.yml`; `logback-spring.xml`; `pom.xml`; `kubernetes/docker/{Dockerfile,Dockerfile_gcp,start.sh,updater.sh}`; `kubernetes/gaia/{configinit.sh,configparser.py}` (filtered); `.github/workflows/build-and-push.yaml` (filtered); README | Helm chart / k8s templates, `dev*/`, confd, `gcp-deploy.sh`, Jenkins files (not read); the one test class (name only); `saxon-license.lic` (not opened) |
| gaia library (the server side gaia-fe uses) | **1.7.2 = `20ec949`** (gaia-fe `pom.xml` `gaia.version=1.7.2`) | all 9 `http-server` main classes; core `DirectTransformationTemplate`, `ErrorTransformationTemplate`, `TransformationTemplateParser`, `TransformationTemplateParsingException`, `TransformationTemplateWrapper`, `GaiaException`; http-common `TransformationTemplateMetadata` | `http-client` `GaiaHttpClient` @1.7.3 (grep only; note 15 covers the client). `git diff 20ec949 5761b32 -- http-server core/src/main` is empty, so 1.7.2 and 1.7.3 are identical there. |
| ansible-gaia | `origin/2.0` = `ebb3d9c`. Tree `eb5b379`, which is identical to master `f601ffb`. | `deploy.yml`, `update.yml`, `status.yml`, `group_vars/all`, `atypon_lifecycle.json`, README, `roles/deploy-cluster/{defaults,tasks/*}`, `roles/update-bundle/tasks/*`, `roles/actions/tasks/docker-gaia-action.yml`, `templates/config.xml.j2`; diff of `files/*.sh` against the gaia-fe copies | `library/docker_container.py`, `docker-remove`, `otel_envs.j2` |
| axel | `7a59a7e` (master); tags `v/2.2.88`, `v/2.2.88.1`, `v/2.2.85.1`; branches `b-2.2.85.1`, `b-2.2.88.1` | `pom.xml`; `.github/workflows/{release,manual}.yml` (filtered); `release`, `update-deps`, `run-tests`, `inventory`; `release-scripts/axel-ticket.sh` (filtered); README | the XSL tree (file census only: 365 files under `src/main/webapp/WEB-INF/axel`); `src/main/java` (names only); tests |
| developer_productivity | `724bbbb` (shallow, one commit, so no history) | `schemeConfig.sh`, `schemeOperatoins.sh`, `schemeCloneRestore.sh`, `tier1flexClone.sh`, `schemeBackup.sh` (all 778 lines) — all filtered | `schemeRestore.sh` (733 lines: function list, exits and success strings only; `main()` read — it is disabled); `cassandraBackup.sh`, `cassandraRestore.sh`, `cleanup/*.sh` (core functions and `main` read); the other 20 files are not called by the Deploy Server (grep census) and were not read |
| deployserver | `b726c83` | `actions.xml` GaiaDeploy, GaiaClusterDeploy, GaiaBuild, GaiaFeTagRelease, GaiaDC, the `AnsibleCheckExitCode` library, and all 16 developer_productivity actions; `ActionSpec` and `ValidateResponseTxt` (how success is decided); `SshExecutedVisitor.visitCheckGaiaVersion`; `PreExecuteVisitor` insertion points for DbProductBackup, LocalDbCloneAndRestore, CassandraProductBackup, DbCleanupLocalBackupOnFTP | the remaining Gaia actions (see note 01) |
| platform-tools | `checkoutGitRepo` (`functions.sh:1968-1990`); `bashLogging.sh` (log functions) | — | — |
| deployconf | `ad1c87a` | parsed `<gaia>` and `<cluster>` of midtierbeta, staging and literatum with xml.etree | — |

**Gaps (not in any clone):**
- `~/scripts/do_dbflexclone.sh` on the tools host. It does the tier-1 NetApp flex clone. tier1flexClone.sh only greps its output.
- `C:\scripts\cloneDB.ps1` on the DB server. The repo copy is `winScripts/cloneDB.ps1`, which was not read. The comment at schemeBackup.sh:584 says the server copy must be pushed by hand.
- The patch API at `patch-dc-1`.
- The opstool Rundeck jobs used by the non-DC Gaia path.

---

## 1. gaia-fe 1.6.7

### 1.1 Image and startup (Confirmed)
- **Build.** A GitHub tag push `gaia-fe-<v>` runs `build-and-push.yaml`:
  - `mvn package`, then Docker `kubernetes/docker/Dockerfile_gcp`;
  - pushes `us-central1-docker.pkg.dev/.../atypon-gaia/gaia-fe:<v>` (the tag with `gaia-fe-` stripped, `:50`).
  - The README still describes a Jenkins pipeline.
- **Stack.** Spring Boot 2.7.4 + Jetty (400/20 threads, idle timeout 120 s; `App.java:29-47`), Java 16, Saxon-EE 11.4 (licence file bundled in resources), gaia library 1.7.2. Logs go to stdout as JSON (`logback-spring.xml`, GCP JSON appender).
- **Entrypoint** `/start.sh` (`kubernetes/docker/start.sh`):
  - `TYPE=dc` starts `updater_runner` in the background: `bash /updater.sh; sleep 10` forever (`:82-94`);
  - symlinks `/gaia-fe/config.xml → /mnt/gaia-fe/config.xml` and `/gaia-fe/bundles → /mnt/gaia-fe/bundles` (`:99-100`);
  - then runs `java $JVM_ARGS -jar /app.jar` (`:112-115`).
  - `Dockerfile_gcp:13-14` creates **empty** `/tmp/configs/config.xml` and `/mnt/gaia-fe/config.xml`.
- **JVM args** (ansible `group_vars/all:62`): `-Dcontent.root=/gaia-fe -Dspring.profiles.active=multi`. That makes `MultipleBundleDeployment` active. `SingleBundleDeployment` (`!multi`) is dev only.
- **No Docker volume.** The container gets no `volumes:` (`app-deploy.yml:118-151`, `keep_volumes: false`), so bundles live in the container's writable layer. `force_recreate=true` throws away every installed bundle, and they are all downloaded again.

### 1.2 How bundles are fetched, installed and loaded (Confirmed)

**The scripts that actually run in the container are the image's copies, not ansible-gaia's.**
- ansible-gaia copies its own `start.sh`, `configinit.sh`, `configparser.py` and `updater.sh` to the **host's** `/tmp` (`app-deploy.yml:64-73`) and deletes them afterwards (`cleanup.yml`). Nothing mounts them into the container.
- The copies differ:
  - `configparser.py` is identical (md5 `11fa39c8`);
  - `configinit.sh`, `start.sh` and `updater.sh` differ.
  - The image's `updater.sh` has explicit error messages. The image's `configinit.sh` computes the used bundles from `/tmp/configs/config.xml`; ansible's copy uses `/mnt/...`.
- Notes 03 and 15 cited ansible-gaia's `files/*.sh` line numbers. The code that runs is `gaia-fe/kubernetes/{docker,gaia}/*` @57ca328.

**Step by step:**
1. **Ansible delivers the config.** It writes the new config to `/tmp/configs/config.xml` inside the container:
   - a running container gets `docker cp` (`app-deploy.yml:101-107`);
   - a new or forced container gets `docker exec … base64 -d` (`:166-171`).
2. **`updater.sh` notices within 10 s** (`:18-37`). When the md5 of `/tmp/configs/config.xml` ≠ the md5 of `/mnt/gaia-fe/config.xml`:
   - `configparser.py` collects every `<string>` text in the config into the set of versions;
   - it calls `./configinit.sh <versions>`;
   - on failure it prints `Config initialization failed` and exits 1. The md5 still differs, so it **retries every 10 s forever**.
3. **`configinit.sh`** (`set -ex`):
   - `curl --head --fail $NEXUS_URL`, or `nexus url doesn't exists` and exit 1 (`:8`). `NEXUS_URL` = `nexus_base_url` = `https://nexus.atypon.com/nexus` (`group_vars/all:4`).
   - For each version: a status curl `-o /dev/null -w '%{http_code}'`. **Only 404** triggers `failed to verify bundle <v>` and exit 1 (`:13-14`). 401/403/5xx fall through to the download (Inferred from the flags; the line is secret-bearing).
   - If `/mnt/gaia-fe/bundles/<v>` already exists, it prints `bundle <v> is already installed` and skips it. It never re-checks the content.
   - Otherwise: download (secret-bearing line at `:19`, no `--fail` flag seen), `jar xvf axel-<v>.war || exit 1`, `mv WEB-INF /mnt/gaia-fe/bundles/<v> || exit 1`, `installed <v>`.
   - **Only after all versions install** does it `cp` the config to `/mnt/gaia-fe/config.xml` (`:25`) and print `installed all versions successfully`.
   - Then it immediately `rm -rf`s every bundle directory not named in the new config (`:29-38`, `Deleted unused bundle <b>`).
   - Secret-bearing lines: `configinit.sh:5,13,19` and `start.sh:58`.
4. **gaia-fe `ConfigWatcher`** (`MultipleBundleDeployment.java:47-78`) is a `java.util.Timer` that runs every 1 s from t=0:
   - it reads the mtime of `/gaia-fe/config.xml`;
   - if the mtime changed, it **stores the new mtime first** (`:69-70`), logs `Config file change detected`, then calls `refresh()`;
   - any exception is logged as `Fail to check config file changes` (`:74-75`).
5. **`refresh()`** (`:80-121`):
   - parses the config with `RegistryFactory`;
   - builds a new selector: the default `bundle`, `scopes/<p>/bundle`, and `scopes/<p>/clients/<branch>`;
   - for every bundle name it **reuses the already-loaded bundle of the same name** (`repository.find(name)`). Otherwise it logs `Loading bundle <name>` and calls `scanner.scan(bundles/<name>)`.
   - It swaps in the repository, then the selector (both `volatile`).
   - If anything throws, the old selector and repository stay in place.
6. **Scanner** (`TransformationTemplateScanner.java`):
   - The layout is Axel v2 if `axel/target/wcms/api` exists, otherwise v1 (`axel/api`) (`:198-203`).
   - It registers `wcms/api/base.xsl` and every file under `wcms/api/products/` as `abstract`/`fulltext`/`pdf`, then the optional `wileyml`, `jats`, `rcms` (`details`/`figures`/`tables`/`media`/`supplements`/`references` → `rcms_*`) and `json` directories. Scope = file name without `.xsl`.
   - **Hard requirements at scan time:** the bundle directory exists (`Files.readAttributes`, `:42`) and `<htmlApi>/products` exists (`Files.walk`, `:59`). A missing `base.xsl` is **not** caught at scan time.
7. **XSL is compiled lazily** (`Suppliers.memoize`, `:132,140,148,183`) on the first request that needs the template, including a metadata `GET /template/{id}`.
   - A compile failure (`TransformationTemplateParser.parse` catches every `Exception`) becomes an `ErrorTransformationTemplate`. The FE logs `Failed to parse template with name: <id>, scope: <s>` (`:192`).
   - The error is **memoized for the life of that bundle object**. Fixing the files under the same version name has no effect until a restart or a version bump, because bundles are reused by name.
   - `wileyml` and `jats` templates are **not** memoized (`:164-166,174-176`), so they are re-parsed on every request (a performance issue, Inferred).
   - Missing templates for a product fall back to `base.xsl` with `productId=<scope>` added (`GaiaFeTransformationTemplateLocator:65-89`, log `Using base templates for scope <s>`).

### 1.3 HTTP API (Confirmed; gaia `http-server` @20ec949 + gaia-fe)

| Endpoint | Behaviour | Error |
|---|---|---|
| `GET /bundle?scope&client` (text) | Bundle name from the **current selector**. Lookup order: (scope, client) → (scope, "") → parent scopes → root default. | `GaiaException` with no message → **500** |
| `GET /templates?scope&client` | Metadata list for the scope | 500 if no bundle |
| `GET /template/{id}?scope&client` | `{id, scope, status: ready\|unavailable, timestamp, errors[]}`. This call **compiles the XSL**. | 404 `NotFoundException`; 500 if no bundle |
| `POST /template/{id}?scope&client` | Runs the transform and returns the output | 500 carrying the GaiaException message (`server.error.include-message: always`) |
| `GET /config` (gaia-fe `ConfigFileApi`) | Raw `/gaia-fe/config.xml` from disk | 404 if missing |
| `/actuator/{info,health,prometheus,threaddump,heapdump}` | `info` gives `build.version`. Metrics carry scope/client/template tags (`GaiaFeTagsProvider`). | — |

- Literatum (http-client 1.7.3) calls `/bundle`, `/templates`, `/template/{id}` (GET and POST) and `/actuator/info` (note 15 §1.2).
- **Health:** no `HealthIndicator` or `@ControllerAdvice` exists anywhere in gaia-fe or the gaia http-server (grep). `/actuator/health` is Spring's default (ping + disk), so it is **UP with zero bundles loaded**.
  - This is the only check used by the Docker healthcheck (`app-deploy.yml:140-145`) and by ansible `status` (`docker-gaia-action.yml:8-17`).
- **Useful probe (Inferred):** compare `GET /config` (the new file on disk) with `GET /bundle?scope=<p>&client=<branch>` (what is loaded).
  - They disagree when the refresh failed.
  - `/config` stays old while bundles are still downloading, or when Nexus lacks a bundle.

### 1.4 Startup race (Inferred from code)
1. A new or forced container starts with an empty `/mnt/gaia-fe/config.xml`.
2. `ConfigWatcher` fires at t=0, and parsing the empty file fails (`Fail to check config file changes`). The selector is empty, so `/bundle` returns 500 while health says UP.
3. Ansible then writes the config, `updater.sh` downloads **every** bundle (all versions, fresh), and only then does `config.xml` change and the bundles load.
4. `deploy.yml` is `serial: 1` but does not wait for the bundles to load. With `force_recreate=true`, each host can serve no bundles for the whole download window while the playbook moves on and reports success.

---

## 2. axel (the XSL bundle)

- **Layout (Confirmed).**
  - Maven `com.atypon:axel`, `packaging war`. `WEB-INF/lib/*.jar` is excluded, and classes are attached.
  - The XSL lives under `src/main/webapp/WEB-INF/axel/`:
    - `target/wcms/{api(80),products(58),preparation,finalization}`
    - `target/rcms/{api(42),products(39)}`
    - `target/{jats,json,wileyml,markdown,xhtml,cms}`
    - legacy v1 `axel/products/*.xsl`, `schemas/`, `transforms/`
  - The war therefore unpacks to `WEB-INF/axel/target/wcms/api/...`, which is exactly the path the scanner's `AxelV2Paths` expects.
  - It depends on `baja` (war, 2.2.78) and `schemas` (war, 1.2.15), and on Saxon-EE 11.4.
- **Versioning (Confirmed).**
  - `maven-release-plugin 2.5.3` with `tagNameFormat v/@{project.version}`. Master pom is `2.2.89-SNAPSHOT`.
  - **4-part versions are hotfix branches** `b-<x.y.z.n>`. For example `b-2.2.88.1` holds `v/2.2.88` + LIT-682951 (APS cover date) and releases `v/2.2.88.1` (`716f7d3e`, 2026-09-21); its pom is now `2.2.88.2-SNAPSHOT`.
  - 4-part tags that exist: 2.2.63.1, 2.2.82.1-.3, 2.2.85.1, 2.2.88.1.
  - There are also `v/2.2.75.pb4`, `.77.pb4` and `.78.pb4` tags.
  - 218 tags in total.
- **Publishing (Confirmed).**
  - `release.yml` (workflow_dispatch) runs `release:prepare` + `release:perform` with `distributionManagement` = **GAR** `us-central1-maven.pkg.dev/atypon-artifact/maven` (`pom.xml:195-204`). Snapshots go to `maven-snapshot`.
  - Optionally it bumps baja first and adds a Jira comment.
  - The Deploy Server step (`AxelVersionAutomationWorkflow`) is **commented out** (`release.yml:162-167`).
  - The tag push fires `manual.yml` → `axel-ticket.sh`, which opens three LIT "Release Axel (version v) - Staging/LTS/Midtierbeta" tasks for ops.
  - **Nothing in axel publishes to Nexus.** Whether Nexus gets the war (proxy or mirror of GAR?) is **Unconfirmed**. There is a branch named `Nexus_readonly`. This is the key question for the GAR-vs-Nexus split.
- **deployconf today (`ad1c87a`).** Non-3-part `bundle_version`s:
  - beta: 2.2.82.3, 2.2.85.1;
  - staging: 2.2.82.3, 2.2.85.1, 2.2.88.1;
  - prod: 2.2.82.2, 2.2.82.3, 2.2.85.1 (54 products).
- **What a broken bundle looks like at runtime (Inferred from the gaia-fe code):**
  - *XSL compile error:* metadata `status: unavailable, errors:[<Saxon message+location>]`, FE log `Failed to parse template…`, Literatum `GaiaException: Template with name: <id>, scope: <p> is not available. Error: …`.
  - *Missing `base.xsl` or included file (IOException):* the same, but `errors` is **empty** (the parser records only TransformerExceptions), so Literatum's message ends with `Error: ` and nothing after it.
  - *Missing `wcms/api/products`, or the war is not an Axel v2 layout:* the scan throws `NoSuchFileException`, `Fail to check config file changes`, the new config is not applied, and the old bundles stay.
  - *Download is an HTML error page (no `--fail`):* `jar xvf` fails and configinit exits 1, so the updater retries forever and the config is never applied.

---

## 3. Verdicts on the notes/15 claims

| # | Claim | Verdict | Evidence |
|---|---|---|---|
| 1 | GaiaDeploy verifies the bundle in GAR, but the container downloads from Nexus | **Confirmed** | GAR HEAD: `ansible-gaia/roles/deploy-cluster/tasks/check-bundle.yml:21-30@ebb3d9c`. Download: `gaia-fe/kubernetes/gaia/configinit.sh:8,13,19@57ca328` with `NEXUS_URL=nexus_base_url` (`group_vars/all:4`, `app-deploy.yml:32`). Correction to notes 03/15: the running script is the **image's** copy; ansible's `files/configinit.sh` never reaches the container (`app-deploy.yml:64-73`, `cleanup.yml`). Also, `update.yml` skips the check entirely. |
| 2 | The version regex truncates 4-part versions | **Confirmed** | `check-bundle.yml:18` `regex_findall('\\d+\\.\\d+\\.\\d+')`. Re-run in Python: `2.2.85.1→2.2.85`, `2.2.88.1→2.2.88`, `2.2.75.pb4→2.2.75`. A missing `2.2.88.1` passes if `2.2.88` exists in GAR. |
| 3 | Bundles install asynchronously after the playbook returns | **Confirmed** | The playbook ends after `docker cp`/`docker exec` of `/tmp/configs/config.xml` (`app-deploy.yml:101-107,166-171`). The install happens in `start.sh:82-94` (updater every 10 s) → `updater.sh:18-37` → `configinit.sh`. The Deploy Server success test is only `COMPLETED SUCCESS` from `$?` of ansible-actions (`actions.xml:1191-1203`, library `:2794-2798`). |
| 4 | A missing bundle folder means gaia-fe keeps the old config until config.xml changes | **Partly right; the mechanism differs** | For the **common** case (bundle absent in Nexus, or a download error): configinit exits **before** copying the config (`configinit.sh:12-25`), so `/mnt/gaia-fe/config.xml` never changes and gaia-fe never even tries. The updater retries every 10 s forever. `NoSuchFileException` / `Fail to check config file changes` happens only when the directory exists but is broken (no `…/api/products`) or was deleted. In that case the mtime was already recorded (`MultipleBundleDeployment.java:68-72`), so there is no retry until the next config change. **Extra risk:** configinit deletes unreferenced bundles right after copying the config (`:29-38`). If the refresh then fails, the old selector points at deleted directories, and any not-yet-compiled template fails (memoized). |

**Additional confirmed deploy gaps (ansible-gaia 2.0):**
- **An image tag change is not applied** unless `force_recreate=true` or the container is not running. The "Deploy container" task has `when: not container_running or force_recreate` (`app-deploy.yml:150-151`). The default GaiaDeploy `$recreate=false` only swaps the config. Deploy succeeds, and the old image keeps running.
- The health check can pass while no bundles are loaded (§1.3).

---

## 4. developer_productivity: what the Deploy Server calls

**How success is decided (Confirmed).**
- `ValidateResponseTxt.isValid` returns true if **any line of the action log contains** the validate text. `or-validate-txt` ORs, `validate-txt` ANDs (`ActionSpec.java:29-44`).
- **Exit codes are ignored** for all of these actions.
- None of them has a custom `SshExecutedVisitor` parser (grep).
- Every action first runs `checkoutGitRepo developer_productivity` (`platform-tools/functions.sh:1968-1990`): reset/fetch/pull of `master` with **no error checks**. A git failure silently runs the stale checkout. The clone line is secret-bearing (`:1987`).

| DS action (actions.xml line) | Script and args | Validate text | What it does | Failure / success-while-broken |
|---|---|---|---|---|
| **DbProductBackup** (559; inserted by `CipProductAdd` when `enableDbProductBackup`, `PreExecuteVisitor:1695`) | `schemeBackup.sh -a acct -p prod [-c fam] -f` \| `-s -i "$selectedTables"` | `finished successfully` | **Nothing.** `main()` prints `The schemeBackup.sh script is no longer used as part of LIT-675060.` and exits 0 (`schemeBackup.sh:739-742`). | **Always Failed**: the text never appears, even though rc is 0. Any CipProductAdd with backup enabled goes red. |
| **DbReportProductBackup** (582) | `schemeBackup.sh … -R ticket -s` | `database finished successfully` | same as above | **Always Failed** |
| **CipLocalTier1DbRestore** (1138), **CipLocalDbRestore** (1164), **CipLocalRestoreIndividualDBProcess** (1824), **CipLocalRestoreIndividualReportDBProcess** (1831) | `schemeRestore.sh -a … -p … [-f] [-d] [-i\|-R ticket]` | `finished successfully` / `database finished successfully` | **Nothing.** `main()` prints `The schemeRestore.sh script is no longer used as part of LIT-675060.` and exits 0 (`schemeRestore.sh:687-690`). | **Always Failed** |
| **LocalDbCloneAndRestore** (287; inserted by ProductRelease when `runDbBackup`, `PreExecuteVisitor:2925`) — tier 2 | `schemeCloneRestore.sh -a acct -p prod [-f fam]` | `Restoring database finished successfully` | Same-server clone of `LITERATUMDB` into `${acct}_${prod}` (or `cip_${fam}_${prod}`):<br>1. creates an empty DB on R:<br>2. `C:\scripts\cloneDB.ps1` through `xp_cmdshell` (secret-bearing `:223`)<br>3. if the target exists, clones to `_new`, drops the old one and renames (single-user → offline → rename files → online)<br>4. `ALTER USER <prod> WITH login`<br>5. on literatum, sets `postclone_cleanup_done` | **Fails on:** tier ≠ 2 (`Only tier-2 products are supported…`, `:90`), a missing source DB, a create failure, clone output matching `exception\|error\|failed\|level` (the DB is dropped), rename errors.<br>**Success-while-broken (Inferred):**<br>- `cloneDB` captures stdout only, so a sqlcmd connection error on stderr leaves an empty result → treated as success with an empty or partial DB;<br>- table count is logged (`getNumOfTables`) but never compared;<br>- `dropOldDatabase` ignores any error that is not deadlock/single-user/"Cannot drop" (`schemeOperatoins.sh:117-143`);<br>- `loginMapping` is unchecked. |
| LocalDbCloneAndRestore — tier 1 (and cabi) | `tier1flexClone.sh -a acct -p prod [-f]` | same | 1. `~/scripts/do_dbflexclone.sh` from the prod DB server/DB in `deployconf.literatum.xml` into `${acct}_${prod}`; success = output contains `hasbeenclonedsuccessfully` (spaces stripped)<br>2. `check_release` sets `db_info.release` from the `lit-NNNN` in `<source>`<br>3. POSTs `http://patch-dc-1.int.atypon.com/api/v1/patch/database` and accepts 200 **or 202** | **Fails on:** tier ≠ 1, missing deployconf values, no `lit-NNNN` in `<source>`, flex clone not reporting success, empty release, patch HTTP ≠ 200/202.<br>**Success-while-broken:**<br>- the `db_info` UPDATE results are never checked;<br>- a non-numeric release only warns;<br>- **202 = queued**, so the DB is reported ready before it is patched (Inferred);<br>- deployconf `git commit`/`git push` are unchecked (cip `-c` path only). |
| **DbProductRestore** (191; cip only) | tier 2 `schemeCloneRestore.sh -a $account … -c`; tier 1 `tier1flexClone.sh … -c` | `Restoring database finished successfully` | CIP copy `cip_${prod}_${fam}_${acct}_<date>`, then edits and pushes `deployconf.cip.xml` and drops the older CIP DB | `$account` is never `#set` in this action; its value depends on the DS velocity context (**Unconfirmed**). With `-a cip` + `-c` → `Invalid options: cannot combine -a cip with -c` (exit 2). A tier other than 1/2 runs nothing → Failed (no text). The deployconf push result is unchecked. |
| **LocalAndCipT1DbRemove** (314) | `tier1flexClone.sh -a … -p … [-f] -r` | `Database removal finished successfully` | `do_dbflexclone.sh -o remove_only`; success = the literal `Congratulations! ... Database Clone were deleted, Please verify!` | Tier-2 products run **nothing**, so Failed with no message. On non-cip accounts the target name is **computed** (`${acct}_${prod}`), not read from deployconf as the usage text says (`:183-185`). |
| **CassandraProductBackup** (1069; ProductRebuild `PreExecuteVisitor:725`) | `cassandraBackup.sh -a acct -p prod -f fam` | `Cassandra finished successfully` | Deletes old backups first, then `ansible-actions -s cassandra -p prod -f fam -a backup -e keyspace_prefix=vos …`. The result is `mv`ed to the archive, or lftp-uploaded for `cip_*`. | **No Cassandra configured** → logs `No Cassandra Configured` then `exitHandler 0` → `ERROR --- 0 ,,, Exiting` → **Failed** although benign (`:64`). rc ≠ 0 from ansible → fail. **Success-while-broken:** `mv` and lftp upload are unchecked; the old backup is deleted before the new one exists. Secret-bearing line `:85` (hard-coded, see header). |
| **CassandraProductRestore** (1062; cip) | `cassandraRestore.sh -a $sourceEnv -p prod` | `Cassandra finished successfully` | Checks for `<acct>_<prod>.ini` on tools-1, scp's it to every node of the default cluster, runs `ansible-actions -s cassandra -n <cluster> -a restore`, then creates the product-catalog Solr collections | Fails on: backup missing on FTP, a remote result containing `Failed`, ansible rc ≠ 0. `status1` checks `$?` of an assignment (`:98-99`), but `:102` covers it. The `githubUtils.py clone` result is unchecked. |
| **CipLocalDBIndividualRemoveProcess** (1838), **CipLocalReportDBIndividualRemoveProcess** (1846), **CipCleanupLocalDbBackup** (2220) | `cleanup/cleanupBackupAndDatabaseOnDevDBServer.sh -p -a [-f\|-i\|-R]` | `Cleanup Database on Dev DB completed successfully` | Deletes the `.bak` under `R:\Backup\Schema_Cloner_<Acct>` and drops the DB | Fails on: unsupported account (`:91`), drop error. Success when nothing is found (both are just logged). `$product`/`$account`/`$family` are not `#set` in these actions (context-dependent, **Unconfirmed**). |
| **DbCleanupLocalBackupOnFTP** (2200), **DbReportCleanupLocalBackupOnFTP** (2212) | `cleanup/cleanupBackupOnFTP.sh -p -a [-f\|-R]` | `Cleanup backup on FTP completed successfully` | `rm -f` of the `.bak` under `/archive3/.../DB/<acct>/`; the CIP path goes over ssh tools-1 | The CIP path's heredoc `exit 1` on remove failure is **not checked**, so the success line still prints. A missing file or folder counts as success. |

That makes 16 DS actions and 8 scripts (`schemeConfig.sh` and `schemeOperatoins.sh` are sourced). The other 22 files in the repo have no DS reference (grep of `deployserver/config` + `src`).

---

## 5. Failure-signature table

| Signature | Where | Meaning | Status |
|---|---|---|---|
| `FAILED - … version_check.status != 200` on `axel-<x.y.z>.war` | GaiaDeploy, `check-bundle.yml:21-30` | 3-part version missing in GAR (a 4-part one is checked as its 3-part parent) | Confirmed |
| GaiaDeploy `COMPLETED SUCCESS`, pages still old; container log `failed to verify bundle <v>` or `Config initialization failed` every 10 s | image `configinit.sh:14`, `updater.sh:27-29` | Bundle not in **Nexus** (e.g. a 4-part hotfix released only to GAR). The config is never applied, and it retries forever. | Confirmed code / Inferred runtime |
| Container log `nexus url doesn't exists` | `configinit.sh:8` | Nexus unreachable from the host network | Confirmed |
| Container log `jar xvf` ZipException / `mv: cannot stat 'WEB-INF'` | `configinit.sh:19-21` | Download returned an error page (no `--fail`) or a non-Axel war | Inferred |
| gaia-fe `Fail to check config file changes` + `NoSuchFileException …/bundles/<v>/…/products` | `MultipleBundleDeployment:74-75`, scanner `:42,59` | Bundle directory broken or deleted, or not an Axel v2 layout. The old config stays until the next config change. | Confirmed code |
| gaia-fe `Fail to check config file changes` just after container start | same, parsing the empty `config.xml` | Normal during a fresh or forced start. `/bundle` returns 500 until the bundles download. | Inferred |
| gaia-fe `Failed to parse template with name: <id>, scope: <s>`; metadata `status: unavailable` | scanner `:192`, `TransformationTemplateMetadata:38-47` | XSL compile error in the bundle. Memoized until restart or version bump. | Confirmed |
| Literatum `… is not available. Error: ` with nothing after it | Literatum locator + parser `:39-40` | IOException (missing include or base file), not an XSL error | Inferred |
| Literatum `Request to Gaia FE failed with code 500` on `/bundle`/`/template` | `BundleApi:24`, `TemplateApi:32,38` | No selector match: empty or unloaded config | Confirmed |
| Health UP, but renders fail or are stale | `/actuator/health` default only | Health says nothing about bundles. Compare `/config` with `/bundle`. | Confirmed |
| New `image_tag` in deployconf, GaiaDeploy green, old image still running | `app-deploy.yml:150-151` | `force_recreate=false` with a running container → config swap only | Confirmed |
| `The schemeBackup.sh script is no longer used as part of LIT-675060.` then action **Failed** | DbProductBackup, DbReportProductBackup | Script disabled; the validate text can never match | Confirmed |
| `The schemeRestore.sh script is no longer used as part of LIT-675060.` then **Failed** | CipLocal*Restore* (4 actions) | same | Confirmed |
| `Only tier-2 products are supported by this script for now (got tier: N)` | `schemeCloneRestore.sh:90` | Tier mismatch or empty `<product-tier>` | Confirmed |
| `Only tier-1 products are supported by this script (got tier: N)` | `tier1flexClone.sh:147` | same | Confirmed |
| `Flex clone did not report success for <db>` | `tier1flexClone.sh:267` | `do_dbflexclone.sh` failed (script not in any repo) | Confirmed |
| `Could not extract sourceRelease (lit-XXXX) from: …` | `tier1flexClone.sh:222` | deployconf `<source>` has no `lit-NNNN` (e.g. a master/trunk source) | Confirmed |
| `Patch API failed (HTTP <n>)` | `tier1flexClone.sh:418` | Patch service at patch-dc-1 | Confirmed |
| `Invalid options: cannot combine -a cip with -c` | both clone scripts | DbProductRestore run on the cip account | Confirmed |
| `ERROR --- <exception/error/level text> ,,, Exiting` after `Beginning cloning script` | `schemeCloneRestore.sh:227-231` | `cloneDB.ps1` error; the target DB was dropped | Confirmed |
| `Failed with: SET SINGLE_USER … DROP DATABASE` after 19 retries | `schemeOperatoins.sh:137` | Sessions holding the DB | Confirmed |
| `No Cassandra Configured for <p>` + `ERROR --- 0 ,,, Exiting` → Failed | `cassandraBackup.sh:64` | Benign: the product has no Cassandra | Confirmed |
| `ansible actions exited with non-zero exit status` | cassandra scripts `:70` / `:91` | ansible-cassandra backup or restore failed (note 03 §4) | Confirmed |
| Green DB clone, but empty or partial DB, wrong release, or unpatched | clone scripts | Unchecked stderr / UPDATEs / a 202 from the patch API (§4) | Inferred |
