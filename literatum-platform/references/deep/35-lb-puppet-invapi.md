# 35 — The DC load balancer: puppet-control HAProxy, k8s-invApi → Consul, and what HostLock/HostUnlock look like at the LB

Written 2026-09-27, read-only, via `tools/safe_view.py` only. Nothing run, nothing changed.

**Repos and commits read**
- `PC/` = `$LIT_REPOS/puppet-control`, branch `production` @ `e5b11acd` (2026-09-24). Grafted clone; file history from `gh api repos/atypon/puppet-control/commits?path=…`.
- `IA/` = `$LIT_REPOS/k8s-invApi`, `master` @ `dd827c8d` (2026-09-06).
- `DS/` = deployserver `master` @ `b726c83`; `OT/` opstool `master` @ `4562351` (via note 18); `L/` = literatum-lit-2610 @ `c9e4556` (`origin/lit-2610`, the beta/stag/prod build branch); `DC/` = deployconf `main` @ `9d5fb1a`; platform-tools `b00c49f` (grep only).
- Context notes reused: 26 (repo map), 18 (DeployFamilyAction/UrlFetch), 12 §1 (HeartBeatServlet), 01 (DS host chain), 06 (ConsulPopulate KV copy).

**Secrets.** Not opened: `data/secrets.yaml`, `.git-crypt/`, hiera eyaml, `PC/site-modules/literatum/files/id_rsa_warplda`, `PC/site-modules/opendkim/files/keys/*/literatum.private` (names only, seen in `git ls-files`). safe_view masked: the Consul address in `PC/data/servertype/haproxy/common.yaml:246`, keepalived `auth_pass` defaults (`profile/manifests/haproxy.pp:77`, hiera comments), the Rundeck token variable in `IA/inv-API/api.py:824`, the `cloudflared` tunnel token keys in `PC/data/servertype/cftunnel/*.yaml`. Values are not recorded here.

**Unlisted repos this depends on (model gaps, flagged):** `atypon/k8s-invApi-helm` (the Helm chart: `health-checks.yaml` ConfigMap and the prod values that set `CONSUL_SYNC_ENABLED`, `HEALTH_CHECK_ENABLED`, `CONSUL_SYNC_SKIP_RESOLVE`, refresh interval — the docs quote them, the values file was not read); `atypon/atypon-haproxy-services` (the non-literatum YAML source, `NONLIT_REPO_NAME`); `atypon/k8s-consul` (`ConsulPutKV.py`, the *other* deployconf→Consul path, note 26); the Puppet Forge/vendored `haproxy`, `keepalived`, `consul_template` modules referenced from `PC/Puppetfile` (not read).

---

## 0. One-paragraph answer

The DC edge is **Cloudflare tunnel → keepalived VIP → HAProxy 3.0 (:80, host-header routing) → Literatum web `<port><ssl>` over TLS**. HAProxy's backends are rendered by **consul-template** on the HAProxy VMs from the **Consul catalog**, which **k8s-invApi** (a GKE service) writes by parsing the **deployconf git repo** (`GIT_BRANCH=main`, every `deployconf.<env>.xml`) — one backend `bk_<envtype>-<product>-web` per product, one `server <host>-<port>-<envtype>-web` per web instance. **The LB decides readiness itself**: every server is probed `GET /heartbeat?id=achs` every 3 s and must return the body `AtyponLiteratumWorksGreat` (`fall 3 rise 2`). Literatum returns that string **only when the node is unlocked+released AND a DB connection can be obtained** (`L/…/HeartBeatServlet.java:216-227,158-196`), otherwise `Not Finished` with HTTP 200. So **HostLock takes a node out of rotation in ≈9 s** (3 failed probes) and **HostUnlock brings it back in ≈6 s** (2 good probes). Consul's own health checks (ESM) and the Deploy Server's `RESULT:SUCCESS` lines have **no bearing** on what HAProxy routes.

---

## 1. puppet-control: how the LB is built

### 1.1 Which hosts, which files

| Thing | Where | Value |
|---|---|---|
| Role | `PC/site-modules/role/manifests/haproxy.pp` | `profile::base` + `profile::haproxy` |
| Tiers (hiera `servertype/haproxy/<tier>[/location/<dc>].yaml`) | `PC/data/servertype/haproxy/{common,prod,nonprod}.yaml`, `…/prod/location/Datacenter_CA.yaml`, `…/nonprod/location/Datacenter_CA.yaml`, `…/location/{Datacenter_CA,Santa_Clara}.yaml` | hosts `haproxy-prod0/1` (VIP `10.120.106.69`, VRRP id 52), `haproxy-nonprod0/1` (VIP `10.120.106.64`, id 53), legacy `haproxy-0/1` (VIP `10.120.106.59`, id 51, "intended to be decommissioned"); Santa Clara VIP `10.61.201.12` |
| **All three tiers render the same backends.** | `prod.yaml:26-31` | The templates filter on `service=literatum`+`type=web` and never on `envtype=`; **domain routing is what separates prod from nonprod**. Consequence: every web instance in every env is probed by every HAProxy VM (6 probers × every 3 s). |
| Front of HAProxy | `PC/data/servertype/cftunnel/{prod,nonprod}.yaml:1-2` | `cftunnel-prod0…` runs `cloudflared` pointed at the prod HAProxy VIP; nonprod likewise. Real client IP arrives as `CF-Connecting-IP` and is rewritten to `F5_Source_IP` in the literatum backends only (`literatum-backends.cfg.ctmpl:38-48,152-153`). |
| HAProxy version / packaging | `profile/manifests/haproxy.pp:114-137`, `common.yaml:127-133` | HAProxy 3.0.x from `haproxy.debian.net` (bullseye), `-f /etc/haproxy/conf.d/ -S /run/haproxy-master.sock` (master-worker) |
| **Not** part of this LB | `PC/site-modules/profile/templates/patch-nginx.erb` | nginx for `daily-patching.atypon.com` (patch server web UI). No varnish anywhere. keepalived only for the VIP (and `doc/warp-gw-keepalived.md` for the WARP gateway). |
| Consul agent on web hosts | `PC/site-modules/role/manifests/literatum/host/production.pp:8`, `profile/manifests/consul_agent.pp`, `data/common.yaml:753-758` | `role::literatum::host::production` **includes `profile::consul_agent`** (Consul 1.18.1, datacenter `consul-gcp`, `retry_join consul-gcp.devops.atypon.com`). Per `IA/docs/MIGRATION_AGENT_REGISTRATION.md` this is **Phase 1: node identity only, registers no services**; HAProxy backends still come from k8s-invApi. Whether the agent is actually enabled on any host is hiera-gated and **Unverified**. |

### 1.2 The rendered config (the four consul-templates)

Shipped by `profile::haproxy` into `/etc/consul-template.d/*.cfg.ctmpl`, rendered by consul-template into `/etc/haproxy/conf.d/*.cfg` (`profile/manifests/haproxy.pp:162-203`, watches `common.yaml:257-310`).

**`literatum-frontend.cfg.ctmpl` → `frontend literatum_in`** (`bind *:80`, `mode http`, `option http-keep-alive`):
- Pass 1: `use_backend bk_<svc> if { hdr(host) -i <domain> }` for every `domain=` tag of every service tagged `service=literatum` **and** `type=web` (`:77-87`); then the same for non-lit services (`config-group=`, not `mode=tcp`).
- Pass 2: `use_backend bk_<svc> if { hdr_end(host) -i .<domain> }` for any `*.literatumonline.com` domain (or a `domain-wildcard=` tag) (`:108-124`).
- `default_backend bk_default` → HTTP **404** `no haproxy backend matches this host` (`common.yaml:207-212`).
- Access log: logfmt to `127.0.0.1:514` → rsyslog → `/var/log/haproxy/access.log` (`profile/manifests/haproxy.pp:213-288`), fields `frontend= backend= server= status= termstate= retries= host= url=` (`literatum-frontend.cfg.ctmpl:73`). Shipped to Loki by the host's Alloy.

**`literatum-backends.cfg.ctmpl` → one `backend bk_<Consul service name>` per literatum web service** (`:131-175`):
```
backend bk_<envtype>-<product>-web
    mode http / balance roundrobin / http-reuse always
    cookie JSESSIONID prefix nocache                       # sticky sessions (F5 port)
    http-request set-header F5_Source_IP %[req.hdr(CF-Connecting-IP)] if …
    option httpchk GET /heartbeat?id=achs
    http-check expect string AtyponLiteratumWorksGreat
    default-server check inter 3s fall 3 rise 2 maxconn 12500 init-addr last,libc,none [ssl verify none]
    server <host>-<sslport>-<envtype>-web <host>:<sslport> cookie <same id>   # one per instance, "any" health
    # or:  server _placeholder 127.0.0.1:1 disabled        # when the service has no instances → 503
```
- `ssl verify none` is emitted when the service carries `backend-scheme=https`, i.e. whenever deployconf has `<port><ssl>` (all 82/80/88 web products in literatum/staging/midtierbeta do). HAProxy therefore talks TLS to the **ssl port**, and (HAProxy default when `ssl` is on the server) the health check is over TLS too.
- `service .Name "any"` (`:169`): **every registered instance is rendered regardless of Consul check status** — Consul/ESM health is *not* consulted; "HAProxy's own check below is the readiness authority" (`:7-11`). The file therefore changes only on an inv-API register/deregister.
- `snippet=sso-shared-session` adds `use-server … if { var(txn.hasrv) -m str <n> }` + `id <n>` per server (`:142-161`). Used by one product each in midtierbeta and staging (`DC/deployconf.midtierbeta.xml:5668-5669`; none in literatum).
- `init-addr last,libc,none` and **no `resolvers`**: hostnames are resolved once at start/reload via libc (`/etc/hosts` + DNS); an unresolvable host is accepted and marked DOWN instead of aborting (`:66-88`). No runtime re-resolution.

**`nonlit-backends.cfg.ctmpl` / `nonlit-tcp-frontend.cfg.ctmpl`**: the non-literatum services (`config-group=` tag; grafana, jenkins, marlin, mms, logstash…) — `health-path=`, `sticky=`, `route-key=`, `mode=tcp`, `listen-port=` tags. Not on the Literatum deploy path; documented in `IA/docs/NON_LITERATUM_SOURCE.md` (not read in full).

### 1.3 Timeouts, stickiness, maintenance

| Setting | Value | Source |
|---|---|---|
| `timeout connect / client / server / http-request / http-keep-alive / tunnel` | 3s / 15s / **60s** / 5s / 30s / 1h | `common.yaml:168-174` |
| `retries 3`, `option redispatch`, `http-reuse always`, `option forwardfor` | connection failures are retried on another server; **a request already sent is not replayed** | `:164-176` |
| `maxconn` | global 262000, per server 12500 | `:145,153`, template |
| Health check | `GET /heartbeat?id=achs`, expect body `AtyponLiteratumWorksGreat`, `inter 3s fall 3 rise 2`; no `timeout check` ⇒ HAProxy uses `inter` (3 s) as the check timeout | template `:155-156,164-167` |
| Sticky sessions | `cookie JSESSIONID prefix nocache` — HAProxy prefixes the server id (`<instance_id>~`) onto Literatum's own JSESSIONID and strips it on the way in. Per-server cookie value = Consul ServiceID, stable across reloads. | template `:21-36,141,170` |
| **Maintenance mode** | **None at the LB.** No `disabled`/`MAINT` toggles, no admin socket use, no ACL for a drain list. The only lever is the application heartbeat (`?id=lock` → body `Not Finished` → DOWN). `_placeholder … disabled` exists only to keep an empty backend syntactically valid. | template `:96-99,172` |
| Stats / metrics / health | `:8404/stats` (GET, 5 s refresh, `show-legends show-node`), `:8405/metrics` (prometheus-exporter, scraped by Alloy every 15 s), `:8406/healthz` (`monitor-uri`, used by keepalived's check `curl -sf --max-time 1`) | `common.yaml:177-206`, `profile/manifests/haproxy.pp:82` |
| VIP failover | keepalived FAULT mode: `track_process haproxy` (ms) + `track_script` every 1 s, `fall 2`; backup claims the VIP in ≈27 ms after a resign advert. If HAProxy is down on **every** node the VIP disappears. | `profile/manifests/haproxy.pp:315-340` |

### 1.4 How config reaches the LB

1. **Puppet** (agent cron every 2 h at a random minute, `PC/README.md:21-38`; r10k deploys `production` every 30 min on the masters, `:57`) manages `haproxy.cfg` (global/defaults/static frontends/`bk_default`/`resolvers` from hiera via `create_resources('haproxy::frontend|backend|resolver', …)`, `profile/manifests/haproxy.pp:290-294`), the four `.ctmpl` files, and the consul-template `config.json`. A template change → `notify Service['consul-template']` → restart → immediate re-render.
2. **consul-template 0.42.0** (`common.yaml:230-256`): blocking queries against Consul (`max_stale 10m`, retry forever), four watches, each `wait 15s:120s` (render after 15 s of quiet, at most 120 s after the first change), then `command: haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/conf.d/ && systemctl reload haproxy` (`command_timeout 30s`, `backup: true`). **If `haproxy -c` fails the reload is skipped and HAProxy keeps the previous in-memory config** while the on-disk file is already the bad one — a later unrelated restart would then come up broken (the hazard `IA/docs/MIGRATION_AGENT_REGISTRATION.md` Phase 5 calls out for duplicate `server` lines).
3. Reload is master-worker (`-Ws`), so keepalived's process tracker does not fault during a reload (`profile/manifests/haproxy.pp:318-324`).

So: **a deployconf change reaches HAProxy via k8s-invApi (seconds with the webhook, ≤1 h by poll) + consul-template (15–120 s) + reload. Puppet is only involved when the templates or haproxy.cfg change.**

---

## 2. k8s-invApi: deployconf → Consul catalog

### 2.1 What it is

A Flask+Gunicorn service (`IA/entry.sh`: 4 workers × 8 threads, `--preload`) on GKE in `atypon-devops`, 2 replicas, deployed by GitHub Actions bumping the tag in `atypon/k8s-invApi-helm` (`IA/docs/DEPLOYMENT.md`). Prod URL `https://k8s-invapi-gcp.devops.atypon.com`, dev `…-dev-gcp…`. It parses **deployconf from git** — `DEPLOYCONF_REPO_URL=https://github.com/atypon/deployconf`, `GIT_BRANCH=main`, `fetch` + `reset --hard origin/main` (`IA/docs/CACHING_AND_SCHEDULER.md:14-47`) — **not** the Consul KV copy that ConsulPopulate/`ConsulPutKV.py` writes under `deployconf/<env>/…` (note 06:30-32). Those are two independent deployconf→Consul paths: the KV copy feeds platform-tools/`setprod --source-env` and the node-selector extension; the **catalog** feeds HAProxy. The legacy `/consul` webhook in `IA/inv-API/api.py:796-830` is the old trigger for the KV path (fires a Rundeck job) and is marked superseded.

### 2.2 Parsing (`IA/inv-API/discovery/literatum_discovery.py`, 300 lines, read fully)

For every `deployconf.<env>.xml` in the repo (env = filename middle, `alloy_deployconf_discovery.py:704-711`), for each `<product enabled="true" name deployfamily>` (skips `$PLACEHOLDER` skeletons, `:133-139`), for each `<server type=…>` with `<port><web>` (skip if absent, `:177`), for each `<machine>` that has `<process name="web">` and whose name starts with `<product>-<servertype|stag|prod|lts|beta>-web` **or** is a direct child of the product (`:227-260`):

- **port** = `<port><ssl>` if present (then `backend_scheme=https`, `http_port=<web>`), else `<port><web>` (`:201-209`). backstage/rbackstage/backoffice targets use the web port and are registered too, but HAProxy fronts only `type=web`.
- **public_url** = `<product><hostname>` text (`:152-155`) → the `domain=` tag → the frontend ACL. In practice these are `*-prod.literatumonline.com`, `*-stag.literatumonline.com` origin names (see §2.6), not the publisher's public domain.
- **snippets** from `<product><haproxy><backend-snippet>` (`:41-65`; unknown names dropped with a warning).
- Whole body in `try/except` → a bad fragment yields fewer targets, never an error (`:298-299`).

### 2.3 Registration contract (`registration_contract.py:202,445,618-700`; `docs/CONSUL_SYNC.md`)

| Item | Rule | Example |
|---|---|---|
| Consul **service name** | `<envtype>-<product>-<type>`; `<envtype>-<product>-<family>-<type>` only when that product has >1 family in that env | `literatum-acm-web` |
| **Instance ID** = Consul `Node` = `Service.ID` = HAProxy server name & cookie | `<host>-<port>-<envtype>-<type>` | `web102-6065-literatum-web` (the DS `tf_argo_tunnel.sh:22-23` usage text uses exactly these) |
| Address | the **hostname** (prod runs `CONSUL_SYNC_SKIP_RESOLVE=true`; GKE cannot resolve DC names) | `web102` |
| Tags | `envtype=`, `type=web`, `service=literatum`, `product=`, `family=`, `domain=<hostname>`, `backend-scheme=https`, `http-port=<web>`, `snippet=…` | |
| NodeMeta | `external-source=inventory-service` (ownership marker; reconciliation only touches these), `external-node=true` (for Consul ESM) | |
| Check (optional, `HEALTH_CHECK_ENABLED`) | node check `service:<instance_id>`, `GET {scheme}://{name}.int.atypon.com:{port}/heartbeat?id=achs`, 10 s / 3 s, `TLSSkipVerify` when https, **status-code only**, no `DeregisterCriticalServiceAfter` | `health_checks.py:114-235`, `docs/HEALTH_CHECKS.md` |

Identifier validation drops rows with characters outside `[A-Za-z0-9-_.]`. A row whose instance_id equals a real hostname is dropped (agent-collision guard).

### 2.4 Refresh cadence and reconciliation (`alloy_deployconf_discovery.py:360-430,497-680`; `consul_sync.py:457-660`)

- **Push-driven**: GitHub webhook `POST /webhooks/github` on push to `main` of deployconf (and of the nonlit repo) → `force_update()` in a background thread → 202. Followers forward to the leader through a Consul KV key.
- **Poll backstop**: `DEPLOYCONF_REPO_REFRESH_INTERVAL_SECONDS` (default 300; **prod 3600**). Failed cycles back off 60 s → 600 s with jitter.
- Each cycle: git pull → parse **every** XML (full rebuild, no diff) → sticky guards (deployconf parsed 0 envs but had data before → keep cache, **skip sync**) → `sync_services_to_consul`: read owned nodes (`/v1/catalog/nodes?node-meta=external-source:inventory-service`, must succeed or abort), read `/v1/health/service/<name>` per desired service, diff on `service_name/address/port/tags/check_signature`, register changed, **deregister owned nodes not desired** (`CONSUL_SYNC_DEREGISTER=true`), 16 threads, 4 retries on 5xx. Empty-desired guard refuses to deregister when the parse produced nothing.
- Only the **leader** pod writes (`CONSUL_SYNC_LEADER_ELECTION`, KV lock, TTL 30 s, stall step-down after 600 s).
- Zero writes on a no-change cycle → Consul index does not move → consul-template does not re-render.

### 2.5 How a stale or wrong deployconf shows up

| deployconf state | Consul catalog | HAProxy | Client sees |
|---|---|---|---|
| Product `enabled="false"` or removed | instances **deregistered** next sync | backend and its `use_backend` lines disappear | **404** `no haproxy backend matches this host` (bk_default) |
| Product present, **no `<machine>` with `<process name="web">`** matching the name pattern | service exists with 0 instances, or not at all | `server _placeholder … disabled` | **503** |
| Wrong `<port><ssl>`/`<port><web>` | instance registered on the wrong port | check fails (refused / TLS error / `400 requires TLS` if the ssl port points at a plain port) → DOWN | 503 if it was the only instance; otherwise traffic shifts to siblings silently |
| Machine listed but never brought up (deployconf = intent, not reality — `MIGRATION_AGENT_REGISTRATION.md:68-76`) | registered, check critical forever | DOWN forever, harmless | nothing; but `stats` shows a standing population of DOWN servers, so DOWN alone is **not** a signal |
| Host listed under product A actually serving product B on that port | registered under A | **`?id=achs` is product-agnostic** (`literatum-backends.cfg.ctmpl:56-58`) → UP | product A's domain is routed to product B's JVM (wrong site / 404s), and the LB considers it healthy |
| `<hostname>` missing or invalid | registered **without** `domain=` tag | backend rendered, **no frontend ACL** | 404, even though `stats` shows the backend UP |
| A push to deployconf but webhook missed | catalog lags up to 3600 s (prod poll) | lags the same | old routing; check `/services/sync-history`, `/debug/status` commit hash |
| deployconf `main` unparsable / git down | sticky guard keeps last good catalog; `invapi_sync_guard_trips_total{sticky_deployconf}` | unchanged | nothing — by design |
| `haproxy -c` rejects the render (e.g. duplicate `server` name, bad snippet) | correct | **no reload**, stale in-memory config; on-disk file already bad | nothing until the next HAProxy restart, which then fails |

### 2.6 Cross-environment hostname collision (new finding)

`<hostname>` values were extracted from `DC/deployconf.{literatum,staging,midtierbeta,readonly}.xml` and compared (82 / 80 / 87 / 92 unique). **literatum and readonly share 17 hostnames** (e.g. `achs-prod.literatumonline.com`, `acm-prod.literatumonline.com`, `apha-prod.literatumonline.com`); staging/literatum and staging/midtierbeta share none. Both envs register `domain=<same>` so the frontend gets **two exact-match `use_backend` lines for one host**; HAProxy takes the first, and consul-template iterates services in Consul's sorted order, so `bk_literatum-acm-web` wins over `bk_readonly-acm-web` by **lexical accident** ("literatum" < "readonly"). The readonly web tier is therefore unreachable by hostname through this HAProxy. How the RO switch (DS `SwitchToROMode`, `ValidateWebOnROMode`) is meant to reach the edge is **not modelled here — Unverified**; it is not done by this LB config.

---

## 3. Tie-in with deploys

### 3.1 The web-host chain (note 01 §589, `DS/…/CreateActionVisitor.java:78-79`)

`HostLock → Pause1Min → HostStop → HostDeploy → HostStart (+HostWaitForWebServer) → HostWarmupTest (+HostEssentialTest) → HostUnlock`, per web host, alphabetically (or `parallelCount` groups).

| Step | What the node does | What HAProxy does | Time to effect |
|---|---|---|---|
| **HostLock** = opstool `DeployFamilyAction -t lock` → `GET localhost:<web>/heartbeat?id=lock&bg=1` (note 18 §3.1) | `unlocked=false` (`HeartBeatServlet.java:383-395`; only from private/loopback callers). From now on `checkDatabase()` returns `1` and **`?id=achs` returns `Not Finished` (HTTP 200)**. `CloseConnectionWhenLockedFilter` adds `Connection: close` to every response (`L/…/CloseConnectionWhenLockedFilter.java:16-22`), so HAProxy's reused keep-alive connections (`http-reuse always`) are torn down. | Body mismatch → check fails; after **3 consecutive failures × 3 s ≈ 9 s** the server is **DOWN** ("L7RSP", "Layer7 invalid response" on the stats page). Sticky clients (JSESSIONID prefix) are moved to another server; `option redispatch` handles the cookie. | ≈9–12 s. **`Pause1Min` gives 60 s**, so the LB is guaranteed to have drained new connections before HostStop; requests still in flight on the old server up to `timeout server 60s` are the residual risk. |
| **HostStop** (`rstrt` stop) | port closes | already DOWN; if the lock had *failed*, connection refused → L4 fail → DOWN after ≈9 s, with `retries 3`+`redispatch` covering new connections and **5xx/`SC` termstates** for requests mid-flight | — |
| **HostDeploy** | files only | nothing | — |
| **HostStart** | Tomcat comes up; `unlocked` re-initialised from `acs/startWebServerUnlocked` (**true** in base) but `released=false` and `acs/heartbeatBasedOnTestResults=true` ⇒ `isUnlockedAndReleased()==false` ⇒ `achs` = `Not Finished` (note 12 §1.6, `HeartBeatServlet.java:202-214`) | check gets 200 + wrong body → stays **DOWN**. **The LB never routes to a started-but-not-unlocked node.** | — |
| **HostWaitForWebServer** = `-t serverup` | passes on any 200 from `/heartbeat?bg=1`, body ignored (note 18) | irrelevant to HAProxy | — |
| **HostWarmupTest / HostEssentialTest** | Selenium via `https://<host>.localhost.literatumonline.com:<ssl>` directly on the node | nothing | — |
| **HostUnlock** = `-t unlock` → `?id=unlock` | `unlocked=released=true`, `ServerHealthChecker.resumeChecking()` (`:373-381`). `achs` now = `AtyponLiteratumWorksGreat` **iff `DbConnMgr.getConnection()` succeeds** | **2 good probes × 3 s ≈ 6 s → UP**; traffic resumes | ≈3–6 s |
| Background path | `StartupCheck` polls its own `/heartbeat` every 30 s; on `1` it calls DS `/unlock` → **TestAsync** → HostWarmupTest → HostUnlock (note 12 §1.6). Also `ServerHealthChecker` can re-**lock** a node (DB pool >90 % or memory >90 %) → `achs` flips to `Not Finished` → LB drops it in ≈9 s and mails "heart beat lock scheduled|triggered". | same as above | — |

Nothing in the chain touches Consul or HAProxy directly; the LB follows the heartbeat.

### 3.2 "Site down after deploy" at the LB level

| Symptom at the edge | Cause | Where to look (read-only) |
|---|---|---|
| **503** for the product's domain (HAProxy's own 503, `termstate` `SC`/`sC`, `server=<NOSRV>`) | all servers of `bk_<env>-<prod>-web` DOWN: every node still locked (HostUnlock never ran, e.g. `parallelizeDeployActions` dropped it, note 01 B10/§584), DB unreachable from the web tier (`HeartBeat Error` in the literatum log → `achs` = `Not Finished` although HostUnlock said `RESULT:SUCCESS`), or the backend has only `_placeholder` | `http://<haproxy-vm>:8404/stats` (per-server status + last check result), `:8405/metrics` (`haproxy_server_check_status`, `haproxy_server_status`), `/var/log/haproxy/access.log`; syslog alert `backend bk_… has no server available!`; on the node `curl -sk https://localhost:<ssl>/heartbeat?id=achs` (must say `AtyponLiteratumWorksGreat`) |
| **404** `no haproxy backend matches this host` | no `use_backend` for the Host header: product disabled/removed in deployconf, `<hostname>` missing/changed, or the client uses a name that is neither the exact `<hostname>` nor a `*.literatumonline.com` subdomain of it | `curl -s https://k8s-invapi-gcp.devops.atypon.com/services?service=literatum` (does the product have a web entry with `public_url`?); Consul `GET /v1/catalog/service/<env>-<prod>-web` (tags contain `domain=`?) |
| Domain resolves to the **wrong product/env** | hostname collision (§2.6) or a machine listed under the wrong product (§2.5) | compare `domain=` tags across `/v1/catalog/services?filter=…` for the hostname; rendered `/etc/haproxy/conf.d/literatum-frontend.cfg` on the LB |
| Node deployed and unlocked but **not in the backend** | inv-API has not registered it: deployconf change not yet merged to `main`, webhook missed (poll up to 1 h), consul-template still in its `wait` window, or `haproxy -c` failed | invapi `/debug/status` (commit hash), `/services/sync-history`, `/services/health` (`sync_leader_node`, last_update); Consul `GET /v1/health/service/<svc>`; on the LB `systemctl status consul-template` / `journalctl -u consul-template` for the `haproxy -c` error |
| Everything UP in HAProxy but the site is unreachable | edge in front of HAProxy: VIP not held (all keepalived FAULT), cloudflared down | `curl -s http://127.0.0.1:8406/healthz` on each LB; `ip addr` for the VIP; `cftunnel-*` hosts |

Consul catalog checks an operator can run (GETs only, need the read token; base `https://consul-gcp.devops.atypon.com` per `IA/docs/MIGRATION_AGENT_REGISTRATION.md:112-113`):
- `/v1/catalog/service/literatum-<product>-web` — instances, ports, tags.
- `/v1/health/service/literatum-<product>-web` — same plus the ESM check status (**informational only**; HAProxy ignores it).
- `/v1/catalog/nodes?node-meta=external-source:inventory-service` — everything inv-API owns.
- `/v1/catalog/node/<host>-<port>-<env>-web` — one instance.

### 3.3 Timing summary

| Event | LB reaction |
|---|---|
| HostLock | out of rotation in ≈9 s (fall 3 × inter 3 s); 60 s pause before stop |
| HostStop | already out; otherwise L4 refused → out in ≈9 s, in-flight requests lost |
| HostStart | stays out (locked) |
| HostUnlock | back in ≈6 s (rise 2 × 3 s) |
| deployconf merge → new server line | webhook: seconds; poll: ≤3600 s; then consul-template 15–120 s; then reload |
| Puppet template change | ≤2 h (agent cron) after r10k (≤30 min) |

---

## 4. Success reported while the LB disagrees (and vice versa)

1. **HostUnlock `RESULT:SUCCESS` but the node stays DOWN.** Unlock only flips `unlocked/released`; `achs` additionally needs a live DB connection (`HeartBeatServlet.java:158-196,216-227`). A web node with a broken DB pool passes HostWaitForWebServer (body `1` accepted) and HostUnlock, and still returns `Not Finished` to HAProxy. Signature: `HeartBeat Error` + stack in the literatum log; server DOWN with a Layer-7 body mismatch on `:8404/stats`.
2. **HostLock always Success (no validator, `DS/config/actions.xml:1462-1466`) while the node keeps taking traffic.** If the lock fetch fails (timeout >3 s, non-200) the node is never locked, `Pause1Min` waits for nothing, and HostStop kills a server that HAProxy still considers UP → a burst of 5xx / `SC` termstates until 3 probes fail. Signature: `DeployFamilyAction.ERROR> Lock …` or `status=false` in the HostLock log (the action is green anyway).
3. **Vacuous `RESULT:SUCCESS`** (note 18 §6.2): if the host's local `~/deployconf.xml` does not list the family on this machine, nothing is locked or unlocked. Same LB consequences as 1 and 2, with **no `DeployFamilyAction.<Action>` line** in the log.
4. **HostUnlock unlocks every product of the family on the host** (`-p` ignored, note 18): a sibling product mid-deploy on the same host goes UP at the LB before its own tests ran.
5. **HAProxy UP for the wrong thing.** `?id=achs` is the same URL for every product and never checks product identity, so a deployconf row pointing at a port that serves another product is healthy at the LB (§2.5).
6. **ESM/Consul "passing" means nothing to HAProxy** (`"any"`), and **HAProxy "UP" means nothing to Consul**. The dashboard/Consul UI can show critical while the site is fine, and passing (status-code-only check, `Not Finished` is a 200) while HAProxy has the node DOWN. Do not triage LB state from Consul health.
7. **consul-template renders, `haproxy -c` fails, reload skipped**: Consul, inv-API `/services/sync-history` and the on-disk `.cfg` all look right; HAProxy runs the old config. Only `journalctl -u consul-template` shows it. The next `systemctl restart haproxy` fails to start.
8. **`sticky_deployconf` / `empty_desired` guards** keep the last good catalog on a failed parse — correct as a safety net, but a genuine "remove everything" change is silently refused; only `invapi_sync_guard_trips_total` and the pod log say so.
9. **Consul-side deregister without an HAProxy change**: `DeregisterCriticalServiceAfter` is never set, so nothing auto-deregisters; but if an operator deregisters a node by hand, consul-template drops the `server` line and reloads — the LB changes with no deployconf or DS event.
10. **All three HAProxy tiers render every environment.** A midtierbeta hostname is routable through the prod VIP and vice versa (domain routing only, `PC/data/servertype/haproxy/prod.yaml:26-31`), so "prod LB is fine" does not prove prod isolation.

---

## 5. Failure-signature table (log text → cause → check)

| Where | Text / observation | Meaning | Read-only check |
|---|---|---|---|
| HAProxy syslog / journal | `backend bk_<svc> has no server available!` | all servers DOWN (locked, DB down, stopped, wrong port) | `:8404/stats`; node `curl -sk https://localhost:<ssl>/heartbeat?id=achs` |
| HAProxy syslog | `Server bk_<svc>/<id> is DOWN, reason: Layer7 invalid response, info: "HTTP content check did not match"` | `achs` returned `Not Finished`: node locked or DB unavailable | literatum log `HeartBeat Error`; DS: was HostUnlock run? |
| HAProxy syslog | `… is DOWN, reason: Layer4 connection refused` / `Layer4 timeout` | JVM stopped / not listening / wrong port in deployconf | `ss -ltn` on the node vs `<port><ssl>` in deployconf and Consul `Port` |
| HAProxy syslog | `… is DOWN, reason: Layer6 invalid response` / SSL handshake failure | plain-HTTP port registered with `backend-scheme=https` (deployconf `<ssl>` wrong) | Consul tags `backend-scheme`, `http-port` |
| HAProxy syslog | `… is UP, reason: Layer7 check passed` ≈6 s after HostUnlock | normal | — |
| HAProxy access.log | `status=503 … termstate=SC server=<NOSRV>` | no server available at request time | as row 1 |
| HAProxy access.log | `status=404 backend=bk_default` | Host header matched no `use_backend` | inv-API `/services?service=literatum` has `public_url`? Consul `domain=` tag present? |
| HAProxy access.log | `status=502/504 termstate=SH|sH` | server closed / timed out mid-request (stop without lock, `timeout server 60s`) | correlate with HostStop time in DS |
| consul-template journal | `(runner) … haproxy -c …: exit status 1` / `Configuration file is valid` absent | render rejected; **HAProxy still on old config** | `haproxy -c -f /etc/haproxy/haproxy.cfg -f /etc/haproxy/conf.d/` (read-only) |
| consul-template journal | `error_on_missing_key` never fires (set false); repeated `rendering` with no `command` | quiescence `wait 15s:120s` still running | wait, or check Consul index |
| inv-API log / metrics | `deployconf produced 0 environments but N are already cached … skipping Consul sync` ; `invapi_sync_guard_trips_total{guard="sticky_deployconf"}` | git/parse failure; catalog frozen | `/debug/status`, `/services/health` |
| inv-API log | `product X asks for unknown HAProxy backend-snippet 'y' — dropped` | typo in `<backend-snippet>`; product renders without the snippet | deployconf `<haproxy>` |
| inv-API log | `Skipping template-skeleton product … $PRODUCT_NAME` | placeholder rows ignored (expected in `deployconf.asal.xml`) | — |
| inv-API log | `Consul sync: FAIL register|deregister <id>` / `existing_external_nodes` failure → sync aborted | Consul write/read failure; catalog stale | `/services/sync-history`, `invapi_last_sync_success` |
| inv-API metrics | `sum(invapi_sync_leader) != 1` | no writer or split brain | `/services/health` `sync_leader_node` |
| DS HostLock log | `DeployFamilyAction.ERROR> Lock …` or `status=false` (action still **Success**) | node not locked; LB keeps routing until HostStop kills it | HAProxy access.log 5xx burst at HostStop time |
| DS HostLock/Unlock log | `RESULT:SUCCESS` with no `DeployFamilyAction.<Action> for …` line | vacuous: family not on this host in `~/deployconf.xml` | `~/deployconf.xml` on the host vs `<machine name>` |
| literatum log | `heart beat lock scheduled|triggered for product <p> on machine <h>` | ServerHealthChecker self-lock; LB drops the node in ≈9 s | DB pool / memory on the node |
| literatum log | `HeartBeat Error` | `achs` = `Not Finished` although unlocked | DB connectivity from the node |

---

## 6. Coverage

- **Read fully**: `PC/site-modules/profile/manifests/haproxy.pp` (392), `role/manifests/haproxy.pp`, `profile/files/haproxy/{literatum-frontend,literatum-backends,nonlit-backends,nonlit-tcp-frontend}.cfg.ctmpl`, `data/servertype/haproxy/*.yaml` (all 7), `data/nodes/servers/grhaproxy.atypon.com.yaml`, `profile/manifests/consul_agent.pp`, `role/manifests/literatum/host/production.pp`, `profile/manifests/literatum/host/production.pp`, `hiera.yaml`, `manifests/site.pp`, `site-modules/consul_template/manifests/watch.pp` (first 60), `data/servertype/web.yaml`, `templates/patch-nginx.erb` (head). `IA/inv-API/discovery/literatum_discovery.py`, `discovery_base.py`, `health_checks.py`, `entry.sh`, `Dockerfile`, `scripts/sync_consul.py`, `.github/workflows/workflow.yaml` (first 80), `cloudbuild.yaml`, `registration_contract.py:618-705`; docs `README.md`, `DISCOVERY.md`, `CONSUL_SYNC.md`, `CACHING_AND_SCHEDULER.md`, `HEALTH_CHECKS.md`, `ARCHITECTURE.md`, `CONFIGURATION.md`, `DEPLOYMENT.md`, `OBSERVABILITY.md`, `MIGRATION_AGENT_REGISTRATION.md` (to line ~350 of 571). `L/…/HeartBeatServlet.java:60-70,150-235,360-400`, `CloseConnectionWhenLockedFilter.java`. `DS/config/actions.xml:1440-1475,1550-1580`, `DS/scripts/tf_argo_tunnel.sh:1-60`.
- **Sampled (grep only)**: `IA/inv-API/consul_sync.py` (def/tag/register lines), `alloy_deployconf_discovery.py` (cadence, guards), `api.py` (routes, `/consul`, `/service/<acct>/add` head), `service_inventory.py`, `scripts/validate_haproxy_config.sh` (header); `PC/README.md` (agent cadence), `data/common.yaml:740-790`, `data/servertype/cftunnel/*` (non-secret lines), `role/manifests/cftunnel.pp`; `DS/src` for the HostLock/HostLockStop/HostUnlock chain; `DC/deployconf.{literatum,staging,midtierbeta,readonly}.xml` for `<hostname>`, `<ssl>`, `<web>`, `<haproxy>` counts; `L/…/IntranetFilter.java`, `StartupCheck.java`; `platform-tools/restart.py`, `lock.py` (head).
- **Not read**: the rest of `api.py` (2793 lines), `api_helpers.py`, `nonlit_source.py`, `pr_plan*.py`, `octo_sts.py`, `sync_metrics.py`, tests, `docs/{API_REFERENCE,DASHBOARD,MULTI_WORKER,NON_LITERATUM_SOURCE,SERVICE_INVENTORY,WORKFLOW}.md`, `docs/legacy-archive/*`; `PC/Puppetfile`, the vendored `haproxy`/`keepalived`/`consul_agent`/`consul_template` module internals (beyond `watch.pp`), `profile/manifests/cftunnel.pp`, `doc/*.md`; DS `PostExecuteVisitor` TestAsync path (taken from notes 01/12).
- **Unverified**: the live values of `CONSUL_SYNC_ENABLED`, `HEALTH_CHECK_ENABLED`, `CONSUL_SYNC_SKIP_RESOLVE`, the refresh interval and the health-checks ConfigMap (all in `k8s-invApi-helm`, not cloned — the docs' claims were taken at face value); whether `profile::consul_agent::enable` is true on any literatum host; whether the legacy `haproxy-0/1` pair is still live; HAProxy's exact log wording for check failures (HAProxy 3.0 defaults, from general HAProxy behaviour, not from a captured log); the `timeout check` = `inter` inference; how readonly traffic is meant to reach the edge (§2.6); per-product overrides of `acs/heartbeatBasedOnTestResults` (a `false` would let a node self-release after 1800 s without tests, and the LB would take it).

> **Correction (2026-09-27, verified in code):** the `?id=achs` heartbeat does NOT check lock/release. `HeartBeatServlet.checkAchs` (lit-2610 :216-227) returns `AtyponLiteratumWorksGreat` whenever `checkDatabase()==SERVER_AVAILABLE`; `!isUnlocked()` is commented out. Only `?bg=1` (:169, `isUnlockedAndReleased`) honours the lock. So HostLock → "DOWN in ≈9 s" is wrong: the node leaves HAProxy only when the JVM stops (HostStop), ≤9 s later. The rest of the chain (Consul → consul-template → HAProxy, k8s-invApi from the deployconf git repo) stands.
