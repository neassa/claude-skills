---
name: focus-content-export
description: Use when working on AIDAFOCUS-362 or any Focus 1.0 content export/migration task — organizing deposit-zip exports, extracting article metadata from JATS XMLs, building FOCUS Content Mapping Template sheets (v3 xlsx), DOI lists per content type, AMPS subject-code hierarchy, sponsors taxonomy, regional access rules, or when asked about the AIDAFOCUS-362-* directories in ~/Downloads.
---

# Focus 1.0 content export & mapping (AIDAFOCUS-362)

**Starting a side task on the import? Read `focus-import-handoff` first** (current state, rules, commands, open items).
This skill is the history and the older gotchas.

Pipeline built 2026-09-01..03 for the Focus 1.0 → 2.0 content migration. Facts verified then; re-verify dirs still exist before relying on paths.

## Directory map (~/Downloads, six dirs — do NOT modify 1–2, outputs go in new dirs)

| Dir | What |
|---|---|
| `AIDAFOCUS-362.tar.gz` + `AIDAFOCUS-362-organized/` | raw export (1.4GB) + zips organized as `2026-09-01/<type>/{production,staging}/` with per-env DOI lists; also `AIDAFOCUS-362-organized.tar.gz` |
| `AIDAFOCUS-362-metadata/` | extracted article XMLs (`xml/<type>/<env>/`), metadata CSVs, **`generate_metadata.py`** (the reusable script; `--help` works), README.md |
| `AIDAFOCUS-362-subjects/` | hand-authored `subject_hierarchy_mapping.csv` (SUPERSEDED by tree-map, see below), `build_hierarchy.py`, `subjects_long.csv`, `anomalies.txt` |
| `AIDAFOCUS-362-mapping/` | **`build_mapping_sheets.py`** → one v3-template xlsx per content type |
| `AIDAFOCUS-362-test/` | throwaway verification run |

## The corpus (this export)

1108 DOIs = 1060 production + 48 staging. Key Opinion 305/18, Expert Perspective 80/15, Whitepaper 6/11, Curated Collection 44/3, Webinar 625/1. One DOI (`ko.10000058`) exists in both envs. DOI prefix = content type (`10.5555/ko.*`). Infographic/Podcast types exist in the template list but not in this export.

## Scripts (run in this order)

```bash
python3 ~/Downloads/AIDAFOCUS-362-metadata/generate_metadata.py <xml_dir> [out_dir]  # CSVs
python3 ~/Downloads/AIDAFOCUS-362-subjects/build_hierarchy.py                        # hierarchy CSVs
python3 ~/Downloads/AIDAFOCUS-362-mapping/build_mapping_sheets.py                    # v3 xlsx sheets
```

All idempotent, read-only on XMLs, stock python3 + openpyxl (2.6.4 installed).

## Mapping-sheet (v3 template) conventions — match these exactly

- Template: `~/Downloads/keyopinion_FOCUS_Content_Mapping_Template_v3_filled-09022026.xlsx`. Rows: 1 banner, 2 headers, 3 EXAMPLE, data from 4. Cols A–R engineering, S–X gold (Samara fills, leave blank).
- **Dates (E/F)**: epub → pub → accepted fallback; E is a real date cell; `date_source` in F.
- **Subject chains (H/I)**: full path per assigned code from `~/Downloads/amps-subject-codes_tree-map.tsv` (`code \t code-path \t label \t label-path`); `;` inside a chain, `,` between chains (`health;md;md60,health;md;mdc0`).
- **Regional access (J/K)**: `<license specific-use="regional-access">` → `<named-content content-type="permitted-location|prohibited-location" vocab="ISO-3166-2" vocab-term="XX">`.
- **Sponsors (N/O)**: code → display name via `~/Downloads/taxonomy_sponsors_*.txt` (`code \t primary-en \t a \t Name` lines).
- Webinar sheet adds 4 cols between R and gold: Event Start/End Date, Partner code/name.
- CSV separators (agreed): comma for tags/subject-codes/sponsors/partners; `; ` for authors and subject_labels (those contain literal commas — "Dr Guy Pratt, Consultant Haematologist", "Tissue, Cell, and Genetic Engineering").

## Data quirks (real, verified — will recur in future exports)

- **678/1108 articles have NO date in deposit XML** (webinars: 623/626). Live pages may have dates the deposit lacks — check `https://focus.wiley.com/doi/xml/<doi>` before claiming missing.
- **Webinar subject codes are label-less** (bare `LS32`) and **webinar sponsors are code-less** (`<compound-subject-part content-type="label">Agilent</...>` only) — resolve both via taxonomy lookups; 188 sponsor labels (Wiley, COMSOL, TESCAN…) have no taxonomy match.
- Non-KO regional-access licenses are free-text stubs ("This is Key Opinion is not available in") with no named-content → correctly empty, flag in Notes.
- Malformed subject entry `,health` on staging `ko.10000133`; codes `ee24, hs06, mddg0, mddp0` missing from tree-map.
- One XML uses undeclared `&reg;` — parse with an HTML-entity fallback (both scripts have it).
- **The official tree-map contradicts intuition**: `ch` is under `life` (Life Sciences & Chemistry), `eg` under `hum`, `be`/`ss` under `pseng`. Never hand-infer hierarchy; always use the tree-map.
- xml:lang present on only 656/1108; v3 sheet language column is xml:lang + stopword detection (de/it/es/fr/pl + CJK check in build_mapping_sheets.py).

## Mistakes made once — don't repeat

- Splitting joined cells on `', '` after a blind separator replace corrupted values containing literal commas. **Regenerate from source XML instead of transforming transformed CSVs**; when splitting comma-joined subject cells use `re.split(r",(?! )", s)` (separator commas never precede a space; embedded ones always do).
- A code-pattern lookahead regex (`[A-Za-z]{2}[A-Za-z0-9]{0,3}`) silently dropped 6-char codes like `health` — count outputs against a known total after every splitter change.
- Saved scripts drifted from inline one-off fixes; fold every accepted format change back into the script and rerun it end-to-end before calling done.

## Import pipeline into EmDash (built 2026-09-16) -- `~/Downloads/AIDAFOCUS-362-import/`

`jats2seed.py` (zips -> EmDash seed JSON, read-only on the export) + `load-seed.mjs` (stages media into
`custom/sites/focus/.emdash/uploads/` + `media` rows, then emdash `applySeed`, then back-dates `published_at`).
README.md there has the exact commands; MAPPING.md has the field-by-field mapping and gaps. Verified end to end
on worktree `aida-emdash-import` (origin/poc @ cf17a0d4) + DB `focus_import_362`: 1109 entries, 182 bylines,
1582 media, pages render on medicine.localhost / science.localhost.

Facts that shaped the design (all verified in code):
- Type mapping: KO -> `key_opinion` (only type with real body); Expert Perspective -> `expert_insight`, Whitepaper -> `whitepaper`,
  Curated Collection -> `article_collection` (all three are PDF landing pages with NO body: teaser goes to `download_description`);
  Webinar -> `webinars` (`video_source=url`, `video_url` from `body//media`).
- **Webinar videos are the only files.atypon.com references in the whole export** (verified 2026-09-23 by scanning every
  XML member of all 1108 zips, manifests and issue-files included): 623 of 626 webinar deposits carry exactly one
  `<media mimetype="video" mime-subtype="mp4" xlink:href="https://files.atypon.com/amps/<32-hex>" xlink:show="embed"/>`
  in `<body>`; all 623 URLs are distinct and extensionless (the hex is the asset id, no `.mp4`). No other content type,
  and no manifest, mentions the host. The 3 without a video: `webinars.10000247`, `webinars.10000235` (production),
  `webinars.10000240` ("Event 21042026", staging). Inventory: `~/Downloads/AIDAFOCUS-362-atypon/webinar-atypon-media.csv`.
  Those URLs live on the AMPS (Literatum) file bucket, not on anything emdash owns — for how they get there,
  the upload scripts and the LOCK/retention question see skill `amps-webinar-video-hosting` (AIDAFOCUS-457 / AMPS-87).
- `applySeed` is the bulk path (bypasses publish-readiness gates, atomic entry+bylines+taxonomies, publishes with live revision)
  BUT it stamps `published_at = now` -> post-pass `UPDATE ec_<coll> SET published_at=...`. Unknown taxonomy term slugs are
  silently skipped -> pre-check against `taxonomies` and report. `$media` URL downloads are SSRF-blocked for localhost ->
  stage files + rows yourself and put `MediaValue {provider:'local', id, meta:{storageKey}}` in the data.
- Site routing = `specialty_methodology` root term (`medicine`/`science`, root counts). Deposit has no site marker: classify AMPS
  codes by tree-map top (`health` -> medicine); code-less Key Opinions default to medicine.
- AMPS codes -> `wol_taxonomy` (904 terms, leaf codes as slugs); 32 corpus codes have no term (parents + a few leaves).
- Body is Portable Text; site blocks: `inlineMedia {mediaType image|videoUrl, image: MediaValue, videoUrl, alt (required), caption}`.
- Main PDF is `<artdir>/<doi-suffix>.pdf` by convention; `self-uri` hrefs are broken for 271/281 EP+CC.
- `unzip -p` cannot match non-ASCII member names (’, ö, ×) -> extract via python zipfile.
- Focus site build needs `packages/plugin-types` etc. built; the root `pnpm build` hangs on `packages/plugins/sandboxed-test`
  (kill it; custom/packages are consumed from src, no build needed).
- "Links / URLs" for exported items = the ORIGINAL `https://focus.wiley.com/doi/<doi>` pages (the `url` column of
  `AIDAFOCUS-362-metadata/metadata_all.csv`, staging rows use the same host), not the local emdash URLs. Zip -> original URL
  table: `AIDAFOCUS-362-import/out/zip-original-urls.{csv,md}` (join entries.csv zip->doi->metadata url).

## The shareable import tool (`~/Downloads/focus-1.0-import-tool/`, archive `focus-1.0-import-tool-<date>.tar.gz`)
- One entry point `./focus-import help`: `convert` (`--title-suffix " - Test"`, `--all`), `dry-run` / `load` (`--slugs`,
  `--on-conflict update`, `--no-media`, `--media-dir`), `check`, `videos`, `quality`, `urlmap`, `workbook`, `checks --zips`.
  Usage guide `docs/focus-import-usage.html` (rebuild `python3 docs/build-html.py`). Keep it in sync: after changing any
  script in `AIDAFOCUS-362-import/`, copy it into the tool and repack.
- POC through the tunnel script (docs, help and README default to IAM + Developer): `focus-node-db-iam.sh --profile …Developer --exec ~/Downloads/focus-1.0-import-tool/focus-import load ...`
  (`--exec` runs any command with the PG* env set).
  Two proven routes (2026-09-29): secret script + Admin profile connects as `focus_app` (every POC load ran this way);
  `focus-node-db-iam.sh --profile …AWSNonProdASTechDeveloper --exec …focus-import dry-run …` connects as `focus_admin`,
  and both the dry run and a real load (20 updated, 91 media reused, notReused empty) passed. QA (`--ro`) cannot load.
  **But the FULL import must use `focus-node-db.sh` + Admin (`focus_app`)**: the IAM token is minted once at start
  (15 min), the loader's pg pool drops idle clients and reconnects with the expired token, so a 15-30 min run dies
  halfway (reasoning in `~/Downloads/projects/focus-362-import-process/focus-362-poc-import.md`; house rule: content
  written by `focus_app`). I told Laith "IAM recommended" for everything before re-reading that doc — check the older
  docs before generalising a route from a short test. Guide now has A (few entries, IAM, `--no-media`), B (full:
  Admin, `--media-dir out/poc-media`, then `aws s3 cp` to `s3://focus-poc-node-nonprod-media-a37eab19/` root) and
  Rollback (`rollback-sql.py`, shipped in the tool; verified on the local main schema in a ROLLBACK'd transaction: 20
  entries + 165 media rows removed, 0 left). Full dry run locally: 900 entries / 121 bylines, 27 s, writes no files.
  Slug lists ship in `reference/slugs/` (sample-slugs.txt, sample-urls.txt, full-slugs.txt = 900, full-slugs.csv). docs/build-html.py now handles `####` headings.
- Shareable archive = tool + full export: `~/Downloads/focus-1.0-import-tool-export-<export date>.tar.gz` (1.3 GB, 1108 zips,
  `export/2026-09-01/` inside; locally a symlink to `AIDAFOCUS-362-organized/2026-09-01`, so pack with `tar -h`). Guide paths
  assume it is unpacked in `~/Downloads`. Guide section "Loading into POC, Dev or UAT": A samples (IAM), B full on POC
  (Admin), C Dev/UAT (`PGDATABASE=focus_dev|uat`; Admin script also needs `DBURL_ARN` = that env's
  `focus-<env>-node-nonprod/app/database-url-XXXXXX`; Dev/UAT start with no media, so never `--no-media` there).
  Dev/UAT commands are written, not yet run.
- **Tunnel speed, measured on the first full POC load**: media rows 3 min, 132 new KOs ~21 min, 81 EIs ~7 min, so
  900 entries is over an hour through the tunnel, not the 15-30 min the old doc estimated. POC also holds ~43k
  `loadtest-w-*` + ~2k/type `*-sample-*` entries (Aug load test); none collide with our slugs.
- **Media reuse gotcha**: without `--no-media`, the loader reuses a media row only if the FILE is also in the local
  `--media-dir` (existsSync). A fresh empty folder on an S3 target re-stages everything (the samples' 91 got new keys
  -> broken until the folder is uploaded). New flag `--reuse-target-media` trusts the DB row (filename+size).
- **`focus-import-fast.sh`** (tool folder, Laith allowed it after the classifier blocked it as "remote shell
  writes"): esbuild-bundles load-seed.mjs (static-import transform of the createRequire block, hard-fails if it
  changes), caches the export tar in `s3://…poc…/ops-tmp/focus-export/<name>-<count>-<bytes>.tar`, pass 1 = SSM on
  the jump host runs the loader with an IAM token for the env's migrator user, result tar back via presigned PUT;
  pass 2 = per-file presigned PUTs (signed locally by `s3-presign.mjs`, SDK from the checkout) so the host uploads
  new media straight to the env bucket; `--resume RUN` retries uploads; `FAST_PGDATABASE`/`FAST_PGSSLMODE` overrides.
  SDK presigned PUTs carry a CRC32 of an empty body by default -> set `requestChecksumCalculation: "WHEN_REQUIRED"`.
  Tested end to end locally with stand-in `aws`/`curl` (fake S3 folder, SSM run locally) on a throwaway DB copy
  (made with the container's own pg_dump; host pg_dump is v14 vs server 17); NOT yet run against AWS.
- **First full POC import done** (tunnel, Admin): 880 created + 20 updated, 103+18 bylines, 266 dated, 828 files
  (985 MB) staged, 129 reused, 0 failed; 1 h 35 min. The follow-up `aws s3 cp` died with ExpiredToken (Admin creds
  pasted before the load had expired) -> fresh creds + `aws s3 sync` (skips uploaded) + `comm` check = 0 missing.
  Chrome check of all 900: 846 published pages 200 with " - Test", 4,280 images all 200; 20 KO 403 = regional
  "allow" rule (expected); 34 drafts hidden. Sciences host answers not-found with HTTP 200 (soft 404, body "couldn't
  be found"), Medicine with 404; check the body, not only the status. Without cookies every fetch = Cloudflare 403.
- **"Partly imported" rows of the 1.0->2.0 check file mostly lose nothing.** `floats-group` always holds exactly the
  one main picture (imported); `back/fn-group` is only the financial-disclosure note (imported) except ko.10000043
  (`fn-type="con"`, contributor note, dropped). Real losses: EI/WP body pictures (WP 15 articles, EI 5 small linked
  pictures + 1 embedded video in expert-perspective.2421). Per-article list: `build-partial-sheet.py` ->
  `FOCUS partly imported and malformed <date>.xlsx`. Its EI small-picture count (5) differs from the check file's 4;
  cause not found yet (not the content-type attribute).
- **Never carry meaning in colour alone in a sheet for Laith's readers.** I greyed the "nothing lost" rows; he read
  grey vs black as "partly imported vs malformed". Use labelled columns instead (here: "Status in the check file" =
  Partly imported / Malformed, and "Anything left out?" = Yes / No).
- **Describe, don't judge, in per-article cells.** Laith rejected "Nothing is missing." Write what the article has and
  what Focus 2.0 does with it, short: "The only footnote is the sponsor statement. Focus 2.0 shows it as the sponsor
  statement." / "The article has 2 pictures in its text. Focus 2.0 does not show them." Column: "What happens on Focus 2.0".
  And always show the evidence: a "What it is in Focus 1.0 (from the XML)" column with the actual footnote text /
  file names / video URL / code, and the exact element (`back/fn-group/fn[@fn-type='financial-disclosure']`, not
  `back/fn-group`). He asked "what sponsor? what is the element?" when the row only summarised.
  No Yes/No verdict column either ("Anything left out?"): a keyword test on my own wording mislabelled rows twice
  ("footnote" contains "not"; "shows neither"), and he called it wrong feedback. The description column carries it.
- **Check how the page SHOWS it, not only that it was imported.** Main-picture frames on POC (desktop, object-fit
  cover, centred): KO 843x420 (wide 2:1), EI and WP 410x580 (tall). So KO main pictures lose ~36% of height, EI/WP wide
  pictures lose up to 84-88% of width (whitepaper-10000074: 1500x500 -> 76% cut). build-partial-sheet.py writes the cut
  per picture (FRAME table; PIL reads the size from the zip).
- **15 Expert Insights have NO main picture on Focus 2.0**: the XML names `secure_file.jpeg`/`.png` but the zip holds
  `secure_file.jpg` (other file ending); the converter matches the exact name (case-insensitively) and gives up.
  curated-collection.165519's picture is only a `.txt` placeholder. Converter fix to offer: match by name without ending.
  Use the seed (`hero_image`/`card_image`) as truth for "shows", never the XML alone.
- **Focus 1.0 footnote visibility (all 153 articles with a footnote, checked twice):** raw-HTML fetch (mine) and a
  rendered-page agent agreed on 151/153; the 2 differences (ko.10000095, ko.10000106) were text present in the HTML but
  hidden (`section.core-funding` display:none) -> trust the RENDERED check. Result: 51 visible (49 under "DISCLOSURE",
  ko.10000043 under "Footnote", EP 2421 in body), 72 not visible (70 Expert Perspectives + 2 KO), 2 empty, ko.10000105
  geo-restricted, 27 staging = 404. Focus 1.0 EP pages do not show the sponsorship footnote; Focus 2.0 does.
  Results: `reference/focus1-footnote-check.json`; sheet column "Shown on the Focus 1.0 page?". Checked signed in.
- **focus-import-fast.sh on POC (first real try 2026-10-05):** the SSM jump host has ~871 MB free in /tmp, the full mode needs ~4 GB (export tar 1.3 GB unpacked + media) and stops at its disk check. `--no-media` (all files already in the bucket) now skips the export and needs ~200 MB. Default profile is Admin. A real media-staging run needs more host disk (infra) or a slimmer export.
- **`--no-media` matched by file NAME only until 2026-10-05: on poc it pointed every `secure_file.jpg` main picture at ONE file** (my fast-script validation run). Fixed: jats2seed writes `size` into every $focusMedia, load-seed reuses on name+size (TIFF: name must be unique). Never recommend a `--no-media` run without the size in the seed. Verify after any load: each file field's media.size == zip member size.
- **Content hash (Laith asked for one):** EmDash uses `media.content_hash = "sha1:<hex>"` (core utils/hash.ts, NOT sha256); jats2seed puts `contentHash` (and `size`) in every $focusMedia except TIFF; load-seed matches by hash first, writes it on new rows, fills it in on older rows matched by name+size. A TIFF re-converted to PNG gives different bytes (ImageMagick timestamp): never write that hash onto an existing row. Check: sha1 of each stored file == its content_hash.
- **Dev/UAT: keep as is with the 10-20 samples (Laith, 2026-10-05).** Only POC gets the full tracker import. Reading dev/uat needs that env's own secret (`DBURL_ARN` + `PGDATABASE`); the POC `focus_app` login has no CONNECT on focus_dev/focus_uat. Each env needs its own sponsor list before a convert.
- **legal_disclosure = `sec[@sec-type="copyright"]` ONLY (Laith, 2026-10-06), all copyright sections merged in body order.** impressum / product-information / notice / prescribing-information stay in the body (links work); notes[disclaimer] no longer feeds it. 12 KOs changed (e.g. ko-146699-2024 "Fachinformation" back in body with its 2 links; ko-145343-2024-1 legal 600->169). Footnotes: every back fn + author-notes fn at the end of the body, heading = own title else "Footnote" (on POC 2026-10-06). Dev/UAT samples: titles " -TEST", own sponsor lists out/{dev,uat}-sponsor-slugs.txt, OUT=out/dev|uat; their media need a tunnel load with --media-dir (73 files not on dev/uat).
- **Content Migration Feedback Tracker** (Confluence AF page 1541079045, Alok) drives the import rules now:
  row 1 sponsorship statement = `notes[notes-type="disclosure"]` ONLY (front or back); row 2 = ONLY the footnote Focus
  1.0 shows at the page end, i.e. `fn-type="con"` (ko.10000043 guest authors) as body section "Footnote" (NOT the
  financial-disclosure fn: that is sponsorship info and is not imported; I wrongly put it in 115 bodies once) -- SUPERSEDED: the converter of 2026-10-07 puts EVERY back/fn-group fn + author-notes fn in the body (see focus-import-handoff); row 13 undated webinars = 2026-01-01 (shown + published). DOI: `<article-id pub-id-type="doi">` -> `doi`
  (AIDAFOCUS-495 #584/#592: CMS only generates for entries created in it; deposit fails without one). load-seed drops
  `doi` for a target without the field (old 4321 DB). Supplementary (row 5) BUILT without site code (Laith: "same as now, but the link the pdf assets link"): each extra
  suppl/ PDF = its own child Expert Insight `<parent>-supplementary-<n>` (pdf_asset = the PDF, hide_from_search, parent's
  taxonomies/date), the parent's "Supplementary material" section links each title to /api/asset/<coll>/<child id>/pdf_asset
  (token __FOCUS_ENTRY_OF__<slug>__ filled by load-seed); a suppl file identical to the parent's pdf_asset links to the
  parent's own route. Only curated-collection.244 (7) + .26080 (6, 1 = own PDF) -> 912 entries. Focus 1.0 suppl links
  (/doi/suppl/...) need a 1.0 sign-in: never link to them. 36-webinar dates zip
  (~/Downloads/webinars_webinars-245.issue-1_36events_withdate_v1.zip) = NEW DOIs, not in the export, dates are
  `pub-date pub-type="ppub"` (converter does not read ppub) -> asked Laith.
- **Revert = the code only.** When Laith says "revert", undo the script change; do NOT also roll back the local DB/site
  he is reviewing unless he says so.
- **Rule (Laith): anything in the rich text (image, video, file) stays in the text.** Downloadable (EI/WP) and webinar
  renderers (`InfographicDetail.astro`, `WebinarDetail.astro`) used a bare `<PortableText>` -> inlineMedia printed an
  error, so jats2seed dropped it. Fix (local, worktree aida-emdash-import-main, uncommitted): register InlineMedia +
  InlineContentCard like ContentDetail.astro; jats2seed keeps the media (`downloadable_media_kept`: EI 6, WP 28).
  Verified locally: WP-10000072 Physics Today logo (shown full column width = upscaled 483->846), EP-2421 Brightcove
  video under "Video Content", EP-164715 picture under its link line. Needs a PR to main before POC.
- WP-10000072 data quirk: XML sponsor code `3d-systems` but footnote "sponsored by HÜBNER Photonics".
- **Inline pictures were enlarged to the column (846 px)** by `InlineMedia.astro` (`inline-size:100%`): 276 of 500 inline
  pictures in 116 articles are narrower (238 KO figures incl. ~150 px author photos shown at 846x1102 on POC; 14 journal
  logos). Focus 1.0 shows natural size. Local fix (uncommitted, same PR as the renderers): images `inline-size:auto;
  max-inline-size:100%` -> verified natural size locally (ko-137938-2024, WP-10000072 483x61).
- **Site PR wiley/aida-emdash #614** (branch AIDAFOCUS-362-inline-media, worktree ~/Downloads/projects/aida-emdash-inline-media,
  from main 3494c117): renderers + natural-size pictures. Copy in tool `site-patches/inline-media-pr614.patch`. On clean
  main `pnpm test` already has 11 failures and `astro check` 84 errors (none in these files); a fresh worktree needs
  root `pnpm build` before the site builds; one site build failed on a transient "fetch failed", then passed twice.
- **POC update from the current tool = 35 EI/WP entries** (KO and webinars identical): 13 safe now
  (`reference/slugs/poc-update-now.txt`: 12 main pictures + EP-10000237 PDF), 22 only after #614 is deployed
  (`poc-update-after-site-deploy.txt`: media in the text, else the page prints the components error).
- **media-check.py** (tool + AIDAFOCUS-362-import; <1 s): every picture/video/PDF the XML names, sorted found /
  other-ending / other-spelling / other-folder / placeholder / missing. Imported articles: 919 refs, 47 not found in 40
  articles. Fixable (file IS there): 16 other-ending (13 main pictures: XML `secure_file.jpeg|png`, zip
  `secure_file.jpg`; 3 in EP-41439 .jpg vs .png), 3 PDFs in another folder (CC-244 prod, EP-10000237/10000103 stag),
  CC-159860: main picture `551148554.jpeg` is truly missing (Laith: not on Focus 1.0 either). `secure_file.jpg` is NOT
  it: the XML uses `secure_file.jpeg` for the KEY IMAGE (abstract-type="key-image"). Never guess a renamed file from
  "the only unused picture"; check every reference first (front matter key image included).
- PDFs "in another folder": CC-244 has NO main PDF, but 7 supplementary PDFs named by `article-meta/self-uri
  content-type="pdf"` (in suppl/). Open question (Laith): include them as the last thing in the body? EP-10000237 and
  EP-10000103 are different: `article-meta/supplementary-material` names the article's own PDF (stored in suppl/).
  Comments live in build-media-report.py COMMENTS -> HTML "Comment" column.
- **Implemented (jats2seed, local only):** `find_member` accepts the same picture name with another picture ending
  when exactly one exists (report: "Pictures found under another file ending"); `main_pdf` also takes
  `<sub>/<article>.pdf` ONLY when named exactly like the article (Laith: never a differently named PDF). Seed diff:
  exactly 15 entries (13 EI card_image, EP-41439 description pictures, EP-10000237 pdf_asset). Loaded + checked
  locally (CC-165320 main picture 2560x1440, EP-41439 3 PNGs). POC needs a reload of those 15 slugs with new media.
  Not recoverable: 18 PDFs absent (13 prod have no PDF on Focus 1.0 either; ko.10000249 HAS one on 1.0 -> export gap),
  CC-16689/39166 PDF placeholder only (no PDF on 1.0 either), CC-165519 all placeholders, EP-10000045 picture missing
  (1.0 says so too). Focus 1.0 serves `assets/secure_file.jpg` for CC-165320, i.e. Literatum resolves the mismatch.
- **Focus 1.0 live XML: `https://focus.wiley.com/doi/xml/<doi>`** (Laith). Behind the same Cloudflare check: a script
  fetch gets 403, but navigating the tab clears it by itself after ~10 s (never click a challenge). CC-165320's live
  XML also says `secure_file.jpeg`, so the mismatch is in Focus 1.0's data, not the export.
  HTML report of the not-found files: `build-media-report.py` -> `~/Downloads/FOCUS missing and misnamed files <date>.html`.
- expert-perspective-2421 on POC: the EI description drops the embedded Brightcove video but keeps its section
  heading, so "Video Content" shows with nothing under it (Focus 1.0 plays the video there). Open: turn it into a link
  line, or drop the empty heading.
- `focus-import check` crawls the LOCAL site only. POC answers every command-line request with 403
  (`cf-mitigated: challenge`, Cloudflare "Just a moment…"), so check POC pages in Chrome (fetch them from a tab on the
  same origin with `javascript_tool`). Never try to get past the challenge. `sitecheck.py` used to treat
  `SITE_BASE=http://127.0.0.1:4321` (the documented form) as a deployed env -> 866 x non-200; fixed: a localhost
  SITE_BASE means local mode. Test the tool from a fresh unpack of the tar, not from the working folder.
- `focus-node-db-iam.sh -c` prints its connection lines (AWS identity, Reusing tunnel, Connecting, Target) to STDOUT, so a
  redirected psql result carries 4 junk lines. Pipe through `grep -E '^[a-z0-9-]+[|].+$'` for sponsor-slugs.txt.
- **The seed must match the schema the target runs** (POC runs `main`). `main`'s #531 (AIDAFOCUS-489) rewrote Native Webinar
  (abstract/body retired -> `video_description`; full-video title+link required) and added a required
  `display_published_date` to Key Opinion; migration 0015 DROPPED the old webinar columns on POC. Before a load, diff the
  target's field list against the seed (unknown fields / missing required).
- `--on-conflict update` rewrites only the fields the seed carries; fields it no longer writes (Partner) keep whatever
  testers typed. `--no-media` reuses the target's media by filename (`notReused` in load-report.json must be empty).
- Expert Insight / Whitepaper descriptions render NO media: pictures AND videos in their body are dropped (3 EI videos).
  Only Key Opinions get authors and references.

## Deliverables in Laith's name (sheets, docs, the shareable tool)
- **He edits the sheets directly, often with the file still open in LibreOffice.** Before rebuilding ANY sheet: look for
  `~/Downloads/.~lock.<file>#` and `~/.config/libreoffice/4/user/backup/<file>_0.ods` (his unsaved edits), run
  `AIDAFOCUS-362-import/sheet-diff.py <generated>.xlsx <his copy>`, and put every change into the generator first; log it in
  `AIDAFOCUS-362-import/SHEET-EDITS.md`. After a rebuild, tell him to close his open copy WITHOUT saving. (Nearly overwrote
  his comments twice.) A LibreOffice fill-down can increment values in his edits (ko.10000056 -> 57, 58): check for it.
- **Each per-type tab describes only its own content type** (his edit: "Image blocks in the body." instead of a
  Key-Opinion-and-Expert-Insight sentence). XML_RULES targets/status can be a dict per collection.
- **ALL the deliverables are for business readers** (checks, not-imported, field mapping, data quality, URL map): technical
  names go in last columns marked "(for developers)"; scan business columns for jargon + other type names before handing over.
- **The check sheets are for business readers**: "Goes to" in plain, short words ("Pictures in the article."), no field
  names or XML terms; each tab mentions ONLY its own content type (no "webinar" on the Key Opinion tab and vice versa);
  status labels imported / partly imported / not imported / not needed. Scan each build for other type names per tab.
- **One row per mapping** in the check sheets: fold children and attribute variants that map the same way ("Also covers").
- **No dates in the notes, Read me lines or code comments** — no "(decision 2026-09-29)", "Generated <date>", "(Laith 2026-09-28)". Data dates stay (published dates, the `2026-09-01` export folder, the `2020-01-01` placeholder). File names may carry the build date.
- Decisions recorded so far (no dates): `<kwd-group>` is not imported (tags come from the AMPS codes); staging items keep their slug and load as drafts; image-only links follow 1.0 (plain H2 + separate link line); knowledge-hub hrefs are left as in 1.0.

## UAT sample load (one richest real item per 1.0 type)

UAT holds ONLY real Focus 1.0 content, titles suffixed ` -TEST` (Laith's rule: no `[AUTO]` fixtures, no invented samples).
Picked by scoring the converted seed (filled schema fields, authors, inline figures, tags, sponsor, PDF, hero, date):
`ko-10000223` (9 authors, 11 figures, Recordati), `expert-perspective-158073` (Merck), `curated-collection-74076`
(Sartorius, -> expert_insight), `whitepaper-10000075` (3D Systems, 9 tags), `webinars-1230492` (atypon video, Merck; no
date -> placeholder). Only 5 of the 20 2.0 types exist in the export; the rest have no 1.0 content. Only ONE webinar has
a real date (`webinars-10000235`) and its video is an ON24 registration page, not playable.
- Loaded on UAT and Dev (Dev: `OUT=out/dev`, `LOCAL_PORT=5437`, bucket `focus-dev-node-nonprod-media-939fd5ba`, one chained `dry-run && load`; with the dates fix the load back-dates all 4 itself, no `--dates-only`).
- Separate `OUT=out/uat` so POC's `out/` stays intact; `--repo` = a detached `origin/main` build worktree.
- UAT route that worked: `OUT=... DBURL_ARN=focus-uat-node-nonprod/app/database-url PGDATABASE=focus_uat LOCAL_PORT=5438
  focus-node-db.sh --profile ...Admin --exec focus-import load ... --slugs a,b --media-dir out/uat-media`, then
  `aws s3 cp out/uat-media s3://focus-uat-node-nonprod-media-a0d7c561/ --recursive`. Pass the secret NAME (list-secrets
  `| [0]` paginates into `None\n<arn>`). Writes as `focus_uat_app`.
- **Converter drift fixed:** main's AIDAFOCUS-489 (#593, migration 0018) retired webinar `video_placeholder` +
  `topic_tags`; jats2seed still wrote `video_placeholder` -> removed. Diff the seed against the target schema before any load.
- **dates.json bug fixed:** dates used `TYPE_DIR_TO_COLLECTION[type_dir]`, content used the remapped `row["collection"]`, so
  every Curated Collection (-> expert_insight) and the 4 EP -> key_opinion rows were never back-dated ("1 not found"; kept
  the import-day date). Now `row["collection"]`. POC's earlier loads likely carry the same wrong dates — re-run
  `load --dates-only` there after a fresh convert. `--dates-only` re-parses the whole seed but writes only published_at.
- **Date rule (Laith, replaces the old 5-step chain): `<pub-date pub-type="epub">` -> `<history><date date-type="epub">` ->
  `<history><date date-type="accepted">` -> default, for EVERY type, webinars included.** `date-type="pub"`, other pub-dates and
  `date-type="start-date"/"end-date"` are no longer read (`event_dates()` removed; "event date" was our label, not the XML's).
  Result on the 900: 207 / 15 / 44 / 634 none (623 webinars + 11 KOs). 8 items moved 1-2 days (were date-type=pub);
  webinars.10000247 broadcast 2026-08-25 -> 2026-08-13. Default: display/broadcast 2020-01-01, published_at = import day.
  Webinar issue XML `<pub-date pub-type="ppub">` = 2026-06-05 on 623 (bulk upload), not used. Page for business:
  `~/Downloads/Focus 1.0 content dates <date>.html`.
- **Converter changed elsewhere (19:01, both copies identical): undated webinars now get `published_at` 2026-01-01 (`WEBINAR_FALLBACK_DATE`, tracker row 13), and supplementary PDFs (`self-uri content-type="pdf"` whose file is in `suppl/`) become a "Supplementary material" body section plus hidden child entries `<slug>-supplementary-N` (own `pdf_asset`, hide_from_search). Only `curated-collection-244` (7) and `curated-collection-26080` (5) have them; all 14 rows are live on POC. `<supplementary-material>` in front/article-meta (5 production KOs) is NOT used. Re-read jats2seed.py before describing date or supplement behaviour.
- `build-mapping-workbook.py` / `build-mapping-checks.py` still mention `video_placeholder` / `topic_tags` rows (harmless; they
  build from the live schema) — clean when next touched.

## Old-vs-new content comparison (2026-09-16, `AIDAFOCUS-362-import/compare.py`)
- **Reproduce 1.0's structure, don't improve it** (Laith, 2026-09-28, corrected twice in one exchange): a reviewer's
  "not linked on new" meant *make it look like prod*, not *make it work better*. I first merged the heading into a working
  PDF link, then made the H2 itself the link — both rejected ("same style as in prod"). What 1.0 renders for
  `<sec><title>…</title><p><ext-link><inline-graphic/></ext-link></p></sec>`: a plain H2, then its own paragraph whose
  link text is `Image (<file>) is missing or otherwise invalid.` when the graphic is not in the deposit (Literatum's
  `core-auxdata-missing`), with the ORIGINAL href. jats2seed now does exactly that. Link targets/redirects (knowledge-hub
  URLs bouncing back to 1.0) are a separate ticket — keep the 1.0 href unless told otherwise. Before changing how a
  section renders, read the 1.0 DOM in his Chrome (heading tag, whether it is a link, the next element) and copy it.
- **Look at a 1.0 page in Laith's Chrome (Claude in Chrome), not Playwright** (2026-09-28): an anonymous browser only gets the
  abstract + "Register & Access the article"; the full text (body sections, in-body links, sponsor text) needs his logged-in
  session. Example: on `expert-perspective.10000045` the "Click to download the webinar digest PDF now." H2 is followed by
  "Image (….jpg) is missing or otherwise invalid." — the link is on that missing image and goes to the knowledge hub,
  which now redirects back to the same 1.0 page, so 1.0 itself has no working digest link. Keep the pace rule below.
- Live side: `gen-pw-batches.py` writes Playwright-MCP harness files (`~/Downloads/projects/.playwright-mcp/live-batch-*.pw.js`);
  each fetches pages same-origin in the focus.wiley.com tab (Cloudflare-cleared), extracts `#bodymatter`, `#abstracts`,
  `.core-authors`, `.core-date-published`, `.amps-disclosure/.amps-sponsorship`, `#bibliography`, `.figure`, `.btn--pdf` and
  saves JSON via `download.saveAs` (the MCP vm has no fs). PACE: <= 1 page / 5 s or the IP gets blocked (see memory).
- Local side + scoring: `compare.py` (bs4) -> `out/compare/compare.{csv,md}`, `diffs/`, `dates-live.json`
  (apply with `load-seed.mjs --dates-only --dates out/compare/dates-live.json`).
- Findings on 102 KOs: titles need `article-title: subtitle`; the deposit lacks the live "Plain language summary" (88/97),
  the live sponsor statement (40/97) and some figures entirely (e.g. ko.10000123 has 2 live figures, zero <fig> in XML);
  20 KOs have live dates the XML lacks; `history[accepted]` is NOT the display date.
- Site gotcha: `inlineMedia.image` / `videoFile` in Portable Text are asset URL STRINGS (`/_emdash/api/media/file/<key>`),
  not MediaValue objects -- objects render nothing (resolveInlineMedia -> null).
- amps-stag.literatumonline.com = the old site's staging: no Cloudflare challenge, production DOIs resolve, the "staging" deposit
  zips are NOT there (404). Downloadables/webinars are registration-gated (403/"Register & Access" for anonymous); the user's
  Connect-logged-in Chrome sees everything -> extract with claude-in-chrome JS and pull data out via navigator.clipboard.writeText
  (needs a click for focus) + `xclip -o`, because JS tool output is truncated at ~1 KB and the tab cannot reach 127.0.0.1 (PNA).
- Digital Publication `download_description` renderer has NO inlineMedia block -> strip images there (jats2seed does).
- Portable Text marks in emdash core are `strong`, `em`, `superscript`, `subscript`, `underline`, `strike-through`, `link` (not sup/sub).
  JATS is pretty-printed: collapse text-node whitespace or every indentation newline shows up in the rendered page.
- Local viewing gotchas the user hit: bare http://localhost:4321 is 404 (host-routed: medicine.localhost / science.localhost);
- Crawling local pages from POC URLs: map the host `sciences-focus-poc…` to `science.localhost` (not `sciences.localhost`), or every Sciences page returns not-found and the check finds nothing. Drafts also answer HTTP 200 with a "Page not found" title, so check the `<title>`, not the status. In the HTML the error reads `is missing &quot;inlineMedia&quot;`.
- That error sits in a `<div style="display:none" data-portabletext-unknown="type">`: readers see NOTHING, the picture is silently dropped. Do not tell Laith the page "shows an error line" (said wrongly once). Check visibility in Chrome before describing what a reader sees.
- Focus 1.0 STAGING articles (404 on focus.wiley.com): https://staging.focus.wiley.com/doi/<doi> and /doi/xml/<doi> work in Laith's Chrome (logged in). amps-stag.literatumonline.com redirects to focus.wiley.com (404).
- KO dates missing in the XML (11 KOs): `reference/dates-from-focus1.csv` (doi,date,source) = dates Laith read off Focus 1.0; jats2seed `--date-overrides` (wrapper passes it) uses it ONLY when the XML has no epub/accepted date. ko.10000105 + ko.10000056 geo-blocked: no date -> 2026-01-01 like every undated item (Laith changed the fallback for all types; was 1 Jan 2020). Never bypass the regional rule to read a date.
  the admin + media library need first-run setup at /_emdash/admin/setup (fresh DB has 0 users); body figures are loading="lazy".
- `sitecheck.py` = full crawl of the local site (pages + every media URL + stored-vs-rendered checks). Broken images that are
  NOT ours: seed sponsor logos (`01KSD8PA…png`) and the seed sample card (`01M0YSS5…jpg`) -- those keys 404 on the poc site too.
  TIFF figures -> loader converts to PNG with ImageMagick. "undefined" grep is a false positive in medical prose.
- Putting samples on the poc env: runbook `AIDAFOCUS-362-import/POC-SAMPLES.md` (loader `--media-dir` hand-off dir -> `aws s3 cp` to the
  media bucket root; content via `focus-node-db.sh --exec node load-seed.mjs ... --slugs`; rollback via `rollback-sql.py`). All DML +
  S3 uploads, no schema/deploy. AWS steps are the user's to run.
## Verified collection mapping (2026-09-22, counted in the local DB, not read off a doc)

| 1.0 type | 2.0 collection | Site | Count |
|---|---|---|---|
| Key Opinion | `key_opinion` | Medicine | 149 |
| Expert Perspective rows 59-62 (Elena's addendum 2026-09-16) | `key_opinion` | Medicine | 4 |
| Expert Perspective (rest) | `expert_insight` | Sciences | 60 |
| Curated Collection (same addendum; NOT `article_collection`) | `expert_insight` | Sciences | 47 |
| Whitepaper | `whitepaper` | Sciences | 16 |
| Webinar | `webinars` | 576 Sciences / 49 Medicine | 625 |

`article_collection` holds no imported content. The four moved Expert Perspective rows are pinned by DOI in
`EP_ROWS_TO_KEY_OPINION`, not by sheet row number, so a re-export with shifted rows cannot break them.
MAPPING.md said `article_collection` until 2026-09-22 — when a doc and the code disagree, count the rows and fix the doc.

## In-text citations (`<xref ref-type="bibr">`) — three separate bugs, all fixed in jats2seed.py

1. **One element, several targets.** `<xref rid="ref-4 ref-5"><sup>4,5</sup></xref>` is normal in these deposits (13 in
   ko.10000223 alone). Linking it whole sends a reader who clicks "5" to reference 4. `grouped_citation_spans()` splits it
   into one link per number, separators staying plain.
2. **The ids are not in printed order.** `rid="ref-15 ref-16 ref-6"` renders "6,15,16". Pair each number with the reference
   it NAMES, never by position. This was 50 wrong links on 8 articles.
3. **Ranges cannot be split.** `rid="ref-20 ref-21 ref-22 ref-23"` printing "20-23" stays one link to reference 20.

What remains is source data, not conversion: 20 single-target markers whose printed number differs from the reference
position (`<xref rid="ref-2">3</xref>` in ko.10000035/40/41/77/78). Focus 1.0 opens reference 2 for that same click, so the
import is faithful. Citations inside figure captions stay plain text — captions carry no marks.
Audit command: fetch the page, then compare each `<a href="#ref-N">` label with N; 263 links, 21 mismatches, all explained.

## Making the citation numbers clickable needs a site change (tested, 96/96)

`--citation-target item` emits `#ref-N`; the deployed template has no such anchors, so on today's poc build the links would
do nothing. Needs: `id="ref-N"` on each reference `<li>`, `scroll-margin-block-start`, and a re-anchor script with
`behavior: "instant"`. Full measurements and the reasoning live in `driving-playwright-directly`.

## Disclosure lives in `<front>` as often as in `<back>` (found 2026-09-23, cost 87 wrong pages)

Full map of the 6 places sponsorship/disclosure text sits, what reaches 2.0 now, and the re-check script: skill
`focus-import-handoff` ("Sponsorship / financial-disclosure text sits in 6 places").

`<notes notes-type="disclosure">` is a direct child of **`<front>`** on 200 Key Opinions in this export, of `<back>`
on 133, and of both on 17. Reading only `<back>` looked correct on the samples and silently dropped the sponsorship
statement on the rest — ko.144589.2024.1 published "Sponsorship information was not present in the Focus 1.0 deposit"
over a full Sanofi disclosure. `back_notes()` now reads both parents. When a JATS element seems missing, count where it
actually sits across the whole corpus before concluding the deposit lacks it.

**Never publish an explanatory placeholder.** A required field with no source value gets an empty string, and the gap is
listed in a report (`out/disclosure-audit.csv`). An internal note about the deposit on a reader-facing page is worse than
a blank. After the fix: 87 disclosures recovered, 648 genuinely empty (624 of them webinars, whose deposits carry none).

## Sponsor logos (AIDAFOCUS-456) and the build trap that hides all media

The logos live in `~/Downloads/all-media.zip`, already named as the `storageKey` values in
`custom/sites/focus/seed/sponsors.json` — 86 of the 90 keys match a file exactly, so they are a storage copy, not a
CMS re-upload: drop them at the bucket root (or the local uploads dir) and the media route serves them. No media row
and no seed change are required. The 4 that are absent (`actelion`, `agilent`, `alexion`, `anthos-therapeutics`) are
the only `01KSD8MAM*` keys; everything else belongs to a later batch. Sponsor `wolfgang` has an empty logo field.

**`pnpm build` without sourcing `.env` silently disables local media.** `EMDASH_LOCAL_MEDIA` is read at BUILD time, so
a build run in a plain shell makes every `/_emdash/api/media/file/<key>` return 500 `NOT_CONFIGURED` — including images
that worked minutes earlier. It looks exactly like missing files. Always `set -a; source .env; set +a` before `pnpm build`,
and if media suddenly 500s, suspect the last build before suspecting the data.

## A review link list goes stale the moment the mapping changes

2026-09-21 review sheet: 9 of 20 rows were "can't load the new URL" or "this should not be in scope". None was a
content defect. The list posted in AIDAFOCUS-366 on 9/17 was reviewed after the 9/20 sheet-driven remap moved Curated
Collections to `/expert-insight/` and one Expert Perspective to `/key-opinion/`, and after the pre-2021 items were
pruned. The reviewers spent their time on dead links.

**Regenerate and re-post the link list after ANY remap or prune, with the date on it**, and say which items were
deliberately removed. Generate it from the target database, never from an older comment.

## POC contents change — query POC before saying what is (not) there

SUPERSEDED: by early October POC held the FULL import (all 15 checked non-sponsored items present, published; webinars without a date had `published_at` 2026-01-01, not the import day — someone loaded with a different date fallback). I told Laith "only the 20 samples" from a 5-day-old listing; he corrected me. Rule: run the slug query against `focus_poc` (Admin profile) before stating presence. Also `slug ~ '^ko-'` counts the `ko-sample-*` load-test rows (7000+), so it is no measure of the import.

Older note:
## poc held ONLY the 20 sample slugs (late September)

Corrected 2026-09-23: I offered `https://medicine-focus-poc.literatum.com/key-opinion/ko-10000110` as a page to check
a sponsor logo on. That slug exists in the LOCAL database (901 entries); poc only ever received the 20 review samples
in `out/poc-sample-slugs-v2.txt`. Check the slug is in that list (or query the target) before putting a URL in front of
anyone. Sample pages that DO carry a sponsor: ko-10000223 (Recordati), expert-perspective-10000045 (SCIEX),
whitepaper-10000074/75/76 (3D Systems), curated-collection-1202 (Bio-Rad, now under /expert-insight/).

## Three more conversion bugs found from the 9/21 review sheet (fixed 2026-09-23)

1. **Webinars printed "About this webinar" twice** — 609 of 625. `NativeWebinarRoute.astro` ALWAYS renders an
   "About this Webinar" section from the `abstract` field and then appends the body, so leaving that section in the
   body duplicates heading and text. `split_about_section()` moves the prose to `abstract` and leaves the body empty
   (624 now have an empty body, which is correct: the section was their only content).
2. **`<abstract abstract-type="toc">` is the PDF's contents list, not a summary.** Printing it pushed the real summary
   below an outline (expert-perspective.10000089, the only one in the corpus). Skipped alongside `key-image`.
3. **A link whose only content is a picture disappeared** — `<ext-link><inline-graphic/></ext-link>`, 410 in the corpus.
   In downloadable descriptions images are stripped, so the link went with them; the section heading is now used as the
   link text and a heading repeated verbatim by that link is collapsed away. NOT done for Key Opinion bodies: 389 of the
   404 there point at `keyopinions.info` image files, i.e. legacy "click the figure" links worth dropping.

Gotcha that cost a cycle: JATS is pretty-printed, so an "empty" link still yields a whitespace-only span. Test for
`any(span["text"].strip())`, not `len(spans) == before`.

## `--no-media` DELETED images from 921 entries (2026-09-24) — and the load reported success

`load-seed.mjs --no-media` resolved every `{"$focusMedia": ...}` placeholder to `undefined`, and the guard below it
then dropped the whole `inlineMedia` block. An `--on-conflict update --no-media` run therefore STRIPPED the figures
from every entry it touched: 901 local entries and the 20 poc samples. `applySeed` reported `content updated 901`
and exited 0 the whole time. Only the crawl found it, as "figures stored N rendered 0" on 95 pages.

Fixed: with `--no-media` the loader now reuses the media row the target already holds (matched by filename) instead
of discarding the reference. Recovery is a normal re-run WITHOUT the flag — it reuses existing media rows and stages
nothing new (`staged so far: 0`).

**Rules this bought:** a flag that says "skip X" must never delete X; and after ANY bulk content update, run
`sitecheck.py` before believing the exit code. `contentcheck.py` (written 2026-09-25) is the data-side twin: required
fields, placeholder text, reachability, dates, duplication and media references, straight from the database.

## The duplicate tag is 264 entries, not 3 (corrected 2026-09-25)

I reported "3 entries, two subject codes sharing a label, cosmetic". Wrong on scale and on cause: my query had been
scoped to `wol_taxonomy` alone. Across ALL taxonomies it is 264 entries, and the cause is `specialty_methodology`
and `wol_taxonomy` each carrying a term with the same label while the page prints both — Dermatology 60, Analytical
Chemistry 43, Microscopy 39. The fix is a product decision (which taxonomy the tag strip shows, or de-duplicate by
label), not a converter change.

## Deliverables for the content team (2026-09-24/27)

- `~/Downloads/Feedback for Sample Set - engineering response 2026-09-24.xlsx` — their sheet with three columns added
  (Status, Current URL, Engineering response); 8 fixed, 7 not a defect, 3 decisions, 2 open.
- `~/Downloads/FOCUS XML to EmDash field mapping <date>.xlsx` — one tab per content type, every CMS field with the XML
  element that fills it, built by `build-mapping-workbook.py` FROM THE LIVE SCHEMA so it cannot drift. Greys out the
  fields nothing feeds (13 of 35 on Native Webinar) and ends each tab with the non-field parts.

## Team docs (2026-09-22, extended 2026-09-23)

`~/Downloads/projects/focus-362-import-process/` — two self-contained HTML docs plus their Markdown and `build-html.py`:
`focus-362-import-process` (local path: requirements, directory structures, every verified flag, a full manual run from an
empty database, the three mapping layers, timings) and `focus-362-poc-import` (POC/Dev/UAT with no local site or database) and `focus-362-field-mapping`
(field-by-field 1.0->2.0 for the CONTENT team, with the exact XML location per field - this is the answer to
Abdallah's ask in AIDAFOCUS-366 for a complete CMS field mapping).
Rebuild with `python3 build-html.py`. Facts to reuse from them: the loader needs only `pnpm install` +
`pnpm --filter emdash build` (it imports `emdash/seed` from `packages/core/dist`) — no astro build, no `.env`, no local DB;
convert of 1109 deposits takes 2 s, a full validate 26 s, a full load is 901 entries and 1732 media files / 1.4 GB.

- Resuming: read `~/Downloads/AIDAFOCUS-362-import/STATUS.md` first (state of local DB, poc samples, gaps, next steps); the session chat log is `SESSION-CHAT-2026-09-16.md` beside it.

## Webinar harvest from the live 1.0 site (`~/Downloads/AIDAFOCUS-362-webinar-harvest/`)
- The 1.0 sitemap (`/sitemap-index-1.txt` -> `sitemap-1.xml`, `sitemap-2.xml`) lists **646 webinars; the export has 626**.
  37 live webinars are NOT in the export (full live JATS saved in `out/live-xml-not-in-export/`, from `/doi/xml/10.5555/<doi>`,
  which needs Laith signed in). 17 export webinars are not in the sitemap: empty or duplicate shells ("Highlights", "(Duplicated)").
- Signed-in webinar pages show exactly what's in the export XML (title, About text, video, sponsor: 257/257 matched). Page-only extras:
  the AI "Plain language summary" and `.meta-panel__onlineDate`, which is 2026-06-11 (the bulk upload day) on nearly all of them, not a broadcast date.
  Upcoming events carry `const startDate = new Date("…")` in a page script = the XML's `<pub-date date-type="start-date" iso-8601-date>`.
- Tools: `harvest-resume.js` (in-page runner; IndexedDB `whv`, resumes from what it has), `build_sheet.py` (parsers), `build_xlsx.py`
  (workbook from raw/*.json). Cloudflare limits are in memory `focus-wiley-rate-limit`.

## What gates a Focus 1.0 page (read in code: literatum master 0c62d01577, ui-products develop 7f77198e1d)
- The gate is Literatum's normal access control: no licence for the content -> access-denial block. Nothing in the
  deposit switches it on or off; the export carries NO access mark (scanned every manifest, issue and article XML).
- `custom-meta[meta-name='connect-form-id']/meta-value` (field 2316 `amps-connect-form-id`, friendly code `connectFormId`,
  xpath in `product/amps/conf/amps.props.xml`) only picks WHICH unlock button the denial shows: `/action/showLogin?doi=..&connectForm=<id>`
  (`fulltext-options-tmpl.jade`, `header-content-after-tmpl.jade` in ui-products acropolis/amps). Without it the denial
  still shows, with a plain sign-in button (seen live on expert-perspective.10000217, no form id, still asks to sign in).
- After the form is answered, `AmpsGrantLicenseForContentAction` checks the answered form name = the stored id, then adds
  the user to group `EVENT_LICENSE_CONTENT_GROUP_<issue-doi-suffix>` with a PERMANENTLY_FREE licence on the article's ISSUE DOI.
- Event/session pages with a start date do not render the denial block (upcoming events).
- So "how much is gated" can't be counted from the export: which content is free (licences in the Literatum DB / AMPS
  admin) is the real answer. Counting connect-form-id = "has a registration form attached", not "is gated".

## Webinar dates from Leo's "withdate" zips (AIDAFOCUS-366)

- Leo's zips (`webinars_webinars-{243,244,245}*_withdate_*.zip`): 6 files in `~/Downloads` + `Migration_Confluance_Wibnar_Leo/`,
  3 distinct contents (MD5, then line by line). 243 = 573 XMLs, 244 = 52, 245 = the 36 we don't have.
- Their `pub-date[@pub-type="ppub"]` fills 514 of our undated webinars through `reference/dates-from-focus1.csv` (same
  mechanism as the 9 KO dates; `build-webinar-dates-sheet.py` rewrites the webinar rows and keeps the KO rows). 109 have no
  date there either. The converter's date-source label now comes from the file's `source` column.
- Laith: only the date is taken; the 36 new webinars are not imported (kept in `export-extra/`).
- The Focus 1.0 page harvest's online date (2026-06-11 for 163) is when the item went online, NOT the webinar date.
- "Same" needs proof at content level: two DOIs in both 243 and 244 share the date but not the XML. Same title is not the
  same webinar either (our export has 4 copies of some titles, each with its own video).
- `build-webinar-diff-sheet.py` -> `FOCUS webinars ours vs Leo's zips <date>.xlsx` (diff by part, sponsor/body by kind).
  Bug I made there: sponsor code+label joined by a space then split back = 115 false "different sponsor". Keep fields
  separate; open raw examples before reporting a big count.
