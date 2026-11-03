---
name: jira-person-activity-report
description: >-
  Use when asked to collect every Jira ticket one person was involved in (assignee, past
  assignee, reporter, creator, watcher/CC, commenter, @mentioned) over a period, and to
  categorise that work, size automation projects from it, or compare periods. Covers atypon
  Jira access through the Atlassian connector, JQL for each role, paging thousands of
  results to disk, the Feb 2026 bulk-update date trap, rule-based categorising, and the
  validation loops. Also use when a report about a person must not show their name, and
  when an atypon Jira "updated since <date>" search returns far older tickets than expected
  (e.g. 2021 tickets in a 2-year window — the Feb 2026 bulk update).
---

# Jira person-activity report

Built 2026-09-24..27 for one ops engineer (5,358 tickets, 2021–2026). Working copy:
`~/Downloads/ops_jira_activity/`. Bundled scripts: `scripts/build_2y.py`,
`scripts/categorize.py` (verified to reproduce the working output byte-for-byte).

## 1. Access (atypon Jira)

- `jira.prod.atypon.com` is only a display domain for **`atypon.atlassian.net`** (Jira Cloud,
  `serverInfo` says `deploymentType: Cloud`). cloudId `6bfba5f3-1c23-4def-98c0-c0592a82537c`.
- The claude.ai Atlassian connector grants **one site per consent**. The error
  `Cloud id … isn't explicitly granted by the user` means: user reconnects in claude.ai →
  Settings → Connectors, picks the site in the "Use app on" dropdown, then `/mcp` reconnect.
  Check with `getAccessibleAtlassianResources` on **both** connectors: on 2026-09-26
  `Atlassian` = atypon, `Atlassian_Rovo` = wiley-global.
- Don't fall back to the OpsBot token hardcoded in `JiraIncidentFetch.py` for searches about
  a person without the user's explicit OK — it's a shared service account.

## 2. Queries (one per role — JQL can't do all of them)

`A` = accountId from `lookupJiraAccountId`.

| Role | How |
|---|---|
| assignee (any time), reporter, creator, watcher | main JQL: `(assignee WAS "A" OR reporter = "A" OR creator = "A" OR watcher = "A" OR text ~ "First" OR text ~ "Last") AND updated >= "…"` |
| past assignee | separate key-only query: `assignee WAS "A" AND (assignee != "A" OR assignee is EMPTY)` |
| mentioned only in text/description | separate key-only query: `(text ~ …) AND NOT (assignee WAS … OR reporter … OR creator … OR watcher …)` |
| commenter | **no JQL for it** — fetch `comment` in the main query and match `author.accountId` |
| @mentioned in a comment | in `markdown` output a mention renders as `@First Last` (inside `<custom data-type="mention">`); match that or the accountId |
| watcher-only | residual: matched the JQL but none of the above |

Get `searchResultMode: "count"` for every query first; it's the completeness target.

## 3. Fetching thousands of tickets

- A page with comments is ~1.2 MB, so the MCP tool saves it to a tool-results file and returns
  the path. **Process with `jq`; never Read the file** (context blow-up, and comments can hold
  secrets). `maxResults: 100`, follow `pageInfo.endCursor` until `hasNextPage` is false.
- For >1,000 tickets, **split by `updated` date windows and run one background agent per
  window**, each copying pages to `raw/<window>/page_NN.json`, plus one agent for the two
  key-only role lists. Give each the no-secrets rule and "report counts only" in the first
  prompt (see `supervising-background-agents`). 5,358 tickets took ~50 min, mostly one window.
- **Verify on disk, not from reports:** every page parses; total keys == unique keys == sum of
  window counts; key lists match `^[A-Z][A-Z0-9]+-[0-9]+$`.
- Small last pages come back **inline**; the agent then writes them by hand. Validate those
  (`jq '.issues.nodes[] | [.key, (.fields|keys|length)]'` → 11 fields each).
- One ticket's comments can time out every time (LIT-654698, 2026-09-26). Bisect `maxResults`
  down to 1, save that ticket without comments, and note the gap.

## 4. The date-window trap (atypon, verified 2026-09-26)

About **4,300 tickets were bulk-updated on 11–14 Feb 2026**. So `updated >= <2 years ago>`
reaches back to 2021 (5,358 tickets instead of ~1,600). Check the top `Updated` dates before
trusting any "updated since" set. The honest 2-year view =
**created since X, OR commented on by the person since X, OR updated in the shorter recent
window**. The last clause makes the long view a superset of the short one; without it, 100 of
the 655 six-month tickets fell outside the "2-year" set and the columns didn't nest.

## 5. Categorising

`scripts/categorize.py [in.csv] [out_prefix] [period label]`: ordered regex rules on
summary + type, first match wins; bugs that land in feature/release/change buckets move to
"Functional bugs"; release-marked bugs become "Release regression". Workflow that worked:

1. Run, then list the **top words in each catch-all bucket** and add rules for real clusters
   (the 2-year run surfaced Proxmox VM moves, flexclone rebuilds, DB moves, `[FIRING]` alerts).
2. Spot-check 6 random tickets per sub-category.
3. **Blind audit**: a fresh agent gets 90 random tickets + the taxonomy, no rules, and lists
   disagreements. 86/90 agreed; all 4 disagreements were correct and became rule fixes.
4. Stop when the catch-all is ~5% and genuinely one-off.

Python-patching-Python gotcha: put regexes in `r'''…'''` and assert each replacement's
count before writing. A heredoc edit with `\\b` silently matched nothing once.

## 6. Sizing projects from the data

Raw counts mislead. For each candidate project also compute: **% assigned to the person**
(assignee now or ever, reporter, creator), **comments per ticket** (effort proxy),
**tickets created this year** (trend). Two projects fell out on this: Proxmox VM moves (52
tickets, 17% owned, 0.3 comments each) and monitoring alerts (26% owned, bot-filed). They
were other teams' tickets the person was CC'd on. Also check the trend per half-year: one
category (build/patch/deploy failures: 9 → 10 → 22 → 60 → 41 in 3 months) carried the case.

## 7. Validation loops (run all three before handing over)

1. **Numbers**: regenerate every number on the page from the CSVs by script (don't hand-edit),
   and assert nesting (6 mo ≤ 2 yrs ≤ history) per row.
2. **Categories**: the blind audit above.
3. **Claims**: each prose sentence with a number or "none since"/"most" gets a programmatic
   check; every cited ticket key must exist in the data. Loop 3 caught a category-level
   number quoted for a sub-category, and a trend figure that went stale after a rule fix.

## 8. Anonymised output

If the user wants the subject hidden (see memory `anonymise-report-subject`): neutral file and
folder names, "Engineer" for their display name in assignee/reporter and summaries, neutral
column names ("Involvement", "Comments by engineer"), no she/he pronouns, neutral titles.
Then `grep -ciE "<first>|<last>"` on every output. The raw pages still contain the name.
Say so, and offer to delete them.

## Running it

```bash
cd <out_dir>
SUBJECT_ACCT="<accountId>" SUBJECT_NAME="<First Last>" RAW_DIR=<out_dir>/raw \
RECENT_SINCE=<YYYY-MM-DD> python3 ~/.claude/skills/jira-person-activity-report/scripts/build_2y.py
python3 ~/.claude/skills/jira-person-activity-report/scripts/categorize.py ops_jira_2y.csv out_categorized "label"
```
