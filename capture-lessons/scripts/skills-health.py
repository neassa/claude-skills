#!/usr/bin/env python3
"""Report on a skills directory: staleness, frontmatter validity, description quality.

Usage:  python3 skills-health.py [SKILLS_DIR ...]
Defaults to the common locations if none is given. Read-only; writes nothing.
"""
import datetime, os, re, sys

DEFAULTS = ["~/.cursor/skills", "~/.claude/skills", "~/.agents/skills",
            ".cursor/skills", ".claude/skills", ".agents/skills"]
STALE_DAYS = 90
MIN_DESC = 60


def parse_frontmatter(text):
    """Minimal YAML-free frontmatter reader: returns dict of top-level scalars."""
    if not text.startswith("---"):
        return None, "no frontmatter"
    end = text.find("\n---", 3)
    if end == -1:
        return None, "unterminated frontmatter"
    body, out, key = text[3:end], {}, None
    for line in body.splitlines():
        m = re.match(r"^([A-Za-z_][\w-]*):\s*(.*)$", line)
        if m:
            key = m.group(1)
            out[key] = m.group(2).strip()
        elif key and line.strip():
            out[key] = (out[key] + " " + line.strip()).strip()
    return out, None


def check(root):
    root = os.path.expanduser(root)
    if not os.path.isdir(root):
        return
    print(f"\n=== {root} ===")
    names, problems, stale, nested_dirs = set(), [], [], []
    today = datetime.date.today()
    entries = sorted(d for d in os.listdir(root)
                     if os.path.isdir(os.path.join(root, d)) and not d.startswith("."))
    for d in entries:
        path = os.path.join(root, d, "SKILL.md")
        if not os.path.isfile(path):
            # A directory with no SKILL.md but containing skills is a nested collection
            # (a sync target, a vendored bundle). Not a broken skill -- note and move on.
            sub = os.path.join(root, d)
            nested = any(
                os.path.isfile(os.path.join(sub, x, "SKILL.md"))
                for x in os.listdir(sub)
                if os.path.isdir(os.path.join(sub, x))
            ) or any(
                os.path.isfile(os.path.join(sub, x, y, "SKILL.md"))
                for x in os.listdir(sub) if os.path.isdir(os.path.join(sub, x))
                for y in os.listdir(os.path.join(sub, x))
                if os.path.isdir(os.path.join(sub, x, y))
            )
            if nested:
                nested_dirs.append(d)
            else:
                problems.append(f"{d}: no SKILL.md")
            continue
        fm, err = parse_frontmatter(open(path, encoding="utf-8").read())
        if err:
            problems.append(f"{d}: {err}")
            continue
        name, desc = fm.get("name", ""), fm.get("description", "").strip("\"'>|- ")
        if not name:
            problems.append(f"{d}: missing name")
        elif name != d:
            problems.append(f"{d}: name is '{name}', should match the folder")
        if name in names:
            problems.append(f"{d}: duplicate name '{name}'")
        names.add(name)
        if not desc:
            problems.append(f"{d}: missing description")
        elif len(desc) < MIN_DESC:
            problems.append(f"{d}: description is {len(desc)} chars, too vague to trigger")
        elif not re.search(r"\buse\b|\bwhen\b", desc, re.I):
            problems.append(f"{d}: description does not say WHEN to use it")
        age = (today - datetime.date.fromtimestamp(os.path.getmtime(path))).days
        if age > STALE_DAYS:
            stale.append(f"{d} ({age}d)")

    print(f"skills: {len(entries) - len(nested_dirs)}")
    if nested_dirs:
        print(f"nested collections (skipped): {', '.join(nested_dirs)}")
    if stale:
        print(f"stale >{STALE_DAYS}d ({len(stale)}): {', '.join(stale)}")
    else:
        print(f"stale >{STALE_DAYS}d: none")
    if problems:
        print(f"problems ({len(problems)}):")
        for p in problems:
            print(f"  - {p}")
    else:
        print("problems: none")


def main():
    roots = sys.argv[1:] or DEFAULTS
    found = [r for r in roots if os.path.isdir(os.path.expanduser(r))]
    if not found:
        print("No skills directory found. Pass one explicitly.")
        return 1
    for r in found:
        check(r)
    return 0


if __name__ == "__main__":
    sys.exit(main())
