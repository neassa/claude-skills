---
name: literatum-patch-system
description: >-
  Use for Literatum DB patches and the patch VM — ProductPatch on the Deploy Server,
  platform-tools patch.py / run_gradle.sh, DbPatchSystem, DB_VERSION,
  literatum-patch stubs (com.atypon.patch.PatchN) vs modules.migration classes,
  reserved patches, patch ordering, and errors like `Patch litNNNNN failed to
  execute`, `ClassNotFoundException: com.atypon.patch.Patch…`,
  `Patch failed! Output is in /var/tmp/…`, `"patch" is null`, ReadOnlyException
  in a patch, `KILLING THE SYSTEM` in the patch VM. Strictly read-only.
---

# Literatum DB patch system (read-only)

**Paths:** relative to this skill's folder (`../literatum-platform/references/deep/`); repos under `$LIT_REPOS`. Read files only through `../literatum-deploy-triage/scripts/safe_view.py`. Patch data may contain customer rows: don't reproduce them.

## How ProductPatch runs

1. Runs on the backstage host after HostStop + HostDeploy. It uses the **deployed** webapp classes, not the fresh build.
2. `patch.py` calls `run_gradle.sh patch runWithJavaExec`, which **always exits 0**. `patch.py` fails only on the text `FAILED` or `KILLING THE SYSTEM`; with `-c` patch failures are swallowed.
3. Gradle first compiles platform-tools' own `operations/tools` (DbGradlePatcher) in the **NFS-shared** checkout. A `NoSuchFileException …/build/generated/sources/annotationProcessor` here is a shared-dir race, not Literatum code (np stag).
4. The **patch VM** (`server.type=patch`) starts nearly the full web Spring context. Anything eager in it can kill the run before any patch: the Gaia Cassandra cache, the cluster mutex (LIT-683431), a missing jar in `WEB-INF/lib`.
5. `DbPatchSystem.run()` builds a queue per pool from the patch files vs `DB_VERSION`, then runs each via `JDBCPatchExecutor`. Re-runs apply whatever is missing. A release mismatch fails unless `-u`/`-R`.
6. Java patches: the stub `com.atypon.patch.PatchN` (in literatum-patch) calls `loadDynamicPatch("com.atypon.modules.migration.PatchN")` (in literatum).
7. Full output is on the host at `/var/tmp/<epoch>.txt` (`Patch failed! Output is in …`). The action log may have only the tail.

## Signatures

| Signature | Meaning |
|---|---|
| `ClassNotFoundException: com.atypon.patch.PatchN` | **stub** missing on that literatum-patch branch. On maint branches it often lands later than on the main line (lit32053: asmj, aami, hanser, app stag). Check the `PATCH BRANCH:` commit history for that file vs the build time. |
| `ClassNotFoundException: com.atypon.modules.migration.PatchN` | the target class is missing from that literatum branch |
| `db_version (litNNNNN) … "patch" is null` at `DbVersionCheck:154` | pre-LIT-677519 bug: a reserved dependency was queued as null. **The named patch is only the last one the loop saw.** The fix `523433c4b1` reached physio's branch on 15 Sep. |
| `ReadOnlyException` at `LicenseImpl.deleteImpl` ← `IdentityImpl.deleteLicenses` | the patch deletes a user who holds a CR-marked license; `deleteLicenses` doesn't unmark (unlike `SyntheticLicense.deleteImpl`). This is site data: it passed on about 26 other sites (aiaa lit32053). Which license: DB. |
| `Failure to load ClusterMutex class` → `ExceptionInInitializerError` | unpatched build: `clusterMetrics = null` (LIT-683431). Fresh build from a branch with `3b5d53c2`. |
| `NoClassDefFoundError … UntypedActorSystemOps` | root-pom forced Akka 2.6 over passport-cluster 2110.0.1 (2610.0.4, 2610.0.6). Fresh build with 2610.0.7. |
| `Invalid column name …` on web start | the WAR is ahead of the DB: the patch didn't run (PageBuilder columns come from Liquibase changesets in patches such as lit31595, lit31745) |
| `already an object` | the patch's DDL already applied; past fix = mark it applied in `db_version` (owner) |

- **After a failed ProductPatch + cancel, the backstage stays stopped** (HostStop ran, HostStart never did).
- **Nightly rehearsal:** Dailypatch-backend runs build → deploy → patch against office DB copies (staging/beta, never prod). A staging failure there for the same patch is a leading indicator. Its Jira signal has been dead since 2025-04; use its API.

## Deep notes

`04-literatum-patch-system.md` (lifecycle, ordering, reserved patches, retries), `02-platform-tools.md` (patch.py, run_gradle.sh), `25-patching-repos.md` (patch creation scripts, Dailypatch, physio), `32-literatum-access-licensing.md` (ReadOnlyException decision tree), `17-literatum-backstage-access-cli.md` (cluster mutex), `36-dailypatch-ui-themes.md`.

## Founding failure

A ProductPatch failure was read as a problem with the patch named in the message. The named patch was only the last one the loop had seen; the null was a reserved *dependency* from before a fix (LIT-677519) reached that branch.
