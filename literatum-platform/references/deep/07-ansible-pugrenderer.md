# 07 — ansible-pugrenderer: how the styleguide actually reaches the sites

Read fully: branch `4.1` (47 files) of atypon/ansible-pugrenderer, plus diff vs `4.0` (both are used: deployconf pugrenderer clusters in beta/stag/prod have `deploy_version` 4.0 or 4.1). `meta/` role dependencies read. Secret-bearing lines filtered (2 lines in `group_vars/all`, 1 in `released-assets-download.yml` were not viewed). Also read `ansible-inventory/pugrenderer.py` (inventory side). Live evidence: prod utb deployment `92404655…`, PugrendererProductDeploy log `c66138c1…` (2026-09-23), HostDeployStyleguide logs `b2b2aebf…` (prod) and `c5c166bf…` (beta), ProductBuildStyleguide log `ec0cb538…` (beta rmit).

## The real styleguide chain (per deployment)
1. **ProductBuildStyleguide** (tools host, round-robin): `Build-Deploy-Styleguide.sh -p P -f F -b <SG branch> -a <acct> [-g group]` → checkout ui-products `<SG branch>` → `utypon build` → tar+gzip `styleguide_new_<acct>_<P>_<F>.tar.gz` → moved to `~/warfiles/` (move unchecked).
2. **PugrendererProductDeploy** (tools host): `ansible-actions -s pugrenderer -p P -f F -a deploy` → `atypon/ansible-pugrenderer` at the cluster's `deploy_version` → hosts = the pugrenderer **nodes of the product's cluster** (`<styleguide><pugrenderer-cluster>`; containers run on the web machines, e.g. `prod-pr-literatum7` on literatum7-prod-web1..5).
   - `deploy.yml` (label=product): role `deploy` → deps `create-paths` → mkdirs + **GET `http://<node>:<port>/invalidateCaches`** (must be 200, 5×3 s) on every node; `deploy-product.yml` only prints "Deployment of styleguide templates … is completed" (no container restart for products); role `validate` → TCP check on the node port (timeout 300 s). `serial: [1,3]`, `max_fail_percentage: 0`.
   - `deploy-released-assets.yml`:
     a. first node only: clean `~/apps64/ansible/pugrenderer/tmp/styleguide_<USER>_<P>_<F>`, then **`cp ~/warfiles/styleguide_new_<USER>_<P>_<F>.tar.gz` there**. `<USER>` = unix account = DS account (midtierbeta / staging / literatum). ~ is shared (the task is literally named "Copy … From NFS"), so the tarball ProductBuildStyleguide left on the tools host is visible (inferred from task names + paths `/na101…/home/<acct>`). If cp fails → `fail: Object styleguide_new<USER>_<P>_<F>.tar.gz is not found in FTP Server or Defined Path. releasedAssets deployment for <P>-<F> has failed…`.
     b. every node (`serial: [1,3,5,7,9,100%]`): mkdir `<base>/styleguide-templates/<SG branch>/ui-products`; copy + unarchive tarball into `temp-register/<P>_<F>`; `rsync -azvhrlqc --delete-after` the product dir (or `sg_group` dir; `ux3` copies node_modules/ux3/classic/photo/eureka) into `styleguide-templates/<SG branch>/ui-products`; clean temp; **GET `/refreshProducts`** (if renderer version ≥ 0.0.51; 5×60 s).
     c. validate on every node: **POST `?p=P&v=<SG branch>&c=payment`** and **GET `?p=P&v=<SG branch>&r=css/build.css`**, each up to 10×60 s — failure means the renderer does not serve released assets for that branch.
     d. first node: cleanup tmp.
   - Base path on node: `/local/ssd<HOME>/servers/common/pugrenderers/<cluster>/docker_pugrenderer_<port>/` (styleguide-templates, logs, temp-register, pug-renderer). Container name `<cluster>-<port>`; docker socket `unix:///var/run/docker-<USER>.sock`.
3. **HostDeployStyleguide (w)** on each web host: no-op since platform-tools LIT-585088 (prints `Not Production, Exiting.` / `>>> Finished styleguide deployment`).
4. **PugrendererInvalidateCache** + **CfInvalidateCache** at the end of the deployment (the former = `invalidatecaches.yml`: GET `/invalidateCaches?r=<SG branch>&p=<P>` on every node).

Cluster-level deploy (`-n <cluster> -a deploy`, label=cluster) is different: `create-image.yml` pulls image `docker-registry:41238/atypon-pug-renderer:<node>-alpine-pg<ver>-d<deploy_version>` or builds it from **`git@github.com:atypon/styleguide-render-pug.git`** at `pugrenderer_version` (npm ci against GitHub npm registry), then recreates containers, validates TCP, optional cleanup of unused SG branches (`cleanup_styleguide`, default false).

## Inventory (ansible-inventory/pugrenderer.py)
- Product groups: `<P>-<F>` with vars `label=product`, `pugrenderer_cluster_name`, `styleguide_versions=[<SG branch>]`, `sg_group` (if `<styleguide><group>`), node host:port list; cluster groups: `label=cluster` with the union of SG versions of its products.
- A product whose `<pugrenderer-cluster>` names an undefined cluster is silently absent (e.g. prod chrysalis) → `invalid choice` exit 2.
- Disabled products still feed SG versions (see note 06).

## Failure signatures
| Signature | Meaning | Class |
|---|---|---|
| `Object styleguide_new<USER>_<P>_<F>.tar.gz is not found in FTP Server or Defined Path. releasedAssets deployment … has failed` | tarball missing in `~/warfiles` — ProductBuildStyleguide failed or its (unchecked) mv failed, or wrong account/product/family | CODE/HOST (upstream styleguide build) |
| `create-paths : Invalidate styleguide caches` fails (non-200 after 5×3 s) | a renderer node/container is down or port wrong | SVC |
| `validate : Validate service is up (TCP Check)` timeout (300 s) | container not listening | SVC |
| `released-assets : Validate Released Assets` fails after 10×60 s | renderer can't serve `css/build.css` / `c=payment` for that SG branch — bad/partial assets, wrong branch dir, renderer too old | CODE/SVC |
| `released-assets : Update product map` (`/refreshProducts`) non-200 after 5×60 s | renderer rejected refresh | SVC |
| `unarchive` / rsync errors | corrupt tarball or disk/permissions on node | HOST |
| cluster deploy: git checkout of styleguide-render-pug fails / docker build fails (`npm ci`) | SSH key / GitHub npm registry auth / renderer build | CRED/CODE |
| `WARN [Skipping updating the repo.]` from ansible-actions | stale playbooks ran | TRANSIENT (silent) |

## Notes / risks
- Product deploy never restarts renderer containers; assets are hot-swapped via rsync + `/refreshProducts` + cache invalidation.
- `rsync --delete-after` of the whole product dir per node, rolling 1,3,5,7,9,100% — a bad tarball is caught only at validate on the first node (serial 1), which stops the rest (`max_fail_percentage: 0`).
- `invalidatecaches.yml` URL has a stray `'` at the end of the query string (`…&p={{ product_name }}'`) — harmless for most servers but worth knowing.
- `status.yml` message says `-consumer-` (copy-paste).
- New repo in the chain: **atypon/styleguide-render-pug** (renderer app, cluster-level image builds only) — not read.
- Prod `prod-pr-literatum7` recap listed a node on `literatum7-beta-web1` — cluster membership comes from deployconf; worth confirming with owners (not investigated).
