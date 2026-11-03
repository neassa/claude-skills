---
name: focus-db-deliver
description: Use when Laith asks to run the migrations and seed on a focus env (poc, dev, uat), "rebuild the seed and latest changes", "deliver main to dev/uat", or pastes output from focus-node-seed-fast.sh --deliver or its step-by-step migrate/seed runs. One-command delivery of origin/main's core migrations, site migrations and update-mode seed to a database on the shared nonprod RDS, in the order an existing database needs.
---

# Deliver main to a focus env DB (migrations + seed)

Laith runs every command (his AWS creds). You prepare the repo, hand over the block, read the pasted output.
Deeper reference: `focus-node-db-access` (tunnels, roles, fast-script internals), `focus-seed-reapply`
(skip vs update semantics), `focus-site-migration-authoring` (writing migrations).

## The one command

```bash
cd ~/Downloads/projects/emdash-bench/bench
REPO=~/Downloads/projects/aida-emdash-main-seed ./focus-node-seed-fast.sh --profile 909176971711_AWSNonProdASTechAdmin --env dev --deliver --build
```
`--env poc|dev|uat` sets `PGDATABASE=focus_<env>` and the migrator (`focus_migrator` for poc, `focus_<env>_migrator`
otherwise). It prompts before each write; `--yes` skips the prompts. Run Dev first, read it, then UAT.

**`--no-seed` (added 2026-10-12, Laith asked for it):** `--deliver --no-seed` runs the same migration stages in the
same order (core, site pre-seed, site post-seed, final status) and skips the seed dry-run, `--update` and the
re-apply step; the seed.json gate is skipped too. Use it for a migrations-only release and for POC (real content).
Refused without `--deliver`. Tested with the AWS stages stubbed, not yet live.

**`REPO` must be `aida-emdash-main-seed`**: a detached worktree kept for this job. The script's default REPO
(`aida-emdash-poc`) is parked on a feature branch and the gate refuses it; `aida-emdash-bastion` is on legacy `poc`.
No worktree has `main` checked out, so the detached one is how you get origin/main. `--build` refuses a named branch
or a dirty tree, so it cannot yank a feature checkout.

## What --deliver does (bench copy, rewritten 2026-10-09)

1. **Repo check**: fetches origin/main; `--build` = `checkout --detach origin/main` + `pnpm install --frozen-lockfile`
   + `pnpm --filter emdash build` + `pnpm --filter focus seed:merge`. Refuses unless HEAD == origin/main
   (`--allow-branch` overrides) and `seed.json` mtime >= HEAD commit time. Prints target, HEAD, seed time; asks.
2. Core `--migrate --status`, apply if pending.
3. `--migrate-site --status`; if pending, `--migrate-site --phase pre-seed`.
4. Seed `--dry-run` (validation only, NOT a diff), then `--update`.
5. `--migrate-site --phase post-seed`.
6. **Re-apply** post-seed files that were ALREADY applied before this run and whose header says "re-apply this file by
   hand" (today: `0022_search_term_descriptions.sql`), via `focus-node-db-iam.sh -v ON_ERROR_STOP=1 -1 -f` as the
   env's migrator. The tracker marks them applied, so migrate-site will never re-run them.
7. Final `--migrate-site --status` must show `pending: 0`, else it fails.

**Stale as of 2026-10-19:** pre-seed is retired (see `focus-site-migration-authoring`) and PR #715 makes deploy run core +
post-seed itself once merged. Step 3 (`--phase pre-seed`) then goes away from `--deliver`; the `--no-seed` path becomes
core + post-seed + status. The script has not been changed yet; check `git status` in the bench folder before handing
over a `--deliver` block.

## Why that order (each one bit us)

- **All site migrations before the seed fails on existing DBs**: `0003_fts_search.sql` references seed-created
  columns (POC, 2026-09-18). Pre-seed / post-seed phases are declared in each file (`-- migration-phase: ...`).
- **`--update` (with content) resets every seeded term's description to empty.** A post-seed data migration run
  before it is wiped. 0022 writes 30 search-page descriptions (20 `specialty_methodology` + 10 `subject`), and on
  a re-delivery it is already applied, so only step 6 brings them back. On Dev 2026-10-09 the re-apply printed `UPDATE 30`.
- `--update` force-republishes the 91 seeded sponsors and overwrites seed-matched rows: editor edits to seeded rows
  are lost. Say so before Laith confirms.

## Reading the output

- `Failed to enable search for <collection>: No Postgres search backend registered`: harmless noise from running
  outside the app (one per collection). The FTS tables come from site migrations. Exit is still 0.
- A good `--update` ends with the `done` JSON (example, Dev 2026-10-09: collections updated 20, fields 394, terms
  1315, redirects 16, content 91) and `[run] status: Success`.
- Success line: `[deliver] DONE: focus_<env> at <sha> <subject>`.

## If the local run died mid-stage

The SSM command keeps running on the jump host after the local script dies. Get its real result before re-running
anything (the command id is on the `[run] SSM command ...` line):
```bash
aws ssm get-command-invocation --profile 909176971711_AWSNonProdASTechAdmin --region us-east-1 --command-id <paste-from-[run]-line> --instance-id i-0b2671c177b8083dd --query '[Status,StandardOutputContent]' --output text | tail -25
```
(Fill the id from the pasted output before handing this over. Never hand over a `<placeholder>`.)

Then check whether the descriptions survived:
```bash
cd ~/Downloads/projects/emdash-bench/bench
PGDATABASE=focus_uat ./focus-node-db-iam.sh --profile 909176971711_AWSNonProdASTechAdmin -c "SELECT name, count(*) AS terms, count(*) FILTER (WHERE btrim(COALESCE(NULLIF(data,'')::jsonb->>'description',''))<>'') AS with_description FROM taxonomies WHERE name IN ('specialty_methodology','subject') AND locale='en' GROUP BY name;"
```
Expected: specialty_methodology 20, subject 10. Zero means re-apply 0022 (or re-run `--deliver`, which does it).

## Rules

- **Never edit `focus-node-seed-fast.sh` (or any handed-over script) while Laith may be running it.** Bash reads the
  file by offset; on 2026-10-09 an in-place rewrite crashed a UAT `--update` mid-poll (`line 376: syntax error`). Write
  to a temp file and `mv` it over. Memory [[no-in-place-script-rewrite]].
- State the branch, SHA and target DB back to Laith before he runs it (the gate prints them; repeat them).
- The bench script is UNCOMMITTED in `emdash-bench`. A vendored copy at `custom/infra/scripts/focus-node-seed-fast.sh`
  (uncommitted, branch `AIDAFOCUS-377`) still has the old broken order, and the drafted GitHub Actions `deliver`
  choice calls it. Don't dispatch that until it's synced.

- **A content load can need a deliver first.** Field limits (`validation.maxLength`) live in the env's
  `_emdash_fields`, and they change only when a deliver runs the new site migrations. Before loading a new convert,
  compare its longest values (UTF-16 units) against the env's limits:
  `select f.slug, f.validation from _emdash_fields f join _emdash_collections c on c.id = f.collection_id where c.slug = 'key_opinion' and f.slug in ('sponsorship_declaration', 'legal_disclosure')`.
  2026-10-14: #690 (KO disclosure rules) gives `ko-145343-2024-1` a 754-unit legal_disclosure; the KO limit is 600 at
  `65fd9f83` (Dev/UAT) and 1500 only from #689 (`b3b4e915`) on main. So #689 has to be delivered to UAT/Dev before a
  KO load with #690 (re-check: it may have been delivered since).

## State log

- 2026-10-09: Dev and UAT delivered at origin/main `4cae0879` (core 54/0 pending, site 23/0, 0021 + 0022 applied,
  30 descriptions present on both). Dev via `--deliver` (first live run, passed). UAT via the manual step blocks.
- 2026-10-11: site migrations 0023 (`podcast_collection_label`) + 0024 (`key_opinions_label`, #637) applied on POC
  (41 applied), Dev and UAT (25 each), `pending: 0`, at origin/main `26afb7e0` (`aida-emdash-main-seed` built 19:04).
  Check with: `for e in poc dev uat; do REPO=~/Downloads/projects/aida-emdash-main-seed ./focus-node-seed-fast.sh
  --profile 909176971711_AWSNonProdASTechAdmin --env $e --migrate-site --status 2>&1 | grep -E 'target|pending|00'; done`.
  POC holds real content: a label-only migration there needs `--migrate-site`, not `--deliver` (the seed `--update`
  would overwrite seeded rows).
- The gate was read in the code (`focus-node-seed-fast.sh:198-223`) when Laith asked "does it make sure it is using
  main?": it fetches origin/main on every run, refuses unless HEAD == origin/main (`--allow-branch` overrides) and
  seed.json is newer than HEAD. If main moves between env runs, the next run refuses until `--build` is added.
