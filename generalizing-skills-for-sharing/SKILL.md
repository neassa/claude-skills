---
name: generalizing-skills-for-sharing
description: >-
  Use when turning internal/company-specific skills or memories into portable ones for
  people outside the project, when building or extending a shareable skills repo (e.g.
  agent-start-kit), when asked "can we share these skills", "will this work in Cursor",
  or before pushing anything skill-shaped to a repo others can read. Covers what to keep,
  what to strip, the leak check, cross-vendor portability, and importing MIT-licensed
  skill libraries.
---

# Generalizing skills for people outside the project

## The one rule people get wrong

**Keep the enforcement, strip the identifiers.**

When generalizing, the temptation is to keep the principle and drop the tables as
boilerplate. That inverts the value. Verified 2026-09-20: the first cut of
`capture-lessons` in `agent-start-kit` kept the principle ("capture at the moment, write
the failure") and dropped the two-pass structure, the routing table, the rationalization
table and the red flags. Laith immediately asked whether it had actually got the
self-learning skill. It had kept ~40%, and the missing 60% was the part that makes an
agent comply.

Generalizing removes WHO and WHERE. It must not remove HOW MUCH.

Always keep: step sequences, routing tables, rationalization/excuse tables, red-flag
lists, and the founding failure. A rule without its founding incident is advice, and
agents apply advice inconsistently.

## What to strip

| Strip | Keep instead |
|---|---|
| Person names | "the user", or delete the attribution |
| Company / product / repo names | the generic role ("a large multi-repo project") |
| Ticket IDs | the shape of the problem |
| Account numbers, instance/resource IDs, ARNs | "the account", "the instance" |
| Internal hostnames, internal URLs | "the environment", "the host" |
| Absolute paths under a home directory | a relative path, or a documented variable |
| Tool-specific plumbing (this harness's file layout) | the portable concept |

The concrete failure stays. "Two runs of about twenty-five minutes completed
successfully and changed nothing" is the useful part; which script and which ticket is
not.

## The leak check — run before every push

```bash
grep -rniE 'ljanaideh|laith|wiley|atypon|emdash|literatum|focus-poc|aidafocus|aisvc|LIT-[0-9]|909176971711|045369966266|i-0[0-9a-f]{8}|db-[A-Z0-9]{10}|/home/|Downloads|medicine-|sciences-|int\.atypon' . \
  --include='*.md' --include='*.sh' --include='*.py' | grep -v '^./.git/'
```

Empty output is the pass condition. **A zero score does not mean shareable**: a skill can
name no account and no host and still be entirely about an internal product. Judge the
TOPIC separately from the grep.

Also run the structural check:
```bash
python3 <repo>/skills/capture-lessons/scripts/skills-health.py <repo>/skills
```

## Variant: sharing with colleagues on the same product (verified 2026-09-25)

When the audience works *on* the product (e.g. the Literatum skills in `~/work/deploy-model/shared-skills/`), the product, repo and host names **are** the content, so keep them. Strip only:
- personal names and usernames (including ones found in code paths or logs → `<developer>`)
- your home paths → a documented variable (`$LIT_REPOS`)
- links to your private memory
- secrets (scan: `grep -rcE '(ghp_|gho_|github_pat_|AKIA[0-9A-Z]{12}|BEGIN (RSA |EC )?PRIVATE KEY|://[^/ :]+:[^/ @]+@)'`)

Make the shared copies the installed copies, so there's a single source and nothing drifts.

## Portability facts (verified 2026-09-20)

- Agent Skills is an **open cross-vendor standard** (agentskills.io), originally
  Anthropic's. A `SKILL.md` needs only `name` and `description`; `scripts/`,
  `references/` and `assets/` are optional.
- **Cursor reads `.cursor/skills/`, `.agents/skills/` AND `.claude/skills/`** plus the
  `~/` equivalents, for compatibility. **No conversion is needed.** Docs:
  cursor.com/docs/context/skills.
- For a repo shared between Cursor and Claude Code users, `.claude/skills/` is the
  safest single location, because both read it.
- Cursor-only optional frontmatter: `paths`, `disable-model-invocation`, `icon`, `color`.
  Harmless to other clients.
- **Subagents do NOT travel.** `~/.claude/agents/*.md` is Claude Code's own concept and
  no other client reads it. To share an agent-based workflow, rewrite it as a skill
  describing the method. Same for slash commands.

## Importing someone else's skill library

Prefer **fetch over vendor**. A vendored copy is a fork you must maintain and it goes
stale silently.

Ship a script that shallow-clones upstream and copies only its `skills/` folders,
skipping anything already present. If the licence is MIT (as Superpowers,
github.com/obra/superpowers, is), copy the upstream `LICENSE` next to the skills — MIT
requires the notice to travel with the copies. Check the licence before copying anything.

## Do not duplicate what already exists locally

A generalized copy living beside its richer internal original will drift, and then the
two contradict. When both are wanted, make the internal memory or skill point at the
shared one as the authority for the general rule, and keep only the project-specific
delta locally.

## Related

`self-learning` (capture discipline this feeds from), `writing-comments` (same
strip-the-identifiers instinct for prose), superpowers:writing-skills (authoring craft).
Repo: github.com/ljanaideh/agent-start-kit — see memory [[agent-start-kit-repo]].
