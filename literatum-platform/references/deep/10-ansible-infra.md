# 10 — Ansible infra repos: zookeeper, kafka, elk, mssql, xse

Scope: `$LIT_REPOS/ansible-{zookeeper,kafka,elk,mssql,xse}` at the branch each env actually deploys.
Builds on `03-ansible.md` (wrapper flow, error codes [51]-[55], inventory internals). Read that first.
Date: 2026-09-25. All read-only (git fetch + `git archive` into the scratchpad; nothing run).

---

## 0. Which branch each env runs (resolved from deployconf, not assumed)

How `deploy_version` is picked (`ansible-inventory/ansible-actions.py:302-308`): if the inventory group has a `deploy_version` var that is not `auto|fallback|latest`, it is used as the branch. Otherwise `atypon_lifecycle.json` is fetched from the repo's **master** and matched against `lit_version`, falling back to the `fallback` row.

Where the var can come from for these services:
- zookeeper / kafka / elk (`CoreService`): every attribute of the `<zookeeper|kafka|elk><cluster …>` element becomes a group var (`zookeeper.py:55-56`, `kafka.py:62-63`, `elk.py:123-124`), plus `<ansible-common><arg/>`.
- mssql / xse (`CoreProduct`): only `<ansible-common>` args, plus (xse only) the attributes of the product's `<xse>` element (`xse.py:75-76`). Product attributes are not copied.

Parsed with `xml.etree` (attributes whose names look secret were skipped). deployconf clone: `ad1c87a` (main, 2026-09-25).

| Service | beta (midtierbeta) | stag (staging) | prod (literatum) | Branch source |
|---|---|---|---|---|
| zookeeper | `beta-zk-1/2/3`: `deploy_version=3.7.1` | `stag-zk-1`, `stag-zk-2`: **3.5.8**. `stag-zk-3`, `stag-zk-4`: 3.7.1 | 22 clusters on **3.7.1**, 12 on **3.5.8** (`literatum-zk-for-mms`, `literatum6-zk`, `literatum-zk-for-akka`, `literatum{2..7}-zk-for-akka`, `pnas-zk-for-akka`, `prod-zk-for-kafka`, `wk-zk-for-akka`) | cluster attribute |
| kafka | `beta-kafka-1` (8 brokers, zk `beta-zk-1`), no `deploy_version` | `stag-kafka-1` (8 brokers, zk `stag-zk-3`) | `prod-kafka-shared-2` (8 brokers, zk `prod-zk-for-kafka`) | lifecycle fallback → **10.0** |
| elk | `elk-cl01` (18 nodes) | `elk-cl01` + `elk-testing-cl01/02` (`elk_image_tag=6.5.4`) | `elk-cl01` | lifecycle fallback → **5.0** |
| mssql | 87 products; DB servers are real MSSQL hosts (`dsql4x` enabled) | 80 products (`dsql4x`) | 82 products (`tsql4x`, `vsql4x`) | lifecycle fallback → **2.0** |
| xse | **no `<xse>` in any enabled product** | none | none | (would be 2.0) |

- The unnamed legacy `<zookeeper><cluster zkversion="3.4.6">` (zk1/2/3-noprod) exists in all three files. It has no `name`, so the inventory skips it (`zookeeper.py:40-47`).
- `elk-cl01` is **the same cluster, same hosts and same ports** in all three deployconfs (elk01-06, tools-1..6, filebeat on elk04).
- `<xse>` appears only in `deployconf.ci.xml`. For beta/stag/prod every Xse* action is cancelled before it runs (section 5).

Branches read (fetched with `--depth 1`):

| Repo | Branch | Commit | Same as master? |
|---|---|---|---|
| ansible-zookeeper | 3.7.1 | `94d62aee46da` (2026-01-05, PR #67 LIT-654589) | master `fd0ece3` differs only in `.github/chainguard` and one exporter line (see 1.5) |
| ansible-zookeeper | 3.5.8 | `00c112526147` (2025-01-21, PR #63) | differs from 3.7.1 only as listed in 1.5 |
| ansible-kafka | 10.0 | `acefeb5b9314` (2026-05-04, PR #76 LIT-667838) | tree identical to master `7799c93` |
| ansible-elk | 5.0 | `dde959ed4204` (2026-07-22, LIT-675495) | master `7a30bcf` differs by one line in `roles/deploy-kibana/files/app/main.py` |
| ansible-mssql | 2.0 | `6db1a47a3131` (2026-09-16, PR #78 LIT-679454) | tree identical to master `9862e1f` |
| ansible-xse | 2.0 | `ef7acda19023` (2022-06-07, LIT-465606) | tree identical to master `36de7ae` |

---

## 1. ansible-zookeeper (3.7.1 and 3.5.8)

**Deploy Server actions**
- `ZkDeploy` (AccountLevel, `ansible="true"`) → `ansible-actions -s zookeeper -n $clusterName -a deploy` + AnsibleCheckExitCode (`deployserver/config/actions.xml:1811-1816`, `actions-config.xml:180`).
- No other DS action calls zookeeper. restart, stop, start, status and remove are CLI-only.

**Actions (top-level playbooks)**: deploy, deploy-exporter, restart, start, stop, status, remove, cleanup, create-image.

**Inventory**: group = cluster name. Hosts are `<cluster>_<host>_<myid>` with hostvars `myid`, optional `exporter_port` (host 1 only in deployconf) and `client_port`. Group vars are all cluster attributes plus `zk_cluster="h:p,h:p,h:p/"`.

**What it touches**
- Container `<cluster>_<client_port>` (e.g. `beta-zk-1_1498`), hostname `<host>-<cluster>`, image `…/docker-registry/id/atypon-zookeeper:<zookeeper_version>-d<deploy_version>`: `3.7.1-d3.7.1` or `3.5.8-d3.5.8` (`group_vars/all:21-26`).
- `network_mode: host`, so it binds `client_port`, `connect_port` and `election_port` directly (e.g. beta-zk-1: 1498/1499/1503). The AdminServer is off (`admin_port` is undefined).
- The container runs as `user: zookeeper` on 3.7.1, and as the **image default (root → gosu)** on 3.5.8 (the `user:` line is commented out).
- Volumes: `/local$HOME/servers/common/zookeepers/<cluster>/<host>_<client_port>/{data,datalog,zk_logs}`. Note the literal `/local` here; kafka uses `$LOCAL_BASE`.
- Heap 2g (`ZK_SERVER_HEAP`). `restart_policy: always`. 4lw whitelist `ruok,srvr,mntr,stat`.
- Exporter `<cluster>_exporter_<exporter_port>` (`dabealu/zookeeper-exporter:v0.1.9` on 3.7.1, `v0.1.2` on 3.5.8), published `exporter_port:exporter_port`, only on hosts that have `exporter_port`.
- Docker socket `unix:///var/run/docker-<USER>.sock` (DC).

**deploy.yml sequence**
1. Pre-task: fail if the group has an even number of hosts: `Please configure Zookeeper with an odd number of nodes. 1 (standalone), 3 or 5. Current length is N.` (`deploy.yml:14-18`).
2. Play "Deploy", serial 1, `max_fail_percentage: 0`, role `node-deploy`:
   1. create dirs (2777).
   2. `docker_image` pull `<image>:<tag>` (`docker-zk-deploy.yml:3-9`). **There is no build fallback.** A missing tag fails here, and the separate `create-image` action is not a DS action.
   3. `echo srvr | /bin/nc.traditional -w 3 <host> <client_port> | grep 'Zookeeper version'` with ignore_errors, to detect whether the node is part of a live cluster (l.12-16).
   4. `docker_container` with `ZOO_SERVERS="server.<myid>=<host>:<connect>:<election>;<client> …"`, `ZOO_STANDALONE_ENABLED` false when there is more than one server, and `recreate: false`. The module recreates only if the config or image differs (l.19-71).
   5. `echo ruok | nc` until `imok`, **30 × 5s** (l.73-79).
   6. Only if step 3 found a running node: `srvr` must contain `Zookeeper version`, 30 × 5s (l.82-90).
3. Play "Verify" on **localhost** (the controller), role `verify-cluster`. It concatenates `srvr` from every node with `nc.traditional`:
   - `grep -c -w follower` must equal N-1, **50 × 5s**.
   - `grep -c -w -E 'leader|standalone'` must equal 1, 50 × 5s (`roles/verify-cluster/tasks/main.yml:7-24`).
4. Play "Deploy Exporter" (not serial): exporter container. Then `GET http://<host>:<exporter_port>/metrics` must contain `zk_up`, 10 × 5s (`roles/zk-exporter/deploy/tasks/main.yml:33-41`).

**Other actions**
- restart: serial, `docker restart -t 60`. **No validation at all.**
- start: not serial. `docker start` only if `.State.Running` is false. No validation.
- stop: serial, `docker stop -t 60`.
- status: prints `State.Running`.
- remove: `vars_prompt force`. Removes the zk and exporter containers and `zk_base_path` (with a path guard).
- cleanup: `docker exec … bin/zkCleanup.sh -n 10` + `du`.
- create-image: builds `FROM zookeeper:<ver>` + log4j + entrypoint and pushes it.

All node actions start with `docker inspect … | grep -E 'true|false'`. A missing container gives grep rc 1, so the task fails with `non-zero return code` on "inspect container".

**Callbacks**: `profile_tasks`, `grafana_annotations`. The callback copy is identical to ansible-consumer's; it differs from ansible-solr's only by the missing `gcp-rehearsal` user. It posts to `grafana.devops.atypon.com` dashboard 172. The callback file itself was diffed, not re-read.

### 1.5 Branch differences
- 3.5.8 vs 3.7.1: `zookeeper_version`, the 3.7.1 entrypoint/Dockerfile (adds `ZOO_CFG_EXTRA` and `chmod -R a+rwx /conf /data /logs /datalog`), `user: zookeeper` (3.7.1 only), and the exporter tag and `-zk-list`.
- The exporter's `-zk-list` is `zk_cluster.replace('/','')` on 3.7.1 (correct: `h:p,h:p,h:p`). It is `.replace('/',',')` on 3.5.8 **and on master** (a trailing comma: `h:p,h:p,h:p,`).

### 1.6 Steps that can succeed while the service is broken
- `ruok` → `imok` only means the process is up, not that it is in quorum. On a **first** deploy (no node answered `srvr` before) the join check is skipped; the only quorum guard is the Verify play.
- `restart.yml` bounces every node back-to-back (serial, with no wait for rejoin). It can drop quorum for the dependent Solr/Kafka/Akka clients and still report `COMPLETED SUCCESS`. The same applies to `start`.
- The exporter check only looks for the metric name `zk_up`, which is present even when the value is 0.
- `myid` is written only if `/data/myid` does not exist (entrypoint l.65-68). Changing `myid` in deployconf for an existing host leaves the old id on disk.
- Inferred (not verified): moving a cluster from branch 3.5.8 (runs as root) to 3.7.1 (runs as `zookeeper`) reuses data files created by root. The entrypoint's `chown` only runs when started as root, so the new container may crash-loop on `Permission denied`.
- remove without `-e force=yes`: the prompt gets no answer, every task is skipped, rc 0 (same as `03` §2.5 item 10).

---

## 2. ansible-kafka (10.0 == master)

**Deploy Server actions**
- `KafkaClusterDeploy` (AccountLevel, opsOnly) → `ansible-actions -s kafka -n ${cluster} -a deploy` (`actions.xml:2769-2774`).
- `KafkaRestart` (AccountLevel) → `aa -s kafka -a restart -p $cluster` (`actions.xml:1532-1537`). It is also created as a child of **EnvironmentRebuild** when `args.restartKafka` is set (`PreExecuteVisitor.java:410-419`, args = `kafkaCluster`).

**Actions**: deploy, restart, start, stop, status, remove, create-image.

**Inventory**: group = kafka cluster name. Hosts are `<cluster>_<host>_<id>`. Vars: `kafka_cluster="h:p,…"`, `zk_cluster="<zk hosts>/<kafka cluster>"` (ZK chroot = cluster name), and all cluster attributes (`jmx_enabled=True`, `jmx_port`, `kafka_port`, `elk_cluster_name`, `zk_cluster_name`).

**What it touches**
- Container `<cluster>-<kafka_port>` (e.g. `beta-kafka-1-1331`), hostname `<host>-<cluster>`, image `…/id/kafka:2.13-2.7.0-d10.0` (wurstmeister 2.13-2.7.0 + jmx_prometheus_javaagent 0.18.0).
- Bridge network. Published `kafka_port:9092`, plus `jmx_port` and `jmx_exporter_port=jmx_port-1` because `jmx_enabled=True` (beta 1347/1346, prod 2009/2008).
- `KAFKA_ADVERTISED_HOST_NAME=<host>`, `ADVERTISED_PORT=kafka_port`, `ZOOKEEPER_CONNECT=zk_cluster`.
- Heap 4g, ulimit nofile 262144, CPU quota 10.
- Retention 72h, `auto.create.topics=False`, delete.topic.enable true, offsets and transaction-state RF 2.
- Volumes `$LOCAL_BASE$HOME/servers/common/kafka-clusters/<cluster>/<host>_<port>/{logs,data}`.
- No exporter in these envs: `kafka_exporter_port` is not set in any of the three deployconfs.

**deploy.yml sequence** (serial 1, `max_fail_percentage: 0`)
1. meta `pull-image`: pull `id/kafka:<tag>` (a missing tag fails; there is no build fallback). Then `docker_image_info` and parse `KAFKA_HOME` from the image Env.
2. Create dirs.
3. `docker_container` (recreate only on a diff, or with `-e recreate_container=yes`).
4. Validate: `docker exec … zookeeper-shell.sh <zk_cluster> <<< "ls /brokers/ids" | grep '^\[.*<id>.*\]'` until the id is in stdout, **20 × 5s** (`roles/node-deploy/tasks/docker-deploy.yml:70-81`).
5. Exporter container: skipped here.

**Other actions**
- restart: serial, `docker restart <container>` with **no `-t`**, so Docker's default 10s applies, not the 60s used elsewhere. **No validation.**
- start: not serial. `docker start` only if stopped.
- stop: serial, `docker stop -t 60`.
- status.
- remove: `vars_prompt`. Removes the containers and data dir. A run_once throw-away container runs `zookeeper-shell.sh <zk> deleteall /<cluster>` with `ignore_errors`.
- create-image.

### 2.1 Succeeds while broken
- **KafkaRestart**: brokers are restarted one after another with a 10s kill timeout (unclean shutdown, long log recovery) and no wait for ISR recovery. Partitions with RF 2 can go offline; the action still prints `COMPLETED SUCCESS`.
- **Deploy validation is weak**:
  - The broker's ZK znode is ephemeral and lingers for the ZK session timeout after the old broker dies, so a freshly recreated broker can "validate" before it has started.
  - The check is a substring match: id `1` matches `[10,…]`.
  - Nothing checks under-replicated partitions before the next broker is touched.
- start/stop/status: no health check.

---

## 3. ansible-elk (5.0 ≈ master)

**Deploy Server actions** (`actions.xml:1110-1135`, `actions-config.xml:337-343`)

| DS action | Command | Branch actually used |
|---|---|---|
| ElkFilebeatDeploy (any account, opsOnly) | `cd /na101/home/literatum/apps64/ansible/elk/latest && git pull && /usr/local/bin/ansible-playbook -i inventory.sh deploy-filebeat.yml -e component_name=$elkCluster 2>&1 > /dev/null` | **whatever the `latest` checkout is on**. It bypasses ansible-actions, the lifecycle and the venv. `2>&1 > /dev/null` sends ansible stdout to /dev/null, so the DS log shows only stderr |
| ElkKibanaBackup (literatum only) | same `cd …/latest && git pull && ansible-playbook backup-kibana.yml …` (`ansible-playbook` from PATH) | same |
| ElkLogstashDeploy (literatum only) | `ansible-actions -s elk -n $elkCluster -a deploy-logstash` | 5.0 |
| ElkRotateIndices (literatum only) | `ansible-actions -s elk -n $elkCluster -a rotate-indices` | 5.0 |

The `latest` checkout on the tools host cannot be checked from here. If `git pull` there fails (dirty tree, detached HEAD), the `&&` chain stops, `$?` is non-zero, and the log shows `COMPLETED FAILURE` with only the git error.

**Actions**: deploy-elastic, deploy-kibana, deploy-logstash, deploy-filebeat, backup-kibana, rotate-indices. There is **no** `deploy`, `start`, `stop`, `restart`, `status` or `remove`, so `-a deploy` gives argparse `invalid choice`.

**Inventory** (`elk.py`)
- Group = elk cluster. Hosts are `<cluster>_<host>_<type>_<idx>`, and plays select them by pattern `…:&~.*(_logstash_).*`, etc.
- Vars: `logstash_*_cluster`, `elastic_cluster`, `kibana_cluster`, and `filebeat_dict`, which holds **every top-level product with `<elk elk_cluster_name=…>`, including disabled ones**, as a list of machine/process names.
- Also `filebeat_{pugrenderer,kafka,redis,zookeeper,cassandra}_dict` for clusters with `elk_cluster_name`.
- An `<elk>` product missing `enabled` or `deployfamily` raises `KeyError` outside any try, so the traceback becomes `Error [53]` for every elk call.

**What it touches** (elk-cl01)
- elastic: `elk-cl01-elastic-<rest_port>`, image `docker.elastic.co/elasticsearch/elasticsearch:<elk_image_tag=6.2.2>` pulled from the internet.
  - Ports: coordinating node elk05 1358/1359; masters elk02-04 1358/1359; data nodes elk01-06 1360/1361.
  - Memory 2×heap. Heap 26g on data nodes, 4g on masters and coordinator.
  - `/…/servers/common/elk/elk-cl01/docker_elastic_<rest_port>/data`; snapshot repo `/shared/docker/backups/elk/elk-cl01`.
  - Zen discovery over the master list; `minimum_master_nodes = masters/2+1`.
  - Watermarks 80/84/90%. xpack security off.
- logstash: `elk-cl01-logstash-1310` on tools-1..6, image `…/devops/atypon-logstash:6.2.2`, ports 1310 (beats), 1311 (logspout tcp), heap 12g, pipelines in `…/docker_logstash_1310/pipeline`, auto-reload on.
  - Outputs go to the data nodes: `filebeat-<account>-YYYY.MM.dd`, `…-accesslogs-…`, `…-publication-events[-failed]-…`, and `logstash-*` for logspout.
- kibana: `elk-cl01-kibana-1312` on elk05, image `…/devops/atypon-kibana:6.2.2`, port 1312→5601, pointed at the coordinating node on the same host.
  - Optional proxy: `bitnami/oauth2-proxy:3.0.0` on `kibana_proxy_port` (1314), plus an http→https redirector on :80 when the proxy port is 443.
- filebeat: not a container. Writes `/na101/home/literatum/apps64/filebeat/prospectors.d/filebeat.<USER>.<product|cluster>.yml` (on the `filebeat`-type host, elk04). Then **`sudo systemctl restart filebeat.service` delegated to every product machine** whose prospector changed.
- curator: throw-away `bobrik/curator:5.4.0` on the coordinating node, running `curator_delete_indices.yml` (retention 15 days prod/nonprod).

**Sequences**
- deploy-elastic (serial per elastic host):
  1. `create-paths` (dirs, curator templates on the coordinator).
  2. `docker_container` started.
  3. `docker exec <c> grep -E '^#-Xm.1g' jvm.options` (**no `-H`**, ignore_errors). If that "fails": `docker kill -s SIGSTOP`, `sed` the jvm.options, then `docker_container` stopped, then started.
  4. validate = TCP `wait_for` on both ports, 120s.
- deploy-logstash: create-paths (pipeline templates) → container → TCP `wait_for` 1310/1311, 120s.
- deploy-kibana: container → `docker exec --user=root … echo sentinl settings >> kibana.yml` → optional proxy → `GET http(s)://host:<port>/status` accepts 200/403 with `body` and `html` in the content, 10 × 3s.
- deploy-filebeat (run_once): for each product, pugrenderer cluster and kafka cluster, build the prospector YAML and copy it; remove the file for disabled products; the handler restarts filebeat on the changed machines.
- backup-kibana: POST `.kibana/_search?size=1000` on the coordinator, then write `…/backups/elk/elk-cl01/kibana/kibana_<ts>.json`.
- rotate-indices: curator container (detach false; a non-zero exit fails the task).

### 3.1 Succeeds while broken / risks
- The elastic and logstash validations are **TCP port checks only**. A red cluster, split brain or broken ES output passes.
- The elastic deploy rolls nodes serially **with no cluster-health wait**. If the jvm.options check "fails", the node is also SIGSTOPped and restarted. Shards can go unassigned while the action reports success.
- The `docker exec` and `docker kill` in `roles/deploy-elastic/tasks/main.yml:15,23,27` have no `-H {{docker_url}}`. They reach the per-account daemon only if `DOCKER_HOST` is set in the account's environment. That is not visible in any repo here (same class as the Gaia issue in `03` §7 item 9).
- backup-kibana silently truncates at 1000 saved objects. There is no retention.
- ElkFilebeatDeploy hides ansible stdout (`> /dev/null`). The only failure evidence in the DS log is stderr plus `COMPLETED FAILURE`.
- elk-cl01 is shared by all accounts but containers are created on the `docker-<USER>.sock` daemon. A deploy-elastic/logstash/kibana from a non-literatum account would collide on ports (`port is already allocated`). The DS limits those actions to literatum; Filebeat is allowed from any account.
- Secret-bearing lines (not read): `roles/create-paths/defaults/main.yml:13` (New Relic key), `roles/deploy-kibana/defaults/main.yml:30-36` (oauth2 client/cookie), `group_vars/all:9,42,44`, `roles/create-paths/files/*.key|*.pem`.

---

## 4. ansible-mssql (2.0 == master)

**Deploy Server actions**
- `DbContainerRemove` → `ansible-actions -s mssql -p <p> -f <f> -a remove -e force=true` (`actions.xml:1790-1795`). It is `accountFilter="cip"` and `requiresDbDocker="true"` (`actions-config.xml:139`), created by `CreateActionMacro.java:545-552` in the CIP branch-switch chain. It is auto-cancelled with `DB Docker is not configured. Ignoring action` when the product has no docker DB (`DeployActionSql.java:391-395`).
- `ProductPatch` on a docker-DB product runs `ansible-actions -s mssql … start-patch-backup` (see `02` §ProductPatch).
- **Neither applies to beta/stag/prod.** Their products point at real MSSQL servers (`dsql4x`, `tsql4x`, `vsql4x`), and the mssql inventory would set `ansible_host` = the DB server IP. Treat any mssql run against these accounts as a misroute.

**Actions**: start, start-patch, start-patch-backup, start-patch-backup-remove, backup, daily-patch, remove, prepare-base-image, prepare-product-mssql, prepare-product-database-from-backup.

**Inventory**: one host per product `<p>-<f>_<dbserver with dots as _>`, `ansible_host=dbserver`. Vars are CoreProduct vars plus `database-server` extra attributes (dbname/dbuser/dbport…; the credential lines were not read).

**What it touches**
- Container `<p>-<f>-mssql-<product_version>` (`product_version` = `trunk` for HEAD/master, else lit_version without `lit-`), image `…/mssql:base-2022-CU18-ubuntu-22.04`.
- Named volume `mssql-<p>-<f>` → `/var/opt/mssql`. Port `dbport:1433`.
- Backups: Maven artifacts `com.atypon.literatum.backup:<p>-{mssql,publisher}:<ver>-SNAPSHOT` in GCP Artifact Registry `maven-snapshot`, downloaded to `~/mssql_docker_backups`.
- Publisher dir `~/publisher/<product_id>`.

**Sequences**
- start / container-start:
  1. meta `pull-artifact` (maven_artifact mssql + publisher).
  2. meta `remove-container`.
  3. Recreate the volume, untar the backup with a throw-away container, reset the publisher dir (it **prompts** if the product is not multi_family, unless `force=true`), then untar the publisher backup.
  4. `docker_container` recreate.
  5. `docker logs` until `Recovery is complete`, **24 × 20s**; then `sqlcmd … | grep master`, 5 × 5s.
- daily-patch:
  1. `select top 1 patchname from db_version` (before).
  2. `setprod <p> <f> && patch.py -p <p> --families=<f> --allowdropcolumn`; it must print `patch pool marker for 'jdbc' ends. All patches applied successfully.`
  3. The same query again (after).
  4. `update domain_info … cip.literatumonline.com`; the check requires the family in `HostName`.
- stop-and-backup (only if the latest patch changed): stop the container, tar the volume, tar the publisher dir, `./gradlew -b publishing.gradle publish`, delete the tmp tars.
- remove: remove the container, remove the volume, remove the publisher dir. **There is no prompt**; `force` is ignored.

### 4.1 Succeeds while broken / risks
- `roles/remove-container/tasks/main.yml`, `stop-and-backup/tasks/main.yml:2-7`, the `backup.yml` / `start-patch-backup.yml` post_tasks, and `prepare-directories.yml:9-12` (docker_volume) have **no `docker_host`**; the rest use `docker-<USER>.sock` (group_vars comment: `# FIX THIS`). Unless `DOCKER_HOST` is exported for the account:
  - remove deletes the publisher dir but leaves the container and volume;
  - "Stop container" acts on the default daemon, so the tar backup is taken of a **running** DB and then published;
  - the post-task start fails with `Cannot create container when image is not specified`.
- Backup publication happens only when the latest patch name changed. A failed backup step after a successful patch leaves the container stopped (in `backup.yml` the start is a separate post_task).

---

## 5. ansible-xse (2.0 == master, last change 2022)

**Deploy Server actions**: XseDeploy, XseRestart, XseBackup, XseRestore (`-e backup_name=`), XseRemove (`-e force=true`), XseCreateIndex (`-e validate_batch=`) → `ansible-actions -s xse -p <p> -f <f> -a <action>` (`actions.xml:920-960`). All are `requiresXse="true"` (`actions-config.xml:262-285`).
- XseDeploy is also added to ProductRelease when `conf.getXse(p,f)` is set (`PreExecuteVisitor.java:2791-2794`).
- Beta/stag/prod configure no `<xse>`. Every Xse* action is cancelled pre-insert with `Xse is not configured. Ignoring action` (`DeployActionSql.java:397-401`).
- A manual run gives argparse `invalid choice` for `-p` (no xse groups).

**Runtime**: xse is **not** in `VENV_PATHS`, so the system `ansible-playbook` runs it (version unknown). The code uses Ansible-2.x constructs: `|failed`/`|success` filters, `warn:` on `command`, `docker_image path:`. On a modern Ansible these fail at template or argument time: `no filter named 'failed'`, `Unsupported parameters … warn`.

**Actions**: deploy, restart, start, stop, status, remove, backup, restore, create-index, create-index-file, change-index-dir, create-image, monitoring.

**What it touches**
- Container `<USER>-<p>-<f>-xse-<xse_port>` (xse_port = srunport+5 or an attribute), image `…/cil/xse:<base_xse_version>-d<deploy_version>`.
  - `base_xse_version` comes from `atypon/xse-server` `atypon_lifecycle.json` via the GitHub API (`roles/atypon-lifecycle`). `deploy_version` defaults to `1.0` in group_vars; the wrapper passes `-e deploy_version=2.0`.
- Port `xse_port:8787`. Data `…/servers/<f>/<host>/docker_xse_<port>/{xse,log}`, backups `/shared/docker/backups/xse/<p>`. Publisher dir mounted read-only.
- create-index runs an indexer container on a random `lion101-110` / `qa31-39` host that is not an xse server.

**deploy**:
1. lifecycle lookup: `Atypon Lifecycle version is not found` if nothing matches.
2. create-paths: fails if the publisher dir is missing.
3. create-image on the first host: pull, or on failure build from the Nexus jar under a lock `~/apps64/ansible/xse/tmp/xse-<tag>.lock` with a 300s wait.
4. `docker_container`.
5. node-validate: `java -jar … --connect host:port --status` must contain `STATUS command finished in`, 5 × 5s. The rescue prints docker logs and fails with `The deployment has failed for node <host> at the node validation task`.

**Succeeds while broken**:
- restart has no `-t`.
- The image HEALTHCHECK only tests that `$PUBLISHER_DIR` exists.
- metrics-parser and newrelic-post ignore errors.
- remove uses `vars_prompt` (the DS passes `-e force=true`, so it runs).

---

## 6. Failure-signature table

| Log text (substring) | Meaning | Likely cause | Next read-only check |
|---|---|---|---|
| `Please configure Zookeeper with an odd number of nodes` | even ZK host count | deployconf `zk-server` list edited | count `zk-server` in `deployconf.<acct>.xml` for the cluster |
| `Error pulling image …/id/atypon-zookeeper:3.x.y-d3.x.y` / `manifest unknown` / `not found` on task `pull image` | ZK image tag never built/pushed | cluster moved to a new `deploy_version`; `create-image` (CLI only) not run | registry listing for `id/atypon-zookeeper`; the cluster's `deploy_version` attribute |
| `FAILED - RETRYING: validate_zookeeper (30 retries left)` then fail | node never answered `imok` | container crash-loop (permissions after the 3.5.8→3.7.1 user switch, bad ZOO_SERVERS, port in use) | `docker -H unix:///var/run/docker-<acct>.sock logs <cluster>_<client_port>` on the host |
| `validate zookeeper node joined the cluster` fail | node up but not serving (`srvr` shows no version) | not in quorum: peers down, election port blocked, myid mismatch | `echo srvr \| nc <host> <client_port>` on each peer |
| `validate_zookeeper_followers` / `validate_zookeeper_leader` retries exhausted (50 × 5s) | quorum shape wrong (followers != N-1 or leader != 1) | node down, split cluster, or `/bin/nc.traditional` missing on the **controller** (then every count is 0) | run `srvr` against each node; `ls /bin/nc.traditional` on the DS tools host |
| `Validate zk exporter` fails (`'zk_up' in validate_status.content`) | exporter not serving `/metrics` | exporter port conflict / image pull | `docker ps -a` for `<cluster>_exporter_<port>` |
| `inspect container` … `non-zero return code` (zk / kafka / xse) | container does not exist on that daemon | never deployed, removed, or wrong account socket | `docker -H …docker-<acct>.sock ps -a \| grep <name>` |
| kafka `pull image` fail for `id/kafka:2.13-2.7.0-d10.0` | image missing | new deploy_version or registry auth | registry listing |
| `FAILED - RETRYING: validate kafka (20 retries left)` then fail | broker id never appeared under `/<cluster>/brokers/ids` | broker crash (ZK chroot unreachable, disk, `port is already allocated`), wrong `zk_cluster_name` | `docker logs <cluster>-<kafka_port>`; `zookeeper-shell <zk>/<cluster> ls /brokers/ids` |
| `Bind for 0.0.0.0:<port> failed: port is already allocated` | host port clash | kafka_port/jmx ports reused, or a second account deploying the shared ELK | `ss -ltnp` on host (read-only) |
| `Error [53] while running dynamic inventory.` on `-s kafka` / `-s elk` | inventory traceback | kafka cluster missing `zk_cluster_name` or pointing at an unknown ZK cluster (`kafka.py:38,61`); `<elk>` product missing `enabled`/`deployfamily` (`elk.py:46-50`) | `python ~/apps64/ansible/inventory/inventory.py kafka` stderr |
| `argument -a/--action: invalid choice: 'deploy'` with `-s elk` | ELK has no deploy.yml | wrong action name | use `deploy-logstash` / `deploy-elastic` / … |
| ElkFilebeatDeploy log shows only a git error + `COMPLETED FAILURE` | `git pull` in `/na101/home/literatum/apps64/ansible/elk/latest` failed | dirty/detached checkout on the tools host | `git -C …/elk/latest status` (read-only) |
| `Timeout when waiting for <host>:1310` (or 1311 / 1358-1361) | logstash / ES port not open in 120s | pipeline config error, heap/OOM, image pull | `docker logs elk-cl01-logstash-1310` / `elk-cl01-elastic-<port>` |
| `Error: No such container: elk-cl01-elastic-…` or `Cannot connect to the Docker daemon at unix:///var/run/docker.sock` on `Pause Elastic container` | CLI hit the default daemon (no `-H`) | account env has no `DOCKER_HOST` | `echo $DOCKER_HOST` in the account's login env |
| `Validate kibana service is up` retries exhausted | `/status` not 200/403 with html | kibana cannot reach coordinator elk05:1359, proxy cert | `curl -s elk05:1312/status` |
| `sudo: a password is required` / `Unit filebeat.service not found` on `Reload filebeat.service` | handler restart failed on a product machine | host lacks sudo rule or filebeat | which machine appears in the handler item |
| curator container `status` != 0 on `Rotate elasticsearch data` | curator action failed | ES unreachable / index pattern | container output in the task result |
| `DB Docker is not configured. Ignoring action` (status Cancelled) | DbContainerRemove on a product without a docker DB | expected for non-CIP | none |
| `Recovery is complete` retries exhausted (24 × 20s) | MSSQL container did not finish startup | corrupt restored volume, backup artifact mismatch | `docker logs <p>-<f>-mssql-<ver>` |
| `grep_for not in daily_patch_result.stdout` on `Daily DB patch` | patch.py did not print the success marker | a failing patch | patch.py output in the task result (`stdout_callback=debug`) |
| `Cannot create container when image is not specified` on post-task `Start container` | start on the default daemon | missing `docker_host` (mssql) | same `DOCKER_HOST` check |
| `Xse is not configured. Ignoring action` | Xse* on a product without `<xse>` | expected on beta/stag/prod | none |
| `Atypon Lifecycle version is not found` | xse-server lifecycle lookup failed | GitHub API/auth or no matching row | none offline |
| `no filter named 'failed'` / `Unsupported parameters for (command) module: warn` | xse playbooks run on a new system Ansible | xse not in `VENV_PATHS`; Ansible-2.x syntax | `ansible-playbook --version` on the tools host |
| `The deployment has failed for node <host> at the node validation task` | xse `--status` did not answer | container crash / publisher dir missing | rescue output prints docker logs |
| (rc 0, nothing removed) after a remove on zk / kafka without `-e force=yes` | `vars_prompt` got an empty answer | non-interactive run | add `force` only after deciding; CLI only |

---

## 7. Coverage

Read fully, meaning every text file in the branch tree, printed through the secret filter:
- **zookeeper 3.7.1** (`94d62ae`): 51 files, all read except the `KEYS` PGP keyring (433 lines, skipped as data) and `callback_plugins/grafana_annotations{,.orig}.py`, which were diffed against the consumer and solr copies, not re-read.
- **zookeeper 3.5.8** (`00c1125`): diffed file by file against 3.7.1 (`diff -r`). Differences are listed in 1.5.
- **kafka 10.0** (`acefeb5`): all playbooks, roles, templates and group_vars, plus `files/2.13-2.7.0/{start-kafka.sh,log4j.properties}`, the version used. Skipped: older version dirs (`0.10.0.1`, `0.11.0.0`, `2.12-*`, `*_orig`), the jmx jar, `jmx_exporter.yml`.
- **elk 5.0** (`dde959e`): every playbook, role task, default, handler and meta file, `group_vars`, `filebeat.yml.j2`, `logstash-logspout.conf.j2`, `curator.yml.j2`, `curator_shrink_indices.yml.j2`, `filebeat.accesslog.yml`, `move_shards.sh`, `saved-search-report/report.{py,sh}`, kibana `app/main.py` + script + Dockerfile, the ci jenkins filebeat template.
  - Skimmed by grep: `logstash-filebeat.conf.j2` (349 lines; input/output/index lines), `curator_delete_indices.yml.j2`, `curator_remove_replicas.yml.j2`.
  - Not read: `request-template.json` (3546 lines), `saved-search-filters.json`, the logstash `.gem`, `templates/not_used/*`, the victorf filebeat templates, and `*.key` / `*.pem` / license json (secret-bearing).
- **mssql 2.0** (`6db1a47`): all playbooks, roles, templates, gradle publish files, readme, local inventories. Skipped: `library/xml.py` (vendored module, 494 lines), `gradlew*`, the wrapper jar, the `tini` binary. SQL command lines carrying credentials were filtered out.
- **xse 2.0** (`ef7acda`): all 83 files (credential lines filtered).

Supporting reads:
- `ansible-inventory` at `0e3ac30` (== origin/master): `zookeeper.py`, `kafka.py`, `elk.py`, `mssql.py`, `xse.py`, `core_service.py`, `core_product.py` (secret lines filtered), `ansible-actions.py:20-45,78-120,295-315`.
- `deployserver/config/actions.xml` (the xse, elk, kafka, mssql, zk and AnsibleCheckExitCode blocks), `actions-config.xml` (their attribute lines), `DeployActionSql.java:385-401`, `PreExecuteVisitor.java:395-420,2780-2796`, `CreateActionMacro.java:530-552`.

Not verifiable from here:
- whether `DOCKER_HOST` is set in DC account environments (it decides the no-`docker_host` issues in elk, mssql and gaia);
- which branch `/na101/home/literatum/apps64/ansible/elk/latest` is on;
- the system Ansible version used for xse.
