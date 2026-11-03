# 11 — Ansible service repos: atm, ingestion, searchservice, proxysolr, tools (+ inventory mismatches)

Scope: `$LIT_REPOS/{ansible-atm, ansible-ingestion, ansible-searchservice, ansible-proxysolr, ansible-tools, ansible-inventory}`.
Read-only. Secrets are not reproduced; where one exists it is written as `<secret-bearing line at file:line>`.
Wrapper / inventory internals already covered in `03-ansible.md` sections 2.x; this file only adds what matters for these five services.
Date of analysis: 2026-09-25.

**Correction to the task framing:** `ansible-actions.py` lives in **atypon/ansible-inventory** (`ansible-inventory/ansible-actions.py`), not in platform-tools. platform-tools only references the `ansible-actions` alias (`notes/02-platform-tools.md:31`, `aliases.sh` is not in the repo).

---

## 0. Which branch each env actually runs

How the branch is picked (`ansible-inventory/ansible-actions.py:302-315`): the group var `deploy_version` wins if set and not `auto|fallback|latest`. Otherwise it takes `lit_version` (the `[-2]` path element of `<source>`), strips `lit-`, and prefix-matches it against **`atypon_lifecycle.json` on GitHub master** of `ansible-<svc>`. There is no `break`, so the last match wins. `fallback` is used when nothing matches.

deployconf parsed with `xml.etree` (secret-looking attributes skipped). No env sets `deploy_version` in `<ansible-common>`. The only `<ansible-common>` args are the registry pull/push URLs.

| Service | Lifecycle (master) | beta (midtierbeta) | stag (staging) | prod (literatum) |
|---|---|---|---|---|
| atm | `9.0:[master,2510,fallback]`, `8.0:[2410,2310,2210]`, `4.2:[2020]`, `3.2:[2010]`, `3.1:[1910,1830]` | 23 enabled ATM products: 21 → **9.0** (lit-2610* and `master` fall to fallback 9.0, because 2610 is not in the matrix), 2 → **8.0** (lit-2410*) | 40: 31 → 9.0, 9 → 8.0 | 43: 30 → 9.0, 13 → 8.0 |
| ingestion | `main:[2410,fallback]` (the same on origin/master 70805e8 and main) | 1 enabled product (asha-B2, lit-2610) → **main** | none configured | none configured |
| searchservice | `4.0:[master,2510,fallback]`, `3.0:[2410,2310,2210]`, `1.1:[2020,2010]` | **no `<searchservice>` in any env today** | none | none |
| proxysolr | `3.1:[HEAD,fallback]`… but every cluster sets `@deploy_version` | 7 clusters: 1910 → **1.0**, 2010/2020 → **2.1**, 2210/2410/master → **3.1**, 2610 → **4.1** | 5 clusters: 2010/2020 → 2.1, 2410/master → 3.1, 2610 → 4.1 | none configured |
| tools | `master:[fallback]` | **master** | master | master |

Commits read (`git fetch --depth 1 origin <branch>` done for every non-master branch):

| Repo | Branch | Commit | Relation to the clone's default branch |
|---|---|---|---|
| ansible-atm | master | 9aa04ff | — |
| ansible-atm | 9.0 | a3d37dd | **same tree as master** (3bdefe2) |
| ansible-atm | 8.0 | e0127e0 | 3 files differ (see 1.6) |
| ansible-ingestion | main | 24b39c6 | default branch; `origin/master` 70805e8 is only used by the wrapper for its lifecycle json |
| ansible-searchservice | master = 4.0 | 00d600e | same commit |
| ansible-searchservice | 3.0 | d083d83 | 3 files differ |
| ansible-proxysolr | master = 4.1 | 4b648fc | same commit |
| ansible-proxysolr | 3.1 / 2.1 / 1.0 | adfca29 / e7a5d02 / c5832db | diffed against 4.1 |
| ansible-tools | master | 750b441 | — |
| ansible-inventory | master | 0e3ac30 | clone up to date with origin |

Note: the wrapper reads the lifecycle json from GitHub **at run time**. If someone edits master's matrix, the mapping above changes without any deployconf change.

---

## 1. ansible-atm (ATM topic-model service)

### 1.1 Invocation
| Deploy Server action | Command (actions.xml) | Validator |
|---|---|---|
| ProductAtmDeploy (ProductRelease child, `PreExecuteVisitor.java:2783-2785`, created when `conf.getAtm(p,f) != null`) | `ansible-actions -s atm -p $util.getProduct() -f $util.getFamily() -a deploy` + `$util.ansibleCheckExitCode()` (X:969-975) | `COMPLETED SUCCESS` |
| ProductAtmRemove (ProductTermination / ProductRebuild child) | `ansible-actions -s atm -f ${util.family} -p ${util.product} -a remove -e force=true` (X:1443-1447) | `COMPLETED SUCCESS` |

`AnsibleCheckExitCode` (actions.xml:2794-2798) echoes `COMPLETED SUCCESS` or `COMPLETED FAILURE` based on `$?` of the wrapper. So **every wrapper exit code other than 0 is just `COMPLETED FAILURE`**, whether it is 1, 2, 4 or 5x.

Actions (the root `*.yml` files): `deploy, restart, start, stop, status, remove, heapdump`.

### 1.2 Inventory (`ansible-inventory/atm.py`)
- Group `<product>-<family>` (product lower-cased), from enabled top-level products only (`core_product.py:86-87`).
- Hosts `<product>-<family>_<atm-server@host>_<idx>`, with `ansible_host = host` (atm.py:132-141).
- `atm_port` = `deployfamilyinfo/entry[@deployfamily]@srunport + 1` (atm.py:26-32; the comment says +3, the code does +1). `atm_cluster` uses host `@atm_port` > `<atm atm_port>` > srunport+1.
- **Required, or the product silently disappears** (the `except Exception: continue` at atm.py:147-150):
  - at least one `<atm-server>` (l.110)
  - `<consumer kakfa_cluster_name=…>` on the same product (l.113; the misspelling is required), and that kafka cluster plus its ZooKeeper cluster must exist
  - at least one `<atm><model …>` (l.126-130 raises `Invalid ATM configuration: no ATM models found`, which is swallowed)
  - every model's `product-family` must resolve in the solr inventory (l.128)
- Today all enabled ATM products in beta, stag and prod pass these checks (verified by parsing deployconf). No ATM host:port collisions either.

### 1.3 deploy.yml task sequence
1. **Play "Identify server type"** (serial 1, run_once): role `server-type`.
   - Meta dependency `atm-version`: fetches `https://raw.githubusercontent.com/atypon/literatum/<lit_version>/atypon/literatum/versions.properties` (git) or SVN `branches/<lit_version>` / trunk. `failed_when: 'atmVersion=' not in content`. Result: `atm_version = atm-<v>` (`roles/atm-version/tasks/atm_version_from_versions_properties.yml:19-49`).
   - Creates `atm_root_dir`. Fetches `api.github.com/repos/atypon/id-atm/contents/id-atm-service/src/main/resources/application.properties?ref=<atm_version>`: 200 = `spring-boot`, 404 = `spring-mvc`, anything else = `invalid`, which fails (`roles/server-type/tasks/main.yml:5-30`).
2. **Play "Deploy Atm"** (serial 1, force_handlers, max_fail 0): roles `atm`, then `validate`.
   - `image-pull.yml`: `docker_image` pull of `<registry>/id/atm:<atmver>-production-d<deploy_version>` (e.g. `…-d9.0` / `…-d8.0`), `ignore_errors`. `build_img = pull failed`.
   - If `build_img`, `create-locks.yml`: lock file `~/apps64/ansible/atm/tmp/atm-<tag>.lock`. If the lock exists: `wait_for` it to disappear (300 s), pull the image, set `build_img=False`.
   - `create-paths.yml`: `/local$HOME/servers/<family>/<ansible_host>/docker_atm_<atm_port>/{logs,run,tmp,registry,atypon}`, plus `…/servers/common/atm-image/<hash>` for builds.
   - `create-image.yml` (build only):
     - SSH `git clone git@github.com:atypon/id-atm.git` @ `atm-<v>`
     - Maven 3.9.10 (copied from `~/apps64/maven-3.9.10`, else downloaded)
     - `mvn clean install -Pproduction [-Dp.type=war]` with `JAVA_HOME=~/apps64/java21` (8.0: java11)
     - unpack `warplda_binaries.tgz`
     - download `platform-tools/atm/warp_learntopics.sh` from GitHub API
     - Dockerfile: spring-mvc uses `jetty:10.0.0-jre11`; spring-boot uses `eclipse-temurin:21-jdk` (8.0: `…/openjdk:11-jdk`)
     - build and push, then remove the lock
   - `deploy.yml`:
     - `intermediate.dtd`, `literatum.props.xml` and `literatum.kafka.props.xml` from literatum@lit_version
     - `atm.props.xml` template (kafka brokers, kafka ZK, models → `/models/<name>` + `zkHost`)
     - `grab_cfg_hierarchy` for the client props, with **`ignore_errors: yes`**
     - `props.files`
     - stat `atm_across_publishers_model_dir` (`/shared/atm/atmdata/classification-model/atm_across_publishers_model/`); **fails if missing**
     - per model: stat `$HOME/publisher/<product>[-<family>]/atmdata/classification-model/<model>`; **fails if missing**
     - md5 of the config dirs goes into env `ATM_CONFIG_MD5`, so a config change recreates the container
     - `docker_container` `<USER>-<product>-<family>-atm-<atm_port>`: host port `atm_port` → 8080, restart_policy `always`, 4 CPUs, heap 8g with models / 2g without (Xms 2g), memory limit off by default
   - `validate`: `GET http://<ansible_host>:<atm_port>` + `/actuator/health` must contain `"UP"` (spring-boot) or `/atmService/configuration/serverTime` must contain `currentTimeEpoch` (mvc). **10 × 5 s** (`roles/validate/tasks/validate.yml:2-15`, task name `Get  status` with two spaces).
3. Other actions:
   - `restart`: `docker restart -t 60`, then validate
   - `start`: inspect, start if `false`, then validate
   - `stop`: inspect, stop if `true`
   - `status`: inspect, validate if running
   - `remove`: `vars_prompt force`; removes the container and the `atm_root_dir` (path guard)
   - `heapdump`: curl `/actuator/heapdump` inside the container, async 10 s, errors ignored

Callbacks: `profile_tasks, grafana_annotations, pushgateway` (Grafana dashboard 255; key `<secret-bearing line at ansible-atm/ansible.cfg:25>`). The plugin files are byte-identical to ansible-consumer's, so **Pushgateway always reports success** (03 §3.1).

### 1.4 Hosts, containers, ports
- Hosts: beta `atm-beta-1..3`; stag `atm-stag-1..3`; prod `prod-atm-literatum[2-7]-1/2`, `prod-atm-<publisher>-1/2`, `wk-prod-atm1/2` (asco-A40 writes it as `Wk-prod-atm1/2`, with a capital W).
- Container `<USER>-<p>-<f>-atm-<srunport+1>`. Host dirs `/local/home/<USER>/servers/<family>/<ansible_host>/docker_atm_<port>`.
- The case difference means `Wk-…` and `wk-…` products on the same machine get different directory and hostname spellings, and `-l wk-prod-atm1` would not match asco-A40's `*_Wk-prod-atm1_*`.

### 1.5 Failure modes (printed text)
- `atmVersion=` failed_when on the versions.properties task: the literatum branch is missing, GitHub token/404, or there is no `atmVersion` line.
- `server_type == "invalid"`: the id-atm `application.properties` call returned neither 200 nor 404 (token, rate limit, or tag `atm-<v>` missing).
- `Timeout when waiting for …/atm-<tag>.lock to be absent`: a previous build was killed or failed. `create-image.yml` has **no rescue**, so a failed mvn or push leaves the lock, and every later deploy of that tag waits 300 s and then fails. The lock is only removed as the last build task (`create-image.yml:95-100`).
- The git clone of id-atm fails (`Permission denied (publickey)` / `Remote branch atm-<v> not found`), or mvn fails (`BUILD FAILURE`), or the docker push fails.
- The `stat` of `atm_across_publishers_model_dir` fails (failed_when is true): the shared model dir is absent on the host.
- `Verify atm models directories exist…` fails: the publisher model dir is absent for a `<model name>`.
- `FAILED - RETRYING: Get  status (10 retries left)` and then a fatal on `validate`: the app did not come up within 50 s. This is common with an 8 g heap plus models; check `docker logs <USER>-<p>-<f>-atm-<port>`.
- The 8.0 → 9.0 switch changes the image tag suffix (`-d8.0` → `-d9.0`) and the Java major version (11 → 21). The first deploy after a product moves to lit-2610 therefore triggers a **fresh build** on the tools host.
- Possible (not verified): the "Pull atm image (remote)" task in `create-locks.yml:38-43` has no `source:` parameter. Recent `community.docker` versions refuse `state: present` without `source`. This only fires when a lock file was found.

### 1.6 atm 8.0 vs 9.0 (full diff)
- `java_version` 11 vs 21.
- Spring-boot base image `…/openjdk:11-jdk` vs `eclipse-temurin:21-jdk`.
- The branch's own lifecycle json.
- Everything else is identical.

### 1.7 Success-while-broken
- `grab_cfg_hierarchy` has `ignore_errors: yes` (`roles/atm/tasks/deploy.yml:52-66`). If the client props hierarchy cannot be fetched, `props.files` contains only `literatum.props.xml` + `atm.props.xml`. The deploy is green but the product-specific config is missing.
- Validate only checks `/actuator/health` `UP` on each host for 50 s. It does not check Kafka consumption or model load.
- Pushgateway shows success even when the playbook failed.

---

## 2. ansible-ingestion (id-ingestion-service), branch `main`

### 2.1 Invocation
- ProductIngestionDeploy (ProductRelease child, `PreExecuteVisitor.java:2787-2789`, when `conf.getIngestion(p,f) != null`): `ansible-actions -s ingestion -p ${util.getProduct()} -f ${util.getFamily()} -a deploy` (X:1216-1220), validator `COMPLETED SUCCESS`.
- Actions: `deploy, restart, start, stop, status, remove`.
- Only beta uses it today (asha-B2; ar-A1, mcp-B1 and aamc-A2 are configured but disabled).

### 2.2 Inventory (`ansible-inventory/ingestion.py`)
- Group `<p>-<f>`, hosts `<p>-<f>_<ingestion-server@host>_<idx>` with `node_ip` from `<machines>`.
- Needs `<ingestion kafka_cluster_name service_port debug_port>`. A missing attribute returns `None`, and l.108 then raises and **drops the product**.
- Also needs a resolvable kafka cluster and a `<solr>` block on the same product (l.111). Any exception drops the product (l.143-146).
- `service_port`: explicit (beta asha-B2 `11882`, debug `11883`, host `beta-consumer-8`).

### 2.3 deploy.yml sequence
1. `ingestion-version` (when `ingestion_version` undefined): **GitHub only** `literatum/<lit_version>/…/versions.properties`, `failed_when: 'ingestionVersion=' not in content`. Result `ingestion-<v>`.
2. `deploy-cluster/main.yml`:
   - Tag `<v>-production-d<deploy_version>`. The wrapper always passes `-e deploy_version=main`, so the tag is **`…-dmain`**; the role default `deploy_version: 1` is dead.
   - `docker_image` pull (errors ignored).
   - If it failed and we are in DC: `build-image.yml` (run_once, delegate_to localhost):
     - GitHub API `git/ref/tags/id-ingestion-service-<v>`; a 404 fails with `Tag 'id-ingestion-service-<v>' does not exist in atypon/id-ingestion-service…`
     - POST `actions/workflows/workflow.yaml/dispatches`, expecting 204 with 3 retries; otherwise `Failed to trigger GitHub Action workflow dispatch after 3 retries…`
     - pause 10 s
   - Then `image-pull.yml`: **20 × 30 s (10 min)** pull retries, `ignore_errors: yes`.
   - Dev mode builds locally with mvn instead.
3. `deploy.yml`:
   - Dirs `/local$HOME/servers/<family>/<host>/docker_ingestion_<service_port>/{atypon,registry,logs,run,tmp}`.
   - `intermediate.dtd` and `literatum.props.xml` from literatum@lit_version (**git only**; the SVN tasks are commented out).
   - `ingestion.props.xml` (solr ZK, kafka brokers, kafka ZK).
   - `grab_cfg_hierarchy` with **`ignore_errors: yes`**, then `props.files`.
   - `docker_container` `<USER>-<p>-<f>-ingestion-<service_port>`: port `service_port` → 8080, `user: root`, restart always. **No -Xmx** (JAVA_OPTIONS has only `-Dregistry.path`).
4. `validate`: `GET http://<host>:<service_port>/configuration/serverTime` must contain `currentTimeEpoch`, **10 × 5 s**.

Other actions:
- `restart`: `docker restart` with no `-t`, then validate.
- `start`: start if stopped, then validate.
- `stop`: see 2.5.
- `status`.
- `remove`: prompt; removes the container, then `cleanup-topics` deletes all `ingestion-<p>-<f>-*` Kafka topics through a throw-away `id/kafka:0.11.0.0` container (`ignore_errors`). **The data dir is not removed.**

Callbacks as ATM (Grafana dashboard 254 — the same id as consumer; key `<secret-bearing line at ansible-ingestion/ansible.cfg:26>`).

### 2.4 Failure modes
- `ingestionVersion=` failed_when: the literatum branch lacks `ingestionVersion`. Older branches (e.g. lit-2210 mcp-B1) would fail here if enabled.
- `Tag 'id-ingestion-service-<v>' does not exist…`, or the workflow dispatch is not 204: GitHub token/permissions, or the tag was never cut.
- `FAILED - RETRYING: Pull image with synchronized tag (with retry) (20 retries left)` × 20, and then the `docker_container` task fails with a pull/manifest error. The GitHub Action did not publish `ingestion:<v>-production-dmain` within ~10 min. Check the id-ingestion-service Actions run (read-only) and whether its `deploy_version` input produced `dmain`.
- `FAILED - RETRYING: Validate service is up` → fatal: the app did not start within 50 s.

### 2.5 Success-while-broken / latent bugs
- **`stop.yml` never stops a running container**: its condition is `inspect_output.stdout == 'false'` (`stop.yml:16-18`), so rc is 0 and nothing happens.
- `grab_cfg_hierarchy` ignore_errors (as ATM).
- `mount_root_dir` is defined in `group_vars/all:25` from `server_type` (spring-mvc / spring-boot). Playbook `group_vars/all` outranks the role default `/app` (`roles/deploy-cluster/defaults/main.yml:40`). Ingestion has no server-type role, so `server_type` is the deployconf `<server type>` value (`beta` / `live`, from `core_product.py:144`). That makes `mount_root_dir` **empty**, and the atypon dir is mounted at **`/atypon`**, not `/app/atypon`. This is inferred from Ansible precedence rules, not observed. Check with `docker inspect` on the container (read-only).
- `remove` leaves the data dir, and topic cleanup errors are ignored.
- Image pull is `ignore_errors`, so the real failure surfaces later at `docker_container`.

---

## 3. ansible-searchservice (id-search-service), master = 4.0

### 3.1 Invocation
- SearchServiceDeploy: `ansible-actions -s searchservice -n $util.getProduct() -f $util.getFamily() -a deploy` (X:962-966).
- It is created in ProductRelease **only inside the `<solr>` branch** (`PreExecuteVisitor.java:2768-2772`), and also in LTF.
- `SetupSearchService` / `RemoveSearchService` edit deployconf (P:1581/1604).
- **No env has a `<searchservice>` today**, so this path is dormant in beta, stag and prod.
- Actions: `deploy, create-image, restart, start, stop, status, remove, heapdump`.

### 3.2 Inventory (`searchservice.py`)
- `searchservice_http_port = srunport + 3` (**the same default as consumer_port**) and `grpc = srunport + 9`. Host or cluster attributes can override them.
- Needs the product `<solr>` and a redis cluster: from `<searchservice redis_cluster_name>` or else `<cache redis_cluster_name>` (l.110-115). Any exception drops the product.
- **A `<searchservice>` element with no `<searchservice-server>` gives a group with `hosts: []`** (l.95-137).

### 3.3 deploy.yml sequence
1. Play `port-conflict-check` (run_once): runs `inventory.py consumer -j -n <p>-<f> | jq .consumer_cluster` and `inventory.py solr … .solr_prometheus_exporter`. It fails (`consumer and searchservice share the same ports so they must be deployed in different machines…`) if a consumer or solr-exporter socket equals a searchservice http or grpc socket.
2. Play deploy (serial 1). Role `deploy`, with meta dependencies `searchservice-version` and `create-image`:
   - Version: `searchVersion=` from versions.properties (git/SVN), giving `search-<v>`. lit-2010/1910/1830 use pom parsing with `.values()[0]`, which is a Python 3 bug.
   - Image `id/searchservice:search-<v>-d<deploy_version>`. The `regex_replace('^searchservice-')` does not strip `search-`.
   - Pull, then lock (`searchservice-<tag>.lock`, 300 s), then build (clone `id-search`, mvn, `eclipse-temurin:21-jdk`; 3.0 uses `openjdk:11-jdk`), then push. No rescue, so a failed build leaves the lock.
   - `get-files`: `id-search-service.props.xml` (redis nodes, solr ZK), then `grab_cfg_hierarchy` (**hard fail in DC**; `ignore_errors` only in dev), then `props.files`, then an md5 of the registry into `REGISTRY_FILES_MD5`.
   - `docker-deploy`:
     - thesaurus synonyms dir `<publisher_home_path or /publisher/common>/journals/lucene/thesaurusSynonyms/en` is **required** (`require_thesaurus_synonyms: True`); smart-expansions is optional
     - container `<USER>-<p>-<f>-searchservice-<http_port>` with ports `http → 8081`, `grpc → 6565`
3. `validate`: `GET http://<host>:<http_port>/ping` must contain `pong`, **10 × 5 s**.

Grafana dashboard 234. `grab_cfg_hierarchy.py` differs from consumer's only by one blank line.

### 3.4 Failure modes
- `Thesaurus-synonyms folder '…' is missing! Indexing does not work without thesaurus-synonyms…` (`roles/deploy/tasks/docker-deploy.yml:17-23`).
- `Smart-expansions folder … is missing!` (only if `-e require_smart_expansions=True`).
- The port-conflict messages above.
- `searchVersion=` failed_when.
- `Failed to gather config file hierarchy with Exception: …` (grab_cfg_hierarchy; the message may echo a token-bearing URL, see 03 §6).
- Lock timeout, like ATM.
- `FAILED - RETRYING: Validate HTTP port` → fatal.

### 3.5 Success-while-broken
- **An empty group** (`<searchservice>` without servers): the play prints `skipping: no hosts matched`, rc 0, `COMPLETED SUCCESS`, and nothing is deployed.
- The port-conflict check is skipped silently if the consumer inventory dropped the product (jq prints `null`, which contains no `:`).

### 3.6 3.0 vs 4.0
- Only Java 11 → 21, the base image, and the lifecycle json.

---

## 4. ansible-proxysolr (id-core solr proxy, gRPC)

### 4.1 Invocation
- ProxySolrDeploy (standalone; **not** a ProductRelease child): `ansible-actions -s proxysolr -n ${cluster} -a deploy` (X:1016-1020).
- `${cluster}` is picked in the UI from `getProxySolrClustersNames(account)` (`ActionArgsVisitorImpl.java:1618-1640`).
- Actions: `deploy, restart, start, stop, status, remove`.
- Only beta (7 clusters, tools-1/2/4/5/6/7/8) and stag (5 clusters, tools-1/2/4/5/6) use it; prod has none.

### 4.2 Inventory (`proxysolr.py`) and its crash behaviour
- Group = `<proxysolr><cluster @name>` (e.g. `midtierbeta-proxy-solr-2610`). Vars: every cluster attribute (`deploy_version`, `proxy_solr_port`, `proxy_solr_version`), plus `proxy_solr_cluster`.
- `zkHosts` = **every enabled top-level product with `<solr>` in the account**, as `{productId, zkHost: <solr zk string>#<source>}` (l.43-64). On `literatum` / `office-santaclara-cip` it is filtered to pre-prod / `incremental-features` / `migration-projects`.
- Hosts `<cluster>_<host>_<idx>`.
- **This module has no try/except around the product loop.** A product with no `enabled` attribute, no `<source>`, or a `<solr>` that the solr inventory drops (`KeyError` at l.41) crashes `inventory.py`. The wrapper then prints `Error [53] while running dynamic inventory.` for **every** proxysolr cluster.
- Because the proxy's inventory is built from all solr products, **one bad solr product anywhere in the account breaks ProxySolrDeploy**.

### 4.3 deploy.yml (4.1 = master)
1. Pull `id/proxy-solr:<proxy_solr_version>-production-d<deploy_version>` (e.g. `core-2610.0.11-production-d4.1`).
2. If the pull fails: lock (`~/apps64/ansible/proxy-solr/tmp/proxy-solr-<tag>.lock`, 300 s), then clone `id-core` @ `proxy_solr_version`, then mvn with Java 21 if the release number is >= 2610 (else 11), then `eclipse-temurin:<java>-jdk`, then push.
3. The handler `cleanup-directories.yml` removes the build dir **and the lock** (`notify` from create-paths plus `force_handlers`), so proxysolr does clean its lock on failure, unlike atm and searchservice.
4. `proxy-solr.props.xml` (the zkHost map).
5. `literatum.props.xml` comes from **literatum `master`** on GitHub (`git_branch: "master"`) whenever the release is >= 2410 or `master`; otherwise from SVN **trunk**. It is **never the product's branch**.
6. `props.files`, then an md5 of the dirs into env `PANOPTICON_CONFIG_MD5`.
7. `docker_container` `<cluster>-<proxy_solr_port>` (**no USER prefix**), `proxy_solr_port → 6565`, a 2 g heap, and a memory limit of **8g enforced** (`docker_container_memory: true`). It is restarted when any config file changed.
8. **There is no validate step at all.** `restart`, `start` and `status` do not validate either (their validate roles are commented out).

Callbacks: `profile_tasks` only (no Grafana, no Pushgateway).

### 4.4 Older branches
- 3.1 (adfca29) differs from 4.1 only by Java: fixed 11 and `openjdk:11-jdk`.
- 2.1 (e7a5d02):
  - clones **`id-proxy-solr`**, not id-core
  - Maven 3.8.8 downloaded every time
  - no `JAVA_HOME` export
  - `literatum.props.xml` **always from SVN trunk**
  - `openjdk:8-jdk`
  - jar paths `target/*.jar`
- 1.0 (c5832db):
  - Nexus `settings.xml` template (`<secret-bearing file roles/proxy-solr-deploy/templates/settings.xml.j2 on 1.0>`, not opened)
  - `docker_image path:` (the old module syntax)
  - Maven 3.3.9
  - `published_ports` built by string concatenation
  - Under Ansible 8.7.0 an **image build on 1.0 is likely to fail** at the `docker_image` parameters (inferred from module-syntax age, not tested). It works only while the image already exists in the registry.

### 4.5 Failure modes
- `Error [53]` (see 4.2). **The inventory traceback itself is not shown**: `dynamic_inventory()` pipes and discards inventory stderr (`ansible-actions.py:45-53`).
- A lock timeout, or `git clone` of an id-core tag that does not exist (`proxy_solr_version` typo in deployconf).
- An mvn failure because `~/apps64/java21` or `java11` is absent on the tools host.
- A GitHub raw 404 for `literatum/master/.../literatum.props.xml` (token).
- Docker `port is already allocated` if two clusters share a host:port.

### 4.6 Success-while-broken
- No health check, so a proxy that crash-loops (`restart_policy: always`) still reports `COMPLETED SUCCESS`.
- `zkHosts` covers only products that were enabled **at deploy time**. A newly enabled product is not routed until someone re-runs ProxySolrDeploy.
- The props come from literatum master regardless of the release line.

---

## 5. ansible-tools

### 5.1 Invocation
- The only Deploy Server use is **UpdateStatusPage**, option "Update Incident" (actions.xml:236-249):
  `ansible-actions -s tools -a status-page-incident -p ${product}-${family} -e component=$component -e status=$status -e "incident_message='$message'" [-e "eta='$eta'"]` + `ansibleCheckExitCode`.
- The other UpdateStatusPage options run `pingdomApi.sh` etc. in `/atypon/scratch/personal/shared/`, not Ansible.
- Wrapper: `-s tools` uses the **`product` inventory** (`ansible-actions.py:247-248`). There is no `-f`, so `-p` must be the exact group `<product lower>-<family>`.
- Version is always `master` (lifecycle fallback).
- Root actions: `status-page-incident`, `cleaner`, `getAccessLogs`, `k8s-prom-deploy-{atm,cassandra,consumer,gaia,kafka,lit,pug,redis,searchservice,solr,zk}`. `archived/*.yml` are not root-level, so they are not actions.

### 5.2 product inventory (`ansible-inventory/product.py`)
- Group `<p>-<f>`. Hosts `<p>-<f>_<machine>_<process>_<idx>` for every `<machine><process>` of the product, with `ansible_host = machine`, `service_type`, `host_rank` (backstage 1, backoffice 2, web 3), and `literatum_process_baseport`.
- `IPs` is read from `~/.litconfig/proxy-whitelist/{envs,products}.yml`.
- **On any exception it does `print e` to stdout** (l.114-116). That corrupts the JSON, so **every `-s tools` action fails with `Error [53]`**, and the wrapper hides the real error. A missing or invalid `proxy-whitelist/*.yml` on the tools host is the obvious trigger.

### 5.3 status-page-incident.yml
- `hosts: <p>-<f>`, `gather_facts: no`. `first_group_host = groups[group_names|first][0]`.
- The role runs `when: inventory_hostname == first_group_host`.
  - In the role line `{ role: …, when: inventory_hostname == first_group_host, product_name is defined and … status_page_enabled|default('true')|bool }` the comma ends the `when:` entry of the YAML flow mapping. So the **`status_page_enabled` / `product_name` / `family` checks are not applied**; they become a null-valued role parameter. This is inferred from YAML flow-mapping rules.
- The `uri` tasks are **not delegated**. In DC (`LOCAL_BASE` set, so no `-c local`) Ansible **SSHes to the product's first machine** and calls `https://<product>.status.atypon.com/api/v1/...` from there. Auth header: `<secret-bearing line at ansible-tools/roles/status-page/incident/defaults/main.yml:3-5>`.
- Sequence:
  1. `assertions.yml`: `component in ['Website','Backstage','Cloudflare']` (`component is not recognized`); `status in [detected, acknowledged, mitigating, fixed]` (`Incident status is not recognized`); GET `/components` accepting 200/500, then assert 200 (`No Components found for <p> or status page does not exist`).
  2. `get-component.yml` maps the component name to its id.
  3. `get-incident.yml` finds the last open incident (status != 4) for that component.
  4. `update-incident.yml` (PUT, expects 200) if one exists, else `open-incident.yml` (POST `/incidents`, expects 200).
- `ansible.cfg` here uses `inventory = inventory` (a directory). That merges `inventory/inventory.sh` (the product inventory) with the two static ini files (`amq_dr_replication: prod104`, `local: localhost`).

### 5.4 Failure modes
- `Error [53]` (the product.py `print`).
- `argument -n/-p/--name/--product: invalid choice: '<p>-<f>'`: the product is disabled, or its name has upper case (the group is lower-cased). **Exit 2.**
- `UNREACHABLE!` to the first product machine.
- The assertion messages above.
- `'current_component_mapping' is undefined`: the component name does not exist on that status page.
- `Status code was … and not [200]` on the POST/PUT.

### 5.5 Other tools content
- `k8s-prom-deploy-*`: creates or cleans up headless Service + Endpoints + ServiceMonitor objects in namespace `kube-monitor-dc`. These are meant to run through the docker/`inventory-ansible-docker/*.sh` path in the README, not through the wrapper. Run via the wrapper they would get the product inventory and lack `atm_port` etc.
- `cleaner.yml` + `roles/docker-cleaner` + `watcher.sh`: lists containers on inventory hosts and files LIT-BTD tickets for orphans.
- `getAccessLogs.yml`: greps resin access logs.
- The kubeconfig / SA files under `roles/k8s/bootstrap/files/` are secret-bearing and were not opened.

---

## 6. ansible-inventory: generation, use, and how host/group mismatches show up

**Generation.** `inventory.py <svc>` reads `~/.litconfig/deployconf.<acct>.xml` (from `-a` or `INVENTORY_ACCOUNT`), else `~/deployconf.xml`. It runs `expandvars` on the raw XML, parses it with minidom, and instantiates `<svc>.<svc>Inventory`. It prints JSON with top-level keys = Ansible groups and `_meta.hostvars`.

**Use.**
- The wrapper runs it **once** (`dynamic_inventory`) to build the argparse choices for name, family and limit.
- Then each repo's `ansible.cfg` → `inventory.sh` runs it **again** inside `ansible-playbook` (the whole account, no `--name`).
- Plays use `hosts: "{{ component_name }}"` = the group key.

**Naming conventions.** The deploy-log host name tells you which inventory you are in:

| Inventory | Group | Host name |
|---|---|---|
| atm / ingestion / searchservice | `<product>-<family>` | `<p>-<f>_<host>_<n>` |
| proxysolr | cluster name | `<cluster>_<host>_<n>` |
| product (tools) | `<p>-<f>` | `<p>-<f>_<machine>_<process>_<n>` |

**How a mismatch shows up in a deploy log:**

| Situation | Log text | Exit | Deploy Server |
|---|---|---|---|
| Product dropped by the inventory (exception swallowed: missing `kakfa_cluster_name`, no ATM models, no `<solr>`, bad kafka/zk ref) **and the command uses `-f`** (atm, ingestion, searchservice) | Python traceback ending in `KeyError: '<p>-<f>'` from `ansible-actions.py` (~l.302). `-f` choices are only restricted when some group has that `product_name`, so the name is built and then looked up. | 1 | `COMPLETED FAILURE` |
| Same, **without `-f`** (proxysolr `-n <cluster>`, tools `-p <p>-<f>`) | `ansible-actions.py: error: argument -n/-p/--name/--product: invalid choice: 'X' (choose from 'all', …)` | 2 | `COMPLETED FAILURE` |
| Group exists but the family differs | `argument -f/--family: invalid choice: 'B3' (choose from 'B2')` | 2 | failure |
| Inventory crashed (uncaught exception, stdout pollution) | `Error [53] while running dynamic inventory.` + `Please verify that you are using the latest version of inventory…` + a JSON `ValueError` message (e.g. `No JSON object could be decoded`). **The inventory's own stderr/traceback is discarded.** | 53 | failure |
| Group exists with **zero hosts** (e.g. `<searchservice>` or a proxysolr `<cluster>` without server children) | `PLAY [...]` → `skipping: no hosts matched` | **0** | **`COMPLETED SUCCESS` with nothing deployed** |
| Host in inventory but DNS/SSH broken | `fatal: [<host>]: UNREACHABLE! => … Failed to connect to the host via ssh: … Could not resolve hostname …` | 4 | failure |
| `-l <host>` differs in case from the deployconf host (e.g. prod `Wk-prod-atm1` vs `wk-prod-atm1`) | `argument -l/--limit: invalid choice` (the choices are exact `ansible_host` values) | 2 | (DS does not pass `-l` for these actions) |
| Deploy Server thinks the service is configured but the inventory disagrees (DS uses its own `DeployConfHelper`; `conf.getAtm/getIngestion/getSearchService` source is not in the cloned repos) | first row above | 1/2 | failure |

---

## 7. Failure-signature table

| Log text (substring) | Meaning | Likely cause | Next read-only check |
|---|---|---|---|
| `KeyError: '<p>-<f>'` traceback from ansible-actions.py | the inventory has no group for that product | the atm / ingestion / searchservice inventory dropped the product | run `python ~/apps64/ansible/inventory/inventory.py atm -j -n <p>-<f>` on the tools host (read-only); check deployconf for `<atm-server>`, `<consumer kakfa_cluster_name>`, `<atm><model>`, `<solr>`, kafka/zk cluster names |
| `argument -n/-p/--name/--product: invalid choice` | group name not in the inventory | disabled product, upper-case name, proxysolr cluster renamed | list groups: `inventory.py <svc> -j \| jq 'keys'` |
| `argument -f/--family: invalid choice` | wrong family | deployconf family changed | as above |
| `argument -a/--action: invalid choice` | no such playbook on that branch | wrong `deploy_version` (e.g. a proxysolr cluster `deploy_version` pointing at an old branch) | `git ls-tree origin/<branch>` for the service repo |
| `Error [53] while running dynamic inventory.` (proxysolr) | proxysolr.py crashed | a product without `enabled` or `<source>`, or a solr product dropped by solr.py | run `inventory.py proxysolr` and read its stderr; `inventory.py solr -j \| jq keys` vs deployconf products with `<solr>` |
| `Error [53] …` (tools) | product.py printed an exception | `~/.litconfig/proxy-whitelist/{envs,products}.yml` missing or invalid; malformed `<machine>/<process>` | `inventory.py product -j \| head` shows the printed error as the first line |
| `Error [51]` / `[52]` / `[54]` / `[55]` | wrapper git/lifecycle errors | see 03 §2.4 | — |
| `MSG  [Will use deploy_version: '8.0' …]` or `'9.0'` / `NO deploy_version is found …, will use the fallback` | informational: which ansible-atm/searchservice branch runs | lit-2610 → fallback 9.0 (atm) / 4.0 (searchservice) | confirm against the matrix in §0 |
| `'atmVersion=' not in gitVal.content` (or `ingestionVersion=`, `searchVersion=`) | versions.properties lacks the key or was not fetched | literatum branch name wrong or missing on GitHub, token, older branch | fetch `literatum/<lit_version>/atypon/literatum/versions.properties` (read-only) |
| `server_type == "invalid"` (atm) | application.properties call returned neither 200 nor 404 | GitHub token or rate limit; `atm-<v>` tag missing in id-atm | `gh api repos/atypon/id-atm/git/ref/tags/atm-<v>` |
| `Timeout when waiting for …/atm-<tag>.lock to be absent` (also `searchservice-…`, `proxy-solr-…`) | stale image-build lock | an earlier build failed or was killed (atm/searchservice have no rescue) | `ls -l ~/apps64/ansible/atm/tmp/` on the tools host: lock age vs the last deploy log |
| `Tag 'id-ingestion-service-<v>' does not exist in atypon/id-ingestion-service` | the release tag is missing | ingestion version bumped in versions.properties without a tag | `gh api repos/atypon/id-ingestion-service/git/ref/tags/id-ingestion-service-<v>` |
| `Failed to trigger GitHub Action workflow dispatch after 3 retries` | dispatch not 204 | token scope, workflow renamed | `gh workflow list -R atypon/id-ingestion-service` |
| 20 × `FAILED - RETRYING: Pull image with synchronized tag` then a docker_container pull error | the image never appeared | GH Action failed or is slow; wrong `-dmain` suffix | `gh run list -R atypon/id-ingestion-service -w workflow.yaml` |
| `FAILED - RETRYING: Get  status` → fatal (atm) | ATM not UP within 50 s | slow start (8g heap + models), Kafka/ZK/solr ZK wrong, missing models | `docker -H unix:///var/run/docker-<USER>.sock logs --tail 200 <USER>-<p>-<f>-atm-<port>` on the ATM host |
| `FAILED - RETRYING: Validate service is up` (ingestion) | `/configuration/serverTime` not answering | app start failure | same with `…-ingestion-<service_port>` |
| `FAILED - RETRYING: Validate HTTP port` (searchservice) | `/ping` has no `pong` | app start failure, redis/solr ZK | `docker logs …-searchservice-<http_port>` |
| stat task on `atm_across_publishers_model_dir` fails, or `Verify atm models directories exist` fails | model dirs missing on the ATM host | new host or publisher mount not provisioned | `ls -ld /shared/atm/atmdata/classification-model/atm_across_publishers_model/ ~/publisher/<p>/atmdata/classification-model/*` |
| `Thesaurus-synonyms folder '…' is missing!` | searchservice host lacks the publisher mount | new host | `ls -ld <publisher_home_path or /publisher/common>/journals/lucene/thesaurusSynonyms/en` |
| `consumer and searchservice share the same ports…` | socket collision (both default to srunport+3) | co-located consumer and searchservice | `inventory.py consumer -j -n <p>-<f> \| jq .[].vars.consumer_cluster` |
| `Failed to gather config file hierarchy with Exception` (searchservice hard fail; atm/ingestion ignored) | client props hierarchy download failed | missing include file, branch, token | the literatum branch's `atypon/product/<p>/conf/…` files |
| `component is not recognized` / `Incident status is not recognized` (tools) | bad UpdateStatusPage input | UI value outside the lists | — |
| `No Components found for <p> or status page does not exist` | status page API not 200 | product has no status page | `curl -sI https://<p>.status.atypon.com/api/v1/components` |
| `'current_component_mapping' is undefined` (tools) | component name not on that page | page components renamed | GET `/api/v1/components` |
| `UNREACHABLE!` on `<p>-<f>_<machine>_<proc>_1` (tools) | cannot SSH to the product's first machine | host down, or the key for that account | `ssh -o BatchMode=yes <machine> true` as the account |
| `skipping: no hosts matched` + `COMPLETED SUCCESS` | **false success** | empty group (no `*-server` children) | deployconf for `<searchservice-server>` / `<proxysolr-server>` |
| Pushgateway metric 1 while the log shows fatal | callback bug | `pushgateway.py` has no `v2_runner_on_failed` | trust the log, not Pushgateway |

---

## 8. Success-while-broken summary
1. Empty inventory group: rc 0 with no hosts (searchservice, proxysolr).
2. proxysolr has **no health check** in deploy, restart or start.
3. atm and ingestion ignore `grab_cfg_hierarchy` failures, so client props go missing silently.
4. ingestion `stop` is a no-op on a running container; `remove` keeps the data and ignores topic-cleanup errors.
5. ingestion `mount_root_dir` resolves to empty (`/atypon` mount), inferred.
6. tools `status_page_enabled` is never honoured (YAML flow-mapping comma).
7. proxysolr uses literatum **master** props for every release ≥ 2410; `zkHosts` is only refreshed on redeploy.
8. Pushgateway always shows success (atm, ingestion, searchservice).
9. The searchservice port-conflict check is silently skipped when the consumer inventory lacks the product.

---

## 9. Coverage statement

| Repo @ commit | Read fully | Diffed / skimmed / not opened |
|---|---|---|
| ansible-atm master 9aa04ff (= 9.0 a3d37dd, same tree) | all 40 playbooks, roles, templates, vars, cfg, lifecycle and scripts | `callback_plugins/*` + `library/grab_cfg_hierarchy*.py` diffed: identical to ansible-consumer (read in 03), except the debugger's example args. `roles/atm/files/warplda_binaries.tgz` is binary, not opened. |
| ansible-atm 8.0 e0127e0 | full `git diff` vs 9.0 (3 files) | — |
| ansible-ingestion main 24b39c6 | all 28 non-library files | `library/*` diffed: identical to consumer. `origin/master` 70805e8: only `atypon_lifecycle.json` read (what the wrapper uses). |
| ansible-searchservice master 00d600e (= 4.0) | all playbooks, roles, templates, vars; `base-jetty-image/*` (legacy, unused by the current Dockerfile) | callbacks identical to consumer; `grab_cfg_hierarchy.py` differs by one blank line. 3.0 d083d83 via full diff. |
| ansible-proxysolr master 4b648fc (= 4.1) | all 27 files | 3.1 / 2.1 full diffs; 1.0 diff read except the secret-bearing `settings.xml.j2` and credential lines. |
| ansible-tools master 750b441 | cfg, lifecycle, group_vars, README (filtered), `status-page-incident.yml` + the whole `status-page/incident` role, `slack-handler`, `cleaner.yml` + `docker-cleaner` (tasks, watcher.sh), `getAccessLogs` + roles, all inventory scripts, `k8s-prom-deploy-atm/lit.yml`, `k8s/bootstrap` main + atm + servicemonitor-atm, `k8s/cleanup`, `create-image` Dockerfile | the other 10 `k8s-prom-deploy-*.yml` grep-skimmed (hosts/roles/when); the other 11 bootstrap + 12 servicemonitor task files diffed against atm (same pattern, different port var); `k8s-prom-deploy-all*.sh` skimmed (docker run lines filtered); `test.json` (3,471 lines of sample inventory) sampled; `archived/` (39 files) listed only, not actions; `roles/k8s/bootstrap/files/*` (kubeconfigs, SA, example secret) **not opened** |
| ansible-inventory master 0e3ac30 | re-read for this note: `ansible-actions.py` (all), `inventory.py`, `core_product.py` l.44-228, `atm.py`, `ingestion.py`, `searchservice.py`, `proxysolr.py`, `product.py`, `solr.py`, `kafka.py`, `zookeeper.py` | `api.py` / `lit_service_manager.py` / `Jenkinsfile` / `lit-service/*.yml` skimmed for structure (they are not on the deploy path; fully covered in 03) |
| deployserver (for context) | `actions.xml` entries X:962-975, 1016-1020, 1216-1220, 1443-1447, 236-249, 2794-2798; `PreExecuteVisitor.java:2764-2800`; `ActionArgsVisitorImpl.java:1618-1640` | `DeployConfHelper` (`getAtm` etc.) is not in the cloned repos |
| deployconf | parsed midtierbeta, staging, literatum with `xml.etree`: products with atm / ingestion / searchservice, proxysolr clusters, kafka clusters, srunports, server types | secret-looking attributes skipped |

Secret-bearing locations (not reproduced):
- `ansible-atm/ansible.cfg:25,29`
- `ansible-atm/group_vars/all:32,69`
- `ansible-ingestion/ansible.cfg:26,30`
- `ansible-ingestion/group_vars/all:11,31`
- `ansible-ingestion/roles/deploy-cluster/tasks/{build-image,deploy}.yml` (header lines)
- `ansible-searchservice/ansible.cfg:25,29`
- `ansible-searchservice/group_vars/all:32,36`
- `ansible-proxysolr/group_vars/all:33,36`
- `ansible-tools/roles/status-page/incident/defaults/main.yml:3-5`
- `ansible-tools/roles/slack-handler/tasks/failure.yml:5`
- `ansible-tools/roles/k8s/bootstrap/files/*`
