# 19 — Host test actions (HostWarmupTest / HostEssentialTest / HostExtraTest / HostTestJane)

Built 2026-09-25, read-only. Code read at: deployserver `master` b726c83 (2026-09-24), platform-tools `master` b00c49f, qa-automation-xml `master` 9f3f654 (shallow clone, no history), opstool `master` 4562351. No `git fetch` was run, so these are the clone states. Live data came from `ds_search.py` (search RPC) and `GET /info/<id>.txt` only, for midtierbeta and staging. I fetched 250 logs one at a time. The logs are in `${TMPDIR:-/tmp}/ds-triage-$USER/warmup/` (chmod 700). No raw log text is copied here.

**Read fully:** `SshExecuteVisitor.runTest/validateRecorderWarmup/triggerDockerTEST/visitHostTestJane/visitMarlinJaneTest` (:477-940), `SshExecutedVisitor` test visitors (:634-662), `DeployDaemonHelper` reschedule/cancel (:52-123), `CreateActionVisitor.visitHostWarmupTest` (:130-157), `CreateActionMacro.MacroHostExtraTest` (:1405-1430), `platform-tools/host_test.py` (all), qa-automation-xml `WarmUpTests.java`, `ReportPortalXMLListener.java`, `AlterSuiteListener.java`, `MainAppTests.java`, `recorder-tests/entrypoint.sh` + `Dockerfile`, `testng/warm_up.xml` (parsed), every `warmUp/*.test.xml` (parsed), opstool `build.xml` bundle target.
**Sampled:** `desktopXml/*` (only group counts and scenario names), opstool `JaneTestDriver.java` (structure only).
**Not available (model gap):** the HTTP client and impersonation code, `com.atypon.web.network.http.AtyponHttpClient` / `HTTPAuthClient` in the **`testypon-web`** jar, and `siteInfo.json`, which is loaded from the classpath. Neither is in any clone. I did not open `deployserver.properties` (it holds secrets), so I don't know the live values of `selenium.test.retry`, `selenium-test.timeout`, `test.jane.products` or `products.warmup.content`.

---

## 1. How each action runs

| Action | Created by | Where it runs / command | Result goes to | Verdict (text match) | Retry / cancel |
|---|---|---|---|---|---|
| **HostWarmupTest** | per-web-host chain after HostStart→HostWaitForWebServer (DeployWithParams:77, ExplodeCmdHelper:539/556), TestAsync (PreExecuteVisitor:2521) | SSH to **the web host itself** as the account user (logs show `staging@literatum6-stag-web1`). Runs `host_test.py -p P -f F -m HOST -t warmup -i ID -a ACCT` (SshExecuteVisitor:843-866). host_test.py reads `~/.litconfig/deployconf.<acct>.xml` for host IP, SSL port and hostname. It runs `git pull origin master` in `~/sourcegit/qa-automation-xml`, takes the **docker tag = that checkout's pom `<version>`** (currently `3.5.4-SNAPSHOT`), then `docker run … -e TESTNGSUITE=WARMUP -e WARMUP=true -e PRODUCT=P -e SITE_DOMAIN=<hostname>.localhost.literatumonline.com:<ssl> --add-host …:<web IP> -v ~/sourcegit/qa-automation-xml/recorder-tests/src/test/resources/warmUp:/testng/warmUp us-central1-docker.pkg.dev/atypon-artifact/docker-registry/qaa/xml-master:<tag>` | **Nothing is kept.** RP_ENABLE=false and the container is `docker rm -f`'d. Only the DS action log remains. | Second SSH "collect" pass: `validateRecorderWarmup` (:830) reads the DS action log. The **first** line with `***Test Is Succeeded***` gives Success and the first with `***Test Is Failed***` gives Failure. **Neither → Failure** (:685) | DeployDaemon loop (DeployDaemon:180-182): `rescheduleFailedTests` puts a Failure back to Scheduled while `repeat_count < retry`. `retry` = `xmllint /site/warm-up[1]/@retry` of `~/source/HEAD/atypon/tool/qa/testconf/hostwarmup/hostwarmup.<p>.test.xml` **on the DS** (an old SVN-era path; whether it exists is unverified), falling back to `selenium.test.retry` (code default 3). After that, `cancelFailedTests` turns it into **Cancelled**. So a failed warm-up **never blocks** the release, and HostUnlock runs anyway. Earlier-attempt logs are deleted on reschedule, and every sampled log shows exactly one run. |
| **HostEssentialTest** | Auto-added **only on `literatum`/`readonly`** when the product isn't pre-prod (CreateActionVisitor:130-157), also by the RO/live-mode switches (DeployUtils:607/630). **Not in beta/stag chains.** The 6 stag rows I sampled were standalone runs by users (parentId=null, forced immediate, DeployActionSql:515). | Same `host_test.py -t essential`. docker runs `-m 16g --cpus=0.5 --env-file=/shared/docker/common/.lambda-env -e TESTNGSUITE=FUNCTIONAL -e GROUP=essential -e DRIVER=lambdaChrome -e SELENIUM_HUB=selenium-grid-test.qaa.atypon.com -e THREAD_COUNT=7` with `desktopXml` mounted. That is real Selenium through LambdaTest / QAA grid. It then `docker cp …:/allure-report /tmp/results/<id>` and zips it. | Collect pass scp's `/tmp/results/<id>.zip` to the DS test-result dir and copies it to `testreport/<acct>/<fam>/<prod>/<host>`. View at `https://deployserver.literatumonline.com/testresult/<id>/index.html`. | Same marker scan of the action log (:710-727). A missing zip is caught and logged `Could not retrieve or parse test result`, and the status stays Failure. | Not in `cancelFailedTests`. On non-prod chains `cancelOnFail=true`, so `cancelFailedActions` cancels it. **On prod/readonly a Failure stays Failure and blocks.** `blockHostActions` allows one per account+host+product. |
| **HostExtraTest** | Macro (MacroHostExtraTest, CreateActionMacro:1405). It **never inserts its own row** (0 search hits on either account) and expands to HostWarmupContent if the product is in `products.warmup.content`, and HostTestJane if it's in `test.jane.products`. Neither is added for Product/HostRestart. | — | — | — | — |
| **HostTestJane** | from HostExtraTest / TestAsync, **marlin only** (visitHostTestJane returns immediately for other products) | SSH to the web host: `cd ~/apps64/opstool; java … -Dtesturl=https://<marlin-secure-test|marlin-secure-stag>.atypon.com.localhost.literatumonline.com:<ssl> com.atypon.testdriver.JaneTestDriver -t All -d ./results/<id>`. These are JUnit web-service suites: Registration, Authentication, Alerts, Claims, ECommerce, Entitlements, Favorites, FreeContents, Offers. | results zip is scp'd to the DS test-result dir as `<id>.zip` | `report.csv` in the zip **contains `FAILED` → Failure**, else Success (:936) | In `cancelFailedTests` → Cancelled, so it doesn't block |
| HostWarmupContent (for reference) | HostExtraTest | opstool `HitUrlsCli` (multi-site) or DeployTestDriver | — | **always Success** (SshExecutedVisitor:634) | — |

### What decides `***Test Is Succeeded/Failed***` (qa-automation-xml)
- `ReportPortalXMLListener.onExecutionFinish` (recorder-api, :48-56) prints Succeeded **iff `failedTestCases == 0 && skippedTestCases != totalTestCases`**. It follows that:
  - **no tests at all** (total 0) gives **Failed**. TestNG then exits with status **8** (`HAS_NO_TEST`), and `MainAppTests` prints `Test is completed with status  : 8` without calling `System.exit`.
  - a `@BeforeClass` config failure (e.g. unparseable XML) leaves 0 tests, printed as `Configuration Failures: 1`, and gives Failed / status 8.
  - The counters count **every** onTestFailure. So a test that fails and then passes via `RetryAnalyzer` probably still makes the run "Failed" (inferred: seen on stag smp essential, where `Total tests run: 9, Passes: 9, Failures: 0`, status 0, and yet `***Test Is Failed***`).
- The container's exit code is ignored. Only the marker text counts.

## 2. Suite map (qa-automation-xml `recorder-tests`)

| Suite (TESTNGSUITE) | TestNG file (baked **into the image**) | Per-product data (mounted **from the host's git checkout**) | Exercises |
|---|---|---|---|
| WARMUP | `testng/warm_up.xml`: 174 `<test>` entries, **101 product codes**, all class `com.atypon.xml.WarmUpTests`. Sub-sites use `subSiteFile` (pericles 27, marlin 24, nrc 10, apha 3, …). | `warmUp/<code><subSiteFile>.test.xml`: 193 files, **4,991 `<open name url>` entries** | **HTTP GET per URL, and each must return exactly 200** (`WarmUpTests.testUrl`, parallel data provider). No browser. Pages: home, browse, journal/LOI/TOC, article/abstract, book TOC, search (`/action/doSearch?…`), login/registration pages, collection/topic pages, and for some sites `QATestActions?test=impersonate`/`doLogin` URLs. The HTTP client also does an **impersonation login** for some products (marlin, aami); that code is in `testypon-web`, which I haven't got. |
| FUNCTIONAL + GROUP=essential | `testng/desktop_browsers.xml`: 206 tests (`XMLTest`, plus `BuildInfoTest` when `buildInfoCheck=true`) | `desktopXml/<code>.test.xml`: 217 files, 1,024 scenarios tagged `essential` | Real browser scenarios: simple/advanced search, LOI/TOC/journal home, home page layout and images, free/protected content access, **PDF check**, book/article pages, alerts, PPV, navigation/footer |
| API_TESTING / CMS / ACCESSIBILITY | `api_testing.xml`, `cms.xml`, `accessibility_testng.xml` | — | not used by host tests |

Product selection: `AlterSuiteListener` keeps `<test>` entries whose `code` equals `PRODUCT`. **A product missing from `warm_up.xml` gets 0 tests, so it fails every time.** Because the suite file is inside the image and the page lists come from the pulled checkout, adding a product needs a **new image** as well as the XML.

**Test-config defects found by parsing the current files:**
- malformed XML (unescaped `&` in a URL): `smp.test.xml` line 14, `evidence.catalyst.test.xml` line 19.
- no `<open>` at all (so 0 tests): `authorea`, `thieme`, `evb`, `aaas.spj`, `catalyst.ai`, `mms.voices`, `pericles.wchh`, and 19 of the 24 `marlin.*` sub-site files.
- products deployed on beta/stag that are **not in `warm_up.xml`**: `ux3`, `support`, `lean` (seen live).
- `recorder-tests/src/test/resources/hosts/hosts` lists `loadrc-id.elsevier.com` and `id.elsevier.com`. `HostsFilesUtil.addIps(ipValue)` maps **every name in that file to the web host's IP**. So in the container the Elsevier IdP resolves to the Literatum web host, and `:443` there is refused. (Confirmed: the log's `Host IP =` value equals the IP in the refused-connection message.)

**Jane (opstool):** `WebserviceTestConstants` reads `wsconf/marlin/wsresources/registration.xml` (and others) relative to `~/apps64/opstool`. These files **are in the opstool repo**, but the `ant bundle` target (`build.xml:47-70`) copies only `lib/`, `config/`, `warmup/` and a few scripts, **not `wsconf/`**. So on the host they "do not exist" unless someone copied them by hand.

## 3. Failure message → meaning

| Message in the action log | Meaning | Class |
|---|---|---|
| `Warm Up Test (<page>) for url <url> has been failed due to: java.lang.AssertionError … expected [200] but found [404]` | That URL no longer exists on the site (content/test-data drift, e.g. a removed collection or a TOC for a dropped journal) | TEST DATA / content |
| `… found [503]` on **the same one or two pages every run**, while all other pages return 200 | Deterministic page-level 503. Cause unverified. Candidates in lit-2610: `RedirectLoopFilter` (`Redirect loop detected … returning 503`, RedirectLoopFilter.java:20/58) or a `LimitedRequestPool` service (default 503). Next read-only check: the web host's literatum log for that URL. | SITE (page), not a deploy regression |
| `… found [503]` on **many** pages in one run, clean on a re-run minutes later | Site still warming up right after start. HostWaitForWebServer only proves `/heartbeat` answers. | TRANSIENT / not-ready |
| `… found [403]` (registration, `showArticleSelect?institutionUserId=…`, or all pages of a site) | Access control or IP rule for the container's source address, or a test institution id that no longer exists | ACCESS / test data |
| `… found [400]` on `doLogin`/`registration` | The test account or form data is invalid for the site | TEST DATA |
| `… NullPointerException: Cannot invoke "org.apache.http.HttpResponse.getStatusLine()" … getResponse() is null` on **every** page, preceded by `Exception during impersonation login: Connect to loadrc-id.elsevier.com:443 … Connection refused` (marlin) or `Unexpected error during impersonation login` (aami) | The HTTP client's pre-request impersonation login failed, so no request was ever sent. For marlin this is caused by the hosts-file mapping above (**harness, not the IdP** — this corrects notes/13 row "marlin warm-up: external IdP"). | HARNESS |
| `***Test Is Failed***` + `Test is completed with status  : 8`, with `The added products to the suite are: []` | Product not in `warm_up.xml` | TEST CONFIG |
| `… status : 8` + `Configuration Failures: 1` (product listed) | Its `warmUp/<p>.test.xml` is malformed or empty | TEST CONFIG |
| `docker: Error response from daemon: manifest for …/qaa/xml-master:<ver> not found: manifest unknown`, then no marker | The pom version on qa-automation-xml master was bumped before that image was published (seen for 3.5.2-SNAPSHOT and 3.5.4-SNAPSHOT) | INFRA (QAA release) |
| Jane: `FAILED,…,expected:<200> but was:<403>` (27×) + `expected:<400> but was:<403>` (10×) + `File 'wsconf/marlin/wsresources/registration.xml' does not exist` / `freeListPostArticle.xml` | The marlin WS endpoints refuse the test client (403), and the wsconf files are missing from the installed opstool bundle | TEST CONFIG / harness |
| Essential: `Element … is not present in screen after 20.0 secs!`, `element click intercepted: … not clickable at point` | Selenium selector/UI drift or overlay (flaky). Needs the Allure report for the screenshot. | SELENIUM / flaky |
| Essential: `Passes: N, Failures: 0`, status 0, yet `***Test Is Failed***` | Listener counted a retried failure (inferred) | HARNESS (false failure) |
| (none of the above, empty run) `Could not retrieve or parse test result` | the zip wasn't produced or copied (essential/Jane) | INFRA |

## 4. Live sample (retention window ≈ 10–25 Sep 2026)

**Search counts** (ids include parent ProductRelease/TestAsync rows):

| Action | beta Failure | beta Cancelled | beta Success | stag Failure | stag Cancelled | stag Success |
|---|---|---|---|---|---|---|
| HostWarmupTest | 0 | 349 | 502 | 0 | 641 | 1117 |
| HostEssentialTest | 0 | 0 | 0 | 0 | 6 | 9 |
| HostExtraTest | 0 | 0 | — | 0 | 0 | — |
| HostTestJane | 0 | 61 | **0** | 0 | 40 | **0** |

The Failure searches return nothing because the daemon turns every failure into Cancelled within one loop.

**Fetched: 250 logs.** First a stratified random sample: 90 beta + 110 stag warm-up ids, 12+10 Jane, all 6 essential. Then 26 warm-up ids from products not yet seen. Of the 250: **111 warm-up runs** (beta 47, stag 64), **9 Jane**, **6 essential**, 96 parent rows (ProductRelease/TestAsync/ProductRefreshDeployUpgrade), and 28 empty (never ran). No HTTP errors. One 18 MB Jane log was cut off by the 60 s curl timeout.

**Warm-up: first real failure per run (111 runs, 27 products):**

| Class | Runs | Products (runs) |
|---|---|---|
| SITE-PAGE: one specific page 503, same page every run (beta and stag alike) | 24 | physio `/librarians` 7, utoronto `/about/open-access` 4, hope `/blog` 3, aha `/all-submission-sites` 3, rsna `/page/staff` 3, jmcp 2, cabi `/topics` 2 |
| TEST DATA / content: stable 404 (+400 login/registration, +403 specific page) | 46 | pericles 15 (JA TOC 404 + Article Select 403; 2 of these runs also had 34–63 pages at 503 just after start on stag 24 Sep, clean at 08:50), mms 14 (`/clinical-cases` 404 + login 400), guilford 3 (TOC 404), app 3, aps 3 (registration 403), ispe 2, naswa 2, aamc 2, ascb 1 (registration 400), acws 1 (all 403) |
| HARNESS: impersonation login fails → NPE on every page | 22 | marlin 15 (IdP hostname mapped to the web IP), aami 7 |
| TEST CONFIG: product not in suite / empty or malformed XML (status 8) | 16 | ux3 5, smp 5, support 3, lean 1, authorea 1, thieme 1 |
| INFRA: `qaa/xml-master` image tag not published | 3 | aami, asce, rmit |
| Site actually down / broad 5xx as the first failure | 0 | (only the 2 pericles partial-503 runs above, which were not the first failure) |

- **Real vs not:** 0 of 111 runs point to a deploy regression. 41 (37%) are harness, test-config or QAA-infra problems. 46 (41%) are stale test data or content. 24 (22%) are the same long-standing page-level 503 on every run. Warm-up failures are basically noise, and "Cancelled" doesn't mean the deploy was bad. Nothing flaky appeared except the two pericles not-ready runs.
- **Always failing** (per-product search, 0 Success rows in the window, Cancelled counts include parents): beta marlin 61, pericles 52, mms 52, physio 24, smp 21, cabi 21, hope 21, ux3 19, aami 17, utoronto 17, aha 13. Stag pericles 70, hope 32, app 30, marlin 40, mms 39, smp 24, utoronto 23 (3 Success), aps 21, physio 21, aami 20, aha 20, jmcp 20, aamc 20, rsna 18, cabi 18, ux3 18. The 26 products seen cover 919 of the 990 Cancelled warm-up ids.
- **HostTestJane (marlin):** 9 of 9 have the same signature (403 on every WS call, plus missing wsconf files). There are **0 Success rows on either account**, so it has failed on every scheduled marlin release in the window.
- **HostEssentialTest (stag, standalone, not in the deploy chain):** 6 runs. 5 were Selenium element-not-present or click-intercepted (aps ×2, utoronto ×2, uchicago). 1 was the listener false failure (smp).

**Corrections to notes/13 / SKILL:** the marlin warm-up "external IdP down" is the harness hosts-file mapping, and it happens every run. The ux3 "status 8, unknown" means ux3 is not in `warm_up.xml`. The guilford TOC failure is a recurring 404 (content). HostWaitForWebServer + HostWarmupTest aren't real readiness evidence on beta/stag for these products, because the warm-up fails whatever the deploy did.

## 5. Open questions
1. What `testypon-web` impersonation does per product, and why aami's fails (the response HTML title is `ARRAY | VIDEO`)?
2. Does the DS path `~/source/HEAD/atypon/tool/qa/testconf/hostwarmup/` exist (the real retry count)?
3. What is the cause of the page-level 503s? Check the web-host literatum log for `Redirect loop detected`.
4. Who owns `warm_up.xml`/`warmUp` hygiene (QAA)? A cheap fix list: add ux3/support/lean, fix smp/evidence.catalyst XML, fill the empty files, drop the `loadrc-id`/`id.elsevier.com` lines from `hosts` (or don't map them to the web IP), and bundle `wsconf/` in opstool.
