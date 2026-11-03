---
name: focus-seed-reapply
description: Use when reseeding or re-applying the EmDash seed on a focus-poc environment (poc v1, hd, node) — the POST /_emdash/api/seed/reapply endpoint, taxonomy/content drift vs the seed, SEED_REAPPLY_DISABLED errors, or "which env allows reseeding".
---

# Focus seed re-apply (API)

**Disambiguation (learned 2026-09-24):** when Laith says "seed the env" / "the migration and seed commands" without mentioning the API, he means the DB-side migrate+seed — and specifically **the fast script `focus-node-seed-fast.sh`** (runs on the jump host in-VPC; see `focus-node-db-access` § FAST DB ops), not the ~45-min tunnel path (`focus-env-db-bootstrap`) and not this HTTP endpoint. Default to the fast script for POC. Since 2026-10-09 the whole migrate+seed delivery for poc/dev/uat is one command, `focus-node-seed-fast.sh --env <env> --deliver`; see skill `focus-db-deliver`.

`POST /_emdash/api/seed/reapply` — from `custom/packages/seed-reapply` (README there covers the full API). Admin-only (`schema:manage`); session callers need `X-EmDash-Request: 1`, bearer tokens need `admin` scope. **Auth is checked BEFORE the env gate** — so `401` says nothing about the gate, and `403 SEED_REAPPLY_DISABLED` proves your admin session works.

## Env gate map (updated 2026-08-24)

| env | gate `EMDASH_SEED_REAPPLY_ENABLED` | to enable |
|---|---|---|
| poc v1 (`medicine-focus-poc`) | **ON** — dry-run verified | — |
| hd (`medicine-focus-poc-hd`) | **ON** (verified 2026-08-24: dry-run 200; was OFF via `d5230b15`, someone re-enabled) | — |
| node (`medicine-focus-poc-node`) | OFF | ECS task-def env var via console (terraform blocked); task roll drops sessions. Usually use `bootstrap-seed.mjs` instead — see `focus-node-db-access` |

**HD update-mode 500s (2026-08-24, unresolved):** on HD, `{"onConflict":"update"}` (even with `includeContent:false`) returns `500 SEED_ERROR "Failed to apply seed"` reproducibly — likely the Worker subrequest cap (update rewrites ~1,300 rows/run and never converges since it redoes them all each run). `{"onConflict":"skip", includeContent:true, skipMediaDownload:true}` works (200 applied). Diagnose the 500 with `wrangler tail` when needed.

## The physics rule (most common mistake)

**The seed applied is the one baked into the running build.** Corollary (2026-09-24): merging a seed fix to the base branch (`poc` then; `main` since 2026-09-28) does NOT repair already-seeded rows — skip-mode leaves them and nothing rewrites them until an update-mode run from a checkout that actually has the fix. PR #518 fixed four sponsor-logo keys on `poc` and poc's DB still served 404s a day later. See `focus-media-reference-audit` and `focus-node-db-access` § PRE-SEED GATE. Editing seed sources changes nothing until rebuild+redeploy — and `onConflict:"update"` forces the DB to match the *embedded* seed, so a seed-borne flaw is applied harder, never fixed, by the API.

Known seed-borne flaw: `subject` taxonomy has `"collections": []` in `custom/sites/focus/seed/taxonomies.json` (flagged in every dry run). Decided fix (2026-08-13, not landed): assign the same 5 collections as `specialty_methodology`.

## skip vs update

- **skip NEVER creates new FIELDS on existing collections** (root-caused 2026-08-24): `applySeed` short-circuits per collection — if the collection exists it counts ALL its fields as `skipped` without checking them individually (`packages/core/src/seed/apply.ts:222`). Only update-mode walks fields one-by-one and creates missing ones. Consequence: a seed change that adds a field to an existing collection (e.g. PR #331's `regional_availability_action` radio) silently no-ops under skip while the summary looks successful (`fields: skipped: N` where N already includes the new fields). New taxonomies/terms/content ARE created by skip (those are checked per-row). Symptom in the app: the field's editor section missing/partial.
- `"skip"` (default): inserts missing rows only (except fields, above); never fixes drift (e.g. gated_content 2-vs-4 collections drift survived it).
- `"update"`: overwrites ALL seed-matched rows and **force-publishes** matched content. No per-taxonomy filter exists — body accepts only `onConflict`, `includeContent`, `dryRun`, `skipMediaDownload` (unknown fields → 400).
- **Taxonomy-only reconcile (the usual want):** `{"onConflict":"update","includeContent":false}` — fixes taxonomy-def drift without touching the 91 seeded sponsor entries. VERIFIED 2026-08-13 on poc v1: 200, gated_content 2→4 confirmed fixed. The node env's Postgres had the same drift — RECONCILED 2026-08-31 via `bootstrap-seed.mjs --update` over the IAM tunnel (gate still off on node; DB-side path per `focus-node-db-access`): collections 6 / fields 112 / terms 1310 updated, 91 sponsors re-published.
- Never touched/deleted: entries and terms created by editors that aren't in the seed.

## Recipe

```js
// browser console ON THE TARGET ORIGIN, logged into /_emdash/admin:
fetch("/_emdash/api/seed/reapply", {
  method: "POST",
  headers: { "Content-Type": "application/json", "X-EmDash-Request": "1" },
  body: JSON.stringify({ dryRun: true }),   // always probe first
}).then(async r => console.log(r.status, await r.json().catch(() => r.text())));
```

Workers envs only: a full apply (~1,000 term rows) can hit the subrequest cap mid-apply; D1 has no transactions → partial state is normal, the endpoint is **idempotent — re-run until it converges** (409 = another apply holds the 10-min claim). Fargate/node has no such cap.

Verify: re-run `dryRun` (warnings only = converged) or check the taxonomy in `/_emdash/admin`.

Related: `focus-node-db-access` (DB-side reseed via bootstrap-seed.mjs); memory `[[focus-poc-hd-deploy-ci]]`.
