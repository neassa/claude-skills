# Deep notes index

Full-read notes per repo/subsystem, with file:line@commit citations. Written by read-only reader agents between 2026-09-24 and 2026-09-26. Claims marked *verified* in `literatum-deploy-triage` were re-checked by hand; notes 16 and 27 are adversarial re-checks of earlier notes. The rest is the reader's own reading.

| # | Note | Covers |
|---|---|---|
| 01 | `01-deployserver.md` | Atypon Deploy Server — full read notes |
| 02 | `02-platform-tools.md` | platform-tools (`~/scripts` on hosts) as driven by the Deploy Server |
| 03 | `03-ansible.md` | Ansible deploy layer (ansible-inventory + service repos) |
| 04 | `04-literatum-patch-system.md` | Literatum DB patch system, end to end |
| 05 | `05-literatum-build-config-gaia.md` | Literatum build, config bootstrap, Gaia FE cache, and the `was` ADVISER failure |
| 06 | `06-deployconf-uiproducts.md` | deployconf (beta/stag/prod) + ui-products / Build-Deploy-Styleguide |
| 07 | `07-ansible-pugrenderer.md` | ansible-pugrenderer: how the styleguide actually reaches the sites |
| 08 | `08-styleguide-render-pug.md` | styleguide-render-pug (the pugrenderer service) |
| 09 | `09-platform-tools-rest.md` | platform-tools: every other script the Deploy Server calls |
| 10 | `10-ansible-infra.md` | Ansible infra repos: zookeeper, kafka, elk, mssql, xse |
| 11 | `11-ansible-services.md` | Ansible service repos: atm, ingestion, searchservice, proxysolr, tools (+ inventory mismatches) |
| 12 | `12-literatum-runtime.md` | Literatum runtime: request path, startup dependencies, search, caches |
| 13 | `13-ds-failure-history.md` | Deploy Server failure history, beta + stag (2026-09-10 → 2026-09-25) |
| 14 | `14-jira-resolutions.md` | How LIT Jira tickets resolved Deploy Server failures (last ~12 months) |
| 15 | `15-gaia-cmsroot-idcore-rootpom.md` | gaia, cms-root, id-core, root-pom: how they feed Literatum deploys and how they fail |
| 16 | `16-claim-verification.md` | Adversarial verification of 20 claims from notes 09–15 |
| 17 | `17-literatum-backstage-access-cli.md` | Literatum backstage robots/mutex (LIT-683431), ingestion, access/read-only, CLI tool JVMs, registry/pool errors |
| 18 | `18-opstool-opscommon.md` | opstool + opscommon: what the Deploy Server's opstool commands actually check |
| 19 | `19-warmup-tests.md` | Host test actions (HostWarmupTest / HostEssentialTest / HostExtraTest / HostTestJane) |
| 20 | `20-styleguide-toolchain.md` | Styleguide build toolchain: utypon-cli, styleguide-bundler, ui-core, composite actions |
| 21 | `21-passport-rootpom-idsearch.md` | platform-passport-cluster, root-pom, id-search: how they feed Literatum and how they fail |
| 22 | `22-gaiafe-axel-devprod.md` | gaia-fe, axel, developer_productivity: how they work and how they fail |
| 23 | `23-testypon-qa.md` | testypon, the warm-up HTTP client, HostTestJane, and the QA repos |
| 24 | `24-marlin-cell-sg.md` | marlin ProductBuildStyleguide: `marlin/cell | failed | 898 ms` |
| 25 | `25-patching-repos.md` | The four "patching" side repos, and the physio lit32046 NPE |
| 26 | `26-ops-infra-repos.md` | Ops / infra repos: are they on the deploy path? |
| 27 | `27-filter-recheck.md` | Filter re-check of negative claims in notes 09–16 (2026-09-25) |
| 28 | `28-literatum-search-rest-db.md` | Literatum search/indexing, REST API, persistence, backstage publish: post-deploy breakage and log signatures |

| 29 | `29-solr-plugins-id-index.md` | solr-plugins (schema from id-core), id-index Kafka consumer: versions, silent doc loss, retries, lag |
| 31 | `31-literatum-ingestion-publish.md` | ingestion intake → engine → publish → post-publish; no dead-letter, robot-dependent scheduling |
| 32 | `32-literatum-access-licensing.md` | identities, sessions/IdPs, access decision, licenses; ReadOnlyException decision tree (aiaa) |
| 33 | `33-literatum-content-delivery.md` | content model, URL→service map, filesystem/VOS/Gaia cache, HTML/PDF delivery, CDN headers |
| 34 | `34-literatum-pages-widgets.md` | PageBuilder/pb2, pugrenderer client, ux3OutputCache key, styleguide manifest, post-deploy page breakage |
| 35 | `35-lb-puppet-invapi.md` | HAProxy/keepalived/Cloudflare chain, k8s-invApi → Consul, health check = `/heartbeat?id=achs` (lock NOT honoured) |
| 36 | `36-dailypatch-ui-themes.md` | Dailypatch dashboards (stale) and API, ui-theme-* pins and develop drift |
| 30 | `30-rd-jobs.md` | Rundeck job definitions (rd_jobs branches), DS action → job map, Rundeck false successes |
