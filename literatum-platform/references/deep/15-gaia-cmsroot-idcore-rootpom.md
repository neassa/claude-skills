# 15 — gaia, cms-root, id-core, root-pom: how they feed Literatum deploys and how they fail

Written 2026-09-25. Read-only: no builds, no runs, no pushes. The only writes were this note, scratch files, and `git fetch` into the local clones (gaia unshallowed; cms-root and id-core got shallow fetches of specific tags and branches).
Secrets: every config/pom/yaml print was filtered (`pass|pwd|token|secret|api_?key|_auth|credential|private|user:pw@`). Filtered lines that carry credentials: `ansible-gaia/roles/deploy-cluster/files/configinit.sh:13,19`, `ansible-gaia/roles/deploy-cluster/tasks/check-bundle.yml:26`, `cms-root/.github/workflows/release.yaml:14,16,31-35,48-49,101,111,138-139,142,150,156,187`, `id-core/.github/workflows/release.yml:33,76,83,85`. No values were read.
Status tags: **Confirmed** (read in code or git), **Inferred** (reasoned from code, not seen in a log), **Unconfirmed** (not checkable here).

---

## 0. Coverage (commits read)

| Repo / source | Ref (commit) | Read fully | Sampled / grep only |
|---|---|---|---|
| gaia (local, now unshallowed, 224 commits) | master `95ab25c` = **1.7.4** (2026-04-28); 1.7.3 = `5761b32` (2024-11-28, no tag) | `build.gradle`, `settings.gradle`, README, release workflow; all of `http-server/`, `http-client/`, `http-common/`, and `registry/` main code; core: `GaiaException`, `GaiaTimeoutException`, `Scope`, `TransformationService`, `TransformationContext`, `transformation/*`, `source/TransformationSource`, `template/{TransformationTemplateParser,GaiaTemplates,GaiaTemplateResource(s),ErrorTransformationTemplate,DirectTransformationTemplate,SimpleTransformationTemplateLocator,TransformationTemplateLocator,TransformationTemplateParsingException}`. Also the full `git diff 5761b32..95ab25c` of main code. | `executor/*` and `cache/*` (grep for errors and logs only; the Cassandra cache was covered in note 05), `trace/*`, `replacer/*`, `writer/*`, tests, `sample/`, `http-server-sample/` |
| gaia-fe (GitHub, **not in the repo list**) | tag `gaia-fe-1.6.7` = `57ca328612` (2026-07-27), the image deployed on every DC cluster | `Beans`, `MultipleBundleDeployment`, `SingleBundleDeployment`, `TransformationTemplateScanner`, `GaiaFeTransformationTemplateLocator`, `api/ConfigFileApi`, `application.yml`, `pom.xml` (filtered) | Helm/k8s files, `GaiaFeTagsProvider`, `App` (names only) |
| axel (GitHub, **not in the repo list**) | — | not read. It is the XSL bundle war (`com.atypon:axel:<bundle_version>`) | — |
| literatum-lit-2610 | `9f8eb846e` (origin/lit-2610, 2026-09-25) | `literatum/gaia/GaiaFeBeans`, `LiteratumTransformationTemplateLocator`; `ReaderGaiaUtil.transform`; the id-core exclusions and `id` deps in `literatum/build.gradle`; the parentPom wiring (`build.gradle:78`, `literatum/build.gradle:242-245`, `AspectJPlugin`, `BridgeAspectsPlugin`) | `GaiaRenderer` catch block; the id-core import census (688 files) |
| literatum master (GitHub) | `0c62d01577` (2026-09-25T12:04Z) | `versions.properties` pins; `ContributorsIndexingUtil.java:210` | — |
| deployserver | `b726c83` | `PreExecuteVisitor.visitGaiaCompatibilityCheck` + `isMatching` (3137-3200), insert conditions (2750-2752, 2797-2799); `actions.xml` GaiaDeploy (1188-1204); `ActionHelper.isDCGaia/getGaiaClusterName` | other Gaia actions (see note 01 §3.6) |
| deployconf | `ad1c87a` (main = origin/main) | parsed `midtierbeta`, `staging`, `literatum` with xml.etree (all `<gaia>` elements, secret-looking attrs skipped); `xslconfig/deployconf.xsl` 1920-1980 and the `gaiak8s` / `gaia-endpoint-template` templates (1981-2160) | the rest of the XSL |
| ansible-gaia | `f601ffb` | `templates/config.xml.j2`, `tasks/{main,check-bundle,app-deploy}.yml`, `files/{start.sh,configinit.sh,updater.sh,configparser.py}` (filtered) | rest as in note 03 §5 |
| platform-tools | `b00c49f` | `deployPropsDeployconf.parseDeployconfXslt` 60-110, `redeploy.py` 295-315 | `env.py` gaia helpers (grep) |
| cms-root (local, shallow) | master `401f9d50` (2026-09-23T10:12Z); `origin/lit-2610` = `b3d8e23`; tags `cms-apis-3.0.18.1` `777ddad`, `cms-apis-3.0.18.2` `b3d8e23`, `cms-apis-4.0.0.28` `735e98c` | root `pom.xml`, `cms-apis/pom.xml` (filtered), `.github/workflows/{release.yaml,ForwardPRCreate.yaml,scripts/update_cmsapis_version.py}` on master; `release.yaml`, `pom.xml`, `jrelease.gdsl` on lit-2610; `CmsContributorRole.java` at all 5 refs | README; `git ls-remote --tags` (all tags, grouped by version line) |
| id-core (local, shallow) | master `afce084` (2026-08-09; remote HEAD is the same); tags `core-2610.0.11`, `core-2710.0.5` | README, all 4 poms (filtered), `.github/workflows/release.yml`, `Contributor.java` (index.fields) at 3 refs | package census; `id-solr*` modules (names only) |
| id-search (GitHub, **not in the repo list**) | tags `search-2610.0.25`, `search-2710.0.5` | root `pom.xml` `id-core.version` property | — |
| root-pom (GitHub, reachable) | master `528af5b041`; lit-2610 `6d88b96a6f`; tags `atypon-root-pom-2610.0.4 … 0.7` | readme, commit list for master + lit-2610, `compare` 0.5…0.6, 0.6…0.7, 0.5…0.7 (full patches), commit `9bd073af4c` patch, PR #76, managed Akka artifacts in `pom.xml@2610.0.6` | the rest of `pom.xml` (74 KB) |

**Gap:** `com.atypon.ops.common.confutils.ConfHelper` (`getGaia`, `getGaiaImageTag`, `isGaiaConfigured`, `getFamilyForProduct`) ships as a jar and is in none of these repos (same gap as note 06). How it picks the image tag is inferred from its name plus deployconf.

---

## 1. Gaia

### 1.1 What the pieces are (Confirmed)
There are three separate artifacts. The deploy vocabulary mixes them up.

| Thing | Repo | Version seen in | Current value |
|---|---|---|---|
| **Gaia library** (`com.atypon.gaia:gaia-{core,registry,http-client,http-common,http-server}`) | `atypon/gaia` (this clone) | Literatum `versions.properties:49-52` `gaia*Version` | **1.7.3** on lit-2410, lit-2610, lit-2610-maint-260901 and master. The library's master is 1.7.4. |
| **Gaia FE service** (Spring Boot + Jetty app, docker image `atypon-gaia/gaia-fe:<image_tag>`) | `atypon/gaia-fe` (**not in the list**) | deployconf `<gaia><cluster image_tag>` | **1.6.7** on dc-beta, dc-stag and dc-prod (aigateway clusters 1.6.5). gaia-fe 1.6.7 is built against gaia library **1.7.2** (`pom.xml` `gaia.version`). |
| **XSL bundle** (`com.atypon:axel:<v>` war: the Axel XSL templates) | `atypon/axel` (**not in the list**) | deployconf product `<gaia bundle_version previous_bundle_version service_cluster>` | beta: mostly 2.2.75 (37 of 62). Staging: 2.2.88 (65 of 74). Prod: 2.2.85.1 (54 of 66). |

So "which gaia branch does deployconf use" has this answer: deployconf never names the gaia library. It pins ansible-gaia `deploy_version=2.0`, the gaia-fe `image_tag`, and per-product axel `bundle_version`s. The library comes only through the Literatum build (1.7.3 everywhere). I read master (1.7.4) and diffed it against 1.7.3 (§1.6).

### 1.2 Architecture (Confirmed)
- **Library** (`gaia:core`): `TransformationService.transform(ctx, writer)` does these steps:
  1. resolves the template through a `TransformationTemplateLocator`;
  2. collects documents from the `TransformationSource`;
  3. builds a `CacheKey` (template key + source key + args);
  4. runs through `TransformationExecutor`, optionally wrapped by the caching decorator, with a `future.get(noCacheTimeout)`;
  5. streams the output through the replacers (`{{…}}` processors).
- **HTTP contract** (`http-server` = server side, `http-client` = Literatum side, `http-common` = JSON model). Mixins give `type: file` (`path`) and `type: string` (`string`, `timestamp`) documents.
  - `GET /bundle?scope=&client=` returns the bundle name as text/plain.
  - `GET /templates?scope=&client=` returns `[TransformationTemplateMetadata]`.
  - `GET /template/{id}?scope=&client=` returns metadata `{id, scope, status: ready|unavailable, timestamp, errors[]}`, or 404.
  - `POST /template/{id}?scope=&client=` takes body `{documents:{id:{type,…}}, arguments:{}}` and returns the output as a string.
  - `GET /actuator/info` supplies `build.version`.
- **Selection on the FE** (`TransformationTemplateBundleSelector.select`): look up `(scope, client)`, then `(scope, "")`, then walk the scope parents split on `-`, then ROOT. The template lookup (`GaiaFeTransformationTemplateLocator`) walks the scope chain too. If nothing matches, it falls back to the bundle's **base** templates with `productId=<scope>` added.
- **Literatum wiring** (`GaiaFeBeans`, lit-2610):
  - `GaiaHttpClient(id=gaia/id, base=gaia/endpoint)` with `stripRedundantDefaultPort`. Pool size comes from `gaia/concurrent-request-count`. Socket/connect timeouts come from `gaia/socket-timeout` / `gaia/connect-timeout`.
  - The template locator is `CachedHttpTransformationTemplateLocator` when `gaia/transformation-template-metadata-cache-window` is greater than 0. It refreshes asynchronously every N minutes.
  - `TransformationService` timeouts are 15 s with no cache and 5 s when a stale cache exists.
  - `getRemoteGaia` (prototype bean, for diagnostics) calls `/bundle`, `/actuator/info` and `/templates`.
  - Nothing in the HTTP beans contacts Gaia FE at Spring startup. Only the Cassandra cache factory does I/O at startup (note 05 §C3).
- **Client id and scope** (Literatum props): `gaia/id=${macro/CVS_BRANCH}` (the source branch) and `gaia/scope=${macro/product-name}`.
- **Endpoint** (deployconf XSL `gaiak8s`, `xslconfig/deployconf.xsl:1981-2139`): `http://<account>-<service_cluster>-gaia-int.<env-defaults/ingress_dc-gaia>`. For example beta gives `http://midtierbeta-dc-beta-gaia-int.gaia.literatumonline.com`, and `:80` is stripped. The mapping has overrides: readonly/rorehearsal use `literatum`, staging `pericles` uses `midtierbeta`, and `external_connection=true` gives `https://…-gaia.` on port 443. Dev-productivity clones (`source_env`) use `https://<source_env>-<GAIA_CLUSTER>-gaia.literatumonline.com` (`gaia-endpoint-template`, fed by `redeploy.py:304` env `GAIA_CLUSTER`).
- **Cache key includes the template timestamp** reported by the FE (`LiteratumTransformationTemplateLocator.getCacheKey`: id + scope parts + timestamp). A new bundle means a new timestamp, which means new versioned Cassandra tables. That is the churn `gaia_cleanup` removes (note 05 §C6).

### 1.3 How bundles are built, shipped and loaded (Confirmed, except where tagged)
1. The axel war is released to **GAR** (`us-central1-maven.pkg.dev/atypon-artifact/maven/com/atypon/axel/<v>/axel-<v>.war`). How axel itself is built was **not read**.
2. Deploy Server `GaiaProductSetAxelVersion` / `ChangeGaiaVersion` edits deployconf `bundle_version` (note 01).
3. **GaiaDeploy** is inserted in a ProductRelease/Refresh when `conf.getGaia(product,family) != null` and the account is not readonly/rorehearsal (`PreExecuteVisitor.java:2797`). For a DC cluster (`k8s_cluster="dc-gaia"`, `ActionHelper.isDCGaia`) it runs `ansible-actions -s gaia -n <service_cluster> -a deploy -e force_recreate=$recreate` (`actions.xml:1191`). $recreate is a UI checkbox, default false. This is **per cluster**: it re-renders the config for **every** product on that cluster, not just the one being deployed.
4. ansible-gaia `deploy` runs these steps:
   1. `check-bundle.yml` renders `config.xml`, regex-extracts `\d+\.\d+\.\d+` and sends a HEAD to **GAR** for each version (expects 200).
   2. `app-deploy.yml` renders again and runs xmllint. If the container is running and not forced, it `docker cp`s the config to `/tmp/configs/config.xml`. Otherwise it creates the container (`TYPE=dc`) and then writes the config through `docker exec`.
5. Inside the container (`start.sh`, `TYPE=dc`), `updater.sh` runs every 10 s. When the md5 of `/tmp/configs/config.xml` differs from `/mnt/gaia-fe/config.xml`, it runs `configparser.py | xargs configinit.sh`:
   - downloads each `axel-<v>.war` from **Nexus** (`https://nexus.atypon.com/nexus…/passport/…`, with credentials);
   - `jar xvf` and `mv WEB-INF /mnt/gaia-fe/bundles/<v>`;
   - copies the config;
   - `rm -rf`s bundles no longer referenced.
6. gaia-fe `MultipleBundleDeployment` (profile `multi`) has a `ConfigWatcher` that polls the config.xml mtime every 1 s. On a change it builds a new selector and repository, calls `TransformationTemplateScanner.scan(bundles/<name>)` for any bundle not already loaded, and then swaps them in (repository first, then selector).
   - The scanner registers templates by walking `axel/target/{wcms,rcms,wileyml,jats,json}/api` (Axel v2) or `axel/{api,rcms/api,…}` (v1): `base.xsl`, then `products/<scope>.xsl`.
   - HTML templates are `abstract`/`fulltext`/`pdf`. rcms gives `rcms_*`. There are also `wileyml`, `jats` and `json`.
   - **XSL is compiled lazily** (`Suppliers.memoize`) on the first request for each template.
7. The config.xml shape (`config.xml.j2`) is:
   - root `bundle` = the cluster `bundle_version` (the default);
   - `scopes/<product>/bundle` = the product bundle_version;
   - `clients/<source-branch>` = bundle_version;
   - `clients/<previous_source_branch>` = previous_bundle_version.

   The branch name is the `[-2]` element of the deployconf `<source>` path. It matches `gaia/id=${macro/CVS_BRANCH}` on the Literatum side, so web hosts still on the old branch keep the previous bundle during a rolling deploy.

### 1.4 What GaiaCompatibilityCheck actually verifies (Confirmed, `PreExecuteVisitor.java:3137-3200`)
- **Inserted when:** account `literatum` (prod only), not SwitchToReadonly, and display action null or ProductRefreshDeploy (`:2750-2752`). It is the first child.
- **Logic:**
  - pre-prod site → `Cancelled` ("Skipped for pre-prod sites");
  - no gaia on prod → `Cancelled` ("Gaia is not configured on Literatum");
  - no gaia on staging → **Failed** ("Gaia is not configured on Staging");
  - otherwise it compares prod against **staging only** (never beta) on:
    - (a) product `bundle_version`, and
    - (b) Gaia image tag (from ConfHelper, presumably the service cluster's `image_tag`).

  Any mismatch → **Failed**. Log lines: `Mismatch Gaia bundle version between literatum <x> and Staging <y> for <p>` / `Gaia image tag matched …`.
- **The staging family** comes from `stagingConfHelper.getFamilyForProduct(product)`, which is a single family.
- **It does not check** that the bundle exists, that Gaia FE is up or has loaded it, `previous_bundle_version`, or beta.
- **Snapshot today (deployconf `ad1c87a`):**
  - image tags match (dc-prod 1.6.7 = dc-stag 1.6.7);
  - **61 of 66** prod gaia products have `bundle_version` ≠ staging, so their ProductRefreshDeploy on prod fails this gate until prod's bundle is set to staging's (e.g. prod 2.2.85.1 vs staging 2.2.88);
  - `nato` and `chrysalis` have gaia on prod but not on staging, so they always **fail**.
- **Latent bug:** `isMatching` guards with `first != null || second != null` and then calls `first.equals(...)`. A null prod value with a non-null staging value throws an NPE. Both null gives a silent `false`, i.e. Failed with no "Mismatch" line. (Inferred from code. Beta `lean` C48 has no `bundle_version`. It is not on prod, so it is not hit today.)

### 1.5 What GaiaDeploy actually verifies (Confirmed)
- **Before:** every `x.y.z` in the rendered config HEADs 200 on **GAR**, and the rendered XML is well-formed.
- **Success text:** the playbook rc through `$util.ansibleCheckExitCode()`, or `COMPLETED SUCCESS` / `gaiadeploy execution success` (`actions.xml:1202-1203`).
- **Not verified:**
  - that the bundle was downloaded from **Nexus**, which is a different repository from the GAR one checked;
  - that configinit succeeded (it runs asynchronously in the container loop after the playbook returns);
  - that gaia-fe loaded the bundle;
  - that `/bundle?scope=<p>&client=<branch>` returns the new version.

  The Docker healthcheck is only `/actuator/health`.
- **Regex hole:** `regex_findall('\d+\.\d+\.\d+')` turns `2.2.85.1` into `2.2.85`. For every 4-part version (54 prod products, e.g. `2.2.88.1` on staging `aps`) the GAR check tests the **3-part parent** version. A missing `2.2.88.1` passes the gate if `2.2.88` exists. (Confirmed by running the regex.)

### 1.6 Library 1.7.3 (pinned) vs 1.7.4 (master) (Confirmed from diff)
- 1.7.4 adds optional input documents (LIT-540148):
  - `DocumentIds(entry, required, optional)`;
  - the registry `documents/<doc required="false">` attribute;
  - the error text changes from `Unknown document '<id>' for source '<src>'` (1.7.3) to `Document with ID '<id>' not found in source '<src>'` (1.7.4).
- 1.7.4 also stops unknown replacer names from being invoked (LIT-612942).
- `DocumentIds` constructors changed (`(String, String...)` → `(String)` / `(String, List, List)`). A Literatum bump to 1.7.4 is **source-incompatible** anywhere Literatum builds `DocumentIds` itself. None was found in lit-2610 (grep for `new DocumentIds` gave 0 hits), but `RemoteTransformation.setDocumentIds` consumes the type.

### 1.7 Gaia failure modes
See the table in §5. Main points:
- **Build:** no Gaia build step exists in the product build. The library is a plain dependency. A missing `gaia-*:1.7.3` in GAR/mavenLocal fails dependency resolution.
- **Startup:** only the Cassandra cache factory (note 05). The HTTP client is lazy.
- **Deploy (GaiaDeploy):**
  - GAR 404 → check-bundle fails;
  - xmllint failure;
  - docker errors;
  - otherwise success, even when configinit then fails in the container.
- **Runtime:**
  - The bundle dir is missing on the FE (Nexus lacks it or configinit failed). `scan()` throws `NoSuchFileException`, `ConfigWatcher` logs `Fail to check config file changes`, and **the old selector and repository stay in service**. The mtime has already been recorded, so the refresh is not retried until config.xml changes again. Literatum silently keeps rendering with the old bundle. (Inferred from code.)
  - XSL compile error in the new bundle. The template metadata comes back `status: unavailable`, and Literatum `HttpTransformationTemplateLocator.ensureReady` throws `GaiaException: Template with name: <id>, scope: <scope> is not available. Error: <xsl errors…>`.
  - `/bundle` with no match. The FE throws a bare `GaiaException`, which becomes a 500.
  - Transform returns non-200. Literatum gets `GaiaException(<json message>)`.
  - Timeout: `GaiaTimeoutException: Timed out while waiting for transform to complete` (15 s). `GaiaRenderer` counts `TIMEOUTS_ERRORS` and logs `Error executing Gaia transform with attributes: …`. The Reader path wraps it as `Error executing Gaia transform for doi <doi>`.
  - Scope mismatch (Literatum `macro/product-name` ≠ deployconf product name) or client mismatch (CVS_BRANCH ≠ the `[-2]` element of `<source>`). The selector falls back to the product bundle, then to the **cluster default** bundle (e.g. dc-beta 2.2.54, dc-stag 2.1.23). Old templates render with no error. (Inferred.)

---

## 2. cms-root (source of `com.atypon.literatum:cms-apis`)

### 2.1 Layout (Confirmed)
- Maven reactor `com.atypon.literatum:cms-root` with one module, `cms-apis`. The model enums live in `com.atypon.cmsapis.model.enums` (e.g. `CmsContributorRole`). There are also beans, suppliers and a registry (README).
- Parent `com.atypon:atypon-root-pom:2411.0.22` on both master and lit-2610. Java 21.
- Depends on **`com.atypon.passport:core:${core.version}=2510.0.1`**. That is passport core, not id-core, and it is also an aspect library.
- Downstream consumers updated on release: pcms, cms-ps-wiley, cms-ps-elsevier, and literatum `atypon/literatum/versions.properties` → `cmsapisVersion`.

### 2.2 Version lines and release (Confirmed)
- **One version line per branch.** Master pom is `4.0.0-SNAPSHOT` and releases `4.0.0.N`. lit-2610 is `3.0.18-SNAPSHOT` and releases `3.0.18.N`. Older lines: 3.0.10 (lit-2610-maint-260901 pins `3.0.10.7`), 2.0.288 (lit-2410 pins `2.0.288.1`).
- The 4th digit is appended by the `multimodule-release` "releaser" plugin (`releaser:release`). Tags are `cms-apis-<v>` and `cms-root-<v>`, not the `v@{version}` of maven-release-plugin. `git ls-remote` shows 794 `cms-apis-*` tags. The line counts are: 29 × `4.0.0.*` (latest **4.0.0.28**), and `3.0.18.0`–`3.0.18.2`.
- **master releases through GitHub Actions** (`release.yaml`, workflow_dispatch). After release, the `update_repositories` matrix checks out each target **at `ref: master`** and opens a "cms-apis released" PR. For literatum it runs `sed s@cmsapisVersion=.*@cmsapisVersion=<v>@` with labels `automated_pr, skip-forward-merge`.
- **lit-2610's `release.yaml` is a stub** (`echo "not ready yet"`). lit-2610 releases through **Jenkins** `jrelease.gdsl` (`branch='lit-2610'`, `litBranch='lit-2610'`, optional `updateLiteratumSource`). That produces the "Cms-apis released module." commits directly on literatum lit-2610:
  - `0af9c92337` (06:16Z): `3.0.18.0` → `.1`
  - `9ddd77bfa8` (10:21Z): → `3.0.18.2`
- `ForwardPRCreate.yaml` forward-ports merged `lit-NNNN` PRs labelled `cms-forward-merge` to `vars.MJR_BRANCHES_LIST`.

### 2.3 The ADVISER case, re-verified today (Confirmed)

| Ref | Commit / time (UTC) | `ADVISOR`/`ADVISER` in `CmsContributorRole` |
|---|---|---|
| `cms-apis-3.0.18.1` | `777ddad` 05:52 | absent |
| `cms-apis-3.0.18.2` = lit-2610 HEAD | `b3d8e23` 09:39 (#499) | **present** |
| `cms-apis-4.0.0.28` | `735e98c` 06:08 | absent |
| cms-root master | `401f9d50` 10:12 (#501 `3118cf4d`) | **present, but unreleased** (no `4.0.0.29` tag exists as of this run) |

Literatum pins (GitHub, fetched today):
- lit-2610: `cmsapisVersion=3.0.18.2`, which compiles.
- master (`0c62d01577`, 2026-09-25T12:04Z): `cmsapisVersion=4.0.0.28`, and `ContributorsIndexingUtil.java:210` still has `case ADVISER -> …`. **Master still fails `:literatum:compileJava`** until cms-apis 4.0.0.29+ is released from master (at or after `401f9d50`) and the auto-PR is merged.

Why the lines diverged:
- The fix was made on lit-2610 first, released by Jenkins, and pinned by a direct commit.
- The master cms-root change landed 30 min later, but no master release was dispatched.
- Meanwhile Literatum's forward cherry-pick (`0b07e5a7c6df`, note 05 §D) carried the *usage* to master.

So a pin mismatch looks like `error: cannot find symbol … variable ADVISER location: class CmsContributorRole` in `:literatum:compileJava`. Because `publish/` is compiled by `:literatum`, it breaks **every product** built from that branch.

---

## 3. id-core

### 3.1 What it is (Confirmed)
- "Information Discovery" core: reactor `com.atypon.id:core` with modules `id-core`, `id-solr` (Solr client) and `id-solr-proxy` (gRPC multi-tenant Solr service).
- Packages: `com.atypon.id.core.{index.fields,index.model,solr,synonym,analysis,cache,redis,…}`. These are the Solr index field model (e.g. `index.fields.Contributor` with `enum ContribType{author, reviewer, editor, external_reviewer, other, adviser, all}`), plus analyzers, synonyms and the Solr client.
- **There is a single `master` branch** (plus `master_jdk_21`). Release lines are `core-26xx`/`core-27xx` tags from master, released by GHA `release.yml`:
  - modes `dry-run`/`test`/`release`;
  - `test` makes versions like `<actor>-<run_id>-<ver>` (those are the `test-release/*` tags);
  - on success it dispatches `id-solr-plugins` and `id-kafka-messaging` with `id-core-version`, as part of a chain started from `id-root-pom`.

### 3.2 How Literatum gets it (Confirmed)
- **Not declared directly.** Literatum declares `com.atypon.id:{federated-search,id-search-client,id-search-core}:${searchVersion}`, `id-robot`, `id-atm-process`, `kafka-messaging`, `id-cf-cassandra` and `ab-testing` (`literatum/build.gradle:313-446`). It **excludes** `id-core` from both `literatum-cms` deps (`:486,:492`).
- The `id-core` version comes from **id-search's** root pom property `id-core.version` (`atypon/id-search`, **not in the list**):
  - lit-2610 `searchVersion=2610.0.25` → **id-core 2610.0.11**;
  - master `searchVersion=2710.0.5` → **id-core 2710.0.5**.

  Other ID artifacts can pull different id-core versions, and Gradle picks the highest. What actually resolves was **Unconfirmed**; check it with `:literatum:retrieveVersions --dependencies com.atypon.id:id-core`.
- Usage: 688 Literatum source files import `com.atypon.id.core.*`, mostly `index.fields` (671), `solr` (120) and `index.fields.utils/attributes`. No Spring XML references it.
- `ContribType.adviser` is present in `core-2610.0.11`, `core-2710.0.5` and master. So on both branches the id-core half of `ContributorsIndexingUtil:210` resolves. Note 05's open "exact id-core version" question is now closed.

### 3.3 Failure modes (Inferred unless noted)
- **Build:** a `searchVersion` bump moves id-core. Renamed or removed `IndexField` constants show up as `cannot find symbol … class <X>` in `publish/…/search/solr/…` under `:literatum:compileJava`, which again breaks all products. If a test-mode version (`<actor>-<runid>-<ver>`) ever lands in a pin, it resolves only if that artifact was published.
- **Startup/runtime:** mixed id-core versions pulled by different ID libs, compiled against different field sets, give `NoSuchFieldError`/`NoSuchMethodError`/`NoClassDefFoundError: com/atypon/id/core/...` at class init of indexing or search code. Typically this happens on the first index or search call or during consumer startup, not at Spring refresh.

---

## 4. root-pom (`com.atypon:atypon-root-pom`), reachable read-only

### 4.1 How Literatum consumes it (Confirmed, lit-2610 `9f8eb846e`)
- `atypon/build.gradle:78` has `parentPomVersion = "2610.0.7"`. It is exposed through `LiteratumPluginExtension.parentPomVersion`.
- `enforcedPlatform("com.atypon:atypon-root-pom:<v>")` is applied to `api`, `testImplementation`, `wars` and `aspectsourcesCompile` (`literatum/build.gradle:242-245`) and to `aspectjtools`/`aspectjrt` (`AspectJPlugin.groovy:48-49`). `BridgeAspectsPlugin.groovy:18` uses a plain `platform` for `aspects`.
- The root-pom readme says the same thing: "versions in `pom.xml` are enforced by Literatum build … if your project runs in the same JVM it will use versions declared here".
- The root-pom Jenkins job releases the pom and can commit the bump to Literatum. On lit-2610 those commits are `atyponci` "Atypon-root-pom version set to …", which change `atypon/build.gradle` only (+1/-1).
- Branch versioning: a major cut uses `YYMM.0.N` and master uses the cut + 1 (e.g. master `2611.0.5-SNAPSHOT`).

### 4.2 2610.0.5 → 2610.0.6 → 2610.0.7 (Confirmed)

| Version | Commit (root-pom lit-2610) | Literatum lit-2610 pin commit | Content change |
|---|---|---|---|
| 2610.0.5 | `b407c51996` 2026-06-23 | `af3d3c2f5c` 06-23 | Solr 9.10.1 (LIT-673028) |
| 2610.0.6 | `527351ec0c` 2026-09-24T08:05Z (PR #76 "Reapply LIT-643926", `9bd073af4c`) | `5b65a1f45c` 09-24T08:06Z | `scala.version 2.12.8→2.12.21`, **`akka.version 2.5.31→2.6.21`**, `alpakka.version 1.0.2→3.0.4` (akka-http stays 10.1.12). Managed: akka-actor/-typed/-cluster/-cluster-typed/-cluster-tools/-stream/-distributed-data/-coordination/-cluster-metrics/-slf4j/-remote/-protobuf/-persistence/-persistence-query `_2.12` |
| 2610.0.7 | `32686fbf9b` 09-24T15:58Z after revert `9a863f0517` (15:55Z) | `00eaa17329` 09-24T15:59Z | Revert of the above. `compare 0.5…0.7` differs **only in `<version>`/`<tag>`**, so 2610.0.7 ≡ 2610.0.5 in content. |

History repeats: the same Akka change went out in **2610.0.4** (`bb5befb9d8`, 03-31) and Literatum reverted its pin on 04-02 (`a17c9ac76d`). Neither revert message nor PR #76 states the reason.
- Literatum lit-2610 still pins `passportClusterVersion=2110.0.1` (passport-cluster-{broadcast,core,crdt,event-transport}), keeps `akka-stream-testkit_2.12:2.5.31` in tests, and enables Artery (`literatum.akka-cluster.props.xml:13`).
- Two plausible causes of the break with Akka 2.6 enforced (**Inferred**, the runtime break itself is **Unconfirmed** here):
  - binary incompatibility of passport-cluster 2110.0.1, compiled against 2.5, giving `NoSuchMethodError`/`NoClassDefFoundError` in `akka.*` at cluster start;
  - 2.5↔2.6 nodes failing to join each other during a rolling deploy.
- Which branch is affected: `lit-2610-maint-260901` (what staging runs) pins `2610.0.5`, so it was never exposed. Only builds of lit-2610 made between 08:06Z and 15:59Z on 09-24 carried 0.6.

---

## 5. Failure-signature table

| Signature (log text) | Where | Meaning / root cause | Status |
|---|---|---|---|
| `Mismatch Gaia bundle version between literatum <x> and Staging <y> for <p>` then GaiaCompatibilityCheck **Failed** | Deploy Server, prod only (`PreExecuteVisitor:3189-3200`) | Prod `<gaia bundle_version>` ≠ staging's. Set prod's bundle (GaiaProductSetAxelVersion) or deploy staging first. 61 of 66 prod products mismatch today. | Confirmed |
| `Mismatch Gaia image tag between …` | same | Cluster `image_tag` differs between prod and staging. They match today (1.6.7). | Confirmed |
| `Gaia is not configured on Staging` then Failed | same | Product has `<gaia>` on prod but not on staging (today: `nato`, `chrysalis`). | Confirmed |
| `Skipped for pre-prod sites` / `Gaia is not configured on Literatum` then Cancelled | same | Benign | Confirmed |
| NPE in `isMatching` during GaiaCompatibilityCheck | `PreExecuteVisitor:3191` | Prod value null, staging value not null | Inferred |
| GaiaDeploy fails at `Verify bundle versions exist remotely` (HTTP 404) | ansible-gaia `check-bundle.yml:21-31` | Axel war (3-part version) not in GAR | Confirmed |
| GaiaDeploy **passes** but pages keep the old XSL; container log `failed to verify bundle <v>` / `nexus url doesn't exists` | in-container `configinit.sh:8,14` via `updater.sh` | Bundle missing in **Nexus** (GAR was checked), or a 4-part version whose 3-part parent exists in GAR | Inferred |
| gaia-fe log `Fail to check config file changes` + `NoSuchFileException …/bundles/<v>` | `MultipleBundleDeployment.ConfigWatcher` | Bundle dir missing. The old config stays active and is not retried until config.xml changes. | Inferred |
| `The XML file ~/tmp/<cluster>-config.xml is invalid.` | `app-deploy.yml:59-62` | Bad value in deployconf | Confirmed |
| `GaiaException: Template with name: <id>, scope: <p> is not available. Error: <xsl msgs>` | Literatum `HttpTransformationTemplateLocator.ensureReady` | XSL compile error in the bundle (lazy compile on the FE, `Failed to parse template with name` in the FE log) | Confirmed |
| `GaiaException: Template with id and scope not found` | `TransformationService.getTemplate` | FE returned 404 for the template (not in the bundle, and no base) | Confirmed |
| `UncheckedExecutionException … NoSuchElementException: No value present` | `CachedHttpTransformationTemplateLocator.TemplateMetadataLoader` (`orElseThrow()`) | Same 404 case when the metadata cache window is > 0 | Inferred |
| `GaiaTimeoutException: Timed out while waiting for transform to complete` | `TransformationService.transform` | FE slower than `gaia/transformation-timeout-seconds` (15 s); `TIMEOUTS_ERRORS` metric | Confirmed |
| `Error executing Gaia transform with attributes: …` / `Error executing Gaia transform for doi <doi>` | `GaiaRenderer`, `ReaderGaiaUtil:76-79` | Wrapper around any of the above | Confirmed |
| `GaiaException: Request to Gaia FE failed with code <n> and response <msg>` | `GaiaHttpClient.template` | FE error (e.g. 500 from a `/bundle`/`/template` selector miss) | Confirmed |
| `GaiaException: java.net.UnknownHostException / Connect…Exception` | `GaiaHttpClient` | Endpoint from XSL wrong or unreachable (`<acct>-<cluster>-gaia-int.gaia.literatumonline.com`) | Inferred |
| `Unknown document '<id>' for source '<src>'` (1.7.3) / `Document with ID … not found` (1.7.4) | `TransformationService.getDocument` | Required input document (prime/info/aux/xlinks) missing for the item | Confirmed |
| Renders succeed but look old; no error | FE selector fallback | `macro/product-name` ≠ deployconf product name, or CVS_BRANCH ≠ `<source>[-2]`, so the cluster default bundle is used | Inferred |
| `ContributorsIndexingUtil.java:210: error: cannot find symbol … ADVISER … CmsContributorRole` → `:literatum:compileJava FAILED` | literatum master | `cmsapisVersion=4.0.0.28` lacks ADVISER. It needs cms-apis ≥ a master release at or after `401f9d50` (none yet). | Confirmed |
| `cannot find symbol` on `com.atypon.id.core.index.fields.*` in `publish/…/solr/…` | `:literatum:compileJava` | `searchVersion` bump moved id-core | Inferred |
| `NoSuchFieldError`/`NoSuchMethodError`/`NoClassDefFoundError: com/atypon/id/core/…` | runtime indexing/search/consumer | Mixed id-core versions from different ID libs | Inferred |
| `NoSuchMethodError`/`NoClassDefFoundError: akka/…` or cluster join failures with a **green** build | runtime passport-cluster | root-pom forced Akka 2.6 (2610.0.4 / 2610.0.6) under passport-cluster 2110.0.1 | Inferred (break not seen here) |
| Dependency resolution failure for `com.atypon:atypon-root-pom:<v>` | Gradle configure | Pin to an unpublished root-pom (e.g. a SNAPSHOT not deployed) | Inferred |

---

## 6. Model gaps (repos named by these flows but not in the list)
- `atypon/gaia-fe`: the service that actually loads bundles and serves the API. Partially read at tag `gaia-fe-1.6.7`.
- `atypon/axel`: bundle content and build. Not read.
- `atypon/id-search`: decides the id-core version. Pom property read only.
- The `ConfHelper` jar (`com.atypon.ops.common.confutils`): not available.
- The Deploy Server's Rundeck gaia-fe jobs (non-DC path): not in any repo.
