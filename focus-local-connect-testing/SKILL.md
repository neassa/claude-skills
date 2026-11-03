---
name: focus-local-connect-testing
description: Use when running the focus EmDash admin (or its Connect/passkey/invite auth) end-to-end on the LOCAL machine — standing up the local Postgres, serving the site under a real hostname over HTTPS, testing against a mock or the real Wiley Connect IdP, or debugging why the local admin login/homepage/pending-invites won't work. Covers the whole rig plus the gotchas that waste an hour each.
---

# Testing focus EmDash admin auth locally

End-to-end local rig for the focus site's admin auth (Connect OIDC, passkeys, invites). Built and used 2026-09-02/03 while shipping `@focus/auth-connect` (#388). The pieces fit together in a specific way; each gotcha below cost real time.

## The rig

- **DB:** docker container `focus-local-postgres` (`postgres:17`, port 5432). Superuser `focus_admin` / `focus_admin_local`. Per-feature branch DB, e.g. `focus_connect_admin`. `docker start focus-local-postgres` if stopped.
  `PGPASSWORD=focus_admin_local psql -h localhost -U focus_admin -d <db>`
**Bring-up VERIFIED end to end 2026-09-22** on a throwaway DB (`focus_doc_test`, dropped after): `createdb` -> core
`migrate.mjs` (53 applied) -> `bootstrap-seed.mjs` -> `migrate-site.mjs` (17 applied), all exit 0. The seed really must sit
BETWEEN the two migration passes. The "no Postgres search backend registered" line from the seed is expected and harmless.
A content import needs far less than this: `load-seed.mjs` only needs `pnpm install` + `pnpm --filter emdash build`
(it imports `emdash/seed` from `packages/core/dist`) and libpq env vars — no astro build, no `.env`, no local DB when the
target is remote. See [[focus-node-db-access]] for which tunnel script to use for that.

- **Build a branch DB:** `createdb` → `node custom/infra/terraform/db/migrate.mjs` (core, ~52) → `pnpm --filter focus seed:merge` → `node custom/sites/focus/db/bootstrap-seed.mjs` (creates ec_* tables) → re-run `migrate-site.mjs` (site migs incl. 0006 fts need the ec_* tables to exist first, so seed BEFORE the second migrate). Env for these: `PGHOST=localhost PGPORT=5432 PGDATABASE=<db> PGUSER=focus_admin PGPASSWORD=focus_admin_local PGSSLMODE=disable`.
- **`.env`** at `custom/sites/focus/.env` (gitignored): `DATABASE_URL`, `EMDASH_SITE_URL`, `EMDASH_ALLOWED_ORIGINS`, `CONNECT_CLIENT_SECRET`, `EMDASH_LOCAL_MEDIA=1`.

## Serving under a real hostname over HTTPS (needed for real Connect + passkeys)

1. `/etc/hosts`: map the hostname to loopback. Add BOTH `127.0.0.1 host` AND `::1 host` — with systemd-resolved the AAAA lookup can win and hit real DNS otherwise. `sudo resolvectl flush-caches`.
2. Self-signed cert for the host (`openssl req -x509 ... -addext subjectAltName=DNS:host`). Trust it in Chrome's NSS store so there's no interstitial the extension can't click through: `certutil -d sql:$HOME/.pki/nssdb -A -t "P,," -n <name> -i cert.pem`.
3. Serve on :443 (EMDASH_SITE_URL has no port). Two ways:
   - **`astro dev`** (fast iteration): add a guarded `vite.server.https` block reading `DEV_HTTPS_CERT`/`KEY`; socat TCP-passthrough `:443`→`:4321`.
   - **prod build** (`pnpm build` + `node dist/server/entry.mjs`, HTTP on 4321): socat **TLS-termination** `OPENSSL-LISTEN:443,cert=,key=`→`127.0.0.1:4321`. Use the prod build when you need the **real email-provider behaviour** (the dev console mailer is auto-on only when `import.meta.env.DEV`, which hides the invite copy-link modal).

## Mock vs real Connect

- **Mock IdP** (fastest, no secret): a tiny node OIDC server (discovery + jwks + authorize page you type any email into + token endpoint issuing an RS256 id_token echoing the nonce). oauth4webapi refuses `http` for URLs it fetches, so serve the issuer/token/jwks over **self-signed HTTPS** (browser-facing authorize page can stay http). Point the admin provider at it via an env override in `astro.config.mjs`.
- **Real Connect**: needs the real `CONNECT_CLIENT_SECRET` and a **Connect-whitelisted origin**. Use the **hd domain** (`medicine-focus-poc-hd.literatum.com`) — it's decommissioned so hijacking it via /etc/hosts breaks nothing live, unlike the poc hosts which ARE production. Connect matches redirect_uri by **origin**, so any callback path on a registered origin works (no per-path re-registration). Staging Connect asserts the **`@atypon.com`** identity — provision users by the email Connect actually returns, not `@wiley.com`.

## Driving state for auth tests (no user creds needed for most)

You control the DB, so flip your own account's state to record each case: provisioned user → login succeeds; delete the user row (+cascade oauth link) → "not provisioned"; delete user + insert an `auth_tokens` invite for the email → auto-accept creates the user. Clear `astro_sessions` to force a fresh login. The ONE thing you can't do headless is authenticate AT Connect when its session has expired (it asks for a password) — that step needs the human. Never enter credentials.

## Gotchas (each cost real time)

- **`.env` is NOT loaded into `process.env`** by `astro dev`/the node server — Astro puts it in `import.meta.env` only. `readClientSecret`/`DATABASE_URL` read `process.env`, so `set -a; source .env; set +a` before launching, or they're empty.
- **`http://medicine.localhost` is NOT a secure context** for a *custom* hostname, so passkeys hide ("Passkeys Not Available Here"). Only bare `http://localhost` or HTTPS counts. This is why the multi-site dev host can't test passkeys — use HTTPS.
- **Backgrounded `socat`/`node ... &` get reaped** by the Bash tool's process-group kill (exit 144). Launch them with the tool's `run_in_background: true`, not shell `&`/`nohup`/`disown`.
- **A fresh build serves stale JS to an open tab** — the admin SPA wedges ("Loading EmDash…", screenshot times out) on cached chunks. Open a NEW tab to get the new build; a hard reload of the wedged tab often isn't enough.
- **Rebuild after code changes, then RESTART `node dist/server/entry.mjs`** — the standalone server does not hot-reload. "It works" against a build older than your last edit is a false positive; check the dist mtime vs your commit.
- **`sites.json` is baked at build time.** A host not listed 404s ("Not found") at the multi-site middleware — admin/`_emdash/*` still works (host-independent), but the public site needs the host in `config/sites.json` + a rebuild.

## Teardown (all local, reversible; keep it OUT of the PR)

`git checkout custom/sites/focus/astro.config.mjs custom/sites/focus/config/sites.json` · `rm custom/sites/focus/.env` · `sudo sed -i '/<host>/d' /etc/hosts` · `certutil -d sql:$HOME/.pki/nssdb -D -n <name>` · stop the run_in_background socat/server tasks · `docker stop focus-local-postgres`. The astro.config HTTPS block, the sites.json extra host, and `.env` are local scaffolding — never commit them.

Related: `[[focus-poc-envs]]`, `[[focus-node-db-access]]`, memory `[[aida-emdash-review-before-push]]`.
