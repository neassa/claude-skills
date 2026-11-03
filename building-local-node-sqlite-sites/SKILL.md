---
name: building-local-node-sqlite-sites
description: Use when asked to build a small website, portal, dashboard, or CRUD app that runs locally with a local database on a machine with Node 22.13+ — especially when npm installs are unwanted or offline, or the user just says "local website with local DB". Also when node --test or node:sqlite behave unexpectedly (MODULE_NOT_FOUND on a test directory, ExperimentalWarning noise).
---

# Building local Node + SQLite sites (zero dependencies)

## Overview

Node 22.13+/24 ships everything a local CRUD site needs: `node:http`, `node:sqlite` (`DatabaseSync`), `node:crypto` (scrypt), `node:test`, `fetch`. No `npm install`, no native build, one DB file. Reference implementation: `~/Downloads/student-portal` (login, roles, CRUD, seed, 15 tests) — copy its structure if it still exists.

## Recipe

**Stack:** `node:http` + hand-rolled regex router · `node:sqlite` file DB (WAL, foreign_keys on) · server-rendered HTML via an auto-escaping tagged template · scrypt password hashes · random session ids stored in a `sessions` table, sent as `HttpOnly; SameSite=Lax` cookies · POST-only mutations · one-shot flash messages in a 30 s cookie.

**Layout:** `src/server.js` (bind 127.0.0.1) · `src/app.js` (router + auth guard + static) · `src/db.js` (schema, `CREATE TABLE IF NOT EXISTS`) · `src/auth.js` · `src/html.js` · `src/pages/*.js` · `scripts/seed.js` (idempotent `INSERT OR IGNORE`, `--reset` flag) · `public/style.css` · `test/*.test.js` (in-memory DB, `listen(0)`, real `fetch`).

**package.json scripts (verified Node 24.14):**
```json
"start": "node --no-warnings=ExperimentalWarning src/server.js",
"seed":  "node --no-warnings=ExperimentalWarning scripts/seed.js",
"test":  "node --no-warnings=ExperimentalWarning --test 'test/**/*.test.js'"
```

**Escaping template (the one piece worth getting exactly right):**
```js
export function html(strings, ...values) {           // interpolations escaped
  let out = '';                                       // unless Raw or nested html``
  strings.forEach((s, i) => { out += s; if (i < values.length) {
    const v = values[i];
    out += v instanceof Raw ? v.value
         : Array.isArray(v) ? v.map(x => x instanceof Raw ? x.value : esc(x)).join('')
         : esc(v); } });
  return new Raw(out);
}
```
Arrays of nested `html\`\`` join with no separator, so `${rows.map(r => html\`<li>…</li>\`)}` just works.

## Gotchas (each cost a round-trip)

| Symptom | Fix |
|---|---|
| `node --test test/` → `MODULE_NOT_FOUND` | Node 24 treats the arg as a file. Use bare `node --test` (auto-discovers `*.test.js`) or a quoted glob. |
| `ExperimentalWarning: SQLite is an experimental feature` on every run | `--no-warnings=ExperimentalWarning` or `--disable-warning=ExperimentalWarning`; no `--experimental-sqlite` flag needed on 24. |
| Table in a half-width CSS grid card pushes the card wider, buttons spill out, page scrolls sideways | Grid items default to `min-width:auto`. Set `.grid > * { min-width: 0 }`, wrap tables in `overflow-x:auto`, and use a narrow-form / wide-table grid (`minmax(260px,320px) minmax(0,1fr)`) for admin list pages. Fewer columns beats scrolling. |
| Number input in a flex `.row` overflows its card | `label > input { width:100%; min-width:0 }`. |
| CSS fix "doesn't work" after restart | Static files served with `max-age=3600`; the browser kept the old sheet. Append `?v=<Date.now() at boot>` to the stylesheet link. Verify with `curl style.css | grep <new-class>` before blaming the CSS. |
| Sessions vanish / or unexpectedly persist across restarts | Sessions live in the DB, so they survive restarts. Fine, but remember it when re-testing login. |
| `pkill -f 'node src/server.js'` kills the Bash tool's own shell (exit 144) | Pattern matches the `bash -c` command line. Use `pkill -f '[s]rc/server.js'`. |
| Server started from a Bash call dies when the call ends | `nohup npm start > log 2>&1 &` then `sleep 1.5; curl -s -o /dev/null -w '%{http_code}' localhost:3000/login`. |

## Verification that counts

`npm test` green is necessary, not sufficient. Also: start the real server, `curl` every route as each role (check status + size), then screenshot in a browser (see verifying-ui-with-playwright-mcp). Dropping is blocked once graded, capacity is enforced, duplicates return a flash — each of these got an HTTP test.
