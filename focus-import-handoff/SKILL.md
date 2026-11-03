---
name: focus-import-handoff
description: Use when starting any side task on the Focus 1.0 to Focus 2.0 (EmDash) content import (AIDAFOCUS-366, export AIDAFOCUS-362) in a fresh agent - converting or loading POC/Dev/UAT, building review sheets, checking a DOI, webinar or KO dates, sponsors, footnotes, legal disclosure, supplementary PDFs, media hashes, Leo's webinar zips, or the toolkit. Start-here summary of the current state, rules and commands; history and older gotchas are in focus-content-export.
---

# Focus 1.0 import: start here

The current state of the import, for an agent starting a side task. Long history, older bugs and the export pipeline are
in the **focus-content-export** skill; read it before changing converter behaviour. Re-check anything marked "state" in
the files before relying on it.

## Rules that apply to every side task (Laith's, all settled)

- **Never run `aws`, terraform, wrangler or anything with Laith's credentials.** Give paste-safe, self-contained command
  blocks (inline values, no shell vars carried across blocks); Laith runs them and pastes the output.
- **Never read credential values** (.env secrets, tokens, secret ARNs' contents). Put this rule in the FIRST prompt of any
  subagent.
- **No site code changes** in wiley/aida-emdash for import work. Converter/loader changes (our tool) are fine, but say
  "this needs a code change, confirm?" first, and test on a scratch output before touching `out/`.
- **Large loads: the fast script** (`focus-import-fast.sh`, jump host) first; the tunnel load is the fallback.
- **Sheets:** check `~/Downloads/.~lock.<file>#` before rebuilding (ask Laith to close it). The check must ABORT the
  build (`[ -e "$lock" ] && { echo LOCKED; exit 1; }`), not just print: a `ls lock; build` chain once overwrote an open sheet. Every tab links Focus 1.0
  (`https://focus.wiley.com/doi/<doi>`, staging items `https://staging.focus.wiley.com/doi/<doi>`) and its XML
  (`/doi/xml/<doi>`), plus the Focus 2.0 POC page when there is one. In/out splits (migrated vs not) go in separate
  tabs with the same columns, not greyed rows in one tab (Laith on the URL map, 2026-10-13). A README tab explains every tab like a table, and
  **every special case names its DOIs**. No dates in prose written in his name (data dates are fine).
- **Quote XML as-is** (`notes[@notes-type="disclosure"]`), never our own labels.
- **Never bypass a Cloudflare challenge** on focus.wiley.com (6.5 s/request still trips it after ~230).
- **Full-rows sheet of an existing tab: keep that tab's columns exactly** (same names, order, "Name [code]" in one cell),
  add only what Laith asks for (here: Leo's zip after "Ours (XML)"). Extra analysis columns go in their own tab, never
  in the main one: a first version split the sponsor and added 6 tag columns, and Laith asked for the old columns back.
  Verify by script that the rows he pasted from the old tab match the new sheet cell by cell, and say so.
- **Before saying two things are "the same", compare the content**, not names or one field: Laith asked "did you go
  through each xml line by line?" (6 zip copies: compare by MD5, then line by line; two DOIs in two zips had the same
  date but different subject codes, sponsor and video link).

## Where everything is

| What | Path |
|---|---|
| The tool | `~/Downloads/focus-1.0-import-tool/` (not git). `./focus-import help`; manual `docs/MANUAL.md` / `MANUAL.html` |
| Converter / loader | `jats2seed.py` (XML -> `out/seed-content.json`, `dates.json`, `entries.csv`, `report.md`), `load-seed.mjs`. Copy of the converter also in `~/Downloads/AIDAFOCUS-362-import/` (keep them identical) |
| Export | `export/2026-09-01/<type>/{production,staging}/*.zip` (symlink to `AIDAFOCUS-362-organized/2026-09-01`) |
| Converted outputs | `out/` = POC (titles " - Test", `out/poc-sponsor-slugs.txt`); `out/dev`, `out/uat` (titles " -TEST", own sponsor lists) |
| Reference | `reference/dates-from-focus1.csv` (dates from outside the XML), `reference/slugs/*.txt` (comma lists for `--slugs`), `reference/slugs/full-slugs.csv` (doi -> poc_url), `reference/mapping-sheet/` |
| Extra webinars | `export-extra/webinars-not-in-the-2026-09-01-export/` (36 XMLs from Leo's zips, NOT imported) |
| Leo's webinar zips | `~/Downloads/webinars_webinars-{243,244,245}*_withdate_*.zip` (+ copies in `~/Downloads/Migration_Confluance_Wibnar_Leo/`); 6 files, 3 distinct contents |
| Toolkit to share | `~/Downloads/focus-import-toolkit-<date>.tar.gz` (tool without out/ and export/, plus the two bench tunnel scripts). Stale after any script change: rebuild |
| Local site | `~/Downloads/projects/aida-emdash-import-main` (main + local inline-media patch), DB `focus_import_362_main`, admin http://medicine.localhost:4321/_emdash/admin |

**URL map (AIDAFOCUS-160, "FOCUS 1.0 to 2.0 URL map <date>.xlsx")**: rebuild after any date/tag/slug change. Run from
`aida-emdash-589-sync/custom/content-migration` (the only copy with the two-tab `build-url-map.py`, uncommitted) on TWO fresh converts in the scratchpad, never on the old `out/`:
```bash
cd ~/Downloads/projects/aida-emdash-589-sync/custom/content-migration; T=~/Downloads/focus-1.0-import-tool; S=<scratchpad>
OUT=$S/conv ./focus-import convert --zips $T/export/2026-09-01 --sponsor-slugs $T/out/poc-sponsor-slugs.txt --title-suffix " - Test"
OUT=$S/conv-all ./focus-import convert --all --zips $T/export/2026-09-01 --sponsor-slugs $T/out/poc-sponsor-slugs.txt --title-suffix " - Test"
lock="$HOME/Downloads/.~lock.FOCUS 1.0 to 2.0 URL map $(date +%F).xlsx#"; [ -e "$lock" ] && { echo LOCKED; exit 1; }
SEED_DIR=$S/conv ALL_EXPORT=$S/conv-all python3 build-url-map.py && cp "out/FOCUS 1.0 to 2.0 URL map $(date +%F)".{xlsx,csv} ~/Downloads/
```
The builder writes into the PR copy's `out/`, not `~/Downloads`: copy it. Tabs (Laith, 2026-10-13): Read me / "Moves to
Focus 2.0" (900) / "Does not move" (209), same 17 columns in both; the split is in the PR copy only, uncommitted (Laith: goes in a later PR, 2026-10-14; the
`focus-1.0-import-tool` copy still writes one greyed "Map" tab). Don't commit it into #673 unasked. The 09-28 file shared on the ticket had 13 columns
(`1.0 area` = production/staging, no dates, staging links wrongly on focus.wiley.com); the current one adds 4 date
columns. 2026-10-13 result vs 09-28: same 1,108 DOI/area keys and addresses, only the 48 staging 1.0 links changed;
dates 523 from the list, 266 from the XML, 111 on 2026-01-01 (109 webinars + ko.10000056, ko.10000105).
`10.5555/ko.120409.2024` is listed twice (two XMLs with one DOI, both pre-2021): known, also in 09-28. Verify by
script: keys vs the shared version, every dates-list date present in the sheet, xlsx tabs == csv rows.

Sheet builders (all in the tool folder, write to `~/Downloads`): `build-tracker-sheet.py` (tracker notes, 6 tabs),
`build-sponsor-sheet.py`, `build-webinar-dates-sheet.py` (dates map; also rewrites the webinar rows of the dates list),
`build-webinar-diff-sheet.py` (ours vs Leo's zips, writes `~/Downloads/FOCUS webinar dates map.csv`), `build-leo-extra-sheet.py` (what Leo's copies have that ours lack, found by comparing every element path: only ppub date 514, sponsor "Wiley" added 206, sponsor code added 244, different sponsor 1, plus the 36 new webinars; each kind tab shows only 10 samples, `--samples N` for more).
`build-leo-sponsor-code-sheet.py` -> `~/Downloads/FOCUS webinars sponsor code added in Leo's zips <date>.xlsx`: ALL 244
rows of the "sponsor code added" kind (imports the extra-sheet builder's functions, same comparison). Pattern for "I need a
sheet for <kind>": a full-rows sheet for one kind of the extra sheet = a small builder that reuses `build-leo-extra-sheet.py`.

## Environments

One RDS instance `focus-poc-node-nonprod-pg`, databases `focus_poc`, `focus_dev`, `focus_uat`; AWS account
909176971711, profile `909176971711_AWSNonProdASTechAdmin`.

| Env | Migrator user | Bucket | Content |
|---|---|---|---|
| POC | `focus_migrator` | `focus-poc-node-nonprod-media-a37eab19` | full import (912 entries incl. 12 supplementary children) |
| Dev | `focus_dev_migrator` | `focus-dev-node-nonprod-media-939fd5ba` | full import (912, 2026-10-12, `focus-import-env.sh`); reloaded 2026-10-13 from PR #687 (gating): 733 tagged `registration-required` (EI 101, KO 1, web 625, WP 6), checked |
| UAT | `focus_uat_migrator` | `focus-uat-node-nonprod-media-a0d7c561` | all 152 KO (2026-10-12, `--types ko`) + the samples (EI 7, WP 3, web 5), " -TEST" titles |

Tunnels: `~/Downloads/projects/emdash-bench/bench/focus-node-db.sh` (POC only, `focus_app`) and `focus-node-db-iam.sh`
(`DB_USER=focus_dev_migrator` reaches Dev/UAT). The jump host (`i-0b2671c177b8083dd`) has ~871 MB in /tmp, so the fast
script only runs `--no-media` (all files already in the bucket).

## Commands (the ones we actually use)

**Run the tool from `~/Downloads/projects/aida-emdash-589-gating/custom/content-migration`, detached at
`origin/AIDAFOCUS-589-content-migration`** (state: `4160e2aa` = #673 tool, #687 gating, #688 slug check + progress,
#690 Mayank's KO disclosure rules). Refresh before every convert:
`git -C ~/Downloads/projects/aida-emdash-589-gating fetch origin '+refs/heads/AIDAFOCUS-589-*:refs/remotes/origin/AIDAFOCUS-589-*'
&& git -C ~/Downloads/projects/aida-emdash-589-gating checkout --detach origin/AIDAFOCUS-589-content-migration`
(this clone's default refspec is main+poc only; a plain fetch leaves the base stale). Not the `589-sync` copy any more
(branch `AIDAFOCUS-589-sync-import-tool`; it holds an UNCOMMITTED `build-url-map.py` change = the URL map split into tabs 'Moves to Focus 2.0' / 'Does not move', in no PR yet; its `focus-import-env.sh`/`jats2seed.py` edits are merged via #687/#688) and not `~/Downloads/focus-1.0-import-tool`
(our rules only, no Mayank KO rules: his version puts a `focusSection` tag in 134 of 152 KO bodies). The local folder
still holds the export, `out/<env>-sponsor-slugs.txt`, the sheet builders and the slug lists: point at them by path.

```bash
# convert POC (Dev/UAT: OUT=out/dev|uat, $T/out/<env>-sponsor-slugs.txt, --title-suffix " -TEST")
cd ~/Downloads/projects/aida-emdash-589-gating/custom/content-migration
T=~/Downloads/focus-1.0-import-tool
./focus-import convert --zips $T/export/2026-09-01 --sponsor-slugs $T/out/poc-sponsor-slugs.txt --title-suffix " - Test"
# fast load on POC: dry run first, then the same without --dry-run (lists: out/slugs/*.txt, or --types key_opinion)
./focus-import-fast.sh --profile 909176971711_AWSNonProdASTechAdmin --env poc --repo ~/Downloads/projects/aida-emdash-import-main --zips $T/export/2026-09-01 --slugs "$(cat out/slugs/<list>.txt)" --on-conflict update --no-media --dry-run
```
**Loading into an env with new media (Dev/UAT): `focus-import-env.sh`** (PR copy). One command: sponsor terms from
the target, convert into `out/<env>/`, dry run, ask, tunnel load as `focus_<env>_app`, `aws s3 sync out/<env>/media`,
counts. Part of the import: `--types ko,ei,wp,web`, `--slugs a,b`, `--slugs-file FILE` (union; unknown slug stops it). The check reads `out/<env>/seed-content.json` (fixed in both copies: it read `entries.csv`, which has 900 rows and no supplementary children, so `registration-required.txt` failed with "12 slug(s) not in this convert: curated-collection-244-supplementary-1 ...").
Hand over short lines with variables (P/R/Z), never one long line:
```bash
cd ~/Downloads/projects/aida-emdash-589-gating/custom/content-migration
P=909176971711_AWSNonProdASTechAdmin
R=~/Downloads/projects/aida-emdash-main-seed
Z=~/Downloads/focus-1.0-import-tool/export/2026-09-01
./focus-import-env.sh --env uat --profile $P --repo $R --zips $Z \
  --read-sponsors --title-suffix " -TEST" --types ko
```
Step 4 prints `[progress] HH:MM <collection> n/total ...` every minute (rows whose `updated_at` is past the step's start: applySeed stamps it on every row it creates or updates; read-only, through the load's tunnel; it goes quiet if SSO expires, the load does not). After applySeed the loader's dates pass sets `updated_at` back to the dates.json date, so those counts FALL to 0; the loop then prints `dates pass: n/total back-dated` instead. ~14 entries/min on a first load, ~7/min for an `--on-conflict update` reload (Dev full reload: 912 in ~2 h 10 min; no files copied, all 900 media matched by hash). Every entry is many sequential queries through the SSM tunnel, so a reload whose files are all in the bucket is faster with `focus-import-fast.sh --no-media` (jump host, next to RDS): tell Laith to refresh SSO creds around 60 min (the S3 step needs them).

**After a load: `load-check.py`** (PR #673, `53d6a0c4`, read only). Per seed entry: present,
status, live revision (published only), title, date vs `dates.json`, author count, tags, media keys in the row, every key
in the bucket. `sql --collection X > f.sql` -> run with `focus-node-db-iam.sh -At -f` -> `aws s3 ls s3://<bucket>/
--recursive` -> `compare --out out/<env> --collection X --rows ... --s3 ... --report ...`. UAT KO 2026-10-12: 152/152,
624 media keys all in the bucket, only `health` x3 missing (tag not on UAT).

**"Search shows only a few" is the language filter, not a missing load.** Site search defaults to English
(`effectiveLanguage`, `search/[...slug].astro:130`); it also drops drafts, `hide_from_search` and expired entries
(`custom/packages/multi-site/src/lib/latest-feed.ts`). KO split: 101 en published (the default search count), 41 de,
2 es, 2 fr, 6 staging drafts. Other languages: `?language=de`. Count from the seed before suspecting the load.

A good dry run says `notReused 0`. To test a converter change: `OUT=<scratchpad dir> ./focus-import convert ...` and diff
the seed against `out/` per entry (only the intended entries may change).

**Checking someone's converter PR (done for #690):** `python3 -m pytest -q tests/test_key_opinion_rules.py` (64 pass
at `4160e2aa`), scratch convert with the env's sponsor list and suffix, then per entry and per `data` field vs
`out/<env>/seed-content.json`, plus `dates.json` (cmp), taxonomies and bylines. Noise to strip before calling a field
changed: Portable Text `_key` and link `markDefs`/`marks` ids are counters, so moving one section renumbers every later
block (#690: `references` "changed" in 100 KOs, all ids only). Then check the result against the TARGET's field
limits (`validation.maxLength` in the seed JSON at the build the env runs, counted as UTF-16 units), not against the PR text.
#690 result: only KO changed (140/152: body 140, sponsorship_declaration 134 now filled vs 21, legal_disclosure 14);
dates, gating, bylines identical. Disclosure-like headings left in 5 KO bodies are plain `<sec>` without `sec-type`
(ko-10000228, ko-140281-2024, ko-141447-2024, ko-143999-2024, ko-145300-2024): by the rules they stay.

## What the import does now (re-read jats2seed.py before describing it)

- `doi` from `article-id[@pub-id-type="doi"]` (dropped when the target lacks the field).
- Sponsor tag: only `subj-group[@subj-group-type="sponsors"]` or custom-meta "sponsor".
- **Key Opinion disclosures (Mayank, PR #690, AIDAFOCUS-620)** - no longer body sections. Sponsorship declaration =
  `notes[@notes-type="sponsorship"]`, then `notes[@notes-type="disclosure"]` (front+back, a repeat once), then
  `sec[@sec-type="MPSectionCategory:financial-disclosure"]` (ko-10000164, leaves the body). Legal disclosure =
  `notes[@notes-type="disclaimer"]`, Notice + Prescribing information sections, `fn[@fn-type="financial-disclosure"]`,
  `fn[@fn-type="COI-statement"]` (from `<back>` and `<author-notes>`). Each source keeps its own heading (title, else
  fn-title, else label), no default headings; text in both fields is kept in both. Both cut at 1500 UTF-16 units, cuts
  and unpublished other note types listed in `report.md`. Impressum stays in the body. Other types: older rules below
  (statement = `notes[@notes-type="disclosure"]` only).
- **Site limit trap:** KO `legal_disclosure` is `maxLength` 600 at `65fd9f83` (the build Dev/UAT were delivered from)
  and 1500 on `main` since #689 (`b3b4e915`, `editorial-feature.json` + a site migration); KO `sponsorship_declaration`
  is 1500 on both. With #690 one KO goes over 600: `ko-145343-2024-1` legal_disclosure 754 (11 KOs have a
  sponsorship_declaration 627-1344, fine). So deliver #689's migration to the env (and use a `--repo` build that has it)
  BEFORE a KO load with #690.
- Footnotes: every `back/fn-group` fn + `front/article-meta/author-notes` fn at the end of the body; heading = its own
  title, else "Footnote".
- Legal disclosure (non-KO): `sec[@sec-type="copyright"]` only, all merged; impressum/product-information/notice stay in the body.
- **Sponsorship / financial-disclosure text sits in 6 places** (whole export, 1,108 XMLs; articles):
  `front/notes[@notes-type="disclosure"]` 217, `back/notes[@notes-type="disclosure"]` 122,
  `back/notes[@notes-type="sponsorship"]` 57 (NOT 1, as Laith first thought), `fn[@fn-type="financial-disclosure"]` 151
  (80 Expert Perspectives have only this), `fn[@fn-type="COI-statement"]` 8 (author conflicts), `notes[@notes-type="disclaimer"]` 2;
  plus `subj-group[@subj-group-type="sponsors"]` 594 (sponsor tag only). Checked against a fresh convert: every disclosure
  note, footnote and COI reaches 2.0 (statement or body footnote) EXCEPT `notes[@notes-type="sponsorship"]` with its own
  wording: 17 imported articles (16 KO + webinars.10000235, which then has no sponsorship text at all). Open decision.
  Re-check (after any converter change): `OUT=<scratch> ./focus-import convert --zips export/2026-09-01 --sponsor-slugs
  out/poc-sponsor-slugs.txt`, then `python3 ~/Downloads/AIDAFOCUS-362-import/sponsorship-sources-check.py <scratch>/seed-content.json
  "~/Downloads/FOCUS sponsorship and disclosure sources 2026-10-05.psv" <out.psv>` (psv = doi|type|env|element|text; match
  on text values only, never raw JSON: Portable Text keys sit between spans and gave false "No").
- **My first answer went stale in 2 days**: on 10-05 I said 91 articles lose everything (footnotes were not imported);
  the 10-07 converter puts every footnote in the body, so it is 1. Re-read `jats2seed.py` (check its mtime) and re-convert
  before quoting what "the import does"; the saved `out/seed-content.json` can be weeks old.
- Gating: `connect_form_id` comes from any custom-meta name containing "form" (also `Amps connect form id`, label "Content Registration on Wiley Focus" on 8 staging drafts). A real `<meta-name>connect-form-id</meta-name>` (not n/a / live_testing) also tags `gated_content: registration-required` (733 entries: web 625, EI 101 incl. 12 supplementary children, which also get the parent's form id, WP 6, KO 1 = expert-perspective-10000214). Without the tag the site never asks for the form (`src/utils/gating.ts`). Slug lists `reference/slugs/registration-required.txt` (733), `uat-registration-required.txt` (13 on UAT). Both converters edited: tool folder + PR #687 (branch `AIDAFOCUS-589-registration-gating`, worktree `~/Downloads/projects/aida-emdash-589-gating`, base `AIDAFOCUS-589-content-migration`; #673 is merged there). Fetch that base with an explicit refspec: a plain fetch left it stale once.
- WOL tags (UAT scan 2026-10-15: 33 EI fail on wol_taxonomy): content management's WOL TAXONOMY UPDATED column is saved as `reference/wol-feedback-content-management.psv`; 21 rows (XML had no codes) went into `wol-overrides.csv` (PR #700, branch `AIDAFOCUS-589-wol-overrides-cm`, worktree `aida-emdash-589-wol`). 10 `ch`/`ms` items stay untagged: 2.0 has them only as word slugs (`chemistry`, `materials-science`); a name-match converter change (PR #701) was closed, Laith: "we will not do it". `expert-perspective.10000082` and `.10000102` got `life;ch,life` (looks like a copy-down slip, asked to confirm). The FINAL sheet's AMPS column has codes for the 22 with none in the XML; the converter does not read it. `wol-overrides.csv` is CRLF: append, never rewrite. Export 2 = `~/Downloads/AIDAFOCUS-362-v2-organized/2026-10-14`; with #698 (38 webinars + 9 RNF KOs added to the sheet) the convert gives 959 entries. `source-inventory.py` (tool folder) lists every article XML in the zips with its import decision.
- Supplementary: `self-uri[@content-type="pdf"]` files in `suppl/` -> bulleted "Supplementary material" list linking
  `/api/asset/<coll>/<id>/pdf_asset`; extra PDFs become hidden child entries `<slug>-supplementary-<n>`.
- Media: every `$focusMedia` carries `size` and `contentHash` (`sha1:<hex>`, EmDash's format; not TIFF); the loader reuses by
  hash, then name+size, then unique name.
- Dates: `pub-date[@pub-type="epub"]` -> `history/date[@date-type="epub"]` -> `history/date[@date-type="accepted"]`; if
  none, `reference/dates-from-focus1.csv` (doi,date,source; the wrapper passes it; the report labels the date with the
  `source` column); none -> 2026-01-01 for EVERY type (page date AND published_at; Laith; KOs were 2020-01-01 page date + import-time published_at before). `--on-conflict update` rewrites data + taxonomies + bylines of the listed slugs, then published_at/created_at/updated_at from dates.json.

## Dates list (state)

`reference/dates-from-focus1.csv` = 9 KO dates read off Focus 1.0 pages + 514 webinar dates from Leo's zips
(`pub-date[@pub-type="ppub"]`, 464 from webinars-243, 50 from 244). 109 webinars have no date in Leo's zip either (no date
element at all, e.g. webinars.1322574) and stay on 2026-01-01.
Slug lists: `reference/slugs/poc-webinar-dates.txt` = the 514 that GET a date (load these to apply the dates);
`reference/slugs/poc-webinars-still-2026-01-01.txt` = the 109 that stay on 2026-01-01 (no date anywhere).
`out/`, `out/dev`, `out/uat` are reconverted with them (only the 514 webinar entries changed).
**Is a date live on POC?** `dates-poc-check.py` (tool folder): `sql --out reference/dates-poc-check.sql` writes a READ-ONLY
query (published_at + page date per DOI in the list); Laith runs it with `AWS_PROFILE=909176971711_AWSNonProdASTechAdmin
./focus-node-db.sh -f <sql> > reference/dates-poc-check-result.psv`; `merge --result <psv>` adds `updated_on_poc` (yes = both
dates equal the list) + `poc_note` to the CSV (temp file + mv; the converter reads only doi,date,source). Re-run `sql`
after the list changes. `build-webinar-dates-sheet.py` rewrites the CSV with 3 columns and DROPS these two: re-run `merge`.
- **"We already loaded that" was wrong** (Laith believed the Leo dates were on POC): only 15 webinars had them, and only
  because the 31-entry WOL-override load reloaded them from the reconverted seed. Every fast-script run writes
  `out/import-fast-<env>-<run>.log`: list them (`ls -la out/import-fast-poc-*.log`) and query the DB before saying
  "applied"; a partial reload also ships any other reconverted change for those slugs.
- Default date rule changed: every type with no date anywhere -> 2026-01-01 (was: non-webinars page date 2020-01-01 and
  published_at = load time). Only ko-10000105 + ko-10000056 changed; loaded on POC with the 514 (516 updated).
  `out/dev`, `out/uat` are NOT reconverted with it (matters only if those 2 KOs are samples).
- `report.md` `no_date` / `fallback_date_used` say key_opinion 11, but only 2 KOs end up undated: count from
  `entries.csv` (`date` empty), not from the report counters.
- **Webinars have no speakers anywhere**: 0 `contrib`/`contrib-group`/`role` in our 626 XMLs (all 625 imported have 0
  bylines, hence `require_byline` fails); Leo's zips have none structured either, 27 only name speakers in the description
  text (e.g. webinars.1317823 moderator). Speaker names need a source outside the XML.
- **Authors per type (POC convert)**: only KO has any. KO 65/152 with bylines (185 links, 257 distinct bylines; 87 none),
  from `<contrib>` (33 XMLs) or `sec[@sec-type="contributor-information"]` (30) / `"author-information"` (6); the
  converter also reads speaker-/chair-information (none exist). Expert Insight, Whitepaper, Webinar: 0 contrib, 0 author
  sections, 0 bylines. 3 KOs have a section but no byline: ko.137938.2024 (3 named "Contributors": a likely MISS, fix =
  converter change, ask), ko.146699.2024 (writing assistance only), ko.140223.2024 (a company). Count: `out/entries.csv`
  `authors` column per `collection`.

## Leo's zips vs our export (facts, from build-webinar-diff-sheet.py)

- **Sponsor code added (244) is proven NOT NEEDED** (2026-10-12): the converter's `sponsor_slug` tries the code first,
  then the name, against `out/poc-sponsor-slugs.txt`; name only (ours) and Leo's code + name give the same tag for all
  244, and `out/seed-content.json` already has it. 21 sponsor rows (one webinar is "Merck [merck], MilliporeSigma
  [milliporesigma]", so the per-name counts Merck 12 / MilliporeSigma 13 include it). 238 rows from webinars-243, 6 from
  244. The zip column shows `webinars-243 ... (1).zip`: the first file read of an MD5-identical pair, not a different zip.
- We take ONLY the date. The 36 webinars not in our export (all in webinars-245) are not imported (Laith).
- In the 623 shared webinars, Leo's copy differs beyond the date: sponsor "Wiley" added where ours has none (206), sponsor
  code added to the same name (244), less body text (19 shorter, 3 empty: webinars.1199817, .1296400, .1443778). Our
  export is the fuller copy.
- webinars.1409630 and .1770285 are in both 243 and 244: same date, different XML (subject codes, video link; .1770285 also
  Merck vs MilliporeSigma).
- Our own export has several webinars with one title (4 x "Aus der Wissenschaft in die Beratung", 4 x "FLT 8 ...", each its
  own video): a title match is never proof of the same webinar.
- Gotcha I hit: joining sponsor code and label with a space and splitting it back cut the first word off code-less labels
  and produced 115 false "different sponsor" rows. Keep code and label as separate fields; when a count looks large,
  open 5 raw examples before reporting it.

## Republish scan (can migrated entries be published again?)

- `publish-gate-check.mjs` (tool folder, READ-ONLY): runs the site's own `validatePublishReadiness` on every entry ->
  jsonl. Same failing entries/issues as a real Unpublish+Publish of all 912 locally, so never mass-unpublish to test.
  POC: `./focus-node-db.sh --exec node <tool>/publish-gate-check.mjs --repo <aida-emdash-import-main> --out ...`.
- `build-republish-scan-sheet.py --gate X.jsonl --terms name|slug.txt [--gate-only]` -> `~/Downloads/FOCUS republish scan
  <date>.xlsx` (README + tab per type, XML evidence per issue). Local result: 719/912 fail (all 625 webinars:
  require_seo + require_byline, import writes neither; KO 49 references required - 21 have them as a body
  sec "References"/"Literatur" with an empty `<ref-list/>`; 64 no WOL: 38 no AMPS codes, 26 only codes the site lacks
  (loader drops them silently); EI 8 no PDF; 5 titles >160). Republish resets published_at (sponsor pages sort on it).
- The gate lists some fields twice (pdf_asset, full_video_url): count per entry.
- **publish-gate-check.mjs hangs forever when the SSO token expires mid-run** (no error, no timeout; UAT 2026-10-15 sat 5 h on webinars). Full UAT scan = ~16 min: refresh creds first and wrap it in `timeout 1800`. The dead tunnel's `session-manager-plugin` is left orphaned (parent = systemd) holding :5433; kill it by PID. Never `pkill -f '<pattern>'` from a Bash tool call whose own command line contains the pattern: it kills the tool's shell (exit 144).
- **Do not run publish-gate-check.mjs on POC over the tunnel**: it walks EVERY entry (POC also holds ~7.7k KO and
  ~8.2k webinar dummy/load-test rows; 912 are migrated) and ran 45+ min still on KO. Use SQL instead: migrated rows =
  `title like '% - Test'` (matches exactly 119/152/625/16); missing PDF = `pdf_asset` '' (text column, not NULL);
  no tag = no `content_taxonomies` row joined to `taxonomies.name='wol_taxonomy'`.
- Main delivery (AIDAFOCUS-549/507/575/570, migrations 0021+0022, seed --update --no-content) was applied locally and
  on POC (Admin profile works for focus_migrator in the fast scripts); worktree `~/Downloads/projects/aida-emdash-main-seed`
  = detached origin/main, rebuilt. Editors' tags: `reference/wol-overrides.csv` + converter `--wol-overrides`
  (31 items, loaded on POC). Remaining: 33 EI tags (editors), 8 EI PDFs, webinars.10000247 video.
- Sheet is for BUSINESS readers (Laith): type tabs named "Native Webinars" etc., one row per item per issue, Issue
  column first (filterable), plus "Issues on this item" / "All issues on this item"; plain Why / What is needed;
  Ticket column (AIDAFOCUS-549 = webinar SEO + byline, AIDAFOCUS-507 = KO references, Laith's call); XML detail only
  on the "Import team detail" tab. No Leo data in this sheet. Quote XML element names only in that detail tab.
- Facts settled: pdf_asset required on EI + WP; full_video_url required on every webinar (webinars.10000247 is a
  live-event registration page, its on24 ext-link is NOT a video); title max 160 (webinars 500); republish keeps
  display_published_date/broadcast_date but resets published_at/updated_at.

## The repo copy (`custom/content-migration/` in wiley/aida-emdash)

Mayank's branch `AIDAFOCUS-589-content-migration` holds the tool in the repo; his first commit `aed65856` was an OLD
copy of ours, made portable (repo-relative defaults, `<profile>` placeholders, `load-seed.mjs` oxfmt-formatted) and
then extended with Key Opinion rules (AIDAFOCUS-590/605/606). Our changes went in through PR #673. Before quoting
"the import does X", say which copy: ours (`~/Downloads/focus-1.0-import-tool`) or the branch.

**Merging ours into the branch again** (`git merge-file <branch file> <aed65856 file> <ours>`):
- The base is a genericized copy, so every path/profile hunk comes back as OUR local value (`~/Downloads/...`,
  `909176971711_AWSNonProd...`, `--repo` made required). Grep the diff for `Downloads|/home/|Path.home|process.env.HOME|
  9091769` and restore the branch's lines.
- `load-seed.mjs` loses its formatting. `custom/content-migration` is in the formatter's ignore list, so run oxfmt on
  a copy: put the repo's `.oxfmtrc.json` and the file in a scratch dir, then `<built checkout>/node_modules/.bin/oxfmt
  file.mjs` there (halved the diff, 346 -> 175 lines).
- Conflict rule Laith accepted: Key Opinions keep the branch's rules (disclosure + financial-disclosure/COI as tagged
  body sections, legal = LEGAL_SECTIONS minus copyright/product-information), every other type follows the tracker
  rows (statement = disclosure note only, every footnote to the body, legal = copyright only).

**Verify a converter merge** by converting the full export three ways (ours, branch as-is, merged) into scratch dirs
and diffing `seed-content.json` per collection and per data field, ignoring `size`, `contentHash` and `_key`. Result
for #673: EI/webinars/WP identical to ours, 912 dates identical, KO = branch + our additions, one real body change
(`ko-10000043` gains "Contributed-by information"). Then `./focus-import test` (51 Python tests).

**Run the tests and a loader dry run locally (no AWS):**
- Local Postgres: `docker start focus-local-postgres` (it stops on reboot). Sign in as `focus_admin` /
  `focus_admin_local`: `focus_migrator` gets `permission denied for table ec_key_opinion` there.
- Dry run: `PGHOST=localhost PGPORT=5432 PGUSER=focus_admin PGPASSWORD=focus_admin_local
  PGDATABASE=focus_import_362_main PGSSLMODE=disable OUT=<convert dir> ./focus-import dry-run --repo
  ~/Downloads/projects/aida-emdash-import-main --zips <export> --on-conflict update --no-media`. Locally
  `notReused 19` is normal (author photos that DB never got); compare with our loader on the same seed before calling
  it a regression. The loader writes `load-report.json` NEXT TO THE SEED, so a second run overwrites the first.
- `tests/byline-custom-fields.test.mjs` needs `kysely` from the repo. In a fresh worktree, copy `tests/` and `*.mjs`
  into `<scratch>/custom/content-migration/`, copy `custom/sites/focus/package.json`, symlink `node_modules`,
  `custom/sites/focus/node_modules` and `packages` from `aida-emdash-import-main`, then
  `FOCUS_TEST_PG_URL=postgres://focus_admin:focus_admin_local@localhost:5432/focus_poc node --test ...` (5/5 on #673).

**What #673 added beyond the merge:** `reference/dates-from-focus1.csv`, `reference/wol-overrides.csv`,
`db-tools/` (`focus-node-db-iam.sh`, `focus-node-db.sh`, `focus-node-seed-fast.sh` + README), `focus-import-fast.sh`,
`s3-presign.mjs`, the checks `publish-gate-check.mjs`, `dates-poc-check.py`, `media-check.py`. Every convert now writes
`out/slugs/{all,date-overrides,wol-overrides,no-date}.txt` (912 / 523 / 31 / 111): use those for `--slugs`, not
hand-made lists, which go stale when the dates or tags files change. `build-url-map.py` no longer needs
`METADATA_CSV`: the Focus 1.0 link is built from the DOI (staging on `staging.focus.wiley.com`), staging copies of
production DOIs come from `staging-duplicates.csv` (written by convert), and migrated rows take collection/site/slug
from the import, not the `--all` run (where Curated Collections are `article_collection`). Not added, by decision:
the `build-*-sheet.py` builders, `site-patches/`, `reference/check-later/`, `out/`; the manual is a separate PR.

**Editor tags on POC:** the `wol-overrides.csv` load ran 2026-10-08 17:57 (31 entries + 14 bylines updated);
`ee13` (`webinars.1407866`) was dropped because POC has no such term. The dates load of 2026-10-11 dropped 17
unknown subject codes in 68 places (`be41`, `ba02`, `hs06`, ...): the site's term list lacks them.

**POC Key Opinions on the merged conversion (2026-10-12):** before, 0 of 152 had Mayank's version (he never loaded
it on POC). Loaded from the PR copy: 144 via the fast script `--no-media` + 8 via the tunnel with `--media-dir
--reuse-target-media` + `aws s3 cp` (15 new files: author photos inside tables/info boxes that the old conversion
dropped, so `--no-media` reported `notReused 19`). Check: `his_version` (`body::text like '%focusSection%'`) = 134,
`with_tables` = 40. In Chrome (read the DOM under the HCP gate, never click it): data tables render as
`table.emdash-table`, info boxes as `.article-table--box` (PR #667 is in POC's build), images 200. Some KO pages say
"unavailable in your region" from here: regional rule, not a fault. Recipe when a dry run shows `notReused > 0` on
`--no-media`: split the slugs, fast-load the rest, tunnel-load the few with media, then copy the media dir to the bucket.

`focus-import-fast.sh` fixes (2026-10-12, both copies): a flag with no value (`--repo` cut off by a broken paste)
looped forever on `shift 2`; the import-block transform now ignores whitespace and rewrites the loader's `./*.mjs`
imports (`byline-custom-fields.mjs`) to absolute paths, since the bundle entry sits in the Focus 2.0 checkout.

**UAT URL check (KO + EI + web from v2, PR copy):** curl gets `403 cf-mitigated: challenge` on UAT too, so run same-origin `fetch` from a tab on each host (3 at a time, 300 ms gap, ~3 pages/s; JS output truncates, return a summary). Result: all 912 seed URLs as expected (published 200 + ` -TEST` title, drafts 404/not found); only misses = 3 whitepapers not loaded (UAT has the 3 samples) and 19 KO `403 unavailable in your region` = exactly the KOs whose `permitted-location` list lacks JO (the browser's country). Expected region blocks depend on where the checker sits.
**Why Leo's 36 + the 2 ON24 webinars are not on any env:** the convert keeps only DOIs in `reference/mapping-sheet/FOCUS Content for Migration_FINAL*.csv` (`--only-mapped`); none of the 38 is in it ("DOIs not in the FINAL sheet" 199 -> 237). To bring them in: add them to the sheet, not `--all` (that also imports the pre-2021 content).

**Sheet update for v2 (PR #698, branch `AIDAFOCUS-589-sheet-new-items`, worktree `~/Downloads/projects/aida-emdash-589-sheet`):** +38 Webinars-tab rows (Leo's 36 + webinars.10000251/252; exact columns from the XML via the original `build_mapping_sheets.py` helpers on `generate_metadata.py` output, site/specialty/language = converter guess from a `convert --all`, Notes says "suggested ... to be reviewed") and `Record Not Found` emptied on the 9 staging KOs. Builder: scratchpad `add_sheet_rows.py` (not in the repo). CSVs round-trip byte-exact with `csv.writer(lineterminator='\r\n')` keeping BOM/encoding (Webinars/KO/CC utf-8-sig, EP/WP cp1252). Result on v2: 959 entries (KO 161, EI 119, WP 16, web 663), the 912 byte-identical, not-in-sheet 199. Science rows keep only the FIRST guessed methodology (one column). Not yet loaded anywhere.

**Why report.md counters overcount (read in main()):** `Article.build()` runs for EVERY article; the sheet filter, the staging-duplicate skip and the `-2` slug rule run afterwards in the main loop. So build-time counters (`no_date`, `no_authors`, `sponsor_unmatched`, `fallback_date_used`, ...) include dropped articles; count from `entries.csv`. Field cuts: KO sponsorship/legal 1500, EI/WP sponsorship + legal 600, webinar disclaimer 600, title 500, full_video_title 200. `kwd-group` never imported. Flow page (convert + load + overwrite rules): https://claude.ai/artifact/6hjU1gu4BuWQ7p1XZ81W2M
**`--on-conflict update` (applySeed, core seed/apply.ts):** sets only the data keys in the seed (other fields kept), status from the seed (republishes / turns staging into drafts), new revision published, DELETES every `content_taxonomies` row of the entry then re-attaches the seed's tags (hand-added tags lost), replaces entry bylines (cleared if none), dates pass sets published/created/updated_at. Never deletes entries; media added only.

## Open items (state; confirm with Laith)

- **Dev gating reload DONE** (#687 convert, all 912 `--on-conflict update`): 912 updated, 912 back-dated, 0 files,
  733 tagged (EI 101, KO 1, web 625, WP 6). Samples: gated `expert-perspective-10000214`, `webinars-10000247`; not
  gated `ko-20000105`, `expert-perspective-169629` (the only published EI without a form id).
- **Prod content load (tickets: sponsors, KO, webinars, Expert Insights)**: shareable docs
  `~/Downloads/projects/focus-multi-env-plan/prod-sponsors-load.html` + `prod-content-load.html` (plain runbooks), ticket helpers
  `prod-content-tickets.html` / `prod-content-subtasks.html`; all four built by `prod-content-docs-src/{gen,share}.py`
  (`python3 share.py <dir>`; `python3 gen.py <out.html> [subtasks]`). Export `~/Downloads/AIDAFOCUS-362-v2-organized/2026-10-14`
  = 959 (KO 161: 145 pub/16 draft, gated 1; web 663 pub, gated 661; EI 119: 101 pub incl 12 suppl/18 draft, gated 101; WP 16).
  Prod gets the " -TEST" suffix (Laith). Tool prod support = PR #713 (`AIDAFOCUS-589-import-env-prod`, worktree
  `~/Downloads/projects/aida-emdash-589-prod`): `focus-import-env.sh --env prod`, `db-tools/focus-node-db.sh --target prod`.
  Prod runs `ed56a4ea` (has #689/0026): core 54 + site 27 migrations applied, KO legal_disclosure 1500. Build R =
  `~/aida-emdash-prod-build` at prod's commit. **The prod SSO role can't `ecr:DescribeImages` on the nonprod repo: read
  the image tag with `909176971711_AWSNonProdASTechAdmin`** (I dropped that fallback once and the block failed). Sponsors:
  91 rows seeded; the 90 seed files copied to `focus-node-prod-media-accfbefe` (done). Unilever logo replaced in all 4
  buckets (same key). 97 unmatched sponsor names -> `partners` text: open decision.
  **Prod load DONE** (one run, `--types ko,web,ei`, ~80 min): created 943 (KO 161, EI 119, web 663), bylines 142, 943 dated,
  838 files staged + synced, 57 matched by hash. Verified: status/gated counts = convert (KO 145/16 gated 1, EI 101/18
  gated 101, web 663 gated 661); `load-check.py` clean except tags prod lacks (KO 6: health/md; EI 48: ch/ms/life/health;
  web 74: be41, ba02, en62, mddp0, ...; 27 codes / 146 assignments dropped). Webinars carry no media in the seed (0 keys).
  Whitepapers not loaded (not in the 4 sub-tasks).
  **Unmatched sponsors sheet:** `build-unmatched-sponsor-sheet.py` (tool folder) -> `~/Downloads/FOCUS sponsors not on Focus 2.0.xlsx`
  (README/Sponsors/Articles): 97 names, 213 articles, 229 pairs = report.md. CORRECTION: on main the unmatched name is NOT
  written to `partners` (ids only; jats2seed.py ~1923 "report, never write") -> those articles show no sponsor at all.
  ko.10000056 has malformed `subj-group-type="sponsors[organon"` + code `asia-pacific]` (= Organon Asia-Pacific).
  Closest-sponsor suggestion must be strict (whole-word containment or ratio >=0.85): looser gave AcroBiosystems->Leica.
  **Prod after reload:** titles real (`--no-suffix` reload: updated 943, only `title` + webinar `full_video_title` change),
  Whitepapers loaded (created 16, 42 files) -> prod has all 959. **Dropped-tags sheet:** `build-dropped-tags-sheet.py`
  -> `~/Downloads/FOCUS subject tags not on Focus 2.0.xlsx`: 35 codes, 221 tags, 143 entries (KO 6, EI 48, WP 15, web 74),
  all from the XML. Target's tag list = wol_taxonomy terms in `<build>/custom/sites/focus/.emdash/seed.json` (904 on prod;
  counts match the loader's "unknown term slugs dropped" lines). Mostly broad codes (health, md, ch, ms, life, pseng, ee...).
- **UAT next, run by another person**: `--types ko,web` (reload 152 KO for the 1 gated KO, add 620 webinars, ~1-1.5 h,
  refresh SSO before step 5). Expect tags `key_opinion|1`, `webinars|625`. Gap: the 5 EI + 3 WP UAT samples with a form
  id stay untagged (`--types ei,wp` would load ALL EI/WP). Proposed, NOT built: `--only-existing` (only slugs already in
  the target). If the KO load includes #690, deliver #689 to UAT first (limit trap above).
- **Handing a run to another person:** no fixed values in the command (Laith rejected 13 inline slugs: "too much fixed
  values"); select with `--types`, or a list file in the repo. Explain P (their SSO profile for 909176971711: Secrets
  Manager read of `focus-<env>-node-nonprod/app/database-url` + SSM session), R (their built aida-emdash checkout at the
  env's build), Z (the export folder, 1.3 GB, not in the repo: Laith gives it). Their tag check:
  `AWS_PROFILE=<p> PGDATABASE=focus_uat DBURL_ARN=focus-uat-node-nonprod/app/database-url ./db-tools/focus-node-db.sh -Atc "..."`
  (secret name instead of ARN: untested).

- POC dates: DONE (load 2026-10-11 18:37: 516 updated/back-dated; `dates-poc-check.py` = all 523 `yes`). Confirm the
  copyright-only load landed.
- The tool is going into the repo: PR #673 (`AIDAFOCUS-589-sync-import-tool` -> Mayank's
  `AIDAFOCUS-589-content-migration`, path `custom/content-migration/`, scripts in `db-tools/`). Key Opinions follow
  Mayank's rules there, other types ours. `convert` now writes `out/slugs/{all,date-overrides,wol-overrides,no-date}.txt`.
  Until it merges, the `~/Downloads/focus-1.0-import-tool` and bench copies are still the ones run: change both.
- **Full import on Dev (2026-10-12)**: `focus-import-env.sh --env dev ... --read-sponsors --title-suffix " -TEST" --yes`
  from the PR copy (`aida-emdash-589-sync/custom/content-migration`, repo `aida-emdash-main-seed` 65fd9f83). Result:
  content created 889 / updated 23, bylines 104/17, 117 byline fields, 912 dated, 755 media staged + synced, counts
  152/119/16/625. 29 subject codes / 209 assignments dropped (Dev lacks them). **Took ~80 min over the tunnel** (not
  15-30): ~14 entries/min. Progress = count `title like '% -TEST'` per `ec_*` table; liveness = `pg_stat_activity`
  grouped by `client_addr` (loader = jump host IP, one connection whose `state_change` keeps moving). SSO expiry
  mid-load is harmless for the DB (connection already open); the S3 step re-reads `~/.aws/credentials`.
- **UAT KO-only load (2026-10-12)**: `focus-import-env.sh --env uat ... --types ko` (option added in `dd3f1295`, PR #673;
  also `--slugs-file`; union of all three, checked against `out/<env>/entries.csv`). A first run was stopped with
  Ctrl+C at 80/152; the rerun gave created 72 / updated 80, bylines updated 121, 152 dated, staged 0 (the stopped run
  had staged all 755 files and written their rows), step 5 synced all 755 from `out/uat/media`. UAT drops only `health`.
  Stopping mid-load is safe: rerun the same command. `--slugs` does NOT narrow the bylines: all 121 load every time.
  applySeed writes bylines first, then content, so the KO count sits still for a few minutes after the authors.
- Dev/UAT sample loads: DONE (both: 18 created + 2 updated, 20 dates, 71 media staged + copied to the env bucket,
  0 failed/notReused; `--repo aida-emdash-main-seed` = the build the Dev/UAT DBs were delivered from). Recipe =
  MANUAL 3c (tunnel, `--media-dir out/<env>-media-tracker --reuse-target-media`, then `aws s3 cp`). The fast script
  can't do this: with media it needs 4 GB free on the jump host (has ~871 MB), and `--no-media` left 81 notReused.
  The 7 subject codes `health life ch ee eg ie ms` are dropped on Dev/UAT (not in their tag list), same as POC.
  Later reloads of the samples: fast script `--no-media` now works (files are in the buckets).
- Verify POC in Chrome after loads. Dev + UAT samples verified in Chrome: all 20 pages 200 with " -TEST" titles, every
  `/_emdash/api/media/file/*` and `/api/asset/*/pdf_asset` link 200 on both hosts (medicine-/sciences-focus-<env>.literatum.com).
  Check by fetch from the page (HEAD + AbortController timeout; a plain GET loop over webinar pages froze the tab).
  Don't click the HCP gate or cookie banner; videos are cookie-gated (expected).
- Concerns sheet not built (36 webinars, COI text, 91 sponsors missing on Dev/UAT, supplementary child pages).
- Decisions for Laith: 28 `notes-type="sponsorship"` notes; ko-10000034 duplicate heading; ko.10000043 heading;
  ko.10000232 (impressum in the disclosure note); the 1,500 limit; tagging untagged sponsors; rebuild the toolkit tar.
