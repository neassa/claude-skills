---
name: literatum-gaia
description: Use for anything about Gaia in Literatum — the Gaia transformation service (gaia-fe docker, axel XSL bundles, bundle_version / image_tag in deployconf), GaiaDeploy / GaiaCompatibilityCheck / GaiaProductSetAxelVersion on the Deploy Server, the Gaia output cache in Cassandra (gaia_<product>_<mode>, table_index), and errors like `Error executing Gaia transform`, `table table_index does not exist`, `Mismatch Gaia bundle version`, `/tmp/start.sh is absent`. Strictly read-only.
---

# Literatum Gaia (read-only)

**Paths:** relative to this skill's folder (`../literatum-platform/references/deep/`); repos under `$LIT_REPOS`. Read files only through `../literatum-deploy-triage/scripts/safe_view.py`.

## "Gaia" is three things

| Part | Repo | Version source |
|---|---|---|
| The library Literatum calls (`GaiaHttpClient`, `TransformationService`, output cache) | `gaia` | Literatum pins 1.7.3 on every branch |
| The **gaia-fe** service (docker, one cluster per env: `dc-beta`, `dc-stag`, `dc-prod`) | `gaia-fe`, deployed by `ansible-gaia` (branch 2.0) | deployconf `<gaia><cluster image_tag=…>` (1.6.7 on all envs, 2026-09) |
| Per-product **axel** XSL bundles | `axel` (released to GAR) | deployconf `<gaia bundle_version=…>` per product (e.g. 2.2.85.1, 2.2.88) |

## Deploy Server steps

- **GaiaDeploy** → `ansible-actions -s gaia …` → ansible-gaia 2.0. **Can go green with nothing changed:**
  - a new `image_tag` is ignored unless `force_recreate=true` (`app-deploy.yml:150-151`);
  - the bundle is checked in GAR, but the container downloads it from Nexus;
  - the check regex cuts `2.2.85.1` to `2.2.85`;
  - bundles install **asynchronously** (an updater loop every 10 s, forever if the bundle is missing in Nexus);
  - `/actuator/health` is UP with zero bundles.
  - Real state: compare gaia-fe `GET /config` with `GET /bundle`.
- **Overlapping GaiaDeploys on one cluster** break each other: `Copy files … (item=start.sh) … (/tmp/start.sh) is absent` (LIT-656679, open). Re-run.
- **SSH host key change** on a gaia node: `REMOTE HOST IDENTIFICATION HAS CHANGED` → UNREACHABLE. Transient if other deploys reached that node that hour (shared `known_hosts`).
- **GaiaCompatibilityCheck** (prod `literatum` ProductRefreshDeploy only, `PreExecuteVisitor.java:2750/3137`):
  - compares prod vs **staging** `bundle_version` and image tag, and fails on any mismatch, on missing staging Gaia (`Gaia is not configured on Staging`), and also when both values are null;
  - 61 of 66 prod products differed from stag on 2026-09-25, so a failure usually means "prod deployconf not yet aligned with the version tested on stag".
- **Rundeck:** GaiaProductSetAxelVersion → ConsulPopulate; the Rundeck GaiaDeploy job passes with no pod Running.

## Gaia output cache (Cassandra), a startup dependency

- Keyspace `gaia_<product>_<build.mode>` on the product's Cassandra cluster. Stag and beta share the **name** (`build.mode=beta`) but not the cluster.
- Bean `GaiaFeBeans.getOutputCacheFactory` is **eager**: it runs at Spring start on web, backstage **and the patch VM**. `isTableExists` reads driver-cached metadata, runs CREATE only if that says missing, then `prepare` hits a node.
  - So `InvalidQueryException: table table_index does not exist` means **nodes disagree about the schema**, or a wedged node. → `KILLING THE SYSTEM`, and no patch runs (informs beta, 24 Sep).
  - Check: Cassandra container logs at that minute, `nodetool describecluster`. Team fix: redeploy Cassandra, then re-run. See `literatum-patch-cassandra-failures`.
- A new `table_index` table appears **per Gaia bundle deploy / scope**, never from a Literatum redeploy. `gaia_cleanup` (ansible-cassandra) keeps the 2 newest ids per template. Gaia keyspaces with 22k–45k tables drifted until SRE rebuilt the cluster (Jira).
- Cache key = publication `PATH` + `[template, scope, templateTimestamp]`.

## Runtime failures in pages

`Error executing Gaia transform for doi <doi>` (`ReaderGaiaUtil.transform`), `has rendering problem, real cause: …`: a missing file or a bundle problem. Compare with other DOIs and the bundle version.

## Deep notes

`05-literatum-build-config-gaia.md` (bootstrap, output cache), `15-gaia-cmsroot-idcore-rootpom.md` (library, compat check), `22-gaiafe-axel-devprod.md` (gaia-fe, axel, GaiaDeploy traps), `33-literatum-content-delivery.md` (cache key, table lifecycle), `03-ansible.md` (ansible-gaia, gaia inventory), `30-rd-jobs.md` (Rundeck Gaia jobs).

## Founding failures

- informs beta ProductPatch died at patch-VM start with `table_index does not exist`. It looked like a missing schema. In fact the bean had created the table, and a node that disagreed answered the `prepare`. Other sites on the same host passed.
- A Gaia deploy failed with `/tmp/start.sh is absent`: another product's GaiaDeploy on the same cluster, 6 seconds earlier, had deleted the file.
