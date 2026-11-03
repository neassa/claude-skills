# 28 — Literatum search/indexing, REST API, persistence, backstage publish: post-deploy breakage and log signatures

Written 2026-09-25 from read-only code reading. Nothing was built, run, or fetched. Every repo file was read through `tools/safe_view.py` (it masks secret-like tokens, so some identifiers show as `Xx***`; where I resolved one by a targeted grep, the resolution is stated).

**Refs read:** Literatum `$LIT_REPOS/literatum-lit-2610` = `lit-2610` @ `9f8eb846e`. ansible-solr master `fc8dcc2`, ansible-consumer master `1629742`, platform-tools `b00c49f`, deployserver (local clone as in note 01), literatum-patch (local clone as in note 04), id-search/id-core (note 21 refs).
Paths are relative to `literatum-lit-2610/atypon/` unless prefixed: `AS/` = ansible-solr, `AC/` = ansible-consumer, `PT/` = platform-tools, `DS/` = deployserver, `LP/` = literatum-patch.
Not repeated here: note 12 §3 (Solr client, runtime search failures, Kafka producer), note 17 §2 (ingestion, workflow engines, stuck-after-deploy checklist), note 04 (patch system, entity read-only), note 03 §3.1/3.4 (ansible-solr / ansible-consumer playbook steps), note 21 §3 (id-search/id-core error texts).

> **Model gap: two repos are not cloned.** (1) **`atypon/solr-plugins`** owns the Solr schema/solrconfig generator (`com.atypon.id.solr.plugins.solr.server.conf.So***`, called from `AS/roles/set-image/tasks/create_profile_collections.yml:21-28`) and the profiles (`/src/main/resources/profiles`, `AS/roles/set-image/tasks/create-image.yml:142-196`). (2) **`atypon/id-index`** is the Kafka consumer app (`com.atypon.id.index.service.IndexService`, `AC/roles/consumer/templates/Dockerfile.j2:19`; cloned at build time from `git@github.com:atypon/id-index.git`, `AC/roles/consumer/tasks/create-image.yml:4`). So the actual `schema.xml` field lists and the consumer's error texts are **not verifiable here**.

---

## 1. Search and indexing

### 1.1 Which cores are really on (correction to the runtime reference)
- The runtime reference says "six Solr cores (JB, DO, DBPUBS, CTG, CONTENTSUPPRESSION, RELATED)". That set comes from docs, not the base config.
- **Base `search/collections/defaults/enabled`** (`literatum/conf/literatum.props.xml:18978-18995`) has 5 entries: `jb`, `ctg`, `contribautocomplete`, `titleautocomplete`, `topicautocomplete`. `custompage`, `caption`, `contentsuppression`, `dbpubs`, `institutionautocomplete`, `do`, `related` and `recommendations` are commented out ("enable as needed per product").
- The Kafka producer core list `index/kafka/cores` (`literatum.props.xml:13146-13163`) names 16 cores. `index/kafka/dependentCores` (`:13169-13182`) re-indexes `contribautocomplete`/`caption`/`affiliation` after `jb`, `titleautocomplete`/`publisher` after `ctg`, and `contribautocomplete` after `do`.
- ansible-solr creates whatever the product's props hierarchy enables: `EnabledCollectionsExtractor`, with a fallback to the ZK configsets (note 03 §3.1). Collections are named `<col>_<YYYYMMDDHHMM>` with alias `<col>`, and `SolrCoreModel.findByName` strips the suffix (note 21).
- **Next check:** the product's own `search/collections/defaults/enabled` overlay, compared with Solr `CLUSTERSTATUS` aliases.

### 1.2 Who owns schema and solrconfig, and how SolrDeploy ships them
- **Literatum ships no `schema.xml` or `solrconfig.xml`.** `find` over the tree finds only test data in `literatum/conf/solr/data/`.
- The configsets are **generated at Solr image build time** by solr-plugins, at the solr-plugins version that the id-search pom pins for `searchVersion`. lit-2610 pins `searchVersion=2610.0.25` (`literatum/versions.properties:136`) → solr-plugins 2610.0.16 (note 21).
- Build steps (`AS/roles/set-image/tasks/create-image.yml`):
  1. Download `solr-pom.xml` and `web.xml` from solr-plugins at that tag (`:25-67`).
  2. Download **`literatum.props.xml` from `atypon/literatum@<lit_version>`** (`:81-89`) and `search-server.props.xml` from solr-plugins (`:103-119`).
  3. Optionally fetch the client props hierarchy (`:123-136`).
  4. Download the profile files (`:142-196`), then for each profile run `java … -Doperation=a -Dproduct=<p> … So***` to write the collection definitions into `profiles/<profile>/<collection>/conf` (`create_profile_collections.yml:19-28`).
- **Image tag** = `<solr-plugins-ver>-d<deploy_version>`, or `<product_id>-<solr-plugins-ver>-d<deploy_version>` when `client_image` is set (`AS/group_vars/all:55`). The default is `client_image: False` (`AS/roles/set-image/defaults/main.yml:11`), so the image is **shared**.
  - The image is built only if the pull fails (`image-pull.yml:31-32`).
  - **Inferred risk:** the first product/branch to build a given tag bakes its own `lit_version` `literatum.props.xml` into the configsets that every other product on the same solr-plugins version and deploy_version then uses.
- **Shipping to Solr:** `bootstrap.yml:10-33` runs a throw-away container with `pre-solr-init.sh` and then `zkcli.sh -zkhost <zk> -cmd bootstrap -solrhome <bootstrap_folder>/`. This uploads the profile's configsets to ZK, retrying 10 times; the failure text is `ERROR: Bootstrap action failed` (`:52-54`).
  - `pre-solr-init.sh.j2:11-22,58-62` copies `solr.xml`, `custom_files` and `search-properties`. It patches `macro/product-name`, `acs-home-path`, `index/solr/zookeeper-connection` and the JB `maxWriteMBPerSec` into the props and into `jb/conf/solrconfig.xml`.
- **Reload:** `deploy.yml:36` runs `solr-commit-reload` with **`reload_collections: false`** (commit only).
  - A node is recreated only if one of these holds: its container is not running, it is not in `live_nodes`, `-e recreate=yes` was passed (`node-deploy/tasks/deploy.yml:95-123`), or the `docker_container` module decides the image changed (inferred from module behaviour).
  - **Consequence (inferred):** when the configset changes but the image tag does not, running cores keep the old schema in memory until a restart or RELOAD. When the tag does change, nodes restart one at a time, so for the length of the rolling window the replicas run mixed schemas.
- Standalone actions: DS `SolrRestart` = `ansible-actions -s solr … -a restart` (`DS/config/actions.xml:1343-1349`). `reload` / `commit-and-reload` exist as ansible actions (note 03).

### 1.3 Index sync (`index.sync`) and DigitalObjectReprocess
- `backstage.sh index.sync` → Ant target `index.sync` (`PT/conf/backstage.xml:1022-1026`) → **`com.atypon.publish.search.solr.index.reconciliation.IndexSyncingTool`**. The masked class value was resolved by grepping the class name, which hit line 1024.
  - `jb.sync` (`:1028`) is a different class. `SolrVerificationTool` is at `:900`.
  - It runs in a backstage-tool JVM (note 17 §4.1: `server.type=backstage`, the deployed classpath, and no DbConf).
- `IndexSyncingTool` (`publish/src/java/com/atypon/publish/search/solr/index/reconciliation/IndexSyncingTool.java`, read fully):
  - `main` → `LogConfiguration.configureLogging()`, `SpringAdapter.init()` (LIT-659152), then `Se***.loadAndRun(run)`, `ShutdownManager.shutdown()`, `System.exit(0)` (`:515-525`).
  - Options (`:67-161`):
    - `-c` core (mandatory; `SolrCoreModel.valueOf`, so a bad name → `IllegalArgumentException`)
    - `-f` calc m/e/s, `-s` sync m/e/s
    - `-a`/`-b` yyyyMMdd
    - `-o` report file, `-l` DOI list: must **not** exist, else `Provided path <p> cannot be used. File exists.`
    - `-i` input DOIs (forces missing-only)
    - `-n` max updates, `-t` pubType (JB only), `-r` area, `-w` website, `-x` flexclone-restore
  - Any `printError` prints `=======\nERROR\n=======\n<msg>. More info about the error could exist in the logs.` and calls **`System.exit(-1)`** (`:318-326`). Ant `failonerror` then prints `BUILD FAILED`.
  - Calculation errors log `Index syncing execution was stopped due to the following exception: …` (BACKSTAGE, `:314`).
  - The summary (`:494-507`) prints `AfterDate:`, `Number of Publications in DB:`, `… in Index:`, `… not indexed:`, `… in index files, but not in the db:`, `… with old xml:`, and then `Missing ratio: Missing ratio: <x>%`. The label is printed twice.
  - `-n` is honoured only when the index/delete "bypass limit" flags are true (`:438-445`, keys masked). The base caps are `index/loggers/max-updates=3000` and `batch-update-size=100` (`literatum.props.xml:13304-13308`).
  - Reindexing goes through `GeneralCoreDeltaIndexer` → `cmsUtilIndexV.indexDocument` (`…/reconciliation/index/GeneralCoreDeltaIndexer.java:25-36`). A failure there only logs `Couldn't schedule pub: <doi> for reindexing in core <c>` (WARN).
- **Scheduled variant:** `index/daily-tasks` = `JBSyncingTask` (`literatum.props.xml:13300-13302`). It runs as the `PeriodicIndexTasksScheduler` WF_SCHEDULE case (`publish/…/search/index/schedule/PeriodicIndexTasksScheduler.java:66-83`), so it needs the backstage SchedulerRobot and an exposed engine (note 17 §2.3).
  - `IndexSyncingTask.execute` (`…/periodical/IndexSyncingTask.java:53-68`) logs `Starting <task>`, `<task> finished` and `There was an exception, in task: <task>`. If `search/collections/defaults/indexing/enabled` is false it logs **`Indexing is disabled`** (only when Solr is enabled).
  - Reports go to `Solr.<core>.delta.report.*.log`. Unknown task class: `Failed to initialize <class>`.
- **DS `SolrIndexSync`** runs `backstage.sh index.sync -c jb -f mes -s mes -n 20000` and checks for `BUILD SUCCESSFUL` (`DS/config/actions.xml:1389-1395`).
  - **`-s mes` includes SYNC_EXTRA**, so this action **deletes** index documents that are not in the DB, and it also reindexes. It is not a report.
  - **Inferred risk:** run against a restored or partial DB, it removes live documents (up to the delete cap).
- **DS `DigitalObjectReprocess`** (`DS/…/SshExecuteVisitor.java:273-293`) runs `cd ~/scripts/reprocess; ./digital_object_reprocess.sh -p -f -t -s -o -i -a -b [-D]`. Script: `PT/reprocess/digital_object_reprocess.sh`, read fully.
  - Delta mode: `backstage.sh index.sync -c DO -f m -a <after> [-b] -o summary.log -l do.txt`. It greps `Missing ratio: ` and, if the value is `0.0%`, posts the summary to Jira and prints `No dois to reprocess.. Exiting` (`:56-73`). When the DB count is 0 the ratio is `NaN%`, so it continues.
  - Full mode: sqsh `select DOI from publication where PubAgentType='125' and path is not null`. The secret-bearing lines are at `digital_object_reprocess.sh:49` and `:52` (DB password on the command line).
  - Then `backstage.sh cli-reprocess … -I doi-list-from-file=do.txt` (queued as `Inplace_reprocess_<id>` submissions, `publish/…/backstage/cli/reprocess/CliReprocess.java:175`). The script loops on `backstage.sh check-reprocess` until `[PROCESSING] 0`, **with no timeout** (`:116-167`). The final step is `index.sync -c DO -a … -f m -o output.txt -l doisForReprocessing.txt` (`:177`).
  - DS success = a log line `No dois to reprocess.. Exiting` or `BUILD SUCCESSFUL`. Failure = `BUILD FAILED` or `Build failed, please check list_arguments.log for more info.` Anything else is rescheduled (`DS/…/SshExecutedVisitor.java:281-306`).
  - `printErrMsg` exits **0** (bare `exit`, `:29-33`), so `ERROR: …` / `Failed To Complete.` are not failure markers for the DS.
  - A second run with the same reprocess id fails at `[…/<id>/] already exists, re-run action with new reprocess Id!` (`:42`).
  - Timeout key `timeout.DigitalObjectReprocess` (`DS/config/deployserver.properties:119`; value masked).

### 1.4 IssuePipeline → Kafka handoff (confirmed, adds to note 17 §2.5)
- `publish/src/java/com/atypon/publish/backstage/IssuePipeline.java:1402-1431`:
  - Returns early unless the submission option `DoSearchIndexing` is set.
  - Logs `Creating intermediate xml for indexing.` and runs `IntermediateXmlUtility.generate`.
  - If `IndexingConf.INDEXING_ENABLED` (= `search/collections/defaults/indexing/enabled`, `IndexingConf.java:23`), calls `IndexingKafkaAPI.submit(xml, JB, flags)` and then **always** calls `IndexingStat.statFor(doi, area, submitDate, successDate)`. `successDate` stays null when `submit` throws.
  - Note 12 §3.4 says `submit` swallows producer errors. If so, `successDate` is set even when the message is later dropped (inferred).
- `INDEXING_STAT` is a clean example of the TableDef pattern (`publish/…/acs/metadata/IndexingStat.java`, read fully): columns `INDEXINGSTATID, DOI, AREA, LASTSUBMITTIME, LASTSUCCESSFULTIME`.
  - Save errors log `Failed to save/update indexing stat for doi/area: <doi>/<area>`.
- **Next check (read-only SQL):**
  - `SELECT TOP 50 DOI, AREA, LASTSUBMITTIME, LASTSUCCESSFULTIME FROM INDEXING_STAT ORDER BY LASTSUBMITTIME DESC;` (rows with a null or old `LASTSUCCESSFULTIME` = the submit threw)
  - `grep -E "Creating intermediate xml for indexing|Message (added to kafka cache|failed sent)" log/literatum.log* log/kafka/*`

### 1.5 Consumer side (ansible-consumer + id-index)
- **App:** `id-index` `IndexService` at `indexVersion` from Literatum `versions.properties` (lit-2610: `indexVersion=2610.0.15`, `literatum/versions.properties:68`). The image is `…/id/consumer:index-<v>-<profile>-d<deploy_version>` (note 03 §3.4).
- **Its registry** (`AC/roles/consumer/templates/consumer.props.xml.j2`, read fully) holds:
  - `macro/product-name`, `product-family`, `macro/redis/nodes`, `consumer/id`
  - `scheduler/{retries,time-threshold,retry-rate,pause-timeout}` (retry of Solr failures)
  - `kafka/zk/index-action-connection`, `kafka/config/{max-partition-fetch-bytes,max-poll-records,session-timeout-ms,auto-commit-interval-ms,max-listeners}`
  - `redis/{connection,retries,pool-size,timeout,maxRescheduleIndexedMessages,maxRescheduleDeleteMessages}`
  - `index/solr/{zookeeper-connection,enabled=true}`
  - optional `search/collections/defaults/enabled/related` when ATM models exist
  - plus the **Literatum props hierarchy at `lit_version`** (grab_cfg_hierarchy) and `literatum.kafka.props.xml` (per-collection `producer-job-factories` and `indexed-fields`, `literatum/conf/literatum.kafka.props.xml`, read fully).
  - So the consumer's field set comes from literatum@lit_version + id-index@indexVersion, while the Solr schema comes from solr-plugins@searchVersion. **These are three version sources, and nothing in the deploy checks that they agree.**
- Solr ZK for the consumer: `solrCloud.properties` `zkNodes=<solr_zk_connection>` (`AC/roles/consumer/templates/solrCloud.properties.j2`).
- **Paused consumers:** a Solr deploy pauses them (note 03). DS `ImmediateSolrBackup` and `SolrLockCleanup` explicitly run `ansible-actions -s consumer … -a unpause` (`DS/config/actions.xml:1737-1753`), and `ProductConsumerDeploy` = `-a deploy` (`:2100-2106`).
- **Next checks (read-only, on the consumer host):**
  - `docker -H unix:///var/run/docker-$USER.sock inspect -f '{{.State.Status}} paused={{.State.Paused}}' $USER-<product>-<family>-consumer-<port>`
  - `curl -s http://<host>:<port>/metrics/ping` (or `/kafkaConsumer/metrics/ping`, expect `pong`)
  - the container log under `/local$HOME/servers/<family>/<host>/docker_consumer_<port>/logs/`

### 1.6 What a schema mismatch after a Solr deploy looks like
These are Solr's own texts, not in any cloned repo, so they are **inferred** from standard Solr behaviour:

| Direction | Where it shows | Text |
|---|---|---|
| Consumer sends a field the new or old schema lacks | consumer (id-index) log; Solr `solr.log` | Solr 400 `ERROR: [doc=<id>] unknown field '<Field>'`. The consumer reschedules through Redis up to `redis/maxRescheduleIndexedMessages`, then drops it. Result: **silent index drift**, visible only in `index.sync` "not indexed". |
| Literatum queries or sorts on a field the schema lacks | `literatum.log` | Solr 400 `undefined field <Field>` / `sort param field can't be found: <Field>` (id-search changes.xml:6684 records the latter as a past "schema xml was not generated properly" bug). It is wrapped as `LitSolrClientException: Failed to operate on core:<CORE>, error-code:400` or a SolrException. SearchApi swallows it: `Unexpected error encountered while executing parametrized search task` → user sent to `errorReturnPage` (note 12 §3.3). |
| Field type changed (e.g. string→text) | same | `can not use FieldCache on a field which is neither indexed nor has doc values` / `cannot change DocValues type`; faceting or sort errors on specific pages only |
| Configset uploaded, cores not reloaded | nothing at deploy time | The old schema is still served until restart. The same query flips behaviour **per replica** during a rolling restart. |
| Wrong/empty ZK chroot after deploy | `literatum.log` | `<zk> is not a valid Zookeeper host…`, `LitSolrClientException: Error creating client for collection:…` (note 21) |
| Collection alias missing | `literatum.log` | `Collection not found` → `Reset Solr clients for all collections zkHost:` → `SolrOutdatedException` (note 21) |

**Next read-only checks:**
- `curl -s 'http://<solr>:<port>/solr/admin/collections?action=CLUSTERSTATUS&wt=json'`: aliases and replica state.
- `curl -s 'http://<solr>:<port>/solr/<col>/schema/fields/<Field>'`: does the field exist in the live schema?
- `curl -s 'http://<solr>:<port>/solr/admin/collections?action=COLSTATUS&collection=<col>'`: configset name.
- Solr image tag on each node: `docker -H … inspect -f '{{.Config.Image}}' $USER-<product_id>-solr-<port>`. Compare it with `solr-plugins` for `searchVersion`.

---

## 2. REST API

### 2.1 Request path
1. **URL → service:** the normalizer rule `"/rest/" [^\n]+` sets `serviceName = "apiRest"` and `path = <rest of URI>` (`literatum/src/java/com/atypon/literatum/customization/DefaultRequestParamsNormalizer.jflex:2512-2518`).
   - More specific rules: `/rest/classification/` → `cilRest` (`:2505-2511`). Connected-products and v2 access addresses → `connectedProducts`, each gated by its own `api/rest/handlers/…/enabled` flag inside the normalizer (`:892-923`, `:2132-2327`). So **a disabled connected-products handler does not even claim its URL**.
2. **Service registration:** `apiRest` is **commented out in base `services.props.xml:2096`**. Each product declares it: e.g. `product/aiaa/conf/aiaa.props.xml:543`, `achs.props.xml:2224`, `mag.props.xml:793` (attributes `enableSharedSessions`, `requireLogin=false`, `requireSecure=true`, `requireSession=false`, `enablePost`).
3. **Front controller:** `RestApiAction` (`publish/src/java/com/atypon/publish/api/rest/RestApiAction.java`, read 1-610 and 700-880 of 880).
   - `executeInternal` (`:101-340`) walks `path.split("/")` down the handler tree (`HandlerNode.getSubhandler`: an exact lower-cased name, then glob patterns, `:776-789`). Unmatched trailing segments become `extraPath`.
4. **Tree building:** `createHandlersTree` (`:520-593`) reads `Conf.getMap("api/rest/handlers")` **once**, when the Spring bean `RestApiService` is created (`literatum/src/java/com/atypon/literatum/spring/WebSpringConfig.java:36-39`, `@Profile("!patch")`, `RestApiService.java:12-14`).
   - Per node, keys `api/rest/handlers/<name>[/subhandlers/<name>…]/`:
     - `enabled` (**absent = true**, `:541`)
     - `class` (instantiated from Spring if a bean exists, else `newBean`)
     - `secure`, `oa***` (OAuth 2.0; name masked), `canUpdate`, `sk***` (skip cookie check), `allow-empty-post`, `allow-empty-put`, `validate-post-body`
   - Each flag is inherited from the parent when absent (`:559-582`). The root node has a null handler and `isSecure()` returns true when the handler is null (`:752-754`), so **top-level handlers default to secure=true**.
   - The base registry documents this layout in `literatum.props.xml:4781-4793`. Base handlers (e.g. `xpath`, `access`, `connectedProducts` and their subhandlers) are all `enabled=false` (`:4794-4900`). Default payload versions are under `api/rest/version/default/*` (`:3893-3920`) with `hobj` classes per version (`:3921-3990`).

### 2.2 Auth for REST (`RestApiAction.java:160-198`)
- **Session type `NORMAL`:** `LicenseReplyService.tryLicenses(context, new ServiceRequest("<serviceName>"))` → the user is the identity holding a **Service license for the `apiRest` service**.
- **Shared session** (`enableSharedSessions`): the caller's **IP** must resolve to an `IPRangeUser` holding a `LicenseReply.Yes` for that service (`:172-181`).
- If there is no user and the handler is secure → **HTTP 401 `Authentication Required to use REST API`** (error code `AUTHENTICATION`). There is no exception object, so **nothing is logged** (`ErrorResponse.logError` returns when `exception == null`, `ErrorResponse.java:118-129`).
- OAuth 2.0 (`isOAuth20Enabled`): `OAuth20Service.checkOAuth20Access` → 401 with the OAuth exception message.
- Writes: POST/PUT/DELETE run inside `Transaction.execute` unless `skipRestfulTransactions`. In **site read-only mode** they call `handlePostReadOnly` / `handlePutReadOnly` / `handleDeleteReadOnly` instead (`:233-298`).

### 2.3 How a missing or disabled handler shows up after a deploy
| Cause | Result | Log |
|---|---|---|
| Product props lack the `apiRest` service (or a new overlay dropped it) | `ActionController` throws `ServiceNotFoundException` (`literatum/src/java/com/atypon/literatum/action/ActionController.java:249-254`); it is an `AcsNotFoundException`, so error page | **WARN** `Service apiRest not found.\nReferring URL: …\nRequested URL: /rest/…` (`ServiceNotFoundException.java:12-16`, `ActionController.java:624-627`) |
| Service present but `enabled=false` | `ACSException("Service apiRest is disabled!")` (`:257-259`) | ERROR `Exception from action detected!` + stack (`:629-635`) |
| Top-level handler `enabled=false` or not defined | no subhandler matches → `handler == null` → `No handler for path: <path>` (`RestApiAction.java:156-158`, text `product/templates/jsp/messages.properties:8085`) → caught as Throwable → **HTTP 500** XML `<error error-code=…>` (stack included while `displayStackTrace=true`, `literatum.props.xml:4776`) | ERROR `exception occurred` + stack (`ErrorResponse.java:124`) |
| Subhandler disabled | the request **falls through to the parent handler** with the segment in `extraPath`, which often treats it as an ID → 404 `Object Not Found: ID supplied in the request does not correspond to an existing record.` or a handler-specific error | `exception occurred` |
| Handler `class` missing or renamed on the new branch | `reg.getClass("class")` throws during `RestApiService` construction → `Cannot initialize Spring` → **`KILLING THE SYSTEM`** on web and backstage (not the patch VM) | stderr banner (note 12 §2.1) |
| Handler enabled only through a DB `REGISTRYVALUE` override | **not applied**: the tree is built at Spring refresh, and `DbConf.start()` runs only after Spring (note 17 §5.3) — inferred from ordering | none; behaves as disabled until the value is in file-based props |
| Caller IP / service license missing after a DB refresh | 401 as above | none |

**Next read-only checks:**
- `curl -sk -o /dev/null -w '%{http_code}\n' https://<host>/rest/<handler>/…`, then read the body (the XML `<message>`).
- `grep -E "Service apiRest not found|No handler for path|Authentication Required to use REST API|exception occurred" log/literatum.log*`
- Compare `api/rest/handlers/<name>/enabled` and `class` in the deployed `WEB-INF/classes/*.props.xml` overlays (and `deployconf.props.xml`) between the old and new builds.
- Check that the product props still declare `<service name="apiRest" …>`.

---

## 3. Persistence

### 3.1 TableDef / AbstractEntity pattern
- **Hierarchy** (runtime ref): `AbstractDbBasic` → `AbstractDbEnhanced` → `AbstractEntity` (`literatum/src/java/com/atypon/literatum/persistence/AbstractEntity.java:30`, single `long` PK; `isPersistent` = id ≥ 0 when a sequence is defined, `:61-65`).
- **The row is a `TableDef` subclass**, for example `IndexingStat.IndexingStatRow` above:
  - Its static block calls `TableDef.define(TABLE, PK, SEQ)` and `defineRequiredCols`.
  - The entity constructor calls `register(TABLE, row)`.
  - `define` twice → `IllegalStateException("Table X is already defined.")` (`TableDef.java:521-524`).
- **Column map = Java fields.** `initColumnMap` (`TableDef.java:468-495`) maps **every non-static, non-final field whose name does not start with `_`** to a column named `field.toUpperCase()`. There is no annotation and no DB check.
  - So **adding a field to a row class is a schema change**, and it needs a matching DB patch in literatum-patch (`LP/mssql/literatum/litNNNNN.sql`, note 04).
- **SQL shape:**
  - Entity loads go through `Administrator.getSelectStatement(selectAllColumns=true)`, which **lists every mapped column explicitly** (`Administrator.java:104-150`).
  - Inserts go through `Executor.insert(table, table.getColumns())` (`AbstractDbBasic.java:371`).
  - Only the raw `Executor.select(…, columns=null)` defaults to `SELECT *` (`database/Executor.java:938-953`).
- **Row fill:** `TableDef.initFrom(rs)` (`:780-843`) reads the DB types from `ResultSetMetaData` once per table and caches them (`getDbColumnTypes`, `:739-760`).
  - A read that throws `SQLException` logs `Mismatch between table schema and TableDef object for column officially named '<COL>' on table '<T>' E179 …` (Lot.ACS, `:835-840`).
  - **Edge case (inferred):** if a `SELECT *` path returns a result set without a mapped column, `dbColumnTypes.get(col)` is null → `NullPointerException` at `TableDef.java:825`.
- **JPA path (newer code and PageBuilder):**
  - Persistence units `com.atypon.persistence.literatum` (`literatum/src/resources/META-INF/com/atypon/literatum/persistence.xml:7`) and `com.atypon.persistence.bridge` (`bridge/src/resources/META-INF/com/atypon/bridge/persistence.xml:7`).
  - Keys `jpa/dialect` (`org.hibernate.dialect.SQLServerDialect`), `jpa/show_sql` (`literatum.props.xml:26241-26244`). No `hbm2ddl` or validate setting was found in this tree, so schema mismatches surface **at query time**, not at startup (library defaults Unverified).
  - PageBuilder schema changes are Liquibase changesets inside the pagebuilder library, applied by DB patches. Examples: `--$pagebuilderConfig(liquibasePatch,PB_ADD_DROPZONE_ORDER)` in `LP/mssql/literatum/lit31595.sql:7-9` and `PB-LIT-574805` in `lit31745.sql:6`. They run through `PagebuilderConfigPatch.liquibasePatch` → `dbUpdater.runChangeset(id)` (`bridge/src/java/com/atypon/bridge/patch/PagebuilderConfigPatch.java:333-339`). Both patches carry a `--@boolean_property_parm` gate (value masked), so they are skipped for products where that property is false (note 04 §3.3).

### 3.2 Schema evolution vs DB patches: how a web node fails when a column is missing
- **Code ahead of DB** (the common post-deploy case: the build was deployed but the patch did not run or failed):
  - TableDef entities: MSSQL `com.microsoft.sqlserver.jdbc.SQLServerException: Invalid column name '<COL>'.` on the first load or insert of that entity.
  - JPA/PageBuilder: Hibernate `SQLGrammarException: could not extract ResultSet` caused by the same `Invalid column name 'PAGE_REMOVED'` / `'DROPZONE_ORDER'`.
  - If that entity is read during startup (PB page/dropzone loading, caches, robots), the error reaches `Cannot initialize Spring` → `KILLING THE SYSTEM`. HostWaitForWebServer then never gets `/heartbeat`. That is the LIT-666058 shape (note 14: lit31745 / lit31595 missing).
  - If it is read only on requests, the site comes up and only the pages that touch the entity fail (`Exception from action detected!` / `Error dispatching request` → 404).
  - Which bean reads the PB tables at startup was **not traced** (it lives in the pagebuilder library).
- **DB ahead of code** (a patch added a column, the old code is running): extra columns are ignored on select. Inserts fail only if the new column is `NOT NULL` without a default: `Cannot insert the value NULL into column '<COL>'` (inferred).
- **Next read-only checks:**
  - `SELECT TOP 20 * FROM DB_VERSION ORDER BY 1 DESC;` and look for the lit number that adds the column (`grep -l '<COL>\|<changeset id>' LP/mssql/literatum/*.sql` locally; for PB changesets grep the changeset id).
  - `SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME='<T>' AND COLUMN_NAME='<COL>';`
  - The DS PatchDB log for that patch (note 04 §4).

### 3.3 Connection pools and their keys
- Pool list `database/dbPoolName` = `jdbc` (must be first), `robot`, `common`, `logging` (`literatum.props.xml:6149-6155`). `database/reInitDbConnectionsPools` has the same list (`:6156-6161`). `related-training` is commented out.
- Other pool sets exist: `passport` (`:6202`; name resolved by grep), `logging` (`:6231`), `robot` (`:6260`, 3/20), `related-training` (`:6308`), `common` (`:6365`).
- Global: `database/dbPool/{expirationTime=30m, checkoutTimeout=30m, monitorInterval=60s}` (`:6139-6146`).
- Per pool `database/<pool>/`:
  - `dbDriver`, `dbUrl` (= `${macro/database/JDBCUrl}`), `dbUserPassword` (namepass, **secret-bearing lines at `literatum.props.xml:6180-6183`, `6208-6211`, `6237-6240`**)
  - `connMinNum` / `connMaxNum` (jdbc 5/200)
  - `caseSensitive`, `RDBMS` (= `${macro/database/type}`), `isolationLevel` (2), `connProxy` (= `${macro/database/Audit}`), `testTimeThreshold` (30s), `latestPatch`
  - Also `database/obfuscatedDbPool/*` (note 12).
- The pool implementation `ConnectionPool` comes from an external library (`persistence/datasource/LiteratumConnectionPoolProvider.java:14-15`), so pool-exhaustion texts are Unverified.
- Literatum-side texts (`DataSourceManager.java`):
  - `No database pools are defined` (:79), ``default pool name must be `jdbc` `` (:82)
  - `An exception occurred testing a connection` (:216), `Cannot register JDBC driver <d>` (:245, WARN)
  - `Pool <name> is not configured` (:359; after the Spring close, note 17 §5.2), `initialization of pool was cancelled` (:372)
- `DbConnMgr`: `[DbConnMgr.commit] Transaction bound to thread is rolling back` (:277,288), `[DbConnMgr.commit] Error in committing.` (:323), `[DbConnMgr.cleanupAndClose] Connection has an open transaction when released` (:449).
- Pool-usage lock: ServerHealthChecker `database-pool-health` at `max-database-pool-percentage=90` → heartbeat lock + email (note 12 §1.6).
- **Warning:** the `DB Pool Info` startup block prints the password (note 12).

### 3.4 Read-only site mode
- `ReadOnlySiteUtil` (`literatum/src/java/com/atypon/literatum/persistence/ReadOnlySiteUtil.java`, read fully):
  - Initial state = `acs/start-in-read-only-mode` (base false, `literatum.props.xml:2294`). Switching is allowed by `acs/enable-switching-read-only-mode` (true, `:2295`); when it is off, a switch throws `Switching Read-Only Mode is Disabled!` (`:46-51`).
  - `setSiteReadOnly` broadcasts `SiteReadOnlyEvent` to every JVM (`:53-61`, local sync listener `:27`). It is lost if broadcasting is disabled (note 12 §4.3).
  - Roles can bypass it: Super admin, Publisher super admin, PB designer/editor, when a bypass flag (masked) is true (`:85-105`).
  - `assertWriteAllowed()` throws `WriteDeniedError` (an **Error**) (`:68-76`). Static init failure logs `Error initializing ReadOnlySiteUtil` (`:31`).
- **Enforcement points:**
  - `ActionController:260-271` for services without `supportReadOnlySite="true"` → `Got WriteDeniedError when checking to see if read-only is enabled for <service>` + the `ERROR_READONLY_SITE` page.
  - REST writes → `handle*ReadOnly`.
  - Backstage robots are **not** blocked (note 17 §2.6).
- Read-only products use `*.props.IBM-ro.xml` / `*.props.IBM-ro-rehearsal.xml` overlays (e.g. `product/aaas/conf/aaas.props.IBM-ro.xml`). Gaia deploys are skipped for users `readonly`/`rorehearsal` (note 03 §5).
- Related keys: `…/enable-read-only-mode-access` (slot licenses in RO mode, `literatum.props.xml:1269`); `disable-read-only` (`:1226`, entity read-only for user license uploads).
- **Next check:** which props overlay the host loaded (`WEB-INF/props.files.<DEPLOY_HOST>`), and `grep "WriteDeniedError\|read-only" log/literatum.log*`.

---

## 4. Publish pipeline on backstage after a deploy

`atypon/publish` is a source root of `:literatum` (`literatum/build.gradle:115-137`), not its own deployable. What "publish" does on backstage after the JVM restarts:

| Step (after restart) | What runs | Can stall because | Signature | Read-only check |
|---|---|---|---|---|
| Robots start | `server/backstage/preload-robots` list (note 12 §2.2): BackstageEngine, EditorBackstageEngine, QServerForWorkflowRobot, InplaceReprocessEngine_1, ReasonerEngine, CategoryIndexerRobot, ContentSuppressionIndexRobot, LicenseCacheRobot … | cluster mutex / passport-cluster (note 17 §1.3, LIT-683431) | `KILLING THE SYSTEM`, `cannot upload type[..] version[..]` | `grep "robot exposed\|cannot upload type" log/cluster.log* log/workflow.log*` |
| Deposit pickup | QServer polls `backstage/incomingDir` every 2 min | mount missing, dir auto-created locally | `was received` absent; `cannot process file … 161` | note 17 §2.1 |
| Content processing | ProcessArticles v211 → IssueZipHandler → **IssuePipeline** | events suspended with backoff 10m→1d; IssueCreate mutex 30 min | `processing of event … failed`, `LOG_BACKSTAGE_ERROR` rows | note 17 §2.3-2.4 SQL |
| Indexing handoff | `IssuePipeline` → `IndexingKafkaAPI.submit` (§1.4) | brokers down, empty `index/kafka/brokerList`, consumers paused by a Solr deploy | `Message failed sent to kafka`, `NoClassDefFoundError …IndexingKafkaAPI` | `INDEXING_STAT`, consumer pause state |
| Make-live | MoveArticles / StartScheduledBackstage via `SchedulerRobot` (wf_schedule, 5 min) | no exposed WfRobot → no SchedulerRobot/ZombieKiller | `cannot process schedule entry N` | `SELECT * FROM WF_SCHEDULE …` (note 17 §2.5) |
| Daily JB index sync | `PeriodicIndexTasksScheduler` → `JBSyncingTask` (§1.3) | same scheduler dependency; `indexing/enabled=false` | `Indexing is disabled`, `There was an exception, in task:` | `ls` of `Solr.jb.delta.report.*.log` |
| DO reprocess (DS action) | `cli-reprocess` → `Inplace_reprocess_<id>` submissions on queues 20-39 | InplaceReprocessEngine not exposed → `[PROCESSING] N` never drops → **script loops with no limit** | DS action stays Executing/rescheduled | `backstage.sh check-reprocess -p <dir>` output; WF_EVENT group-by for queues 20-39 |

---

## 5. Failure-signature table

| Log text (substring) | Where | Meaning | Next read-only check | Status |
|---|---|---|---|---|
| `ERROR: Bootstrap action failed` | ansible-solr `bootstrap.yml:54` | zkcli config upload failed 10x | ZK `srvr`; image tag present | Confirmed |
| (no error) new configset, same image tag | SolrDeploy | cores not reloaded (`reload_collections: false`, `deploy.yml:36`) | Solr `schema/fields/<F>` vs expected | Inferred |
| `unknown field '<F>'` | consumer / solr.log | schema lacks a field the consumer sends | consumer log; `index.sync -f m` | Inferred (Solr text) |
| `undefined field <F>` / `sort param field can't be found` | literatum.log via `Failed to operate on core` | query/sort field missing in the schema | live schema API | Inferred |
| `Unexpected error encountered while executing parametrized search task` | literatum.log | search failed and was swallowed; user sees the search error page | preceding Solr cause | Confirmed (note 12) |
| `Indexing is disabled` | backstage literatum.log | `search/collections/defaults/indexing/enabled=false` (proxy-Solr envs) | effective props | Confirmed |
| `Index syncing execution was stopped due to the following exception:` | tool stdout + log | IndexSyncingTool calc error → exit -1 → `BUILD FAILED` | tool output above it | Confirmed |
| `Provided path <p> cannot be used. File exists.` | tool stdout | rerun into the same dir (`-o`/`-l`) | `ls` the reprocess dir | Confirmed |
| `Missing ratio: Missing ratio: <x>%` | tool stdout | normal summary (label printed twice); `0.0%` = nothing to do | — | Confirmed |
| `No dois to reprocess.. Exiting` | DO reprocess log | DS success marker | — | Confirmed |
| `ERROR: … Failed To Complete.` | DO reprocess log | script error but **exit 0**; DS reschedules, does not fail | `list_arguments.log` | Confirmed |
| `Couldn't schedule pub: <doi> for reindexing in core <c>` | backstage log (WARN) | delta reindex submission failed | Kafka producer lines | Confirmed |
| `Failed to save/update indexing stat for doi/area:` | literatum.log | INDEXING_STAT write failed | DB | Confirmed |
| WARN `Service apiRest not found.` | web literatum.log | product lacks the `apiRest` service | product props `<service name="apiRest">` | Confirmed |
| `Service apiRest is disabled!` | web literatum.log | service `enabled=false` | props | Confirmed |
| `No handler for path: <p>` + `exception occurred` (HTTP 500) | web literatum.log | top-level REST handler disabled or missing | `api/rest/handlers/<name>/enabled` | Confirmed |
| HTTP 401 `Authentication Required to use REST API` (no log) | response only | no service license for the session/IP; secure handler | caller IP vs IP-range users; service license | Confirmed |
| `Cannot initialize Spring` with root `ClassNotFoundException` under `RestApiAction.populateHandlers` | stderr → KILLING | REST handler `class` missing on this branch | props vs jar | Inferred (code path) |
| `Invalid column name '<COL>'` (SQLServerException / Hibernate `SQLGrammarException`) | startup stack (HostWaitForWebServer window) or request log | **DB not patched** for this build | `DB_VERSION`; `INFORMATION_SCHEMA.COLUMNS` | Confirmed (code + note 14) |
| `Mismatch between table schema and TableDef object for column officially named '<COL>' … E179` | Lot.ACS | type mismatch between the entity field and the DB column | column type in DB | Confirmed |
| `NullPointerException` at `TableDef.initFrom` (`TableDef.java:825`) | stack | `SELECT *` result lacks a mapped column | same as missing column | Inferred |
| `Cannot insert the value NULL into column '<COL>'` | stack | DB ahead of code (new NOT NULL column) | patch vs deployed build | Inferred |
| `Table <T> is already defined.` | stack | duplicate `TableDef.define` (two classes, same table) | — | Confirmed (code) |
| `Pool <name> is not configured` | any | DB used after Spring closed (note 17) | order of shutdown lines | Confirmed |
| `Got WriteDeniedError when checking to see if read-only is enabled for <svc>` | web log | site in read-only mode | loaded props overlay (`IBM-ro`) | Confirmed |
| `Switching Read-Only Mode is Disabled!` | stack | switch attempted with `acs/enable-switching-read-only-mode=false` | props | Confirmed |

---

## 6. Coverage

**Read fully:**
- `IndexSyncingTool.java` (526 lines)
- `IndexSyncingTask.java`, `DOSyncingTask.java`, `IndexerFactory.java`, `GeneralCoreDeltaIndexer.java`, `PeriodicIndexTasksScheduler.java` (89)
- `IndexingStat.java`, `ReadOnlySiteUtil.java` (141), `RestApiService.java`, `WebSpringConfig.java`, `ServiceNotFoundException.java`, `literatum.kafka.props.xml` (265)
- `PT/reprocess/digital_object_reprocess.sh` (284)
- `AS/deploy.yml`, `AS/roles/bootstrap/tasks/bootstrap.yml`, `AS/roles/set-image/tasks/{main,image-pull,create_profile_collections}.yml`, `AS/roles/set-image/templates/pre-solr-init.sh.j2`
- `AC/roles/consumer/templates/{consumer.props.xml,solrCloud.properties,props.files,Dockerfile}.j2`
- `LP/mssql/literatum/lit31595.sql`, `lit31745.sql`

**Read in part:**
- `RestApiAction.java` 1-610, 700-880 of 880
- `ActionController.java` 240-275, 600-680
- `ErrorResponse.java` 110-175
- `TableDef.java` 1-200, 445-530, 735-850 of 1877
- `Administrator.java` 100-150
- `Executor.java` 925-960
- `EntityQuery.java` 265-292
- `AbstractEntity.java` 1-80
- `DataSourceManager.java` / `DbConnMgr.java` (throw/log grep only)
- `IssuePipeline.java` 1395-1435
- `IndexingConf.java` 15-60
- `CliReprocess.java` (output grep)
- `PagebuilderConfigPatch.java` 330-360
- `DefaultRequestParamsNormalizer.jflex` 890-925, 2500-2525 (+ grep)
- `literatum.props.xml` 2286-2302, 3850-3990, 4760-4900, 6114-6240 (+ pool grep), 13130-13320, 18973-19030, 26225-26260, 26280-26300
- `services.props.xml` 2080-2110
- `AS/roles/set-image/tasks/create-image.yml` (step names), `AS/roles/node-deploy/tasks/deploy.yml` 90-141
- `DS/config/actions.xml` 1340-1400, 1735-1810, 2095-2115
- `DS/…/SshExecuteVisitor.java` 270-320, `SshExecutedVisitor.java` 278-340
- `PT/conf/backstage.xml` 1015-1040

**Not read:**
- solr-plugins (schema generator, profiles) and id-index (consumer), because neither is cloned
- the `IndexingKafkaAPI` jar and the pagebuilder library (PB entities, Liquibase changesets, which PB bean reads at startup)
- the external `ConnectionPool`
- `RestActionHandler` implementations and `OAuth20Service`
- the `IndexReconciliator` library
- the rest of the ~34k Java files

**Open items:**
1. Clone `atypon/solr-plugins` and `atypon/id-index` to confirm schema field lists and consumer error texts.
2. Which startup bean first reads the PB tables (turns `Invalid column name` into KILLING).
3. Whether `docker_container` recreates Solr on an image change in the pinned Ansible version.
4. Whether DB `REGISTRYVALUE` overrides for `api/rest/handlers/*` are ignored in practice.
