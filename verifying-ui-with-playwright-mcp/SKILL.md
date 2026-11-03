---
name: verifying-ui-with-playwright-mcp
description: Use when checking a web page visually from Claude Code with the mcp__playwright__* tools — reproducing a reported layout/styling bug, confirming a CSS or template fix on a local dev server, or taking screenshots of a site you just built. Also when a Playwright screenshot "cannot be found", a fix "did not apply" after restart, or a Bash pkill kills the tool shell.
---

# Verifying UI with the Playwright MCP tools

## Overview

Tests prove behaviour; only a rendered screenshot proves layout. The Playwright MCP tools (`mcp__playwright__browser_*`) drive a persistent Chromium: cookies survive between calls, and every file it writes lands in **its own cwd**, not the Bash cwd.

## Where the files are (checked 2026-09-14)

| Tool output says | Actual path |
|---|---|
| `./login.png` | `~/Downloads/login.png` (the MCP server's cwd = the directory the Claude session started in) |
| `.playwright-mcp/page-*.yml`, `console-*.log` | `~/Downloads/.playwright-mcp/` |

Read screenshots with the `Read` tool (renders PNG). Delete the PNGs and `.playwright-mcp/` when done — they litter the user's Downloads. Never `find /` for a missing file; it runs for minutes and gets backgrounded.

## Workflow

1. **Load tools once**: `ToolSearch select:mcp__playwright__browser_navigate,mcp__playwright__browser_take_screenshot,mcp__playwright__browser_fill_form,mcp__playwright__browser_click,mcp__playwright__browser_snapshot,mcp__playwright__browser_close`.
2. **Start the server detached** from Bash: `nohup npm start > $SCRATCH/server.log 2>&1 &` then `sleep 1.5; curl -s -o /dev/null -w '%{http_code}\n' localhost:3000/login`.
3. **Detect a stale session before screenshotting**: the navigate result prints `Page URL:`. If it differs from the URL you asked for (asked `/login`, got `/dashboard`), the browser is still logged in from an earlier call, possibly as another role. Click the logout form button (`form.userbox button` or equivalent) and navigate again; only then log in as the role under test.
4. **Fill and submit with CSS selectors** as `target` (`input[name=username]`, `button[type=submit]`) — no snapshot round-trip needed. `fill_form` then `click` must be separate, sequential calls.
5. **Screenshot → Read → judge**, with `fullPage: true` when the bug may be below the fold. A "Console: N errors" line in the navigate result usually is just `/favicon.ico` 404 — confirm in the console log rather than assume.
6. **Fix, restart, re-verify** — restart with `pkill -f '[s]rc/server.js'` (bracket trick; a plain `pkill -f 'src/server.js'` matches the Bash tool's own `bash -c` line and kills the shell, exit 144). `kill $(lsof -ti:3000)` also works.
7. **Prove the new CSS is live before judging the fix**: static files are often served with `max-age`; the old sheet stays cached across restarts and the fix looks "not applied" (a new grid class renders as plain block → columns stack). `curl -s localhost:3000/public/style.css | grep -c <new-class>` and add a `?v=<boot timestamp>` to the stylesheet link so it never recurs.
8. **Optional numeric check** via `browser_evaluate`: `el.scrollWidth - el.clientWidth` on the card vs the table wrapper tells a real overflow apart from an intended in-card scrollbar.
9. `browser_close`, remove the PNGs, commit.

## Common mistakes

| Mistake | Reality |
|---|---|
| Judging a fix from the first post-restart screenshot | It may be the cached stylesheet. Step 7 first. |
| Trusting `overflow-x:auto` as the fix | It contains the table but clips buttons behind a scrollbar; drop a column or widen the grid track so it fits. |
| Screenshot at one viewport | The MCP viewport is ~900px CSS; the user's window is likely wider. Fix for both, state which you checked. |
| Reading the JSONL task output file of a subagent to "see progress" | Overflows context. Wait for the notification. |

## Real-world impact

2026-09-14, student-portal admin/students: the six-column table pushed its grid card wide, Remove buttons spilled out. First post-fix screenshot looked "fixed" only because the stale sheet made the grid stack. Cache-busting + `min-width:0` + fewer columns gave the real fix; two restarts and four screenshots total.
