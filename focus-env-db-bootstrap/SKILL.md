---
name: focus-env-db-bootstrap
description: Use when creating, rebuilding or moving a focus environment's Postgres database on the shared nonprod RDS instance (focus-poc-node-nonprod-pg) or preparing/checking the separate prod instance (focus-node-prod-pg, account 577211136297) — new env (dev/uat/next), fresh rebuild of an env DB, or switching an ECS env to a different database — including CREATE DATABASE, parameterized roles.sql, the four bootstrap commands, the terraform switch/roll, the setup wizard and the verification queries. Laith runs every command; you hand them over and read the pasted output.
---

# Bootstrap a focus environment database on the shared instance

## A NEW, SEPARATE instance (prod) — differences that bite

Prod has its own RDS instance, not a 4th database here. The runbook is `prepare-prod.md` (see "Prod is DONE" below); `prod-db-prepare.md` is the superseded draft.

- **`focus_admin`'s password is a ONE-SHOT on a fresh instance.** `roles.sql` ends with `GRANT <migrator> TO CURRENT_USER` and the migrator holds `rds_iam` → from that moment `focus_admin` is PAM/IAM-only and its password never works again (the state POC/shared are in). So `CREATE DATABASE` + `roles.sql` must run in ONE master-password tunnel session, before anything else. Precedent: `bringup-dev-uat.md` Phase C.1.
- **New instance = new DbiResourceId** → `rds-db:connect` must cover it (SSO sets are expected `dbuser:*/*`). Verify with a trivial `select current_user` BEFORE the migrate/seed stages, or every stage PAM-fails at the door.
- **Use the prod switches, not env overrides:** `focus-node-db-iam.sh --target prod` and `focus-node-seed-fast.sh --env prod` set account, RDS prefix, jump-host tag, database, user and (fast script) the prod media bucket, and refuse nonprod values. Without them the fast script defaults to POC's bucket and the first online SSM instance. (Manual pinning still works: the IAM script skips discovery only when `RDS_EP` AND `DBI_ID` are both set.)
- **`environment = "prod"` in the `rds-postgres` module flips a real profile** (`modules/rds-postgres/main.tf`): `multi_az`, `backup_retention_period` 14 vs 1, `deletion_protection`, `skip_final_snapshot=false` + `<base>-pg-final`, `apply_immediately=false`, KMS window 30d, PI on by default. Other modules keyed on `is_prod`: `s3-media` (`force_destroy`), `db-app-credential` + env stacks (secret `recovery_window_in_days` 30 vs 0), `30-node-app` ECR `force_delete`, `ecs-app`. Instance name = `${name_prefix}-${environment}-pg`.
- **`--no-content` kills sponsors too** (`bootstrap-seed.mjs:69` → `includeContent`): the 91 sponsors are content rows (`ec_sponsors`), not taxonomy. "Schema+taxonomy only" and "sponsors but no samples" are NOT the same flag.
- Prod port convention 5439 (5432 local pg, 5433 shared, 5434 HD, 5435/5437 dev/uat). **Never point `rebuild-dev-uat.md` at `focus_prod`** — it DROPs the database.

**Prod is DONE and the runbook is proven end to end: `~/Downloads/projects/focus-multi-env-plan/prepare-prod.md` (+ `.html`, built by `build-html.py`).** Steps: 0 check, 1 build prod's commit, 2 scale ECS to 0, 3 `roles.sql` (master password, one shot, through `focus-node-db-iam.sh --target prod --exec bash -c 'PGPASSWORD="$MASTER_PW" psql …'`, so no second terminal), 4 IAM logins, 5 the fast stages, 6 verify, 7 scale back to 4, 8 setup wizard.
- Access is the SSM jump host `focus-node-prod-ssm-jump` (`i-09e84afc7207325b6`, PR #662 / AISVC-3061). The Wiley VPN doesn't route `10.193.8.0/22`. `focus-node-db-iam.sh --target prod` (port 5439, default user `focus_prod_ro`, jump host by tag) and `focus-node-seed-fast.sh --env prod` (prod account, RDS, jump tag, bucket `focus-node-prod-media-accfbefe` found by name; refuses nonprod values, and `--deliver` unless `--no-seed` — `--deliver --no-seed --build` = migrations only, the way to bring prod up to a new image) both work on prod. The jump host gets `dnf` and the presigned payload through the VPC's S3 gateway endpoint.
- Build commit: prod's task-definition digest, then its ECR tags. **Read the ECR tags with the NONPROD profile** (`909176971711_AWSNonProdASTechAdmin`): the prod SSO role gets `AccessDeniedException … no resource-based policy allows the ecr:DescribeImages action` on `focus-poc-node-nonprod`. (An earlier note said prod could read them; that came from the runbook's silent nonprod fallback.) First run: `b17dc8fb` / `focus-v0.1.8`, which gave 54 core + **21** site migrations (10 pre + 11 post) and seed counts 20 / 393 / 7 tax / 1315 / 16 / 91.
- The app was RUNNING (4 tasks) when the DB was empty. Laith wants it stopped before any DB work (memory `feedback-env-fact-is-a-requirement`). After the restart there were 24 `focus_prod_app` connections, all targets healthy.
- The auto-mode classifier blocks writing an all-in-one prod-prep wrapper script ("Production Deploy"). Hand the steps over as blocks instead.
- **Prod hostnames are `medicine`/`sciences.focus-prod.literatumonline.com`** (decided; the wizard's `site_url` must be `https://medicine.focus-prod.literatumonline.com`). What still has to change before the wizard: runbook step 8-pre and skill `focus-poc-envs`. The older note follows. **Setup wizard was blocked until the DNS cutover (AISVC-3064):** the ALB SG allows only the Cloudflare prefix list `pl-0e8c219ccb4c09cab`, so a hosts-file entry is refused. `medicine.focus.wiley.com/` still redirects to Focus 1.0 and `/_emdash/*` gets Cloudflare `Missing resource`. The DB is ready (users 0); the wizard is the first action at cutover, because the first visitor becomes admin.
- `focus_admin` is IAM-only on prod after step 3. Prod content: real only, no ` -TEST`, and the import decision is still open.
- **Lessons from the prod run:**
  - The master secret ARN comes from `describe-db-instances … MasterUserSecret.SecretArn`; the app password from `focus-node-prod/rds/app` (check length 40, never print it). Step 3 runs psql inside `--exec bash -c` so the password session and the tunnel are one command.
  - Stop = record desired count, `--desired-count 0`, `wait services-stable`, check `0 0`. Restore = the recorded count (4), then `describe-target-health` all `healthy`; `services-stable` can time out at 10 min while tasks are still starting, so re-check before deciding.
  - **Connection proof** (read-only, as `focus_prod_ro`): `pg_stat_activity` grouped by `client_addr` for `usename='focus_prod_app'` must show the same 4 `10.193.9.x` IPs as `ecs describe-tasks … privateIpv4Address`. First run: 24 connections.
  - Wizard state check `select (select count(*) from users), (select value from options where name='emdash:site_url'), (select value from options where name='emdash:setup_complete')` gives `0||` before the wizard, `1|"https://medicine.focus-prod.literatumonline.com"|true` after.
  - `curl …/_emdash/api/setup/status` = `404 text/plain;charset=UTF-8` means Cloudflare's `Missing resource` (host not routed to the ALB yet), not the app.
  - **Prod is LIVE on the temporary hostname:** setup wizard done (`users`=1, `emdash:site_url`=`https://medicine.focus-prod.literatumonline.com`, `setup_complete`=true), revision `:2` set by hand in the console (image `08317967`, the two `EMDASH_*` vars), 4/4 healthy, 32 app connections. Terraform doesn't know `:2`: any prod plan must carry the temporary hostname values. `focus_prod_ro` can't see other users' `client_addr`/`backend_start` in `pg_stat_activity` (count works; use `DB_USER=focus_admin` for the IPs).
- **New image on prod = migrations first, then the revision.** `b17dc8fb`→`08317967` (`focus-v0.1.45`) needed site `0021`–`0024` (no core). `focus-node-seed-fast.sh --env prod --deliver --no-seed --build` with `REPO=…/aida-emdash-main-build` did it in one run (site 21→25, `[deliver] DONE: focus_prod at 08317967`). The container does NOT run migrations at start (`CMD node ./dist/server/entry.mjs`), and a console "Force new deployment" reuses the digest-pinned revision. First deliver run failed `AWS account is '577211136297', expected 909176971711`: the stage re-runs didn't get the prod settings; fixed by exporting `TARGET_ENV` and setting `ACCOUNT` in the prod block.
- Still open: step 6 counts block never run (expect 20 | 393 | 9 | 1315 | 16 | 91 | 0 | 54 | 21 | ~19), step 8 wizard at cutover, step 9 cleanup (close the 5439 tunnel, `ops-tmp/` empty), and the two bench-script changes are uncommitted.

## The shared nonprod instance

Proven end to end on Dev and UAT 2026-09-17 (AISVC-3036, PR #490). One RDS instance `focus-poc-node-nonprod-pg` (PG17, DbiResourceId `db-4YWQVCVU7CDV6M4P54IICOGSPA`) holds one database per env: `focus_poc`, `focus_dev`, `focus_uat`. Roles are per INSTANCE, so every env has its own `focus_<env>_app` (password, ECS), `focus_<env>_migrator` (IAM, DDL owner), `focus_<env>_ro` (IAM). `CONNECT` per database, revoked from `PUBLIC`. Reference doc: `~/Downloads/projects/focus-multi-env-plan/shared-db-structure.md` (+ `.html`); runbook Phase F in `bringup-dev-uat.md`; repo plan doc `custom/infra/plan/multi-env-dev-uat-plan.md` §16.

## Hard rules

- **Laith executes** every AWS / terraform / psql mutation in his terminal; you give exact commands with the expected output, then read what he pastes (memory `aws-commands-not-execute`, `never-run-terraform`). Reading state (`gh`, git, local files) is fine for you.
- **Databases, not schemas.** Focus tooling hardcodes `public.` (seed preflight, `migrate-site.mjs` tracking table, FTS migrations, `roles.sql`, `state-report.sh`).
- **Terraform never creates the database or roles** (AWS provider can't; the `postgresql` provider would need the tunnel on every plan). Inside-Postgres objects are created over the SSM tunnel by hand.
- **Fresh env DBs are EMPTY by decision** — schema + taxonomies + 91 sponsors only. Never apply `custom/sites/focus/db/seeds/*_seed_dummy_pg.sql` to Dev/UAT.
- **Four SEPARATE bootstrap commands**, never one chained line: SSO creds (~1 h) and IAM tokens (15 min) expire during the ~45-min seed; a chained 4th command dies with `ExpiredToken`. Refresh `~/.aws/credentials` while the seed runs so the queued command survives.

## Prerequisites (verify, don't assume)

```bash
export AWS_PROFILE=909176971711_AWSNonProdASTechAdmin TF_PLUGIN_CACHE_DIR=~/.terraform.d/plugin-cache
REPO=~/Downloads/projects/aida-emdash-bastion   # on main (was poc until 2026-09-28), PULLED + BUILT: pnpm install --frozen-lockfile && pnpm --filter emdash build && pnpm --filter focus seed:merge
BENCH=~/Downloads/projects/emdash-bench/bench
STACK=$REPO/custom/infra/terraform/envs/nonprod/31-node-app-dev   # or 32-node-app-uat
ENV=dev
```
- `aida-emdash-bastion` is the ONLY checkout holding the gitignored `backend.hcl` + `terraform.tfvars` for 31/32 (recreated from the `.example` files 2026-09-17; same bucket `focus-poc-tfstate-909176971711`, KMS `042479d0-…`, key `envs/nonprod/<stack>/terraform.tfstate`). `aida-emdash-poc` may be on another branch with uncommitted work — leave it alone. A branch is checked out in ONE worktree only (`git worktree list`).
- The IAM script's DEFAULT target (`--target node`, `RDS_PREFIX=focus-poc-node`, local :5433) IS the shared instance; pick the env with `PGDATABASE=focus_<env> DB_USER=focus_<env>_migrator`. `focus_admin` (rds_superuser) is the default user and reaches every database.
- Admin profile's `rds-db:connect` covers new user names (verified: `focus_dev_migrator`, `focus_uat_migrator`). `PAM authentication failed` on a new user = policy gap or expired token.

## Procedure (new database or rebuild)

```bash
# 1. database + roles (as focus_admin; roles.sql must be run CONNECTED TO THE TARGET DB — it refuses otherwise)
terraform -chdir=$STACK init -backend-config=backend.hcl -input=false
APP_PW=$(aws secretsmanager get-secret-value --secret-id "$(terraform -chdir=$STACK output -raw app_secret_arn)" --query SecretString --output text | jq -r .password); echo ${#APP_PW}   # 40
$BENCH/focus-node-db-iam.sh -c "CREATE DATABASE focus_$ENV;"
PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh -v env=$ENV -v app_password="$APP_PW" -f $REPO/custom/infra/terraform/db/roles.sql
#   expect: "roles: app=focus_dev_app migrator=focus_dev_migrator ro=focus_dev_ro database=focus_dev", CREATE ROLE ×3 (first run), ALTER ROLE, GRANT ROLE ×3, ALTER DEFAULT PRIVILEGES ×4, no ERROR
DB_USER=focus_${ENV}_migrator PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh -Atc "select current_user, current_database()"

# 2. bootstrap — FOUR commands, run one at a time
DB_USER=focus_${ENV}_migrator PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh --exec node $REPO/custom/infra/terraform/db/migrate.mjs                          # 53 core
DB_USER=focus_${ENV}_migrator PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh --exec node $REPO/custom/sites/focus/db/migrate-site.mjs --phase pre-seed        # 4 site
DB_USER=focus_${ENV}_migrator PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh --exec node $REPO/custom/sites/focus/db/bootstrap-seed.mjs                       # ~45 min, no output until final JSON
DB_USER=focus_${ENV}_migrator PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh --exec node $REPO/custom/sites/focus/db/migrate-site.mjs --phase post-seed       # 5 FTS site migrations
DB_USER=focus_${ENV}_migrator PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh --exec node $REPO/custom/sites/focus/db/migrate-site.mjs --status                # applied: 9, pending: 0
```
Seed noise that is NORMAL: 21× `Failed to enable search for <collection>: No Postgres search backend registered` stack traces (the standalone script has no pg-search backend; FTS comes from the post-seed migrations). Expected final JSON: collections 21, fields 490, taxonomies 7 / terms 1315, redirects 20, content 91.

```bash
# 3. verify the data (TABLE NAMES: _emdash_redirects, options.name — NOT redirects / options.key)
DB_USER=focus_${ENV}_migrator PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh -Atc "
select 'collections', count(*) from _emdash_collections
union all select 'fields', count(*) from _emdash_fields
union all select 'taxonomy_defs', count(*) from _emdash_taxonomy_defs
union all select 'terms', count(*) from taxonomies
union all select 'redirects', count(*) from _emdash_redirects
union all select 'sponsors', count(*) from ec_sponsors
union all select 'users', count(*) from users
union all select 'core_migrations', count(*) from _emdash_migrations
union all select 'site_migrations', count(*) from _focus_site_migrations
union all select 'content_tables', count(*) from information_schema.tables where table_schema='public' and table_name like 'ec\_%'"
# expect 21 | 490 | 9 | 1315 | 20 | 91 | 0 | 53 | 9 | 21
PGPASSWORD="$APP_PW" psql "host=127.0.0.1 port=5433 dbname=focus_$ENV user=focus_${ENV}_app sslmode=require" -Atc "select count(*) from ec_sponsors"   # 91 — the exact creds ECS will use
```
Seed PROGRESS from a second terminal (needs `export AWS_PROFILE`, reuses the tunnel; `ec_sponsors` appears mid-seed so guard it):
```bash
PGDATABASE=focus_$ENV ./focus-node-db-iam.sh -Atc "select 'terms', count(*) from taxonomies union all select 'sponsors', case when to_regclass('ec_sponsors') is null then 0 else (xpath('/row/c/text()', query_to_xml('select count(*) as c from ec_sponsors', false, true, '')))[1]::text::int end union all select 'migrator_sessions', count(*) from pg_stat_activity where usename='focus_${ENV}_migrator'"
```
Order inside the seed: collections → fields → terms (1315) → sponsors (91).

```bash
# 4. point the ECS env at it — the stack's db_name/app_username defaults already name focus_<env>/focus_<env>_app.
#    When SWITCHING from another database (as in the #490 move): targeted apply first so nothing is destroyed while the task still uses the old DB.
#    moved blocks need BOTH addresses as targets or the plan errors "Moved resource instances excluded by targeting".
terraform -chdir=$STACK plan -out=s1.tfplan -target=module.app_credential -target=aws_secretsmanager_secret_version.database_url -target=aws_vpc_security_group_ingress_rule.shared_rds_from_app -target=aws_kms_key.env -target=aws_kms_alias.env -target=module.rds.aws_kms_key.rds -target=module.rds.aws_kms_alias.rds
#    expect: Plan: 3 to add, 1 to change, 2 to destroy (2 secret versions replaced, 1 ingress rule, secret description)
terraform -chdir=$STACK apply s1.tfplan
aws ecs update-service --cluster focus-$ENV-node-nonprod-focus --service focus-$ENV-node-nonprod-focus --force-new-deployment >/dev/null
aws ecs wait services-stable --cluster focus-$ENV-node-nonprod-focus --service focus-$ENV-node-nonprod-focus
curl -s -o /dev/null -w '%{http_code}\n' https://medicine-focus-$ENV.literatum.com/   # 200 (sciences likewise)
aws secretsmanager get-secret-value --secret-id "$(terraform -chdir=$STACK output -raw database_url_secret_arn)" --query SecretString --output text | sed -E 's#://([^:]+):[^@]+@#://\1:***@#'
PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh -Atc "select usename, datname, count(*) from pg_stat_activity where usename like 'focus_%app' group by 1,2 order by 1"   # focus_<env>_app|focus_<env>|~10
```
A targeted apply leaves OUTPUTS stale (`rds_db_name`, `master_user_secret_arn`) until the next full apply — not a bug.

```bash
# 5. setup wizard — the PUBLIC homepage does NOT redirect on an empty site; go to the admin path
#    https://medicine-focus-<env>.literatum.com/_emdash/admin/setup
PGDATABASE=focus_$ENV $BENCH/focus-node-db-iam.sh -Atc "select (select count(*) from users), (select value from options where name='emdash:site_url'), (select value from options where name='emdash:setup_complete')"
#    expect 1|"https://medicine-focus-<env>.literatum.com"|true

# 6. (move only) full plan/apply removes what the config no longer has; grep needs -no-color
terraform -chdir=$STACK plan -no-color -out=s2.tfplan | grep -E '^Plan:|will be destroyed'
terraform -chdir=$STACK apply s2.tfplan
terraform -chdir=$STACK plan -no-color | grep -E 'No changes|Plan:'
```

## Rebuild of an existing env DB (drop + recreate) — `rebuild-dev-uat.md`

Proven on UAT and Dev (Dev from `ff8e6fd5`, image = same digest, desired count 1) from `main` `1c6caf4d` (image was `9b4a519d` — see the HEAD-moved gotcha). Build `origin/main` in a DETACHED worktree `~/Downloads/projects/aida-emdash-main-build` (no checkout holds `main`; bastion/poc sit on legacy/feature branches) and pass `REPO=` to every `focus-node-seed-fast.sh` call (its default is `aida-emdash-poc`). Fast script = seconds per stage on the jump host, not the ~45-min tunnel seed.
- **Check first that the env RUNS that commit**: service task def image digest == ECR digest of `:<short sha>` (CI's `deploy-env.yml` pins digests; UAT needs approval in `build-focus-node-image.yml`). Don't rebuild an image that's already deployed.
- **Gate the DROP on `runningCount=0` AND zero NON-app connections** (Dev: 10 idle `focus_dev_app` sessions from the stopped task lingered after services-stable; FORCE closes them). Earlier rule was **Gate the DROP on 0 connections in shell** (`[ "$N" = 0 ] && DROP`), never a `# expect 0` comment — pasted as one block, 20 draining-task connections were printed and the DROP ran anyway.
- `information_schema`/`pg_tables` only see the CONNECTED db (script default `focus_poc`) — set `PGDATABASE=focus_<env>` for any "is it empty" check.
- App-creds check: `DBURL_ARN=focus-<env>-node-nonprod/app/database-url` (secret NAME). `list-secrets --query '...| [0]'` paginates → `None\n<arn>` → `ValidationException: Invalid name`.
- `main` expected counts: collections 20, fields 393 (seed JSON; my own jq over seed.json said 403 because slugs repeat across merged parts — count unique slugs per collection), taxonomy_defs 9 (7 seeded + 2 core), terms 1315, redirects 16, sponsors 91, users 0, core migrations 54, site migrations 18 (9 pre + 9 post; post-seed 0015/0016/0018 retire fields — deleted nothing on a fresh DB), FTS tables 19. The skill's 21/490/53/9 numbers above are `poc`-era.
- **The build worktree can move under you.** UAT: step 0 built `9b4a519d` at 11:42, the step-0 block was re-run at 12:09 (reflog: `checkout: moving from 9b4a519d… to origin/main`) and rebuilt `1c6caf4d`, so the DB got #593's migration 0018 while the image stayed `9b4a519d`. I then reported "DB matches 9b4a519d" without re-checking. Re-check `git -C …main-build log -1` right before stage 4 and state the commit the DB was ACTUALLY built from (reflog + `seed.json` mtime settle it after the fact).
- **Step 0 now starts from the env's RUNNING image**: task def image digest -> ECR tags -> 8-char commit -> `checkout --detach <sha>` (never `origin/main`). Runbooks `rebuild-dev.md`/`rebuild-uat.md` (generated by `gen-rebuild-docs.py`) also carry step 8 (the 5 real samples) and "Getting a new image onto <env>".
- **UAT approval**: env `focus-node-deploy-uat` (id 23058756874) requires team `aida-focus-sre` (mvariaaty, hbhavsarwiley, ashishkhandale) or `mvariaaty`; Laith is NOT a reviewer. `build-focus-node-image.yml` has `cancel-in-progress: true` per ref, so a newer push to main cancels a run parked at the UAT gate, and re-running the old run cancels the newer build (both happened: ff8e6fd5 attempt 1 cancelled by 0719556a; Laith's re-run then cancelled 0719556a's build).
- curl 403 with `cf-mitigated: challenge` = Cloudflare edge, not the app; prove health with `elbv2 describe-target-health` (2 healthy) and do the setup wizard in a real browser.

## Gotchas hit (each cost a round-trip)

- `psql -c "a; b"` prints ONLY b's result — one statement per `-c`, or `-f file`.
- The IAM script appends a `PAM authentication failed` HINT footer to EVERY error, including plain SQL errors — read the real `ERROR:` line above it.
- `terraform` output is colored: `grep '^Plan:'` on raw output matches nothing; use `plan -no-color`. `| tail -1` lands on `Releasing state lock…`, not the verdict.
- Local `pg_dump` is v14 and refuses a PG17 server. To copy a DB instead of rebuilding, run the v17 client from a container over the tunnel: `... --exec docker run --rm --network host -e PGHOST -e PGPORT -e PGUSER -e PGPASSWORD -e PGDATABASE -e PGSSLMODE -v /tmp:/tmp postgres:17-alpine pg_dump -Fc --no-owner --no-privileges -f /tmp/x.dump`, restore as `focus_<env>_migrator`, then re-run `roles.sql` for the grants.
- If the plan shows FEWER destroys than expected and an RDS destroy "completes after 1s", something already ran (UAT 2026-09-17: an apply from the first plan ran unseen between prompts). `aws rds describe-events --source-type db-instance --source-identifier <id> --duration 1440` (UTC) and CloudTrail `DeleteDBInstance` settle it. Ask what ran in the gap before theorizing.
- `roles.sql` was validated in `docker run postgres:17-alpine` before shipping (dev/uat/poc names, idempotent re-run, wrong-db guard, cross-db CONNECT denied, DDL denied, migrator-created table writable by app). Repeat that when changing it.

Related skills: `focus-node-db-access` (tunnel/IAM script details), `focus-poc-envs` (stacks, hosts, CI/CD), `shareable-html-docs` (the doc set). Memory: `focus-multi-env-plan`.
