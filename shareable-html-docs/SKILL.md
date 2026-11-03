---
name: shareable-html-docs
description: Use when creating a single-file HTML doc/report/guide with embedded images or diagrams that will be shared (email, Slack, Confluence), when a clicked image opens a blank tab, when rendering SVG diagrams to PNG on Linux, when converting an HTML doc to PDF (print-to-pdf, page breaks, blank first page), or when a local HTML file's JavaScript needs verification before sharing.
---

# Shareable single-file HTML docs

Build a doc as ONE self-contained .html: images as base64 `data:` URIs, all CSS/JS inline. It must work from disk, attachments, or any file share — assume no server and no external requests.

## Core rules (each one was a real shipped bug)

1. **Never `window.open(img.src)` / `<a href="data:...">` for click-to-zoom.** Browsers block top-level navigation to `data:` URLs → blank tab. Use an in-page lightbox instead:
   ```html
   <style>.lb{position:fixed;inset:0;background:rgba(15,18,22,.93);display:none;z-index:1000;overflow:auto;cursor:zoom-out}
   .lb.open{display:block}.lb img{max-width:none;margin:1.5rem auto;display:block}</style>
   <script>(function(){var lb=document.createElement("div");lb.className="lb";
   var i=document.createElement("img");lb.appendChild(i);document.body.appendChild(lb);
   document.querySelectorAll("main img").forEach(function(m){m.addEventListener("click",function(){i.src=m.src;lb.classList.add("open")})});
   lb.addEventListener("click",function(){lb.classList.remove("open")});
   document.addEventListener("keydown",function(e){if(e.key==="Escape")lb.classList.remove("open")})})();</script>
   ```
2. **Embed each image ONCE.** Wrapping `<img src="data:...">` in `<a href="data:...">` doubles the file size. The lightbox reuses `img.src`, no second copy.
3. **Generate via a build script** (python: base64-encode files into an f-string template), keep the script next to the output so the doc is rebuildable. In f-strings, inject JS/CSS with literal braces via a post-build `page.replace("__TOKEN__", block)`, not inside the f-string.
4. Add `<link rel="icon" href="data:,">` to suppress the favicon 404 when someone serves the file.
5. `cursor:zoom-in` on clickable images; `max-width:100%` inline.

## SVG diagrams → PNG (Linux)

ImageMagick `convert` renders SVG text/CSS poorly. Use headless Chrome:
```bash
google-chrome --headless=new --disable-gpu --screenshot=out.png \
  --window-size=1500,900 --default-background-color=FFFFFFFF --hide-scrollbars "file://$PWD/in.svg"
```
Author diagrams as hand-written SVG (keep the .svg as editable source), then READ the rendered PNG to check for label collisions and arrows crossing boxes — fix coordinates and re-render.

## Reuse the converter, do not rewrite it

`~/Downloads/projects/focus-multi-env-plan/build-html.py` is a working Markdown-to-single-file-HTML converter: headings with
anchors and a two-column contents box, pipe tables, fenced code, one nesting level of lists, inline code/bold/links, images
as data URIs, the lightbox below. Copy it into the new doc folder, change the `DOCS` list to `(md, html)` pairs, write the
Markdown, run it. Two docs built this way 2026-09-22 in `~/Downloads/projects/focus-362-import-process/`.

The copy in `~/Downloads/focus-1.0-import-tool/docs/build-html.py` also handles `####` (the original stops at `###`, and a `####` line renders as a literal paragraph). After a rebuild, reload with a cache-buster (`?v=2`): Chrome served the stale page once.

Stay inside that Markdown subset: no nested tables, no HTML blocks, no reference-style links, no more than one list level.
Verify after every build (below); the cheap assertions are heading count, table count, code-block count, that every contents
link resolves to an existing id, no console errors, and `document.documentElement.scrollWidth <= innerWidth`.

## Verify before sharing (mandatory)

**`file://` works** — corrected 2026-09-24, three docs verified that way. The old "Playwright blocks file://" line was wrong for a FULLY self-contained doc (every image is an inline `data:` URI, so nothing is fetched cross-origin). Only spin up `python3 -m http.server 8377 --bind 127.0.0.1` if the page still references external files.

Assert, in one run: every `img.naturalWidth > 0`, click an image → overlay `.open` present and lightbox img loaded, Esc closes it, zero console/page errors, and **no horizontal overflow at BOTH 1280 and 400 px**.

**Claude in Chrome cannot open `file://`** (2026-09-29: "Can't interact with browser-internal or unparseable URLs") unless the extension's "Allow access to file URLs" is on. Serve the folder with `python3 -m http.server 8377 --bind 127.0.0.1` (run it as a background task and stop THAT task; never `pkill -f 'http.server'` from Bash, it matches and kills its own shell) and open `http://127.0.0.1:8377/<doc>.html`. `resize_window` does not shrink a maximised window (innerWidth stayed 1920), so run the 400 px check in a scripted headless browser (below).

**Markdown tables: a `|` inside a cell, even inside backticks, splits the row** (`slug|label` did). Say "separated by a vertical bar" instead, and assert every table row has the header's cell count.

**Test at 400 px or the worst bug hides.** `document.documentElement.scrollWidth > innerWidth` is false at the default viewport and true on a phone. Culprit is almost always a table: `width:100%` loses to the table's min-content width, so it bursts out of its padded container. Fix once, in the shared CSS:
```css
@media (max-width:640px) { table { display:block; overflow-x:auto; } }
```
When overflow does fire, find the guilty node instead of guessing — walk `main *` and report any `getBoundingClientRect().right > innerWidth + 1`.

**Launching chromium here (2026-09-24):** `playwright-core` in the repos is 1.61.1 and wants browser build 1228, which is NOT in `~/.cache/ms-playwright` (1208 and 1223 are). Launch fails with "Executable doesn't exist … chromium_headless_shell-1228". Pass an installed one explicitly:
```js
const {chromium} = require("/home/ljanaideh/Downloads/projects/aida-emdash-poc/node_modules/.pnpm/playwright-core@1.61.1/node_modules/playwright-core");
const b = await chromium.launch({ executablePath:
  "/home/ljanaideh/.cache/ms-playwright/chromium_headless_shell-1223/chrome-headless-shell-linux64/chrome-headless-shell" });
```
See also the `driving-playwright-directly` skill.

## Common mistakes

| Mistake | Fix |
|---|---|
| "Open full size" link on a data: URI | In-page lightbox (rule 1) |
| Image embedded in both `<a>` and `<img>` | Embed once, lightbox reuses src |
| Verifying with `--dump-dom` only | Click-path test via Playwright over localhost |
| `convert in.svg out.png` garbled text | Headless Chrome screenshot |
| Build script left in session scratchpad | Store it beside the generated .html |
