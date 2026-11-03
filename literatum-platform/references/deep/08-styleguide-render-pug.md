# 08 — styleguide-render-pug (the pugrenderer service)

Read fully at tag `UI-Renderer-V2.6.7` (the version most deployconf pugrenderer clusters use; rmit uses V2.4.0, stag amps V2.7.0, `-pr-debian11` clusters 1.5.8 — not read): all of `src/` (NestJS/TypeScript, ~35 files), package.json, README, docker/production/dockerfile, .github/workflows. Skipped: `.npmrc`, `.ci.npmrc`, `.env.example`, `docs/postman/postman.json` (may hold tokens), tests. Secret-bearing lines filtered (e.g. `src/modules/worker.module/middlewares/global.middleware.ts:27`, express-session secret — not viewed).

## How it is built and run in Atypon envs
- ansible-pugrenderer (cluster-level deploy only) clones this repo at `pugrenderer_version` (deployconf cluster `version`, e.g. `UI-Renderer-V2.6.7`), builds with its own `Dockerfile.j2` (`npm ci` via GitHub npm registry → `npm run build` → `node:16.13.1-alpine`), tags `docker-registry:41238/atypon-pug-renderer:<node>-alpine-pgUI-Renderer-V2.6.7-d<deploy_version>`. The repo's own GitHub release workflow (GAR `us-docker.pkg.dev/.../styleguide-render-pug`) is **not** what the DC deploy uses.
- Container env (from ansible): `STYLEGUIDE_DIR`, `PUG_THREADS`, `PORT`, `HOSTNAME`, `TZ`, `DISABLE_ERROR_LOG_BODY` (+ `PROMETHEUS_PORT`/`PROMETHEUS_METRICS`). `LOGS_DIRECTORY` is **not** set → logs go to stdout = `docker logs <cluster>-<port>` (the mounted logs dir stays empty for app logs; `/debug/logs` answers "No logs path configured").
- Process model: Node `cluster` primary forks `PUG_THREADS` workers (re-forked on exit); primary listens on `PROMETHEUS_PORT` (default 3001) for metrics; workers serve on `PORT`.

## What it serves (all unauthenticated)
| Endpoint | Behaviour |
|---|---|
| `POST /?c=<component>&p=<product>&v=<SG branch>[&t=<template>][&f=<file>][&raw=1]` + JSON body | renders a pug/ejs template; not found → 404; any render exception → 500 with `e.toString()` |
| `GET /?p=&v=&r=<resource>` | static asset from `<STYLEGUIDE_DIR>/<v>/ui-products/<product path>/releasedAssets/`, resolved via `manifest.json` fingerprints; missing → 404 |
| `GET /?p=&v=&c=&t=` | returns the template file path (sendFile) |
| `GET /invalidateCaches?r=<branch>&p=<product>` | broadcast to all workers: delete cache keys containing both strings; with no params → flush all; then eager-reload the product list |
| `GET /refreshProducts` | flush all caches + reload product list |
| `GET /info?p=&v=` | the product's `releasedAssets/styleguide.info` (written by Build-Deploy-Styleguide: version, date, git short hash, ui-* versions) + dependency versions — **the quickest way to see which ui-products build a node is serving** |
| `GET /version`, `GET /` | renderer version |
| `GET /releases`, `/release/products?v=`, `/templates?p=&v=&c=` | listing |
| `GET /early-hints?p=&v=` | preload Link headers |
| `GET /debug/cache`, `/debug/logs` | cache dump (unauthenticated) / logs |

## Product discovery and caching (why cache invalidation matters)
- A "product" = any directory under `<STYLEGUIDE_DIR>/<branch>/ui-products/**` that contains `scss/build.scss` (recursive, skipping `node_modules`); keyed by the last directory name. A tarball missing `scss/build.scss` makes the product invisible → templates/assets 404.
- Everything goes through an in-memory `node-cache` with **no TTL**: product list, template lookups, **file-existence checks**, manifests, compiled templates. After new assets are rsynced, nodes keep serving the old view (including cached 404s) until `/invalidateCaches` or `/refreshProducts` — hence the invalidate/refresh tasks in ansible-pugrenderer and the final PugrendererInvalidateCache step. `DISABLE_CACHE=TRUE` disables it (not set by ansible).
- Template lookup order: product levels (deepest first), then inherited `node_modules` packages `@atypon/amps`, `life-core`, `ui-base`, `ui-core`, `ui-article`, `ui-theme`; structural `js-*-body`/`css-*-head` templates come from `@atypon/styleguide-core-partials`.

## Failure signatures (renderer side)
| Symptom | Meaning |
|---|---|
| ansible `Validate Released Assets` fails on `r=css/build.css` (404) | `releasedAssets/manifest.json` or `css/build-*.css` missing for that branch/product on the node, or product not discovered (no `scss/build.scss`), or stale cache |
| `c=payment` POST 404/500 | template missing (404) or pug/ejs render error (500, message in body and in `docker logs`) |
| `/invalidateCaches` non-200 | worker down / container restarting |
| Container keeps restarting | startup crash; see `docker logs`; workers auto-refork, primary crash = container restart (`restart_policy: always`) |
| Site shows old styleguide after a Success deploy | caches not invalidated on some node, or wrong branch dir (`v`) — check `/info?p=&v=` on each node |

## Other versions in use (compared 2026-09-25)
`pugrenderer_version` is a cluster attribute in deployconf. Usage:

| Env | V2.6.7 | V2.4.0 | Other |
|---|---|---|---|
| beta (midtierbeta) | 17 clusters | `midtierbeta-pr-rmit` (rmit-R), `midtierbeta-pr-aaas` (aaas-A17) | `midtierbeta-pr-debian11` = `atypon-pug-renderer-1.5.8`, node 14.16.0, ansible-pugrenderer `3.1` — **no product points at it** (looks orphaned) |
| stag (staging) | 17 | `staging-pr-rmit` (rmit-R) | `staging-pr-amps` (amps-A8) = **`UI-Renderer-V2.7.0` — this tag/ref does not exist** in atypon/styleguide-render-pug (newest tag V2.6.7; develop package.json = 2.6.7) |
| prod (literatum) | 23 | `literatum-pr-rmit` (rmit-B29) | — |

- **V2.7.0 risk:** a *cluster-level* deploy of `staging-pr-amps` pulls image `…:16.13.1-alpine-pgUI-Renderer-V2.7.0-d4.1`; only if that image is missing from the registry does it build, and the build's `git checkout UI-Renderer-V2.7.0` will fail (retries 5). Product deploys for amps don't build images, so they are unaffected. Whether the image exists in the registry is unverified.
- **V2.4.0 (package.json says 2.2.0) vs V2.6.7** — same NestJS app and the same endpoints/caching; differences (12 src files, +326/−75):
  - V2.6.7 compiles pug via `@atypon/pug-utils` (passes `productPath`) instead of raw `jade`.
  - Template lookup: V2.6.7 adds `@atypon/amps`, `life-core`, `ui-base` to the inheritance chain (V2.4.0: `ui-core`, `ui-article`, `ui-theme` only), supports nested component paths (`a/b/c`) and `generic`/`ecommerce` widget subfolders, and GraphQL template files (`c=gql&e=gql|data|varsJson`); V2.4.0 used `e=` as a type with `c=<component>`.
  - `/info`: V2.4.0 returns 404 when `styleguide.info` is missing; V2.6.7 returns "Build info not found" + a dependency-version report (ui-base/ui-core/ui-article/ui-theme/webpack-config).
  - `early-hints.json` moved from `releasedAssets/../` to the product root.
  - Triage impact: a styleguide built for newer ui-* packages (amps/life-core/ui-base inheritance, nested widgets, gql templates) can render wrong or 404 on V2.4.0 clusters (rmit, aaas) while working elsewhere.
- **1.5.8** — a different, single-file Express app (`index.js`, jade, node 14): same core endpoints (`/invalidateCaches` flushes everything — no product/release filter, `/refreshProducts`, `/version`, `/info`, `/release/products`), product discovery also via `scss/build.scss`, logs to `LOGS_DIRECTORY` (default `/usr/src/app/logs/`, i.e. the mounted logs dir), NewRelic, and an optional **WebDAV read/write mount of the whole styleguide dir** when `WEBDAV=true` (ansible doesn't set it). Only relevant if `midtierbeta-pr-debian11` is ever used.

## Notes / risks
- No auth on any endpoint (cache dump, logs, cache flush).
- `@atypon/pug-renderer-metrics: "latest"` in package.json (npm ci still uses package-lock).
- Error bodies echo `e.toString()` to callers.
- Request log only for status ≥ 400 or > 1 s, including full request/response bodies.
