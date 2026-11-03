# 36 — Dailypatch UIs (frontend, dashboard) and the ui-theme-* repos

Written 2026-09-27, read-only. I ran nothing except `git fetch --depth 1` of tags/branches, `git ls-remote`, and two read-only Jira JQL searches. Every repo file went through `tools/safe_view.py`; secret-bearing lines are cited by file:line only. Follows notes 25 (Dailypatch-backend), 20/24 (styleguide toolchain, marlin) and 06 Part B (ui-products, BDS).

## 0. Coverage

| Repo | Ref read | Read fully | Sampled / not read |
|---|---|---|---|
| Dailypatch-frontend | master `4d4426c` 2023-07-20 (single-commit shallow clone; 1 branch on origin) | README, Dockerfile, pom, all 3 properties/yml, all controllers, DashboardService, all 9 models, index.jsp (758 lines), LogViewer.jsp, index.js, LogViewer.js | CSS not read |
| dailyPatchDashboard | master `71834dc` 2022-08-25 (shallow) | pom:1-25, application.properties, controller mapping grep, DailyPatchService:1-70, file list diffed against Dailypatch-backend master | the rest (it is the predecessor of Dailypatch-backend, see §1.3) |
| Dailypatch-backend | master `e4c1526` (local); **`refactor/simplify-architecture` `31a881e` 2026-08-02 fetched shallow** — this is the deployed code | rewrite: README (all), ProductController (all), DashboardStats, TicketMessageFactory:1-45; grep of DailyPatchService, JobState, PatchController, application.properties | master controllers by mapping grep only |
| ui-theme-classic | develop `a2764ff` 2026-09-10; tags **v2.8.74, v2.8.84, v2.8.85** fetched shallow | package.json (develop + 3 tags), README:1-90, AGENTS.md (all 111 lines), postinstall.sh, buildci.sh, bundler.config.js, `.github/workflows/{build,deploy}.yml`, top-level layout | scss/jade content not read |
| ui-theme-photo | develop `eb5a1ea` 2026-09-21 | package.json, deploy.yml, layout | rest |
| ui-theme-eureka | develop `6a48542` 2026-09-23 | package.json, layout | rest |
| ui-core | tag **v2.8.81** fetched shallow | package.json at v2.8.81 | — |
| ui-products | develop `7f77198e1d` 2026-09-25 + the 5 local maint branches | `.gitmodules`, `ux3/{package.json,bundler.config.js,README.md}`, `aiaa/package.json`, `utoronto/package.json` (grep), marlin + marlin/cell package.json on all 6 refs (version probes), `git submodule status` | other products only via a `#develop` theme-pin grep |
| styleguide-bundler | main `9fb5025` (1.4.7) | `src/core/install/DependencyInstaller.ts` (all 176 lines) | rest covered in note 20 |
| platform-tools | `b00c49f` | BDS:160-232, 268-304; functions.sh:740-760 | — |
| puppet-control | local clone | `data/servertype/patch.yaml:1-95`, `patchserver.pp:125-165`, 2 node files | — |
| Jira (read-only JQL) | — | `summary ~ "Dailypatch"` top 50; `labels = patching AND created >= 2025-05-01` (count); full read of LIT-658534, LIT-660942, LIT-660943, LIT-676662 | — |
| Ops repos scan | k8s-opstools, ansible-*, opstool, deployserver, rd_jobs, platform-tools (2503 files) | grep for dailypatch/patchdash/patch-dc/patch-jo/patch-sc | — |

Secret-bearing lines (not read, masked by safe_view): `dailyPatchDashboard/src/main/resources/application.properties:20-22, 38, 44-46` (JDBC, SSH and Jira credentials committed in plaintext); `Dailypatch-backend` rewrite `application.properties:25`; `puppet-control/data/servertype/patch.yaml:27-28`. **Dailypatch-frontend renders the office DB credentials into the HTML page** (`index.jsp:434-437` and `:720-725`, "JDBC Url … Db Creds: …") — every viewer of the dashboard sees them.

## 1. Dailypatch UIs

### 1.1 What the three repos are

| Repo | What it is | Live? |
|---|---|---|
| **dailyPatchDashboard** (2022-08) | The **first Dailypatch backend**, Maven/Spring Boot 2.6, package `com.atypon.DailyPatch`, "Daily patch API" (`pom.xml:17`). Same REST surface as Dailypatch-backend master (`/api/v1/products/{meta,queue,active,previous,logs/…}`, `/api/v1/patch/…`), a `Pipeline/*` chain, SSH to `patch-jo` (`application.properties:26,35`), MongoDB, Jira. No web views despite the JSP prefix lines. Dailypatch-backend master (2024, Gradle) is its rewrite, and `refactor/simplify-architecture` (2026-08) is the rewrite of that. | **Stale** — superseded twice. Only value: history and the plaintext creds it leaks. |
| **Dailypatch-frontend** (2023-07) | Spring MVC + JSP + Bootstrap dashboard, a pure REST client of the backend ("has no influence over the patching process i.e) only for monitoring", README:3 — **not true**, see below). Calls `http://<office host>:6767/api/v1/products/…` (`DashboardService.java:53-157`, `application.properties:6,12,23`). Office hosts: Jordan `patch-jo02.atypon.com`, Santa Clara `patch-sc01.atypon.com`, Athens = an unrelated PHP page `http://10.1.200.9/index.php?env=staging&db=hera`. | **Stale and incompatible with the deployed backend** (see 1.2). Replaced in 2026-02 by a **React dashboard whose repo is not in the list** (LIT-658534 comment 2026-02-02: "Made a new dashboard that is written in React … deployed at http://cipsc-services-3.atypon.com:3000/"). **Model gap.** |
| Dailypatch-backend `refactor/simplify-architecture` | Java 21, MongoDB, one `PatchExecutor`, SSH to workers. Deployed on **`patch-dc-1.int.atypon.com:6767`** with workers `patch-dc-1/2/3.int.atypon.com` as user `dailypatching` (README:111-126); also reachable through nginx/Cloudflare on `:80` (LIT-676662 comment 2026-08-19). Swagger at `/docs` (README:106-107). | **Live** (endpoint verified by Hadeel on 2026-08-19, LIT-676662). |

### 1.2 What the frontend shows, and why the 2023 JSP cannot be what is running

Page `index?office=jordan|santa-clara&env=all|staging|midtierbeta|office-santaclara-cip|lts|migration` (`index.jsp:89-180`; **no production env exists — Dailypatch never touches prod**):
- Header counters from `GET /meta` → `Metadata{currentlyActive, successfulPatches, failedPatches, queueSize}` (`index.jsp:56-77`).
- **Queue tab**: per product `name/family`, `branch/env`, office DB `dbName/dbServer/dbCreationDate`, and three buttons Build / Deploy / Patch coloured by `progress.{build,deploy,patch}` ∈ `IN_QUEUE|IN_PROGRESS|SUCCESS|FAILED|TIMED_OUT|DB_CHECK` (`StageStatus.java`). Success/failed buttons open `/logFile/{office}/{env}/{action}/{product}`, in-progress opens `/logviewer` which polls the same URL every 3 s (`LogViewer.js:24-37`).
- **History tab**: previous runs with `failure` badge, last action time, `lastSuccessfulPatch`, the open Jira ticket (`ticketKey` → `openTicket` URL) and a **Rerun button** that does `POST /rerun/…` → backend `PUT /api/v1/patch/push/{env}/{branch}/{product}` (`DashboardService.java:160-170`, `index.js:55-63`). So the dashboard **can** trigger work on the patch VMs; it is not read-only. Anyone on the office network can re-queue a build.
- No auth anywhere; the backend has `@CrossOrigin(origins="*")`.

Against the deployed backend (`refactor/simplify-architecture`):
- `GET /api/v1/products/meta` **no longer exists** (replaced by `/stats` and `/stats/{env}` returning `DashboardStats{queued,running,completed,failed,cancelled,failedAtBuild/Deploy/Patch,byEnvironment,computedAt}`). `getIndex` calls `getMetadata` first → RestTemplate 404 → the JSP index 500s.
- `/previous` now returns a paged `Map{content,page,size,totalElements,…}` (`ProductController.java:82-114`), not `List<ProductWrapper>`; job model is `JobState{status, currentStage, buildResult/deployResult/patchResult{status,executionId,…}, failureReason, ticketKey, ticketUrl}` — none of the JSP `product.progress.build` paths resolve.
- Logs are now per **`executionId`**, not per product (`ProductController.java:185-201`).
- `/active` exists, `/success`, `/failed`, `/jobs/{env}/{branch}/{product}`, `/environments`, `/branches` exist; `PUT /push/async/…` was added "for the dashboard" (`PatchController.java:98-100`).
- The frontend's hosts (`patch-jo02`, `patch-sc01`) are the old office VMs. LIT-660942 (2026-02/04): patch-jo01/02 offline, patch-sc01 crippled by Falcon, patch-gr useless; resolved 2026-05-07 with "effort to migrate to DC in IT-23685". Backend now runs on `patch-dc-*` (README; `functions.sh:747` special-cases `patch-dc-*`). puppet-control has servertype `patch.yaml` (user `dailypatching`, docker, lit-2210/2020/2010/1910 checkouts — stale list) but **no `patch-dc-*` node files** (only `daily-patching`, `patchgr`, `patch-jo`): the DC VMs are managed elsewhere. Model gap.

### 1.3 Where the data comes from
Backend only. The backend reads product inventory from `~/.litconfig/deployconf.{migration,lts,cip,staging,midtierbeta}.xml` (`DEPLOYCONF_FILES`, README:17-21, `application.properties:9`), runs `rebuild.py → redeploy.py → patch.py` over SSH on the workers against **office copies** named `<env>_<product>` (CIP keeps its LITERATUMDB name), stores `JobState` in MongoDB, and serves it. It does not read the Deploy Server, and the Deploy Server does not read it (note 25). Jira is written, never read, by the backend.

### 1.4 Is any of it a read-only signal for "will tonight's ProductPatch on prod fail"?

**Partly, and only through the live React dashboard / REST API, not through Jira and not through these two repos.**

- **The Jira signal is dead.** JQL `project = LIT AND labels = patching AND created >= 2025-05-01` → **0 issues**. The newest `Dailypatch: Failed Patch Dev.DB : …` bug is LIT-626474, **2025-04-18**. Since the 2026-02 relaunch the backend runs with Jira **off** by default (`jira.enabled=${JIRA_ENABLED:false}` semantics per README:14; the documented production `docker run` (README:114-126) sets `GNOTIFY_ENABLED=true` but **not `JIRA_ENABLED`**). LIT-658534 comment: "running on one VM with Jira disabled". So "no Dailypatch bug in LIT" means nothing today. Timeout notifications go to Google Chat (`GNOTIFY_ENABLED`), failures are only in the dashboard/Mongo.
- **What to read instead (read-only GETs, from the office/VPN network):**
  - `http://patch-dc-1.int.atypon.com:6767/api/v1/products/stats` — `failed`, `failedAtPatch` since the 01:00 GMT+3 run (`DailyPatchService.java:400`; master branch at 05:00, `:425`).
  - `…/products/failed` — the `JobState`s with `status=FAILED`: look at `environment`, `branch`, `patchResult.status`, `failureReason`, then `…/products/logs/{env}/patch/{executionId}` for the patch.py output.
  - `…/products/previous?size=100&status=FAILED` — paged history.
  - Dashboard: `http://cipsc-services-3.atypon.com:3000/` (LIT-660943, still Open: the old DNS name `daily-patch-center.atypon.com` points at the dead qa35).
- **How to read it as a prod predictor.** Dailypatch patches `staging_<product>` / `midtierbeta_<product>` copies on the *staging/beta literatum branch of that product* (`Product.branch` from the env deployconf). Tonight's prod ProductPatch runs the prod branch against the prod DB. So a Dailypatch failure is a leading indicator only when (a) the failing patch file is also pending on prod's `db_version` and (b) the prod branch has the same patch code (same `lit-2610-maint-*` line). A `patchResult.status=FAILED` with `failureReason` matching a `issue-types.yml` class (`Patch lit… failed to execute`, `Missing prerequiste patch`, `doesn't equal your build version`) on **staging** for the same product is the useful case; `failedAtBuild`/`failedAtDeploy` say nothing about the DB. A clean Dailypatch is **not** a green light: office copies are refreshed from prod only when someone clones them (DS template "Clone the staging $release DB to the local offices"), and prod-only/beta-only patches (`--@server_mode_parm`) never execute in the rehearsal (the lit32046 case in note 25 §3 would have been invisible).
- **Caveat:** I have not opened either URL; reachability and the exact `/api/v1/products` prefix (masked by safe_view; LIT-658534 says "/products/previous") are inferred from code and tickets.

## 2. ui-theme-{classic,photo,eureka}

### 2.1 What a theme provides
A theme is a **git-installed npm package** (no registry publish, no tag workflow) laid out like a product: `basic/`, `components/`, `widgets/`, `templates/`, `page-structure/`, `plugins/`, `scss/`, `js/`, `sourceJs/`, `fonts/`, `images/`, `locales/`, `config.json`, `info.json`, `index.jade`, `bundler.config.js`. Content by count (classic): 399 `.jade` templates, 286 `.json` widget/component configs, 157 `.scss`, 56 `.js`; eureka is TypeScript-heavy (194 `.ts`) and ships design tokens (`figma-tokens.json`, `variables.json`, `ui-theme.d.ts`, `public.config.js`). Layering is product → theme → libraries (`AGENTS.md:20`):

```
ui-theme-classic            (tag vX)
  ├── ui-article            (git tag)
  └── ui-core               (git tag) → ui-base (git tag) → ui-article
```
(`AGENTS.md:99-111`). The theme's `bundler.config.js` is the same 2-line `BuildController.init(__dirname, require.resolve)` as a product, so the styleguide site can build it standalone. `postinstall.sh` symlinks `node_modules/{ui-core,ui-article}` to the parent's copies when installed as a module ("second layer"). Only ux3's postinstall is run by the bundler (`DependencyInstaller.ts:124-135`); for a product build the theme's postinstall runs inside npm during `npm i`.

**package.json `version` is meaningless**: classic tags v2.8.74/84/85 all carry `"version": "2.6.0"`, develop says `2.11.0`; photo develop `2.11.0`, eureka `2.11.0`. Never read the version from the file; read the tag.

### 2.2 How a product pin is resolved at build
1. BDS checks out `ui-products` at the SG branch, runs `git submodule init && git submodule update --remote` (**checked**, BDS:296-302, for **every** product, not just ux3), installs `utypon-cli`, runs `utypon build optimized` (note 06 B2).
2. `DependencyInstaller.optimizedDependencyInstall` (`:88-122`) loops over `package.json.dependencies` **in file order**, ignoring any lockfile. For `ui-theme`, `ui-core`, `ui-theme-*` and the config package it first stages `@atypon/<config>@latest` into `global_node_modules/node_modules` (`startFromAutomationUI`, `:137-149`). Then, per dependency, cache key = `sha256(name + versionString)` (`:105`); on miss it writes a one-dependency `package.json` in `global_node_modules` and runs plain **`npm i`** (`:151-163`).
3. For `"ui-theme": "git+ssh://git@github.com/atypon/ui-theme-classic.git#v2.8.84"` npm 6 does `git ls-remote` on the tools host's SSH identity, resolves `v2.8.84` to a commit, clones, reads the **theme's own package.json at that tag** and installs its dependencies too, hoisted flat: `ui-theme-classic`, `ui-core@<theme's pin>`, `ui-base@<ui-core's pin>`, `ui-article@<theme's pin>`, `@atypon/<config>@1.3.8`, `@babel/runtime`. Then `mv node_modules <hash>`.
4. `yes | cp -rf <hash>/* <product>/node_modules` (`:115`). **`cp -rf` merges directories**; it overwrites files but never removes files that only exist in the destination.
5. Any error is caught, logged as `Error Installing Package <name> <err>` to build.log **and** the DS console, and the loop continues (`:117-120`). The build then fails later inside webpack.

Consequences:
- **Two copies of ui-core can land in one product.** Themes pin ui-core; "Products on Classic often pin this theme and ui-core directly" (`AGENTS.md:111`; acm, achs, was, fsg do, note 06). Both hashes are `cp -rf`'d into the same `node_modules/ui-core`, so the result is the **last-listed dependency's files laid over the first's**, with orphan files from the first left in place. Same for `@atypon/<config>` (theme 1.3.8 vs product 1.3.12 vs the pre-staged `latest`). The build usually succeeds. This is a silent chimera, ranked C2 in note 20.
- aiaa and utoronto list `ui-theme` first, config second (`aiaa/package.json:16-17`, `utoronto/package.json:18-19`), and pin no ui-core, so their ui-core is exactly the theme's pin.
- No `--cacheDir` on DS (note 20), so every DS run re-resolves every tag. GitHub CI uses `--cacheDir`: there a **moved** tag is invisible until the cache key (name+string) is evicted.
- The whole chain must be SSH-reachable from the tools host: ui-products, ui-theme-*, ui-core, ui-base, ui-article, plus `bootstrap`/`autocomplete.js` forks for eureka (`ui-theme-eureka/package.json:25,28`).

### 2.3 Pins that matter today (verified with `git ls-remote --tags`; all exist)

| Product | develop / stag-marlin `maint-260922` | stag `maint-260901` | prod `maint-260804` | prod-marlin `maint-260702` | beta-app `maint-260415` |
|---|---|---|---|---|---|
| **aiaa** (`ui-theme` = classic) | v2.8.84 | v2.8.74 | v2.6.73 | v2.6.71 | v2.6.66 |
| **utoronto** (classic) | v2.8.84 | v2.8.74 | v2.8.68 | v2.8.28 | v2.6.68 |
| **marlin** (+cell; no theme) | ui-core v2.8.80, ui-article v5.2.29 | ui-core v2.8.64, ui-article v5.2.28 | v2.8.64 / v5.2.28 | v2.8.64 / v5.2.28 | v2.8.64 / v5.2.28 |

deployconf SG branches (note 06 CSV): aiaa beta `develop` / stag `maint-260901-581e6c66` / prod `maint-260804-ef154e82`; utoronto same three; marlin beta `develop` / stag `maint-260922-ad0af6c9marlin` / prod `maint-260702-89e08a43marlin`.

Tag → nested pins (classic): **v2.8.74** (2026-08-23, annotated) → ui-core **v2.8.73**, ui-article **v7.1.6**; **v2.8.84** (2026-09-21, lightweight, "LIT-677817: bump ui-article version") → ui-core **v2.8.81** (2026-09-20) → ui-base **v2.8.89**; ui-article **v7.2.8**; **v2.8.85** (2026-09-23) → ui-core v2.8.82, ui-article v7.2.8. Remote tags: classic 1095, photo 1339, eureka 1150; the v2.8.x line is contiguous v2.8.70…v2.8.85 then v2.9.0. Photo and eureka have malformed tags too (`v.2.7.48`, `v.1.1.4`) — a typo'd pin like `#v.2.7.48` would resolve, which is a trap in the other direction.

**Theme ↔ ui-core coupling:** a product that pins only the theme gets ui-core transitively and exactly (tag → tag → tag). A product that also pins ui-core gets the overlay described in 2.2. **Hotfix tags keep the lower pins unless the hotfix commit bumps them** (`AGENTS.md:109`), so a ui-core fix reaches a Classic product only after (1) a ui-core tag, (2) a theme commit + tag bumping it, (3) a product commit bumping the theme, all on the product's SG maint branch. There is no tag-creation workflow in any theme repo (`build.yml` builds every push; `deploy.yml` deploys the SG doc site from develop on `[DEPLOY]`); tags are cut by hand or by the `create-hotfix-tags` skill in `ui-agent-standards` (another unlisted repo).

### 2.4 ux3 and `#develop`
- `ux3/` has four **submodules** `ux3/{ux3→ui-core, classic, photo, eureka}` all `branch = develop` (`.gitmodules`). The recorded gitlinks (`git submodule status`: classic `17e19ba`, eureka `9cbbb14`, photo `aacbf9a`, ui-core `44a5f31`) are **not** what gets built: BDS `git submodule update --remote` checks out each submodule's **develop tip** (`BDS:300-302`), on every SG branch including prod `maint-260804-ef154e82`. ux3's own `package.json` has only config 1.3.8 + jquery; `bundler.config.js` uses `initChildren()`, and `DependencyInstaller.listProjectsDirectories` recurses into every sub-dir with a package.json, so the four submodule checkouts are installed and built as sub-products with **their develop package.json**: classic/photo develop pin `ui-core#develop` and `ui-article#develop`; eureka develop pins `ui-base#develop`. So a ux3 build is floating at every level; the result is stamped `styleguide version: <maint branch>` in `styleguide.info` (BDS:182), which is misleading.
- Products with a floating theme pin (`ui-theme*: …#develop`, grep on develop): **aea, nato, rsc, mms-nextgen(+ai, catalyst, evidence, mms, voices)**. Their prod SG build changes whenever the theme's develop moves.
- `styleguide.info` records the theme tag by grepping package.json (BDS:213) and `UI-article` from `_from` in an installed package.json (BDS:199); for ux3 it records core/classic/photo but **not eureka** (BDS:218-227). It never records the nested ui-core of a themed product.

### 2.5 How a theme change shows in ProductBuildStyleguide logs
| Log text (DS action log unless noted) | Meaning |
|---|---|
| `Started Installing Package ui-theme Version git+ssh://…ui-theme-classic.git#v2.8.84` then `Finished Installing Package To Cache ui-theme …` | tag resolved and cloned with its nested ui-core/ui-article. Only the version string is shown, never the commit. |
| `Error Installing Package ui-theme Error: Command failed: npm i` (both DS log and build.log; npm's own stderr — `fatal: couldn't find remote ref v2.8.84`, `Permission denied (publickey)`, `ERR! code 128` — **only in build.log** under `Executing: npm i on path …/global_node_modules`) | missing/deleted/typo'd tag, a tag whose nested pin is missing (ui-core/ui-base/ui-article), or SSH/auth failure. Build continues; the product row later shows `failed` after tens of seconds (SCSS `@import '~ui-theme/…'` → `Module not found` / `SassError` in build.log) or <1 s (`getConfigsForProduct … Cannot find module`). |
| `Failed to run CMD: [git submodule update]` (BDS:302, action fails before utypon) | ui-core / ui-theme-* develop tip unreachable, force-pushed away, or repo access lost. Hits **every** product's SG build on that host, not just ux3. |
| A previously green product row turns `failed` with SassError / `Undefined variable` / `mixin not found` after a **product commit** that bumps only the `ui-theme` pin | theme API change between tags (or ui-core change pulled in by the theme's nested pin). Confirm with `git diff v2.8.74..v2.8.84` in the theme and its ui-core pins (v2.8.73 → v2.8.81). |
| Same failure with **no ui-products commit** | only possible via a floating ref: `#develop` theme pin, ux3 submodules, `@latest` config/generator, or a **moved tag**. Check `git ls-remote --tags origin <tag>` against the last good run. |
| `styleguide.info`: `UI-theme : ui-theme-classic.git#v2.8.84` | what BDS believes was built; it is grep'd from package.json, not from `node_modules`. |

## 3. Failure-signature table

| # | Signature | Where | Cause | Action / check |
|---|---|---|---|---|
| D1 | Dailypatch-frontend index page HTTP 500 (`RestTemplate` 404 on `/meta`) | old JSP dashboard | 2023 frontend vs 2026 backend API | Use the React dashboard at `cipsc-services-3:3000` or the REST API; retire the JSP repo |
| D2 | No `Dailypatch: Failed Patch Dev.DB` LIT bugs since 2025-04-18 | Jira | `JIRA_ENABLED` unset in the deployed backend; tickets are not written | Don't treat Jira silence as green. Read `/api/v1/products/failed` |
| D3 | `Dailypatch: Failed Patch Dev.DB : <desc> [litN] in <env>` (if Jira is re-enabled) / `JobState.failureReason` | backend `TicketMessageFactory:14-45`, `issue-types.yml` | office-copy rehearsal failure on the env branch | Leading indicator for prod **only** when the same patch is pending on prod and the branch line matches (§1.4) |
| D4 | `Dailypatch: DB Existence in <env>` | same | office DB `<env>_<product>` missing | clone the DB to the office |
| D5 | Dashboard "Rerun" clicked by a viewer | frontend `POST /rerun` → `PUT /api/v1/patch/push/…` | no auth, `CrossOrigin *` | dashboard is not read-only; don't click while triaging |
| D6 | `patchResult.status = TIMED_OUT` + Google Chat notice | backend `GNOTIFY_ENABLED` | stage timeout | not a patch error class |
| T1 | `Error Installing Package ui-theme …` then product `failed` | build.log + DS log | tag missing/moved/typo, nested pin missing, SSH | `git ls-remote --tags git@github.com:atypon/ui-theme-classic.git v2.8.84`; read `Executing: npm i` block |
| T2 | `Failed to run CMD: [git submodule update]` | DS log, before utypon | any of the 4 ux3 submodule develop tips unreachable | affects every product; check `git ls-remote origin develop` on ui-core and the 3 themes |
| T3 | SassError / `Module not found` after a theme-pin bump only | build.log | theme API change or nested ui-core change | diff theme tags and their ui-core pins |
| T4 | Same failure, no ui-products commit | build.log | floating `#develop` (aea, nato, rsc, mms-nextgen, ux3), `@latest`, or a moved tag | compare theme/ui-core develop `git log` with the last good run time |
| T5 | Build **succeeds**, site renders wrong | none | ui-core chimera: theme-nested ui-core overlaid by product-pinned ui-core via `cp -rf` (order = package.json order) | compare `node_modules/ui-core/package.json._from` in the tarball with both pins; pin only one |
| T6 | Build succeeds, `styleguide.info` says `UI-theme : …#v2.8.84`, prod looks like develop | styleguide.info | ux3/`#develop` products: the stamp is the SG branch, content is develop tip | read `git log -1` in the submodule of the built tree |
| T7 | `UI-core: Not Found` / `UI-article: Not Found` in styleguide.info | BDS:194-227 | grep/awk parse miss (e.g. eureka never recorded for ux3) | cosmetic |

## 4. Success-while-broken and drift risks (summary)
1. **Jira silence ≠ health**: Dailypatch has written no LIT bug for 17 months because Jira is off; the rehearsal is alive but its only outputs are Mongo/REST/Google Chat.
2. **Dashboard repo drift**: the running React dashboard has no repo in the model; Dailypatch-frontend (JSP) and dailyPatchDashboard are dead code that still carry credentials (plaintext in one, rendered into HTML by the other).
3. **Host drift**: frontend/puppet still describe `patch-jo*/patch-sc*`; the backend runs on `patch-dc-1..3`, which puppet-control does not know.
4. **Theme pin ≠ full pin**: a tag pins the theme and (transitively) ui-core/ui-base/ui-article, but products that also pin ui-core get an order-dependent overlay; the build passes.
5. **ux3 and four `#develop` product groups float on every environment, including prod**, and `git submodule update --remote` makes every SG build depend on four develop tips being reachable.
6. **Tags are hand-made and lightweight/annotated mixed**; `package.json.version` inside them is wrong; malformed `v.x.y.z` tags exist in photo/eureka. `ls-remote` is the only truth.
7. **Install errors are swallowed** (`DependencyInstaller.ts:117-120`), so a bad pin surfaces as a late webpack error whose real cause is one `Error Installing Package` line earlier in build.log.

## 5. Open items I could not verify
- Reachability/content of `http://cipsc-services-3.atypon.com:3000/` and `http://patch-dc-1.int.atypon.com:6767/api/v1/products/stats` (not opened).
- The exact `@RequestMapping` prefix of `ProductController` (masked; inferred `/api/v1/products` from LIT-658534).
- Whether `JIRA_ENABLED=true` is set on the real `patch-dc-1` container (the README run command omits it; the 0-tickets JQL is consistent with it being off).
- Which repo holds the React dashboard, and who manages `patch-dc-*`.
