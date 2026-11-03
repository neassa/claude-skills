---
name: focus-site-migration-authoring
description: Use when writing or reviewing a focus site migration (custom/sites/focus/db/migrations-pg/*.sql) — removing a collection or fields, renaming or retyping columns, cleaning drift a seed run left behind, or any hand-written DDL against a focus Postgres env. Covers what applySeed can and cannot do, the FTS trigger trap that breaks every later write, phase choice, and how to test the SQL before it touches a shared database.
---

# Writing a focus site migration

A site migration is the ONLY way to remove or reorder anything in a focus database.
Reseeding cannot do it, and reaching for the seed first is the usual wasted hour.

## What applySeed cannot do

Both verified in `packages/core` on 2026-09-24:

- **It never deletes.** `--update` reconciles rows TO the seed and leaves everything else.
  A seed run from a stale branch adds its extra collections and fields permanently; a
  later `--update` from the base branch (`main`; `poc` before 2026-09-28) restores what it declares and cannot remove the rest.
- **It never writes `sort_order`.** `createField` appends at `max+1`
  (`schema/registry.ts:470`), `updateField` keeps the existing value (`:634`), and
  `applySeed` passes neither. A field added to the MIDDLE of a seed's field array lands at
  the END of the table forever. On POC this had silently misordered 5 of 20 collections —
  two of them with no extra fields at all, purely wrong order.

So: "the seed is fixed, reseed it" is wrong for any removal or reordering. Write a
migration.

## The FTS trap — read before dropping any column

`applySeed`'s `createField` calls `syncSearchState`, which rebuilds
`_emdash_fts_<slug>_trigger_fn` from whatever field list was current at the time. So the
trigger on a drifted env may reference fields the current seed does not declare. Drop such
a column and **every later write to that table fails**:

```
ERROR:  record "new" has no field "abstract"
CONTEXT:  PL/pgSQL function _emdash_fts_<slug>_trigger_fn() line 4
```

Reads keep working, so this does not surface until someone saves an entry.

The fix is to `CREATE OR REPLACE` the trigger function to the CURRENT seed's definition
BEFORE dropping, copying the block from `0003_fts_search.sql` (or `0006_editorial_feature_fts.sql`).
`CREATE OR REPLACE` preserves the pg_proc OID so the AFTER trigger stays attached.

Then guard it properly: **skip a collection whole unless you can install the correct
trigger first.** The guard must cover the shadow table AND `emdash_pt_to_plain()` AND the
case where a trigger function exists that you cannot replace. Gating the drops on a
weaker condition than the reset is the exact hole a reviewer proved reachable on PG 17:
guards passed, reset was skipped, columns went anyway.

## Phase: everything is post-seed now (decision 2026-10-19)

Laith retired the pre-seed phase while PR #715 (AIDAFOCUS-675, migrations on deploy) was in review: deploy runs core
`migrate.mjs` then `migrate-site.mjs --phase post-seed` as one-off ECS tasks, never pre-seed, never the seed. Write every
new migration as `-- migration-phase: post-seed`. Files still labeled pre-seed (0001, 0002, 0004, 0005, 0011-0014, 0017,
0020_infographic, 0021) would be skipped by `--phase post-seed`: relabel them (safe, the tracker keys on filename) or drop
`--phase` from the deploy step. Do not call skipping pre-seed a gap in a review, and do not suggest running it. Still to
change when phases go: `phase-parser.mjs` VALID_PHASES, `bootstrap-fresh-pg.sh`, `focus-node-seed-fast.sh --deliver`.
Since the seed is not re-applied, a seed change (field limits, labels, terms) reaches existing envs only through a
migration; 0025/0026 are the pattern (UPDATE `_emdash_fields` guarded on the old value, "safe to re-run").
Because deploy migrates BEFORE the service update, old tasks run on the new schema for the rollout: ship a DROP COLUMN
one release after the code stops using it (cached-plan errors on old tasks otherwise).

The older text below predates that decision; its pre-seed/post-seed mechanics still explain existing files.

## Phase (older text): default to post-seed

- `db/README.md:14` — pre-seed "must not reference `ec_*` tables". Any cleanup that
  touches content tables is therefore post-seed by convention.
- `bootstrap-fresh-pg.sh` order is core -> **pre-seed** -> seed -> **post-seed**. A
  pre-seed cleanup on a fresh bootstrap runs BEFORE the seed creates the drift, records
  itself in `_focus_site_migrations`, and can never run again. Post-seed cleans the same
  run.
- Phase does NOT control whether a later `--update` re-creates something. Only the seed
  not declaring it does that. Do not write that rationale into a header; it is wrong.

## Copy what core's own delete does

`SchemaRegistry.deleteField` (`schema/registry.ts`) drops the `_emdash_fields` row, syncs
FTS, drops the column, AND calls `markContentMediaUsageCollectionStaleSafely`. Hand-written
SQL that skips the last step leaves `_emdash_media_usage` rows keyed on dropped
`field_slug`s, so the media library keeps counting phantom "used by" references:

```sql
DELETE FROM "_emdash_media_usage"
WHERE field_slug = ANY (ARRAY['hero_image','...'])
  AND source_key IN (SELECT source_key FROM "_emdash_media_usage_sources"
                     WHERE collection_slug = '<slug>');
UPDATE "_emdash_media_usage_index_status" SET status='stale', last_error_code='CONTENT_USAGE_STALE'
WHERE adapter_id='content-media' AND scope_type='collection' AND scope_key='<slug>';
```

For a whole collection, `0011_retire_removed_content_types.sql` is the reference: FTS
function CASCADE, FTS table, `ec_` table, then `revisions`, `_emdash_seo`,
`_emdash_comments`, `content_taxonomies`, `_emdash_content_bylines`, media-usage
occurrences before sources, and `_emdash_collections` last (fields cascade).

## Renumbering sort_order

Seed-declared fields first in declared order, everything else after in its existing
relative order, so legacy columns are never lost or shuffled arbitrarily:

```sql
WITH ranked AS (
  SELECT f.id, (ROW_NUMBER() OVER (
           ORDER BY COALESCE(array_position(ordered_array, f.slug), 1000000 + f.sort_order),
                    f.sort_order) - 1) AS new_order
  FROM "_emdash_fields" f JOIN "_emdash_collections" c ON c.id = f.collection_id
  WHERE c.slug = '<slug>')
UPDATE "_emdash_fields" f SET sort_order = r.new_order FROM ranked r
WHERE f.id = r.id AND f.sort_order IS DISTINCT FROM r.new_order;
```

`idx_fields_sort` is NOT unique, so the whole collection renumbers in one statement with no
intermediate collision.

## Test it locally before it touches a shared env

There IS a local Postgres with focus databases: `focus_migrator` / `focus_migrator_local`
on `localhost:5432` (`focus_poc`, `focus_poc_node`, `focus_poc_sync_*`, `focus_poc_sqltest`).

- `focus_migrator` **cannot CREATE DATABASE** locally, so no scratch copy. Use transactional
  DDL instead — Postgres rolls back `ALTER TABLE` and `DROP` cleanly:
  `BEGIN; \i migration.sql; \i migration.sql; <verification SELECTs>; ROLLBACK;`
  Two `\i` in one transaction tests idempotency for free.
- **Always wrap. No exceptions.** 2026-09-24 a "fresh DB inertness" check was run without
  `BEGIN`/`ROLLBACK` against `focus_poc_sqltest`; it carried the drift and was permanently
  modified (6 collections -> 5). Unwrapped psql against any local focus DB is a real write.
- Local `focus_poc` is the OLD content model, so it is a good drifted fixture but lacks
  poc's later columns. Cover both branches: the poc-shaped path (add the missing column
  inside the transaction) and the not-poc-shaped path (leave it out, assert the collection
  is skipped WHOLE — no rows deleted, no columns dropped).
- Prove a regenerated trigger by writing through it: INSERT a row, check the shadow table,
  UPDATE it, check reindex, DELETE it, check removal, and `search_vector @@ to_tsquery`.

## After applying

`ALTER TABLE ... DROP COLUMN` takes ACCESS EXCLUSIVE. Long-lived app connections hold
cached plans over the old column set and throw `cached plan must not change result type`.
Force a new ECS deployment and wait for `rolloutState COMPLETED` before testing writes.

## Verifying afterwards, and its limits

Schema state and search are checkable read-only through
`/_emdash/api/schema/collections/<slug>/fields` and `/search?q=`. A WRITE is the only thing
that exercises the trigger, and two things can block that probe without meaning anything is
broken:

- **Stale draft revisions.** The migration clears columns and `_emdash_fields` rows but not
  revision JSON blobs, so `GET` on an entry with an outstanding draft still returns keys for
  dropped fields. Echoing that back in a `PUT` gets `unknown field on collection`.
- **Fixtures that predate a required field.** `auto-*` rows written by an older seed fail
  `display_published_date: required` on both PUT and publish, before the request ever
  reaches the database.

When the API path is blocked, settle it with SQL instead of asserting it works:

```sql
SELECT proname, prosrc LIKE '%<dropped_col>%' AS still_refs
FROM pg_proc WHERE proname LIKE '\_emdash\_fts\_%\_trigger\_fn';
```

Related: `focus-node-db-access` (applying via the fast script, and the PRE-SEED GATE on
which branch `$REPO` is on), `focus-seed-reapply`, `focus-media-reference-audit`.

## Reviewing a migration or deploy PR (technique, 2026-10-19)

Read the PR head without touching any worktree: in a clone whose `remote.origin.fetch` is narrow, fetch the PR ref
explicitly, then use `git show`/`git ls-tree` on it.
```bash
git fetch origin main refs/pull/<N>/head:refs/remotes/origin/pr-<N>
git rev-parse origin/pr-<N> origin/main
git ls-remote origin refs/heads/main refs/pull/<N>/head    # must match the two SHAs above
```
Check the scripts the PR calls at THAT ref (phase flags, env vars, Dockerfile COPY/WORKDIR so the path resolves in the
image), not a worktree on another branch. Checks that mattered on #715: failure of an earlier step stops later ones
(no status function in `if:` means implicit `success()`), `always()` cleanup, per-file transactions plus advisory lock,
IAM scope of RunTask/StopTask/PassRole/logs, and that the deploy role can now run any command as the DDL role.
The CI design: Terraform (once per env) creates the migrator task-definition family, task role and log group; each
deploy describes the family, swaps in the digest-pinned image, registers a new revision, `run-task` with a command
override, waits, reads the exit code and logs. The task stops itself on exit; revisions are never deregistered.
