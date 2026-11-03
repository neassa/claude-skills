# 12 — Literatum runtime: request path, startup dependencies, search, caches

Written 2026-09-25 from read-only code reading. Nothing was built or run. No secret values were read; props/xml were printed through the filter `pass|pwd|token|secret|api_?key|_auth|authorization|credential|private|salt|://user:pw@`.

**Branch read:** `$LIT_REPOS/literatum-lit-2610` = `lit-2610` @ `9f8eb846e` (2026-09-25 14:58 +0300, "Merge PR #14304 LIT-683228"). Paths below are relative to `atypon/` unless prefixed. `AGENTS.md` and `docs/architecture/*.md` do **not exist on lit-2610**; they were read from the master clone `$LIT_REPOS/literatum` (`0c62d0157`).
**Other repos:** `DS/` = `$LIT_REPOS/deployserver`, `PT/` = `$LIT_REPOS/platform-tools`, `XSL` = `$LIT_REPOS/deployconf/xslconfig/deployconf.xsl`, **opstool** = GitHub `atypon/opstool` @ master (read with `gh api`, `DeployFamilyAction.java` last changed `5c494561b1`, 2022-01-02).

> **Model gap (unlisted repos):** the Deploy Server's web-server/heartbeat/warm-up checks are implemented in **`atypon/opstool`** (DeployFamilyAction; UrlFetch is in yet another lib `com.atypon.ops.common.utils`, not found anywhere locally) and the warm-up/essential tests are Selenium suites from **`qa-automation-xml`** (docker image `qaa/xml-master`). Neither is in the deploy-model clone list.

Not repeated here (see the existing notes): patch system (04), build/registry layering/Gaia Cassandra cache (05), pugrenderer internals (07/08), deployconf XSL key sources (06), DS action flow (01).

---

## 1. Web request path

### 1.1 Bootstrap order (who registers what)
`bridge/src/resources/META-INF/web-fragment.xml` declares, in order: `StartupListener` → `SessionMonitor` → `WebContextLoaderListener` (child context `/WEB-INF/web.spring.xml`) → `CustomWroServletContextInitializer` → `StartupCheck`. Error pages: 404 → `/templates/jsp/pb2/404.jsp`, 500 → `/templates/jsp/pb2/500.jsp`.

- `StartupListener.contextInitialized` (`publish/src/java/com/atypon/publish/acs/StartupListener.java:20-47`): defaults `server.type=web`, `JavaEE.register(context)`, then `new WebMain().run()`. Any Throwable → `Lot.LITERATUM.fatal(...)` and `RuntimeException("[StartupListener] Error initializing Literatum")` → **the Tomcat context fails but the JVM keeps running** (every URL then 404/503 from Tomcat). Note that most init failures never reach this catch because `Main.run` calls `System.exit(1)` first (§2.1).
- `JavaEE.register` (`literatum/src/java/com/atypon/literatum/web/JavaEE.java:347-418`): servlets/filters/mappings come from registry `web/servlets`, `web/servlet-mappings`, `web/filters`, `web/filter-mappings`, `web/init-parameters`. Every filter is registered as a `FilterDecorator` with init param `delegate=<class>` (`:373-376`). A mapping whose filter/servlet name is not registered is **silently skipped** (`:387-389`, `:400-403`). Example on lit-2610: base `web.props.xml:121` maps `securityChecksHeadersFilter` and `:140` maps `sessionLocalPersonaFilter`, neither defined in `web.props.xml` (they must come from other overlays or are no-ops).
- Mapping names are registry keys, so an overlay can **replace** a base mapping: PB2 `midtier.props.pb2.base.xml:565` reuses `$42000` for `PageBuilderEditorFilter` (`/pb/*`), replacing the base `$42000 httpSecurityHeadersFilter` (which is also mapped at `$15059`).

### 1.2 Filter chain (base `literatum/conf/web.props.xml:118-153` + PB2 `product/midtier/conf/midtier.props.pb2.base.xml:557-567`)
| Order | Filter | What matters after a deploy |
|---|---|---|
| $8000 | `DebugHooksFilter` | `?<hook>=` diagnostics (`frontend/debug-hooks`) |
| $8500 | `CloseConnectionWhenLockedFilter` (`literatum/src/java/com/atypon/modules/servlet/CloseConnectionWhenLockedFilter.java:16-22`) | while heartbeat is **locked** (`HeartBeatServlet.isUnlocked()==false`) every response gets `Connection: close` |
| $9500 | `DomainInitializerFilter` | binds the domain/website context |
| **$10000 (PB2)** | **`HttpCacheFilter`** | **styleguide asset proxy to pugrenderer** (§1.5) |
| $11000/$11100/$11250 | `ClientIpFilter`, `RequestDataFilter`, UA throttling | |
| $11500 | `IntranetFilter` on servlet `heartbeat` | `/heartbeat` from a non-private IP → 401 (`publish/.../IntranetFilter.java:56-66`) |
| $15030/$15037/$15040 | `BlockCheckerFilter`, `PageBuilderFilter` (PB2), `SessionFilter` | |
| $40000/$41000 | `SsoFilter`, `BlobStorageFilter` | |
| **$45000** | **`DispatcherFilter`** (`dispatchers="REQUEST"`) | terminal for service URLs |
Servlets (`web.props.xml:38-88`): `file` = `FileServlet` on `/` (catch-all static), `/ControllerServlet`, `/heartbeat/*`, `/ops/deployment`, `/wat/*`, `/jsJawr/*`, `/cssJawr/*`, `/api/soap/*`, `/registryQuery`, … PB2 adds `springServlet` on `/pb/*`, `/sd/*`.

### 1.3 Normalizer → ControllerServlet → ActionController → Action
1. `ServiceFilter.doFilter` (`literatum/src/java/com/atypon/literatum/action/ServiceFilter.java:39-58`, 84-93) sets charset, runs the normalizer once per request (cached as request attribute `ServiceFilter.RequestNormalizerReply`). Not a service → chain continues (FileServlet etc.).
2. `CompoundNormalizer.normalize` (`literatum/src/java/com/atypon/literatum/customization/CompoundNormalizer.java:38-170`), order: URI ending `/undefined` → service `gone` (410); `IntrusionDetection.isSuspicious` → redirect to the FBI cyber page with `Lot.ACS.warn("Blocked a suspicious request. IP: ...")`; SFF normalizers; website-specific normalizer (`acs/WebsiteSpecificNormalizer`, multisite only); **product normalizer** `acs/RequestParamsNormalizer`; optional Highwire/Silverchair/Ingenta/MetaPress/Acropolis/LeanWorkflow; `DefaultRequestParamsNormalizer`; story normalizer; **PB2 normalizer** `frontend/page-builder-2/normalizer`. Config keys are read in `CustomizationSpringConfig.newCompoundNormalizerConfig` (`literatum/src/java/com/atypon/literatum/customization/CustomizationSpringConfig.java:93-110`): `acs/useHighwireNormalizer`, `acs/useSilverchairNormalizer`, `acs/useIngentaNormalizer`, `acs/useMetaPressNormalizer`, `acs/useAcropolisNormalizer`, `leanworkflow/enabled`, `acs/RequestParamsNormalizer`, `acs/SFFNormalizer`, `frontend/page-builder-2/enabled` + `/normalizer`, `frontend/stories/enableCustomUri` + `/normalizer`.
   - A bad normalizer class name fails **at Spring startup**: `IllegalArgumentException("Failed to load RequestParamsNormalizer class; config path: <path>")` (`:113-119`) → KILLING THE SYSTEM.
   - A normalizer that throws at request time: `Log.error(Log.ACS, "Failed trying a normalizer <class>")` + `RuntimeException` (`CompoundNormalizer.java:189-193`).
3. `DispatcherFilter.doServiceFilter` (`literatum/src/java/com/atypon/literatum/customization/DispatcherFilter.java:34-54`): redirects first (`redirectIfNeeded`, `:56-127`). **If the Host header is not a known domain** (`getDomainFromContext()==null`) it answers **301 to the default host name** (`:92-109`); no Host header → 505 page `ERROR_HTTP_1_0`. Otherwise stashes service name/params as request attributes and **forwards to `/ControllerServlet`**.
4. `ControllerServlet.service` (`literatum/src/java/com/atypon/literatum/action/ControllerServlet.java:28-128`): HTTPS redirect for secure services; wraps in `ACSRequest/ACSResponse` from `ReqResPool`; `controller.dispatchRequest(...)`. Catch-all: **any Throwable → `Log.error(Log.LITERATUM, "Error dispatching request ", t)` and HTTP 404** (`:114-121`). Other outcomes: `IpBlockException`/`BlockException`/`IllegalStateException`/`WriteDeniedError` → 403 + error page; `ExcessiveRequestException` → `"Detected Excessive Request"`.
5. `ActionController.dispatchRequest` (`literatum/src/java/com/atypon/literatum/action/ActionController.java:154-705`): service lookup (`frontend/services`; unknown → `ServiceNotFoundException`, disabled → `ACSException("Service X is disabled!")`, `:248-259`); read-only check (`"Got WriteDeniedError when checking to see if read-only is enabled for X"`, `:262-271`); `ServiceACS.checkAccess`; `findAction`; `AntiForgeryToken.validate`; **`action.execute(context)`** (`:382`); response handling: FORWARD → `pbRender()` (PB2/PB3 page context defined → forward to `/pb2/renderPage.jsp` or `/pb3/renderPage.jsp`, `:725-740`) else JSP forward; missing page → `PageNotFoundException` and `"Requested page does not exist: ..."` (`:444-452`); REDIRECT; SERVICE. Action exceptions → `Log.error(Log.LITERATUM, "Exception from action detected!\n<logAction>", e)` + error page `PageKeys.ERROR` (`:627-660`); `AcsNotFoundException` → warn only.

### 1.4 How a request reaches Gaia
- Wiring: `literatum/src/java/com/atypon/literatum/gaia/GaiaFeBeans.java:10-163` (components `gaia-fe-base`/`gaia-fe`/`gaia-fe-pcms` from `midtier.props.gaia-fe*.xml`). `GaiaHttpClient` uses `gaia/id`, `gaia/endpoint`, `gaia/concurrent-request-count`, `gaia/socket-timeout`, `gaia/connect-timeout` (`:50-56,147-162`); `TransformationService` timeouts `gaia/transformation-timeout-seconds` (default 15) and `gaia/transformation-timeout-seconds-stale-cache-exist` (default 5) (`:21-31`); template-metadata cache `gaia/transformation-template-metadata-cache-window` (`:40-47`); repository from `gaia/transformations`; caches `gaia/caches` (eager Cassandra, note 05).
- **The Gaia HTTP service is not contacted at startup** by these beans (only the Cassandra cache is). It is first called on a render.
- Callers: `ReaderGaiaUtil.transform` (`publish/src/java/com/atypon/publish/frontend/reader/gaia/ReaderGaiaUtil.java:27-47`) → on `GaiaException` throws `RuntimeException("Error executing Gaia transform for doi <doi>")` → ActionController `"Exception from action detected!"` → error page. GraphQL `LiteratumXsltFetcher` (`publish/.../graphql/literatum/fetcher/LiteratumXsltFetcher.java:56-92`) resolves Gaia transformations **at bean init** when `websiteAdmin/frontend/axelEnabled` and a `graphql/literatum/xslt` entry has `type="gaia"`: a template missing from `gaia/transformations` → bare `RuntimeException` from `orElseThrow` (`:85`) at startup → KILLING THE SYSTEM with no message text.
- Diagnostics: service `showGaiaStatus` (`midtier.props.gaia-fe.base.xml:14`, `ShowGaiaStatusAction`, login required); `RemoteGaia` prototype bean calls `client.bundle`, `fetchGaiaFeVersion`, `templates` (`GaiaFeBeans.java:95-145`); `GaiaDebugHook`.

### 1.5 How a request reaches pugrenderer (styleguide)
Two paths, both through the `frontendNodeJs` connection (`literatum/conf/spring/frontend/nodejs.xml:6-9`, `NodeJsFactory.java:21-44`):
- **Config keys:** `frontend/nodejs/enabled` (base default is spelled `<booolean>` at `literatum.props.xml:12056` and `midtier.props.pb2.ux3.xml:50`; deployconf XSL writes a correct `<boolean name="enabled">true` at XSL 561-562/638-639/719-720, so deployed envs are fine; how the registry treats the typo is Unverified), `frontend/nodejs/address/$n` (from deployconf `pugrenderer-cluster`), `frontend/nodejs/product-name` (= `${macro/product-name}`), `frontend/nodejs/product-version` (= `SG-${macro/build/branch}` in ux3 midtier, overridden by deployconf `styleguide/version`), `frontend/nodejs/so-timeout` (1000 ms base), `frontend/nodejs/implementation-factory` (`loadBalancedPooledHttpServiceConnectionFactory`), `frontend/nodejs/blackList/{firstFailBackOff,nextFailBackOff,failureCountThreshold}` (3s/30s/10), `frontend/nodejs/ux3CachingEnabled`, `ux3AsyncRenderingEnabled`, `ux3AsyncRenderingMinDropzoneWidgets` (5), `extensionsToForceCacheControl`, `frontend/HttpCacheFilter/styleguideProxyEnabled`.
- `enabled=false` → `DisabledServiceConnection`, every call throws `"Node.js is disabled (/frontend/nodejs/enabled)"` (`DisabledServiceConnection.java:51`). Empty address list → `IllegalArgumentException("At least one address is required")` **at Spring startup** (`NodeJsFactory.java:33-35`) → KILLING THE SYSTEM (this is what note 06 D18 "empty frontend/nodejs/address" turns into).
- **Static assets:** `HttpCacheFilter` ($10000) matches `^((.*/releasedAssets)|(/specs/products/[^/]+))(/.+)$` (`literatum/src/java/com/atypon/modules/servlet/HttpCacheFilter.java:50,97-105`) and proxies to pugrenderer `GET /?p=<product-name>&v=<product-version>&r=<resource>` (`:169-227`), copying status/headers/body (errors ≥400 get `Cache-Control: no-store`). **Any exception (renderer down, all nodes black-listed) → plain 404 with no log line** (`:225-227`).
- **Widget rendering:** PB2 widget → `NodeJsJadeRenderer` (`bridge/src/java/com/atypon/frontend/pagebuilder/extensions/impl/jade/NodeJsJadeRenderer.java`) → `Ux3ServiceImpl.renderSync/renderAsync` (`literatum/src/java/com/atypon/modules/ux3/impl/Ux3ServiceImpl.java:53-62,479-538`) → `POST /?c=<component>[&t=<template>|&raw=true]&p=&v=` (or legacy `/?f=`) with JSON body. Other calls: `/templates?c=`, `/version`, `/early-hints` (errors ignored), GraphQL associated files `/?c=&t=&e=` via `ux3GqlCacheService`. Non-prod only: cookies `sg_version` and `pug_address` override version/renderer.
- **Failure behaviour** (`literatum/src/java/com/atypon/literatum/frontend/nodejs/LoadBalancedPooledHttpServiceConnection.java:113-168`): hosts are grouped local/site/rest and round-robined; IO errors are retried up to `giveUpThreshold` (cluster size+1, or `failureCountThreshold`+1); a node is black-listed after `failureCountThreshold` failures or immediately on `HttpHostConnectException` (`"Blacklisting Node.js node <host>"`); each failure logs `"request to external service <req> failed: <host>. Wasted <n>ms. Exception: <e>"`; exhausted → `RuntimeException("request to external service failed, no more targets to try!")`. A **non-2xx reply is not retried**: `RuntimeException("Service replied with error.\n\tRequest URL: <host><uri>\n\tStatus Code: <n>\n\tReason: <r>")` — this is how a missing template (404) or pug render error (500) surfaces. Sync render failures propagate (`NodeJsJadeRenderer.java:70-76`); async (dropzone) failures are swallowed per widget: `"Failed to render widget async: <widgetId>"` (`:407-409`) → **the page renders with that widget missing**. How the external pagebuilder core handles a sync widget exception (error box vs whole page error) is Unverified (library not in repo).
- On `StyleguideDeployedEvent` (cluster broadcast) `Ux3ServiceImpl.receive` only wipes the local dir `<tempDir>/styleguideCache` (`:320-342`); log `"Failed to delete contents of <dir>"` on error.

### 1.6 What the Deploy Server's readiness actions actually check
| DS action | Command it runs | Literatum handler | What it proves |
|---|---|---|---|
| **HostWaitForWebServer** | sleep `webservercheck.freq` (30s default, `DS/src/.../DeployServerConfig.java:442`), then opstool `DeployFamilyAction -f <family> -t serverup -v` (`DS/src/.../SshExecuteVisitor.java:81-85`); success text `RESULT:SUCCESS`, rescheduled until `timeout.HostWaitForWebServer` (`SshExecutedVisitor.java:614-622`) | `GET http://localhost:<httpPort>/heartbeat?bg=1` (opstool `DeployFamilyAction.java:111` `ServerUp("/heartbeat?bg=1","",true)`) | expected body is **empty string**, so **any successful HTTP fetch passes** — including body `1` (DB down or not yet released). It proves only that Tomcat answers `/heartbeat` (i.e. the webapp context started). Whether a 404/500 counts as "fetch success" depends on `UrlFetch` (not available, **Unverified**). |
| HostWaitForHearbeat | opstool `-t lock` | `/heartbeat?id=lock&bg=1` | body starts with `Locked` |
| HostLock | opstool `-t lock` (note 01) | `sendLock` sets `unlocked=false` only if caller IP is private/loopback (`HeartBeatServlet.java:383-395`) | |
| HostUnlock | opstool `-t unlock -p <product>` (`SshExecuteVisitor.java:92-96`) | `/heartbeat?id=unlock&bg=1` → `unlocked=released=true`, `ServerHealthChecker.resumeChecking()` (`:373-381`) | body starts with `Unlocked`. **Bug:** opstool `Command` does `product = cmd.hasOption('p') ? null : value` (`DeployFamilyAction.java` Command ctor), so `-p` is ignored and **every product of that family on the host is unlocked**. |
| HostWarmupTest / HostEssentialTest | `PT/host_test.py -t warmup|essential` → docker `qaa/xml-master` (TestNG suites WARMUP / FUNCTIONAL, `host_test.py:89-101`) against `http://<host>.localhost.literatumonline.com:<port>` | real site pages through the full chain above | the only readiness check that exercises normalizers, actions, DB content, Solr, Gaia, pugrenderer. Failed warm-up tests become Cancelled and do not block (note 01). |
| (web JVM itself) | `StartupCheck` thread (`publish/src/java/com/atypon/publish/acs/StartupCheck.java:176-303`), only when `server/mode != dev` and `server.type=web` | polls its own `http://127.0.0.1:<process-web-base-port+http-port>/heartbeat` every 30s; on `1` ("Locked") calls `${deployserver/url}/unlock?account=&product=&host=&family=` (5 tries, 10s apart) | DS `/unlock` = `TestAsyncServlet` → creates **TestAsync** (warm-up + unlock chain) unless one is Scheduled/Executing (`DS/src/.../rest/TestAsyncServlet.java:30-62`). Logs: `"sending request to deploy server to start startup tests <url>"`, `"The deploy server accept the request..."`, `"...skipping the request, the test action already scheduled"`, `"deploy server did not respond <url>"` + email `"Unable to connect to deploy server to start startup test"`; if heartbeat already says `0`: stack trace `"The server started with status Unlocked"`. This is the background TestAsync that note 01 B9 could not find. |

**`HeartBeatServlet`** (`publish/src/java/com/atypon/modules/servlet/HeartBeatServlet.java`, mapped `/heartbeat/*`, behind `IntranetFilter`). `bg=1` is not read by the servlet. `id` values (`:81-125`): none/unknown → `checkDatabase`; `database`; `search` (runs `SearchApi.executeSearch("heart-beat-search", Fulltext=<query|work>)`, `0` only if hits>0, `:234-278`); `uptime`; `all` (`db,uptime,sessions,threads,lockedReqs,poolSize,search`); `sessions`; `threads`; `webserver` (same without search; used by `PT/restart.py:2005` health check); `release`; `lock`; `unlock`; `healthcheck&enabled=`; `achs` (`AtyponLiteratumWorksGreat`/`Not Finished`); `session&jsessionid=`; `cluster` (`PassportClusterServletHandler`); `prometheus`; `sysMonitor`.
- `checkDatabase` (`:158-196`) returns `1` unless **released AND unlocked**, then `0` if `DbConnMgr.getConnection()` gives an open connection; on failure logs `"HeartBeat Error"` + stack and returns `1`. It also toggles `ServiceStat.enabled`.
- State: `unlocked` starts as `acs/startWebServerUnlocked` (**true** in base, `literatum.props.xml:2293`); `released` starts false and, because `acs/heartbeatBasedOnTestResults=true` (`:2297`), is **only** set by `?id=unlock`/`?id=release` — the time-based release after `acs/startupDelay` (1800 s, `:2290`) applies only when that flag is false (`:202-214`). So after every restart the heartbeat answers `1` until the DS (HostUnlock/TestAsync) unlocks it; the load balancer keeps the node out until then.
- `ServerHealthChecker` (`literatum/src/java/com/atypon/literatum/action/health/ServerHealthChecker.java`), enabled by `?id=healthcheck&enabled=true` (`PT/healthcheckenable.py`): conditions `acs/server-health-locking/conditions` (`database-pool-health`, `memory-usage-health`, periods in `check-period-millis`, thresholds `max-database-pool-percentage`/`max-memory-usage-percentage` = 90, `literatum.props.xml:1528-1541`). A tripped condition schedules a heartbeat lock (heartbeat flips to `1`, node leaves LB) and mails the operator `"heart beat lock scheduled|triggered for product <p> on machine <h> for reasons: [...]"` (`:113-148`).
- `/ops/deployment?delay=&message=&inProgress=&broadcast=&force=` (`publish/src/java/com/atypon/modules/servlet/DeploymentServlet.java:106-168`): only for IPs in the `ATYPON_IPS` group (needs DB); sets a "deployment in progress" banner status, optionally broadcast to the cluster. Not a readiness check.

---

## 2. Startup of a web vs backstage server

### 2.1 Sequence and fatal paths (`literatum/src/java/com/atypon/literatum/Main.java`)
`Main.run` (`:68-104`): `ManagementService.start()` (Jetty on `system/management-service-port`; failure is **non-fatal**: `"cannot start management server"`) → `initialize()` → `DbConf.start()`. **Any Throwable** → mail `"Cannot start webapp!!!!"` → `abortSystemStartup` (`:384-393`) prints to **stderr**:
```
********** ERROR LOADING PRODUCT <product> **********
<stack trace>
********** KILLING THE SYSTEM **********
```
and **`System.exit(1)`** — the whole JVM (Tomcat) dies, so HostWaitForWebServer can never succeed. Success prints `>>>>> Server Initialization Complete <<<<<`; start prints the `____ Initializing Server ___` banner with Product/Type/PID (`:395-410`).

`initialize()` (`:153-209`), in order — each step's failure goes to KILLING THE SYSTEM:
1. `configureLogging`, `setDefaultLocale` (`"Language must be defined in acs/locale-info"`, `:276-286`), `system/properties`, `XslConstants.initialize`.
2. `verifyFileSystem` (`:337-352`): when `LOCAL_BASE` is set and `server/<type>/verify-file-system` is true, `server/verification-directory` (= `${content/journal-root}`) must exist → `"Failed to verify file system for directory <dir>"` (NFS/content mount missing).
3. **Spring** (`SpringAdapter`, `literatum/src/java/com/atypon/literatum/spring/SpringAdapter.java:96-142`): builds and eagerly refreshes all contexts from `components/`; any bean failure → `log.error("Cannot initialize Spring", e)` + `Error`. This is where every external dependency below fails.
4. `PreloadRunnable.preloadLiteratumTypes` / `preload()` (`literatum/src/java/com/atypon/literatum/acs/PreloadRunnable.java:14-28`): class preloading from `acs/preload-classes-{common,<server-type>,types}`; failure → `"Error preloading, aborting initialization"`; a missing class is only logged `"Cannot load class: <name>"` (`:74-75`).
5. `SearchConfigurationLoader.load(skip.db.loading)` unless `server.type=patch` (`:184-193`), then `"SearchConfigurationLoader.load() took : N ms"` (§3).
6. `WebMain.initialize` extras (`publish/src/java/com/atypon/publish/acs/WebMain.java:114-126`): `cache/cacheCitationMapAtServerStart` → citation map; **`DomainHandlerSingleton.getDomain()`** → with no website/thread context, `getRootPrimaryDomain()` throws **`DomainHandlingException("Primary root domain is undefined!!!")`** when the DB has no primary domain for the current `server/mode` (= `macro/build/mode`) (`literatum/src/java/com/atypon/literatum/acs/domain/DomainHandlerSingleton.java:167-175,187-197`); `XslCacheValidator.forceUpdateXslTimestamp()` unless read-only/Passport CMS.
7. `DbConf.start()` — DB-backed registry overrides.

Outside `Main.run`: `JavaEE.register` and the child `web.spring.xml` context (`WebContextLoaderListener`) fail the Tomcat context **without** killing the JVM; `SingletonPassportClusterProvider` can `System.exit(111)` later (§2.3).

### 2.2 Web vs backstage: what differs
- Spring contexts are the **same** for all roles: only `workflow-monitoring` and `paypal-tx-status-updater` carry `server-type=backstage` (`literatum.props.xml:25998-26009`); `kafka` is gated by `${index/kafka/enabled}` and `db-query-console` by `${db-query-console/enabled}`. Component list: `literatum.props.xml:25912-26016` (`last`, `robots`=`RobotsRegistrar`, `core-java`=`CoreSpringConfig`, `core`, `cms-java`, `cms`, `acs`, `ecommerce`, `customization-java`, `frontend-java`=`WebSpringConfig`, `frontend`, `bridge`, `analytics`, `search`, `kafka`, `cil`, `jwt`, `product` = `<product>.spring.xml`, …) plus midtier components (`gaia-fe-base` 275, `gaia-fe` 280, `gaia-fe-pcms` 281, `page-builder-2` 95, …).
- **Robots** differ: `RobotsRegistrar` (`literatum/src/java/com/atypon/literatum/spring/RobotsRegistrar.java`, `@Profile("!patch")`) turns `server/<server.type>/preload-robots` into Spring beans, so robot constructors run during Spring refresh. `web` (`literatum.props.xml:26025-26040`): SystemMonitorRobot, PublishWebAppRobot, CacheLoaderRobot, LogMonitorRobot, RegistryPathStatisticsRobot. `backstage` (`:26042-26077`): BackstageEngine, EditorBackstageEngine, NoBackstageEngine, QServerForWorkflowRobot, BounceMailRobot, CategoryIndexerRobot, TopicAcIndexerRobot, ExternalFilesRobot, CustomPagesIndexerRobot, ContentSuppressionIndexRobot, InplaceReprocessEngine_1, BackstageCacheLoaderRobot, AlertEngine, LicenseCacheRobot, OALicenseCacheRobot, ReasonerEngine, RegistryPathStatisticsRobot. `rbackstage`, `alert`, `backoffice`, `related` have their own lists.
- Overlays: `host.props.web.xml` (Quartz scheduler name only); `host.props.backstage.xml` (backstage Quartz scheduler, db-pool alerts off, customization cache fading window 30m, bot mitigation off, search computation-timeout 30s); `midtier.props.host.backstage.xml` (`cluster/akka/port = ${deployconf/process-backstage-akka-port}`).
- Only the **web** role runs `StartupCheck` and is `web-server=true`/`safe-for-read-only-mode=true`.

### 2.3 External services touched at startup
| Dependency | Where (class:line) | Config keys (names) | Startup failure → text |
|---|---|---|---|
| **MSSQL pools** `jdbc`, `robot`, `common`, `logging` (+ obfuscated, NewRelic) | `DataSourceManager.newDataSourceManager` (`literatum/src/java/com/atypon/literatum/persistence/DataSourceManager.java:75-123`), pools initialised async by 3 "DB pool initializer" threads; `initPool` `:248-262`; `getDS` waits for the future `:351-384`. First hard use: `CoreSpringConfig.coreLegacySingletons` → `Currencies.getAll()` (`literatum/src/java/com/atypon/literatum/spring/CoreSpringConfig.java:76-86`), then `DbConf.start`, domains | `database/dbPoolName`, `database/dbPool/{expirationTime,checkoutTimeout,monitorInterval}`, `database/<pool>/{dbDriver,dbURL,...}` ← `macro/database/*` (deployconf), `database/obfuscatedDbPool/*`, `database/reInitDbConnectionsPools` | `"No database pools are defined"`, `"default pool name must be `jdbc`"`; unreachable DB: `"Cannot get database name of pool <name>"` (logged, not fatal by itself) then the first query fails → `Cannot initialize Spring` → KILLING. **Warning:** `DataSourceManager.log` prints a `DB Pool Info` block to log and stdout whose `dbUserPassword` line contains the DB user **and password** (`:266-276`, password at `:271`) — treat startup logs/catalina.out as secret-bearing and filter that line. |
| **Akka / Passport cluster** (always) | `Broadcaster` bean always uses `BroadcasterTransportPassportCluster` (`CoreSpringConfig.java:32-41`), whose constructor calls `SingletonPassportClusterProvider.INSTANCE.getOrCreate()` (`literatum/src/java/com/atypon/literatum/cluster/BroadcasterTransportPassportCluster.java:8-10`) → `ClusterSystem(ClusterConfig.apply(registry))` (`SingletonPassportClusterProvider.java:30-86`). So the Akka cluster is created at startup **whatever the robot manager is**. Robot manager: `cluster/enabled-remote-robots` + `cluster/robots-manager-implementation` (`CoreSpringConfig.java:138-167`); base = `RobotManager_DbArmi`, but **prod `midtier.props.IBM.xml` includes `midtier.props.akka-cluster.IBM.xml` (`:17`) and IBM-stag/IBM-beta include `midtier.props.akka-cluster.IBM-nonprod.xml` (`:19`); both set `RobotManager_Akka`** → `PassportClusterSpringConfig` (answers docs/04 "Unverified") | `literatum.akka-cluster.props.xml`: `cluster/akka/{port (= deployconf/akka-port), server-host, account-id, seed-nodes, discovery, artery, aeron/*, max-message-size, broadcast/*, persistence/*, extra-config*}`; deployconf XSL 1390-1512 writes `cluster/akka/seed-nodes` (web+backstage `host:port`, port = http/proxy port + base port + 400) or `cluster/akka/discovery` (ZK `host:port` list from `<akka join_type="discovery" zk_cluster_name>`) | stderr **`"Exception initializing cluster, reason: <msg>"`** (`SingletonPassportClusterProvider.java:35-37`) → `Cannot initialize Spring` → KILLING (port in use, bad seed/discovery). Later: `"Cluster system was terminated , shutting down the application."` and **`System.exit(111)`** (`:88-96`). Robot lookups: `"cluster in bad shape, unable to get the robot for id: {}"` (`RobotManager_Akka.java:100`), `"Error during robot lookup by id"`. Root-pom Akka version drift (2610.0.6) breaks exactly this bean (runtime ref). |
| **Cassandra (Gaia output cache)** | `GaiaFeBeans.getOutputCacheFactory` (`GaiaFeBeans.java:70-88`) | `gaia/caches/cassandra/*`, `cassandra/nodes` | see note 05 §C4 (`AllNodesFailedException`, `GaiaException: Missing nodes`, `keyspace not defined...`) → KILLING, also in the patch VM |
| **pugrenderer** | `NodeJsFactory.getObject` — builds the pool only; **no request at startup** | `frontend/nodejs/*` | only config errors are fatal: `"At least one address is required"`; unknown host names are only logged `"Error getting InetAddress for url: <addr>"` (`LoadBalancedPooledHttpServiceConnection.java:71-72`) and the host is dropped |
| **Gaia HTTP** | not called at startup (§1.4) | `gaia/endpoint` | config-only failures (`LiteratumXsltFetcher` missing template → bare RuntimeException) |
| Solr/ZK, Kafka, Redis | §3, §4 | | |
| Content filesystem | `Main.verifyFileSystem` | `server/verification-directory`, `content/journal-root` | `"Failed to verify file system for directory <dir>"` |
| Domains (DB) | `WebMain` → `DomainHandlerSingleton.getRootPrimaryDomain` | `server/mode` (`macro/build/mode`) | `"Primary root domain is undefined!!!"` |
| SMTP | `Main.run` failure mail, `StartupCheck` mail | `host/smtp-server`, `admin/*` | swallowed |

Registry failures before any of this: `LiteratumRegistryFactory` `"Error loading property file from system property: <f> : Killing server"` (`literatum/src/java/com/atypon/literatum/registry/LiteratumRegistryFactory.java:121`) and `"failed to build"` (note 05 §B).

---

## 3. Search and indexing

Source: delegated read of lit-2610 plus my spot checks (`SearchConfigurationLoader.java:119-126`, `literatum.props.xml:25977-25980`, `versions.properties:66,136` confirmed). **Version caveat:** lit-2610 pins `searchVersion=2610.0.25`, `idKafkaMessaging=2610.0.11`, `coreVersion=2510.0.8`, but only **2410.x** jars are in `~/.gradle` (id-solr/id-core 2410.0.39, id-search-* 2410.0.93, kafka-messaging 2410.0.36, kafka-clients 2.8.0). Every library-side statement below comes from `javap` on those 2410 jars → **Unverified for 2610**.

### 3.1 Solr client
- Built by `com.atypon.id.core.solr.client.CloudSolrJClientFactory` (id-solr jar), one `CloudLegacySolrClient` per (collection, zkHost, SearchType), **lazily on the first request** for that collection. Callers use `LitSolrClient.newInstance(core)` → `getSolrClient(SearchType)`. **Not a Spring bean** (`literatum/conf/spring/search.xml:12` only component-scans `com.atypon.publish.backstage.do_fields,com.atypon.literatum.id`).
- Keys: `index/solr/zookeeper-connection` (empty default, `literatum.props.xml:13256`; deployconf writes `<zk hosts>/<name_prefix><path>`, XSL 1559-1562 — **a chroot is mandatory**, regex `(\S)+:(\d)+/(\S)+`), `index/solr/enabled` (false default `:13265`, XSL sets true), `index/solr/zookeeper-timeout` (defined twice, `:13255` string 30s and `:13259` duration 5s — which wins is Unverified), `index/solr/indexing-http-connection-timeout`, `index/solr/large-indexing-http-connection-timeout`, `index/solr/zkClientTimeout`, cross-product targets `search/collections/<prod>-<coll>/{zkHost,solr-collection-name}`, proxy `search/proxy/*`, remote gRPC search `search/service/{enabled,nodes,inbound-size}`.
- Cores: `SolrCoreModel` enum (JB, DO, DBPUBS, CTG, CONTENTSUPPRESSION, RELATED, CUSTOMPAGE, LICENSECACHE, RECOMMENDATIONS, autocomplete cores, …); collection = lower-cased name resolved through ZK aliases; enabled set = `search/collections/defaults/enabled`.
- **ZK/Solr is not contacted at startup.** `SearchConfigurationLoader.load` calls `ZkStateFactory.init()` only if Solr is enabled, and in 2410 that just builds a 30-min cache; the connect happens lazily in `getZkStateReader()`. → **Solr/ZK down at deploy time does not kill the JVM**; search fails per request.

### 3.2 `SearchConfigurationLoader.load()` (`literatum/src/java/com/atypon/literatum/SearchConfigurationLoader.java:119-150`)
Not wrapped in try/catch → any throw = KILLING THE SYSTEM. Fatal (config): `IndexLocaleHandler.loadPubDefaultLocale` → `"Could not get default index locale by language code: "` (`IndexLocaleHandler.java:111`); missing `search/adaptive-search-duration-window` or `search/max-boolean-clauses`. Non-fatal (DB, skipped with `-Dskip.db.loading=true`): `SeriesRelationshipLoader.preloadAll`, `TopicRelationshipLoader.updateStandardTaxonomies`, `FilterUpdate.updateSearchFilters` (each `Lot.SEARCH.error(msg)`), AB experiments `"An unexpected exception was encountered while loading ABExperiment data"`. Also JAXB check `"JaxbContext not loaded properly for indexing..."`, WordNet init, `LoggerHook` (`"LoggerHook failed to instantiate"`, library).

### 3.3 Runtime search failures
- `/action/doSearch` → `DoSearch` (`services.props.xml:834`, `publish/src/java/com/atypon/publish/search/configurator/api/DoSearch.java:79`) → `SearchApi.executeSearch`. The library catches everything: empty `ResultBean` with the error, **user is forwarded to the profile's `errorReturnPage`** (root: `/search/searchAdvanced.jsp`, `literatum.props.xml:17061`), not a 500. Logs (`literatum.log`): `"Unexpected error encountered while executing parametrized search task (<params>):"` + stack, and via `LitItlLogHook` `"Error encountered during search:\nqueryID: ..."`. Every query logs `"Search request with QueryID: {}, core: {}, searchName: {}"`.
- Library error strings: bad/empty zkHost `"<zk> is not a valid Zookeeper host. A valid zookeeper host has the following format : <host>:<port>,<host>:<port>/<chroot>..."` then `LitSolrClientException("Error creating client for collection:<c> , zkHost:<zk> , searchType<t>")` (repeats every request; null client is not cached); `"Failed to initialize CloudSolrClient."`; ZK refresh `"Failed to refresh <ZkState>. Keeping the previous state. Will try again after a few minutes."` (INFO level!); `"ZkStateReader no available from Zk"`; missing collection → message containing `Collection not found` / `Could not load collection from ZK` → `"Reset Solr clients for all collections zkHost:{}"` + `SolrOutdatedException`; `"Failed to operate on core:%s, error-code:%s"`; disabled core `"Not enabled collection:<c>"`; gRPC `"Search-service list is empty."`.
- Circuit breaker `SearchCircuitBreaker`: keys `search/circuit-breaker/{failure-threshold,success-threshold,delay}` (10/10/60s, `literatum.props.xml:16755-16758`) + per-core overrides; `"Circuit Breaker : Received exception %s with message:%s and cause:%s"`, then `"QueryID: <id>, Circuit-breaker is open"` — after ~10 failures searches fail fast for 60s even if Solr has recovered.
- Heartbeat `?id=search`: because SearchApi swallows Solr errors, a Solr outage appears as `"no search result found"` (stderr stack) and body `1`.
- Timeouts: `search/adaptive-search-duration-window` (30s, also Solr `timeAllowed`), profile `timeLimit` 30, `search/sub-search/computation-timeout` 15s, `search/literatum-search-pool/*` (backstage overlay: computation-timeout 30s).
- Log destinations (`literatum/conf/log4j2.xml`): `com.atypon.*` → `literatum.log`; `org.apache.zookeeper` → `zookeeper.log`; **`org.apache.solr` and `org.apache.kafka` have no logger → root (ERROR) → `unknown.log`**.

### 3.4 Kafka indexing producer
- `spring/kafka.xml` is empty (placeholder only); component `kafka` is gated on `${index/kafka/enabled}`, a key **defined nowhere** in the repo or XSL (resolution Unverified; harmless, no beans).
- Producer = `IndexingKafkaAPI` static init → `KafkaMessageProxyProd` → `MessageProducer` → `KafkaProducer` (kafka-messaging jar): **created lazily on first use of the class**, not at startup. Requires `index/kafka/brokerList` (empty default `literatum.props.xml:13145`; deployconf fills it only if the product has consumer servers, XSL 337-376), `deployconf/product`, `deployconf/family`; missing → `IllegalStateException("Registry value <key>, did not find into registry")` → `ExceptionInInitializerError` on first call, then `NoClassDefFoundError: Could not initialize class ...IndexingKafkaAPI` on every later call **until restart** (Errors escape `catch (Exception)` e.g. `DoIndexProc.java:190`).
- Producer keys: `index/kafka/producer/{max-request-size,request-timeout-ms (90000),buffer-memory-size,linger,batch-size,retries (3)}`; `max.block.ms` not set (kafka default 60s). App retry: `index/kafka/producer/scheduler/{reties (sic),retry-rate (5 min),cache-size (150 LRU)}`. Others: `index/kafka/{cores,cache-invalidation,dependentCores}`, `literatum.kafka.props.xml`. Gates: `backstage/intermediate-xml/send-to-kafka` (default false, XSL sets true with a broker list; `DoIndexProc.java:163`), `search/collections/defaults/indexing/enabled` (`IndexingConf.java:23`; XSL sets false for proxy-Solr envs).
- **Brokers down:** startup unaffected. `send()` blocks the calling thread up to ~60s on metadata; failures → `"Message added to kafka cache, key:{}, trID:{}, topic:{}, action:{} cache:{}"`, retried every 5 min `"Message rescheduled from cache key:{}..."`, after 3 tries `"Message failed sent to kafka, key:{}..., error:{}"` and **dropped**. Nothing persisted (lost on restart). `IndexingKafkaAPI.submit` swallows exceptions, so `DoIndexProc` still records `lastSuccessDate` → **index drift without a failed job**; repair with `DOSyncingTask`/`IndexSyncingTask`/`SolrVerificationTool`. Success log: `"Message sent to kafka, key:{}, trID:{}, topic:{}, action:{}, size:{}"`.
- Producers are mostly backstage (`DoIndexProc`, `AdminSearchUtil`, `SolrDatabaseIndexer`, bridge `ContentProcessor`, `LicenseCacheRobot`); model/event paths (`Publication.java:489`, `Article.java:6059`, `LicenseCacheEventListener.java:60`, `ContentCacheEventListener.java:74`) may produce on web too (Unverified).
- In-app consumer `KafkaConsumerDispatcher` (`literatum/src/java/com/atypon/literatum/id/KafkaConsumerDispatcher.java`, Spring `@Component`) is enabled only with `index/kafka/receiptCores` (only pericles); akka `RestartSource` with backoff, so a dead broker does not block startup. Log `"KafkaConsumerService enabled:{}"`.

### 3.5 Backstage search robots
`CategoryIndexerRobot` (`search/collections/ctg/indexing/periodic-global-refresh`, needs cluster lock + DB; `"CategoryIndexerRobot disabled"`), `ContentSuppressionIndexRobot` (`"Timeout while waiting for acquiring lock…"`, `"Failure during execution of scheduled indexing to CONTENTSUPPRESSION"`), `LicenseCacheLoader` (direct `LitSolrClient`), REST `SolrClientUpdateHandler` can switch ZK at runtime (`"Request to update Zookeeper cluster to …"`).

---

## 4. Caches

Source: delegated read of lit-2610 plus my spot checks (`RedisUtil.java:18`, `InvalidateCloudflareCache.py:23-26`, ansible-pugrenderer `origin/4.1:roles/released-assets/tasks/released-assets-invalidatecache.yml:3` confirmed). Library texts come from locally cached **Jedis 5.1.1 / spring-data-redis 3.2.x** (root-pom 2411.0.16). The 2610.0.7 root POM is not cached, so those texts are **Unverified for 2610**.

### 4.1 Redis
- **Client:** Jedis via Spring Data `JedisConnectionFactory`. There is no Lettuce or Redisson.
- **Central factory:** `RedisUtil` (`literatum/src/java/com/atypon/modules/redis/RedisUtil.java`).
  - The node list comes from the static `Conf.getString("macro/redis/nodes")` (`:18`).
  - One factory per service name, cached only on success (`:55-57`).
  - An empty list throws `IllegalStateException("There must be at least one redis node")` (`:65-66`).
  - It always builds a **cluster** config and calls `afterPropertiesSet()`, which connects at once (`:72-76`).
  - Key prefix: `<product>:<family>:` (`:28-41`).
- Unreachable cluster, library text: `"Could not initialize cluster slots cache."`; empty list: `"No nodes to initialize cluster slots cache."`. At runtime: `"No reachable node in cluster."`, `"Cannot get Jedis connection"`.
- **Only `macro/redis/nodes` is read by lit-2610 code.** deployconf also writes the following keys, but nothing in this tree reads them, so every feature uses the `macro/redis/nodes` cluster:
  - `macro/redis_am/nodes` (XSL 1125-1149)
  - `frontend/redis/redis-nodes`
  - `passportSessionManagement/redisCluster/startupNodes` (XSL 988-1048)
  - `passport/rdf-cache/redis-nodes`
  - `acs/redis/clusterNodes`

  An outside consumer is Unverified.
- Redis logging: real errors go to `literatum.log` or `report.log`. `redis.log` (logger `Redis`) gets debug output only.

| Feature (class:line) | When created | Redis down → |
|---|---|---|
| **RDF cache** `bridge/src/java/com/atypon/bridge/ResourceManagerConfig.java:53-111` (bean `resourceManagerConfig`, `bridge-cms.xml:1716`), when `passport/rdf-cache/impl=redis` (acm, marlin, was, pericles, deployconf `caching/cache[@type='rdf']`) | **Spring refresh.** Runs `INFO cluster` on the first node | **The only Redis path that kills the JVM**: `"No redis nodes specified!"`, `"unexpected response of 'info cluster' command"`, `"Invalid value of passport/rdf-cache/impl property: "` or a Jedis connect error → Cannot initialize Spring → KILLING |
| IAM/ACS `publish/src/java/com/atypon/publish/acs/redis/RedisCacheConfig.java:12-13` (used by `Cache.java:39-40` even with `acs/redis/enabled=false`, `LicenseCache.java:37`, `CheckCookieFilter`, `SSORedisTokenService`, `UserRequestHeadersRedis`) | static init on first class load | not caught. `ExceptionInInitializerError`, then `NoClassDefFoundError: Could not initialize class ...RedisCacheConfig` / `...LicenseCache` on license lookups (`LicenseServiceImpl.java:140,167`) **for the rest of the JVM's life**. Fixing Redis is not enough; the JVM must be restarted (inferred from code) |
| Cookie check `literatum/src/java/com/atypon/modules/servlet/CheckCookieFilter.java:80-175` | static | at startup: `"Failed to initialize redis cache"`, feature off. **Lost at runtime:** `"Error in CookieCheckerFilter"` + **HTTP 500** for first-time visitors without the test cookie |
| `SessionByUserService.java:89-106` (`acs/individual/max-concurrent-sessions`>1), `SessionByIPService`, `CartCheckoutByIPService`, `MediaCoverageService.java:295-306` (report.log), `RedisAiSearchRateLimiter` (`ai.spring.search.xml:11`), `RedisDulConfig` (`integration/dul/enabled`) | static or bean init, caught | `"Failed to initialize <Service>"`, feature off until restart. Runtime calls are caught in some classes (`"Failed to record cart checkout for IP: "`, `"Failed to get/record/revert AI search attempt for user {}"`, `"Failed to get licenses from cache"`) and not in others (SessionByUser, MediaCoverage `:311`, `DoiSummaryUserVoteService` which retries init on every call) |
| `AuditRedisConfig` (`acs/redis/enabled`), support `RegistryTree` (`registry-query-redis/enabled`=true), acm `RedisConfig` | static | not caught |

Other key names: `acs/redis/{enabled,connMaxNum,expirationTime,inMemoryExpirationTime,redis-key/*}`, `passport/rdf-cache/{impl,redis-pool-max,redis-key-prefix}`, `search/results-cache/redis/enabled`, `webadmin/audit/use-redis-storage`, `integration/dul/*`, `frontend/redis/*` (acm). Secret-bearing lines at `literatum.props.xml:2932`, `:2944`.

### 4.2 Local caches
- **Spring cache.** `defaultLiteratumCacheManager` is EhCache (`literatum/conf/spring/core.xml:16-22`). Bridge aliases it to Passport's `coreSpringCacheManager` (`bridge-cache.xml:9`). `LiteratumSpringCacheConfig` is loaded from `last.xml:13`. All 38 `CacheConfigBean`s are `type=LOCAL`.
- **EhCache.** `literatum/conf/ehcache.xml` defines 61 caches. All are in memory, with **no replication and no event listeners**. They clear only by TTL/TTI or restart.
- **AsyncCache family** (`literatum/src/java/com/atypon/modules/cache/`).
  - Configured by `cache/customization/<name>/*`, falling back to `cache/customization/default` (`literatum.props.xml:5625-5795`): `FadingMemoryCacheStoreProvider`, 30m window, `validPeriod` infinite, `invalidPeriod` 0s.
  - Invalidation is by cluster events: `ClusterEventBasedInvalidator` (errors only `Log.error(Log.CACHE, e)`), `DbChangeEventInvalidator` (a `ComplexUpdate` triggers `invalidateAll`), `DbCollectionInvalidator`.
  - Logs: `"Could not finish generating cache value for key: "`, `"Cannot convert a cached object, removing it"`.
  - Manual per-cache clear: `/action/cacheMonitor` (`services.props.xml:304`, `cacheInspect.jsp` `update=clear|start|stop`).
- **XSL/HTML disk cache.** `WebMain` calls `XslCacheValidator.forceUpdateXslTimestamp()` (`literatum/src/java/com/atypon/literatum/util/xml/XslCacheValidator.java:120-150`).
  - It touches only runtime XSLs under `<siteRoot>/templates/xsl` whose mtime is **on the build day**, then rewrites `xsl2_cache.info`.
  - Cached HTML is judged stale by timestamps (`literatum/src/java/com/atypon/literatum/util/CacheUtil.java:149-184`). On error it logs `"Cannot determine last modified date of content formats for publication "` and **serves the old HTML**.
  - Other logs: `"can't validate runtime XSL files"`, `"Failed to update xsl info map."`
  - Risk: XSL files dated other than the build day keep serving stale HTML.
- **PB2/UX3.**
  - `ux3OutputCache` (`page-builder-2.xml:947-956`, LOCAL, 10000 entries, LFU): the key is widget cache key + product name, validated only by `widget.getLastModified()`. The key does **not include the styleguide version** and the cache has **no StyleguideDeployedEvent listener**. After a styleguide-only change, rendered widget HTML stays old until a widget edit, eviction or restart. Gated by `frontend/nodejs/ux3CachingEnabled`. Its TTL default is Unverified.
  - `ux3GqlCacheService` (TTL 600s) runs `removeAll()` on StyleguideDeployedEvent (`Ux3GqlCacheHandler.java:56-63`).
  - `StyleguideManifestCacheServiceImpl` keeps the manifest when `websiteAdmin/frontend/resourceUrlRewrite/replaceStyleGuideAssets` and `styleguideProxyEnabled` are both set. An empty manifest is retried every 30 min. Logs: `"Request to styleGuide failed with status code "`, `"Error requesting styleGuide manifest"`.

### 4.3 Invalidation after deploy
- **`StyleguideDeployedEvent`** is fired only by `/action/styleguideDeployed` (`services.props.xml:159`, `requireSecure`, `ATYPON_IPS` only; `literatum/src/java/com/atypon/literatum/action/StyleguideDeployed.java:19-23`). It returns `{"status":"success","message":"SG Cache Cleared!"}`.
  - Listeners: `StyleguideDeployedListener` (refreshes the manifest and deletes `<siteRoot>/releasedAssets`), `Ux3ServiceImpl` (tmp dir) and `Ux3GqlCacheHandler`.
  - The only caller is the dev-path `PT/deployStyleguideNew.py:109-120`. It compares `status_code != '200'` (int vs str), so it always prints `"Cache action is not returning status 200, so cache might be not invalidated"`.
  - **The Deploy Server never calls it.** JVM caches are cleared after a release only because the web JVMs restart.
- **Broadcaster caveats** (`literatum/src/java/com/atypon/literatum/cluster/Broadcaster.java`).
  - Listeners registered with `includingLocal=true`, which covers all the styleguide ones, are fed only through the inbox. The inbox is filled only when remote broadcast is enabled. When it is disabled, the log reads `"Broadcaster Did not send (Broadcasting is disabled) [null]:…"` (cluster.log INFO) and even the local listeners do not run (`:209-227`).
  - The flag comes from `cluster/enabled-remote-events` && `cluster/enabled-remote-robots`, then `literatum.remoteBroadcastEnabled` (the patch VM sets it false).
  - The transport is fire-and-forget.
  - Errors: `"Failed receiving event"`, `"Failed receiving eveny in sync mode"` [sic], `"Error initializing broadcaster"`, `"Could not deliver all queued events"`. Backlog shows as `"Broadcaster.InBox.size=<n>"`.
  - Bug: `setThreadBroadcastEnabled` ignores its argument (`:249-250`).
- **Manual actions:**
  - `cacheMonitor`
  - `pbFlushPageCompiler` (`:565`)
  - `cmsInvalidateRedisCache?rid=` (`:2123`, RDF)
  - `updateArticleMetricsCache` (`:1884`)
  - `flushListBasedCustomizationSetLocator` (`:1691`)
  - backstage "Invalidate HTML caches" (`InvalidateHTMLContentActionImpl`; `"Cannot invalidate HTML cache of {0}"`)
  - diagnostics `/action/pugrendererInfo` (`"Pugrenderer Version: …"`, `"Renderer pool:"`, `"Error while loading pugrenderer info"`)
  - Literatum has no Cloudflare purge. `CdnManager.purge` is only for content uploads.
- **Deploy Server steps.** `PreExecuteVisitor.java:2906-2910` appends these when build+deploy runs and the product has a pugrenderer cluster. `DeployActionSql.java:453-459` otherwise cancels them with `"Styleguide or Pugrenderer cluster are not configured. Ignoring action"`.
  - **PugrendererInvalidateCache** (`DS/config/actions.xml:403-409`) runs `ansible-actions -s pugrenderer -a invalidatecaches` and is validated by `COMPLETED SUCCESS`.
    - The 4.x playbook calls `GET /invalidateCaches?r=<styleguide_versions[0]>&p=<product>'`. **The URL has a stray `'` after the product.** The renderer deletes only keys containing both strings, so this very likely clears nothing and still returns 200 (inferred).
    - `invalidatecaches.yml` exists on ansible-pugrenderer origin/4.0 and 4.1 but **not on master**.
    - The effective flush is the parameterless `/invalidateCaches` in PugrendererProductDeploy's `create-paths` role (`flushAll`, retried 5×3s).
  - **CfInvalidateCache** (`actions.xml:410-415`) runs `InvalidateCloudflareCache.py`. Its first `__main__` block prints `">>> Finished Invalidating Cloudflare Cache"` and exits 0 (`PT/InvalidateCloudflareCache.py:23-26`). The purge code after that is dead and even commented out. **A deploy never purges Cloudflare. The step always passes.**
  - **Secret hygiene:** `PT/InvalidateCloudflareCache.py:124` contains a commented-out literal that looks like a credential. It was not read or reproduced here. It should be checked or rotated by its owner.

---

## 5. Startup dependency → failure log text → meaning

| Dependency / condition | Log text (where) | Meaning / next step |
|---|---|---|
| Any fatal init error | stderr: `********** ERROR LOADING PRODUCT <p> **********` … `********** KILLING THE SYSTEM **********` (`Main.java:386-392`), mail `Cannot start webapp!!!!` | The JVM exited 1. HostStart may say "running", but HostWaitForWebServer never passes. Read the stack between the two banners |
| Spring bean failure | `Cannot initialize Spring` (`SpringAdapter.java:139`) | Look at the root cause in the stack (rows below) |
| MSSQL unreachable or bad creds | `Cannot get database name of pool <jdbc>` then SQLException → KILLING | DB/network or deployconf `database` entry. **The same log prints `dbUserPassword` in clear, so do not paste raw logs** |
| No DB pools configured | `No database pools are defined` / ``default pool name must be `jdbc` `` | Broken props chain |
| Akka cluster bind/join | `Exception initializing cluster, reason: <msg>` (stderr) → KILLING | Akka port in use (old JVM still up?), bad `cluster/akka/seed-nodes`/`discovery`, Akka jar drift (root-pom) |
| Akka cluster died later | `Cluster system was terminated , shutting down the application.` → exit **111** | Cluster down/partition; the JVM kills itself |
| Cassandra (Gaia cache) | driver `AllNodesFailedException`, `GaiaException: Missing nodes`, `keyspace not defined…` → KILLING | note 05 §C4. Also hits the patch VM |
| pugrenderer config | `At least one address is required` → KILLING | deployconf `pugrenderer-cluster` undefined (note 06 D18) |
| pugrenderer host name | `Error getting InetAddress for url: <addr>` | Host dropped silently. Remaining hosts are used |
| Normalizer class | `Failed to load RequestParamsNormalizer class; config path: <p>` → KILLING | Product props/class missing on this branch |
| Content mount | `Failed to verify file system for directory <dir>` → KILLING | NFS `content/journal-root` not mounted |
| Domains | `Primary root domain is undefined!!!` → KILLING | No primary domain in the DB for `server/mode` (`build.mode`) |
| Search config | `Could not get default index locale by language code: …` or a missing `search/*` key → KILLING | Config, not Solr connectivity |
| Solr / ZooKeeper down | nothing at startup | Not checked at startup. It shows later per request (§3.3) and in heartbeat `?id=search` = `1` |
| Kafka brokers down | nothing at startup | Producer is lazy. Later `Message added to kafka cache…` / `Message failed sent to kafka…` |
| Kafka broker list empty | first index call: `Registry value index/kafka/brokerList, did not find into registry` → `NoClassDefFoundError …IndexingKafkaAPI` | deployconf has no consumer servers. Indexing is dead until restart |
| Redis (RDF-cache products) | `No redis nodes specified!` / `unexpected response of 'info cluster' command` / Jedis error → KILLING | acm/marlin/was/pericles or rdf-cache products. Check `macro/redis/nodes` |
| Redis (others) | `There must be at least one redis node`, `Failed to initialize <Service>`, `NoClassDefFoundError …RedisCacheConfig` | Starts degraded. License cache is poisoned until restart |
| Gaia transformation missing (axel) | bare `RuntimeException` from `LiteratumXsltFetcher.java:85` → KILLING | `graphql/literatum/xslt` template not in `gaia/transformations` |
| Registry | `Error loading property file from system property: … : Killing server` / `failed to build` | Props chain |
| Tomcat context only | `[StartupListener] Error initializing Literatum` (JVM stays up) | `JavaEE.register` failure. Tomcat answers 404, and HostWaitForWebServer may pass depending on opstool UrlFetch |
| Management port | `cannot start management server` | Non-fatal |
| Heartbeat after start | body `1` until HostUnlock/TestAsync; `HeartBeat Error` if DB fails | Normal while locked. `StartupCheck` asks the DS to run TestAsync (`sending request to deploy server to start startup tests`) |

**Runtime (site "up" but broken):** `Error dispatching request ` → 404 (`ControllerServlet.java:115`); `Exception from action detected!` → error page; `Error executing Gaia transform for doi …`; `Service replied with error.… Status Code: 404|500` (pugrenderer template); `request to external service failed, no more targets to try!` / `Blacklisting Node.js node …` (renderer down); styleguide assets 404 with **no log** (`HttpCacheFilter.java:225-227`); `Failed to render widget async: <id>` (widget missing); `Circuit-breaker is open` (Solr); `Error in CookieCheckerFilter` + 500 (Redis lost); stale widgets after an SG-only change (`ux3OutputCache`); Cloudflare never purged.

---

## 6. Coverage

**Read fully by me (lit-2610):**
- `HeartBeatServlet`, `StartupListener`, `WebMain`, `StartupCheck`, `JavaEE`
- `CloseConnectionWhenLockedFilter`, `IntranetFilter`, `DeploymentServlet`, `ServerHealthChecker`
- `DispatcherFilter`, `ServiceFilter`, `CompoundNormalizer`, `ControllerServlet`
- `Main`, `CoreSpringConfig`, `GaiaFeBeans`, `NodeJsFactory`, `LoadBalancedPooledHttpServiceConnection`
- `Ux3ServiceImpl`, `PreloadRunnable`
- `PassportClusterSpringConfig`, `PassportClusterService`, `SingletonPassportClusterProvider`, `RobotManager_Akka`, `BroadcasterTransportPassportCluster`, `StyleguideDeployedEvent`
- `web.props.xml`, `web-fragment.xml`, `host.props.{web,backstage}.xml`, `midtier.props.host.backstage.xml`, `midtier.props.akka-cluster.IBM.xml`, `spring/frontend/nodejs.xml`
- opstool `DeployFamilyAction.java` (via `gh api`)

**Read in part by me:**
- `ActionController` 154-470, 596-757 of 1023
- `SpringAdapter` 96-200
- `DataSourceManager` 75-135, 228-400
- `DomainHandlerSingleton` 95-200 (+ grep)
- `CustomizationSpringConfig` 85-130
- `HttpCacheFilter` 44-110, 165-232
- `NodeJsJadeRenderer` (grep + 395-420)
- `ReaderGaiaUtil` / `LiteratumXsltFetcher` (grep + 55-95)
- `RobotsRegistrar` (grep)
- `literatum.props.xml`: 1525-1545, 2280-2300, 5830-5833, 6135-6175, 12054-12074, 25912-26200, 28529-28531
- `midtier.props.pb2.base.xml` 530-567, `midtier.props.pb2.ux3.xml` 40-58
- `literatum.akka-cluster.props.xml` (key names)
- deployconf XSL 1390-1512, nodejs lines
- DS `SshExecuteVisitor` 70-120 / 480-520, `SshExecutedVisitor` 600-660, `DeployUtils` 590-640, `TestAsyncServlet`, `DeployServerConfig` (grep)
- PT `lock.py`, `restart.py` 1990-2060, `fabfile.py` 510-540, `host_test.py` (grep), `hostRefreshDeply.sh` 40-100

**Sections 3 and 4:** read by two delegated agents. Their coverage lists (files read fully, line ranges, and the 2410/2411 jar `javap` checks) are summarised in the section headers. I spot-checked the load-bearing claims.

**Not read:** the rest of the ~34k Java files; external jars' source (Passport registry/cluster, pagebuilder core, id-search/id-solr 2610, kafka-messaging 2610, gaia); opstool `UrlFetch`; `qa-automation-xml` test suites; `DbConf`; `SessionFilter`/`BlockCheckerFilter` internals.

**Key Unverified items:**
1. Whether opstool `ServerUp` treats a Tomcat 404 as success.
2. All 2610-version library texts (Solr, Kafka, Jedis).
3. How the registry handles `<booolean>` and the undefined `${index/kafka/enabled}`.
4. Pagebuilder handling of sync widget failures.
5. Which ansible-pugrenderer version production runs.
