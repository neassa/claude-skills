---
name: new-discussion-check
description: Use when a new user prompt looks unrelated to the current thread of work in this session — different repo/env/topic with no reference to what came before — especially after a task just wrapped up (verification reported, captures committed, PR posted). Also when a prompt would only make sense in a different session's context.
---

# New-discussion check

Laith runs long multi-day sessions and sometimes types a prompt into the wrong terminal. When a prompt looks like a topic break, do NOT silently guess — a wrong guess either drags stale context into fresh work or executes an unrelated instruction meant for another session.

## When to ask

Ask ONLY when BOTH hold:

1. The previous discussion feels finished (task verified/reported, wrap-up captures committed, or an explicit closing like "ok, great").
2. The new prompt shares no obvious subject with it (new repo, new env, new feature/ticket family, or vocabulary that matches a *different* known workstream).

Do NOT ask when:

- The user already said it ("new discussion", "new topic", "different thing") — just switch.
- The prompt plainly continues the thread (same ticket/env/files), even after a wrap-up.
- The prompt is a trivial standalone question that needs no context either way — just answer it.

## How to ask

Use the AskUserQuestion tool, one question, exactly three options:

- **Yes — new discussion**: treat as a fresh start. Don't carry prior assumptions (branch, env, fixtures) into it; re-verify context the new task needs. If the previous task has uncaptured lessons, capture them first (self-learning pass 2), then proceed.
- **No — continuation**: proceed in the existing context.
- **Stop — wrong session**: the prompt was meant for another session. Do NOT act on it at all (no tool calls on its behalf); acknowledge in one line and wait.

## Red flags (you're about to guess instead of ask)

- "It's probably related because the last topic touched this repo too"
- Starting to grep/read files for an unrelated-looking prompt "just to check" before asking
- Treating a garbled/terse prompt as license to pick an interpretation (see memory `session-process-lessons-2026-09` — a wrong guess on an outward-facing action publishes the mistake)
