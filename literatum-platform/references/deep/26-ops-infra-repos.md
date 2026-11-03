# 26 — Ops / infra repos: are they on the deploy path?

Read 2026-09-25, read-only. Clones under `$LIT_REPOS` are shallow single-commit clones; history below comes from the GitHub API (`gh api repos/atypon/<r>/commits`). The deploy path checked: `deployserver/config/*.xml` + `src` + `scripts`, `platform-tools`, `ansible-inventory`, `deployconf` (main @ ad1c87a), all `ansible-*` clones, `opstool`. Search = `safe_view.py --grep` on each repo name, its entry scripts, and its Rundeck job UUIDs, plus `gh search code --owner atypon` (default branches only; the last query hit the API rate limit).

## Summary

| Repo | Used? | By what | Notes |
|---|---|---|---|
| **k8s-rundeck** | **Yes (indirect)** | The Rundeck server `rundeck.devops.atypon.com` that opstool `RundeckApiService` calls (`opstool/.../RundeckUrl.java`: DATACENTER=http, CIP=https, same host) | Helm chart + images for the Rundeck server and worker on GKE (`kubernetes/rundeck/values-gcp.yaml:85`). It has **no job definitions**. On pod start, `postStart.sh:27-49` clones **`atypon/rd_jobs` branch `archives`** and imports the project jars and SCM. Last commit 2026-02-26 (PKG worker config). Many git-crypt secret files; not opened. |
| **atypon/rd_jobs** (NOT in the clone list) | **Yes** | The Rundeck job YAMLs that print the DS pass markers | Private. One branch per project: `gaia-fe_jobs`, `pugrenderer_jobs`, `common_jobs`, `audit_service`, … The DS job UUIDs match its filenames. Model gap, so it's flagged. |
| Rundeck-tool-wrapper | No | — | 2019 prototype (one commit, 2019-07-28): two sample job YAMLs (`Full Product Deployment`, `Deploy Product WAR`), dependency YAMLs, a Spring `dependencyRestApi`, and a bundled `rd` CLI. None of its job IDs appear in the DS. |
| k8s-opstools | No | — | Dockerfile that builds opstool from `ops-tools` into a Java 8 image (one commit, 2020-01-28). The DS runs opstool from `~/apps64/opstool` with java11 on the tools host, not from this image. |
| **ansible-traefik** | **CIP only** | DS `CipGenerateProfile`, `CipRemoveProfile`, `CipRestartTraefik`, `GaiaGenerateProfile` (`actions.xml:982-1008, 1703-1711`), via `checkoutGitRepo ansible-traefik` → `~/sourcegit/ansible-traefik` **master** | `accountFilter="cip"` / `office-jordan-cip` (`actions-config.xml:60-63, 793`). Inventory is only santaclara-01..03 and jordan-01/02. It generates Traefik file-provider profiles for the office CIP/QA hosts from `inventory.py product`. **Not** on the beta, stag or prod path. Active: last commit 2026-03-31 (IT-23555, gaia-cip profile). |
| ansible-haproxy | No | — | Installs HAProxy on two standalone GCP boxes (`aip-haproxy`, `tandf-haproxy`) that front `*-gcweb*` hosts. Last commit 2025-11-09 removed an exposed key; the one before that is from 2020. The **DC HAProxy in front of Literatum web hosts is elsewhere** (see below). |
| literatum-node-selector | No (tester tool) | — | Chrome MV3 extension ("Literatum Web Selector" 0.0.3). It reads product, host and port from the Consul deployconf API and sets request headers so the load balancer pins one web node. It depends on Consul being kept fresh by ConsulPopulate. Last commit 2026-01-21. |
| gaia-scripts | No | — | Ad-hoc JSPs (transform single/batch, cache delete per DOI, timestamp extractor) and Python stress tests for Gaia. Nothing on the deploy path references it. All work is from 2025-01-14. |
| platform-passport-cluster-tools | No | — | Maven tools: `zookeeper-mutex-cleanup-tool`, `zookeeper-discovery-patch`, `event-transport-flush-tool`, benchmarks. master was last changed 2018-11-07 (LIT-244610). GitHub `pushed_at` is 2024-10-03 (a push to some branch; not cloned). |
| literatum_dependency_analyzer | No (dead) | Its hooks exist but are off | classgraph runtime conflict reporter (`ldaVersion=0.0.1`). The dependency is **commented out** in literatum lit-2610 `atypon/literatum/build.gradle:148`. The hooks: `restart.py --generate-dependency-conflict-analysis-reports` (`restart.py:836, 1575-1599`), `platform-tools/uploadDependencyAnalysisReports.sh`, and DS `DependencyReportChecker` (`actions.xml:1712`, body `echo "skip"`, CIP qaa only, `PreExecuteVisitor.java:2912-2921`). Last commit 2025-01-20. |
| ansible-docker-registry | No | — | Cleanup and GC playbook for a self-hosted Docker registry (`hosts`: `docker-registry`; sample config deletes `helm-nexus-plugin` tags). Last commit 2019-02-14. The atm and searchservice builds push and pull **GAR** `us-central1-docker.pkg.dev/.../id/<image>` (`ansible-atm/group_vars/all:6-7,20-21`, same in ansible-searchservice), not this registry. |
| ansible-git-repos | No | — | 2018 cherry-pick and missed-merge-detector playbooks (`~/apps64/ansible/git-repos`). Last commit 2018-08-17. |
| ansible-infra | No | — | Infra-team roles: vault, openldap, freeradius, netbox, librenms, phpipam, postgres, mariadb, snmpd, jump-server. Last commit 2021-04-02. |
| id-ansible-playbooks | No | — | 2017 playbook that sets up i-d module git worktrees for `lit-1620..1730`. Last commit 2017-11-06. |

Other repos this work touched that are not in the clone list: **`atypon/rd_jobs`** (Rundeck jobs), **`atypon/puppet-control`** (DC HAProxy config), **`atypon/k8s-invApi`** (deployconf → Consul discovery), **`atypon/k8s-consul`** (`ConsulPutKV.py`, run by the ConsulPopulate job).

## Rundeck (k8s-rundeck + rd_jobs)

**Call chain**: DS action → `cd ~/apps64/opstool; java11 … com.atypon.opstool.rundeck.RundeckApiService -a <acct> -i <jobUUID> [-o opts] [-p <project> -w]` → Rundeck API v33 at `rundeck.devops.atypon.com` (k8s-rundeck on GKE) → job from rd_jobs → the job's log is streamed back → DS `validate-txt`.

**Which DS actions go to Rundeck, and are they on the beta/stag/prod path?**

| DS action | Job (rd_jobs branch / file) | Marker | On beta/stag/prod path? |
|---|---|---|---|
| ConsulPopulate | `common_jobs` `Consul/Consul populate from deployconf-3b8f04a7…` | `ConsulPopulate execution success` | **Yes.** Auto-scheduled after `GaiaProductSetAxelVersion` (`PostExecuteVisitor.java:1009-1045`, followed by GaiaDeploy). Also run manually (opsOnly). |
| GaiaDeploy (non-DC branch) | `gaia-fe_jobs` `update gaia cluster bundle_version-8c143b4e…` (literatum) / `…LIT-591161-92c55383…` (others) | `gaiadeploy execution success` | **No, today.** `ActionHelper.isDCGaia()` (`:414-429`) is true when the product's gaia `service_cluster` has `k8s_cluster="dc-gaia"`. In midtierbeta all 62 products use `dc-beta`, in staging 73 use `dc-stag`, in literatum 65 use `dc-prod` (plus one `aigateway-*` each), all dc-gaia, so they go to ansible-gaia. Each env still has one `k1` gaia cluster, but no product points at it. |
| K8sPugrendererDeploy/Destroy/Build | `pugrenderer_jobs` `Pugrenderer/…-cbbd4389/411a9a73/24236c76` | `K8sPugrenderer* execution success` | No: no product-level `<k8spugrenderer>` in midtierbeta or staging, and `requiresK8sPugrenderer` auto-cancels the action. |
| MountFS | `common_jobs` `FileSystem/MountFS-bbe57326…` | `MountFS execution success` | Hidden action (`visible="false"`). Called around `fc.py`. |
| UpdateStatusPage (non-ansible branch) | job `644be223…` (branch not checked: rate limit) | `COMPLETED SUCCESS` | literatum only. |
| GaiaClusterDeploy / GaiaBuild / GaiaFeTagRelease / DestroyGaiaCluster | `gaia-fe_jobs` `e401d86e` / `9c9442ab` / `d7c3f7c7` / `ae64794a`; GaiaBuild `23138522` not located | `gaia cluster deploy execution success` / `gaiabuild…` / `gaiadeploy…` / `gaiadestroy…` | Manual only. |
| AuditDeploy/Destroy/Backup/Restore | `audit_service` `Audit/…-05dfd132/3f042aac/007c9c7a/779cd9ea` (Deploy is named "Deploy Audit - **Disabled**") | `COMPLETED SUCCESS` | Manual only. |

Caveat: the job YAMLs in git are SCM **exports** (last syncs: gaia-fe_jobs 2024-11-21, common_jobs 2024-01-07, audit 2022-01-24, pugrenderer 2020-10-17). The live jobs live in Rundeck's DB and may have drifted. **Unverified**: whether the live jobs still match git.

**Failure signatures** (DS log text):
- `Connecting to http://rundeck.devops.atypon.com` then `ERROR: <body>` / `Couldn't run the job on Rundeck`. The job start was refused, the process exits 0 and no marker is printed, so the action is **Failed on missing marker** (note 18 §3.4).
- ConsulPopulate: `python3 ConsulPutKV.py -e <env> -c <cluster>`, then the stderr file is dumped, then `ConsulPopulate execution failed`.
- GaiaDeploy (Rundeck): `failed to verify default bundle` / `failed to verify bundle <V>` (Nexus `gcservices.atypon.com/nexus …/axel/<V>/axel-<V>.war` returns 404), `ERROR: missing consul token`, `Timed out verifying configmap in pods`, `gaiadeploy execution failed`. When the first step fails (`Cluster <env>-<cluster>-gaia not found, trying to deploy it`), the error handler runs JobWrapper → the gaia-fe cluster deploy job.
- K8sPugrendererDeploy: the `helm upgrade --install … --wait --timeout 500` line, then `K8sPugrendererDeploy execution failed`.
- Log truncated mid-job with no marker: a non-503/504 error from the log API (`followLogs` breaks silently).

**Success while broken** (from the job source):
1. **MountFS job is a no-op.** Its script is `echo "MountFS execution success"; exit 0`, and the real ansible mount logic below it is commented out (`MountFS-bbe57326…yaml:84-99`). The action always passes and mounts nothing.
2. **ConsulPopulate with Environment=null** loops over 11 envs, but `ex_st` is overwritten on each pass. Only the **last env's** result (office-jordan-cip) decides pass/fail, so failures for earlier envs (staging, literatum, midtierbeta, …) still print `execution success`. With a single env the status is correct.
3. **GaiaDeploy (Rundeck)**: `performance_sage` short-circuits with `skipping deployment` + `gaiadeploy execution success`. Pods that are not in `Running` phase are skipped by `break`, so if no pod is Running it still prints success. Only a `configinit.sh` failure sets `ex_status=1`.
4. **RundeckApiService never reads the job's final status** (note 18). Pass/fail comes only from the marker, so any job that echoes its marker before failing passes.
5. A stale Consul (ConsulPopulate silently failed or not re-run) affects consumers that read Consul deployconf: platform-tools `setprod --source-env` / `deployPropsDeployconf.py` (note 06), k8s-invApi discovery → HAProxy backends, and literatum-node-selector.

Secret-bearing lines (not recorded): `opstool/src/com/atypon/opstool/rundeck/RundeckApiService.java:73` (hard-coded API token), `k8s-rundeck/kubernetes/rundeck/configuration/postStart.sh:27`.

## ansible-traefik (CIP only)

- Branch: `master`, via `checkoutGitRepo` (`platform-tools/functions.sh:1968-1995`: `git reset --hard origin/master; git clean -fdx; git pull`).
- `main.yml` = `prepare-traefik` + `restart-traefik`, `serial: 1`, `hosts: {{ target }}`, where target is the DS account. `prepare-traefik` runs `python ~/apps64/ansible/inventory/inventory.py product [-n <p-f>]`, renders `profile.j2` / `sourcejsProfile.j2` / `gaiaProfile.j2` into `~/traefik/config-<date>/`, validates each with `yaml.safe_load`, links it as `~/traefik/config`, and installs a watcher cron.
- Pass = `COMPLETED SUCCESS` from `$util.ansibleCheckExitCode()`.
- Failure signatures: an ansible task `fatal:` on the yaml validate, or `inventory.py` output that is not JSON (then `dict['stdout']` indexing fails). **Unverified** against real logs.
- Success while broken: the host groups exist only for `office-santaclara-cip` / `office-jordan-cip`. A `target=cip` that matches no inventory group makes ansible run nothing (`skipping: no hosts matched`), and rc 0 could then pass `ansibleCheckExitCode`. **Unverified.** The ansible-traefik inventory has no `cip` group, so whether `CipGenerateProfile`, which is filtered to account `cip`, does anything depends on how `target=cip` resolves.
- `generate-profile.yml:68-77` restores the gaia profile from the **second-newest** `gaia-cip.yaml` (`[1]`), so if only one old copy exists, nothing is preserved.

## Front of the Literatum web hosts (not ansible-haproxy)

The DC front is **HAProxy managed by `puppet-control`** (`site-modules/profile/files/haproxy/literatum-backends.cfg.ctmpl`, consul-template). `k8s-invApi` registers the web backends in Consul from deployconf (`inv-API/discovery/literatum_discovery.py`; health check `/heartbeat` for web; see its `docs/DISCOVERY.md`). The optional deployconf `<product><haproxy><backend-snippet>` becomes a `snippet=<name>` Consul tag, used today only by `sso-shared-session` (one product each in midtierbeta and staging). HAProxy fronts only `type=web`. The DS `scripts/tf_argo_tunnel.sh` (IT-23963) pins ephemeral routes through Consul and the DC HAProxy. None of these repos were read in depth (read only via GitHub), so the web-reachability failure modes after a host deploy are **not modelled here**.

## ansible-docker-registry vs the atm/searchservice image locks

The image lock mechanism is in **ansible-atm / ansible-searchservice**, not in ansible-docker-registry:
- The lock file is `~/apps64/ansible/{atm,searchservice}/tmp/<svc>-<tag>.lock` (`create-locks.yml`).
- A second deploy that finds the lock waits up to 300 s (`wait_for state=absent`), then pulls the image from GAR `…/id/<svc>:<tag>` instead of building it.
- The lock is removed only by the last task of `create-image.yml` (`ansible-atm/.../create-image.yml:95-100`; searchservice `:66`).
- Failure: if the build or push fails after the lock was created, the lock stays behind. The next deploy with the same tag logs `Wait until lock file … is removed (300s)` → `Timeout when waiting for file …`. Fix: delete the stale lock file. (Log text is the standard ansible `wait_for` message. **Unverified** against a real DS log.)

## safe_view masking gaps seen during this pass

`safe_view.py` printed two secret-bearing lines **unmasked**: `deployserver/config/actions.xml:676` (the password argument on the `do_deactivateemployee.sh` line) and `deployconf/deployconf.midtierbeta.xml:5666` (`<sslpass>`). The values are not recorded here. The masker should be extended to cover CLI `-P <value>` arguments and `<sslpass>` elements.
