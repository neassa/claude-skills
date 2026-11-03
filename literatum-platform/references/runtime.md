# How the Literatum application works (deploy- and debug-relevant)

Sources: `$LIT_REPOS/literatum/AGENTS.md`, `docs/architecture/*.md` (read 01,02,03,04,05,09,10,18,19,20,21), plus code reads in `deep/04` and `deep/05`. Read the architecture doc for a subsystem before changing it; the corrections at the bottom override the docs.

## Things that mislead (from the repo's own AGENTS.md)
- Custom MVC: JFlex URL normalizers → `ControllerServlet` → `ActionController` → `Action.execute()` (not Spring MVC/Struts).
- Main REST API is a handler tree configured in `literatum.props.xml` (not JAX-RS).
- Persistence is mostly custom JDBC with nested `TableDef` rows (`AbstractDbBasic`/`AbstractEntity`); a JPA path exists for newer code.
- `atypon/publish/` is a second source root of `:literatum`, not its own project.
- Wiring is configuration: services, filters, REST handlers, caches must be registered in `*.props.xml` / Spring XML — adding a class is rarely enough.

## Build
- `./gradlew :product:<p>:war` → depends on `deployWeb` → `:literatum:compileJava` (literatum + publish sources). A compile error anywhere breaks **every** product on that branch.
- Dependency versions: `atypon/literatum/versions.properties` pins Atypon libs; the **root-pom** (`atypon/build.gradle` `parentPomVersion`, repo atypon/root-pom) sets third-party versions such as **Akka/Scala/Alpakka** (2610.0.6 moved Akka 2.5→2.6 and broke passport-cluster at runtime; 2610.0.7 reverted it). A root-pom bump is a prime suspect for runtime `NoClassDefFoundError` with a green build. Example failure: code on `master` used an enum value (`CmsContributorRole.ADVISER`) that the pinned `cms-apis 4.0.0.28` didn't have yet.
- On DC build hosts `rebuild.py` applies an out-of-git source patch for master/lit-2610 (LIT-656000); a failed apply is swallowed and the build ships unpatched (deep/02 §3.3).

## Configuration and startup
- Registry = layered `*.props.xml`: base `literatum.props.xml` → host / `server.type` overlays → `midtier.props.*` (e.g. `midtier.props.IBM-stag.xml`, `midtier.props.gaia-fe.xml`) → `deployconf.props.xml` (generated from deployconf at deploy time) → DB overrides.
- `build.mode` (from midtier props) is `beta` for both IBM-stag and IBM-beta.
- `Main.run` → logging/system props → **Spring context built from registry `components/`** (every config-file unless disabled or excluded by `server-type`) → `DbConf.start()`. Any Throwable → `ERROR LOADING PRODUCT <p>` / `KILLING THE SYSTEM` → exit 1.
- **Server roles** (`server.type`): `web` (default, serves the site), `backstage` (ingestion, workflows, robots), `patch` (the DB patch VM — loads nearly the full web Spring context, profile `patch` removes only robots and a few beans).

## Persistence and read-only
- MSSQL (Oracle support exists). Entities: `AbstractDbBasic` → `AbstractDbEnhanced` → `AbstractEntity`.
- **Two kinds of read-only**: site mode (`ReadOnlySiteUtil`, throws `WriteDeniedError`) vs **entity read-only** (`isReadOnly()`: CR-marked fields, identity in a read-only group, license whose holder is read-only; `LicenseImpl.getCopy` copies) → bare `ReadOnlyException`.

## DB patches (see deep/04)
- `patch.py` → `run_gradle.sh patch runWithJavaExec` (always exits 0) → `DbGradlePatcher` → `DbPatchSystem.run()` → per-pool queue from patch files vs `DB_VERSION` → `JDBCPatchExecutor` per patch → `DB_VERSION` row (status, message). Re-runs apply whatever is missing.
- Java patches: `com.atypon.patch.PatchN` stub (literatum-patch) → `loadDynamicPatch("com.atypon.modules.migration.PatchN")` (literatum). `ClassNotFoundException` on the first = stub missing; on the second = class missing from that branch.
- Runs against the **deployed** webapp classes and (on DC hosts) the deployed `iapps/patch` files — not the fresh build.
- Release gate: DB release ≠ build branch → fails unless `-u`/`-R`.

## Search and indexing
- Solr cores are per-product config in `literatum.props.xml` (lit-2610 base enables jb, ctg, contribautocomplete, titleautocomplete, topicautocomplete; products add do, dbpubs, related, contentsuppression …). The earlier "six cores" line was wrong. Solr cloud with ZooKeeper (`<solr zk_cluster_name>`). Literatum ships **no** Solr schema: configsets come from atypon/solr-plugins (at `searchVersion`) + literatum.props.xml (at `lit_version`) built into a shared Solr image; the consumer (atypon/id-index, at `indexVersion`) derives fields separately, and nothing checks the three agree (notes/28). Indexing is asynchronous via Kafka (`IssuePipeline`, not `DoIndexProc`) → consumers (ansible-consumer) → Solr; backstage doesn't index directly. A Solr deploy pauses consumers and can leave them paused on failure. ansible-solr `deploy.yml` (19.1 = `271d672`) commits with `reload_collections: false`, then `node-deploy` runs `docker_container state: started, recreate: {{ recreate_container }}`: a node picks up a new configset only if its container is recreated (new image, or recreate forced).

## Caches and data stores
- Redis (deployconf `<cache>`: cache + ArticleMetrics clusters).
- Cassandra: VOS data keyspaces (`vos_…`) and the **Gaia output cache** keyspace `gaia_<product>_<build.mode>` (same name in stag and beta, but on each env's own cluster) with `table_index` (versioned tables; old versions dropped by ansible-cassandra gaia_cleanup). The Gaia cache bean (`GaiaFeBeans.getOutputCacheFactory`) is eager and does Cassandra I/O at Spring startup — including in the patch VM.

## Gaia and styleguide rendering
- Gaia = remote transformation service (XSLT/HTML) called via `GaiaHttpClient`/`TransformationService`; deployed as docker containers by ansible-gaia; bundles per product (`<gaia bundle_version>`).
- Styleguide = ui-products build served by **pugrenderer** (styleguide-render-pug) nodes that run next to the web JVMs; Literatum web calls them for template rendering and static assets (`/?p=&v=&r=`). Renderer caches have no TTL → deploys must invalidate them.

## Corrections to docs/architecture (verified in code)
- 04 §Schema patching: the `Patcher` diff engine doesn't execute; the live system is `DbPatchSystem` (sets `server.type=patch`).
- 05: only `DB_VERSION` tracks patches (`DB_INFO` holds release/product info).
- 05: most `modules.migration` classes **are** run automatically by the patch system (via stubs), not only standalone.
- 19: `patchDB`/`ExecutePatch` runs `DbPatchSystem.run()`, not the `Patcher` engine.
