---
name: amps-webinar-video-hosting
description: Use when hosting or re-hosting webinar/video assets on the Atypon file server (files.atypon.com/amps) — AIDAFOCUS-457 Bizzabo MP4 delta, AMPS-87, token_generator.sh / upload.js / generateToken.js, "upload the mp4s to Atypon for streaming", tus uploads, LOCK/META ops, or any Focus 1.0 webinar video URL work.
---

# AMPS webinar video hosting (files.atypon.com/amps)

Worked out 2026-09-23 from AIDAFOCUS-457, the June 2026 precedent, the real upload scripts, and the Literatum source. Re-verify paths and the shared secret before a run.

## Scope — this is Focus 1.0 / AMPS, NOT emdash

Focus 1.0 = the **AMPS product on Literatum** (`focus.wiley.com/doi/10.5555/webinars.*`). `files.atypon.com/amps` is that product's file bucket (`bucket = ${macro/product-name}`). EmDash/Focus 2.0 never uploads to or manages it:

- `custom/sites/focus/tests/unit/brightcove.test.ts:45` asserts `parseBrightcoveUrl("https://files.atypon.com/amps/…")` → **null**
- `custom/docs/specs/analytics-datalayer/FE-tech-video-events.md:21` lists it under "not supported: any other host"
- `custom/sites/focus/db/seeds/webinars_dummy_pg.sql` carries legacy URLs as plain `video_url` strings

2.0's only involvement is passive inheritance: URLs minted here become remote `video_url` values in the 1.0→2.0 export ([[focus-content-export]], AIDAFOCUS-362/366/381). Because the Brightcove parser rejects the host, those videos don't go through the Brightcove player path, so REQ-045 Brightcove video events (AIDAFOCUS-258) won't fire for them.

**Corollary for searching:** nothing about this work lives in `aida-emdash*`, Wiley Jira, or Wiley Confluence. It's AMPS-side — Atypon Jira and the AMPS team.

## Ticket trail

| Item | What it holds |
|---|---|
| **AIDAFOCUS-457** "Events Migration Delta - MP4 Hosting required" (Task/Backend, reporter Leo Hardy, assignee Mayank Varia, created 2026-09-18) | the 37-row job; attachment `Focus_Bizzabo_migration_delta_Sep2026_v5.xlsx` (tab `migration_ready`); Alok Avjeet's 2026-09-22 comment = the only written steps |
| **AMPS-87** (`jira.prod.atypon.com`) | the prior round: the DEH spreadsheet + JATS field-mapping Q&A in comment `13065831`. Not reachable from the Atlassian MCP here (wiley-global only) and the browse URL is login-gated |
| Confluence AF page `1053851670` "2026-06-04 On demand webinar migration on Focus1.0" | Alok's record of the first batch, sample on `amps-stag.literatumonline.com`, and item 19 predicting this delta ("videos were supplied in December … there will need to be a delta") |
| Dec 2025 batch | **623 distinct `files.atypon.com/amps/<hex>` URLs**, enumerable from `~/Downloads/AIDAFOCUS-362-import/out/seed-content.json` — diff the delta rows against these to confirm what's genuinely missing |

Contract constraint from the ticket: Bizzabo lapsed **end of Sept 2026**; 12-month contractual hosting obligation for the recordings.

## The scripts

`~/Downloads/bizzabo_upload_Scripts/bizzabo_downloadupload_Scripts/` (Mac zip, AMPS-side, arrived 2026-09-23; the user also keeps a copy under `~/personal/.../amps` — confirm the real path with him, don't guess it).

| File | What it does |
|---|---|
| `token_generator.sh` | `base64( ts . md5( ts . SECRET ) )` |
| `generateToken.js` | same in Node |
| `upload.js` | `tus-js-client` → `https://files.atypon.com/amps/`, 20 MB chunks, metadata `{filename, filetype}`, header `Authorization: Atypon <token>`, appends `"Filename","URL"` to `files.csv` beside itself |

**Four defects — all four will bite:**

1. The `Authorization` token is **hardcoded** in `upload.js` and dates from **2026-06-10 17:55 UTC** (decode the base64 to read its timestamp). Live it returns 403. `upload.js` never calls the generator — the token is hand-pasted, which is why Alok's step 3 (generate) precedes step 4 (upload).
2. **The secret is the open question.** A token freshly generated from the bundled secret was rejected live (`Authorization failed. Invalid access token.`), and that secret **differs** from the one checked into `product/amps/conf/amps.props.xml` in the lit-2610 worktree (compare by hash; never print values). Get the current prod value from the AMPS team or the live registry (`backstage/files.atypon.com/secret`) and probe before a batch run.
3. **`require` fails under `~/Downloads`**: `~/Downloads/package.json` has `"type": "module"`, so Node treats these `.js` files as ESM → `ReferenceError: require is not defined in ES module scope`. Move the folder out of `~/Downloads` or rename to `.cjs`.
4. No LOCK, no batch loop, and **no downloader** despite the folder name (`.DS_Store` lists no other files). Secrets sit in plaintext — never commit that folder.

## Protocol (source of truth: `~/sourcegit/literatum-worktrees/lit-2610/atypon`)

`publish/src/java/com/atypon/publish/AtyponFilesServiceImpl.java`:

- token = `base64( ts + "." + md5( ts + "." + secret ) )`, md5 lowercase hex, header `Authorization: Atypon <token>`; timestamp-bound, regenerate per run
- endpoint `https://files.atypon.com/` — or `https://files-test.literatumonline.com/` when `backstage/files.atypon.com/dev-mode=true`; bucket = product name
- upload = **tus**; live `OPTIONS https://files.atypon.com/amps/` (2026-09-23) → `tus-resumable: 1.0.0`, `tus-extension: creation,creation-with-upload,termination`. `creation-with-upload` means an upload can be one POST; failures resume rather than restart
- other ops = POST to the **file** URL with `Atypon-Method: META | LOCK | UNLOCK | DELETE | METRICS | TASK | TASK-STATUS` + JSON body; 200 = ok. `METRICS` targets the **bucket** URL and is the cheap read-only auth probe
- `isReadOnly()` is **client-side** (non-prod without `master-mode`): a raw token from a laptop has no such guard — uploads, LOCK and DELETE are all real. Never test `DELETE`
- **LOCK = "can never be deleted."** The bucket runs a cleanup job (`METRICS` returns `last_cleanup`) and the platform locks a file only once content references it (`LiteratumSubmissionAttachmentService.java:51`). For the 12-month obligation either LOCK explicitly or get AMPS to confirm the JATS deposit does it
- GraphQL `{ filesService { endpoint token isEnabled } }` (`AtyponFilesSchemaExtension.java`) hands an authorised front-end a ready `Atypon <token>` — an alternative to holding the secret
- admin page `publish/src/web/admin/atyponfiles/debug.jsp` → enabled / read-only / object count / disk usage / last cleanup + File Metadata lookup (`/action/atyponFiles`, `do=meta`). Lookup only, no upload form

## Runbook (the scripts cover phase 2 only)

**0. Prep.** Export tab `migration_ready` to CSV (`event_id, session_id, video_asset_url_bizzabo_old`). Move scripts out of `~/Downloads` (or `.cjs`), `npm i tus-js-client`, put the secret in `token_generator.sh` **quoted**, then probe:

```bash
TOKEN=$(bash token_generator.sh | tr -d '\n')
curl -s -X POST 'https://files.atypon.com/amps/' -H "Authorization: Atypon $TOKEN" \
  -H 'Atypon-Method: METRICS' -H 'Content-Type: application/json' -d '{}'
```
JSON with `objects_count` = good. `Authorization failed` = wrong/rotated secret; stop.

**1. Download first, everything, before any upload** — the vendor deadline is the only irreversible one. Name each file `<event_id>+<session_id>.mp4`; that name is the *only* link between a sheet row and the server-minted random id. Pace requests, then validate: 37 files, non-zero, `file *.mp4 | grep -v 'ISO Media'` to catch HTML error pages saved with a 200.

**2. Upload.** Fresh token pasted in, then one invocation per file; collect `files.csv`. Regenerate the token if the run is long or 403s appear; re-run failures (tus resumes).

**3. Verify + protect.** Per URL: `META` (and/or HEAD) with size matching the local file, then `LOCK`. Expect 38 lines in `files.csv` (header + 37).

**4. Hand back.** Parse `session_id` out of each filename, write the URL into `video_asset_urls_new` on that row, confirm all 37 populated, re-attach the xlsx to 457 and comment with counts, failures and whether files were locked. Leo then publishes into Focus 1.0 via Direct Publishing — the URL lands as `<media mimetype="video" mime-subtype="mp4" xlink:href="https://files.atypon.com/amps/…">`, same shape as the 623 live ones. Spot-check a published page plays.

## Where the answers are NOT (verified negatives, 2026-09-23)

- `locate` DB (9.36M names, built 2026-09-13) + live `find` over all of `$HOME` incl. `node_modules`: no `token_generator*` / `upload.js` before the user extracted the zip
- git index and full `--all` history of `literatum-git`, `platform-tools`, `developer_productivity`: nothing
- Confluence site-wide: no page documents the upload procedure; no matching attachments
- Wiley Jira: AIDAFOCUS-457 is the only issue with "Events Migration" in the summary; its own comment is the only mention of either script. Every other Bizzabo ticket (BQM/DAI/RMDA/ECDP/SSPSAP) is registration-data/pipeline work
- Jira/Confluence **text** search is fuzzy token matching — quoted dotted strings like `"files.atypon.com"` match nothing useful. Use `summary ~`, `project =`, `space =` or CQL `type = attachment` instead
- The Rovo `search` tool and reading tokens out of local scripts are both **blocked by the auto-mode classifier** (credential exploration). Hand those over as commands

## Mistakes made once — don't repeat

- **Framed it as Focus 2.0/emdash work.** the user corrected it; the code proves it's AMPS. Check which platform a Focus ticket belongs to (Literatum DOI URLs vs emdash CMS) before assuming the repo is involved.
- **Assumed the repo props secret was the live one.** `amps.props.xml` in a release worktree differs from what the working scripts carry. Registry values in a branch are not prod; verify with a `METRICS` probe.
- Recommended `base64` for the token without `-w0` — fine here (60 chars, no wrap) but add `-w0` for anything longer.
- A `find -iname '*deh*'` matched `<user>` and buried the real results. Anchor loose globs.
