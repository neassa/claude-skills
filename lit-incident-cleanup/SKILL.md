---
name: lit-incident-cleanup
description: Use when working with JiraIncidentFetch.py, the LIT incident cleanup queue (Moni Bot tickets labeled Closed_Incident but still open), closing LIT incidents via script, the incident queue HTML/email report, or when email from a script isn't arriving (laptop SMTP blocked, prod102 relay, Wiley delivery delay).
---

# LIT Incident Cleanup (JiraIncidentFetch.py)

## Overview

`JiraIncidentFetch.py` finds Moni Bot LIT incidents whose alert already cleared (label `Closed_Incident`) but whose ticket was never closed, reports them (console/CSV/HTML/email), and can close them via Jira transitions. Built 2026-08-29, verified end-to-end including a real close.

**Locations** (keep in sync via scp):
- Runs for real: `literatum@prod102:~/personal/ljanaideh/scripts/JiraIncidentFetch.py`
- Dev copy: `~/Downloads/JiraIncidentFetch.py` (Laith's laptop)

## Quick Reference

```bash
# Report + email (on prod102; plain localhost:25 works there)
python3 JiraIncidentFetch.py --email --csv

# From the laptop: no outbound SMTP — tunnel through prod102 first
nc -z localhost 2525 2>/dev/null || ssh -f -N -L 2525:localhost:25 literatum@prod102
python3 JiraIncidentFetch.py --email --csv --smtp-port 2525

# Closing (workflow has "Close Issue" id 2 -> Closed, works from Open)
python3 JiraIncidentFetch.py --list-transitions LIT-XXXXX   # read-only
python3 JiraIncidentFetch.py --close LIT-XXXXX --dry-run    # preview
python3 JiraIncidentFetch.py --close LIT-XXXXX[,LIT-YYYYY]  # close specific
python3 JiraIncidentFetch.py --close-all                    # whole queue, asks 'yes'
# extras: --comment "text", --resolution Fixed (auto-retried only if Jira demands it)
```

Outputs land beside the script in `jira_incident_reports/{reports,logs}/`, timestamped per run (base overridable via `INCIDENT_REPORT_DIR`).

## Key facts

- **API**: Jira Cloud v3, Basic auth email+token (env `JIRA_EMAIL`/`JIRA_TOKEN`/`JIRA_URL`, OpsBot defaults hardcoded). Search uses `POST /rest/api/3/search/jql` with `nextPageToken` paging — the legacy `/search` endpoint was removed by Atlassian in 2025.
- **Closes appear as OpsBot** (`opsmail@atypon.com`) in Jira history, not as Laith.
- **Two JQLs**: default = queue (labels `= Closed_Incident`, open, assignee OpsBot account id `712020:e0ca7355...`); `ACTIVE_JQL` (labels `!=`) feeds the second "Active Incidents" table in the HTML.
- **HTML auto-switches**: all-open result → queue view (age tiles, age-colored oldest-first table, >1d yellow / >3d red); mixed → analytical view (resolve times, type×product heatmap). Queue view is the approved format.
- **Jira field IDs**: Client = `customfield_10210`, RCA Status = `customfield_10230`; product also in `<X>_Issues` labels; Moni Bot summaries parse as `Incident triggered for <type> - <detail>` (or `... on <host>`).

## Email gotchas (hard-won)

| Symptom | Reality |
|---|---|
| "Email sent" but nothing arrives from laptop | Laptop has NO outbound SMTP (port 25 and 587 blocked); message sits deferred in local postfix. Use the prod102 tunnel. |
| Sent from prod102, not received "yet" | Wiley delivers with ~3 min delay — wait before debugging. `mailq` empty on prod102 = it left successfully. |
| Suspected spam filtering | `user@laptop-hostname` senders are spam bait; script defaults From to `ljanaideh@atypon.com` (override `--from`). `literatum@prod102.int.atypon.com` is the fastest-delivering sender. |

Recipient default: `ljanaideh@wiley.com`.
