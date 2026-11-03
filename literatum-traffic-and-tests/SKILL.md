---
name: literatum-traffic-and-tests
description: Use for how traffic reaches Literatum web nodes and how deploys check them — Cloudflare, keepalived, HAProxy (puppet-control), Consul / k8s-invApi backends, the /heartbeat servlet (?id=achs, ?bg=1), HostLock / HostUnlock / HostWaitForWebServer (opstool DeployFamilyAction), and the test steps HostWarmupTest / HostEssentialTest / HostTestJane (qa-automation-xml, testypon). Use for "site down/5xx during deploy", "warm-up failed", "node still getting traffic". Strictly read-only.
---

# Literatum traffic path and deploy-time checks (read-only)

**Paths:** relative to this skill's folder (`../literatum-platform/references/deep/`); repos under `$LIT_REPOS`. Read files only through `../literatum-deploy-triage/scripts/safe_view.py`.

## Traffic path

Cloudflare tunnel → keepalived VIP → **HAProxy** (`:80`, host-header routing) → Literatum web `<port>`:
- HAProxy config is consul-templated from `puppet-control` `site-modules/profile/files/haproxy/literatum-backends.cfg.ctmpl`.
- Backends come from the Consul catalog, which **k8s-invApi** writes from the deployconf **git** repo (webhook, hourly poll).
- consul-template `wait 15s:120s` → `haproxy -c && reload`. A rejected config leaves HAProxy silently on the old one.

**Health check:** `GET /heartbeat?id=achs`, expects the body `AtyponLiteratumWorksGreat` (`inter 3s fall 3 rise 2`).
- Literatum's `HeartBeatServlet.checkAchs` (lit-2610 :216-227) returns that whenever `checkDatabase()` is OK. **The lock test is commented out.**
- **So HostLock does NOT drain a node.** It keeps getting traffic through Pause1Min until HostStop kills the JVM; HAProxy drops it ≤ 3 checks (~9 s) later, i.e. a short 5xx burst per web node per deploy (inferred).
- `achs` is product-agnostic, so a wrong host/port in deployconf still passes.

## Deploy Server checks (opstool)

| Step | What it really checks |
|---|---|
| HostWaitForWebServer | `DeployFamilyAction -t serverup`: fetches `/heartbeat?bg=1` (honours lock/release) with **empty expected text**, so any HTTP 200 passes, even body `1` (DB down / locked). 404, refused or >3 s fails. If the host's `~/deployconf.xml` matches nothing, it prints `RESULT:SUCCESS` having checked nothing: the tell is no `DeployFamilyAction.<Action> for …` line. |
| HostLock / HostUnlock | `DeployFamilyAction.java:70` inverts `-p`: the product is always null, so **every product of that family on the host** is locked/unlocked. Unlock stops at the first failure. HostLock has no validator. |
| HostWarmupTest | `host_test.py` → `qaa/xml-master` docker (qa-automation-xml master). The verdict is the **first** `***Test Is Succeeded***`/`***Test Is Failed***` line; no marker = Failure. Retried, then Cancelled: **never blocks the release**. |
| HostEssentialTest | real browser suite; only on prod/readonly deploys |
| HostTestJane | marlin only; never passed on beta/stag (WS allow-list has `127.*`/`10.*` commented out; opstool's bundle omits `wsconf/`) |

## Reading warm-up failures

- In a 111-run sample (10–25 Sep) **none pointed to a bad deploy**:
  - 37% harness/test config: logins; ux3, support and lean not in the suite;
  - 41% stale test data: the same 404/403/400 pages every run;
  - 22% one page 503 every run.
- 13 products almost never pass. Compare with that product's own history first.
- Each page first logs in via `GET /action/QATestActions?test=impersonate&email=…` (testypon `HTTPAuthClient.java:129-160`):
  - **marlin:** the site redirects to Elsevier ID, and the test container's hosts file (qa-automation-xml `recorder-tests/.../hosts/hosts:17-18`, rewritten by `HostsFilesUtil.addIps`) points `loadrc-id.elsevier.com` / `id.elsevier.com` at the web host. The connection is refused on every page. A test bug, not an outage (LIT-639552).
  - **aami:** 403, the caller IP isn't in `AUTO_TEST_USER` (test data).
- `siteInfo.json` is built daily by testypon from the Consul copy of deployconf.

## Deep notes

`35-lb-puppet-invapi.md` (LB chain; see its correction on `achs`), `18-opstool-opscommon.md`, `19-warmup-tests.md`, `23-testypon-qa.md`, `12-literatum-runtime.md` §1, `01-deployserver.md` (test actions).

## Founding failure

A reader concluded HostLock drains a node from HAProxy in about 9 seconds, because the LB checks `/heartbeat`. Reading the servlet showed the `?id=achs` branch had its lock check commented out: only the `?bg=1` path the Deploy Server uses honours the lock.
