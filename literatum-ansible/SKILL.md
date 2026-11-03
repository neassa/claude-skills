---
name: literatum-ansible
description: Use when a Literatum Deploy Server step that runs Ansible fails or misbehaves (SolrDeploy, ProductConsumerDeploy, GaiaDeploy, PugrendererProductDeploy, CassandraDeploy, ZkDeploy, KafkaClusterDeploy, ProductAtmDeploy, ProductIngestionDeploy, Elk*, ProxySolrDeploy, …), when a log shows `ansible-actions`, `SYNC [...ansible/<svc>/<ver>...]`, `Error [51]`–`[55]`, `COMPLETED SUCCESS/FAILURE`, `fatal: [...] UNREACHABLE`, or when asked how atypon/ansible-* repos, ansible-inventory or a service's deploy_version work. Strictly read-only.
---

# Literatum Ansible deploy layer (read-only)

Load `literatum-platform` for the overall map; use `literatum-deploy-triage` for the release tree. This skill is the Ansible layer those steps call into.

**Paths:** `../literatum-platform/references/deep/` is relative to this skill's folder; in Cursor resolve it against where the skills are installed. Repo paths are relative to `$LIT_REPOS` (setup: `../literatum-platform/SETUP.md`). Read repo files only through `../literatum-deploy-triage/scripts/safe_view.py`: ansible `defaults/`, `group_vars/` and inventory modules hold plaintext credentials.

## How every Ansible step runs

`ansible-actions -s <svc> -p <product> -f <family> -a <action>` (or `-n <cluster>`) → `ansible-inventory/ansible-actions.py` (Python 2) on the tools host:

1. **Inventory:** `python ~/apps64/ansible/inventory/inventory.py <svc>` builds groups from the host's `~/deployconf.xml` (= deployconf `deployconf.<account>.xml`). Stdout must be pure JSON; anything else → `Error [53]`.
2. **Branch (`deploy_version`):** if the group has a `deploy_version` var that isn't `auto|fallback|latest`, it's used verbatim. Otherwise the Literatum branch (`lit_version`, from deployconf `<source>`, `lit-` stripped) is matched by prefix against **`atypon_lifecycle.json` on the service repo's master branch** (last match wins). No match → `MSG [NO deploy_version is found for identifier '<branch>', will use the fallback deploy version: 'X']`, **normal, not an error** (consumer 10.0, atm 9.0, ingestion main).
3. **Sync:** `git@github.com:atypon/ansible-<svc>.git` at that branch into `~/apps64/ansible/<svc>/<deploy_version>`, a **shared checkout on the NFS home** used by every product and tools host of the account. Printed as `SYNC [<dir> with repo <url>]`.
4. **Run:** `/opt/ansible_env/8.7.0/bin/ansible-playbook -v <repo>/<action>.yml -e component_name=<name> -e deploy_version=<dv>` (system Ansible for services not in `VENV_PATHS`). Actions = top-level `*.yml` of the repo.
5. **Verdict:** the wrapper prints `COMPLETED SUCCESS` / `COMPLETED FAILURE` from ansible's exit code; the Deploy Server matches that text.

## Wrapper error codes

| Printed | Meaning | Usual cause |
|---|---|---|
| `Error [51] while cloning repository.` | first clone of that branch failed | branch missing on GitHub, SSH key / known_hosts, empty deploy_version |
| `Error [52] while pulling repository` + `Permission denied (publickey)` | pull failed on credentials | tools host's key can't read the repo (often transient) |
| `Error [52]` + git `divergent branches` / `no such ref was fetched` | pull failed on the **shared checkout** | concurrent pulls by parallel deploys (asmj consumer: 5 deploys in 41 s), or a dirty/diverged checkout, or deploy_version is a tag. Re-run; if persistent, the checkout needs resetting (host) |
| `WARN [Skipping updating the repo.]` | pull hit `Cannot rebase onto multiple branches` | **runs STALE playbooks** and may still end SUCCESS |
| `Error [53] while running dynamic inventory.` | inventory stdout not JSON | deployconf missing/unparseable, a product dropped from deployconf, a stray print |
| `Error [54] … atypon_lifecycle.json` | couldn't fetch the lifecycle matrix | GitHub token/401/404 |
| `Error [55] wildcard match is not supported.` | `*` in a matrix key | lifecycle file bug |
| Python `KeyError: '<p>-<f>'` / argparse `invalid choice` | product/family not in the inventory | deployconf doesn't have that product (or not for that account) |

## Green steps that lie (per service)

| Service / step | Trap (verified unless marked) |
|---|---|
| any | `skipping: no hosts matched` (empty group) still ends `COMPLETED SUCCESS` with nothing deployed. Pushgateway always reports OK. |
| **solr** (19.1) | `deploy.yml` commits with `reload_collections: false`; a node picks up a new configset only if its container is recreated (new image or forced). Configsets come from solr-plugins + literatum.props baked into a shared image. |
| **consumer** (10.0) | validates `/metrics/ping` (metrics servlet), not `/ping`: passes with Solr/Redis unreachable. |
| **gaia** (2.0) | new `image_tag` ignored unless `force_recreate=true`; bundle checked in GAR but downloaded from Nexus; the check regex cuts 4-part versions (`2.2.85.1`→`2.2.85`); bundles install asynchronously after the playbook returns; `/actuator/health` UP with zero bundles. Overlapping GaiaDeploys on one cluster: `(/tmp/start.sh) is absent` (LIT-656679). |
| **pugrenderer** (4.0/4.1) | delivers the styleguide (not HostDeployStyleguide). `released-assets-invalidatecache.yml:3` URL ends `&p=<product>'` (stray quote) → the per-product invalidate very likely clears nothing, yet returns 200. |
| **cassandra** | `CassandraDeploy` is account-level (no product): search it without a product filter. `gaia_cleanup` keeps the 2 newest table ids per template. |
| **zookeeper** | two versions in use (stag `stag-zk-1/2` on 3.5.8, others 3.7.1; prod 12 clusters on 3.5.8). restart bounces nodes with no health check. |
| **kafka** (10.0) | restart has no health check and no `-t` (10 s kill); deploy check is a substring match on broker id in ZK (can't collide today: ids 1–8). |
| **elk** | ElkFilebeatDeploy / ElkKibanaBackup bypass the wrapper and `git pull` a fixed `…/ansible/elk/latest` checkout; checks are TCP-port only; Kibana backup stops at 1000 objects. |
| **atm / searchservice** | a failed image build leaves a lock → next deploy waits 300 s and fails (reader). |
| **proxysolr** | no health check at all; each cluster pins its own branch (1.0/2.1/3.1/4.1). |
| **xse** | no product has `<xse>` on beta/stag/prod → every Xse* action is cancelled `Xse is not configured`. |

## Triage checklist for an Ansible step

1. From the log: `SYNC [...]` (service + branch), the `MSG [...deploy_version...]` line, then the first `fatal:` / `Error [5x]` / `failed=` line, **then** the `COMPLETED …` line.
2. `UNREACHABLE` / `REMOTE HOST IDENTIFICATION HAS CHANGED` → host or ssh, not playbook code. If the same play reached that node seconds earlier/later, it's transient (shared `known_hosts` on NFS).
3. Read the playbook **at the branch that ran** (`git fetch --depth 1 origin <branch>` in the clone, then `git show FETCH_HEAD:<path> | safe_view.py -`), not master.
4. Look sideways: other deploys of the same service in the same minute share the checkout and often the cluster (`ds_list.sh <acct> "" <Action> "" 300 '<time>'`).
5. For a green step, check the service-specific trap above before believing it.

## Deep notes (file:line@commit)

`../literatum-platform/references/deep/`: `03-ansible.md` (wrapper, inventory modules, solr/cassandra/redis/consumer/gaia), `07-ansible-pugrenderer.md`, `10-ansible-infra.md` (zookeeper, kafka, elk, mssql, xse + branch per env), `11-ansible-services.md` (atm, ingestion, searchservice, proxysolr, tools, inventory mismatches), `22-gaiafe-axel-devprod.md` (gaia-fe side), `29-solr-plugins-id-index.md` (what Solr/consumer actually load), `30-rd-jobs.md` (Rundeck-run jobs), `35-lb-puppet-invapi.md` (traffic path).

## Founding failures

- An ansible-driven consumer deploy failed with `Error [52]` and a git "divergent branches" hint. It looked like a credential or code problem. It was five deploys pulling the same NFS-shared checkout within 41 seconds; one lost. A re-run passed.
- A Gaia deploy failed with `/tmp/start.sh is absent`: another product's GaiaDeploy on the same cluster had started six seconds earlier, and its cleanup deleted the file mid-run. Neither log alone explains it.
- SolrDeploy, GaiaDeploy and ProductConsumerDeploy can all report `COMPLETED SUCCESS` while the new config, bundle or connectivity never took effect. Each has a different reason (table above). "Green" at this layer means "ansible exited 0", nothing more.
