#!/usr/bin/env python3
"""Categorise the ops tickets by what the issue/task is about (rule-based on summary + type).
Rules are ordered: first match wins. Writes *_categorized.csv and prints the breakdown."""
import csv
import os
import re
from collections import Counter, defaultdict

HERE = os.getcwd()  # input/output CSVs are read and written in the current folder
import sys
# usage: categorize.py [input.csv] [output prefix] [period label]
SRC = os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "ops_jira_6mo.csv")
OUT = sys.argv[2] if len(sys.argv) > 2 else "ops_jira_6mo_categorized"
PERIOD = sys.argv[3] if len(sys.argv) > 3 else "updated since 2026-03-24"

# (category, sub-category, regex) — first match wins, so specific rules go first
RULES = [
    # --- monitoring alerts / production incidents
    ("Production incidents & site outages", "Monitoring alert", r"^incident triggered|^\[firing|RCA for|^rca\b|crowdstrike|load average"),
    ("Production incidents & site outages", "Site / server down",
     r"\bis down\b|are down|\bdown\.?$|backstage server is down|backstages are down|can'?t start|not able to start|"
     r"failed to start|unavailable|OOM|memory|unreachable|disk space|ReqPoolLocked|load balancer|"
     r"403 forbidden page|500 internal server error when|ingestion is down|solr is down|no space|can(no|')?t reach|very slow|timed? ?out|outages?\b"),

    ("Production incidents & site outages", "Frequent restarts / OOM", r"restarts|keeps restarting|outofmemory|\bheap\b"),

    # --- test/stag database refreshes and DB moves
    ("Environment DB refresh & DB moves", "Flexclone / byteclone rebuild",
     r"flex ?clone|byte ?clone|needs to be rebuilt|\brebuilt\b"),
    ("Environment DB refresh & DB moves", "Database server move",
     r"\bsql\d{2}\b|database move|move .*database|migrate .*database|db migration|db server"),

    # --- proxmox host maintenance (VM move-outs before firmware upgrades)
    ("Infrastructure & ops tooling", "Proxmox VM moves / firmware maintenance",
     r"move out|\bpve\d+|firmware"),

    # --- admin
    ("Admin, meetings & misc", "Worklogs / time", r"worklog|log(ging)? time|time log"),

    # --- read-only mode / DB cluster migration testing
    ("Read-only mode & DB migration", "RO mode / rehearsal testing",
     r"new db cluster migration|\bRO\b|_ro\b|ro-mode|read-?only|rorehearsal|ro rehearsal|reh[ea]+r?sal"),
    ("Read-only mode & DB migration", "Database move / clone",
     r"sql3x|sql4x|flex clones|db clone|new created dbs|login failed on"),

    # --- build / deploy pipeline failures
    ("Build, patch & deploy failures", "Product patch failure",
     r"product patch|patch lit\d+ ran|patch(ing)? fail|patch .* failed|failed .*patch|lit\d{4,5}(\.sql)? patch|productpatch"),
    ("Build, patch & deploy failures", "Solr deploy / restore failure", r"solr ?deploy|solr restore"),
    ("Build, patch & deploy failures", "DB upgrade failure", r"dbupgrade|upgrade db failed|dtssetter|dts runs failed"),
    ("Build, patch & deploy failures", "Build / Styleguide failure",
     r"actions? failed|deployments? (is |are )?failing|patches are failing|db upgrade failure|productdeploy failure|deploy(ment)? failure|forward merge failed|build fail|build failed|\bSG\b|style ?guide (failure|failed)|styleguide fail|productbuild|compil|deployment .*failed|"
     r"deployment failed|deploy failed|redeployment failing|hostwaitforwebserver|hostessential|consumer ?deploy|"
     r"productconsumer|atm deploy|qemu|builddockerdatabaseimage|pr plan failed|cms branch creation failed|"
     r"updatestatuspage|fs clone action failed"),

    # --- PCMS migration
    ("PCMS migration", "PCMS migration",
     r"pcms migration|migrate .* to pcms|passport cms migration|pcms \|.*migration|trial pcms|pcms launch|apps? pcms|lcms/pcms|"
     r"digital objects not migrated|ascb pcms|uchicago pcms|mag pcms"),

    # --- content reprocessing, indexing, slices
    ("Content reprocessing & indexing", "Reprocess / indexing",
     r"reprocess|re-?index|indexing|index(ed)? content|missing ratio|jb core|do core|content slice|"
     r"blob cache|migrate content formats|restoring the new indexed solr|solr is not synched|review the solr|"
     r"toc heading|content generation"),

    # --- deposits & external integrations
    ("Content deposits & integrations", "Deposit / feed / external integration",
     r"deposit|crossref|crossmark|portico|pubmed|doaj|\bmarc\b|ai licensing|webdav|elsevier|ex libris|oai-pmh|getftr|"
     r"researchgate|web of science|\bwos\b|isi\) linking|kbart|counter 5|niso crec|google.scholar|meru|oa integration"),

    # --- content operations seen in the older tickets
    ("Content reprocessing & indexing", "Content export / transfer / moves",
     r"export|transfer|move .*(journals?|issues?|content)|live to staging|delta processing|upload zips|sitemap"),
    ("Content reprocessing & indexing", "Run tool / script on content",
     r"run (the )?tool|run .*jsp|run .*detect|updatearticlemetrics|run .*query"),

    # --- environments and instance placement
    ("Infrastructure & ops tooling", "Environment setup / bring-up",
     r"bring(ing)? up|brining|bring .* up|create an environment|pre-?prod(uction)? site|deployment of .* site|"
     r"report(s)? (db|database)|set ?up .* (db|database)|test env(ironment)? up"),
    ("Infrastructure & ops tooling", "Instance moves / placement",
     r"move .*(instance|web\d+)|out of web\d+|\bweb\d{2,3}\b"),

    # --- access requests phrased as permissions/users
    ("Access, whitelisting & SSO", "Admin / console access",
     r"permission|\bSA role|access rights|cross site db query|access .*action/alist|action/alist|user for .* (sa|permission)|create a user"),

    # --- payments / e-commerce and small site behaviour settings
    ("Feature enablement & site configuration", "E-commerce / payments",
     r"braintree|stripe|e-?commerce|woocommerce|shopping cart|price"),
    ("Feature enablement & site configuration", "Property / registry / feature toggle",
     r"redirect|maintenance page|deployconf|theme"),
    ("Admin, meetings & misc", "Meetings / admin", r"time tracking|training|readme"),

    # --- releases: off-schedule + component upgrades first
    ("Releases, upgrades & branches", "Off-schedule deployment", r"off[- ]?schedul"),
    ("Releases, upgrades & branches", "Component upgrade (Axel / Solr / Styleguide)",
     r"axel|pug ?renderer version|upgrade pug|solr 9|deploy_version|styleguide version|vaadin|spring security"),

    # --- access, whitelisting, auth/SSO
    ("Access, whitelisting & SSO", "IP whitelisting", r"whitelist|zuperadmin|ip address|\bips?\b|trusted proxy|nat ips|without vpn"),
    ("Access, whitelisting & SSO", "Admin / console access",
     r"developer (access|role)|admin rights|super ?admin|\bSA access|grant me|request(ing)? access|access (to|on|for)|atypon support console|access on|ldap|"
     r"account lockout|2fa|sendgrid|password"),
    ("Access, whitelisting & SSO", "SSO / login / identity",
     r"sso|saml|shibboleth|openathens|idp|log ?in|login|identit|connect|azure"),

    # --- client lifecycle
    ("Client onboarding / departure", "Site launch / departure / cleanup",
     r"depart|decommission|create .* product|shut ?down|shutting down|launch (checklist|plan)|site launch|set up .*site|"
     r"setup test environment|new site|drop .* beta|clean ?up|cleaning|remove old|deprecated|delet"),

    # --- meetings / admin
    ("Admin, meetings & misc", "Meetings / admin",
     r"meeting|coordination|^engineer$|general bug fixing|billing|log time"),

    # --- infrastructure & ops tooling
    ("Infrastructure & ops tooling", "VMs / servers / tooling",
     r"lts environment|gaia move|\bgke\b|dc cluster|kafka|db and fs|sharded|fresh clone|copy db|local env|\bpve\d|vm\b|vms\b|ssh|cassandra|keyspace|puppet|ansible|terraform|proxmox|fs clone|rbackstage|deploy ?server|"
     r"kibana|jira tickets|jira .*cli|restart .*server|backup|noclassdeffound|lr tool|cip environment|preprod deploys|"
     r"performance testing|locust|fake usage data|consumer is paused|saxon license|review the enabled"),

    # --- feature enablement / configuration
    ("Feature enablement & site configuration", "Digital Objects (DO)", r"digital object|(?-i:\bDOs?\b)|oembed|exam"),
    ("Feature enablement & site configuration", "AI features",
     r"\bai\b|ai companion|summar|semantic search|caption|gen-ai"),
    ("Feature enablement & site configuration", "fields.xml / taxonomy / author standardisation",
     r"fields\.?xml|fields xml|taxonomy|author standardi[sz]ation|mesh props"),
    ("Feature enablement & site configuration", "Property / registry / feature toggle",
     r"^(enable|disable)|\b(enable|disable)[sd]? |set |setting|configure|configuration|propert|registr|upload handler|"
     r"handler|rest api|cms api|license|alert|price upload|revision|pubversion|friendly url|cookie|segment|feed|"
     r"monitoring rule|e-?reader|epub|pdf|facet|worklist|smart groups|abuse|audit|cf stream|cloudflare|"
     r"^revert|revert (changes|the|enabling)"),

    # --- releases, upgrades, branches (generic)
    ("Releases, upgrades & branches", "Major / minor release & rehearsal",
     r"major|minor release|\bmjr\b|\bmr\b|26\.1|2610|2410|2210|24\.1|25\.1|group ?[0-3]|gr-?[0-3]|gr3|"
     r"branch|midtierbeta|daily deployment|rebuild|trunk|staging products status|load tests|stress test|"
     r"preparation|psta|roll ?back|\bdeployments?\b|redeploy|upgrade .*sites|wave ?\d|skip next rebuild|bring .* (back|up)|deploy .* on|post release|rollout|"
     r"xml files related"),

    # --- functional bugs & regressions reported against sites
    ("Functional bugs & regressions", "Release regression", r"regression"),
    ("Functional bugs & regressions", "Site functionality bug", r"."),  # applied only to Bug/Inquiry
    ("Client change requests", "Small client change", r"."),              # remaining tasks/improvements
]
COMPILED = [(c, s, re.compile(p, re.I)) for c, s, p in RULES]

OTHER = ("Admin, meetings & misc", "Other")


def categorise(summary, itype):
    for cat, sub, rx in COMPILED:
        if sub == "Site functionality bug":
            if itype in ("Bug", "Inquiry"):
                return cat, sub
            continue
        if sub == "Small client change":
            return cat, sub
        if rx.search(summary):
            return cat, sub
    return OTHER


rows = list(csv.DictReader(open(SRC)))
# column names differ between the 6-month and 2-year files
INV = "Involvement"
CMT = "Comments by engineer"
# bugs that landed in a feature/release/change bucket are really site bugs
RELEASE_BUG = re.compile(r"regression|2610|26\.1|major|minor|mjr|\bmr\b|maintenance release|alpha|beta", re.I)
BUG_RECLASS = {"Feature enablement & site configuration", "Releases, upgrades & branches", "Client change requests"}
for r in rows:
    cat, sub = categorise(r["Summary"], r["Type"])
    if sub == "Site functionality bug" and RELEASE_BUG.search(r["Summary"]):
        sub = "Release regression"
    if r["Type"] in ("Bug", "Inquiry") and cat in BUG_RECLASS and sub != "Off-schedule deployment":
        cat = "Functional bugs & regressions"
        sub = "Release regression" if RELEASE_BUG.search(r["Summary"]) else "Site functionality bug"
    r["Category"], r["Sub-category"] = cat, sub

cols = ["Key", "Category", "Sub-category"] + [c for c in rows[0] if c not in ("Key", "Category", "Sub-category")]
rows.sort(key=lambda r: (r["Category"], r["Sub-category"], r["Updated"]), reverse=False)
with open(os.path.join(HERE, OUT + ".csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

by_cat = Counter(r["Category"] for r in rows)
by_sub = defaultdict(Counter)
for r in rows:
    by_sub[r["Category"]][r["Sub-category"]] += 1
for c, n in by_cat.most_common():
    print(f"{n:4}  {c}")
    for s, m in by_sub[c].most_common():
        print(f"        {m:4}  {s}")

# ---------------- HTML report ----------------
import html as _h

DONE = {"Closed", "Resolved"}
cats = [c for c, _ in by_cat.most_common()]

def owned(r):
    inv = r[INV]
    return any(x in inv for x in ("Assignee", "Past assignee", "Reporter", "Creator"))

summary_rows = []
for c in cats:
    rs = [r for r in rows if r["Category"] == c]
    subs = ", ".join(f"{s} ({n})" for s, n in by_sub[c].most_common())
    summary_rows.append(
        f'<tr><td><a href="#" data-cat="{_h.escape(c)}">{_h.escape(c)}</a></td><td class="n">{len(rs)}</td>'
        f'<td class="n">{sum(r["Status"] not in DONE for r in rs)}</td>'
        f'<td class="n">{sum(owned(r) for r in rs)}</td>'
        f'<td class="n">{sum(int(r[CMT]) > 0 for r in rs)}</td>'
        f'<td class="muted">{_h.escape(subs)}</td></tr>')

show = ["Key", "Category", "Sub-category", "Summary", "Status", "Type", INV,
        CMT, "Assignee", "Updated"]
body = []
for r in rows:
    body.append(f'<tr data-cat="{_h.escape(r["Category"])}"><td><a href="{r["URL"]}" target="_blank">{r["Key"]}</a></td>' +
                "".join(f"<td>{_h.escape(r[c])}</td>" for c in show[1:]) + "</tr>")

opts = "".join(f'<option>{_h.escape(c)}</option>' for c in cats)
page = f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Ops Jira Categories</title>
<style>
:root {{ --bg:#fff; --fg:#1d2433; --muted:#667085; --line:#e4e7ec; --accent:#0b5cad; --head:#f7f8fa; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#14171c; --fg:#e6e8eb; --muted:#98a2b3; --line:#2b313a; --accent:#6aa8ff; --head:#1b1f26; }} }}
body {{ background:var(--bg); color:var(--fg); font:14px/1.45 system-ui,sans-serif; margin:0; padding:24px 16px; }}
h1 {{ font-size:20px; margin:0 0 4px; }} h2 {{ font-size:15px; margin:22px 0 6px; }}
.muted {{ color:var(--muted); }} .n {{ text-align:right; font-variant-numeric:tabular-nums; }}
.wrap {{ overflow-x:auto; }}
table {{ border-collapse:collapse; width:100%; font-size:13px; }}
th, td {{ border-bottom:1px solid var(--line); padding:5px 8px; text-align:left; vertical-align:top; }}
th {{ background:var(--head); white-space:nowrap; }}
#t th {{ position:sticky; top:0; cursor:pointer; }}
a {{ color:var(--accent); }}
.controls {{ display:flex; gap:8px; flex-wrap:wrap; margin:8px 0; }}
select, input {{ padding:6px 10px; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); }}
input {{ flex:1; min-width:200px; max-width:420px; }}
</style></head><body>
<h1>Ops tickets by category</h1>
<div class="muted">atypon Jira · {PERIOD} · {len(rows)} tickets · categories are rule-based on the ticket summary</div>
<h2>Summary</h2>
<div class="wrap"><table><thead><tr><th>Category</th><th class="n">Tickets</th><th class="n">Still active</th>
<th class="n">Engineer owned*</th><th class="n">Engineer commented</th><th>Breakdown</th></tr></thead>
<tbody>{"".join(summary_rows)}</tbody></table></div>
<div class="muted" style="margin-top:4px">*Assignee (current or past), reporter or creator. Click a category to filter the list.</div>
<h2>Tickets</h2>
<div class="controls"><select id="cat"><option value="">All categories</option>{opts}</select>
<input id="q" placeholder="Filter by key, summary, status, role…"><span id="cnt" class="muted"></span></div>
<div class="wrap"><table id="t"><thead><tr>{"".join(f"<th>{_h.escape(c)}</th>" for c in show)}</tr></thead>
<tbody>{"".join(body)}</tbody></table></div>
<script>
const q=document.getElementById('q'), sel=document.getElementById('cat'), cnt=document.getElementById('cnt');
const trs=[...document.querySelectorAll('#t tbody tr')];
function apply(){{const v=q.value.toLowerCase(), c=sel.value; let n=0;
  trs.forEach(r=>{{const ok=(!c||r.dataset.cat===c)&&r.textContent.toLowerCase().includes(v); r.style.display=ok?'':'none'; if(ok)n++;}});
  cnt.textContent=n+' shown';}}
q.addEventListener('input',apply); sel.addEventListener('change',apply);
document.querySelectorAll('a[data-cat]').forEach(a=>a.addEventListener('click',e=>{{e.preventDefault();sel.value=a.dataset.cat;apply();document.getElementById('t').scrollIntoView();}}));
document.querySelectorAll('#t th').forEach((th,i)=>th.addEventListener('click',()=>{{
  const tb=th.closest('table').tBodies[0], asc=th.dataset.asc!=='1'; th.dataset.asc=asc?'1':'0';
  [...tb.rows].sort((a,b)=>{{const x=a.cells[i].textContent,y=b.cells[i].textContent,nx=+x,ny=+y;
    return (isNaN(nx)||isNaN(ny)?x.localeCompare(y):nx-ny)*(asc?1:-1);}}).forEach(r=>tb.appendChild(r));}}));
apply();
</script></body></html>"""
open(os.path.join(HERE, OUT + ".html"), "w").write(page)

print()
print(f"{'Category':42} {'All':>4} {'Active':>6} {'Owned':>5} {'Cmtd':>5}")
for c in cats:
    rs = [r for r in rows if r["Category"] == c]
    print(f"{c:42} {len(rs):4} {sum(r['Status'] not in DONE for r in rs):6} {sum(owned(r) for r in rs):5} "
          f"{sum(int(r[CMT])>0 for r in rs):5}")
