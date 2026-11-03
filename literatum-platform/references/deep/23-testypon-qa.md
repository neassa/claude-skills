# 23 — testypon, the warm-up HTTP client, HostTestJane, and the QA repos

Built 2026-09-25, read-only. Nothing was built or run.

**Code read at:**
- testypon `develop7` add335f, plus tag `v7.3.2` e5e4acd (2026-09-15), which I fetched shallow into the clone.
- qa-automation-xml `master` 9f3f654.
- qa-automation-lit `lit-2610` 0e0652b.
- literatum-test-tools `main` d0faa61.
- deployserver `master` b726c83, platform-tools `master` b00c49f, opstool `master` 4562351.
- Literatum `lit-2610` 9f8eb846e (`literatum-lit-2610` clone). I used it for the server side of the impersonation and Jane calls.

**Live evidence:** the DS logs already fetched for note 19, in `${TMPDIR:-/tmp}/ds-triage-$USER/warmup/logs/`:
- marlin warm-up `2bf0895e` (stag)
- aami warm-ups `67b5a405`, `1599b08b`, `254d6232`
- aami image-missing run `cf2e56e1`
- 9 Jane logs

I extracted only status codes, stack frames and page titles. The GitHub history came from read-only `gh api` GETs.

**The testypon version a warm-up uses:** qa-automation-xml pins `testypon-web` **7.3.2** (`qa-automation-xml/pom.xml:24`). Between `v7.3.2` and develop7 HEAD, `git diff` shows changes **only** in `siteInfo.json` and `model/xml/Scenario.java`. So every testypon line cited below is the code that actually runs. The live stack traces agree: the line numbers `HTTPAuthClient.java:92/136/157/158` and `WarmUpTests.java:94/103/105/107` match the source.

---

## 1. testypon architecture (the parts that matter for DS)

| Module | Role |
|---|---|
| `testypon-model` | DTOs and interfaces: `CacheService`, `HTTPClient`, `siteinfo.*` (`Environments` → `Environment` → `Site`), exceptions (`AtyponRestCallException`, `AuthenticationException`) |
| `testypon-web` | Selenium, Playwright and Apache-HTTP clients: `HTTPAuthClient`, `HttpClientImpl` (the `AtyponHttpClient` interface), retry listeners, `deployConf/SiteInfo*` (siteInfo.json producer and reader), `LiteratumApiImpl` |
| `testypon-testng` | `AtyponTestNGTestBase`, `RetryAnalyzer`, and `RetryConfiguration` (an `IConfigurable`; it re-runs a config method only if the context attribute `retry` is true) |
| boot/server/report/atlassian/cucumber/async/cache/security | the portal, reporting and Jira integration. Not used by host tests. |

Spring wiring: `WebConfiguration` registers a **`request` scope implemented as `SimpleThreadScope`** (`testypon-web/.../spring/WebConfiguration.java:53-60`). As a result `HttpClientImpl` (`@Scope("request")`, `HttpClientImpl.java:44`) is **one instance per thread**, and its `response` field is per thread, so the parallel data provider does not share it.

### 1.1 HTTP client and login flow used by `WarmUpTests`

The call chain, in order:

1. **Setup.** `WarmUpTests.setSiteDomain` is a `@BeforeTest`, run once per `<test>`, meaning once per sub-site (`qa-automation-xml/recorder-tests/.../WarmUpTests.java:85-97`). It does the following:
   - `HostsFilesUtil.addIps(ipValue)` then `mergeHostsFiles()` (:90-91). See §1.2.
   - `domainService.siteBranchAndSiteCode(ctx)` (:92). This sets `cacheService.getSiteInfo().url`:
     - It starts from `SITE_DOMAIN` (`DomainService.java:83-84`).
     - With `secondaryDomain`, sub-sites become `<secondaryDomain>.<SITE_DOMAIN>` (:97-114).
     - The result is prefixed with `https://` (:142) and written to the cache (:149-151).
     - It then **appends `ipValue <siteDomain host>` to `/etc/hosts`** (`addMultiHosts`, :167-176).
   - `httpAuthClient.getHttpClient()` (:94). This is the first **impersonation login**.
2. **Per page.** `testUrl` calls `getPageStatusCode` (:99-108), which calls `client.sendRequestToUrl(url, GET)`. That method routes to `emailDev` (default `qaautodev@atypon.com`, `HttpClientImpl.java:58-59,364-367`), then to `getAuthenticatedClient(email)` (:110-123):
   - If the cache holds a client, it is reused.
   - Otherwise `authClient.getHttpClient(email)` does a **fresh impersonation login**. **A failed login is never cached, so every page retries it.**
   - Then `GET <siteUrl><path>` (:378-380). The response is kept in the thread's `response` field.
   - Any exception is logged as `Error while sending request to …` (WarmUpTests:104-106).
   - Then `client.getResponse().getStatusLine()` (:107) throws an NPE if no request was ever sent.
   - Pass means exactly **200** (:113-115).
3. **The impersonation login itself.** `HTTPAuthClient.getHttpClient(email)` (`testypon-web/.../spring/HTTPAuthClient.java:80-103`):
   - It builds a fresh Apache HttpClient: `BasicCookieStore`, **`LaxRedirectStrategy`** (it follows every redirect, including off-site ones), `NoopHostnameVerifier`, and a trust-all SSL context (:105-107, :163-173).
   - It calls `performImpersonationLogin` (:129-160): **`GET <siteUrl>/action/QATestActions?test=impersonate&email=<urlencoded email>`** (:133-136). There is no password and no IdP of its own: it relies on the Literatum QA backdoor.
     - Status 200 counts as success (:138-140).
     - Any other status throws `Impersonation login failed. HTTP error code: <n>` (:141-153), logged at :143/:147/:151.
     - A transport error is logged as `Exception during impersonation login: <msg>` (:157) and rethrown (:158).
   - The caller logs `Unexpected error during impersonation login` (:92) and throws `AtyponRestCallException` (:99).
   - Retry: the no-arg `getHttpClient()` is `@Retryable` (:73). The listener `httpAuthRetryListener` then runs `BaseRetryListener.onError`, which calls `refreshAuthentication()`. That calls `HttpClientImpl.preAuthenticateUsers()` (`BaseRetryListener.java:45-56,95-101`), which logs in again as **three** users (`qaautopub`, `qaautodev`, `qaautomation`, `HttpClientImpl.java:89-103`). So one failed setup makes about 4 more impersonation calls.
   - The `@Retryable` on the **private** `performImpersonationLogin` (:128) has no effect, because a Spring AOP proxy does not intercept self-calls to private methods.
4. **The hosts it calls:** only the Literatum site URL (the web host IP via `/etc/hosts`), **plus wherever the site redirects**. Because of `LaxRedirectStrategy` that can be an external IdP.
5. **Server side** (Literatum lit-2610, `literatum/src/java/com/atypon/literatum/action/test/QATestActions.java`):
   - `impersonate` is in the `skipMethods` list (:77), so `preProcess` only runs `checkSessionAccess` (:80-81). That returns true if `session.isTestUser() || session.isQA() || loopback IP` (:988-995).
     - `isTestUser` means the session holds the `AUTO_TEST_USER` group (`SessionData.java:3320-3327`). In practice that comes from an IP-range identity in that group, per product DB (inferred from `ClientIpFilter.isQA`, `ClientIpFilter.java:150-166`).
     - **If the check fails, the response is 403** (`ResponseForbidden`).
   - `impersonate` (:134-192) always returns **200**. If the user is unknown or not allowed, the body is `cannot add your identity on the session`. **So testypon's "200 = login OK" is a false success.** It is harmless for warm-up, because the pages are then fetched anonymously.
   - marlin overrides `preProcess` (`product/marlin/.../MarlinQATestActions.java:42-51,220-222`) with the same access rule. aami has no override; it uses the base class through `literatum/conf/services.props.xml:543`.

### 1.2 Host mapping inside the container

- `/testng/hosts/hosts` is **baked into the image**. `HostsFilesUtil.java:16`; `recorder-tests/Dockerfile:8` copies `target/test-classes` to `/testng`. The mount from the host is only `/testng/warmUp` (`platform-tools/host_test.py:90`).
- `addIps(ip)` puts **the web host IP in front of every line** of that file (`HostsFilesUtil.java:20-29`). `mergeHostsFiles` appends the result to `/etc/hosts` (:31-43).
- The file's 18 names (`recorder-tests/src/test/resources/hosts/hosts:1-18`) include `downloads.lambdatest.com` (:13), `loadrc-id.elsevier.com` (:17) and `id.elsevier.com` (:18).
- History (`gh api …/commits?path=…/hosts/hosts`): `loadrc-id.elsevier.com` was added in 3de0eb80 and `id.elsevier.com` in b7093879. Both are dated 2025-08-05, from ticket **LIT-639552** ("update hosts and tags/marlin essential").
- docker also gets `--add-host <hostname>.localhost.literatumonline.com:<IP>`, and `DomainService.addMultiHosts` adds each sub-site host.

### 1.3 Why marlin and aami fail on every page

**marlin** (stag example `2bf0895e`: `Total tests run: 63, Passes: 1, Failures: 62`, `Configuration Failures: 24`):
1. marlin has Elsevier ID+ (OIDC) integration enabled, and all its endpoints are on `loadRC-id.elsevier.com` (`product/marlin/conf/marlin.props.xml:701-710`, `idPlusIntegration enabled=true`, `tickUrl …/ext/tick`).
2. So the impersonate GET on a marlin sub-site is redirected to `loadrc-id.elsevier.com`, and `LaxRedirectStrategy` follows it. The redirect itself is inferred. The evidence is that `HTTPAuthClient.java:136` is the only `execute` in the method, and the exception names that host.
3. In the container, `loadrc-id.elsevier.com` resolves to **the web host IP** (log: `Connect to loadrc-id.elsevier.com:443 [loadrc-id.elsevier.com/10.120.0.72] failed: Connection refused`, at `HTTPAuthClient.java:157`). That matches `Host IP = 10.120.0.72`. Nothing listens on :443 there, because the web host serves SSL on the product port (25138).
4. The setup fails at `WarmUpTests.java:94`. That is 24 configuration failures, one per marlin sub-site `<test>`. The tests still run: `@Test(alwaysRun=true)` at :110 is the likely reason (TestNG semantics not verified).
5. Every page repeats the login (not cached), gets `AtyponRestCallException` (:105), and then hits the NPE at :107. The **1 pass** is the `jada-ada-org` sub-site, where impersonation returned 200 (log line 7216), so that sub-site doesn't take this redirect path.

- **Root cause:** the harness. The LIT-639552 hosts entries point the Elsevier IdP at the Literatum web host, and the HTTP client follows the site's IdP redirect.
- It is **not** the IdP being down, and **not** a deploy regression.

**aami** (beta `67b5a405`, stag `1599b08b`/`254d6232`: 24/24 failures each):
- The impersonate GET returns **403**. That is `Impersonation login failed with unexpected status code: 403` (`HTTPAuthClient.java:151`), 26× per run.
- The body is aami's standard error page, title `ARRAY | VIDEO` (the site's own title; the page text reads "403 An error has occurred").
- That 403 is `QATestActions.preProcess` → `checkSessionAccess` = false (:80-81, :994). The container's source address is not an `AUTO_TEST_USER` IP on aami's beta/stag DB, and not loopback.
  - The source is probably the docker bridge address, since the container talks to its own host's IP (inferred).
  - Other products pass the same check, so this is **aami test data** (the AUTO_TEST_USER IP range) and not code.
- Pages then NPE as for marlin.

### 1.4 siteInfo.json: what it holds and where it comes from

- **Shape** (`testypon-model/.../siteinfo/*`, `testypon-web/src/main/resources/siteInfo/siteInfo.json`, 4,384 lines):
  - The top level is `environments`, with 14 keys: atypon, cip, gcp, gcp-rehearsal, literatum, lts, midtierbeta, migration, office-jordan-cip, office-santaclara-cip, performance, readonly, rorehearsal, staging.
  - Under each: `sites{code → {code, url (= host_name), family[] , styleGuideVersion, isEnabled, sourceBranch, environment}}`.
  - Example: midtierbeta marlin = `marlin-test.literatumonline.com`, family `f`, branch `lit-2610`.
- **Source: deployconf, through Consul/InvAPI. The deployconf git repo is not read directly.** The producer is `SiteInfoDAO` + `SiteDao` (Spring profile `siteInfo`):
  - `GET http://invapi.invapi.svc/getconsul?path=deployconf/` gives the env list (`SiteInfoDAO.java:35-39,55-82`).
  - `…deployconf/<env>/products` gives the product codes (:105-137).
  - Per product (`SiteDao.java:56-142`): `…/products/<code>` gives the families. Then `/<fam0>/metadata/host_name`, `/metadata/enabled`, `/metadata/source_branch` and a styleguide-version key are read, **for the first family only**.
  - `SiteInfoJSONWriter.writeSiteInfo` (`SiteInfoJSONWriter.java:28-43`) validates, writes a temp file next to `target/classes/siteInfo/siteInfo.json`, validates it again, and atomically replaces the file.
- **Refresh:** `.github/workflows/siteinfo.yml` runs daily at 02:00 UTC (`:6`).
  - It pre-checks InvAPI (at least 5 envs; must include staging, midtierbeta, literatum, readonly; `:28-71`).
  - It runs the cucumber `@siteInfo` feature (`siteInfoBuild.feature`, `SiteInfoStepDefs.java:19-27`) and copies the file into `src/main/resources`.
  - It opens a PR to **develop7**, auto-approves it and merges it (`:158-205`).
  - The old Jenkins `pipelines/siteInfo.gdsl` pushed to `develop` instead.
- **Consumer:** `SiteInfoParser` reads `/siteInfo/siteInfo.json` **from the testypon-web jar on the classpath** (`SiteInfoParser.java:29,61-73`). It does this at `@PostConstruct` and again from `DomainService.siteBranchAndSiteCode` (:80). With `isLiteratum` (default `true`, :43) it caches `getSite(product.code, environment)` (:95-109).
  - **A product missing from siteInfo for that env throws `IllegalArgumentException`** (:124-135).
  - In warm-up the URL is then **overridden by `SITE_DOMAIN`**, so a stale URL or branch doesn't matter. Only the product's presence does.
- **Staleness:** a deploy only sees the siteInfo inside the **released** jar (7.3.2, 2026-09-15). The develop7 copy is refreshed daily but isn't used until the next release plus a qa-automation-xml bump. The diff between 7.3.2 and HEAD is 394 lines; for example, staging marlin `sourceBranch` in the jar is still the 260702 MR0 branch. ux3, support, lean and smp **are** present for midtierbeta and staging, so their note-19 failures are the `warm_up.xml` ones, not siteInfo.

## 2. HostTestJane: 403 on every call, and missing files

**The 403.** Every Jane web service extends `MarlinWebserviceAction`. Its `execute` returns `ResponseAccessDenied` when the caller IP doesn't match `acs/ElsevierWebserviceIPRanges` (`product/marlin/src/java/com/atypon/marlin/MarlinWebserviceAction.java:28,40-41`).
- In `product/marlin/conf/marlin.props.xml:581-608` the list has 18 entries: Elsevier and Atypon public ranges, plus `192.168.*`.
  - **`loopback 127.*` and `private-class-a 10.*` are commented out** (:603-605, "HASSAN: I removed loopback because some A&E calls are not being well served").
  - `private-class-b` (:606) has spaces inside its alternation, so it probably never matches (unverified; depends on `IPAddressUtil.ipListToPattern`).
- Neither `marlin.props.IBM-beta.xml` nor `IBM-stag.xml` overrides the key. A DB-level override is possible but was not checked.
- JaneTestDriver runs **on the web host itself**: `cd ~/apps64/opstool; java … -Dtesturl=https://marlin-secure-{test,stag}.atypon.com.localhost.literatumonline.com:<ssl>`.
  - So the caller IP is 127.0.0.1 or the host's own `10.120.x`, and both are excluded.
  - Every `/ae/auth|ecomm|autz/*`, `/v1/autz/claim` and `/action/*` call that the tests make (`opstool/src/com/atypon/testdriver/marlin/webservice/WebserviceTestConstants.java:24-97`) gets 403.
- All 8 Jane logs that have results show the identical signature: `expected:<200> but was:<403>` ×36 and `expected:<400> but was:<403>` ×14. The 400 cases are error-path tests (`BaseTestWorker.doErrorCheck`, default 400, `BaseTestWorker.java:168-175`); they are blocked before they can produce their 400.
- **Verdict:** a harness or environment mismatch. The IP allow-list was written for Elsevier's JANE middleware, not for an on-host test driver.

**Missing files.** The tests read their POST bodies from paths **relative to the cwd** `~/apps64/opstool`, as `wsconf/marlin/wsresources/<f>`:
- `WebserviceTestConstants.java:15,48,60,61,74,91`: `registration.xml`, `add_favorites.xml`, `orderShippingBilling.xml`, `orderAddPromo.xml`, `freeListPostArticle.xml`.
- Generated names: `register-<i>.xml`, `updateUser-<i>.xml`, `order-<i>.xml`, `order-bad.xml` (`RegistrationTestWorker.java:59-60`, `AuthenticationTestWorker.java:232-233`, `ECommerceTestWorker.java:314-315,437-438`).
- **All 43 files are in the opstool repo** (`opstool/wsconf/marlin/wsresources/`, plus rcnp, restapi, soapapi and tandf: 63 wsconf files in all).

Why they are missing on the host:
- The `ant bundle` target (`opstool/build.xml:47-70`) copies only `fkidxdb.sh`, `runtest.sh`, `*.sql`, `lib/*.jar`, `config/**` and `warmup/**`. **It never copies `wsconf/`.**
- `platform-tools/build_opstool.sh:23-37` (DS `ToolOpstoolInstall`) runs `ant bundle`, then **`rm -rf ~/apps64/opstool`**, then unzips. So even a hand-copied `wsconf/` is wiped on every reinstall.
- The logs report only the first two reads, `registration.xml` and `freeListPostArticle.xml` (8/8 logs). The other suites fail on 403 before reading their files.
- Fix: add `<copy todir="bundle/wsconf"><fileset dir="wsconf"/></copy>` to `bundle`. That alone still fails on the 403.

## 3. qa-automation-lit and literatum-test-tools in the DS

**qa-automation-lit: YES, but only on CIP.** The chain:
1. **HostUnlock** (web, `account=cip`, parent ProductRelease or ProductRefreshDeploy), when the release args have `runQaaTests` and the deployconf `<product category="qaa">` (`deployserver/.../SshExecutedVisitor.java:567-602`).
2. That creates **GatherFactsForJenkinsJob** (`SshExecuteVisitor.java:548-556`, which runs `-p passport/enabled`). **Both of its branches set Success** (`SshExecutedVisitor.java:511-537`).
3. That creates **QaaIntegrationTests** (:539-551).
4. QaaIntegrationTests is a `curl POST https://api.github.com/repos/atypon/qa-automation-lit/actions/workflows/${product}_ds_github_bdd_runs.yml/dispatches` with **`"ref":"lit-2610"` hard-coded** and inputs product_code, environment and family (`deployserver/config/actions.xml:1754-1761`).
   - Pass = `http_status=200|201|204`, which only means the **dispatch was accepted**. The BDD result is never read by DS (a false-success class).
   - `timeout.QaaIntegrationTests=12h` (`deployserver.properties:118`, that line only).
- Workflows exist on lit-2610 for marlin, pericles, tandf, ux3 and wspc (`qa-automation-lit/.github/workflows/*_ds_github_bdd_runs.yml`). They call a shared reusable workflow. qa-automation-lit also pins testypon 7.3.2 (`qa-automation-lit/pom.xml:18`).
- **Not reachable on midtierbeta or staging.**

**literatum-test-tools: NO DS use.**
- Zero hits in deployserver, platform-tools, opstool, deployconf, ansible-tools and ansible-git-repos.
- It is a 2020 unit-test helper (`aspectj-cacheable-service/MockCacheableService`), used only as a Literatum `testImplementation` dependency (`literatum-lit-2610/atypon/literatum/build.gradle:1002`, `LiteratumSpringCacheConfigTest.java:6`).

**Related DS test hooks** (for completeness):
- `JenkinsTestypon` (`actions.xml:350-355`) runs `platform-tools/testypon_jenkins.sh`, which triggers the acjenkins `Release_Testypon` job and comments on Jira. It is a QAA-permission account-level tool and not part of deploys.
- The legacy `TestUtils.generateTestTool` (`deployserver/.../teststrategy/util/TestUtils.java:15-80`) pulls `atypon/xmlqaauto` `atypon_lifecycle.json`. Warm-up and essential never reach it (`SshExecuteVisitor.java:576-578` returns first).

## 4. Which branch a deploy actually uses

| Component | What decides it | Value now |
|---|---|---|
| qa-automation-xml **data** (`warmUp/*.test.xml`) | `host_test.py:64-82` runs `git pull origin master` in `~/sourcegit/qa-automation-xml` **on the web host** (merged into whatever branch is checked out there; logs show `branch master -> FETCH_HEAD`), mounted at `/testng/warmUp` | live `master` |
| qa-automation-xml **image tag** | `getDockerImageTag()` takes the root pom `<version>` of that checkout (`host_test.py:13-23`) | `3.5.4-SNAPSHOT` (mutable tag) |
| **Image content** (`warm_up.xml` suite, `hosts` file, compiled tests, testypon jar) | `build_docker_image.yml` runs on push to **master** **except `recorder-tests/src/test/resources/**`** (:9-13), and on release or manual runs | the last master build. **A resources-only fix (hosts, warm_up.xml) does not rebuild the image.** It needs a manual dispatch or `build_docker_image_xml_changes.yml`. |
| testypon | Maven release `testypon-web` `${qa.automation.tool.version}` = **7.3.2** (`qa-automation-xml/pom.xml:24,203`). No branch is involved. | tag `v7.3.2` e5e4acd. develop7 (the default branch, which gets the siteInfo auto-merges) reaches a deploy only after a release plus a pom bump (`release_qaaxml.yml` `testyponVersion` input). |
| qa-automation-lit (CIP only) | hard-coded `"ref":"lit-2610"` (`actions.xml:1756`) | `lit-2610` |
| opstool (Jane) | whatever `ToolOpstoolInstall` last built from `~/sourcegit/opstool` (`build_opstool.sh`) | branch on the host not verified |

## 5. Failure message → cause → fix / check

| Message in the DS action log | Cause | Fix / read-only check |
|---|---|---|
| `Exception during impersonation login: Connect to loadrc-id.elsevier.com:443 [loadrc-id.elsevier.com/<webIP>] failed: Connection refused` then `Unexpected error during impersonation login`, then on every page `Error while sending request … ` + `NullPointerException … getResponse() is null` (**marlin**) | marlin's impersonate URL redirects to Elsevier ID+ (`marlin.props.xml:701-710`); `LaxRedirectStrategy` follows it (`HTTPAuthClient.java:106`); the container hosts file maps the IdP to the web IP (`hosts:17-18` + `HostsFilesUtil.java:20-29`, added in LIT-639552) | QAA: drop `loadrc-id`/`id.elsevier.com` from `hosts`, or stop following off-site redirects during impersonation, **and rebuild the image manually** (resources-only pushes don't). Check: the IP in the exception = `Host IP =`. |
| `Impersonation login failed with unexpected status code: 403. Response: <aami error page "ARRAY \| VIDEO">` → NPE on every page (**aami**) | `QATestActions.checkSessionAccess` is false: the container's source IP is not an `AUTO_TEST_USER` IP on aami's DB (`QATestActions.java:77-81,988-995`) | aami DB test data: add the container or host source range to AUTO_TEST_USER (QAA/aami owner). Check: web access log source IP of `/action/QATestActions?test=impersonate` |
| `Impersonation login failed … 400` / `… 500` (`HTTPAuthClient.java:143/147`) | site-side error on the QA backdoor | web-host literatum log at that time |
| every page NPE **with no** impersonation error before it | not seen. `getResponse()` is null whenever `sendRequestToUrl` throws before `execute`, e.g. a DNS failure of the sub-site host | check the `/etc/hosts` dump (`DomainService.java:172-174`) |
| `Site code '<p>' not found in environment '<env>'` / `Environment not found` | product or env missing from the siteInfo.json **inside testypon 7.3.2** (`SiteInfoParser.java:124-135`) | check `git show v7.3.2:testypon-web/src/main/resources/siteInfo/siteInfo.json`. Fix: testypon release + qa-automation-xml bump |
| Jane `FAILED … expected:<200> but was:<403>` ×36, `expected:<400> but was:<403>` ×14 | `MarlinWebserviceAction` IP allow-list `acs/ElsevierWebserviceIPRanges` excludes 127/8 and 10/8 (`marlin.props.xml:603-605`, `MarlinWebserviceAction.java:40-41`) | allow the web-host IPs on non-prod marlin, or retire HostTestJane (0 Success in the window) |
| Jane `File 'wsconf/marlin/wsresources/registration.xml' does not exist` / `freeListPostArticle.xml` | `opstool/build.xml` bundle omits `wsconf/`; `build_opstool.sh` wipes `~/apps64/opstool` on reinstall | add `wsconf/**` to the `bundle` target |
| QaaIntegrationTests Success (cip) | only means the GitHub dispatch was accepted (`http_status=204`) | look at the qa-automation-lit Actions run `Run_BDD_<p>_<fam>_<env>` |

## 6. Security findings (values not reproduced)

`safe_view.py` **missed** some of these, so I saw them:
- `literatum-lit-2610/atypon/product/marlin/conf/marlin.props.xml:690,695`: a cloud access key and a consumer key, committed in plain text.
- `deployserver/src/com/atypon/deployserver/server/strategy/teststrategy/util/TestUtils.java:47`: a hard-coded GitHub token in a curl header. **It should be rotated.**
- `testypon/.github/workflows/siteinfo.yml:147` and `testypon/pipelines/siteInfo.gdsl:18`: a Jira password literal on the mvn command line.
- `opstool/src/com/atypon/testdriver/marlin/webservice/WebserviceTestConstants.java:16-17`: test-user credentials.

Suggestion: extend safe_view's patterns to cover `AKIA[0-9A-Z]{16}` and bare 40-hex tokens.

## 7. Coverage

**Read fully:**
- testypon: `HTTPAuthClient`, `HttpClientImpl`, `AtyponHttpClient`, `BaseRetryListener`, `HttpAuthRetryListener`, `HttpRetryListener`, `spring/WebConfiguration`, `SiteInfoJSONWriter`, `SiteInfoDAO`, `SiteDao`, `SiteInfoParser`, `RetryConfiguration`, `siteInfoBuild.feature`, `SiteInfoStepDefs`, `.github/workflows/siteinfo.yml`, `pipelines/siteInfo.gdsl`.
- qa-automation-xml: `WarmUpTests`, `HostsFilesUtil`, `DomainService`, `DomainProps`, `hosts/hosts`, `recorder-tests/entrypoint.sh`, `Dockerfile`.
- platform-tools: `host_test.py` (§40-100), `build_opstool.sh`, `testypon_jenkins.sh`.
- opstool: `WebserviceTestConstants`, `BaseTestWorker`, `build.xml` bundle.
- Literatum lit-2610: `QATestActions` (:64-200, :966-1005), `MarlinQATestActions` (:1-80, :200-223), `MarlinWebserviceAction` (:25-60), `SessionData.isQA/isTestUser`, `ClientIpFilter.isQA`.
- DS: `actions.xml` QaaIntegrationTests and JenkinsTestypon, `SshExecutedVisitor` 500-605, `SshExecuteVisitor` 548-580, `TestUtils` (except :47).

**Sampled:**
- `siteInfo.json` (parsed as JSON; checked envs and the marlin, aami, ux3, support, lean and smp entries).
- `marlin.props.xml` (only :578-608 and :690-720).
- `build_docker_image.yml` (:1-18 plus grep), `release_qaaxml.yml` and `build_docker_image_xml_changes.yml` (grep), the qa-automation-lit workflow (`marlin_ds_github_bdd_runs.yml`), the Jane test-worker file reads (grep).
- The other testypon modules: file lists only.

**Not read or not available:**
- The Literatum ID+ filter that issues the marlin redirect (the redirect is inferred from the exception host).
- aami's `AUTO_TEST_USER` IP ranges (DB data).
- A DB override of `acs/ElsevierWebserviceIPRanges`.
- `IPAddressUtil.ipListToPattern` (the whitespace question).
- The qa-automation-lit reusable BDD workflow.
- `JaneTestDriver` beyond its structure.
- The opstool branch on the hosts.
