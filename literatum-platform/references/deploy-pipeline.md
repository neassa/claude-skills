# How a deployment runs, end to end

Sources: deep/01 (Deploy Server), deep/02 (platform-tools), deep/03 (ansible), deep/07 (pugrenderer), plus live logs of real deployments (2026-09-23/24).

## 1. Request → tree
- A user (UI), githubbot (`/run`) or a cron template creates a row in `deploy_action`. ProductRefreshDeploy / ProductDeployNoBuild / ProductRestart / HostRestart / … become a **ProductRelease** row (original type kept in `display_action`).
- ProductRelease expands into children (same `parent_id`, ordered by `create_date, sequence_num`), then marks itself Success immediately. Children shown as `<ParentType> - <Child>`.
- Deploy Server re-syncs deployconf from git before deployconf-dependent actions (SvnRefreshScripts / SyncDeployConf).

## 2. The ordered children (typical ProductRefreshDeploy)
| # | Step | Runs on | Command (what actually executes) | Repo |
|---|---|---|---|---|
| 1 | GaiaCompatibilityCheck (prod) | DS | Java | deployserver |
| 2 | ProductBuild | tools-N | `setprod P F; sync_branches.sh; rebuild.py -rbsw -p P -f F` → gradle war → `~/warfiles/P_F_<ts>.war` | platform-tools, literatum, literatum-patch |
| 3 | ProductBuildStyleguide (auto) | tools-N | `Build-Deploy-Styleguide.sh -p P -f F -b <SG branch> -a <acct>` → `~/warfiles/styleguide_new_<acct>_P_F.tar.gz` | platform-tools, ui-products |
| 4 | SolrDeploy / SearchServiceDeploy / ProductConsumerDeploy / ProductAtmDeploy / ProductIngestionDeploy / XseDeploy / GaiaDeploy | tools host | `ansible-actions -s <svc> -p P -f F -a deploy` (Gaia: `-n <cluster>`) → `ansible-<svc>@<version>` | ansible-inventory, ansible-<svc> |
| 5 | PugrendererProductDeploy | tools host → renderer nodes | `ansible-actions -s pugrenderer -p P -f F -a deploy`: invalidate caches, copy tarball from `~/warfiles`, rsync into `styleguide-templates/<SG branch>`, `/refreshProducts`, validate `css/build.css` + `c=payment` | ansible-pugrenderer, styleguide-render-pug |
| 6 | backstage: HostStop → HostDeploy → ProductPatch → HostStart | `<g>-<env>-bks1` | `rstrt -b` / `rdply -n --no-styleguide -f F` (unpack latest WAR) / `patch.py -p P --families F` (patch VM) / `rstrt …` | platform-tools, literatum(-patch) |
| 7 | each web host (alphabetical): HostLock → Pause1Min → HostStop → HostDeploy → HostDeployStyleguide → HostStart → HostWaitForWebServer → HostWarmupTest (+HostEssentialTest prod) → HostExtraTest → HostUnlock | `<g>-<env>-webN` | opstool lock/unlock/serverup; `rstrt`; `rdply`; `deployStyleguide.py` (no-op); warm-up tests | platform-tools, opstool |
| 8 | rbackstage/backoffice: Stop → Deploy → Start | `rbks`/`bko` | same scripts | platform-tools |
| 9 | PugrendererInvalidateCache → CfInvalidateCache | tools / CDN | renderer `/invalidateCaches`; CDN purge | ansible-pugrenderer |

Conditions: each service step only if deployconf configures it for the product; ProductBuildStyleguide only with a styleguide version (and no k8s pugrenderer); HostDeployStyleguide only on web hosts.

## 3. How a step is judged
- The DS types commands into one interactive SSH shell per action, waits for the prompt, and **matches text** in the whole log (`validate-txt` / `invalid-txt` in `actions.xml`, or parsers in `SshExecutedVisitor`). Exit codes are ignored (and often lost anyway).
- Log per action: `GET /info/<id>.txt` (SSH command list + log); older ProductBuild attempts `_N`. Logs and Success/Cancelled rows are purged after 15 days.
- A Failure blocks every Scheduled action of the same account+family until someone acts; failed warm-up tests and `cancelOnFailure` types become `Cancelled` (`canceled_by='auto'`).

## 4. Where truth lives when something is off
| Question | Look at |
|---|---|
| Which code was built | ProductBuild log: `LIT BRANCH :`, `PATCH BRANCH:`, `The revision =`, LIT-656000 patch lines |
| Which playbook version ran | service step log: `SYNC [<dir>/<svc>/<version> with repo <url>]` |
| Why a patch failed | ProductPatch log tail; full output `/var/tmp/<epoch>.txt` on the backstage host; `DB_VERSION` row |
| Is the site really up | HostWaitForWebServer / HostWarmupTest, not HostStart |
| Which styleguide a node serves | renderer `GET /info?p=<P>&v=<SG branch>` (git hash from the build) |
| Which branch/version is configured | deployconf for that account (parse the XML) |
