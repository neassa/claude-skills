# 20 — Styleguide build toolchain: utypon-cli, styleguide-bundler, ui-core, composite actions

Written 2026-09-25. Goes with 06 (Part B: deployconf, ui-products, Build-Deploy-Styleguide.sh) and 08 (pugrenderer).

## Coverage: what I read, at which commit

| Repo | Ref | Read |
|---|---|---|
| utypon-cli | `main` 69e1b08 (= tag 1.31.19). The clone is shallow; I fetched tags 1.31.7–1.31.19 | Read fully: `src/modules/build/{index,optimized}.ts`, `src/core/{Utypon,UtyponModule,UtyponModuleOption}.ts`, `src/utils/Generic/index.ts`, `src/modules/update/index.ts`, `bin/utypon`, `package.json`, `.npm/{postinstall,preinstall}`, `.npmignore`, both `patches/*`. Diffed every tag pair from 1.31.10 to 1.31.19. **Not opened:** `.env` (bin/utypon loads it with dotenv) and `.ci.npmrc`. Other modules (figma, workspace, generate and so on) not read. |
| **styleguide-bundler** (new clone: `$LIT_REPOS/styleguide-bundler`) | `main` 9fb5025 (= 1.4.7), tags 1.4.1–1.4.7 | **All of `src/`** (11 files, 807 lines), plus `package.json`. Diffed 1.4.4→1.4.7. This is the code that actually does the build, and it was not on the repo list: model gap, now filled. |
| ui-products | `develop` 7f77198e1d; stag `maint-260922-ad0af6c9marlin` ce8795f50b; stag app `maint-260901-581e6c66` 185ac68243; prod `maint-260702-89e08a43marlin` 8b7685f066 and `maint-260804-ef154e82` 35e4578df5; beta app `maint-260415-e3fcd3c2` 55ebb37f56. I deepened the 2 stag branches by 200 commits | `marlin/{package.json,bundler.config.js,bundler.custom.js,public.config.js,bundle.json,.npmrc}`; `marlin/{cell,ha,lancet}` file lists, package.json and lock (blob-hash compare); `app/{package.json,bundler.config.js}` and the app lock pins; `git log` on `app/` and `marlin/`; commits 700d1c1f23 and 962e66e402 |
| ui-core | `develop` 63b0ed8 plus tags v2.8.64–v2.8.82 | `package.json` at each tag, `bundler.config.js`, `.github/workflows/{build,deploy,lint}.yml`, `buildci.sh` (sampled) |
| styleguide-composite-actions | `main` f52b32c | `styleguide-{build,product-build,deploy}/action.yml` read fully. `styleguide-lint` not read |
| platform-tools | b00c49f | `Build-Deploy-Styleguide.sh` lines 300–480 re-read (the rest is covered in 06) |
| deployconf | local clone | `<styleguide>` for marlin/app in the midtierbeta, staging and literatum files, parsed with xml.etree |
| ls-remote only | ui-theme-eureka, ui-core, ui-article | Confirmed that tags v2.6.77/85/86, v2.8.105, v2.8.80 and v5.2.29 all exist |

**Not available:** `@atypon/styleguide-webpack-configuration` (`atypon/styleguide-webpack-configuration` returns "Repository not found"). That is `BuildController.init()`, i.e. how sub-products are discovered and the webpack/SCSS rules. I also have no DS `build.log` for the failing runs.

## deployconf `<styleguide>` for marlin and app (no `<group>` on any of them)

| Env | marlin | app |
|---|---|---|
| beta | `develop` → midtierbeta-pr-marlin | `maint-260415-e3fcd3c2`, **product disabled** |
| stag | `maint-260922-ad0af6c9marlin` → staging-pr-marlin | `maint-260901-581e6c66` → staging-pr-literatum4 |
| prod | `maint-260702-89e08a43marlin` | `maint-260804-ef154e82` |

**`marlin/` is byte-identical on `develop` and on the stag branch** (`git diff --stat` is empty). So beta and stag build exactly the same marlin tree.

## 1. How `utypon build optimized` works, end to end

1. **BDS** runs `cd <product>` (e.g. `ui-products/marlin`), then `rm -rf node_modules releasedAssets`, then `utypon build optimized --productsPath=$PWD --noSudo --noContainer --threadsCount=10 --ramCount=10`. With `NODE_OPTIONS=--max-old-space-size=25000` and `NODE_ENV=production` exported. It ignores utypon's exit code and greps `build.log`.
2. **utypon-cli** (`optimized.ts`):
   - The options it knows are `products-path`, `max-threads`, `max-ram`, `skip-install`, `product`, `skip-build`, `throw-on-error`, `cache-dir`, `environment-variable`, `clean-up` and `styleguide`. yargs is not in strict mode, so **`--threadsCount`, `--ramCount`, `--noSudo` and `--noContainer` are silently ignored** on the DS product/group path. Only the Jenkins path (BDS:430) uses the real `--maxThreads/--maxRam/--cacheDir`.
   - The result on DS: `NUMBER_OF_THREADS=""`, which means one worker per CPU (`os.cpus().length`). `CACHE_DIR=""`, so the dependency cache is rebuilt from nothing on every run. The heap setting is BDS's 25000 MB. This is the same in every version.
   - It runs two `shelljs.exec` steps, in the process's cwd: `node <utypon>/node_modules/@atypon/styleguide-bundler/dist/core/install/index.js`, then `.../build/index.js`.
   - **It exits 0 even when products fail**, because `--throwOnError` isn't passed.
3. **Install** (`styleguide-bundler/src/core/install/DependencyInstaller.ts`):
   - It writes `build.log` = `cleared`.
   - It finds every sub-directory containing a `package.json`, recursively and in readdir order (libuv sorts it). Then the root.
     - For marlin that is `cell`, `ha`, `lancet`, then `marlin`.
   - For each directory:
     - `rm -rf node_modules; mkdir node_modules`.
     - For each **package.json dependency** (**lockfiles are never used**):
       - The cache key is `sha256(name+version)` under `<root>/global_node_modules`.
       - On a cache miss it writes a one-dependency `package.json` there, runs `npm i`, then `mv node_modules <hash>`.
       - It then copies `cp -rf <hash>/* <dir>/node_modules`.
       - For `ui-core`, `ui-theme*` and `@atypon/styleguide-webpack-configuration` it first stages `styleguide-webpack-configuration@<ver or latest>` into `global_node_modules/node_modules` (`startFromAutomationUI`).
     - `handleGeneratedFile` copies every short-named entry of `global_node_modules`, including a leftover `node_modules`, into the product dir.
   - **Every install error is caught.** It is logged as `Error Installing Package <name> <err>` to build.log and stdout, and the loop continues.
   - `postinstall.sh` only runs for `ux3`.
   - Consequence: **the first sub-product (marlin → `cell`) is the one that does every real `npm i`.** `ha` and `lancet` mostly get cache copies, and they retry any package that failed for cell. So a failure that happens only on the first attempt leaves **only cell** without a module.
4. **Build** (`src/core/build/*`):
   - The cluster master (`Controller.ts`) `require`s `./bundler.config.js`. Marlin's version sets `global.skipChildTransformation`, calls `BuildController.init`, then applies `bundler.custom.js`.
   - It maps each config to a `product` name, taken from the entry path after `ui-products/` (e.g. `marlin/cell`), and sorts them.
   - It forks N workers (`silent`). Each worker's stdout/stderr goes to `<product dir>/worker_logs_<id>.log`.
   - Each worker (`ProductBuilder.ts`) does `require('<path>/bundler.config.js')` → `webpack(config).run()`.
   - Status handling (`State.ts`):
     - Status is `inProgress` → `success`/`failed`, and `stuck` after 120 min (1.4.7; 60 min in 1.4.6, 25 min in 1.4.5).
     - Two `stuck` marks turn into `failed`.
     - On every change it runs `console.clear()` + `console.table({product,status,duration})`. **That table is what the DS action log shows.**
   - At the end it writes `Build Failed For The Following Products - [<last path segment>]` or `All Products Have been Built Successfully` to build.log and stdout, then `process.exit(0)`.
5. **build.log** is `<product dir>/build.log`, written only by the master. It contains:
   - `Executing: <cmd> on path <dir>` for every install/cp command, followed by that command's stdout/stderr.
   - `Error Installing Package …` lines.
   - `Assigning Product <path> to proccess <id>` and `Number of active threads …`.
   - **For each failed product, the error payload**: either the webpack `stats.toString()` (compile errors), or `Returned error message from getConfigsForProduct <Error>\n Files in directory: …`, or `Configs for product <path> not found`.
   - BDS tars it to `~<acct>/logs/<acct>/<prod>/UI/build.tgz`. **The real error is only there** (and in `worker_logs_*.log`), never in the DS action log.

### What `'failed' | '898 ms'` means
The duration runs from `inProgress` (task sent) to `taskFinished`. An SCSS/JS compile of a marlin sub-product takes tens of seconds, so **under 1 s means the product failed before or at webpack start**:
- (a) `require('<product>/bundler.config.js')` threw, e.g. `Cannot find module '@atypon/styleguide-webpack-configuration'`/`ui-core`, or a TypeError inside `BuildController.init` or `../bundler.custom.js`. build.log then shows `Returned error message from getConfigsForProduct …` plus the directory listing.
- (b) `webpack(config)` threw synchronously (schema validation, missing plugin).
- (c) The compile failed immediately on an unresolvable entry or loader.

Contrast: `'inProgress' | 'NA ms'` in the final table means the worker died or hung and never reported back (see note 14 §1d).

## 2. utypon-cli postinstall and `patch-package`
- `postinstall` = `patch-package && bash ./.npm/postinstall` (the latter runs `husky install` and chmods hooks only when `.git` exists). This is identical in 1.31.10 through 1.31.19.
- The patches:
  - `yargs+17.2.1.patch` adds `return;` at the top of yargs' internal `argsert` type-error function (`Invalid <n>th argument. Expected … but received …`), which **disables yargs' API-argument type checks**.
  - `@atypon+figma-tokens-api+1.0.6.patch` adds a `useBearerToken` option (OAuth vs personal token) to the figma sync resources. It is used only by the `utypon figma …` commands.
- If it doesn't run (`sh: 1: patch-package: not found`):
  - Figma sync loses bearer-token support. That is irrelevant for builds.
  - The yargs checks come back. A type mismatch in utypon's own `yargs.option/command` calls would then throw at startup, before any build.log is written, so there would be no status table. The DS log does show a status table, so utypon clearly parsed its CLI. **I judge it non-fatal for `build optimized`.**
  - Why the binary isn't found is unverified. It is a regular dependency (`^6.4.7`), so it should be in `…/utypon-cli/node_modules/.bin`. This affects every env, because the script is the same in every version.
  - Unverified risk: if npm treats the failed postinstall as an install failure, the global install may be left partial or at the previous version. Check with `utypon --version` or `npm ls -g @atypon/utypon-cli` on the tools host.

## 3. 1.31.10/11 (prod) vs 1.31.17–19 (beta/stag)

| Tag | Date | Change relevant to `build optimized` |
|---|---|---|
| 1.31.10 | 2026-05-04 | bundler 1.4.5 (stuck timer 25 min) |
| 1.31.11 (prod pin) | 2026-05-12 | bundler **1.4.6** (stuck timer 60 min; LIT-650413) |
| 1.31.12–16 | May–Aug | `workspace init`, `sync-agent-standards`, `update` command, `.env` edits. **Not used by build** |
| 1.31.17 | 2026-09-07 | bundler **1.4.7**: stuck timer **120 min** (the only code change) |
| 1.31.18–19 | 2026-09-14 | docker/dockerfile only (Debian snapshot mirror, openssh-client) |

- **Code-wise, prod and beta/stag run the same install/build logic.** The only difference is the stuck timeout, which cannot cause an 898 ms failure.
- What does differ between envs:
  - (i) beta/stag re-resolve `@latest` of utypon-cli on every build. utypon itself floats `@atypon/styleguide-code-standards`, `ui-declarations`, `ui-product-boilerplate` and `ui-scripts` at `latest`, but those aren't on the build path.
  - (ii) Different SG branches (for app).
  - (iii) Different tools hosts, npm caches and network.
- Note 14 records "utypon-cli outdated on CIP/stag" for marlin (LIT-681645/680822/673347). Measured against the code, a newer utypon only buys the longer stuck timer.

## 4. ui-core and theme/core pinning
- Products pin `ui-core`/`ui-theme` as **git+ssh tags** in `package.json` (e.g. marlin `ui-core#v2.8.80`, `ui-article#v5.2.29`; app `ui-theme` = `ui-theme-eureka#v2.6.86` on stag, `#v2.8.105` on develop). Plus `@atypon/styleguide-webpack-configuration` 1.3.12.
- **The lockfiles are stale and are ignored by the bundler.**
  - The marlin locks still say ui-core `#v2.8.64` (7dd7f4cb) and ui-article `#v5.2.28`.
  - The app locks say ui-theme `#v2.6.77`.
  - These don't matter for DS builds, but they mislead anyone who reads the lock.
- ui-core's own dependencies:
  - `ui-base` is a git+ssh tag written in **scp-style inside an ssh URL** (`git+ssh://git@github.com:atypon/ui-base.git#v2.8.88` at v2.8.80). That has been the form since at least v2.8.64. On `develop` it is `…/ui-base.git#develop` (floating).
  - `@atypon/get-ftr` is `latest` (floating).
  - Also `@atypon/ui-utils` 1.0.6 and `@types/styleguide` → `npm:@atypon/styleguide-types@1.0.8`.
- **Marlin bumped ui-core v2.8.64 → v2.8.80 on 2026-09-17** (962e66e402, LIT-682864, in all 4 marlin package.json files). That moves ui-base v2.8.75 → v2.8.88. It is a new, uncached git dependency tree for every DS run, and it lines up in time with the marlin failures.
- Fast-failing (<1 s) causes on the ui-core side: a git+ssh fetch/auth failure for ui-core, ui-base or ui-article from the tools host; a `latest` package (`get-ftr`) that won't install; or a ui-core layout change that `BuildController.init`/`bundler.custom.js` trips on. Only the first two are install-time failures, and they show up as `Error Installing Package ui-core …` in build.log.
- CI: ui-core `build.yml`/`deploy.yml` use `styleguide-composite-actions/*@main` in the `utypon-cli:latest` image. Deploy runs only on develop commits tagged `[DEPLOY]`.

## 5. Why marlin/cell (and app) could fail in <1 s: candidate causes

| # | Candidate | Evidence for | Evidence against | How to confirm |
|---|---|---|---|---|
| C1 | **A dependency install failed only for cell** (the first-installed sub-product), so the require in cell's `bundler.config.js` fails | The bundler installs cell first with no persistent cache; install errors are swallowed; ha and lancet retry the failed package and succeed. The ui-core v2.8.80 bump (09-17) brought in a new git dependency tree. cell, ha and lancet have identical package.json files (and identical locks apart from `name`) and identical `bundler.config.js`, so only install order sets cell apart | A consistent failure would hit ha and lancet too | build.log: `Error Installing Package <x>` just after `Started Installing Dep on Project …/marlin/cell`; `getConfigsForProduct Error: Cannot find module …` for marlin/cell |
| C2 | **Stateful staging in `global_node_modules` gives cell a different `node_modules` than ha/lancet** | `startFromAutomationUI`, the `npm i` of ui-core into a dir already holding `styleguide-webpack-configuration@latest`, and `handleGeneratedFile` copying the leftover `node_modules` all depend on order. cell is the only product whose ui-core comes from a fresh `npm i`. A new `styleguide-webpack-configuration@latest` could then change the loader shape. `bundler.custom.js` does `ScssRule.use.findIndex(l => l.loader.includes(...))`, which throws a TypeError if no SCSS rule is found or a loader is a string | Speculative. It depends on npm 6's pruning, and on webpack-configuration source I can't see | build.log: `getConfigsForProduct TypeError: Cannot read property 'use'/'includes' …`; compare `marlin/cell/node_modules/@atypon/styleguide-webpack-configuration/package.json` version with `ha`'s |
| C3 | The error is in cell-specific source (entry/SCSS/import) | Would explain a cell-only failure | Would take seconds, not 898 ms, unless the entry itself is unresolvable. marlin is the same on develop and stag, and prod builds an older branch | build.log: webpack stats `Module not found`/`SassError` under marlin/cell |
| C4 | utypon-cli version (beta/stag `@latest` vs prod 1.31.11) | Only beta/stag failed | There is no build-path code difference except the stuck timer | — |
| C5 | Tools-host state (npm cache, git ssh to github, disk) | beta and stag each fail on their own host | — | `Executing: npm i on path …/global_node_modules` followed by an npm ERR in build.log |
| A1 | **app (stag)**: SCSS import order in `app/scss/build-article.scss` | Fix 700d1c1f23 (LIT-683350, 2026-09-24): `./variables/variables` moved after `~ui-theme/scss/variables/typo-variables`. Branch tip 185ac68243 has it | It's an SCSS error, so it would normally take longer than 1 s; the app duration isn't known | Re-run stag app at 185ac68243; build.log SassError. Note that ui-theme-eureka is pinned at v2.6.86 on stag vs v2.8.105 on develop |

**Next step (read-only):** get `~midtierbeta/logs/midtierbeta/marlin/UI/build.tgz` and the staging equivalent from the tools host, then `grep -nE "marlin/cell|Error Installing|getConfigsForProduct|Configs for product|npm ERR"`. That tells C1, C2 and C3 apart in one pass.

## 6. styleguide-composite-actions vs the Deploy Server path

| | Deploy Server (`ProductBuildStyleguide`) | GitHub Actions (`styleguide-build`/`styleguide-product-build`/`-deploy`) |
|---|---|---|
| Runner | Tools host, node 14.16.0/npm 6.14.11, global utypon `@latest` (beta/stag) or 1.31.11 | Container `ui/utypon-cli:latest` (image-baked utypon), npm 6.14.17 |
| Scope | One deployconf product/group on the SG branch | Top-level dirs changed in the last commit (`CLIENTS`), or the lib copied to `ui-products/generic` |
| Flags | Unknown `--threadsCount/--ramCount`, **no cache, no `--throwOnError`**; success = grep of build.log | `--throwOnError --cacheDir=$RUNNER_TEMP/utypon_cache` (+`--cleanUp --styleguide` for SG site builds) |
| Output | Tarball `styleguide_new_*` → pugrenderer nodes (note 06/08) | `ui/sg_prod:<sha>` image → helm `develop-styleguide` (the SG documentation site); build.log uploaded as an artifact on failure |

- They are **independent**: a green GitHub build does not prove a DS build will pass (different utypon install, cache, flags and host).
- The ui-products `SgreleaseAssetsBuild.yml` (manual, note 06) is the only CI job that uses the DS-like `--maxThreads/--maxRam` flags.

## Failure-signature table (styleguide toolchain)

| Signature (DS log / build.log) | Meaning | Where the real error is | Class |
|---|---|---|---|
| Table row `'…/ui-products/<p>/<sub>' │ 'failed' │ '<1000 ms'` | Config load, webpack init or dependency failure (see §1 a/b/c) | build.log: `getConfigsForProduct …` / `Configs for product … not found` / `Error Installing Package …` | DEP/CODE |
| Row `'failed'` with a duration of tens of seconds or more | webpack compile errors (SCSS/JS) | build.log: webpack `stats.toString()` | CODE |
| Row `'inProgress' │ 'NA ms'` in the final table | Worker died or hung (OOM, crash), or the run was killed | `worker_logs_<id>.log` in the product dir | TRANSIENT/INFRA |
| `Product … has exceeded stuck threshold of 2` | Build exceeded 120 min twice (1.4.7) | build.log | INFRA/perf |
| `Build Failed For The Following Products - [cell]` | Only the last path segment is printed (`cell`, not `marlin/cell`) | build.log | — |
| `Error Installing Package <name> …` (build keeps going) | npm/git install failed. Swallowed, so it only surfaces later as a fast `failed` | build.log `Executing: npm i on path …global_node_modules` block | DEP/TRANSIENT |
| `sh: 1: patch-package: not found` during `npm i -g @atypon/utypon-cli` | postinstall patch step skipped: yargs arg checks re-enabled, figma bearer patch missing | DS log | Non-fatal for builds (unless utypon fails to start) |
| `Failed to Build The Product` with no status table | utypon never started (`command not found`, startup crash) | DS log | DEP (S18 in note 06) |
