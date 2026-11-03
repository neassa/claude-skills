# 29 — solr-plugins and id-index: what is deployed, how schema and consumer are built, version compatibility, failure signatures

Written 2026-09-26 from read-only code reading. Nothing was built or run. Tags were fetched with `git fetch --depth 1` into the local clones, extracted with `git archive` into the session scratchpad, and read through `tools/safe_view.py` (masked identifiers show as `Xx***`). No secret values were read. Closes open item 1 of note 28 (repos now cloned).

Prefixes: `SP/` = solr-plugins @ `solr-plugins-2610.0.16` (`5423fe9`), `IX/` = id-index @ `index-2610.0.14` (`b5d7089`), `AS/` = ansible-solr branch `19.1` (`271d672`), `AC/` = ansible-consumer branch `10.0` (`f2a6e7d`), `IC/` = id-core. Java package prefixes `com/atypon/id/solr/plugins/` and `com/atypon/id/index/` are dropped.

---

## 1. What is actually deployed (from deployconf `main` `ad1c87a`, 2026-09-25)

Deployconf does **not** carry `searchVersion`/`indexVersion`. Chain:
- `lit_version` = path element `[-2]` of the product's `<source>` text (`ansible-inventory/core_product.py:129-131`), e.g. `$HOME/sourcegit/literatum-worktrees/lit-2610-maint-260804-334bb8be6fa2/atypon` → `lit-2610-maint-260804-334bb8be6fa2`.
- ansible-solr `search-version` role: `searchVersion=` from `raw.githubusercontent.com/atypon/literatum/<lit_version>/atypon/literatum/versions.properties` (`AS/roles/search-version/tasks/get_search_version.yml:6-47`) → id-search `pom.xml@search-<v>` → `<solr-plugins.version>` (`get_solr_plugins_version.yml:3-36`).
- ansible-consumer: `indexVersion=` from the same file → image `consumer:index-<v>-<profile>-d<dv>` (note 03 §3.4).
- Playbook branch (`deploy_version`): prod lit-2610 products pin `<solr deploy_version="19.1">` (58 products). Everything else uses the lifecycle matrix: solr `19.1:[2610]`, `18.3:[2410]`, `20.0:[master]`; consumer has no 2610 row, so lit-2610 → `10.0` (note 03).

Enabled products with a `<solr>` block, grouped by branch (python `xml.etree`, secret-like attributes skipped):

| Env | Branch (count) | searchVersion | solr-plugins | id-core (SP) | indexVersion | id-core (IX, via id-kafka-messaging) | Literatum `idKafkaMessaging` |
|---|---|---|---|---|---|---|---|
| literatum (prod) | lit-2610-maint-260804-334bb8 (53), marlin-mr0, maint-260707 | 2610.0.25 / .23 | **2610.0.16** / .14 | 2610.0.11 | **2610.0.14** | 2610.0.11 | 2610.0.11 |
| literatum | lit-2410-maint-260804-4f43c1 (14) + tandf/achs/pericles/aaas/lit-2410 | 2410.0.111 (.110 achs) | **2410.0.84** (.83) | 2410.0.44 | **2410.0.49** (.48 achs) | 2410.0.44 | 2410.0.45 |
| literatum | lit-2610-maint-260609-21d30c (1) | 2610.0.15 | 2610.0.9 | 2610.0.7 | 2610.0.9 | 2610.0.7 | 2610.0.7 |
| staging | lit-2610-maint-260901-13150c (63) | 2610.0.25 | 2610.0.16 | 2610.0.11 | 2610.0.14 | 2610.0.11 | 2610.0.11 |
| staging | lit-2410-maint-260901-0891f9 (7) + custom 2410 (5) | 2410.0.111 | 2410.0.84 | 2410.0.44 | 2410.0.49 | 2410.0.44 | 2410.0.45 |
| midtierbeta | lit-2610 (28) + lit-2610-marlin-mr1 | 2610.0.25 | 2610.0.16 | 2610.0.11 | **2610.0.15** | 2610.0.11 | 2610.0.11 |
| midtierbeta | lit-2610-acc / physio-pcms / maint-260707 | 2610.0.23 | 2610.0.14 | 2610.0.11 | 2610.0.14 | 2610.0.11 | — |
| midtierbeta | master (1, deploy_version 19.1) | 2710.0.5 | 2710.0.5 | 2710.0.5 | 2710.0.6 | 2710.0.5 | 2710.0.5 |

**Finding (Confirmed):** in every deployed combination, the id-core version behind the Solr schema (solr-plugins pom `id-core.version`) equals the id-core version behind the consumer (id-index → `kafka-messaging.version` → id-kafka-messaging pom `id-core.version`), and Literatum's producer (`idKafkaMessaging`) matches the consumer's kafka-messaging. The id-search/id-core/solr-plugins/id-index release trains are pinned together per Literatum line. A mismatch therefore needs someone to bump **one** of `searchVersion` / `indexVersion` / `idKafkaMessaging` in `versions.properties` without the others, or to deploy Solr and the consumer from different branches (§4).

Other observations:
- id-index 2610.0.14 → 2610.0.15 changes only `AffiliationIndexingPolicy.java` (1 line) and poms; solr-plugins 2610.0.14 → 2610.0.16 changes only query parsing (`PhraseQueryFactory`, `ResolveFieldSubscribersNodeProcessor`). Neither changes schema.
- The IndexFields enum is the same in id-core 2610.0.11 and 2710.0.5. id-core 2410.0.44 has **`EditionDescription`**, which 2610.0.11 no longer has. That is the concrete cross-major field drift (see §4).
- `lit-2410` solr-plugins builds against Solr **9.1.1** jars (`SP-2410.0.84/solr-pom.xml:24`), and ansible-solr 18.3 hard-codes base `solr:9.1.1` (`AS-18.3/roles/set-image/tasks/get-base-solr-image.yml:29`). 19.1/master hard-code `9.10.1`, which matches solr-plugins 2610/2710. That only works because the lifecycle keeps 2410 on 18.3. A lit-2410 product pinned to `deploy_version=19.1` would copy 9.1.1 `solr-core` jars into a 9.10.1 webapp (`Dockerfile.j2:51` `COPY lib/* …/WEB-INF/lib/`), giving mixed-version jars (Inferred). None is pinned that way today.

---

## 2. solr-plugins: how configsets are produced and packaged

### 2.1 Generator (read fully: `SolrServerConfigurator.java` 683 lines, `SolrStandaloneConfigurator.java` 216, `SchemaGenerator.java` 355)
- **Entry point:** `solr/server/conf/SolrStandaloneConfigurator.main`, run by `AS/roles/set-image/tasks/create_profile_collections.yml:19-28` with `-Doperation=a -Dproduct=<p> -DsolrPort=-1 -Dsearch.home.target=<profile dir> -DworkingDir=<cfg_dir>`.
  - Registry = `search-properties/props.files`. When `client_image` is false (the default), that file lists only `literatum.props.xml` (downloaded from `atypon/literatum@<lit_version>`), `search-server.props.xml` (from solr-plugins) and the profile XML (`create_profile_collections.yml:11-16`). So **product props overlays do not affect the configsets**. Only base Literatum props at the building branch do.
- **Cores:** `coresToDeploy = EnumSet.allOf(SolrCoreModel)` minus `NOT_AVAILABLE` (`SolrServerConfigurator.java:99-100`). A configset is generated for **every** core. Cores not enabled in base props get `disabled.core.properties`, and `create-image.yml:199-204` then renames them all to `core.properties`.
- **Schema per core** (`:286-312`):
  - If `templates/<core>/managed-schema` or `schema.xml` exists as a resource, it is copied. The premade cores are `campaigns, price, offer, discount, entitylinking, licensecache`.
  - A core that is not field-model-aware and has no template → `IllegalStateException("Core X requires a premade schema.xml file, and no such file exists at …")`.
  - Otherwise `SchemaGenerator` builds `schema.xml` from **id-core**: the core's `getFields()`, **plus all of `IndexFields.VALUES`**, plus `DynamicFieldPrototypes` for each concrete locale (the locales come from an enum, not from the registry), plus external-file fields (`SchemaGenerator.java:237-259`).
    - Only `DocKey` is `required=true` (`:158-162`).
    - Registry inputs are few: `search/similarity` (`SolrServerConfigurator.java:589-603`) and a query-analyzers list (`SchemaGenerator.java:37-40,294-311`).
  - **Consequence:** the field set is a pure function of the id-core version. Literatum props cannot add or remove schema fields.
- **solrconfig per core** (`:315-347`): generated by `ConfigXmlGenerator`. Registry-driven values:
  - autocommit / soft-commit / openSearcher per collection (`SolrConfHelper`)
  - `indexConfig` (`use-compound-file`, `ram-buffer-size-mb`, `merge-factor`, `segments-per-tier`, `pct-deleted-allowed`; `:415-433`)
  - page size, default field and return fields from search profiles (`:555-582`)
  - lib path `/opt/publisher/smart-expansions/`
- **Request handlers:**
  - `fields` and `select` on every generated core, with the Deduplication and SpellCheck components before Highlight.
  - Per-core additions (`:435-515`):
    - JB: `spell`, `prfselect`, IndexMetadata/IndexBloomFilter listeners, ContentSuppressionWarmupListener if contentsuppression is enabled in base props
    - DO: `autocompleteSelect`, `prfselect`
    - DBPUBS/CUSTOMPAGE: `prfselect`
    - CONTENTSUPPRESSION: its own `select`
    - CTG: `prfselect` + IndexMetadata
    - autocomplete handlers: contrib / title / topic / affiliation / institution / publisher
  - Error texts: `field X specified an analyzer Y that has no definition` (`SchemaGenerator.java:347`) and `Failed to generate <CORE>:schema.xml!` (`:290`).
- **Custom plugin inventory** (by source file names; implementations were not read):
  - ~82 `analysis/` classes: tokenizers `Doi/Isbn/Issn/PageString/AuthorString…TokenizerFactory`; filters `AtmSynonym`, `JapaneseSynonym`, `Lemmatization`, `TolerantEdgeNGram`, `YearConversion`, `SynonymGraphWrapper`, `UnicodeToAscii`, …
  - ~126 `query/` classes (LightQueryParser/QueryParserQpPlugin, query factories)
  - scoring similarities `BM25SimilarityCustomFactory`, `LogNormTFIDF`, `MultiField`, `PayloadNormalized`
  - components `PRFQueryComponent`, `DeduplicationQueryComponent`, `CustomTermVectorComponent`, `FieldsComponent`
  - handlers `AtyponCollectionsHandler`, `ClusterStateAwarePingRequestHandler`, `ExternalFiles*Handler`, `UploadFileHandler`, `PerformanceTrackerHandler`
  - update processors `AnalysisVersionUpdateProcessorFactory`, `AtomicUpdateUpdateProcessorFactory`
  - listeners `SolrServerConfigListener`, `Solr5InitListener`, `SolrSynonymsLoader`

### 2.2 Packaging into the image (cross-checked with `AS` 19.1)
1. `solr-pom.xml@solr-plugins-<v>` → `mvn dependency:copy-dependencies -Dsearch.version=<v>` into `lib/` (`create-image.yml:25-47`).
   - The jar is `com.atypon.id:solr-plugins:<v>-javax` plus solr-core/solrj/ltr/scripting at `lucene-solr.version` (`SP/solr-pom.xml:57-62,24,510-580`).
2. Profiles (`src/main/resources/profiles/*.xml`, 24 files) → one generator run per profile → `/opt/solr_bootstrap/profiles/<profile>/<core>/conf` (`Dockerfile.j2:57`).
3. `COPY lib/* /opt/solr/server/solr-webapp/webapp/WEB-INF/lib/`, then `web.xml` (from solr-plugins) (`Dockerfile.j2:51-52`). Base image `solr:9.10.1`, Temurin 21.
4. **`ENV literatum-branch={{ lit_version }}`** (`Dockerfile.j2:69`). The image records which branch's `literatum.props.xml` it baked. Tag = `<sp-ver>-d<dv>` (shared across products and maint branches).
5. At deploy: `zkcli bootstrap` uploads the product's profile configsets (note 28 §1.2). `collections_ensure` runs `EnabledCollectionsExtractor` inside the container against the **product** hierarchy at `lit_version` (`AS/roles/collections_ensure/tasks/main.yml:80-109`) and creates missing collections with `collection.configName=<core>` (`create_collection.yml:58-64`).
6. **Runtime:** Solr's `SolrServerConfigListener` reads the image's search conf and loads synonyms. On any exception it logs `Failed to initialize search.jar in Solr installation. Solr won't function properly.` and **continues** (`SP/solr/server/listeners/SolrServerConfigListener.java:58-60`; the same text is in `Solr5InitListener.java:37`, plus `Failed to properly load suggestion dictionary.` at `:46`).

### 2.3 Silent-fallback trap (Confirmed code)
`EnabledCollectionsExtractor.main` wraps everything in `catch(Exception e) {}` and always exits 0 (`SP/…/conf/EnabledCollectionsExtractor.java:21-32`). The ansible step also filters stdout to lowercase-only lines. If the extractor fails (bad props, classpath), the play falls back to **all configsets in ZK** (`main.yml:94-109`) and creates every core's collection. The deploy log gives no error. Check: the `Get enabled collections from registry` task output being empty.

---

## 3. id-index (consumer) at index-2610.0.14

### 3.1 Wiring (read fully: `KafkaConfiguration`, `MessageListener`, `ActionListener`, `MessageProcessorCms`, `MessageIndexer`, `MessageEraser`, `FailureHandler(Cms)`, recovery/*, repository/*, controllers, `ZkConnector`)
- Spring Boot `IndexService`. The registry is `props.files` under `registry.path` (`ApplicationProperties.java:90-119`): Literatum props hierarchy at `lit_version` + `literatum.kafka.props.xml` + `consumer.props.xml` (`AC/roles/consumer/tasks/deploy.yml:83-111`). If the registry load fails, the error is only logged (`:99-101`).
- **Topics** = `<product>-<family>-<topic>`, group `gr***-<topic>`, offset reset **`latest`** (`GenericDatasourceConfig.java:82-84`). Topics: `index_jb, index_do, index_dbpubs, index_related, index_recommendations, index_topic_ac, index_ctg, index_custom_page, index_content_suppression, change_enforcer, index_product_catalog, index_license_cache`, plus `index_receipt` (produced).
  - A listener auto-starts only if `search/collections/defaults/enabled/<core>` exists in the consumer registry (`GenericDatasourceConfig.java:23-79`). `change_enforcer` is always on.
  - Kafka brokers are discovered from the Kafka ZK `/brokers/ids`. Concurrency = number of topic partitions, capped by `max-listeners` (`KafkaConfiguration.java:221-224`, `ZkConnector.java:49-73`).
  - AC 10.0 defaults: `max_poll_records 50`, `session_timeout_ms 120000`, `max_reschedule_indexed_messages 150`, `scheduler_retries 3`, `retry_rate 20m`, `pause_timeout 5s` (`AC/roles/consumer/defaults/main.yml:25-43`).
- **Message:** Avro `KafkaMessage` (id-kafka-messaging) → JSON `IndexingActionMessage {core, zookeeperHost, content}` (`MessageProcessorCms.java:57-99`). The Solr target is the **ZK host inside the message**, i.e. the Literatum node's `index/solr/zookeeper-connection`, not the consumer's own ZK setting (`MessageIndexer.java:61-71` → `CoreIndexer`).
- **Document build** (`SolrCoreIndexer.java`, read fully):
  - `index()` first **deletes existing docs** by DOI/area key (`SolrCoreUpdater.deleteExistingDocuments`), then builds new docs (`:99-107`).
  - Fields = the producer-job-factory's `indexed-fields` from `literatum.kafka.props.xml` (per pubType producer) + ubiquitous fields, minus disabled fields (`:150-189`, `IndexDocProducer.java:88-165`).
  - **Field names unknown to id-core are skipped silently** (`IndexDocProducer.java:136-138`). A props/id-core mismatch on the consumer side never errors; the field just stops being indexed.
  - Adds `AnalysisVersion=<solr-plugins spec title>-<impl version>` to every doc (`:128-130`).
- **Solr client:** `index/solr/SolrClient` → id-core `LitSolrClient.indexSolrDocs` (`IC/id-solr/…/LitSolrClient.java:94-102`; unchanged between core-2610.0.11 and master).
  - A non-zero status gives `Failed to operate on core:<C>, error-code:<code>` (`:454-461`).
  - `version is not high enough` / `Document not found for update` → version exception (`:444-447`).
  - `Collection not found` / `Could not load collection from ZK` → `resetSolrJClients` + `SolrOutdatedException` (`:449-452`).

### 3.2 Retry, pause, discard (Confirmed code)
- Solr failure → `SolrRecoverableException` → `FailureHandlerCms.recoverFromFailure` → stored in Redis `<product>-<family>-<reschedule table>` with a counter. Log: `Message rescheduled Action:…, Core:…, key:…` (`FailureHandler.java:94-114`).
- Avro/JSON decode errors and unknown actions → `NoRecoverableException` → Redis `…-discard` + ERROR `Message discarded, key:…, trID:…, <err>` (`:116-122`, `DecodeUtils.java:26-70`).
  - This is the **DLQ equivalent: a Redis hash, not a Kafka topic**. The offset is committed either way (`handleOne` returns true, `:66-84`).
- A scheduler every `retry-rate / consumer-id` resends stored messages (log `Document resent for indexing, DocKey:…`). It runs only when `SolrConfHelper.ping()` succeeds, and behind a ZK `InterProcessMutex` (`MessageScheduler.java:56-68`, `DistributedLocker.java`).
  - After `scheduler/retries` attempts: `Document purged from Redis, DocKey:…, exceeded max number of retries` (`RecoveryProcessor.java:60-67`). **The document is then lost from the index until `index.sync`.**
- **App-level pause:** when the reschedule hash reaches `maxRescheduleIndexedMessages` (150) or the delete hash reaches 100000, the listener pauses its partition. Log `Pause for topic:…, partitions:…`. It spins `poll(0)`/sleep until the size ≤ half, then logs `Resume for topic:…` (`ActionListener.java:61-95`, `PauseValidator.java`). This is the in-app backpressure that produces **Kafka lag**.
- **Ansible pause** is different: `docker pause` of the whole container during Solr deploy/backup (note 03). Kafka session timeout is 120 s, so a pause longer than that expires the members, and the group rebalances on unpause (log `…: partitions revoked/assigned`). Inferred from Kafka semantics.
- **Silent loss path (Confirmed code):** in `indexNewDocuments`, an `IndexingException`/`NumberFormatException` while building docs is logged as `Failed to process document on core <C>` and **swallowed**. The existing docs were already deleted in step 1, so the message counts as success and the document **disappears** from the index (`SolrCoreIndexer.java:109-126`).
  - Triggers: `This field cannot be empty: <F>`, `<F> field cannot have more than one value …`, `Could not retrieve enabled fields for core "<c>"`, `Could not retrieve collection for core: <C>` (`IndexCollectionManager.java:69-77`).
- When a Solr doc update fails, `MessageIndexer` logs `Message processing failed` with trID/version/stack. A version conflict is downgraded to INFO `Message already processed, type:…` (`MessageIndexer.java:79-92`).
- `IndexCollectionManager.load` logs and skips any collection whose registry entry fails to construct (`:37-42`). Later messages for that core then hit `Could not retrieve collection for core:` (see the silent-loss path above).

### 3.3 Health
- **Ansible validate hits `/metrics/ping`** (`AC/roles/validate/tasks/validate.yml:4`). That path is the Dropwizard `AdminServlet` mounted at `/metrics/*` (`IX/…/configuration/metrics/MetricsServletContextListener.java:38-41`), whose ping returns `pong` whenever the web container is up (standard Dropwizard behaviour, Inferred).
- The **real** check is `GET /ping` (`HealthController.java:54-64`), which returns `pong` only if `SolrConfHelper.ping()` **and** Redis succeed, else `Service not ready`.
- So **ProductConsumerDeploy can pass with Solr or Redis unreachable**.
- Other endpoints:
  - `/actuator/health` (Solr/Redis indicators)
  - `/metric/values` (rescheduled indexed/delete sizes, stopped-consumer count, assigned partitions)
  - `/metric/discarded`, `/metric/rescheduled_indexed/<core>`
  - `/scheduler/solr_rescheduled_indexed` (triggers recovery: **state-changing, do not call**)
  - `/debug/reset/rescheduled_delete` (**destructive**)
- `Consumer stopped:<src>, count:N` (ERROR) on a Spring `ConsumerStoppedEvent` (`ServiceStatus.java:38-41`).
- Log file: `logs/kafka-consumer-sb.log`, 10 MB × 10 (`logback.xml:13-27`). The `org.apache.solr` logger is **OFF** and `org.apache.kafka.clients` is ERROR, so Solr's own 400 text shows only inside the wrapped exception or stack.
- Per-message INFO: `Message processed, size:…, key:…, trID:…, topic:…, partition:…, offset:… in …`.

---

## 4. Version compatibility: what breaks and where it shows

Three version sources feed one index. None of them is checked against the others at deploy time:
- (a) the **Solr schema/solrconfig/plugins** come from solr-plugins → id-core (via `searchVersion`)
- (b) the **documents** come from id-index → id-kafka-messaging → id-core (via `indexVersion`), shaped by `literatum.kafka.props.xml` + the product props at the consumer's `lit_version`
- (c) the **messages and queries** come from Literatum (`idKafkaMessaging`, id-search at `searchVersion`)

| Mismatch | Deploy Server (SolrDeploy / ProductConsumerDeploy) | Runtime |
|---|---|---|
| id-core in id-index newer than in solr-plugins (new IndexField) | nothing: both pass `COMPLETED SUCCESS` | Solr 400 `ERROR: [doc=…] unknown field '<F>'` → consumer `Failed to operate on core:JB, error-code:BAD_REQUEST` or a stack in `Message processing failed` → rescheduled ×3 → `Document purged from Redis …` → **silent index drift** (Inferred Solr text; retry path Confirmed) |
| id-core in solr-plugins newer (field dropped, e.g. `EditionDescription` 2410→2610) | nothing | same `unknown field` for the dropped field if the consumer still sends it; Literatum queries on it fail `undefined field` (note 28 §1.6) |
| Field type/analyzer changed between versions | nothing; the new configset is uploaded but **not reloaded** (`reload_collections: false`, `AS-19.1/deploy.yml:36`) | old schema served until the container restarts; after restart, sort/facet errors `cannot change DocValues type` or `can not use FieldCache …` until reindex (Inferred) |
| Plugin class renamed/removed in solr-plugins vs configset in ZK | SolrDeploy fails in `node-validate` (`FAILED - RETRYING: Ensure node is alive and all cores are active (1440 …)`, 2 h) because cores fail to load | `solr.log`: `SolrResourceLoader … Error loading class '<cls>'` / `ClassNotFoundException`, core init failure `SolrCoreInitializationException` (Inferred, standard Solr); `Failed to initialize search.jar in Solr installation. Solr won't function properly.` (Confirmed code) |
| Solr jar major mismatch (2410 plugins on the 19.1/9.10.1 base) | image build passes; nodes may not start → node-validate timeout | `NoSuchMethodError` / `NoClassDefFoundError` in `solr.log` (Inferred) |
| `idKafkaMessaging` (Literatum) ≠ consumer kafka-messaging (Avro schema / ActionType) | nothing | consumer ERROR `Message discarded, key:…, trID:…` (Avro) or `Not recognized actionType: X, trID: Y` → Redis discard, offset committed (Confirmed code) |
| Core enabled in consumer props but no Solr collection (Solr deployed from an older branch, or the extractor fell back) | nothing at ProductConsumerDeploy (`/metrics/ping` is always pong) | `Collection not found` → `Reset Solr clients for all collections zkHost:` → `SolrOutdatedException` → reschedule → at 150 the partition pauses (`Pause for topic:`), **Kafka lag grows** (Confirmed code path) |
| Collection exists but core disabled in consumer props | nothing; the listener is not started (`autoStartup=false`) | messages pile up in `<p>-<f>-index_<core>`. With offset reset `latest`, enabling the listener later **skips the backlog** if the group had no committed offset (Confirmed config + Kafka semantics) |
| `literatum.kafka.props.xml` names a field this id-core lacks | nothing | field silently not indexed (`IndexDocProducer.java:136-138`) |
| Shared image baked from another branch's `literatum.props.xml` | nothing; tag `<sp>-d<dv>` is reused | solrconfig commit/cache/profile values and similarity come from the first builder's branch; check `docker inspect … literatum-branch` |

---

## 5. Failure-signature table

| Log text (substring) | Where | Meaning | Next read-only check | Status |
|---|---|---|---|---|
| `Solr profile <p> not found. Available profiles are …` | SolrDeploy log | deployconf `solr_profile` missing at this solr-plugins tag | `ls SP/src/main/resources/profiles` at the resolved tag | Confirmed (`verify_profile_in_solr_plugins_version.yml:20`) |
| `Core <C> requires a premade schema.xml file, and no such file exists at …` | SolrDeploy (image build, java) | template missing for a non-field-model core | `git ls-tree` of `templates/<core>/` at the tag | Confirmed (`SolrServerConfigurator.java:304`) |
| `field <F> specified an analyzer <A> that has no definition` / `Failed to generate <C>:schema.xml!` | SolrDeploy (image build) | id-core field references an analyzer absent from `analyzerDefs` | compare id-core `AnalyzerType` vs `analyzerDefs-NoNgram.xml` at both tags | Confirmed (`SchemaGenerator.java:290,347`) |
| empty output of `Get enabled collections from registry` | SolrDeploy | extractor swallowed an exception → all ZK configsets used | Solr `CLUSTERSTATUS` collection list vs product `search/collections/defaults/enabled` | Confirmed (`EnabledCollectionsExtractor.java:30`) |
| `Failed to initialize search.jar in Solr installation. Solr won't function properly.` | `solr.log` | Solr-side plugin config/synonyms load failed; Solr keeps running | lines after it in `solr.log`; image `literatum-branch` env | Confirmed (code) |
| `Error loading class` / `ClassNotFoundException` / `SolrCoreInitializationException` | `solr.log`; SolrDeploy stalls in node-validate | plugin class in the configset not in the image jar | `docker inspect` image tag vs expected `<sp>-d<dv>`; `unzip -l` of the solr-plugins jar in the container | Inferred (Solr text) |
| `ERROR: [doc=…] unknown field '<F>'` | `solr.log`; consumer stack under `Message processing failed` | schema id-core older than consumer id-core | `curl …/solr/<core>/schema/fields/<F>`; compare `id-core.version` in both poms | Inferred (Solr text) |
| `Failed to operate on core:<C>, error-code:<code>` | consumer log | Solr returned non-zero status | `solr.log` at the same timestamp | Confirmed (`LitSolrClient.java:458`) |
| `Message rescheduled Action:<A>, Core:<C>, key:<k>, <err>` | consumer log | Solr write failed; stored in Redis for retry | `/metric/values` (rescheduled size) | Confirmed (`FailureHandler.java:101`) |
| `Could not reprocess document, DocKey:… pending for rescheduling` | consumer log | retry failed again | same | Confirmed (`RecoveryProcessor.java:50`) |
| `Document purged from Redis, DocKey:…, exceeded max number of retries` | consumer log | **message dropped after `scheduler/retries`**; index drift | `backstage.sh index.sync -c <core> -f m` report (report-only, no `-s`) | Confirmed (`RecoveryProcessor.java:63`) |
| `Message discarded, key:…, trID:…` | consumer log (ERROR) | non-recoverable: Avro/JSON decode or unknown action; stored in Redis discard hash | `/metric/discarded`; compare `idKafkaMessaging` vs consumer kafka-messaging | Confirmed (`FailureHandler.java:120`) |
| `Not recognized actionType: <T>, trID: <id>` | inside the discard message | producer newer than consumer | versions.properties `idKafkaMessaging` vs id-index pom | Confirmed (`MessageProcessorCms.java:86`) |
| `Failed to process document on core <C>` | consumer log (ERROR, stack) | doc build failed **after old docs were deleted**; message treated as success → doc vanishes | cause in stack (`This field cannot be empty`, `cannot have more than one value`, `Could not retrieve collection`) | Confirmed (`SolrCoreIndexer.java:120`) |
| `Could not retrieve collection for core:<C>` | consumer log | core not in consumer registry `search/collections` or not Literatum-enabled | consumer `registry/props.files` + `search/collections/defaults/enabled` | Confirmed (`IndexCollectionManager.java:75`) |
| `Couldn't delete items (query: …). We will retry later on` | consumer log | pre-index delete failed (core disabled in consumer's `SolrConfHelper`, or Solr error) | same | Confirmed (`SolrCoreUpdater.java:69`) |
| `Message already processed, type:…` | consumer log (INFO) | optimistic-concurrency version conflict; harmless | — | Confirmed (`MessageIndexer.java:86`) |
| `Pause for topic:<t>, partitions:[…]` … `Resume for topic:` | consumer log | in-app backpressure: reschedule hash ≥ 150 → **Kafka lag** | `/metric/values`; `kafka-consumer-groups.sh --describe --group gr***-<p>-<f>-index_jb` | Confirmed (`ActionListener.java:81,93`) |
| `The number of rescheduled messages should always be equal to the number of message retry counters` | consumer log | Redis hash/counter drift | Redis `HLEN` of both hashes (read-only) | Confirmed (`RescheduleRepository.java:111`) |
| `Consumer stopped:<src>, count:N` | consumer log | a Kafka listener container stopped | `/metric/values` stopped count; restart history | Confirmed (`ServiceStatus.java:40`) |
| `Service not ready` (HTTP 500 on `/ping`) | curl | Solr or Redis unreachable from the consumer | `curl -s http://<host>:<port>/ping` and `/actuator/health` | Confirmed (`HealthController.java:62`) |
| `FAILED - RETRYING: Get ping status (20 …)` | ProductConsumerDeploy | web app not up at all (the `/metrics/ping` path does not check Solr/Redis) | container log `kafka-consumer-sb.log` start-up | Confirmed (validate.yml) |
| `Initiated N listener(s) for <group>:<topic> servers:<brokers>` absent for a core | consumer start-up log | listener not enabled for that core | consumer registry `search/collections/defaults/enabled/<core>` | Confirmed (`KafkaConfiguration.java:226`) |

---

## 6. Coverage

**Tags and branches read:**
- solr-plugins `solr-plugins-2610.0.16` (`5423fe9`, main read). Also `2610.0.14`, `2410.0.84` and `2710.0.5`, for poms only plus `diff --stat` 2610.0.14..16.
- id-index `index-2610.0.14` (`b5d7089`, main read). Also `2610.0.15` (`67324a8`, `diff --stat`), `2410.0.49` and `2710.0.6` (poms only).
- id-core `core-2610.0.11`: `LitSolrClient` identical to master `afce084`. `IndexFields` constant list compared for 2410.0.44 / 2610.0.11 / 2710.0.5.
- id-kafka-messaging poms at 2610.0.11, 2610.0.7, 2410.0.45 and 2710.0.5, via `gh api`.
- id-search `pom.xml` at search-2610.0.25/.23/.15, 2410.0.111/.110 and 2710.0.5.
- Literatum `versions.properties` at 20 deployed branches (grep of 4 keys only).
- ansible-solr `19.1` (`271d672`) and `18.3` (`5aa5eab`); ansible-consumer `10.0` (`f2a6e7d`) and `9.1` (`4003dee`, `diff --stat` only).
- deployconf `ad1c87a`.

**Read fully:**
- SP: `SolrServerConfigurator.java`, `SolrStandaloneConfigurator.java`, `SchemaGenerator.java`, `EnabledCollectionsExtractor.java`, `SolrServerConfigListener.java`
- IX: `IndexService`, `KafkaConfiguration`, `CustomRebalanceListener`, `MessageListener`, `ActionListener`, `PauseValidator`, `MessageProcessor(Cms)`, `MessageIndexer`, `MessageEraser`, `MessageLogger`, `FailureHandler(Cms)`, both exceptions, `MessageScheduler`, `MessageIndexedScheduler`, `DistributedLocker`, `ResetSolrClientListener`, `RecoveryProcessor`, `MessageValidator`, `MessageCounter`, `RescheduleRepository`, `DiscardRepository`, `CoreIndexer`, `SolrCoreIndexer`, `SolrClient`, `SolrCoreUpdater`, `AbstractIndex`, `IndexChangeEnforcer`, `IndexCollectionManager`, `IndexCollection`, `IndexDocProducer`, `InterXmlIndexDocProducer`, `DatasourceConfig`, `GenericDatasourceConfig`, `EnabledTopicsExtractor`, `CollectionUtils`, `DecodeUtils`, `ZkConnector`, `Health/Metrics/Scheduler/Solr/DebugController`, `SolrHealthIndicator`, `ServiceHealth`, `ServiceStatus`, `Metrics/HealthCheckServletContextListener`, `logback.xml`, `application.properties`, `topics-production.json`, root `pom.xml`
- AS 19.1: `search-version/tasks/*`, `get-base-solr-image.yml`, `create_profile_collections.yml`, `Dockerfile.j2`
- AC 10.0: `consumer.props.xml.j2`, `defaults/main.yml`, `validate.yml`

**Read in part:**
- `IX/ApplicationProperties.java` 1-160 and 490-525, plus a grep of key names
- `SP/solr-pom.xml` 1-110, plus grep
- `AS/create-image.yml` 192-222, plus step names
- `AS/collections_ensure` (grep)
- `AC/deploy.yml` (grep)
- `IC/LitSolrClient.java` 90-115 and 425-465
- `IndexFields.java` constant grep
- `SP/Solr5InitListener.java` (grep)

**Not read:**
- SP `ConfigXmlGenerator`, `AnalyzerDefMap`, `ComponentDefMap`, `CopyFieldGenerator`, `SolrXmlGenerator`, `DeployCustomFilesDirGenerator`; every analyzer/query/scoring implementation; `analyzerDefs-NoNgram.xml` / `componentDefs.xml` content (class values are masked by safe_view); the premade `templates/*/managed-schema`
- IX `SolrDocUtils`, `IndexDoc`, every `*IndexingPolicy`, `MessageDeleteScheduler`, `CacheUpdater`, listeners for product catalog and license cache, the `pkg` profile classes
- tests and `changes.xml` (grep only)
- Solr's own error texts: every Solr-side string in §4/§5 marked Inferred comes from standard Solr behaviour, not from a cloned repo

**Open items:**
1. Confirm that Dropwizard `AdminServlet` `/metrics/ping` is unconditional in the bundled metrics version. If so, propose that validate use `/ping`.
2. Confirm on a live consumer (read-only) whether `Failed to process document on core` occurs in practice. It is a silent delete-without-reindex.
3. Kafka topic retention for `index_*` topics (not set in `topics-production.json`; broker default unknown). This decides how long a paused or stopped consumer can lag without loss.
4. Which lit branch the current shared images (`2610.0.16-d19.1`, `2410.0.84-d18.3`) baked in (`docker inspect … literatum-branch` on one Solr node per env).
