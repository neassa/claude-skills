---
name: focus-bench-load-test
description: Use when running or validating a focus-poc load/performance test (node or HD env) — the focus-users.py harness / self-extracting kits, pool-mode auth, per-site discovery, and how to confirm the numbers are real.
---

# focus-poc load testing

JMeter-style harness at `~/Downloads/projects/emdash-bench/bench/`. One `threading.Thread` per virtual user; `--rps N` = throughput ceiling (needs enough `--users`); think time + ramp; results TIMESTAMPED in `./…-results/`. Run it on a **remote box (prod102/stag), not the laptop** — WARP caps ~40 req/s.

## Run (turnkey kits — token/creds baked)

- **Node:** `dist/focus-bench-node.py` — defaults to `node-pool-mix-80u` (authenticated, stag Connect, target `_node-poc-hosted`).
- **HD:** `dist/focus-bench.py` — defaults to `hosted-pool-mix-80u` (stag Connect, target `_hd-poc-hosted`, has `topic`).

Standard cases (30 min): `--rps 25 --duration 1800 --users 120 --sample 500` and `--rps 56 … --users 180 …`. First run add `--rediscover`; drop it after (cache reused ≤6h). Anonymous instead: node `--plan plans/node-writemix-80u.json`.

**Remote kit path (stag boxes):** `/atypon/scratch/personal/ljanaideh/bench/` — both kits scp'd there (confirmed on prod102; same convention on achs-stag-web1). Push: `scp ~/Downloads/projects/emdash-bench/bench/dist/focus-bench.py staging@<box>:/atypon/scratch/personal/ljanaideh/bench/`. Pull results: `scp -r 'staging@<box>:/atypon/scratch/personal/ljanaideh/bench/focus-bench-results/<date>*' ~/Downloads/`. Stag hostnames may not resolve from the laptop shell — use the FQDN/ssh-config alias.

**Run detached** (survive SSH disconnect): `nohup python3 <kit> … > pt-<env>-$(hostname -s)-$(date +%Y%m%d-%H%M%S).log 2>&1 &`. On the atypon stag boxes `screen` is wrapped by `script` and exits immediately — **use nohup, not screen**. Result files don't collide across boxes (name carries the target `_node-`/`_hd-poc-hosted`). Report columns per action: **Med/Sci sample split · median Bytes · Cache** (DYNAMIC=origin, HIT=CDN) — so a run self-validates.

## k6 harness (full port, 2026-09-08)

Grafana k6 **v2.2.0** at `~/.local/bin/k6` (manual binary — update via GitHub release tarball, NOT apt). All scripts in `~/Downloads/projects/emdash-bench/bench/`; `k6 inspect <script>` compiles without traffic — always run it first. **Current node hosts: `medicine-focus-poc.literatum.com` + `sciences-focus-poc.literatum.com`** (in focus-targets.json `_node-poc-hosted`; site slug stays `science`), on PUBLIC DNS — reachable without WARP, so heavy runs can go from any box. Verify target identity before load (title + `/_emdash/api` + OIDC issuer — see memory [[verify-target-before-load]]).

- **`k6-read-mix.js`** — anon read mix (detail 69 w/ folded topic, search 9, hub 9, home 7, sponsor 5), URLs from the discovery cache, soft-404 check (200 + >20KB + no "Page not found"). Knobs `-e`: `RPS`, `DURATION`, `TARGET`.
- **`k6-pool-mix.js`** — full port of `node-pool-mix-80u` (detail 55/topic 14/search 9/hub 9/home 7/sponsor 5/content_write 8/media_write 3). setup(): pool login (5 stag creds x 2 sites), image-pool upload (dedup-idempotent), dynamic topic rediscovery from content_groups (works: 18 med/17 sci). Writes = bearer `FOCUS_API_TOKEN` (extract: `sed -n 's/^TOKEN = "\(.*\)"/\1/p' dist/focus-bench-node.py`), create->delete + PNG-in-JS multipart upload->delete, self-cleaning. `-e AUTH_MODE=anon` skips pool login (reads anon — on node authed~=anon). **RPS = iterations/s; write iterations do 2 requests -> total ~1.11xRPS.**
- **Turnkey kit:** `dist/k6-focus-kit.tar.gz` (30M: binary + scripts + config + creds + discovery) — untar anywhere, `source k6-secret.env`, run. **Rebuild the tarball after ANY script edit** — it ships a snapshot, so an edited script does not reach the remote box until you re-tar (shipped a stale pre-threshold script once).
- Old `k6-smoke.js` starter is superseded.

### Per-action breakdown = thresholds, not tags
k6 tags every request (`action`, `site`) but the end-of-run summary prints a per-tag line **only for tags a threshold references** — verified 2026-09-10 with a minimal local repro (same script, tags alone → zero `{action:…}` lines; add `'http_req_duration{action:alpha}': ['p(95)<3000']` → the line appears). So to get the python harness's per-action table out of k6, declare one loose threshold per action and per site (see the block at the top of `k6-pool-mix.js`); the real pass/fail signal stays `http_req_failed` + `checks`. Add `--summary-export=results/<name>.json` for the machine-readable copy; `results/k6-sample.json` is a kept reference sample.

Short validation runs give **directional** per-action percentiles only — a 90 s run puts ~30 samples in `search`. Judge tails only on the 30-min runs (45k+ iterations); see the p99 note below.

## Auth = pool mode (stag)

**2026-09-08: ALL 5 pool accounts are NOT_FOUND on stag Connect** (`errors[0].code=NOT_FOUND` pointer=identifier on `/api/rest/login/password`) — wiped since the Aug runs. Pool mode is blocked until they're recreated; the bearer API token still works (writes unaffected). Until then run k6-pool-mix with `AUTH_MODE=anon`.

`login_mode: pool` via `focus-auth-stag.json` (`https://wiley.stag.connectscience.io`): the 5 `ljanaideh+1..5@atypon.com` accounts log in ONCE at preflight, then sessions replay as cookies (no ongoing Connect load). Watch for `[auth] pooled session (… @ medicine/science)`; `ABORT: … no credential could log in` = the env's OIDC/`CONNECT_CLIENT_SECRET` isn't wired for stag. **Stag password differs from rehearsal's `Az123456789#`** (inline `user:pass` in credentials.txt override `FOCUS_CONNECT_PASSWORD`).

## Discovery = per-site early-stop

Pages each collection's API list and probes ONLY sites still short of `--sample`, stopping when every site is full (`DISCOVERY_MAX = sample×20`, probe concurrency 48). Replaced the old shared `sample×6` pool that showed `medicine renders 0` for tail-ordered content. Check the `[diag]` lines read `renders 500` on BOTH sites. **Topic discovery is dynamic** (from `content_groups` where `page_type=topic`, probed per site — not the old hardcoded slug list, which only matched HD's real slugs and left node at `live topics=0`). Confirm `live topics>0`.

## Per-site content counts (no DB needed)

The **content API is env-wide** — `GET /_emdash/api/content/{coll}?status=published&limit=1` → `data.total` is per-collection but NOT per-site (both hosts return the same; items carry no taxonomy). For the **medicine/science split**, use the **taxonomy API**: `GET /_emdash/api/taxonomies/specialty_methodology/terms` returns the term tree with a `count` per term — sum each root's subtree (`medicine` vs `science`). Validated against the node DB (±0.3%), and it works for HD too (whose DB is KMS-walled). Finding: node ~50/50; HD ~86/14 medicine-skewed (test load stays 50/50 by design regardless).

**Seed composition (verified on node DB, 2026-08).** The build seed (`.emdash/seed.json` from `custom/sites/focus/seed/*.json`) contains only **6 collections + 5 taxonomy defs + 91 sponsor rows** — NOT the article volume. Article content is loaded separately by `db/seeds/*_dummy_pg.sql`. Taxonomy term counts in the node DB (exact match to `seed/taxonomies.json`): `specialty_methodology` 40, `subject` 13, `wol_taxonomy` 904, `gated_content` 2, `sponsor` 91; the `sponsors` content table held 20,958 rows. Manual reseed = `bootstrap-seed.mjs` (schema/taxos/sponsors) or the dummy SQL (content) — see the `focus-node-db-access` skill and memory [[focus-node-bootstrap-seed]].

## Validate a run (don't trust the report alone)

From the `.jtl.csv` (cols incl. `status,bytes,cf_cache,server_timing`):
- **Full pages?** detail/home/search `bytes` should be ~100–190 KB, `status=200`, `cf_cache=DYNAMIC` (origin SSR), and carry `server_timing` (`render`+`db.total`). Tiny/uniform bytes = soft-404 (focus serves 404 as 200 + "Page not found").
- **Writes real?** create `201`, delete `200`, media upload `201`.
- **Assets are light by design** — a few CSS/JS bundles per user, once (`assets=first`), all `cf_cache=HIT` (CDN, never hit origin). This is an **app-capacity** test, not a full browser-asset simulation.
- **Authed vs anon:** re-fetch a detail URL anonymously and compare `bytes` — on **node** authed≈anon (gating is cosmetic, ~2 KB), so auth isn't a meaningful axis there; re-check on HD before claiming a gating difference.

## Gotchas
Sessions are per-container filesystem → keep `desired_count=1` or use ALB stickiness (PR #304) for multi-task. Node app-CPU ceiling ~56 req/s is single-vCPU; earlier scaling-matrix numbers were confounded by a recovery/seeding trend — re-run back-to-back on a settled env. Output stays **plain text — no decorative emoji** in tables/reports (see [[no-decorative-emoji]]).

**HD webinars 500 — FIXED (verified 2026-08-16).** Previously every HD webinar detail page threw HTTP 500 (`WebinarDetail` used `GatedContent`+`Icon`, one threw on the Worker runtime) and discovery silently dropped `webinars` from HD detail. The Aug 16 runs serve full webinar detail pages (~116 KB, 0 errors), so discovery re-includes them — **per-action sample counts shift vs pre-fix runs** (other detail types drop from ~6.8k to ~5.1k @25rps). Compare like-for-like actions, not just the TOTAL row, across the fix boundary.

**p99 is noise below ~1,500 samples** — at `--sample 500` a create/delete action's p99 is its ~5 slowest requests; apparent p99 regressions there aren't real if the same action at 56 rps (2× samples) is flat. Judge tails on p95 or on high-sample actions.

**Headline result (Aug 2026, pool-mode, 0 errors):** node ~2× faster than HD (avg 144/156 ms @25/56 vs HD 318/292 ms); medicine slightly slower than science on both (node +7%, HD +30%). **HD rerun 2026-08-16 vs 08-11:** HD itself got faster — median -7% @25 (275→257 ms), -14% @56 (257→222 ms), tails much tighter (media upload p95 1034→564 ms); origin `server_timing` barely moved, so the gain is edge/network-side, plus webinars re-entering the mix.

**R2 write path (HD `media upload`/`media delete`):** the jitteriest actions in the mix — consistent with Cloudflare R2's public record (1 write/s per key limit, slow small-object PUTs, two 100%-write-failure incidents in 18 months). Context reports: `~/Downloads/focus-HD-compare-aug11-vs-aug16.html` (run comparison + R2-vs-S3 write table) and `~/Downloads/cloudflare-r2-stability-incidents.html` (incident record, write limits, S3-backup patterns); published at claude.ai/code/artifact/87aebd36-9049-4278-b097-c648e733e2fb and .../e5dda87f-2e4e-4f98-b3ea-e59bdbdc8cba.

Related: `focus-node-db-access`, `focus-node-passkey-recovery`, memory [[focus-bench-harness]], [[focus-poc-node-env]].
