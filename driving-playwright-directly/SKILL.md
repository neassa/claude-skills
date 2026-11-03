---
name: driving-playwright-directly
description: Use when a browser check must run without the Playwright MCP tools — the MCP server failed to connect or dropped mid-session — or when the check needs many cases (pages x viewports x states) with a repeatable pass/fail report. Covers resolving playwright inside a pnpm repo, launching an already-installed chromium, and measuring scroll/anchor behaviour. Also when `Cannot find module 'playwright'` or "Executable doesn't exist at .../chromium_headless_shell-NNNN".
---

# Driving Playwright directly from a node script

The MCP tools (see `verifying-ui-with-playwright-mcp`) are right for "look at this page". They are wrong when the server is down, or when the answer is a rate — *how often does this work* — because that needs dozens of cases and a report you can diff after a fix. Then write a standalone script and run it with the repo's own Playwright. No install, no MCP.

Verified 2026-09-21/22 on the aida-emdash worktree (Playwright 1.61.1, pnpm workspace).

## The two things that block you at the start

**1. `playwright` is not hoisted in a pnpm repo.** `@playwright/test` resolves, the bare package does not. Load it from pnpm's hidden hoist directory instead:

```js
import { createRequire } from "node:module";
const REPO = process.env.REPO ?? `${process.env.HOME}/Downloads/projects/aida-emdash-import`;
const require_ = createRequire(`${REPO}/package.json`);
const { chromium } = require_(`${REPO}/node_modules/.pnpm/node_modules/playwright/index.js`);
```

`node_modules/.pnpm/node_modules/` holds every workspace dependency, which is the same trick `focus-node-seed-fast.sh` uses via `NODE_PATH`.

**2. The browser build the library wants is usually not the one installed.** Playwright 1.61 asks for `chromium_headless_shell-1228`; the box had `chromium-1223`. Do not run `npx playwright install` — it downloads hundreds of megabytes and can outpace the pinned version. Point at what is there:

```js
const CHROME = process.env.CHROME_PATH ?? `${process.env.HOME}/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome`;
const browser = await chromium.launch({ executablePath: CHROME, args: ["--no-sandbox"] });
```

Check what exists with `ls ~/.cache/ms-playwright/`, and find the binary with `find <dir> -maxdepth 3 -name "chrome" -type f`. The path differs by build: `chrome-linux64/chrome` on newer ones, `chrome-linux/chrome` on older.

## Shape of a matrix script

One context per viewport, one page reused across cases, a flat object per case, a verdict function, counts, and a JSON file so the next run is comparable.

```js
const VIEWPORTS = [{ name: "desktop", width: 1280, height: 862 }, { name: "mobile", width: 390, height: 844 }];
const MODES = ["jump-from-top", "read-then-click", "fully-loaded"];   // how a real reader arrives
for (const vp of VIEWPORTS) {
  const ctx = await browser.newContext({ viewport: { width: vp.width, height: vp.height } });
  const page = await ctx.newPage();
  for (const slug of PAGES) for (const mode of MODES) {
    const row = { viewport: vp.name, slug, mode };
    try { /* navigate, dismiss consent, act, then measure */ }
    catch (e) { row.error = String(e.message).split("\n")[0].slice(0, 80); }
    results.push(row);
  }
  await ctx.close();
}
const verdict = (r) => r.error ? "error" : r.visible ? "lands OK" : `missed (${r.where})`;
console.log(`cases: ${results.length}`, results.reduce((a, r) => ((a[verdict(r)] = (a[verdict(r)] || 0) + 1), a), {}));
```

Run it with the Bash tool's `run_in_background` (a 96-case run took about 7 minutes) and collect it with `TaskOutput`. A foreground call dies at the 2-minute mark and you lose the run.

## Gotchas, each one cost a run

| Symptom | Cause and fix |
|---|---|
| `TypeError: r.viewport.padEnd is not a function` AFTER the whole matrix finished | the measured object returned a `viewport` number (`window.innerHeight`) and overwrote the loop's viewport label. Never reuse a loop label as a measured field name; the crash lands at reporting time, after all the work. |
| Every case times out at 30s on `click` | a modal (consent, HCP confirmation) intercepts pointer events. Dismiss it right after navigation: `const b = page.locator('button:has-text("CONFIRM")').first(); if (await b.count()) await b.click().catch(() => {});` |
| Results look worse after a fix, with bigger error distances | you may be measuring mid-animation. See the scroll section. |
| `download.saveAs` / `Target page … closed` | the MCP server dropped. That is the trigger for this skill, not something to retry. |

## A bot challenge beats this harness

Headless Chromium launched this way is challenged exactly like curl: the FOCUS poc/dev/uat hosts served Cloudflare's
"Just a moment..." at 403 to both on 2026-09-23. Do not burn attempts on User-Agent tricks. Verify from the other
side of the system (storage listing, database query) and have a human open one URL in their own browser. This harness
is for LOCAL sites and anything not behind a challenge.

## Measuring an in-page anchor jump

The question "does clicking this land the reader on the right thing" is not answerable by reading the DOM. Measure geometry after the click:

```js
page.evaluate((h) => {
  const el = document.getElementById((h || "").replace("#", ""));
  if (!el) return { noTarget: true };
  const r = el.getBoundingClientRect();
  const hh = Math.round(document.querySelector(".site-header")?.getBoundingClientRect().height ?? 0);
  return { top: Math.round(r.top), headerHeight: hh, innerHeight: window.innerHeight,
           visible: r.top >= hh && r.top < window.innerHeight,       // clears the sticky header
           underHeader: r.top >= 0 && r.top < hh,
           where: r.top < 0 ? "above" : r.top >= window.innerHeight ? "below" : "in",
           targetText: (el.textContent || "").replace(/\s+/g, " ").trim().slice(0, 45) };
}, href);
```

Three arrival patterns matter and fail differently: clicking on a cold page, scrolling to the marker first, and scrolling the whole page before clicking. Cold pages fail most, because lazy images below the fold have not loaded.

### What the numbers proved (FOCUS article template, 42 and 96 case runs)

| Version | Cases landing |
|---|---|
| marker links to the section heading | 8 of 42 |
| per-reference anchors plus `scroll-margin-block-start` | 37 of 42 |
| the above plus a re-anchor script using smooth scrolling | 34 of 42, worse |
| the above with `behavior: "instant"` | 42 of 42, then 96 of 96 |

Two causes, both needed fixing. **Images without intrinsic size** reflow after the jump, so the target slides away; and **`html { scroll-behavior: smooth }`** means the browser animates to a position computed before that reflow. A correction script must therefore re-apply the scroll for a couple of seconds after the click, and must use `behavior: "instant"` — an animated correction re-triggered on an interval restarts its own animation and the reader crawls down the page instead of arriving. Also give the anchor `scroll-margin-block-start` so it clears a sticky header, and stop correcting the moment the reader scrolls (`wheel`, `touchmove`, scroll keys).

## Verify the target text, not just the landing

Landing on *something* is half the check. Compare the visible label with the target it opens, across every link on the page:

```bash
curl -s -H "Host: medicine.localhost" http://127.0.0.1:4321/<path> |
  grep -o 'href="#ref-[0-9]*"' | wc -l      # count, then diff label vs target in python
```

On the FOCUS corpus that comparison found 71 mismatches, of which 50 were a real bug (grouped citations all pointing at the first reference) and 21 were the source data's own mislabelling. Without it, a 96/96 landing rate would have looked like success.

Related: `verifying-ui-with-playwright-mcp` (interactive, screenshots), `focus-content-export` (the FOCUS import pipeline this was built for).
