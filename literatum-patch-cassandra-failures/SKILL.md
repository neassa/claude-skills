---
name: literatum-patch-cassandra-failures
description: Use when a Literatum product deploy (patch.py / ProductPatch / DbPatchSystem) fails during the JDBC patch phase with a Cassandra error — any patch that opens a Cassandra session, not just lit31621. Triggers include InvalidQueryException "table does not exist" that contradicts what cqlsh shows, NoClassDefFoundError from a Cassandra driver (e.g. FutureFallback), a dormant patch suddenly running after a feature flag flipped, or cqlsh refusing connections on staging.
---

# Debugging Literatum Patch Failures Against Cassandra

Platform context (repos, patch VM, Gaia, Cassandra keyspaces): skill `literatum-platform`.

## Overview

lit31621 (campaign migration) is the worked example throughout, but the failure modes and the diagnostic sequence apply to any Literatum patch that opens a Cassandra session — the same node-health, classpath, and feature-gating mechanics recur.

Literatum JDBC patches that talk to Cassandra hard-fail the entire ProductPatch on any `Throwable`. The error text reports what **one Cassandra node answered at deploy time**, not the true cluster state — a wedged node returns false schema errors for hours while cqlsh (which may hit a healthy node or post-restart state) shows everything fine.

**Core principle:** when the patch's Cassandra error contradicts cqlsh, suspect node health or classpath before schema or conf. Check the container's own log at the deploy timestamp first.

## Recognize the signature

| Observation | Meaning |
|---|---|
| `InvalidQueryException: table X does not exist` but cqlsh shows the table on all nodes | Node the driver hit was wedged — look for `StackOverflowError` / `ERROR ... ExceptionHandlers` in the Cassandra container log **before** the deploy time. Fix: redeploy/restart the container |
| `NoClassDefFoundError: com.google.common.util.concurrent.FutureFallback` at `getCassandraSession` | Classpath clash: old DataStax driver + Guava ≥20 in the patch JVM. No connection was ever made. Fix dependencies, not Cassandra |
| "Keyspace does not exist: X" printed, patch skipped | Graceful guard worked — conf keyspace name wrong or env has no VOS data |
| A years-old patch suddenly runs | Patches gate on boolean props (lit31621: `product-catalog/enabled` AND `product-catalog/campaigns/enabled`); enabling a feature wakes dormant patches |

### Variant: the patch VM dies at Spring startup on the Gaia output cache (no patch ran)

Seen 2026-09-24 on informs beta (ProductPatch on literatum3-beta-bks1). Signature: `BeanCreationException … 'getOutputCacheFactory' … GaiaFeBeans` ← `InvalidQueryException: table table_index does not exist` → `ERROR LOADING PRODUCT` / `KILLING THE SYSTEM`, with **no** `Executing patch …` line and no `db_version` rows.

- The patch VM (`server.type=patch`) loads almost the full web Spring context. `GaiaFeBeans` (no `@Profile`/`@Lazy`) is eager for any product whose props include `midtier.props.gaia-fe.xml`. This holds even when deployconf has no `<gaia>` for the product, as with informs beta.
- `CassandraOutputCacheFactory.produce` (external `gaia-registry`/`gaia-core` 1.7.3) connects, runs `createKeyspaceIfNotExists gaia_<product>_<build.mode>`, runs `CREATE TABLE IF NOT EXISTS …table_index`, then **prepares** queries on it. So "does not exist" right after the create means the node that answered didn't see the new table: a wedged node or schema disagreement. The core principle above applies unchanged.
- Stag and beta both run `build.mode=beta`, so the keyspace **name** is the same (`gaia_<product>_beta`), but each env normally uses its own Cassandra cluster — verify with deployconf before assuming cross-env impact (informs: different clusters).
- `isTableExists` checks the **driver's cached schema metadata** (atypon/gaia `VersionedCassandraOutputCache.java:155`); the `prepare` that fails runs on a node. "does not exist" there = schema disagreement between nodes. Confirm with `nodetool describecluster` (schema versions) and the container logs at the failure time.
- The only code that drops Gaia tables is `ansible-cassandra` cleanup (`roles/cleanup/tasks/cleaner.yml`). It drops tables, then deletes their `table_index` rows as a separate step, so `table_index` can point at dropped tables (LIT-682047, open; LIT-681676, fixed with `DROP TABLE IF EXISTS`).
- The fix is on the Cassandra side, or make the bean lazy / `@Profile("!patch")`. No patch change can work around it. **Team practice (operator, 2026-09-25): a similar informs case was solved by redeploying Cassandra (CassandraDeploy on the product's cluster), then re-running the deploy.** Reschedule only the failed ProductPatch row (not RestartWorkflow, which re-runs the whole family incl. the build). On a 2-node cluster (RF 2, QUORUM) each node restart briefly fails QUORUM reads for every product on that cluster. Optional evidence first: `nodetool describecluster` (two schema versions = confirmed).
- Deep notes: `../literatum-platform/references/deep/04-*.md` §5 and `05-*.md` §C. Triage context: skill `literatum-deploy-triage`.

## Diagnostic sequence

1. **Deploy output**: full patch output path is printed as `Patch failed! Output is in /var/tmp/<ts>.txt` on the backstage host. The last `Caused by` before the first retry is the real error; retries repeat it 3×.
2. **Cassandra container log at the failure timestamp** (the decisive probe — do this before schema archaeology):
   `docker logs --since/-n ... cassandra-stag-<cluster>-<port>` — errors like `StackOverflowError` on `Native-Transport-Requests` predating the deploy prove the node was sick.
3. **cqlsh — staging clusters listen on custom native ports** (container name suffix = port, e.g. `cassandra-stag-lit2-2123` → port 2123; default 9042 refuses):
   `docker exec <container> cqlsh localhost <port> -e "SELECT table_name FROM system_schema.tables WHERE keyspace_name='<ks>';"`
   Over ssh, drop `-it` (no TTY) and escape inner quotes: `ssh host "docker exec c cqlsh localhost 2123 -e \"...'ks';\""`
4. **Only if 2–3 don't explain it**: compare registry props `cassandra/nodes` and `cassandra/vos/keyspace` (amps A8 staging: `vos_amps_1820_beta_a8` on lit2) against where you probed; check other clusters via unfiltered `docker ps | grep -i cassandra`.

## Fixes

- **Wedged node**: redeploy/restart the Cassandra container, re-run the deploy. The Deploy Server action is **`CassandraDeploy`** (also `CassandraRestart`), which is `scope="AccountLevel"` with the cluster name as its target and no product. So find past runs with `ds_search.py <acct> "" CassandraDeploy 200` (no product filter), then read each log header for the cluster. Failed patches aren't marked applied, so a clean re-run completes them.
- **Fragile patch code** (`atypon/publish/src/java/com/atypon/modules/migration/Patch031621.java`): guards missing-connection and missing-keyspace but not missing-table; `getCassandraSession()` catches `Exception` only, so `Error`s (NoClassDefFoundError) escape the graceful-skip path. Harden with a `keyspaceMetadata.getTable(...) == null` guard and `Throwable` handling.

## Common mistakes

- Treating "table exists in cqlsh now" as proof it existed *to that node* at deploy time — verify node health at the failure timestamp instead.
- Chasing schema-disagreement/DDL races before reading the container log — `nodetool describecluster` is fine, but a plain `docker logs` grep is faster and was the actual answer.
- cqlsh "Connection refused" on 9042 read as "cluster down" — staging uses per-cluster custom ports.
- Assuming the failing patch is new code — check its gating properties; feature-flag rollouts wake dormant patches across many products at once.
