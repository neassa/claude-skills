#!/usr/bin/env python3
"""Build one person's Jira involvement list from raw MCP search pages.

Env (all required except OUT_DIR):
  SUBJECT_ACCT   Jira accountId of the person (lookupJiraAccountId)
  SUBJECT_NAME   display name as it appears in "@Name" mentions, e.g. "Jane Doe"
  RAW_DIR        folder with w*/page_*.json and roles/{past_assignee,text_only}.txt
  RECENT_SINCE   YYYY-MM-DD; rows updated on/after it get "In last 6 months" = yes
  OUT_DIR        where to write the CSV (default: cwd)
Output uses neutral labels ("Engineer") so the subject's name never appears in reports."""
import csv
import glob
import json
import os
import re

HERE = os.environ.get("OUT_DIR", os.getcwd())
RAW = os.environ["RAW_DIR"]
ACCT = os.environ["SUBJECT_ACCT"]
NAME = os.environ["SUBJECT_NAME"]
SINCE_6MO = os.environ["RECENT_SINCE"]
BROWSE = "https://jira.prod.atypon.com/browse/"
MENTION_RE = re.compile("@" + re.escape(NAME) + "|" + re.escape(ACCT))


def keys(name):
    path = os.path.join(RAW, "roles", name)
    return set(open(path).read().split()) if os.path.exists(path) else set()


issues = {}
for page in sorted(glob.glob(os.path.join(RAW, "w*", "page_*.json"))):
    for n in json.load(open(page))["issues"]["nodes"]:
        issues[n["key"]] = n          # windows don't overlap; dict also dedupes
past_assignee = keys("past_assignee.txt")
text_only = keys("text_only.txt")
print(f"issues={len(issues)} past_assignee={len(past_assignee)} text_only={len(text_only)}")


def acct(u):
    return (u or {}).get("accountId")


def name(u):
    if acct(u) == ACCT:
        return "Engineer"
    return u.get("displayName", "") if u else "Unassigned"


rows = []
for key, i in issues.items():
    f = i["fields"]
    comments = (f.get("comment") or {}).get("comments", [])
    mine = [c for c in comments if acct(c.get("author")) == ACCT]
    mentioned = [c for c in comments if acct(c.get("author")) != ACCT
                 and MENTION_RE.search(json.dumps(c.get("body"), ensure_ascii=False))]
    roles = []
    if acct(f.get("assignee")) == ACCT:
        roles.append("Assignee")
    if key in past_assignee:
        roles.append("Past assignee")
    if acct(f.get("reporter")) == ACCT:
        roles.append("Reporter")
    if acct(f.get("creator")) == ACCT:
        roles.append("Creator")
    if mine:
        roles.append("Commenter")
    if mentioned or key in text_only:
        roles.append("Mentioned")
    if not roles:
        roles.append("Watcher (CC)")
    created = (f.get("created") or "")[:10]
    rows.append({
        "Key": key,
        "Project": (f.get("project") or {}).get("key", ""),
        "Type": (f.get("issuetype") or {}).get("name", ""),
        "Summary": re.sub("|".join(map(re.escape, [NAME] + NAME.split())), "Engineer", f.get("summary", "")),
        "Status": (f.get("status") or {}).get("name", ""),
        "Priority": (f.get("priority") or {}).get("name", ""),
        "Involvement": ", ".join(roles),
        "Comments by engineer": len(mine),
        "Last comment by engineer": max((c["created"][:10] for c in mine), default=""),
        "Times @mentioned": len(mentioned),
        "Assignee": name(f.get("assignee")),
        "Reporter": name(f.get("reporter")),
        "Created": created,
        "Created half": f"{created[:4]}-H{1 if created[5:7] <= '06' else 2}" if created else "",
        "Updated": (f.get("updated") or "")[:10],
        "In last 6 months": "yes" if (f.get("updated") or "")[:10] >= SINCE_6MO else "no",
        "URL": BROWSE + key,
    })

rows.sort(key=lambda r: r["Updated"], reverse=True)
with open(os.path.join(HERE, "ops_jira_2y.csv"), "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
print("wrote ops_jira_2y.csv", len(rows))
