# Which repo and branch each step uses

All repos are under github.com/atypon. Local read-only clones: `$LIT_REPOS/`.

| Step | Code that runs | Repo(s) | Branch / version comes from |
|---|---|---|---|
| ProductBuild | `setprod`, `sync_branches.sh`, `rebuild.py` → `./gradlew :product:<p>:war` | platform-tools (as `~/scripts`), **literatum**, **literatum-patch** | literatum = segment before `/atypon` in deployconf `<product><source>`; log prints `LIT BRANCH :`, `PATCH BRANCH:`, `The revision =`. Patch branch: plain `lit-NNNN` or `master` → literatum-patch `master`; anything else → same-named branch (must exist). |
| (build deps) | Gradle | literatum `atypon/literatum/versions.properties` (authoritative; root BOM only manages `com.atypon:registry`) | e.g. `cmsapisVersion` (cms-apis from atypon/cms-root), gaia-registry/gaia-core 1.7.3 (atypon/gaia) |
| (build-time source patch) | `rebuild.py` applies `~/scripts/patch/*.txt` on master / lit-2610* | platform-tools | file names are swapped: master gets `lit-2610.maint.txt`, maint branches get `common`+`master.patch.txt` |
| ProductBuildStyleguide | `Build-Deploy-Styleguide.sh` → utypon | platform-tools, **ui-products** | deployconf `<styleguide><version>` (priority: `k8spugrenderer/@styleguide_branch` > `styleguide/version` > `products-integration`); group from `<styleguide><group>` |
| PugrendererProductDeploy (**this is what deploys the styleguide**) | `ansible-actions -s pugrenderer -p P -f F -a deploy` on a tools host | **ansible-pugrenderer** (read fully, notes 07); cluster-level image builds also use **atypon/styleguide-render-pug** (not read) | pugrenderer cluster `deploy_version` (prod-pr-literatum7 → `4.1`); styleguide branch = product `<styleguide><version>`; takes the ProductBuildStyleguide tarball from `~/warfiles`; tasks `released-assets : …`, `Invalidate styleguide caches`, `Deploy docker pugrenderer node`; targets the pugrenderer containers on the web machines |
| HostDeployStyleguide (w) | `setprod P F; ~/scripts/deployStyleguide.py` on each web host | platform-tools | no-op since LIT-585088 (prints `Not Production, Exiting.`) |
| SolrDeploy etc. | `ansible-actions -s solr` | ansible-inventory (wrapper), **ansible-solr** | product `<solr deploy_version>`; if absent/auto/fallback/latest → product `lit_version` matched in `atypon_lifecycle.json` on the service repo's `master` (last `startswith` match wins; else `fallback`). Checkout at `~/apps64/ansible/<svc>/<version>`; log line `SYNC [<dir> with repo <url>]` is authoritative. |
| ProductConsumerDeploy | `ansible-actions -s consumer` | ansible-consumer | product `<consumer deploy_version>` or lifecycle; requires `<solr>` and `kakfa_cluster_name` in deployconf |
| GaiaDeploy | `ansible-actions -s gaia -n <cluster>` | **ansible-gaia** (beta/stag/prod clusters use `2.0`, identical to master as of 2026-09-25) | gaia service cluster `deploy_version` (e.g. `dc-beta` = 2.0); bundle = product `<gaia bundle_version>` |
| Cassandra / Redis / ZK / Kafka / ELK / MSSQL / XSE / ATM / Ingestion / SearchService / ProxySolr / tools | `ansible-actions -s <svc>` | `ansible-<svc>` (repo = `git@github.com:atypon/ansible-<svc>.git`, `ansible-actions.py:20,314`) | named cluster `deploy_version` or lifecycle |
| ProductPatch | `patch.py` → `run_gradle.sh patch runWithJavaExec` → `DbGradlePatcher` | platform-tools, literatum (patch framework + `com.atypon.modules.migration.*`), literatum-patch (SQL files + `com.atypon.patch.*` stubs) | runs against the **deployed** webapp classes and, on DC hosts, the deployed `iapps/patch` files; branch = the one last deployed |
| HostDeploy / HostStop / HostStart | `redeploy.py`, `restart.py` | platform-tools | deployconf hosts/processes for the env |
| Lock/Unlock/WaitForWebServer | opstool `DeployFamilyAction` | opstool (jar on hosts; repo name match only, unverified) | — |
| Gaia CI/K8s/QA actions | Rundeck / Jenkins / GitHub Actions | outside these repos | — |

## deployconf per env
- File per account: `deployconf.midtierbeta.xml` (beta), `deployconf.staging.xml` (stag), `deployconf.literatum.xml` (prod). DS syncs `main` every ~10 s.
- `<product name enabled deployfamily>` — beta has many products disabled (36 of 87 enabled).
- Per-env product tables (branch, SG version, clusters, hosts) are in `../literatum-platform/references/deep/06-*.md` §4 — refresh from the repo before relying on them.
- Stag and beta both run build mode `beta`, so Gaia keyspaces have the same **name** `gaia_<product>_beta` in both — but each env points at its own Cassandra cluster (check `<cassandra cassandra_cluster_name>`), so they are not shared unless the clusters are the same (informs: different, checked 2026-09-25).
- Reading deployconf: filter out secret-bearing attributes (`<database-servers>`, passwords) — read only names/hosts/branches.

## Practical facts (checked 2026-09-26)

- **Update clones before reading** (they are shallow, default branch only):
  - default branch: `git -C $LIT_REPOS/<r> fetch --depth 1 origin <default> && git -C $LIT_REPOS/<r> reset --hard FETCH_HEAD`
  - another branch (e.g. lit-2610): `git -C $LIT_REPOS/literatum fetch --depth 50 origin lit-2610:refs/remotes/origin/lit-2610`, then read with `git -C … show origin/lit-2610:<path>`, or refresh the worktree `$LIT_REPOS/literatum-lit-2610` (a *detached* worktree of the literatum clone, so `git status` says "HEAD detached"): `git -C $LIT_REPOS/literatum-lit-2610 checkout --detach origin/lit-2610`
  - a single file at any ref: `gh api "repos/atypon/<repo>/contents/<path>?ref=<branch>" --jq .content | base64 -d` (then read it with `scripts/safe_view.py`).
- **Paths in literatum:**
  - midtier props: `atypon/product/midtier/conf/midtier.props.IBM*.xml`
  - base props: `atypon/literatum/conf/literatum.props.xml`
  - dependency pins: `atypon/literatum/versions.properties`
  - root-pom version: `atypon/build.gradle` (`parentPomVersion`, ~line 78)
  - product props: `atypon/product/<p>/conf/<p>.props.xml`
- **Tag names:** root-pom `atypon-root-pom-2610.0.X`; styleguide renderer `UI-Renderer-V2.6.7`; gaia-fe `gaia-fe-1.6.7`. Use `git ls-remote --tags origin | grep <ver>` rather than guessing.
- **Account-level actions** (e.g. `CassandraDeploy`, `scope="AccountLevel"` in `deployserver/config/actions-config.xml`) carry **no product**, so a product-filtered search never finds them. Search them without a product: `ds_search.py <acct> "" CassandraDeploy 200`.
- **Jira:** LIT lives on `atypon.atlassian.net` (Atlassian connector cloudId `6bfba5f3-1c23-4def-98c0-c0592a82537c`), read-only JQL. Not the wiley-global site.
- **Search the org** before calling code missing: `gh search code "<file or symbol>" --owner atypon`. Package names and repo names often differ (e.g. `@atypon/styleguide-webpack-configuration` lives in `styleguide-bundle-configurations`).

