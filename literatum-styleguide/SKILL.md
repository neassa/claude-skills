---
name: literatum-styleguide
description: Use for the Literatum styleguide / front-end chain — ui-products, ui-theme-* and ui-core pins, utypon-cli and styleguide-bundler builds (ProductBuildStyleguide, Build-Deploy-Styleguide.sh), pugrenderer (styleguide-render-pug) delivery (PugrendererProductDeploy, PugrendererInvalidateCache, HostDeployStyleguide), PageBuilder widgets and ux3OutputCache, and symptoms like `Build Failed For The Following Products`, `'failed' | 898 ms`, `npm ERR! 404 … @atypon`, old CSS / widget HTML after deploy, 404 on fingerprinted assets. Strictly read-only.
---

# Literatum styleguide chain (read-only)

**Paths:** relative to this skill's folder (`../literatum-platform/references/deep/`); repos under `$LIT_REPOS`. Read files only through `../literatum-deploy-triage/scripts/safe_view.py`.

## The chain, and which step really does the work

1. **ProductBuildStyleguide** (tools host) runs `platform-tools/Build-Deploy-Styleguide.sh`:
   - checks out `ui-products` at the deployconf `<styleguide><version>` branch into a **shared** `~/sourcegit/ui-products-branches/<branch>`;
   - installs `@atypon/utypon-cli` (`@latest` on beta/stag, pinned on prod);
   - `utypon build optimized` runs `styleguide-bundler` (the real logic);
   - tars `~/warfiles/styleguide_new_<acct>_<p>_<f>.tar.gz`.
2. **PugrendererProductDeploy** (ansible-pugrenderer 4.0/4.1) **delivers** it: copies the tarball, creates `styleguide-templates/<branch>`, rsyncs, flushes caches (`/invalidateCaches` with no params = `flushAll`), and redeploys the renderer containers on the web hosts.
3. **HostDeployStyleguide** is a **no-op** since LIT-585088: it prints `Not Production, Exiting.` and can't fail.
4. **PugrendererInvalidateCache**: the URL ends `&p=<product>'` (stray quote), so the per-product invalidate very likely clears nothing, yet returns 200. **CfInvalidateCache** is a stub that never purges Cloudflare.

## Build failures

| Signature | Meaning |
|---|---|
| status row `'<…>/ui-products/<p>/<sub>' \| 'failed' \| '<~900> ms'` → `Build Failed For The Following Products` | failed before webpack ran (config/dependency load). The real error is only in `~<acct>/logs/<acct>/<p>/UI/build.tgz` on the tools host. For marlin, the failing sub-product hopped between cell and ha across days: likely a race in `@atypon/ui-bundle-generator` (`"latest"` in styleguide-bundle-configurations), since all parallel workers write the same generator folder. |
| `npm ERR! 404 … registry.npmjs.org/@atypon%2f<pkg>` → `Cannot find module '@atypon/<pkg>'` | the `@atypon` scope fell back to the public registry: a **race on the NFS-shared `~/.npmrc`**, which every build rewrites (the nightly 01:00 batch runs about 9 at once). Re-run passes. |
| `sh: 1: patch-package: not found` | utypon-cli postinstall noise; **not** the cause |
| `PRODUCT MISSING OR NOT FOUND …` | grouped product without `<group>` in deployconf, or no dir on that branch |
| git `pathspec … did not match` then a build of the *previous* branch | git steps are unchecked: it built stale code and `styleguide.info` lies |
| `BUILD COMPLETED` with a missing tarball | the tar/gzip/mv failures aren't checked |

Dependency drift: themes and ui-core are **git tags resolved by npm at build** (`ui-theme-classic#v2.8.84` → nested ui-core/ui-base pins). `ux3/*` submodules and aea, nato, rsc and mms-nextgen float on `#develop`. `git submodule update --remote` makes **every** build depend on four develop tips. Install errors are swallowed.

## Runtime (pages and widgets)

- Widgets call the renderer at `POST /?c=&t=&p=<frontend/nodejs/product-name>&v=<styleguide/version>`. `v` must equal the renderer's `styleguide-templates/<branch>`. A non-2xx answer is never retried: `Service replied with error… Status Code: 404|500`. The result is an error box, or a literal `<!-- pb/async #id/view -->` left in the page.
- **Old widget HTML after a styleguide-only deploy:** the `ux3OutputCache` key = widget key + `frontend/nodejs/product-name` + view context, with **no styleguide version and no TTL** (`NodeJsJadeRenderer.java:122-128`). Bypass with `?ux3Cache=false`; a restart clears it.
- **404 on fingerprinted CSS/JS:** the manifest refreshes only on `StyleguideDeployedEvent`, which nothing in the Deploy Server path fires. The only caller of `/action/styleguideDeployed` is the never-run `deployStyleguideNew.py`. Meanwhile `rsync --delete-after` removed the old files. Fix: restart the web JVM.
- Diagnostics: `/action/pugrendererInfo`, `?showJson`, `?ux3AsyncRender=false`; renderer `/releases`, `/info?p=&v=`, `/templates?c=`.
- `Invalid column name PAGE_REMOVED/DROPZONE_ORDER` = pb2-core Liquibase columns not applied, i.e. the DB patch didn't run.

## Deep notes

`06-deployconf-uiproducts.md`, `07-ansible-pugrenderer.md`, `08-styleguide-render-pug.md`, `20-styleguide-toolchain.md`, `24-marlin-cell-sg.md`, `34-literatum-pages-widgets.md`, `36-dailypatch-ui-themes.md`.

## Founding failures

- For a styleguide problem, the first instinct is to read HostDeployStyleguide. It deploys nothing, and PugrendererProductDeploy (earlier in the tree) does the work.
- `patch-package: not found` was reported as the cause of marlin's styleguide failures. The install actually completed, and the real failure was a sub-product failing in under a second, logged only in `build.tgz`.
