---
name: focus-node-db-access
description: Use when you need to connect to or run SQL against the focus Postgres RDS databases (node or hd target in account 909176971711, or prod via --target prod in 577211136297) — e.g. inspecting users/content, auth break-glass, migration checks, or reseeding via bootstrap-seed.mjs. IAM auth is the preferred path.
---

# focus-poc-node DB access

The node RDS is **not public** — reach it via an SSM port-forward through a jump host, then psql as the **app** user. Password login as `focus_admin` can never work (see gotchas).

**Shareable docs (for teammates / tickets):** `~/Downloads/projects/AWS_steps_iam_db/` holds `iam-db-access-guide.md` + self-contained `.html` (6-step screenshot walkthrough: SSO portal → temp creds → run script) and `focus-envs-overview.md`/`.html` (architecture + CI/CD diagrams for both envs, SVG sources included). Rebuild the HTMLs with the `build-*.py` scripts in the same folder; the HTML pattern follows the `shareable-html-docs` skill. Added 2026-09-17: `focus-node-db-iam-guide.html` — the reference for the *script* `focus-node-db-iam.sh` (why/quick start, inline-SVG connection-flow diagram, every flag, env overrides, prereqs, DB-roles and troubleshooting tables incl. "no online SSM instance"); hand-written, no build script, no screenshots, Playwright-verified. **The md and html in this folder are not generated from each other** — `build-html.py` hard-codes the screenshot walkthrough, so the "Migrations + seed update" section appended to `iam-db-access-guide.md` on 2026-09-17 is NOT in `iam-db-access-guide.html`. Editing a `.md` here does not update its `.html`; check which of the pair you are sharing.

## Quick path (IAM — preferred since 2026-08-14)

```bash
cd ~/Downloads/projects/emdash-bench/bench
./focus-node-db-iam.sh --profile 909176971711_AWSNonProdASTechDeveloper        # node RDS, interactive
./focus-node-db-iam.sh --target hd --profile … -c "SELECT count(*) FROM users;" # HD RDS (focus-poc-nonprod-pg)
./focus-node-db-iam.sh --help                                                   # full usage incl. prerequisites
```

Legacy secret-based script (connects as `focus_app`; needed for DML *as the app user* and for a fresh caller with no `rds-db:connect` yet):
```bash
./focus-node-db.sh --profile 909176971711_AWSNonProdASTechAdmin   # Laith's preferred profile for the secret path (asked to swap SRE→Admin 2026-09-06; SRE also works)
./focus-node-db.sh --target hd -c "..."   # HD via secret is still BLOCKED (CMK: GetSecretValue allowed, kms:Decrypt denied) — use the IAM script for HD
```

The script: verifies the AWS **account** (any profile/env creds accepted — it prints the resolved identity ARN) → opens SSM tunnel on **local :5433** (reuses if up) → pulls `focus_app` creds from the `database-url` secret → `psql` over SSL → closes the tunnel on exit. Overridable env: `LOCAL_PORT`, `PGDATABASE`, `JUMP_HOST`, `RDS_EP`, `DBURL_ARN`; `--profile NAME` as first arg exports `AWS_PROFILE`.

## Prod (`--target prod`, account 577211136297)

```bash
cd ~/Downloads/projects/emdash-bench/bench && ./focus-node-db-iam.sh --profile 577211136297_AdministratorAccess --target prod -Atc "select current_user, current_database()"
```
- Port 5439, default user `focus_prod_ro` / database `focus_prod`; jump host found by tag `focus-node-prod-ssm-jump`; prints `*** PROD database ***`. `--ro prod` = the same read-only login; a mismatched `--ro`/`--target` is refused. Use `DB_USER=focus_prod_migrator` only for schema work.
- `focus_admin` is IAM-only after `roles.sql`; there's no password path on prod. The Wiley VPN can't reach the VPC, the jump host is the only way in.
- Seed/migrate on the jump host: `focus-node-seed-fast.sh --env prod` (refuses `--deliver`).
- App-connected check: `pg_stat_activity` grouped by `client_addr` for `focus_prod_app` vs the task IPs (recipe in `focus-env-db-bootstrap`).

## Dev / UAT databases on the SAME instance (since 2026-09-17, PR #490)

`focus-poc-node-nonprod-pg` now holds three databases: `focus_poc` (POC), `focus_dev`, `focus_uat`. Roles are per instance, so each env has its own: `focus_<env>_app` (password, the env's `rds/app` secret), `focus_<env>_migrator` + `focus_<env>_ro` (IAM, `rds_iam`); CONNECT only on the env's own database (revoked from PUBLIC — `focus_dev_app` → `focus_uat` fails `User does not have CONNECT privilege`). `focus_admin` (rds_superuser) reaches all three. The DEFAULT target of the IAM script IS the shared instance, so an env is just two env vars:
```bash
PGDATABASE=focus_dev DB_USER=focus_dev_migrator ./focus-node-db-iam.sh --profile 909176971711_AWSNonProdASTechAdmin ...   # Dev (uat likewise)
PGDATABASE=focus_dev ./focus-node-db-iam.sh -c "..."                     # as focus_admin on Dev's DB
PGDATABASE=focus_dev DB_USER=focus_dev_migrator ./focus-node-db-iam.sh --exec node $REPO/custom/infra/terraform/db/migrate.mjs --status
```
`RDS_PREFIX=focus-dev-node|focus-uat-node` no longer resolves (instances destroyed; snapshots `focus-<env>-node-pre-shared-20260917`). New env on the instance: `CREATE DATABASE focus_<env>` as focus_admin, then `PGDATABASE=focus_<env> ./focus-node-db-iam.sh -v env=<env> -v app_password="$APP_PW" -f $REPO/custom/infra/terraform/db/roles.sql` (roles.sql is parameterized; no `-v env` = POC names; it refuses a wrong target DB). Admin-profile `rds-db:connect` covers the new user names (verified). Gotchas hit 2026-09-17: `options` column is `name` (not `key`); redirects table is `_emdash_redirects`; `psql -c "a; b"` prints only b; seed-progress query must guard `ec_sponsors` with `to_regclass` (table appears mid-seed).

## QA read-only access — `--ro` and the `AWSNonProdASTechQA` permission set (LIVE 2026-09-24)

Permission set `AWSNonProdASTechQA` (role `AWSReservedSSO_AWSNonProdASTechQA_5bb0093a9b4904fa`, profile `909176971711_AWSNonProdASTechQA`) holds ONE inline policy and no managed policy: `rds-db:connect` on `dbuser:db-4YWQ…/*_ro` only, `ssm:StartSession` on `instance/*` restricted to the two port-forwarding documents, `TerminateSession`, `rds:DescribeDBInstances` + `ssm:DescribeInstanceInformation`, and an explicit Deny on `secretsmanager:GetSecretValue`, `kms:Decrypt`, `ssm:SendCommand`, `ssm:StartAutomationExecution`, `ecs:ExecuteCommand`. Full policy + design rationale in memory [[qa-permission-set-rds-readonly]].

**`--ro poc|dev|uat` (added to the script 2026-09-21, committed `25628a3` in emdash-bench)** sets the read-only user AND its database together, because they must agree — each `_ro` role has CONNECT only on its own database:

| `--ro` | user | database |
|---|---|---|
| `poc` | `focus_ro` | `focus_poc` |
| `dev` | `focus_dev_ro` | `focus_dev` |
| `uat` | `focus_uat_ro` | `focus_uat` |

**POC's role is `focus_ro`, NOT `focus_poc_ro`** — the irregular one, handled inside the flag. With no env argument it is inferred from `PGDATABASE`; an unrecognised value exits rather than guessing.

```bash
./focus-node-db-iam.sh --profile 909176971711_AWSNonProdASTechQA --ro poc -c "SELECT count(*) FROM users;"
```

**The trap: the script defaults to `DB_USER=focus_admin`, which QA is denied** → a bare run fails `PAM authentication failed for user "focus_admin"`. That message means "you forgot `--ro`", not a broken grant.

Refusals verified live 2026-09-24 as `focus_ro`: writes → `permission denied for table`, CREATE → `permission denied for schema public`, **DROP → `must be owner of table` (different wording — do not grep only for "permission denied")**, cross-DB → `permission denied for database`. `focus_app` fails with *password* authentication failed, not PAM, because it uses password auth and has no `rds_iam`.

### When the tunnel will not come up ("tunnel not ready after 15s", "Reusing existing tunnel" then "Connection terminated")

The log stops at `Starting session with SessionId: ...` and never prints `Port 5433 opened`: the jump host's SSM agent
cannot open the data channel. Diagnose in this order (all read-only, hand them over):
1. `aws ssm describe-instance-information --filters Key=InstanceIds,Values=i-0b2671c177b8083dd` — `ConnectionLost` means the
   agent is gone; `Online` can be STALE (it pinged once), so also run 2.
2. `aws ssm send-command ... AWS-RunShellScript` then `get-command-invocation` — `Undeliverable` = the agent takes nothing.
3. `aws ec2 get-console-output --latest | grep -iE 'out of memory|killed process'` — the real cause on 2026-09-28: the host
   was a **t4g.nano (0.5 GB)** and the account's Quick Setup "Host Management" patch **Scan** (`AWS-RunPatchBaselineAssociation`,
   daily, targets `InstanceIds: *`) ran `dnf`, which swapped the agent out; `oom_score_adj -900` protected dnf, so it never
   died and the box thrashed at 80-96% CPU. Two reboots did not help (the scan restarts after boot).
4. Also `aws ssm describe-sessions --state Active`: aborted attempts stay Active on the agent; terminate them.
Fix that worked: resize to **t4g.small** (terraform `envs/nonprod/10-foundation/main.tf`, `module "ssm_jump"`
`instance_type = "t4g.small"`, PRs #555 main / #556 poc; targeted apply `-target=module.ssm_jump`, in-place, ~4.5 min).
**Script bug:** `focus-node-db.sh` cleanup kills the `aws` process but not its `session-manager-plugin` child, so every
failed run leaves an orphan (the cause of a stale "Reusing existing tunnel"). Before retrying:
`pkill -f 'session-manager-plugin.*i-0b2671c177b8083dd'`. A stuck plugin ignores Ctrl+C: kill it from another terminal.
Reliable pattern for long loads: open the port-forward yourself in terminal 1 (`aws ssm start-session ...
AWS-StartPortForwardingSessionToRemoteHost`), wait for "Waiting for connections", then run the script in terminal 2
(it prints "Reusing existing tunnel"). Idle SSM sessions close after ~20 minutes.

### GUI clients (pgAdmin etc.) — hold the tunnel open yourself

The script closes its tunnel on exit, so a GUI needs the raw tunnel running separately, then connects to `127.0.0.1:5433` with the token as the password. Verified end-to-end 2026-09-24:

```bash
printf '{"host":["<rds-endpoint>"],"portNumber":["5432"],"localPortNumber":["5433"]}' > /tmp/t.json
aws ssm start-session --target i-0b2671c177b8083dd \
  --document-name AWS-StartPortForwardingSessionToRemoteHost --parameters file:///tmp/t.json
# second terminal: the password
aws rds generate-db-auth-token --hostname <rds-endpoint> --port 5432 --username focus_ro
```

`--parameters file://<json>` works and is the portable form (avoids Windows command-line JSON quoting). pgAdmin's default `sslmode=prefer` connects fine — no SSL tab changes needed. **A client's built-in "AWS IAM authentication" option will fail through the tunnel**: it signs the token for the host you typed (localhost) but the token must be signed for the REAL RDS endpoint. Paste manually.
**UNVERIFIED (creds expired mid-test 2026-09-27):** that ONE tunnel carries three SIMULTANEOUS connections (pgAdmin with three servers open). Sequential reuse across all three DBs IS verified — the script printed "Reusing existing tunnel". Prove the concurrent case before trusting the doc line that asserts it.

### Windows

`focus-node-db-iam.sh` **fails in Git Bash**: its tunnel probe is `(exec 3<>/dev/tcp/…)` and Git for Windows builds bash without net-redirections. Options: WSL2 (bash script works unchanged; install aws/psql/session-manager-plugin INSIDE WSL and use WSL's `~/.aws/credentials`), or `focus-node-db-iam.ps1` (PowerShell port, `-Ro`/`-AwsProfile`/`-Query`, probes with `System.Net.Sockets.TcpClient`). **The .ps1 is UNTESTED and uncommitted** — pwsh would not start locally. Two Windows bugs already fixed by inspection: `$ErrorActionPreference='Stop'` + native stderr under `2>&1` can raise `NativeCommandError` on a *successful* run, and killing `aws.exe` does not kill its `session-manager-plugin.exe` child, which keeps the port bound.

QA guides (md + self-contained html + `build-*.py`) live in `~/Downloads/projects/AWS_steps_iam_db/`: `focus-qa-db-access-guide` (Linux/bash), `focus-qa-pgadmin-guide` (Windows/pgAdmin), `focus-qa-windows-cli-guide` (Windows/PowerShell).

## IAM-token variant (no Secrets Manager) — `focus-node-db-iam.sh`

`./focus-node-db-iam.sh [--profile NAME] [psql args]` — same tunnel, but auths with `aws rds generate-db-auth-token` as `focus_admin` (default; `DB_USER=` to override) and **discovers** the RDS endpoint/jump host from the AWS APIs instead of hardcoding. Benefits: no secretsmanager access needed, 15-min per-user-attributable revocable tokens. Token subtlety: it is signed for the **real endpoint host:port** even though psql connects to `127.0.0.1:5433`.

**STATUS 2026-08-24: PROFILE SPLIT — use the Developer profile for IAM DB auth.** The SRE profile's `rds-db:connect` regressed when its inline policy was replaced (it carries a literal unsubstituted `arn:aws:rds-db:<region>:<account-id>:dbuser:…` template ARN → PAM failure); Developer works, and the secret path (`focus-node-db.sh`) now also works on SRE since `kms:Decrypt` was granted. Earlier status 2026-08-14: WORKING on BOTH DBs, both profiles — `rds-db:connect` grant landed (policy: `dbuser:*/*` + `iam:SimulatePrincipalPolicy` on SSO roles, both verified). Node DB connects as `focus_admin` via Developer AND SRE profiles. **HD DB too**: `./focus-node-db-iam.sh --target hd --profile … -c "..."` — `focus_admin` exists there with `rds_iam`, so IAM auth bypasses the CMK-blocked secret (HD app dbname verified = `focus_poc`, same as node; HD uses local :5434). Prefer IAM over the secret path.

`--target node|hd` added to the IAM script 2026-08-14 (mirrors focus-node-db.sh); `--profile`/`--target` accepted in either order but must precede psql args. Env (`RDS_PREFIX`, `LOCAL_PORT`, …) still wins over the target mapping. For teammates consider a least-privilege `focus_ops` role (`LOGIN` + `rds_iam` + `GRANT focus_app`) instead of `focus_admin` (which is `rds_superuser`). If a connect fails `PAM authentication failed`, the caller's permission set lacks `rds-db:connect` on `arn:aws:rds-db:us-east-1:909176971711:dbuser:db-4YWQVCVU7CDV6M4P54IICOGSPA/<db_user>` (the script prints this triage hint).

## Run a non-psql command over the same tunnel (`--exec`)

`./focus-node-db.sh --exec CMD …` runs `CMD` with the tunnel up and the libpq `PG*` env already exported as `focus_app`: `PGHOST=127.0.0.1 PGPORT=5433 PGUSER=focus_app PGPASSWORD=<from secret> PGDATABASE=focus_poc PGSSLMODE=require`. Used to run node scripts that read `PG*` (e.g. `bootstrap-seed.mjs`) against RDS without a separate tunnel.

`focus-node-db-iam.sh --exec` works the same way with an IAM token (`focus_admin` by default). Verified 2026-09-29 with the Developer profile: the Focus 1.0 import tool's `focus-import dry-run` and `load` both passed through it on `focus_poc`.

## Reseed via bootstrap-seed.mjs (verified 2026-08 on branch poc-sync-postgres-node)

**Use branch `main`** (it was `poc` from 2026-08-31 until 2026-09-28; superseded 2026-09-28: aida-emdash now merges to main, see memory `aida-emdash-main-is-base`). PR #314 (AIDAFOCUS-262, merged to poc 2026-08-24, on main via #545) gave the real `bootstrap-seed.mjs` a native `--update` flag (line ~60: `process.argv.includes("--update")`), plus `bootstrap-seed.md` docs. **The working repo (since 2026-09-01) is `~/Downloads/projects/aida-emdash-poc`** (it was kept on branch `poc` then; Laith's choice; it's also the fast script's default REPO — the old `aida-emdash-psn-tf` clone still exists but is retired); the old trap (`poc-sync-postgres-node` hardcoded skip and silently ignored `--update`) only matters if someone checks that stale branch out again — verify with `grep -n '"--update"' custom/sites/focus/db/bootstrap-seed.mjs` before an update run. Update-runs verified as `focus_migrator`: 2026-08-24 (fields created 5/updated 107) and 2026-08-31 on poc (collections updated 6, fields updated 112, terms 1310, content updated 91 — sponsors force-re-published, the accepted cost; ~4 min over the tunnel, no progress output until the final JSON — check liveness via `pg_stat_activity WHERE usename='focus_migrator'`; `SEED_QUERY_LOG=1` at launch for per-query trace). Update-mode is the ONLY way to deliver a NEW field on an EXISTING collection — skip-mode never checks fields individually (see `focus-seed-reapply`).

**Non-fatal error during content writes** (`relation "_emdash_media_usage_index_status" does not exist`, 42P01): RESOLVED 2026-08-24 — core migrations 044–050 applied to node via migrate.mjs; node DB now at 51 applied / 0 pending. If it reappears, the schema is behind the build again: run the migrate path below.

## FAST DB ops: focus-node-seed-fast.sh (built + verified 2026-09-01)

### PRE-SEED GATE — the branch of `$REPO` decides what lands in the DB

`REPO` defaults to `~/Downloads/projects/aida-emdash-poc` (`focus-node-seed-fast.sh:62`),
the one clone that is always parked on whatever ticket branch Laith is mid-flight on. The
script ships `$REPO/custom/sites/focus/.emdash/seed.json` (line 166) to the jump host, so
that file — not `origin/main` — is what `--update` writes. Nothing in the script output
names the branch or SHA; a wrong-branch run reports `exit=0` / `status: Success`.

**Burned 2026-09-24:** a `--update` run from `AIDAFOCUS-377` (tip 2026-09-02) rewrote poc
with a three-week-old content model and re-applied the sponsor-logo key typo that PR #518
had already fixed on `poc` the day before. Laith: "you should make sure it is the correct
branch, or at least ask me — as far as I know the branch should be poc when we reseed."
(That was the base then; since 2026-09-28 the reseed source branch is `main`.)

Run before every seed/migrate, and state the branch back to him:

```bash
git -C ~/Downloads/projects/aida-emdash-bastion branch --show-current   # expect: main (was poc until 2026-09-28)
cd ~/Downloads/projects/aida-emdash-bastion
git fetch origin '+refs/heads/main:refs/remotes/origin/main' && git pull
pnpm install --frozen-lockfile && pnpm --filter emdash build && pnpm --filter focus seed:merge
ls -l custom/sites/focus/.emdash/seed.json    # mtime MUST be from this build
```
Not `main` -> stop and ask. Then pass `REPO=~/Downloads/projects/aida-emdash-bastion` on
**every** invocation (inline, not exported — the blocks get pasted alone later).

`seed:merge` can silently leave a weeks-old `seed.json` in place, so check the mtime and,
when chasing a specific defect, grep the merged artifact for it rather than the source
file. Reading repo state to ANSWER a question has the same rule: check `origin/main`, not
the open checkout, before telling him a repo file needs changing (2026-09-24: proposed a
PR for a fix that was already merged as #518).


**Env targeting (verified by reading the script 2026-09-24):** honors `DB_USER` (default `focus_migrator`), `PGDATABASE` (default `focus_poc`), `RDS_PREFIX` (default `focus-poc-node`), `RDS_EP/RDS_PORT`, `JUMP_HOST`, `REPO`, `PAYLOAD_BUCKET/PREFIX`. Dev/UAT (same instance) = `PGDATABASE=focus_dev DB_USER=focus_dev_migrator ./focus-node-seed-fast.sh ...` (uat likewise). Confirm the target from the remote log line `[migrate] target <user>@<host>/<db>`. HD would need `RDS_PREFIX=focus-poc-nonprod DB_USER=focus_admin` — UNTESTED (jump-host→HD-RDS SG reachability and payload-bucket perms unverified). Extra args pass through, so `--migrate-site --phase pre-seed` works (verified `--phase` still in migrate-site.mjs). The script CANNOT create a database or run roles.sql — from-scratch step 1 stays on the tunnel path (`focus-env-db-bootstrap`), then fresh-DB order: `--migrate` → `--migrate-site --phase pre-seed` → seed no-flags (skip creates all on empty DB) → `--migrate-site --phase post-seed`.

**POC state 2026-09-24 (seed run from branch `AIDAFOCUS-377` in aida-emdash-poc — NOT `poc`; deliberate for the content-groups delivery):** core 52 applied / 0 pending; site 27 applied / 0 pending (tracker rows now span three naming generations; branch ships 8 files 0001_sso…0008_language_taxonomy_single_select); seed `--update`: collections created 1 (`content_groups`) / updated 5, fields created 50 / updated 67, terms 1316, content created 8 / updated 123. Seed run 11 s on-host. Check which branch a checkout is on before seeding an env from it.

`./focus-node-seed-fast.sh [--profile NAME] [--dry-run|--update]` (same bench dir) runs bootstrap-seed **ON the jump host inside the VPC** instead of through the tunnel — seconds instead of ~4 min (the tunnel adds ~80ms/query × thousands of sequential queries). Also wraps the migrate scripts: `--migrate [--status]` (core migrate.mjs) and `--migrate-site [--status]` (migrate-site.mjs; ships `migrations-pg/*.sql` in the payload) — each ~1s, verified 2026-09-01. Fast runbook after a `main` pull+build: `--migrate --status` → `--migrate-site --status` → apply any pending → `--update`. Or one shot: **`--env poc|dev|uat --deliver [--build] [--yes]`** (REWRITTEN 2026-10-09 in the bench copy — the old migrate→migrate-site→seed order failed on POC 2026-09-18). New order: repo gate (REPO HEAD must equal origin/main, seed.json mtime ≥ HEAD commit time; `--allow-branch` overrides) → core migrate → `migrate-site --phase pre-seed` → seed dry-run → `--update` → `--phase post-seed` → re-apply already-applied post-seed files whose header says "re-apply this file by hand" (0022 term descriptions, which `--update` wipes) via `focus-node-db-iam.sh -1 -f` → final `migrate-site --status` must be pending 0. `--build` = `checkout --detach origin/main` + install/build/seed:merge, ONLY in a detached clean worktree (use `REPO=~/Downloads/projects/aida-emdash-main-seed`; refuses a named branch). FIRST LIVE RUN 2026-10-09 on Dev PASSED (core 0 pending, site 0 pending so both phases skipped, --update 15 s, 0022 re-applied `UPDATE 30`, final pending 0). UAT same day via the step blocks; 30 descriptions verified. Earlier history: the 2026-09-15 version — orchestrates that whole sequence by re-invoking the script per stage: each migrate `--status` auto-skips apply on `pending: 0` (greps the runner's own summary line), prompts before each apply and before `--update` (`--yes` = unattended), always dry-runs before update, ends with a converge dry-run. Stops on first stage failure. **GitHub Actions wrapper drafted 2026-09-15 (uncommitted in `aida-emdash-poc`):** `.github/workflows/db-migrate-seed-focus-node.yml` — workflow_dispatch (`status` = no-writes report, `deliver` = full pipeline via the vendored script copy at `custom/infra/scripts/focus-node-seed-fast.sh`), OIDC role `…-gha-db-ops` (new tf: `30-node-app/ci-github-db-ops.tf`), gated by the `focus-node-deploy` environment, branch-guarded to `poc`. Needs: tf apply (Laith), PR+merge to `poc`, then dispatch from `poc`. **Its `deliver` choice is one call to `--deliver --yes` using the VENDORED repo copy, which still has the old broken order (only the bench copy was fixed 2026-10-09) — sync the vendored copy before anyone dispatches `deliver`. The `status` choice is three separate `--status`/`--dry-run` calls and writes nothing, so it is safe to dispatch as-is.** Still uncommitted as of 2026-09-27 (the three files sit untracked in a checkout on branch `AIDAFOCUS-377`, not `poc`). Keep the bench and repo copies of the script in sync. Pipeline: esbuild-bundles bootstrap-seed+emdash+kysely+pg into one .mjs (transforms the script's dynamic `createRequire` block to static imports — HARD-FAILS if upstream changed that block; externals: `pg-native`, `cloudflare:sockets`, `virtual:emdash/*`, `astro:*`; `createRequire` banner for CJS interop), tars it with seed.json + a fresh 15-min IAM token for `focus_migrator` signed for the REAL endpoint (host connects direct, no tunnel), ships via private S3 `focus-poc-node-nonprod-media-a37eab19/ops-tmp/` + 15-min presigned curl (jump-host role can't read the bucket; it CAN reach the internet), runs via `ssm send-command` as root (auto-installs `nodejs20` via dnf if missing — done once 2026-09-01), polls and prints the log tail; full log stays at `/tmp/seed-fast-<ts>/run.log` on the host; S3 object deleted on exit. Extra IAM needed: `ssm:SendCommand`/`GetCommandInvocation`, S3 Put/Get/Delete on the prefix (all verified present on Developer). Same local prereqs (built repo + seed.json). The tunnel path (`--exec node bootstrap-seed.mjs`) remains the fallback.

**Fixed 2026-09-07 — `--migrate` esbuild "Could not resolve kysely/pg":** entries outside `custom/sites/focus` (core `migrate.mjs` lives in `custom/infra/terraform/db/`) can't resolve bare `kysely`/`pg` via the node_modules walk (only `@aws-sdk/*` is publicly hoisted). `run_esbuild` now exports `NODE_PATH=$REPO/node_modules/.pnpm/node_modules` (pnpm's hidden hoist, holds every workspace dep). Also: the script honors `REPO=` — needed when the base branch (`main`; `poc` before 2026-09-28) is checked out in a different worktree (e.g. `aida-emdash-bastion` while `aida-emdash-poc` sits on a feature branch; a branch can only be checked out in ONE worktree, so `git checkout main` fails with "already checked out at ..." — build in whichever worktree holds `main` and pass `REPO=` to the script).

## Renumbered site migrations on `poc` (PR #482, 2026-09-17) — existing-DB trap

`_focus_site_migrations` is keyed by FILENAME. #482 renamed 7 files (0006_fts_search→0003, 0007_astro_sessions→0004, 0008_language_taxonomy_single_select→0005, 0010_editorial_feature_fts→0006, 0013_downloadable_fts→0007, 0014_native_webinar_fts→0008, 0016_collection_fts→0009) and deleted 8 realign migrations (incl. 0018_podcast_legacy_fields, never applied on POC). On POC (17 old names recorded) migrate-site therefore reports `pending: 7`. All 7 are re-runnable (IF NOT EXISTS / OR REPLACE / guarded UPDATE) and re-running the FTS ones is WANTED (#436/#447/#467 edited 0006_fts_search in place after POC applied it). But `0003_fts_search.sql` now references seed-only columns (`podcast_description` from #467) → fails `column does not exist` unless `bootstrap-seed --update` ran first. **Order on an existing DB: seed --update (optionally --no-content) → migrate-site (no --phase).** DONE on POC 2026-09-18 03:01–03:03 via the fast script: `--update --no-content` → collections updated 21, fields created 17 / updated 473, redirects created 1 / updated 19, content 0 (6 s); then `--migrate-site` applied all 7 renamed files (15 s) → `applied: 24, pending: 0`. Old tracker rows stay (harmless duplicates, 24 rows = 17 old + 7 new). NOTE: bootstrap-seed `--dry-run` is a VALIDATION only (prints 'seed valid, schema present'), it does NOT diff seed vs DB — do not describe it as a converge check. POC never got the deleted podcast/infographic/collection legacy-field realigns → legacy columns remain on ec_podcasts etc.; applySeed never deletes fields.

## Core migrations via migrate.mjs (verified 2026-08-24)

`custom/infra/terraform/db/migrate.mjs` reuses emdash's own `runMigrations` (records in `_emdash_migrations`), reads `PG*` env — so it runs over the same `--exec` tunnel. Requires built workspace + `focus_migrator`:
```bash
DB_USER=focus_migrator ./focus-node-db-iam.sh --profile 909176971711_AWSNonProdASTechDeveloper \
  --exec node "$REPO/custom/infra/terraform/db/migrate.mjs" --status   # report only; review pending list first
# drop --status to apply; verify after: --status shows pending: 0
```
It applies ALL pending core migrations of the checked-out branch — review the list (grep each for createTable/createIndex vs data backfills) before applying. Site migrations are a separate runner, same invocation shape (run 2026-09-15 via the tunnel):
```bash
DB_USER=focus_migrator ./focus-node-db-iam.sh --profile 909176971711_AWSNonProdASTechDeveloper \
  --exec node "$REPO/custom/sites/focus/db/migrate-site.mjs" --status   # then apply (drop --status), then --status again
```

**Ordered runbook for a schema-change + seed delivery on an EXISTING DB** (what "run the migrations and update-seed" means; Laith executes; full procedure in skill `focus-db-deliver`): pull+build `main` → core `migrate.mjs --status`/apply → `migrate-site --phase pre-seed` → `bootstrap-seed.mjs --dry-run` → `--update` (only update-mode creates new fields on existing collections; force-republishes the 91 sponsors; resets seeded term descriptions) → `migrate-site --phase post-seed` → re-apply already-applied post-seed data files (0022) → `migrate-site --status` pending 0. Fast path: `focus-node-seed-fast.sh --env <env> --deliver` does exactly this (above). Migrations must precede the seed — its preflight throws without `_emdash_collections`, and a behind schema caused the `42P01` of 2026-08.

**Profile scope gotcha (2026-08-24):** `DB_USER=focus_migrator` works via the **Developer** profile but PAM-fails via **SRE** — the SRE permission set's `rds-db:connect` evidently doesn't cover `dbuser/focus_migrator` (only verified for `focus_admin`). Use Developer for migrator work, or extend the SRE policy.

Manual reseed WITHOUT enabling `EMDASH_SEED_REAPPLY_ENABLED`. Prep in a checkout on `main` (e.g. `~/Downloads/projects/aida-emdash-poc` only if `git branch --show-current` says main — see the pre-seed gate above; Node ≥22): `pnpm install` → `pnpm --filter emdash build` → `pnpm --filter focus seed:merge` (writes `custom/sites/focus/.emdash/seed.json`). Then:
```bash
REPO=~/Downloads/projects/aida-emdash-poc
./focus-node-db.sh --exec node "$REPO/custom/sites/focus/db/bootstrap-seed.mjs" --dry-run   # validate, no writes
./focus-node-db.sh --exec node "$REPO/custom/sites/focus/db/bootstrap-seed.mjs"             # apply (SEED_QUERY_LOG=1 to trace)
```

Facts about the script (read + ran twice):
- Applies the built `.emdash/seed.json` via emdash `applySeed` — `onConflict:"skip"` (idempotent), `includeContent:true`, `skipMediaDownload:true` unless `SEED_INCLUDE_MEDIA=1`. Resolves `emdash`/`kysely`/`pg` through the built workspace (needs `packages/core/dist`).
- Connection = `PG*` env vars only. **Does NOT migrate** — preflight `SELECT to_regclass('public._emdash_collections')` throws if the schema is absent. No admin user, no setup-complete.
- Seed payload = **6 collection schemas + 5 taxonomies + 91 sponsor rows** only (no article content). Article-content volume comes from `db/seeds/*_dummy_pg.sql` (DML, runs as `focus_app`).
- On the already-seeded node DB it is a **no-op**: 6 collections / 107 fields / 91 sponsors all skipped, 0 created. Ran fine **as `focus_app`** — no DDL wall, because objects exist so it only issues `SELECT`+skip, never `CREATE`/`ALTER`. A fresh DB would need `focus_migrator` (rds_iam, no password) after migrations.
- **`onConflict:"skip"` only creates MISSING rows — it never UPDATES existing/drifted ones.** Verified drift: `taxonomies.json` assigns `gated_content` to 4 collections (`key_opinion, webinars, infographics, podcasts`) but `_emdash_taxonomy_defs.collections` in the DB has only 2 (`key_opinion, webinars`); re-running the seed does NOT reconcile it (created:0). All other focus defs matched (specialty_methodology 40, subject 13, wol_taxonomy 904, gated_content 2, sponsor 91 terms). To fix drift: `onConflict:"update"` (script hardcodes skip) or manual `UPDATE _emdash_taxonomy_defs …` as focus_app (DML). The DB also carries emdash defaults `category`/`tag` (→`["posts"]`) not in the focus seed.
- Per-collection `Failed to enable search … No Postgres search backend registered` errors are **non-fatal**: the standalone script doesn't register `@wiley/emdash-pg-search` (only the app runtime does, via `custom/packages/pg-search/src/middleware.ts`). The script still exits 0 with the `done` JSON. FTS tables already exist from migration `0006_fts_search.sql`. See memory [[focus-node-bootstrap-seed]].

## Run the DEPLOYED app locally over the tunnel (debug recipe, proved out 2026-08-31)

To debug the exact deployed build with full instrumentation (used to crack the search-404/1019 bug — see memory `focus-search-404-editor-1019`):
1. `docker create` + `docker cp` the app out of the ECR image (`focus-poc-node-nonprod:dev` — what POC runs since 2026-10-01; `:poc-node-latest` is frozen) — the JS is arch-independent even though the image is ARM64 (**never `docker run` it on x86 — exec format error**). Copy `dist/` into the repo checkout (e.g. `custom/sites/focus/dist-extract/`) so externals (`react`, …) resolve from the workspace `node_modules`.
2. Patch the extracted `dist` freely (e.g. add logging inside swallowed catches) — it's a throwaway copy.
3. Launch via `./focus-node-db.sh --exec <script>` where the script builds `DATABASE_URL` from the exported `PG*` env (URL-encode the password; `?sslmode=no-verify`) and runs `node dist-extract/server/entry.mjs` with `HOST=127.0.0.1 PORT=8787`.
4. **Must also set the task-def env** (`S3_BUCKET`, `S3_REGION`, `S3_ENDPOINT`, `EMDASH_SITE_URL`, `EMDASH_ALLOWED_ORIGINS`, `EMDASH_SEED_REAPPLY_ENABLED=false` — read them with `aws ecs describe-task-definition`): without S3 config the runtime init fails non-fatally and authenticated code paths silently degrade, masking bugs.
5. Send requests with the right `Host:` header (multi-site routing). Sessions can be planted directly in `astro_sessions` (devalue format, e.g. `[["Map",1,2],"user",{"data":3,"expires":-1},{"id":4},"<user-ulid>"]`) — cookie `astro-session=<row id>`. Clean up planted rows after.
Caveats: the local instance runs the in-process 60s scheduler against the shared DB (harmless duplicate of prod's) and boot-applies any pending migrations of the extracted build (none, since it IS the deployed build). ECS Exec is disabled on the service — this recipe replaces it.

## Field definitions drift between local and poc, and a dry run will not catch it

2026-09-24: a content load that passed its dry run crashed mid-write with `invalid input syntax for type json`,
`Token "TESCAN" is invalid`. `partners` is a TEXT column locally and a JSON column on poc, so the same seed is valid
against one and not the other. The dry run validates the seed and the taxonomy terms; it never attempts a write, so
column types are invisible to it. Three collections had already been written when it died — a half-applied load.

Fix now in `load-seed.mjs`: read the target's own `_emdash_fields` before writing and reshape values that do not fit
(comma-joined string into an array for a list-shaped JSON field, JSON-encode any other string). Check the target when
a load fails this way:

```bash
./focus-node-db-iam.sh --profile 909176971711_AWSNonProdASTechDeveloper -c \
  "select c.slug, f.slug, f.type, f.column_type from _emdash_fields f
     join _emdash_collections c on c.id=f.collection_id where f.column_type ilike '%json%' order by 1,2"
```

**Serialisation trap:** passing a JS array straight to node-postgres produces a Postgres ARRAY literal
(`{"TESCAN"}`), which a json column rejects. It only works through emdash, whose `serializeValue` JSON-stringifies
objects and arrays first. Test the real path, not the shape you assume.

## Which script for which job (settled 2026-09-22, by a failure mode not a preference)

Both open the same SSM tunnel; they differ in who logs in and where the password comes from.

| Job | Script | Why |
|---|---|---|
| Short reads: counts, field checks, term exports | `focus-node-db-iam.sh` | 15-min token is plenty, needs no Secrets Manager access, attributable per caller, discovers endpoint/jump host |
| Long writes: content import, DML passes, applying SQL | `focus-node-db.sh` | the secret password does not expire mid-run, and it connects as `focus_app`, the role that should own content |

**The failure the IAM script produces on a long run.** An IAM token lasts 15 minutes and is only checked at connect time, so
an interactive session survives. A node loader does not: `load-seed.mjs` holds a `pg.Pool` with `max: 4` and pg's default
10-second idle timeout, and media staging spends minutes writing files without issuing a query. The pool empties, the next
reconnect presents a token minted long ago, and the run dies with an authentication error AFTER writing some entries.
Anything longer than ~15 minutes that reconnects belongs on the secret path.

Using IAM *as* the app role is not possible: `focus_app` has no `rds_iam` on purpose, and granting it would force IAM-only
auth and break the running site's password login.

## Targeting Dev or UAT (they share POC's instance since #490)

One instance, `focus-poc-node-nonprod-pg`, three databases, per-env roles. Only three things change, and both scripts take
them as env overrides (`focus-node-db.sh`: `RDS_EP`, `DBURL_ARN`, `PGDATABASE`, `LOCAL_PORT`; the IAM script: `RDS_PREFIX`,
`PGDATABASE`, `LOCAL_PORT`).

| | POC | Dev | UAT |
|---|---|---|---|
| Database | `focus_poc` | `focus_dev` | `focus_uat` |
| Roles | `focus_app` / `focus_migrator` | `focus_dev_*` | `focus_uat_*` |
| Media bucket | `focus-poc-node-nonprod-media-a37eab19` | `focus-dev-node-nonprod-media-939fd5ba` | `focus-uat-node-nonprod-media-a0d7c561` |
| Hosts | `medicine-/sciences-focus-poc` | `-dev` | `-uat` |
| Secret | `focus-poc-node-nonprod/app/database-url` | `focus-dev-node-nonprod/app/database-url` | `focus-uat-node-nonprod/app/database-url` |

```bash
DBURL_ARN=<that env's secret ARN> PGDATABASE=focus_dev LOCAL_PORT=5437 \
  ./focus-node-db.sh --profile 909176971711_AWSNonProdASTechAdmin --exec <command>
```

The ARN suffix is random and the secret VALUES were re-pointed during the move to the shared instance, so resolve it rather
than pasting one: `aws secretsmanager list-secrets --query "SecretList[?contains(Name,'app/database-url')].[Name,ARN]"`.
The script prints the identity and resolved database before running anything — read that line, it is the cheap guard against
writing into the wrong environment. Dev and UAT deliberately hold only schema, taxonomies and 91 sponsors.

## Facts

| thing | value |
|---|---|
| account | `909176971711` (RDS + secrets live here) — scripts enforce account, not profile |
| profiles | `…_AWSNonProdASTechDeveloper`, `…_AWSNonProdASTechSRE`, and `…_AWSNonProdASTechAdmin` (all pasted temp creds, ~1h — they expire mid-task, ask the user to re-paste; no `aws sso login` config). SRE verified able to read the node secret. **Admin verified 2026-08-31:** IAM DB auth as `focus_admin` works, secret path works, plus ECR pull, ECS/logs describe, `logs tail`. |
| RDS | `focus-poc-node-nonprod-pg…rds.amazonaws.com:5432` (PG17), DbiResourceId `db-4YWQVCVU7CDV6M4P54IICOGSPA`; databases `focus_poc` (POC), `focus_dev`, `focus_uat` (since 2026-09-17) |
| jump host | `i-0b2671c177b8083dd` (since 2026-09-03 scheduled-restart replacement, PR #392; auto-discovered by the IAM script). Self-heals: agent restarts daily 01:00 UTC, instance reboots Sun 01:30 UTC via EventBridge Scheduler — a tunnel dropped at those times is the schedule, not a bug. Mid-day `ConnectionLost` anyway → `aws ec2 reboot-instances` |
| app login | `focus_app`, creds from secret `focus-poc-node-nonprod/app/database-url` |
| per-env roles (2026-09-17) | `focus_dev_app|_migrator|_ro`, `focus_uat_app|_migrator|_ro` — same grant shape as POC's, CONNECT only on their own DB |
| role grants (verified 2026-08-13) | `focus_admin` → `focus_migrator`, `rds_superuser` (⇒ transitively `rds_iam`); `focus_migrator` → `rds_iam` direct; `focus_app` → no `rds_iam` |

## Gotchas (each one bit us — see also DB-CONNECT-node.md)

- **Wrong AWS account + `> file` = silent failure.** `focus-node-db.sh` prints `ERROR: current AWS account is '045369966266', expected 909176971711` to STDOUT, so with `-f q.sql > out.psv && wc -l out.psv` Laith saw nothing (the `&&` stopped). Hand over with `AWS_PROFILE=909176971711_AWSNonProdASTechAdmin` inline and `;` before `wc -l`; a 3-line file = the error, read it.

- **Expired/wrong creds.** Pasted temp creds last ~1h; scripts now print the real STS error (e.g. `ExpiredToken`) and the identity ARN on success. Any profile for the account works. Also: `AWS_PROFILE=x cmd $(aws …)` does NOT apply the profile inside the `$(…)` substitution — export it instead.
- **Local port 5432 is a local Postgres** — the tunnel must use `localPortNumber 5433`, else psql hits the wrong DB (`password authentication failed for focus_admin`).
- **`focus_admin` PAM explained (verified 2026-08-13):** it inherits `rds_iam` *transitively* via `focus_migrator`, so RDS routes it through PAM — that's why its **password** login always fails `PAM authentication failed`, and why **IAM tokens** fail too *until the caller has `rds-db:connect`*. It is not a dead end; it's a missing AWS grant. For password/secret work use `focus_app`.
- **Never `GRANT rds_iam TO focus_app`** — membership forces IAM-only auth and would break the ECS task's password login (site down).
- **SSL is mandatory** — without `sslmode=require`: `pg_hba.conf rejects … no encryption`.
- **DML only as `focus_app`, never DDL** (project rule). SELECT/INSERT/UPDATE/DELETE fine; schema changes not.
- **terraform apply is blocked** for the dev SSO role (`kms:Decrypt` denied on the tfstate key) — but the **SRE profile CAN plan+apply** (verified 2026-09-01: Laith applied `30-node-app` AIDAFOCUS-360 with SRE). For ad-hoc task-def tweaks without terraform, console edit preserves ARM64 `runtimePlatform`.
- **NEVER execute `terraform plan`/`apply` yourself (Laith's explicit rule, 2026-09-01)** — he runs terraform in his own terminal; provide the exact commands/steps only, and interpret plan output he pastes back.

Related: `focus-env-db-bootstrap` (create/rebuild/move an env database on the shared instance — full procedure + verification queries), `focus-poc-envs` (architecture/bindings/CI-CD of both envs), `focus-node-passkey-recovery` (uses this connection), `focus-seed-reapply` (API-side reseed + env gate map), `focus-bench-load-test` (load/perf testing the same env); memory `[[aws-access-tickets-2026-08]]` (pending grants that unblock the IAM path).
