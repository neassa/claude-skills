#!/usr/bin/env python3
"""SessionStart hook for the self-learning system. Prints 3 status lines, writes nothing.

Line 1: personal skills untouched >90 days (names + dates) — re-verify before relying.
Line 2: lessons committed to the ~/.claude repo in the last 7 days (capture-rate metric).
Line 3: memory dirs found on disk vs tracked in git — a mismatch means the whitelist
        .gitignore no longer matches the harness layout and captures are NOT versioned.
"""
import datetime, os, subprocess

CLAUDE = os.path.expanduser("~/.claude")
SKILLS = os.path.join(CLAUDE, "skills")
VENDOR_PREFIXES = ("aws-", "amazon-bedrock", "launch-with-aws", "signing-in-to-aws")

def run(args):
    try:
        return subprocess.run(args, cwd=CLAUDE, capture_output=True, text=True,
                              timeout=10).stdout.strip()
    except Exception:
        return ""

# 1: stale personal skills (mtime; git snapshot too young to be the signal yet)
stale, personal = [], 0
today = datetime.date.today()
for d in sorted(os.listdir(SKILLS)):
    p = os.path.join(SKILLS, d, "SKILL.md")
    if not os.path.isfile(p) or d.startswith(VENDOR_PREFIXES) or d.endswith("-workspace"):
        continue
    personal += 1
    m = datetime.date.fromtimestamp(os.path.getmtime(p))
    if (today - m).days > 90:
        stale.append(f"{d} ({m})")
print(f"skills: {personal} personal · stale >90d: {', '.join(stale) if stale else 'none'}")

# 2: capture-rate metric
n = run(["git", "log", "--oneline", "--since=7.days"])
print(f"lessons committed last 7d: {len(n.splitlines()) if n else 0}")

# 3: whitelist drift detector
found = 0
for root, dirs, files in os.walk(os.path.join(CLAUDE, "projects")):
    if "MEMORY.md" in files:
        found += 1
    dirs[:] = [x for x in dirs if x != "node_modules"]
tracked = sum(1 for l in run(["git", "ls-files"]).splitlines() if l.endswith("MEMORY.md"))
flag = "" if found == tracked else "  <-- DRIFT: some memory is NOT versioned, fix .gitignore"
print(f"memory dirs: {found} found / {tracked} tracked{flag}")
