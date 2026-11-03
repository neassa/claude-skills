# 03 — Ansible deploy layer (ansible-inventory + service repos)

Scope: `$LIT_REPOS/{ansible-inventory, ansible-solr, ansible-cassandra, ansible-redis, ansible-consumer, ansible-gaia}`.
Read-only analysis. Secrets are never reproduced; they are written as `<secret at file:line>`.
All paths below are relative to `$LIT_REPOS/`.

---

## 1. Coverage

Enumerated with `git ls-files` (and `git ls-tree -r origin/2.0` for Gaia 2.0).

| Repo (branch) | Files | Lines (total) | Read fully | Scanned / skimmed (why) |
|---|---|---|---|---|
| ansible-inventory (master) | 35 | 3,845 | 35 files / 3,845 lines (every .py incl. `ansible-actions.py`, `inventory.py`, `api.py`, all 22 inventory modules, `lit_service_manager.py`, `lit-service/*.yml`, `Jenkinsfile`, `pom.xml`, `requirements.yaml`, chainguard yaml) | none |
| ansible-solr (master) | 157 | 38,981 | 142 files / ~6,485 lines: every playbook, role (tasks/defaults/handlers/meta/templates), `group_vars/all`, `hosts/dev`, `ansible.cfg`, `atypon_lifecycle.json`, `inventory.sh`, `Jenkinsfile`, both callback plugins, `library/grab_cfg_hierarchy*.py`, `library/find_g1_heap_region_size.py`, `files/*.sh`, `roles/set-image/files/{cdcr-solrconfig-setup.sh,solr-heap-dump.sh,metaproxy/*}` | 13 Solr-exporter XML configs + 2 Grafana dashboard JSONs (31,564 lines, upstream Apache exporter config; scanned for structure/secrets only); `library/unused/*.py` (608 lines, **not on the module path**); `files/solrdump.py` (324 lines, legacy standalone script, skimmed) |
| ansible-cassandra (master) | 69 | 4,268 | 66 files / ~1,795 lines (every playbook/role/vars/files/*.sh/README/ansible.cfg/lifecycle) + core logic of `getSnapshot` (l.196-306) and `putSnapshot` (l.180-348) | `roles/create-image/files/cassandra.yaml` (1,819 lines, key settings grepped: `auto_snapshot: true`, `AllowAllAuthenticator`, `num_tokens: 16`, `listen_address: 172.17.0.2`); rest of vendored snapshot tools (arg parsing/usage) |
| ansible-redis (master) | 46 | 3,123 | 45 files / 815 lines | `templates/redis.conf.j2` (2,308 lines; all 19 templated lines + key directives grepped) |
| ansible-consumer (master) | 53 | 2,349 | 53 files / 2,349 lines (callback plugins + `grab_cfg_hierarchy.py` diffed against the solr copies: identical except whitespace, grafana user allow-list lacks `gcp-rehearsal`, debugger args) | none |
| ansible-gaia (master) | 34 | 20,363 | 32 files / 802 lines | `library/docker_container.py` (2,034 lines, vendored Ansible 2.1-era module, only referenced by unused role `docker-remove`); `roles/deploy-cluster/files/java-buildpack-memory-calculator` (ELF binary; `strings` shows cloudfoundry java-buildpack-memory-calculator) |
| ansible-gaia (origin/2.0) | 34 | 20,363 | identical | `git rev-parse master^{tree} origin/2.0^{tree}` both = `eb5b379…`; master HEAD `f601ffb` is "Merge PR #32 from atypon/2.0". **Beta's 2.0 branch and master are byte-identical today.** |

---

## 2. ansible-inventory: exact flow of `ansible-actions -s <svc> -p/-n/-f -a <action> -e …`

File: `ansible-inventory/ansible-actions.py` (Python 2: `print` statements). Constants: `ANSIBLE_ROOT=$HOME/apps64/ansible` (l.19), `REPO_BASE_NAME=git@github.com:atypon/ansible-` (l.20), GitHub token `<secret at ansible-inventory/ansible-actions.py:21>`.

### 2.1 Step-by-step

1. **Arg parse #1** (l.233-244). `-s` must be one of 21 services (solr, redis, zookeeper, kafka, pkgconsumer, consumer, searchservice, pugrenderer, cassandra, elk, mssql, rest_atm, atm, mongodb, xse, tools, grobid, panopticon, proxysolr, gaia, ingestion). `-n/-p/--name/--product` are aliases of the same arg. `-e` and `-l` append.
2. **Inventory** (l.247-250 -> `dynamic_inventory` l.44-54): runs `python ~/apps64/ansible/inventory/inventory.py <svc>` (`tools` maps to `product`), parses **stdout only** as JSON. Any non-JSON stdout -> `Error [53]`, exit 53. Note: the wrapper never updates the inventory checkout; it only tells you to `git -C ~/apps64/ansible/inventory/ pull origin master` (l.51).
3. **Name choices** (l.253-256): every top-level key except `_meta` (= Ansible group names) plus `all`.
4. **Arg parse #2** (l.259-283): with `-f`, `-p` must be a single product name (not `all`) (l.264-269); family choices are the `family` vars of groups whose `product_name == -p` (l.271-277); name becomes `<product>-<family>` (l.280). Without `-f`, `-n` must be an exact group name (l.282-283). Invalid choice -> argparse exits **2** (same code as a playbook failure, see 2.4).
5. `-n all` expands to every group (l.285-286).
6. **Per name loop** (l.290):
   - `-e deploy_version=X` overrides the inventory value (l.294-299).
   - **Version selection** (l.302-308): if group var `deploy_version` exists and is not `auto|fallback|latest` it is used verbatim; else `identifier = lit_version` (or `"fallback"` if absent) and `get_deploy_version()` is called.
   - `get_deploy_version` (l.80-118): strips `lit-`, GETs `https://raw.githubusercontent.com/atypon/ansible-<svc>/master/atypon_lifecycle.json` with the token header (always **master's** matrix, l.89), then for each `{version: [values]}` sets `deploy_version=version` whenever `identifier.startswith(value)`; **no break**, so the last match in file order wins (l.99-104). `fallback` value used when nothing matched (l.109-111). A `*` in the result -> `Error [55]`, exit 55 (l.114-116).
   - Repo path `~/apps64/ansible/<svc>/<deploy_version>` (l.311).
   - **Git sync** `git_clone_pull` (l.56-77): `Repo.clone_from(url, dir, branch=deploy_version, depth=1)`; if stderr contains `already exists` -> `git pull` in that dir; pull stderr containing `Cannot rebase onto multiple branches.` -> prints `WARN [Skipping updating the repo.]` and **continues on stale code**; any other pull error -> `Error [52]` exit 52; any other clone error -> `Error [51]` exit 51.
   - **Action choices** = basenames of `*.yml` at repo root (l.318-320) — so any top-level playbook (e.g. `gaia_cleanup`, `cdcr-postdeploy-tasks`, `validate-dependencies`) is an action.
   - **Limit choices** = `ansible_host` of the group's hosts (l.323-327); `-l qa21` becomes `-l '*_qa21_*,'` (l.378-383).
   - **Arg parse #3** (l.330-339) makes `-a` required with those choices.
   - `install_collection_requirements()` is commented out (l.341-348) — `requirements.yaml` is dead (it contains `<secret at ansible-inventory/requirements.yaml:2>`).
7. **Per action** (l.351-417):
   - venv: `VENV_PATHS[svc]` -> `/opt/ansible_env/8.7.0/bin/ansible-playbook` for ingestion, gaia, atm, zookeeper, redis, kafka, cassandra, proxysolr, searchservice, consumer, elk, tools, solr, mssql, pugrenderer (l.24-42, 352-359); others use system `ansible-playbook`. Version-specific venv keys are supported but none are defined.
   - Command: `ansible-playbook -v <repo>/<action>.yml -e component_name=<name> -e deploy_version=<dv>` (+ `-c local` **only when `LOCAL_BASE` is NOT set**, l.363-367, i.e. developer boxes; DC accounts, which have `LOCAL_BASE`, SSH to `ansible_host`), then every other `-e` (l.370-375), `-l`, `-q` (removes `-v`, l.386-387), `--list-tags/-t/--skip-tags`.
   - Env: `ANSIBLE_CONFIG=<repo>/ansible.cfg` (l.402) -> each repo's `inventory = ./inventory.sh` -> `python ~/apps64/ansible/inventory/inventory.py <svc>` (full inventory, all groups).
   - Execution: `Popen(stderr=PIPE)`; stdout is **not captured** (goes straight to the terminal/Rundeck log), stderr is re-printed line by line (l.120-127). Prints `PPID [...]`, `RUN [...]`, `CMD [...]`, `TIME [...]`.
   - rc != 0 -> `MSG [ansible-playbook finished with a non-zero exit code for <name>]`, `MSG [stopping the deployment pipeline for <name>]`, remaining actions **for that name** skipped; other names still run (l.410-417).
8. Exit (l.420-426): any failed name -> prints list, `sys.exit(2)`; else 0.

### 2.2 Inventory generation (`inventory.py` + modules)

- Deployconf file (l.133-145): `-a <acct>` -> `~/.litconfig/deployconf.<acct>.xml`; else env `INVENTORY_ACCOUNT`; else `~/deployconf.xml`. Missing file -> `raise Exception` (traceback, stdout empty -> wrapper `[53]`).
- Newlines are stripped and `os.path.expandvars` applied **to the whole XML before parsing** (l.150-153): an unset `$VAR` stays literal; a `$` in a password gets expanded.
- `_meta.env` = second dot-field of the **realpath** of the file (l.160) (`deployconf.beta.xml` -> `beta`; a non-symlinked `~/deployconf.xml` -> `xml`). Used by `product.py` for proxy whitelists.
- Class is located dynamically as `<svc>.<svc>Inventory` (l.165).
- Empty-inventory guard (l.176) compares to `{"_meta":{"hostvars":{}}}` — dead for CoreService modules because `_meta.env` is always present.
- `<ansible-common><arg k="v"/></ansible-common>`: every attribute becomes a group var for **every** service (`core_service.py:5-11`, `core_product.py:46-52`). This is the only way to inject `deploy_version` for non-Gaia services.

**CoreProduct (solr, consumer, atm, xse, …)** — `core_product.py:73-228`, only top-level `<product enabled="true">` (l.86-87):
| deployconf | var |
|---|---|
| `product@name` (lower-cased) / `@deployfamily` | `product_name`, `family`, group/`product_identifier` = `name-family` (l.89-114) |
| `product@singleindex` | appended to `singleIndexProducts` (l.94-98) |
| `server/web`, `server/ssl`, `server/proxy` text | `literatum_{web,ssl,proxy}_port` (l.117-121) |
| `product@multi_family` | `multi_family` (default `'false'`) (l.124-127) |
| `source` text, path element `[-2]` | `lit_version` (l.129-131) — drives lifecycle matching |
| `exports/export[@name=DEPLOY_HOST]` | `deploy_host` (l.134-137) |
| `databases/database-server` attrs + `database[@type=LITERATUMDB]` + top `database-servers/database-server[@enabled=true]` | `dbserver, dbport, dbname, dbuser, dbpass` + any extra attrs (l.8-44, 140-142) — **DB password becomes an Ansible var** (`<secret-bearing line at ansible-inventory/core_product.py:36>`) |
| `server@type`, `hostname`, `product-tier` (default "0"), `styleguide/version`, `akka@join_type/@zk_cluster_name`, `@pre-prod`, `@git`, `@passport`, `extra_domains`, `atm/model@*`, `rest-atm/model@*`, `publisher-home-path` | `server_type, hostname, product_tier, styleguide_version/is_styleguide, akka_*, pre_prod, git, passport, extra_domains, atm_models, rest_atm_models, publisher_home_path` (l.144-228) |

**solr** (`solr.py`): `solr_port = deployfamilyinfo/entry[@deployfamily]@srunport + 7` (l.17-24); product `<solr …>` attrs copied (`collections` split on `,`, `sharded` JSON with `'`->`"`) (l.89-95); `<solr-server host [solr_port] …>` -> host `"<product-family>_<host>_<idx>"` with `ansible_host=host` and every attr as hostvar (l.100-109); per-host `solr_port` > `solr@solr_port` > srunport+7 (l.51-59); `solr_cluster="h:p,…"`, `solr_prometheus_exporter = first host:port+2` (l.86-87); `zk_cluster = <zk hosts>/ + name_prefix + product[-family]` from `zookeeper/cluster[@name=solr@zk_cluster_name]` (l.26-37, 98). Products without `<solr>` are dropped (l.79-81). **Any exception silently drops the product** (l.117-118).

**consumer** (`consumer.py`): `consumer_port = srunport + 3` (l.21-28); `<consumer kakfa_cluster_name=… [redis_cluster_name] [cassandra_cluster_name] [consumer_port]…>` (attribute is literally spelled **`kakfa`**, l.120-122); `kafka_zk_connection = <zk string of kafka's zk cluster> + <kafka cluster name>`, `kafka_cluster`, `solr_cluster`/`solr_zk_connection` from the same product's `<solr>` (l.123 — **a consumer without a `<solr>` block is silently dropped**), `redis_connection`, `cassandra_connection` (never used by templates), `solr_replicas`, `atm_models[].zk_conn_str`; hosts `<consumer-server host …>` (l.138-147). Exceptions swallowed (l.155-156).

**cassandra** (`cassandra.py`): two passes. `runClusters` (l.41-58): each `cassandra/cluster@name` (lower-cased group; the `-n` match lower-cases only the XML side, l.51) with `label=cluster`, all cluster attrs (`native_transport_port`, `storage_port`, `name` keeps original case), `cassandra_cluster="h:ntp,…"`; hosts `<cluster>_<host>_<idx>` from `cassandra-server` attrs. `runProducts` (l.62-88, skipped if env `CLUSTERS_ONLY=true`): each enabled top-level product with `<cassandra cassandra_cluster_name=…>` (and not `cassandra_product_catalog="false"`) gets group `<product-family>` with `label=product`, `product_name`, `family`, `lit_branch` (= source `[-2]`) and **the same cluster's hosts/vars** (l.92-125). No `lit_version` -> lifecycle `fallback` (4.0).

**redis** (`redis.py`): `redis/cluster@name` group, attrs (`redis_port`, `replicas`, …), `redis_cluster="h:p,…"`; hosts `<cluster>_<host>_<idx>` with `node_ip = DNS(host)` falling back to `machines/machine[@name]@ipaddress` (l.12-22, 66-75).

**gaia** (`gaia.py`): `gaia/cluster@name` group (l.82-90) with fixed `docker_registry_base_{push,pull}_url`, and cluster attrs `bundle_version, image_tag, memory, cpu, port, node_port, deploy_version` via `getAttribute` (missing -> `""`) (l.93-103). `vars.products[<product@name>]` for **every** `<product>` in the document (no `enabled` or top-level filter; keyed by name only, so families collide — last wins) that has `<gaia bundle_version=… service_cluster=<this cluster> [previous_bundle_version]>`, plus `deployfamily`, `source`, `previous_source_branch` text (l.37-73, 109-124). Hosts `<cluster>_<host>_<idx>` from `gaia-server` attrs + `node_ip` from `machines` (l.127-136). This is the only module that emits `deploy_version`.

**zookeeper/kafka** (used as lookups): `zk_cluster = "h:client_port,…/"` (trailing `/`) (`zookeeper.py:12-32`), hosts keyed by `myid` (l.60); kafka `kafka_cluster="h:kafka_port,…"`, `zk_cluster` = zk string + kafka cluster name (`kafka.py:12-38,61`).

### 2.3 Version selection per service (lifecycle matrices, master)
| Service | Matrix | Identifier used |
|---|---|---|
| solr | `20.0:[master,fallback]`, `19.1:[2610]`, `18.3:[2410,2310]`, `16.6:[2210]`, `13.0:[2020]`, `12.1:[2010]`, `11.4:[1910,1830]`, `10.1:[1820]`, `8.3:[1810,1730,1720]`, `6.3:[1710,1630]` | product `lit_version` |
| consumer | `10.0:[2510,master,fallback]`, `9.1:[2410,2310,2210]`, `7.5:[2020,2010]`, `6.0:[1910,1830]`, `4.0:[1820,…]` | product `lit_version` |
| cassandra | `4.0:[fallback]` | none (cluster) -> 4.0 |
| redis | `4.1:[fallback]` | none -> 4.1 |
| gaia | `2.0:[fallback]` | cluster `@deploy_version` if set (and not auto/fallback/latest), else fallback -> **2.0** |

Note consumer has no `2610` entry: a lit-2610 product falls to `fallback` = `10.0` (same as 2510/master).

### 2.4 Error / exit codes
| Code | Message | Where | Cause |
|---|---|---|---|
| 51 | `Error [51] while cloning repository.` + git stderr | `ansible-actions.py:75-77` | branch `deploy_version` missing on GitHub, SSH key/known_hosts failure, empty `deploy_version` |
| 52 | `Error [52] while pulling repository` | l.71-73 | local changes/divergence in `~/apps64/ansible/<svc>/<dv>`, force-pushed branch, **deploy_version is a tag (detached HEAD: pull fails on the second run)** |
| 53 | `Error [53] while running dynamic inventory.` | l.50-53 | deployconf missing (traceback), XML parse error, stray `print` in module (`product.py:115`), empty-JSON guard exception |
| 54 | `Error [54] while trying to download atypon_lifecycle.json for <svc>` + `http code …` | l.92-97 | GitHub 404/401 (revoked token -> 404 body not JSON), bad JSON |
| 55 | `Error [55] wildcard match is not supported.` | l.114-116 | `*` in matrix key |
| 2 | `MSG [ansible-playbook finished with a non-zero exit code for the following products: …]` | l.420-423 | any playbook rc != 0 — **also argparse `invalid choice` exits 2** |
| 1 | `-p` multiple with `-f`, or `-p all -f` | l.265-269 | usage |
| 1 (traceback) | `NameError: r` / `TypeError: argument of type 'NoneType'` / `ValueError list.remove` | l.95, l.114, l.387 | see 2.5 |

### 2.5 Silent-failure / misleading paths in the wrapper + inventory
1. `get_deploy_version`: on a `RequestException` (DNS/timeout) the handler references `r` which is unbound -> `NameError` traceback, exit 1, **no [54]** (l.91-96).
2. No match and no `fallback` -> `deploy_version=None` -> `TypeError` at l.114.
3. Prefix matching without `break` (l.99-104): identifiers are matched with `startswith` and later rows override earlier ones; a new branch with no row silently gets `fallback` (e.g. consumer lit-2610 -> 10.0).
4. `Cannot rebase onto multiple branches` -> WARN and run **stale playbooks** (l.67-69).
5. `git pull` pulls whatever is checked out; nothing verifies the working tree matches `deploy_version`.
6. Gaia: if the cluster has no `deploy_version` attribute, inventory emits `""`, which is not in `[auto,fallback,latest]` -> `abs_path=~/apps64/ansible/gaia/` and clone with empty branch -> `[51]` (or `[52]` if that dir exists and is not a repo).
7. Inventory modules swallow every exception per product (`solr.py:117`, `consumer.py:155`, `atm.py:147`, …): the product silently disappears and the wrapper fails with argparse `invalid choice` (exit 2) — indistinguishable by exit code from a playbook failure.
8. Consumer inventory requires `<solr>` on the same product and the misspelled `kakfa_cluster_name`; either missing -> product dropped (item 7).
9. `-q` together with `-vv` -> `cmd.remove('-v')` raises `ValueError` (l.387).
10. Playbooks with `vars_prompt: force` (solr/redis/cassandra/consumer/gaia `remove.yml`, cassandra `remove-node.yml`): without `-e force=yes` Ansible prompts on stdin; non-interactive runs get an empty answer -> every destructive task skipped -> **rc 0, nothing removed**.
11. The collection-install step is disabled; any role needing a collection not already in `~/.ansible` fails only at run time.
12. `expandvars` on raw XML (inventory.py:153) can silently alter values containing `$`.

---

## 3. Service repos

Common: `dev_mode = LOCAL_BASE undefined`; `docker_url = unix:///var/run/docker-<USER>.sock` in DC (per-account docker daemon), `docker.sock` in dev. All containers are plain Docker on the deployconf hosts (no k8s, no Rundeck code in these repos). ansible.cfg in every repo: `inventory=./inventory.sh`, `profile_tasks` callback, SSH ControlPersist 600s, pipelining.

### 3.1 ansible-solr

Callbacks: `profile_tasks,grafana_annotations,pushgateway` (`ansible.cfg:5`); Grafana `http://grafana.devops.atypon.com/api/annotations`, dashboard 175, key `<secret at ansible-solr/ansible.cfg:26>`. Container names: `<USER>-<product_id>-solr-<solr_port>`, exporter `<USER>-<product_id>-solr-exporter-<solr_port+2>`, bootstrap `<USER>-<product_id>-solr-bootstrap`. `product_id = product_name` (or `product-family` if `multi_family`) (`group_vars/all:51`). Paths: `{LOCAL_BASE}/ssd$HOME/servers/<family>/<host>/docker_solr_<port>/{index_def,index,logs,registry}` (l.22-28). Image `…/docker-registry/id/solr:<solr-plugins-ver>-d<deploy_version>` (client image: `<product_id>-…`) (l.55). Secrets in vars: `<secret at ansible-solr/group_vars/all:37>`, `<secret at ansible-solr/group_vars/all:84>`.

Required inventory vars: `product_name, family, product_identifier, lit_version, git, solr_port, zk_cluster, solr_cluster, multi_family, deploy_host?, collections?, sharded?, product_tier?, publisher_home_path?, cdcr_*?, heap_size?`.

**deploy.yml**
1. Play "Bootstrap" (serial 1, first host only) -> role `bootstrap` whose meta deps run first: `zookeeper-check` (`echo srvr | nc -w 3` each ZK, 3 retries; fail `Zookeeper cluster is not available`; asserts ZK>=3.5.5 not with lit-1*, ZK<3.5.0 only with lit-1*), `search-version` (versions.properties `searchVersion=` from GitHub raw literatum@lit_version or SVN; pom parsing for lit-2010/1910/1830; then `solr-plugins.version` from id-search pom via GitHub API; verify `solr_profile` exists), `set-image` (pull image; if missing: lock `~/apps64/ansible/solr/tmp/solr-<tag>.lock`, wait up to 480s if another build holds it, build: Maven 3.9.10, solr-pom deps, web.xml, literatum.props.xml, zkClientTimeout, profiles, `SolrStandaloneConfigurator`, metaproxy via Maven, base image **hard-coded `solr:9.10.1`** (`get-base-solr-image.yml:28-29`, root-pom value is fetched then ignored), Dockerfile with Temurin 21, push). Then CDCR pretasks (if `cdcr_type=source`) and a throw-away container that runs `pre-solr-init.sh` + `zkcli.sh -cmd bootstrap` to upload configs to ZK; retries 10, delay 5-20s; fail `ERROR: Bootstrap action failed` (`roles/bootstrap/tasks/bootstrap.yml:52-54`).
2. Play "Pause consumers and commit" (run_once) -> `solr-commit-reload` with `commit_collections=true`, `pause_consumers=true` (DC): CLUSTERSTATUS, then `consumers-pause.yml` (below), then `update?commit=true&openSearcher=false` per collection (timeout 620s, 1 retry). `ignore_role_errors: True` by default -> **all of this may fail silently**.
3. Play "Deploy" (serial 1, force_handlers) -> `node-deploy` (meta: search-version, set-image again per host): notify `unpause_consumers` handler; create dirs (incl. backup mounts); G1 region size; inspect image env `SYNONYMS_SUFFIX`; **fail if term/thesaurus synonyms dirs missing** (unless `require_*=False`); decide `recreate_container` (container not running, or node not in `live_nodes` after 2x5s, or `-e recreate=yes`); `docker_container` start (volumes: backups x3, index, index_def, logs, registry, /etc/timezone, optional synonyms/newrelic; ports solr_port, solr_port+1, optional metaproxy/jmx/debug; restart_policy always); exporter container on first host only; on failure retry once with recreate and 10 retries (`deploy.yml:125-140`); then `node-validate.yml`: CLUSTERSTATUS until node in `live_nodes` and all its replicas `active`, **1440 x 5s = 2h** (`node-validate.yml:3-19`). Handler unpauses consumers after the last host (or on a failed host thanks to force_handlers).
4. Play "Ensure collections" (first host) -> `collections_ensure`: replica count = min(#nodes,3) (or sharded profile math); assert `Wrong number of nodes (…) and shard configuration.`; `grab_cfg_hierarchy` (git sparse clone of `literatum` via HTTPS+token into `/tmp/sparse_<lit>_<product>`, or SVN); `EnabledCollectionsExtractor` inside the Solr container (fallback: ZK configsets); ADDREPLICA for missing replicas; CREATE missing collections `<col>_<YYYYMMDDHHMM>` with alias `<col>`, `perReplicaStates=true`, placement plugin `AffinityPlacementFactory`; verify all cores in `[active, recovering]` **120 x 5s**; ping every collection (5 x 5s, timeout 90).

**restart.yml**: pause+commit (run_once) -> serial `docker restart -t 60` + `node-validate` (2h) -> separate play unpauses consumers. **If a node fails, the unpause play never runs; consumers stay paused.**

**stop/start/status** (`roles/node-action`): `docker inspect .State.Running`; stop `-t 60` serial; start only if `false`. No consumer pausing, no validation.

**remove.yml**: `vars_prompt force`; removes solr + exporter containers, `solr_root_dir` (path guard), ZK chroot (`znode` recursive delete, only if no `-l` and `product_id in zk_cluster`); then `remove-gone-replicas` when run with `-l` (DELETEREPLICA of `down` replicas, `onlyIfDown=True`).

**backup.yml** (used nightly by `files/solrdump.sh` via `ansible-actions.py -s solr -a backup -n <p> -e rotate=true -e check_index=false`):
1. pause consumers + commit; on `literatum` also **creates a 5h Alertmanager silence** (`http://alertmanager.devops.atypon.com/api/v2/silences`, matchers instance=prod, job=checkconsumer, product, alertname) (`consumers-pause.yml:34-92`).
2. `backup-restore` role: backup name `<product>_<USER>_<YYYYMM>{01|16}-000000` (reused for 16 days -> **incremental**, `group_vars/all:93-95`); dir `/shared/docker/backups/solr/<product>[_nonprod]`; wait 300s for `restore.lock`/`backup.lock` absent (**outside the block**, `roles/backup-restore/tasks/main.yml:7-15`); create lock only if dir already exists (l.17-22); pretasks (solr version, collection list, dir renames); per collection commit, reload, DELETESTATUS, `BACKUP … async=<name>-<col> incremental=true maxNumBackupPoints=16`; verify REQUESTSTATUS until `completed` (12000/10 = **1200 x 10s**); remove lock; unpause consumers + delete silence. `rescue:` removes lock, unpauses, fails `Solr backup for <user>@<p>-<f> has failed.`
3. externals (serial): rsync `external_*.txt` per collection into `<backup>/externals/<col>`; e-mail `solr-monitoring@atypon.com` if > 500 files.
4. `backup-integrity` (optional CheckIndex; writes `backup_valid` + `backup_metadata.ini`), optional `backup-to-cloud` (S3 / GCS / GCP-NFS via delegate `tools-1..10`, `gcptools`), optional `backup-retention` (keep >=1, delete >12h).

**restore.yml**: `find_backup.yml` (`backup_name=latest-<acct>` or exact); assert `backup_valid` and that `lit_version_major` in the metadata equals ours; per collection DELETESTATUS + `RESTORE` async + REQUESTSTATUS (48000/10 = **4800 x 10s**); product-catalog collections (`price, offer, discount, campaigns, pc-*`) skipped by default; externals re-uploaded via `/solr/<core>/admin/uploadfile`.

Other actions: `commit`, `reload`, `commit-and-reload`, `cleanup` (deletes all `backup.lock`/`restore.lock` under the backup dir), `create-image`, `heapdump` (`/opt/solr-heap-dump.sh` via jattach, async, 300s), `validate-dependencies`, `download-backup-from-gc`, `upload-backup-to-{gc,s3}`, `deploy-and-restore`, `remove-deploy-and-restore`, `remove-gone-replicas`, `bootstrap`, `cdcr-postdeploy-tasks`.

**Side effects on other services (solr -> consumer)**: `consumers-pause.yml:3` runs `~/apps64/ansible/inventory/inventory.py consumer -j -n <p>-<f> | jq …consumer_cluster`, `add_host consumer_<host>_<port>`, then **SSH to each consumer host** and `docker -H <docker_url> pause|unpause <USER>-<product>-<family>-consumer-<port> || true` (l.21-32). The `|| true` and `ignore_role_errors` make pause failures invisible; if the consumer inventory drops the product (2.5 item 7) jq prints `null` and pausing is silently skipped.

**Logging**: Ansible stdout -> wrapper stdout (Rundeck/terminal). `solrdump.sh` writes `~/apps64/ansible/solr/tmp/<user>-<product>.log` and mails `solr-monitoring@atypon.com` on failure (`files/solrdump.sh:32-43`). Container logs json-file 10m x 20; Solr log4j2 `solr.log` 40MB x 25 in `solr_logs_dir`.

**Pushgateway** (`callback_plugins/pushgateway.py`): enabled only for users literatum/staging/midtierbeta/lts/migration/atypon/readonly (l.125); URL `pushgateway-prod.devops.atypon.com` (literatum) or `pushgatewaynonprod.k1ingresslb.int.atypon.com:30080` (l.141-147); job `ansible_actions_<user>_solr_<action>_<product>_<family>`, metric `ansible_actions{product,family,product_id,service,environment,action}` value `1`=ok `2`=failed (l.184-195). **The plugin never implements `v2_runner_on_failed`, so `errors` stays 0 and it always pushes 1 (success)** — Pushgateway cannot show Ansible failures.
**Grafana** (`callback_plugins/grafana_annotations.py`): start annotation, one annotation per non-ignored failed task, and a region annotation with status OK/FAILED at the end; tags include playbook, hostname, product, user, service. Failures to post are only `display.error`.

### 3.2 ansible-cassandra

No callbacks except `profile_tasks`; `stdout_callback=debug`. Required vars: `label, name, native_transport_port, storage_port, cassandra_cluster` (+ `product_name, family, lit_branch` for backup/restore).

**Container / ports convention**: container `<groupname>-<native_transport_port>` where `groupname = group_names[0]` (lower-cased cluster name) (`roles/deploy/tasks/deploy-cluster.yml:7`); backup/restore/repair/cleanup use `<name>-<native_transport_port>` where `name` is the raw XML attribute (case preserved). Hostname `<host>-<cluster>`. Published ports: `storage_port`, `native_transport_port`, and **host port 9500** for the Prometheus agent (fixed, `roles/deploy/defaults/main.yml:42-43`). Image `…/docker-registry/cassandra:4.1.3-d<deploy_version>` built from `cassandra:4.1.3` + instaclustr exporter 0.9.12 + repo `cassandra.yaml`. Data: `/local$HOME/servers/common/cassandras/<cluster>/docker_cassandra_<ntp>/data`; backups: `/shared/docker/backups/cassandra/<product>/`. Heap 8g (Xms 2g), memory limit 4x heap, 8 CPUs.

**deploy.yml**: assert `label == 'cluster'` (`Not allowed to run this action for a product. …`); assert seeds on distinct hosts; serial: create-paths (entrypoint override, `getSnapshot-<dv>`/`putSnapshot-<dv>` copied into backup dir) -> `docker_container` (seeds = all hosts, env CLUSTER_NAME/BROADCAST/SEEDS/ports/timeouts/JVM_OPTS) -> `validate-node` (`cqlsh … SELECT bootstrapped FROM system.local` until `COMPLETED`, **30 x 5s**); then `validate-cluster` if >1 node (`system.peers` count == N-1, `nodetool describecluster` schema list == N; **5 x 5s** each).
**restart**: serial `docker restart -t 60` + validate-node. **start/stop/status**: inspect + start/stop (+ validate). **remove**: prompt force; container + data dir. **remove-node**: prompt; removes container/data on `node_name`, then `nodetool removenode <hostid>` from another node. **repair** (cron script `files/cassandraNodetoolRepair.sh`): validate node+cluster, then serial `nodetool repair --partitioner-range`, fail unless `Repair completed successfully`.
**backup** (cron script `files/cassandrabackup.sh`, excludes `acm-J`, `ux3-C5`): run_once on a **product group**; assertions (`lit_branch` HEAD or `lit-*`); `ls …/data | grep vos_<product>` (fails if the keyspace dir is absent); `getSnapshot -k <keyspace>` inside the container (flush + `nodetool snapshot` + schema `desc keyspace` + tar) must print `Successfully created snapshot package`; rename to `<USER>_<keyspace>-<ts>.tar.gz`; write `.ini` (account, product, family, macro_build_mode, lit_branch, keyspace, `backup=success`); `rotate` -> keep 1, delete > 1 day, `nodetool clearsnapshot --all <ks>`.
**restore**: find backup (`latest-<acct>` -> newest `<acct>_vos_*-<14 digits>.ini`); check `.ini` lines product/backup/context; **`drop keyspace if exists`**, sleep 10, `putSnapshot -k <ks> -r <#hosts>` (schema replay + `sstableloader` per table), fail on `ERROR|Exception|Connection error` or missing `Import operation complete`.

### 3.3 ansible-redis

No Grafana/Pushgateway. Container `<component_name>_<redis_port>` and `<component_name>_<redis_port>_exporter` (host network, exporter port `redis_port+11000`), image `redis:7.2-alpine`, exporter `oliver006/redis_exporter:v1.45.0-alpine`; dir `…/servers/common/redis-clusters/<cluster>/<host>_<port>/{data,logs,backups}`. Config: `protected-mode no`, no `requirepass`, `save ""` (unless `rdb_enabled`), `appendonly no`, `cluster-enabled yes`, `maxmemory 64G volatile-ttl`, `cluster-require-full-coverage no`. Required vars: `redis_port, replicas, node_ip, ansible_host`.

**deploy.yml**: serial per node: dirs; template `redis.conf`; pull image; if config changed and node is a master with replicas -> `failover-node` (`cluster failover takeover` on its first slave, must return `OK`); `docker_container` (restart if config changed); exporter; `redis-cli info` 12 x 5s; `verify-redis-cluster` (`loading:0` 60 x 10s, slaves `master_sync_in_progress:0` 60 x 10s); exporter `/metrics` contains `redis_up` 10 x 5s. Then run_once `create-cluster`: `docker run … redis-cli --cluster create <all sockets> --cluster-replicas <replicas>`; rc 1 with "Either the node already knows other nodes" = already created; verify `cluster_state:ok` 10 x 10s.
**restart/stop/remove**: failover first if master with replicas; start/stop/restart via docker CLI; verify cluster after restart/start. **add-node**: forget failed node(s), deploy, `--cluster add-node` if node sees only itself. **forget-node**, **deploy-exporter**, **status**.

### 3.4 ansible-consumer

Callbacks as Solr (`service_name=consumer`, dashboard 254, key `<secret at ansible-consumer/ansible.cfg:26>`). Container `<USER>-<product>-<family>-consumer-<consumer_port>` (host port -> 8080). Image `…/docker-registry/id/consumer:<index-ver>-<profile>-d<deploy_version>` (profile `production`). Paths `/local$HOME/servers/<family>/<host>/docker_consumer_<port>/{logs,run,tmp,registry,atypon}`. Secrets `<secret at ansible-consumer/group_vars/all:32>`, `<secret at ansible-consumer/group_vars/all:73>`. Required vars: `product_name, family, consumer_port, consumer_cluster, kafka_zk_connection, solr_zk_connection, redis_connection, kakfa_cluster_name, lit_version, git, id, product_tier?, atm_models?, deploy_host?`.

**deploy.yml**
1. `port-conflict-check` (run_once): runs `inventory.py searchservice -j -n <p>-<f>` and fails if any consumer socket equals the searchservice gRPC/HTTP socket (`Consumer and Searchservice share the same ports …`).
2. serial: `server-type` (-> `consumer-version`: `indexVersion=` from literatum `versions.properties` on GitHub raw/SVN -> `consumer_version=index-<v>`; pom path for old branches) -> GET `id-index/.../application.properties?ref=<tag>`: 200 = `spring-boot`, 404 = `spring-mvc`, else fail.
3. `consumer` role: pull image; if missing: lock `consumer-<tag>.lock` (300s wait), **SSH git clone `git@github.com:atypon/id-index.git`@tag**, `mvn clean install -P<profile>`, docker build/push (lock removed in `always`/`rescue`).
4. deploy: `solrCloud.properties`, `intermediate.dtd`, `update.dtd` (errors ignored), `consumer.props.xml`, `grab_cfg_hierarchy`, `literatum.kafka.props.xml`, `props.files`, md5 of config dirs (env `CONSUMER_CONFIG_MD5` forces recreate on change); pull `id/kafka:0.11.0.0`; fetch `topics-<product>.json` (404 allowed) else `topics-<profile>.json`; run `EnabledTopicsExtractor` in a throw-away consumer container; run `kafka-topics.sh --create --if-not-exists` for enabled topics named `<product>-<family>-<topic>` in a throw-away Kafka container; `failed_when: 'Created topic' not in output and 'Due to limitations in metric names' not in output` (`roles/consumer/tasks/deploy.yml:240`); start consumer container (restart if any config file changed).
5. `validate`: `GET http://<host>:<port>[/kafkaConsumer]/metrics/ping` contains `pong`, **20 x 5s**.

Other actions: `restart` (docker restart + validate), `start` (start if stopped, **`docker unpause` if running**), `unpause`, `pause`, `stop`, `status`, `heapdump` (actuator heapdump), `remove` (prompt; container, data dir, then `cleanup-topics`: `rmr /locks/indexed-<p>-<f>`, `rmr /locks/delete-<p>-<f>` and delete all `^<p>-<f>-` Kafka topics).

### 3.5 ansible-gaia — see section 5.

---

## 4. Cassandra: keyspaces, tables, cleanup

**VOS keyspaces** (backup/restore/retention only; the playbooks never create schema, the application does):
`keyspace_name = <prefix>_<product>_<infix>_<mode>_<family>` (`roles/backup/defaults/main.yml:9-14`)
- `prefix` = `vos` by default (`keyspace_prefix`), can be overridden with `-e keyspace_prefix=…`.
- `infix` for `vos` = `1810` if `lit_branch` starts with `lit-1810`, else **`1820` for every newer release**; for other prefixes = `trunk` (HEAD) / branch number / backup-name field.
- `mode` = `environment_mapping[USER].macro_build_mode` (`group_vars/all:49-97`: literatum/readonly/gcp/gcp-rehearsal=live, staging/midtierbeta/performance=beta, lts=lts, atypon/aws1=qa, migration=migration, *-cip=cip, ci=dev); unknown user -> `dev`.
- Example: `vos_aaas_1820_live_a1`. Developer-productivity restore (`-e source_env=…`) uses `<source_env>_<product>`.
- Restore **drops the keyspace first** (`restore-keyspace-snapshot.yml:2-5`) and recreates it with RF = number of cluster hosts.

**Gaia keyspaces / `table_index` / cleanup** — `gaia_cleanup.yml` + `roles/cleanup` (only place in all six repos that touches Gaia data):
1. Run as `ansible-actions.py -s cassandra -n <cassandra cluster> -a gaia_cleanup`; asserts `label == 'cluster'`; runs only on the first host and only if container `<groupname>-<ntp>` is running (`gaia_cleanup.yml:22-37`). Most tasks are `no_log: True`.
2. `get_keyspaces.yml:2-10`: `SELECT * FROM system_schema.keyspaces` via cqlsh in the container, keeps rows matching `grep -i gaia`, first column = keyspace. **Every keyspace whose name contains "gaia" is processed.**
3. `cleaner.yml` per keyspace:
   - `SELECT * FROM table_index` -> rows containing `_<digits>`, spaces removed; column 1 = `id`, column 2 = table name (l.1-8).
   - "templates" = id with the trailing `_<digits>` collapsed to `_<first digit>` (l.21-25).
   - per template: ids that `grep <template>` and end in a digit, `sort -r | tail -n+3` -> **everything except the two lexicographically-highest ids is marked for deletion** (l.36-43).
   - table names for those ids via `grep <id>` on the full output (l.54-61).
   - `DROP TABLE IF EXISTS <ks>.<table>` (l.67-76); `DELETE FROM <ks>.table_index WHERE id IN (…)` (l.78-85).
   - **on every cluster node**: `find /var/lib/cassandra/data -type d -iname '<table>*' -exec rm -rf {} +` (l.88-96).
   - on every node: `nodetool clearsnapshot --all -- <ks>; nodetool cleanup <ks>` (l.99-106).
   These versioned tables are what the Gaia side calls output-cache / per-bundle tables; the playbook treats them generically as "`table_index` ids with a numeric suffix".
4. **Cron**: there is **no crontab/cron task in any of these repos**. The only cron-oriented scripts are `files/cassandrabackup.sh` and `files/cassandraNodetoolRepair.sh`; whatever schedules `gaia_cleanup` lives outside these repos (Rundeck/crontab on the tools host — not verifiable here).

---

## 5. Gaia (ansible-gaia, master == origin/2.0)

- **What is deployed**: a plain Docker container per `gaia-server` host, named `<ansible_host>-<component_name>` (component_name = the Gaia cluster name, e.g. `dc-beta`), image `us-central1-docker.pkg.dev/atypon-artifact/docker-registry/atypon-gaia/gaia-fe:<image_tag>`, `network_mode: host`, `user: root`, memory limit `memory+2048M` / reservation `memory`M, OOM score 100, Docker healthcheck `curl -f http://localhost:<node_port>/actuator/health` (30s/10s/3/60s) (`roles/deploy-cluster/tasks/app-deploy.yml:118-151`). **No Kubernetes, no Rundeck code.** (`app_conf_path=/tmp/gaia-fe/kubernetes/gaia`, `git_repo_url`, `app_repo_path`, `git_branch`, `unique_hash/build_dir` in `group_vars/all` are unused.)
- **Variables** (all from the `<gaia><cluster …>` element, see 2.2): `image_tag` -> image tag; `bundle_version` -> default `<string name="bundle">` in `config.xml`; `memory` -> JVM sizing via `java-buildpack-memory-calculator` (`jvm-args.yaml:8-22`) and container limits; `node_port` -> `SERVER_PORT` and health URL; `deploy_version` -> **only** selects the ansible-gaia branch in the wrapper (never used by the playbooks). `cpu` and `port` are emitted but unused. `dc-beta` is just the cluster (group) name; beta resolves `deploy_version` to `2.0` (attribute or lifecycle fallback), whose tree equals master.
- **config.xml** (`templates/config.xml.j2`): `<configuration><string name="bundle">{{bundle_version}}</string><set name="scopes">` then per product `<set name="<product>"><string name="bundle">…</string><set name="clients"><string name="<source-branch>">bundle</string>[<string name="<previous_source_branch>">previous_bundle_version</string>]`, where the branch name is the `[-2]` path element of `<source>` / `<previous_source_branch>`.
- **deploy.yml** flow (`roles/deploy-cluster/tasks/main.yml`): skipped entirely (rc 0) when `USER` is `readonly` or `rorehearsal` (l.2-5); jvm-args; `check-bundle.yml` (render config, extract every `\d+.\d+.\d+`, HEAD `https://us-central1-maven.pkg.dev/atypon-artifact/maven/com/atypon/axel/<v>/axel-<v>.war` with basic auth `_json_key_base64` + base64 of controller file `/var/tmp/puppet-gcp-key.json`, must be 200); `app-deploy.yml`: render config, `xmllint`, copy start/configinit/configparser/updater to host `/tmp` (never mounted, deleted by `cleanup.yml`), inspect container; if running and not `force_recreate` -> `docker cp` new config to `/tmp/configs/config.xml` inside the container (the in-container `updater.sh` loop, `TYPE=dc`, re-runs `configinit.sh` within ~10s); if `force_recreate` -> remove; start container if not running or forced; copy OTel agent `~/apps64/otlp-java-agent/atypon_opentelemetry_javaagent_stacktrace_2_10_0.jar` (unless USER `cip`), copy `/var/tmp/puppet-gcp-key.json`, write base64 config into the container.
- In-container scripts: `configinit.sh` downloads `axel-<ver>.war` bundles from **Nexus** `…/repositories/passport/content/com/atypon/axel/…` with credentials `<secret at ansible-gaia/roles/deploy-cluster/files/configinit.sh:13>` / `:19`, unpacks `WEB-INF` to `/mnt/gaia-fe/bundles/<ver>`, copies config, deletes bundles not referenced by the config. OTel env -> `http://alloy.devops.atypon.com:4317/4318`, service `gaia_<account>`.
- Other actions: `update` (render + xmllint + `docker cp` config, **no bundle check**), `start/stop/restart/status` (status polls `/actuator/health` 15 x 5s), `remove` (prompt; container only, data removal commented out).
- **GitHub / SSH**: the only GitHub access is the wrapper cloning `git@github.com:atypon/ansible-gaia.git` over SSH with the running account's key, and the lifecycle JSON over HTTPS+token. `ansible.cfg:3` sets `private_key_file = ~/.ssh/id_rsa` for SSH to target hosts. gaia-fe source is **not** fetched.
- **Cassandra**: nothing in ansible-gaia creates or references Cassandra, keyspaces, `table_index` or output-cache tables; the rendered config has no Cassandra settings (the image/Spring profile `multi` carries them). Gaia Cassandra housekeeping exists only in `ansible-cassandra/gaia_cleanup.yml` (section 4).
- Callbacks: `ansible.cfg:5` whitelists `grafana_annotations` but the repo has **no `callback_plugins/`**, no dashboard id; Grafana key `<secret at ansible-gaia/ansible.cfg:21>`. No Pushgateway.

---

## 6. Consolidated failure-signature table

| Exact message (substring) | Meaning | Task file:line | Likely root-cause class |
|---|---|---|---|
| `Error [51] while cloning repository.` | ansible-<svc> branch clone failed | ansible-inventory/ansible-actions.py:75 | missing branch / empty `deploy_version` / GitHub SSH key |
| `Error [52] while pulling repository` | existing checkout cannot pull | ansible-actions.py:71 | dirty/diverged checkout, tag checkout, force-push |
| `WARN [Skipping updating the repo.]` | concurrent update; runs stale code | ansible-actions.py:69 | parallel runs on same account |
| `Error [53] while running dynamic inventory.` | inventory stdout not JSON | ansible-actions.py:50 | deployconf missing/invalid XML, stale inventory checkout |
| `Error [54] while trying to download atypon_lifecycle.json` | lifecycle fetch failed | ansible-actions.py:92 | GitHub token revoked (404), network |
| `NameError: … 'r'` traceback | network exception in lifecycle fetch | ansible-actions.py:95 | GitHub unreachable |
| `Error [55] wildcard match is not supported.` | bad matrix | ansible-actions.py:115 | lifecycle json edit |
| `argument -n/-p/--name/--product: invalid choice` (exit 2) | name not in inventory | ansible-actions.py:282 | product disabled/dropped by an inventory exception, misspelled family |
| `argument -a/--action: invalid choice` | no such `<action>.yml` in that version | ansible-actions.py:337 | wrong deploy_version branch |
| `MSG [ansible-playbook finished with a non-zero exit code …]` | playbook failed | ansible-actions.py:413,422 | see rows below |
| `Zookeeper cluster is not available` | no ZK answered `srvr` | ansible-solr/roles/zookeeper-check/tasks/zookeeper-check.yml:24 | ZK down / nc path / firewall |
| `Zookeeper version (…) and lit_version (…) mismatch` | ZK/lit compatibility | zookeeper-check.yml:44,55 | wrong ZK cluster in deployconf |
| `searchVersion=` (failed_when) | versions.properties fetch failed | ansible-solr/roles/search-version/tasks/get_search_version.yml:18 | GitHub token / branch missing in literatum |
| `Solr profile … not found. Available profiles are …` | profile missing in solr-plugins | search-version/tasks/verify_profile_in_solr_plugins_version.yml:20 | deployconf `solr_profile` |
| `Timeout when waiting for …/solr-<tag>.lock to be absent` | stale image lock | ansible-solr/roles/set-image/tasks/create-locks.yml:30 | killed earlier build; run `cleanup` of tmp lock manually |
| `ERROR: Bootstrap action failed` | zkcli bootstrap container failed 10x | ansible-solr/roles/bootstrap/tasks/bootstrap.yml:53 | ZK/config/image problem |
| `Term-synonyms folder '…' is missing!` (also Thesaurus/Smart-expansions) | publisher dirs absent | ansible-solr/roles/node-deploy/tasks/deploy.yml:57,73,89 | new env/host without publisher mount |
| `FAILED - RETRYING: Ensure node is alive and all cores are active (1440 …)` then fail | node not live/active in 2h | ansible-solr/roles/node-deploy/tasks/node-validate.yml:3 | replica recovery slow, OOM, ZK |
| `Wrong number of nodes (N) and shard configuration.` | replica math out of range | ansible-solr/roles/collections_ensure/tasks/main.yml:25 | `sharded`/node count |
| `Failed to gather config file hierarchy with Exception: …` | props hierarchy download failed | ansible-solr/library/grab_cfg_hierarchy.py:298 (also consumer) | branch missing / missing include file / token (message can echo the clone URL incl. token) |
| `Verify cores are of accepted state …` retries exhausted | cores not active in 10 min | collections_ensure/tasks/main.yml:158 | cluster unhealthy |
| `A lock file from another SolrRestore/SolrBackup job is found …` | lock present > 300s | ansible-solr/roles/backup-restore/tasks/main.yml:12 | concurrent/stale backup (consumers stay **paused** in this path) |
| `Solr backup|restore for <user>@<p>-<f> has failed.` | block failed; rescue ran | backup-restore/tasks/main.yml:151 | Solr async BACKUP/RESTORE error |
| `"fatal"/"error"/"exception"` verify_status json | Solr async request failed | backup-restore/tasks/verify.yml:24 | disk/NFS, Solr error |
| `ERROR: Backup is corrupted! Please run a rolling restart …` | CheckIndex failed | ansible-solr/roles/backup-integrity/tasks/backup-check-index.yml:38 | corrupt segment |
| `<backup_name> backup not found.` | find_backup no match | ansible-solr/tasks/find_backup.yml:29,56 (cassandra tasks/find_backup.yml:22,50) | wrong name/account |
| `file (…/backup_valid) is absent` | incomplete backup | backup-integrity/tasks/restore-check-index.yml:2 | backup failed earlier |
| `couldn't resolve module/action 'gc_file_storage'` | module only in `library/unused/` | ansible-solr/roles/backup-to-cloud/tasks/upload-to-gc.yml:17 | GCS upload path is broken unless module installed elsewhere |
| `Not allowed to run this action for a product. …` | cassandra action given product group | ansible-cassandra/deploy.yml:18 (restart/start/stop/status/remove/repair/gaia_cleanup) | used `-n <product-family>` |
| `Not allowed to deploy multiple nodes of the same cluster on the same machine.` | duplicate hosts | ansible-cassandra/deploy.yml:27 | deployconf |
| `FAILED - RETRYING: Validate node is up (30 …)` | no `COMPLETED` bootstrap | ansible-cassandra/roles/validate/tasks/validate-node.yml:2 | node not joining (seeds, ports, disk) |
| `Validate cluster is up` / `nodes are reachable` fail | peers/schema count != N | validate/tasks/validate-cluster.yml:2,19 | node down, schema disagreement |
| `Successfully created snapshot package` not in stdout | getSnapshot failed | ansible-cassandra/roles/backup/tasks/backup-keyspace-snapshot.yml:15 | keyspace missing, disk |
| non-zero rc on `ls -l …/data | grep vos_<product>` | keyspace dir absent | backup-keyspace-snapshot.yml:7 | product not using Cassandra / wrong prefix |
| `this_backup in existing_backups` failed_when | no new tarball | ansible-cassandra/roles/backup/tasks/main.yml:34 | getSnapshot wrote elsewhere |
| `Import operation complete` missing / `ERROR`/`Exception` | putSnapshot/sstableloader failed | ansible-cassandra/roles/restore/tasks/restore-keyspace-snapshot.yml:17 | schema/replication mismatch (keyspace already dropped!) |
| `Repair completed successfully` missing | nodetool repair failed | ansible-cassandra/roles/repair/tasks/repair.yml:5 | node down/streaming |
| `Requested clearing snapshot(s) for [` missing | clearsnapshot failed | ansible-cassandra/roles/backup-retention/tasks/snapshot-retention.yml:7 | container name case (`name` vs group) |
| `Error on cluster create <c>: …` | redis-cli create failed | ansible-redis/roles/create-cluster/tasks/create-cluster.yml:28 | nodes not empty / unreachable |
| `cluster_state` != ok after 10 x 10s | redis cluster not ok | create-cluster/tasks/verify-cluster-state.yml:3 | slots uncovered, node down |
| `<c>_<port> is not ready yet to accept operations.` | still `loading:1` after 10 min | ansible-redis/roles/verify-redis-cluster/tasks/verify-redis-cluster.yml:21 | big dataset/replica sync |
| failover `stdout != "OK"` | takeover refused | ansible-redis/roles/failover-node/tasks/failover-node.yml:26 | replica unhealthy |
| `New node added correctly.` missing | add-node failed | ansible-redis/roles/add-node/tasks/main.yml:42 | node not empty |
| `Consumer and Searchservice share the same ports …` | socket collision | ansible-consumer/roles/port-conflict-check/tasks/port-conflinct-generic.yml:13 | deployconf |
| `indexVersion=` failed_when | versions.properties fetch failed | ansible-consumer/roles/consumer-version/tasks/consumer_version_from_versions_properties.yml:29 | token/branch |
| `'dict_values' object is not subscriptable` | py3 bug on old branches | consumer_version_from_pom_xml.yml:120 | lit-2010/1910/1830 under Ansible 8.7 |
| `server_type == "invalid"` | application.properties neither 200 nor 404 | ansible-consumer/roles/server-type/tasks/main.yml:28 | GitHub token/rate-limit |
| `Task failed and lock file cleanup completed` | image build failed (rescue) | ansible-consumer/roles/consumer/tasks/main.yml:26 | git SSH clone / mvn / push |
| `'Created topic' not in … and 'Due to limitations in metric names' not in …` | topic creation output check | ansible-consumer/roles/consumer/tasks/deploy.yml:240 | no enabled topics, Kafka/ZK down, or all topics already existed without underscore names |
| `FAILED - RETRYING: Get ping status (20 …)` | no `pong` in 100s | ansible-consumer/roles/validate/tasks/validate.yml:2 | app start failure (Kafka/Solr ZK/Redis) |
| `Error response from daemon: Container … is not paused` | unpause on a running container | ansible-consumer/start.yml:19, unpause.yml:19 | `start` on an already running consumer |
| `'force_recreate' is undefined` | var never defaulted | ansible-gaia/roles/deploy-cluster/tasks/app-deploy.yml:99 | deploy run without `-e force_recreate=…` |
| `The XML file ~/tmp/<c>-config.xml is invalid.` | xmllint failed | app-deploy.yml:59 (update.yaml:16) | bad deployconf values |
| `version_check.status != 200` on `axel-<v>.war` | bundle absent in GCP Artifact Registry | ansible-gaia/roles/deploy-cluster/tasks/check-bundle.yml:30 | unpublished bundle, bad key file, stray `x.y.z` string |
| `could not locate file in lookup: /var/tmp/puppet-gcp-key.json` | key missing on controller | check-bundle.yml:33 | puppet not run on tools host |
| `No such container: <host>-<c>` on `docker cp/exec` | CLI hit default docker socket | app-deploy.yml:102,154,161,167; update.yaml:22 | per-user socket (`docker-<USER>.sock`) not used |
| `failed to verify bundle <v>` (container log only) | in-container Nexus 404 | ansible-gaia/roles/deploy-cluster/files/configinit.sh:14 | bundle on GCP AR but not on Nexus |
| `nexus url doesn't exists` (container log only) | Nexus unreachable | configinit.sh:8 | network |

---

## 7. Bugs and risks

1. **Pushgateway always reports success** — no `v2_runner_on_failed`, so `status` is always `"1"` (`ansible-solr/callback_plugins/pushgateway.py:184-192`; same in consumer). Also mixes `datetime.now()` and `utcnow()` (l.121, 181).
2. **Gaia-keyspace cleanup can delete live data**: `find /var/lib/cassandra/data -type d -iname '<table>*' -exec rm -rf` searches **all keyspaces** (VOS included) with a **prefix** glob, on every node, while Cassandra is running (`ansible-cassandra/roles/cleanup/tasks/cleaner.yml:88-96`). Kept tables whose names start with a deleted table's name (e.g. `x_1` vs `x_12…`) lose their data directories.
3. Cleanup selection is fragile: substring `grep` for templates/ids (`cleaner.yml:37,55`), lexicographic `sort -r` of numeric suffixes of different lengths (l.37), "template" = first digit only (l.22), every keyspace matching `gaia` case-insensitively (`get_keyspaces.yml:6`), most tasks `no_log: True` (hides what was dropped).
4. **Consumers left paused**: solr `restart.yml` unpause is a separate play that never runs after a node failure (`ansible-solr/restart.yml:32-40`); backup lock-wait failure happens outside the rescue block (`roles/backup-restore/tasks/main.yml:7-15`) so consumers stay paused and the 5h Alertmanager silence is left behind; pause failures masked by `|| true` + `ignore_role_errors: True` (`roles/solr-commit-reload/tasks/consumers-pause.yml:24`, `defaults/main.yml:12`).
5. Backup lock is only created if the backup dir already exists (`backup-restore/tasks/main.yml:17-22`) — the first backup of each 16-day window runs unlocked.
6. `gc_file_storage` module lives in `ansible-solr/library/unused/` (not on the module path) but is used by `roles/backup-to-cloud/tasks/{upload-to-gc,download-from-gc}.yml:15-17` — GCS upload/download fails at include time unless the module is installed elsewhere.
7. `restore-externals` uses `lookup('file', item[0])` (controller-side read of a target-side path) (`roles/backup-restore-externals/tasks/restore-externals.yml:30`).
8. Gaia `force_recreate` has no default -> every deploy fails unless passed (`ansible-gaia/roles/deploy-cluster/tasks/app-deploy.yml:99-171`).
9. Gaia `docker cp/exec` omit `-H {{ docker_url }}` while `docker_container` uses the per-user socket (`app-deploy.yml:102-107,153-171`; `update.yaml:21-24`) — in DC the CLI talks to the default daemon.
10. Gaia verifies bundles in GCP Artifact Registry (`check-bundle.yml:21-33`) but the container downloads them from Nexus (`configinit.sh:13,19`); `update.yml` skips the check entirely. A bundle present in one repo but not the other makes `updater.sh` loop forever inside the container while Ansible reports success.
11. Gaia deploy silently no-ops (rc 0) for USER `readonly`/`rorehearsal` (`roles/deploy-cluster/tasks/main.yml:2-5,19`).
12. Gaia inventory includes disabled and non-top-level products and keys products by name only (`ansible-inventory/gaia.py:109-124`); missing cluster attributes become `""` (l.96-103) -> empty `deploy_version` -> `[51]`.
13. Gaia `Xms` regex misses `G` units and yields `-XmsNone` if the calculator output changes (`jvm-args.yaml:18`); `ansible.cfg` whitelists a callback that is not shipped (`ansible-gaia/ansible.cfg:5`).
14. Consumer `start.yml`/`unpause.yml` run `docker unpause` on any running container -> fails when it is not paused (`ansible-consumer/start.yml:19-21`, `unpause.yml:19-21`).
15. Consumer topic-creation success check relies on Kafka's underscore warning when topics already exist (`ansible-consumer/roles/consumer/tasks/deploy.yml:240`); an empty enabled-topic list always fails.
16. Consumer pom path: `.values()[0]` breaks on Python 3 (`consumer_version_from_pom_xml.yml:120`).
17. Consumer lifecycle has no `2610` row -> lit-2610 silently uses fallback `10.0` (`ansible-consumer/atypon_lifecycle.json:6`).
18. Consumer inventory requires the misspelled `kakfa_cluster_name` and a `<solr>` block; otherwise the product vanishes (`ansible-inventory/consumer.py:120-123,155`).
19. Wrapper: unbound `r` (`ansible-actions.py:95`), `None` deploy_version (l.114), no `break` in matrix loop (l.99-104), argparse exit 2 collides with failure exit 2, `-q -vv` crash (l.387), stale-code warning path (l.67-69), tag checkouts fail on pull (l.65).
20. Inventory: `deploy_host` loop iterates all `export` elements for each `exports` (`core_product.py:134-137`); the empty-inventory guard is dead (`inventory.py:176`); `expandvars` on raw XML (l.153); DB passwords exported as Ansible vars and via `api.py` `kvlist/varList` (`core_product.py:36-42`, `api.py:254-262`).
21. Cassandra container name mixes `group_names[0]` (lower-cased) and raw `name` (`deploy-cluster.yml:7` vs `backup-keyspace-snapshot.yml:13`, `repair.yml:3`, `cleaner.yml:4`) — any upper-case cluster name breaks backup/repair/cleanup.
22. Cassandra exporter binds fixed host port 9500 (`roles/deploy/defaults/main.yml:42-43`) — two clusters on one host collide.
23. Cassandra backup snapshots one node only (`backup.yml:4` run_once + node-local `nodetool snapshot`); complete only if RF == #nodes. Restore drops the keyspace before verifying the load can succeed (`restore-keyspace-snapshot.yml:2-18`).
24. Vendored `putSnapshot` only `echo`es the table-file rename (`…/cassandra-snapshot-tools/putSnapshot:268`); `getSnapshot` checks `$?` after `RC=$?` (l.274-276).
25. `cassandraNodetoolRepair.sh` writes `…/tmp/<user>-<cluster>.log` but `postReport` reads `…/tmp/repair-<user>-<cluster>.log` (`files/cassandraNodetoolRepair.sh:18,25`).
26. Cassandra/Redis have no auth (`cassandra.yaml` `AllowAllAuthenticator`; redis `protected-mode no`, no password, no persistence: `templates/redis.conf.j2:111,444-446,1397`); `rdb_enabled` is tested as a raw truthy value (`redis.conf.j2:440`), so a string `"false"` from deployconf enables RDB.
27. Redis `verify-redis-cluster` only fails on `loading == '1'`; an empty result (container down) passes (`verify-redis-cluster.yml:20-24`); `create-cluster` ignores rc other than 0/1 (`create-cluster.yml:12-40`).
28. Solr base image hard-coded `9.10.1` regardless of root-pom (`roles/set-image/tasks/get-base-solr-image.yml:28-29`); `node-validate` can block for 2h per node (`node-validate.yml:18`); `grab_cfg_hierarchy` uses a shared `/tmp/sparse_<branch>_<product>` dir (race between concurrent runs) and its failure message can include the token-bearing clone URL (`library/grab_cfg_hierarchy.py:163-170,298`).
29. `vars_prompt force` on remove playbooks turns non-interactive runs into silent no-ops (e.g. `ansible-solr/remove.yml:11-15`).
30. Hard-coded credentials in version control (do not rotate from here; listed for the owner): `ansible-inventory/ansible-actions.py:21`, `ansible-inventory/requirements.yaml:2`, `ansible-solr/ansible.cfg:26` (+ commented `:30`), `ansible-solr/group_vars/all:37,84`, `ansible-solr/roles/backup-to-cloud/files/gc_sa.json:4-5`, `ansible-solr/roles/backup-to-cloud/tasks/upload-to-s3.yml:6-7` (+ commented `:12-13`), `ansible-solr/roles/set-image/defaults/main.yml:40`, `ansible-consumer/ansible.cfg:26` (+ `:30`), `ansible-consumer/group_vars/all:32,73`, `ansible-gaia/ansible.cfg:21`, `ansible-gaia/roles/deploy-cluster/files/configinit.sh:13,19`, `ansible-gaia/roles/deploy-cluster/files/start.sh:22`.
