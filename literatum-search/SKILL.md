---
name: literatum-search
description: Use for Literatum search and indexing — Solr cloud cores and configsets (solr-plugins), ZooKeeper, the Kafka indexing path (IssuePipeline → id-index consumer → Solr), SolrDeploy / ProductConsumerDeploy / SolrIndexSync / DigitalObjectReprocess on the Deploy Server, and symptoms like missing or stale search results, `Circuit-breaker is open`, `is not a valid Zookeeper host`, `Failed to process document on core`, `Document purged from Redis … exceeded max number of retries`, `Pause for topic:`. Strictly read-only.
---

# Literatum search and indexing (read-only)

**Paths:** relative to this skill's folder (`../literatum-platform/references/deep/`); repos under `$LIT_REPOS`. Read files only through `../literatum-deploy-triage/scripts/safe_view.py`.

## The pieces

| Piece | Repo | Version source |
|---|---|---|
| Solr schema + solrconfig + plugins (configsets) | `solr-plugins` | Literatum `versions.properties` `searchVersion` (2610.0.16 on lit-2610 / maint) |
| Core list per product | Literatum `literatum.props.xml` | lit-2610 base enables jb, ctg, contribautocomplete, titleautocomplete, topicautocomplete; products add do, dbpubs, related, contentsuppression |
| Solr client, ZK chroot | `id-core` via `id-search` | id-search 2610.0.25 on lit-2610 |
| Kafka consumer app | `id-index` (deployed by `ansible-consumer`) | `indexVersion` (2610.0.14–15) |
| Solr/consumer deploy | `ansible-solr` (19.1), `ansible-consumer` (10.0 fallback) | deployconf / lifecycle json |

- **Literatum ships no schema.** The schema field set is generated from id-core `IndexFields`. The consumer builds documents from id-core too, so in every deployed combination (2026-09) schema and consumer agree. `EditionDescription` exists in 2410, not 2610.
- **Indexing is async:** backstage publishes via `IssuePipeline` to Kafka (`DoIndexProc` is dead code), then the id-index consumer, then Solr. Backstage doesn't write Solr directly.
- The ZK string needs a chroot: deployconf builds `hosts/<prefix><product>[-family]`.

## Deploy-time traps

| Step | Trap |
|---|---|
| SolrDeploy | `deploy.yml` commits with `reload_collections: false`; a node takes a new configset only if its container is **recreated** (new image or forced). The configsets are baked into a **shared** Solr image. The step that picks collections to create swallows exceptions and then creates every configset's collection. |
| ProductConsumerDeploy | validates `/metrics/ping` (metrics servlet), **not** `/ping` (which checks Solr + Redis): passes with Solr unreachable. |
| SolrIndexSync (`index.sync -s mes`) | **writes**: reindexes and deletes index docs that aren't in the DB. Not a read-only check. |
| DigitalObjectReprocess | exits 0 on error; loops with no time limit while `[PROCESSING]` > 0 (reader). |
| ProxySolrDeploy | no health check; `literatum.props.xml` from GitHub master (2410+) or SVN trunk (1910–2210). |
| Solr host | `fatal: [..solr1]: UNREACHABLE … Connection timed out` = host/network, transient if later runs pass (cabi beta). |

## Runtime symptoms

| Symptom / log text | Meaning |
|---|---|
| `is not a valid Zookeeper host`, `Error creating client for collection` | ZK string / chroot wrong or ZK down |
| `Circuit-breaker is open` → user sent to search error page | Solr failing per request; Solr/ZK aren't checked at startup |
| Document missing after publish, no error | consumer deletes old docs first; if building the new one fails it logs `Failed to process document on core X` and **counts the message as done** |
| `Document purged from Redis … exceeded max number of retries` | failed Solr writes retried 3× from Redis, then dropped |
| Kafka lag growing, `Pause for topic:` | 150 messages awaiting retry → partition paused |
| Newly enabled core missing old documents | offset reset is `latest`: messages before its first commit are skipped |
| Kafka send failures from Literatum | cached, retried, then dropped without failing the job (lit-2610 jar not locally verified) |

## Deep notes

`28-literatum-search-rest-db.md` (cores, index sync, IssuePipeline), `29-solr-plugins-id-index.md` (schema generation, consumer, versions matrix, 22 signatures), `21-passport-rootpom-idsearch.md` (id-search client), `03-ansible.md` (ansible-solr, ansible-consumer), `11-ansible-services.md` (proxysolr, searchservice), `10-ansible-infra.md` (ZooKeeper, Kafka), `12-literatum-runtime.md` §3.

## Founding failure

The first note said Literatum had "six Solr cores" and shipped its own schema. Both were wrong for lit-2610: five base cores, and the schema comes from solr-plugins/id-core baked into a shared image. That changes what a "SolrDeploy succeeded but results are wrong" investigation looks at.
