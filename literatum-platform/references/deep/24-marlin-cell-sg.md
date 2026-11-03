# 24 — marlin ProductBuildStyleguide: `marlin/cell | failed | 898 ms`

Written 2026-09-25. Builds on note 20 (toolchain) and note 06 (deployconf/ui-products). Read-only analysis. There is no build.log, so the ranking below comes from the code plus the DS logs.

## Coverage: what I read, at which commit

| Repo | Ref | Read |
|---|---|---|
| styleguide-bundle-configurations (`@atypon/styleguide-webpack-configuration`) | `main` fb0ba06 = tag 1.3.12. I unshallowed it and fetched all tags (1.1.2-alpha … 1.3.12, incl. `1.3.9-marlin`) | **All of `src/`** (26 files, ~2.3k lines), `package.json`, `.npmignore`, both workflows. Diffed 1.3.11→1.3.12 and `1.3.9-marlin`. `.ci.npmrc` not opened |
| styleguide-bundler | `main` 9fb5025 (1.4.7) | **All of `src/`** (807 lines), re-read for this note |
| **ui-bundle-generator** (new clone `$LIT_REPOS/ui-bundle-generator`, depth 50) | `develop` aae52e6 = tag 1.4.3 | `lib/webpack/index.js`, `lib/index.js`, `lib/config.js`, `lib/utils/path-resolver.js`, `lib/utils/ux3-module.js`, `lib/public-path-generator.js`, `lib/default-imports-generator.js` (lines 1–120 and 330–432), `lib/js-generator.js` (lines 170–243), `package.json` head. I also read commits 1b9001c (1.3.0) and 75eddb9 (1.4.3). **This repo was not on the list. It is the config package's `BundleGenerator` plugin (dependency `@atypon/…: latest`): a model gap, now filled.** Also sampled: dynamic/lazy/groups generators and `utils.js` |
| ui-products | `develop` 7f77198e1d (= local HEAD), `maint-260922-ad0af6c9marlin` ce8795f50b, `maint-260702-89e08a43marlin` | marlin root and cell/ha/lancet: `package.json`, `bundler.config.js`, `bundler.custom.js`, `public.config.js`, `.npmrc`, blob-hash compare of every top-level file. The clone is shallow (history starts 2026-09-03) |
| deployconf | `origin/main` ad1c87a (fetched, parsed with xml.etree) | `<styleguide>` for marlin on midtierbeta and staging |
| DS logs | `${TMPDIR:-/tmp}/ds-triage-$USER/history/logs/` | All 3 marlin SG logs (the whole utypon section of each) plus the 2 stag `app` SG logs (final table only) |

`safe_view` masks most `@atypon/<name>` strings. I identified the four `latest` `@atypon` dependencies of the config package from their code roles (design-tokens loader, **ui-bundle-generator**, code-standards, automation-testing helper), not by reading their names directly.

## deployconf now (origin/main ad1c87a)
- beta: marlin SG `develop` → midtierbeta-pr-marlin
- stag: marlin SG `maint-260922-ad0af6c9marlin` → staging-pr-marlin
- `marlin/` is byte-identical on develop and on maint-260922. Between those two and maint-260702, only the ui-core/ui-article pins differ (v2.8.64→v2.8.80). All three branches pin config **1.3.12** in all 4 package.json files. `bundler.config.js` has the same blob (70e8b37262) in cell, ha and lancet on all three branches.

## cell vs ha vs lancet (develop = maint-260922)
- `package.json`: identical except `name`. `bundler.config.js`, `config.json`, `.npmrc`, `.babelrc`, `tsconfig.json` and `early-hints.json` are identical blobs.
- `bundle.json`: cell = lancet (29845b78f8). **ha differs** (7dcaf50730): it has no `ab-logger` module entry. `info.json` differs in all three (metadata).
- Nothing cell-specific shows up in the files the config code touches at load time.

## 1. What the config package does at load time (1.3.12)
`cell/bundler.config.js`: `require('@atypon/styleguide-webpack-configuration').defaults.init(__dirname, require.resolve)`. Then, unless `global.skipChildTransformation`, it runs `../bundler.custom`.
- `src/index.ts`: `import "reflect-metadata"`. It picks `TestingConfig` if `ENABLE_UNIT_TESTING=TRUE`, else `MainConfigs`.
- `new MainConfigs()`: `new` on every plugin and loader class, then `buildEntryObject()`, which only calls readdir/exists on `js/`, `scss/` and `basic/themes/scss` (all checked for existence first).
- `init()`: sets productPath/resolver, then `c.build()`. The build returns `undefined` when there are **no entries**, and `initChildren()` runs unless `SKIP_CHILD=TRUE` (the worker sets it).
- `build()` → `buildLoaders()`: each loader's `init()`, then **`require.resolve(loader)`**. `buildPlugins()` → each plugin's `init()`, which `require`s the plugin module.

Env vars read: `NODE_ENV` (only `development` = dev), `SKIP_CHILD`, `ENABLE_UNIT_TESTING`, `REF_SITE`, `INC_SOURCEJS`, `LOCAL_BUILD`, `ENABLE_LINTING` (dev only). **None is required and none throws.** No config keys are required either: `config.json` parse errors are swallowed (`{}`).

**Every synchronous throw before webpack starts** (each one surfaces as `getConfigsForProduct` in build.log):
| # | Where | Throws when | Message |
|---|---|---|---|
| T1 | `Loader.build` → `require.resolve` for design-tokens loader, `@epegzz/sass-vars-loader`, `@ibrahim-rahhal/sass-loader`, resolve-url, file, postcss, css, style, babel, ts, pug, expose loaders; also `require('sass')`, `mini-css-extract-plugin`, and autoprefixer/pixrem/postcss-* inside `postCssLoader.init` | the package is missing from the resolution chain (config pkg dir → cell/node_modules → marlin/node_modules …) | `Error: Cannot find module 'X'` |
| T2 | plugin `init()`: clean-webpack-plugin, friendly-errors, fix-style-only-entries, mini-css-extract, copy-webpack, webpack-manifest, webpackbar, merge-jsons, terser, non-digest, optimize-css-assets | module missing | `Cannot find module` |
| T3 | **`BundleGenerator.init` → `require(ui-bundle-generator)`**. **Loading the module runs the generator** (see §3) | FS race on a shared dir, or a module in bundle.json that can't be found | `ENOENT …` / `TypeError: error.toString(...).include is not a function` / `GENERATOR ISSUES …` |
| T4 | `WebpackDefinePlugin` → `GenericStaticFiles.getFilesFingerprint` → `crypto.hashPath`; also `CopyWebpackPlugin` → `apply()` → `hashPath` | a `path` listed in a `public.config.js` (ui-core's, **`../public.config.js` = marlin's**, or the product's) doesn't exist. marlin lists `node_modules/mathjax-modern-font/chtml/dynamic`, resolved **relative to cell** | `Error: The specified directory does not exist : …/marlin/cell/node_modules/mathjax-modern-font/chtml/dynamic` |
| T5 | `CopyFiles` → `require(images/journal-colors.json)` | the file exists but is invalid JSON | SyntaxError |
| T6 | `../bundler.custom.js` (worker path, since `skipChildTransformation` is unset there) | no rule whose `test` matches `.scss` (`ScssRule` undefined), or a `use` entry without a `.loader` | `TypeError: Cannot read property 'use' of undefined` / `'includes'` |

Missing files are otherwise tolerated: every path is checked with `fileExist`, `public.config.js` requires are wrapped in try/catch, and the copy patterns use `noErrorOnMissing`. There is **no theme/core resolution that throws**. A missing ui-core or ui-theme only removes inherited config, locales and images.

**Versions:** tags 1.2.10 … 1.3.12, published to GitHub Packages from `main` by `release.yml`. **marlin pins 1.3.12** (fb0ba06, 2026-03-26, LIT-664173). 1.3.12 vs 1.3.11 is `package.json` only: the version bump plus one added dependency at 1.0.5 (its name is masked). The bundler's `startFromAutomationUI` stages `@latest` of the config package for ui-core. `latest` should also be 1.3.12, but I did not check the registry. All four `@atypon` dependencies of the config package are **`latest`** (floating), including ui-bundle-generator (→ 1.4.3).
- **Tag `1.3.9-marlin`** (16c0c99, 2025-10-02, "fix ui-bundle generator", on no branch) pinned one `@atypon` dependency from `latest` to **1.2.0**. That dependency is the generator: 1.2.0 is the last version before the module-load `generator.run()` was added. So marlin once had a dedicated workaround for exactly this generator. It is gone now that marlin is on 1.3.12.

## 2. What a <1 s `failed` means (bundler 1.4.7)
- The master `require`s `marlin/bundler.config.js`, which builds all four configs in one process (root plus children), sorts them, and forks `os.cpus()` workers. They all go `online` at the same moment and each gets one product immediately. The DS table shows all four `inProgress` before the first result.
- Worker `buildProduct`:
  1. `getConfigsForProduct`: `SKIP_CHILD=TRUE`, then `require(<p>/bundler.config.js)`. A throw here sends `status 1` with the error `Returned error message from getConfigsForProduct <e.toString()>\n Files in directory: <ls>`. A falsy return gives `Configs for product <p> not found`.
  2. `webpack(config)` inside try/catch. A synchronous throw sends `e.toString()` with no prefix. This includes plugin `apply()` and the **environment hook**, where the generator runs again for the product's own dir.
  3. `compiler.run`: `err.toString()` or `stats.toString()`.
- The duration runs from `inProgress` to `taskFinished`. Healthy marlin sub-products take **523–644 s** in these logs, so 898/904/913 ms is config load or `webpack()`, never a compile. Such tight, repeatable timings point to a fixed amount of work (loading the config package and plugins) followed by a throw.
- **What goes only to build.log**: it is written only by the master. It holds `Executing: <cmd>`, and each command's stdout/stderr (so npm/git output is **only** there), plus `Assigning Product …`, `Number of active threads …`, **the `taskFinished` error payload**, stuck messages and the final summary.
  - The DS log gets only master console output: the `Started/Finished Installing …` and `Error Installing Package …` lines (those go to both), the tables, and the summary.
  - Anything a worker prints (webpackbar, the generator's `console.warn('Warning: Could not delete and recreate directory …')`, friendly-errors) goes only to `<marlin>/worker_logs_<id>.log`. BDS doesn't tar those, and the next checkout's `git clean -fdx` deletes them.

## 3. The new finding: ui-bundle-generator runs at `require` time against the shared marlin root
`lib/webpack/index.js` (since 1.3.0, 1b9001c, 2025-09-23) starts with:
```js
let generator = new Generator();
generator.run();
```
- `Configs.instance.rootPath` is `'./'`, i.e. the **process cwd = `ui-products/marlin`** (workers inherit it), not the product.
- `run()` → `init()` reads `marlin/bundle.json`, then `new DefaultImportsGenerator(...)`:
  - The constructor does `rmdirSync(outputPath, {recursive})` (errors swallowed).
  - `initialize()` does `ensureDirectoryExists(outputPath)`, then **`writeFileSync(outputPath/webpack-public-path)`**, `ensureDirectoryExists(outputPath/groups)` (marlin's bundle.json has `groups`), group files, and **`writeFileSync(outputPath/index)`**.
  - `outputPath` = `<cwd>/node_modules/@atypon/<generator>/<.gen dir>` (the segment names are masked in my viewer). **It is the same directory for every worker.**
- So every worker does rm/mkdir/write on one shared directory at the same moment, as soon as it `require`s its product's config. The master already did the same once, alone, which is why the master never fails.
  - If worker A's `rmdirSync` lands between worker B's `mkdirSync` and `writeFileSync`, B gets **`ENOENT … open '<marlin>/node_modules/@atypon/…/…/index'`** (or `webpack-public-path`, or a groups file). That error is not caught.
  - If B's `mkdirSync(<dir>/groups)` hits the missing parent, `ensureDirectoryExists` does `error.toString().include(...)` (typo for `includes`). That throws **`TypeError: error.toString(...).include is not a function`**.
  - Either error propagates out of `require` → `BundleGenerator.init` → `bundler.config.js` → `getConfigsForProduct` → `failed` in about 0.9 s.
- The ui-bundle-generator authors already hit this race once. 1.4.3 (75eddb9, LIT-646682, 2025-10-20) replaced a bare `mkdirSync` with `ensureDirectoryExists`, which handles only `EEXIST`. The ENOENT windows are still open.

## 4. What the DS logs show (the only 3 marlin SG runs in the history)
| Action | Env/host | SG branch | utypon | Failed row | Failed product |
|---|---|---|---|---|---|
| 3d1d3fed 2026-09-13 | beta tools-11 | develop | 1.31.17 | 898 ms | **cell** |
| e966368f 2026-09-13 | stag tools-8 | maint-260702-89e08a43marlin | 1.31.17 | 913 ms | **cell** |
| eccd088a 2026-09-14 | stag tools-5 | maint-260702-89e08a43marlin | 1.31.19 | 904 ms | **ha** |

- The other three products succeeded in each run (523–644 s).
- **No `Error Installing Package` line in any run.** Every cell dependency shows `Finished Installing Package To Cache`, and ha/lancet use the cache. `patch-package: not found` appears as before and is non-fatal.
- **These runs predate the ui-core v2.8.80 bump (2026-09-17)**, so that bump is not the trigger.
- The **same branch** failed on cell once and on **ha** the next day (a different host), so the failing product is not fixed.
- I have no DS log for the current (post-09-22) beta/stag runs. Please check that they also show about 0.9 s. The two stag `app` failures in the history are 184 s and 200 s. That is a compile failure, a different class (A1 in note 20).

## 5. Ranked candidates
| Rank | Cause | For | Against | The one build.log line that confirms it |
|---|---|---|---|---|
| **1** | **ui-bundle-generator's module-load `generator.run()` races across parallel workers on `marlin/node_modules/@atypon/<gen>/<.gen>`** (T3) | Explains a fast, product-agnostic, random victim (cell, cell, ha); the ~0.9 s fixed cost; the master never failing; clean installs; identical sub-products; no link to the ui-core bump. The maintainers already fixed one EEXIST variant (LIT-646682), and there was once a marlin-only pin to generator 1.2.0 (`1.3.9-marlin`) | Not seen in a build.log yet. Why the root `marlin` product never loses is unverified (it is probably just chance) | `Returned error message from getConfigsForProduct Error: ENOENT: no such file or directory, open '…/ui-products/marlin/node_modules/@atypon/…/index'` (or `…/webpack-public-path`), **or** `… TypeError: error.toString(...).include is not a function` |
| 2 | `public.config.js` fingerprint: `node_modules/mathjax-modern-font/chtml/dynamic` missing under one product (T4) | Fast, synchronous, uses a parent-level file | Deterministic, so it would hit the same product every run. mathjax-modern-font installed cleanly in all 3 runs | `Returned error message from getConfigsForProduct Error: The specified directory does not exist : …/marlin/cell/node_modules/mathjax-modern-font/chtml/dynamic` |
| 3 | Missing module in one product's node_modules (T1/T2, the old C1/C2 order effects) | cell is the first-installed product | No `Error Installing Package` in any run; ha failed once | `Error Installing Package <x>` earlier in the file, then `getConfigsForProduct Error: Cannot find module '<x>'` |
| 4 | Generator "module not found" in the environment hook (per-product dir) | Throws synchronously in `webpack()`; ha's bundle.json differs | Deterministic per product; the files are identical across branches | `=========================GENERATOR ISSUES====` / `Oops some of <dir> modules were not found in the project.` (no getConfigsForProduct prefix) |
| 5 | `bundler.custom.js` TypeError (T6), or webpack schema error | Fast | Deterministic, would hit all 3 sub-products, and the master applies the same transform successfully | `getConfigsForProduct TypeError: Cannot read property 'use' of undefined` / `WebpackOptionsValidationError` |
| 6 | Immediate compile failure (unresolvable entry) | — | A compile takes well over 1 s; same code on all branches | webpack stats `Entry module not found` / `Module not found` under marlin/cell |

**Read-only check:** `scp tools-11:~midtierbeta/logs/midtierbeta/marlin/UI/build.tgz .` (and the staging equivalent), then `grep -nE "getConfigsForProduct|ENOENT|include is not a function|does not exist|Cannot find module|GENERATOR ISSUES|Error Installing"`. The first match tells ranks 1–5 apart.

**If rank 1 is confirmed, the fix direction (for the ui-bundle-generator / config package owners, not a DS action):**
- Drop or guard the module-level `generator.run()`, or scope its output dir per process.
- Fix `.include` → `.includes`.
- Or pin the generator in the config package, as `1.3.9-marlin` did.
- Rerunning succeeds only by chance. Serialising (`--maxThreads=1`) would avoid it, but BDS's flags are ignored (note 20 §1).
- Prod runs the same config 1.3.12 and generator `latest`, so it is exposed too (unverified).
