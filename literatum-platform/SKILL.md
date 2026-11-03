---
name: literatum-platform
description: Use when working on, debugging, or explaining anything about the Atypon Literatum platform as a whole — how the repos (literatum, literatum-patch, ui-products, styleguide-render-pug, deployconf, deployserver, platform-tools, ansible-*) connect, what runs where at runtime (web/backstage/patch servers, MSSQL, Solr/ZooKeeper, Kafka consumers, Redis, Cassandra VOS/Gaia cache, Gaia service, pugrenderer), and how a change travels from a branch to a running site through the Deploy Server. Start here, then load literatum-deploy-triage (failed deploys) or literatum-patch-cassandra-failures (patch VM / Cassandra errors).
---

# Literatum platform — the core map

The entry point: how the pieces fit together. Detail, with file:line citations, is in `references/`:

- `references/system-map.md`: every repo, what it is, who consumes it, how it's versioned.
- `references/runtime.md`: how the Literatum app works (build, config registry, Spring, server roles, persistence, patches, search, caches, Gaia, styleguide rendering).
- `references/deploy-pipeline.md`: a deployment end to end, and where each step's truth lives.
- `references/deep/README.md`: index of 28+ full-read notes (Deploy Server, platform-tools, every ansible repo, patch system, runtime, tests, styleguide toolchain, Gaia, dependencies, failure history, Jira resolutions).

**First time?** Follow `SETUP.md` in this folder (prerequisites, the clone list, the lit-2610 worktree, `TMPDIR`, secret handling). Paths below are relative to this skill's folder; in Cursor, resolve them against where the skill is installed.

Set `LIT_REPOS` to a folder of **read-only** clones of the atypon repos (`gh repo clone atypon/<repo> -- --depth 1`). Paths in the notes are relative to it. All Literatum-related code is under github.com/atypon (1,200+ repos); search the org before calling anything missing.

## Rules (why each exists)

1. **Read-only.** No creating, cancelling, rescheduling, restarting or unlocking Deploy Server actions; no UI Status dropdown; no DB access; no code changes unless asked. *The Deploy Server has no server-side auth, so every call is effectively made as an operator.*
2. **Never read secret values.** Repos, deployconf, logs and props hold plaintext credentials, often as bare literals no keyword filter catches. Read files through `../literatum-deploy-triage/scripts/safe_view.py` (it masks them), never open credential files, and put this rule word for word in every sub-agent's **first** prompt. *Founding incidents (2026-09-25): readers without the rule, or with name-only filters, printed cloud keys, a Jira login, an SFTP password and a GCP service account.*
3. **Understand from code, then conclude; verify, don't assume.** Mark each claim checked (log / code at commit / live search) or inferred. Grep-level reading gave wrong diagnoses more than once.
4. **Take repo/branch/version from the failing log first**, then deployconf. A repo you meet that isn't in `references/system-map.md` is a gap: say so.
5. **A step that did nothing doesn't mean nothing happened.** Check its siblings (HostDeployStyleguide is a no-op; PugrendererProductDeploy delivers the styleguide).
6. **Read current code at the product's own branch.** Update clones first, and read at the branch that env builds (deployconf `<source>`; beta, stag and prod differ). `master` is not what they run. State branch + commit behind every code claim.
7. **Parse deployconf with an XML parser**, not grep: values are often attributes.
8. **Failure is reliable; Success often isn't** (text-matched verdicts, lost exit codes). See `../literatum-deploy-triage/references/false-successes.md`.

## The system in one picture

```
                         ┌──────────────── GitHub (atypon/*) ────────────────┐
  code:  literatum ──┬── literatum-patch        ui-products ── styleguide-render-pug
                     │   (SQL + patch stubs)    (styleguide)   (renderer app)
  config: deployconf (per-env XML: products, hosts, branches, clusters, versions)
  ops:    platform-tools (~/scripts)  ansible-inventory + ansible-<svc>  opstool
  orch:   deployserver ── Postgres deploy_action ── SSH ──▶ hosts
                         └───────────────────────────────────────────────────┘

  Deploy Server ─(SSH, typed shell)─▶ tools-N ── build WAR (gradle) ──▶ ~/warfiles (NFS home)
                                           ├─ build styleguide (utypon) ─▶ ~/warfiles/styleguide_new_*.tar.gz
                                           └─ ansible-actions -s <svc> ──▶ Solr/ZK, consumers, Cassandra, Redis,
                                                                          Gaia, pugrenderer containers
                 ─(SSH)─▶ <group>-<env>-bks1   HostStop → HostDeploy (unpack WAR) → ProductPatch (patch VM) → HostStart
                 ─(SSH)─▶ <group>-<env>-webN   Lock → Stop → Deploy → Start → WaitForWebServer → WarmupTest → Unlock

  Runtime (one site):  browser → CDN → web JVM (Literatum, server.type=web)
        ├─ MSSQL (JDBC, custom TableDef persistence)        ├─ Solr (search; via ZooKeeper)
        ├─ Redis (cache / ArticleMetrics)                   ├─ Cassandra (VOS data; Gaia output cache gaia_<p>_<mode>)
        ├─ Gaia service (remote XSLT/HTML transforms)       ├─ pugrenderer (styleguide templates + assets)
        └─ Kafka (indexing events) ─▶ consumer ─▶ Solr       backstage JVM (server.type=backstage): ingestion, workflows, robots
```

## Environments

- Deploy Server **account** = env: beta = `midtierbeta`, stag = `staging`, prod = `literatum` (also readonly, rorehearsal, lts, cip, gcp…). Each has `deployconf.<account>.xml`; the unix user on hosts has the same name.
- A **product** = a site (e.g. `aaas`), deployed per **family** (e.g. `A17`). Host names: `<group>-<env>-<role><n>` with role `web`, `bks` (backstage), `rbks`, `bko`; build/ops hosts `tools-N`.
- Stag and beta both run `build.mode=beta`, so their Gaia keyspaces have the same **name** `gaia_<product>_beta` — but each env's product points at its own Cassandra cluster (e.g. informs: `beta-cassandra-literatum3` vs `cassandra-stag-lit3`), so the data is **not** shared unless the clusters are the same (check deployconf `<cassandra cassandra_cluster_name>`).
- Branches: beta mostly `lit-2610` / `master` / `develop` styleguide; stag and prod run dated maint branches (`lit-2610-maint-YYMMDD-<sha>`, styleguide `maint-YYMMDD-<sha>`). Read the current value from deployconf — they move weekly.


## Where to go next

| You need… | Load |
|---|---|
| Why a deployment failed / which step / which repo | `literatum-deploy-triage` |
| ProductPatch died with Cassandra / `KILLING THE SYSTEM` / `table … does not exist` | `literatum-patch-cassandra-failures` |
| An Ansible-driven step (Solr, consumer, Gaia, pugrenderer, Cassandra, ZK, Kafka, ATM, ELK…) failed or lied | `literatum-ansible` |
| How a subsystem works | `references/runtime.md`, then the matching `references/deep/` note, then `$LIT_REPOS/literatum/AGENTS.md` + `docs/architecture/*.md` (see corrections in `runtime.md`) |
| Which repo/script a deploy step runs | `references/deploy-pipeline.md` |

## Known gaps (as of 2026-09-26)

- Literatum as a whole (~34k Java files): only the deploy-relevant subsystems are read (patch system, startup, backstage/cluster, ingestion, access rules, search/REST/DB). Estimated ~35% overall.
- Repos seen but not read: puppet-control (HAProxy in front of web hosts), k8s-invApi (Consul registration), Dailypatch-frontend, dailyPatchDashboard. solr-plugins, id-index and rd_jobs are being read (notes 29, 30).
- Prod: known from code only (GaiaCompatibilityCheck, HostEssentialTest); logs were read for beta and stag only.
- Host-side facts (bashrc, NFS layout, registry contents, `/var/tmp` patch output, styleguide `build.log`) and DB state: ask the user.
