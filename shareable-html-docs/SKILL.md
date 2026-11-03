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

Stay inside that Markdown subset: no nested tables, no HTML blocks, no reference-style links, no more than one list level.
Verify after every build (below); the cheap assertions are heading count, table count, code-block count, that every contents
link resolves to an existing id, no console errors, and `document.documentElement.scrollWidth <= innerWidth`.

## Verify before sharing (mandatory)

Playwright blocks `file://` — serve locally, then test the real behavior:
```bash
python3 -m http.server 8377 --bind 127.0.0.1 &   # from the doc's folder
```
With Playwright: navigate, assert every `img.naturalWidth > 0`, click an image → overlay `.open` present and lightbox img loaded, Esc and overlay-click close it, zero console errors. Kill the server after.

## Common mistakes

| Mistake | Fix |
|---|---|
| "Open full size" link on a data: URI | In-page lightbox (rule 1) |
| Image embedded in both `<a>` and `<img>` | Embed once, lightbox reuses src |
| Verifying with `--dump-dom` only | Click-path test via Playwright over localhost |
| `convert in.svg out.png` garbled text | Headless Chrome screenshot |
| Build script left in session scratchpad | Store it beside the generated .html |
