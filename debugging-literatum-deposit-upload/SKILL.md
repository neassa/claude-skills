---
name: debugging-literatum-deposit-upload
description: >-
  Use when driving or debugging a curl-based deposit/upload probe against a
  Literatum / Atypon site (hosts like *.literatumonline.com, pericles-stag,
  action endpoints such as /action/directSubscriptionUpload, /action/doLogin,
  /action/acceptTerms). Triggers whenever an upload returns an HTML error page,
  a 400/403/500, an empty response, or keeps redirecting to a login or
  "Accept Terms" page — and whenever the user is scripting a "Deposit ZIP
  submission" or subscription/content upload with cookies and headers. Reach for
  this even for one-off "why did my curl upload fail" questions on these hosts;
  it encodes the exact per-layer failure signatures (auth, terms gate,
  authorization, server error) that are easy to misread.
---

# Debugging a Literatum deposit / subscription upload probe

Literatum (Atypon's platform, e.g. Wiley Online Library `*.literatumonline.com`)
gates its `/action/*` endpoints behind several independent layers. A single
"the upload failed" symptom can come from any of them, and they look alike at a
glance — every failure tends to return a **full styled HTML page with HTTP 200
or a redirect**, not a clean API error. The job of this skill is to read the
response correctly so you fix the layer that actually failed instead of
guessing.

## The mental model: four layers, each with a distinct signature

A deposit request passes through these gates in order. Identify which one you're
stuck at *before* changing anything.

| Layer | Failure signature | Fix |
|---|---|---|
| 1. Authentication | Page shows `"login-status":"guest"`; POST to `doLogin` redirects back to `/action/showLogin` | Real credentials; confirm session cookie written |
| 2. File attachment (client-side) | Tiny upload byte count (hundreds of bytes, not the file size) | `-F file1=@"/abs/path"` — the `@` and an absolute path |
| 3. Accept-Terms gate | Response redirects to `/action/acceptTerms`; body has `name="accept-terms"` checkbox | `GET /action/acceptTerms?accept-terms=true&redirectUri=/` |
| 4. Service authorization | `HTTP 403` + `"error":{"code":403,"message":"Service:<endpoint>"}`; GET of the form is *also* 403 with no form | Grant the account the role/entitlement — **server-side, not fixable by curl** |
| 5. Deposit processing | `HTTP 500`, often a bare `500\n` body (Content-Length: 4) | Server-side exception — chase via logs using `cf-ray` / `x-webstats-respid` |

The single most useful habit: **always capture response headers (`-D`) and read
the embedded signals in the body**, never judge success from the absence of a
curl error.

## How to read a Literatum response

Every page embeds machine-readable state. Grep these out of the saved body
instead of eyeballing rendered HTML:

- `"login-status":"logged-in"` vs `"guest"` — the real auth state (in the
  `adobeDataLayer` push near the top of `<head>`).
- `"error":{"code":NNN,"message":"Service:..."}` — the real error, even when the
  visible card says something generic like "Error 400 / Invalid page request".
- `name="pbContext" content="...page:string:Action Error..."` — tells you the
  page *type* (Home Page, Action Error, Terms And Conditions, etc.).
- `name="service_name" content="..."` — which action handler responded.

From the headers file: the **first `HTTP/` status line** and any `location:`
header. With `-L`, curl follows redirects, so the *body* you saved may be the
page it landed on (e.g. the Terms page) — the headers reveal the redirect chain.

## The known-good probe sequence

Run these in order, verifying each before moving on. Set `BASE` and `ZIP` once.

```bash
mkdir -p ~/tmp
BASE="https://pericles-stag.literatumonline.com"
ZIP="$HOME/Downloads/your-deposit.zip"

# 1) Prime a session (guest cookies) — guest here is expected
curl -sS -L -c ~/tmp/cookies.txt -o ~/tmp/root.html -D ~/tmp/root-h.txt "$BASE/"

# 2) Log in with REAL credentials for an account that has deposit rights
curl -sS -L -b ~/tmp/cookies.txt -c ~/tmp/cookies.txt \
  -o ~/tmp/login.html -D ~/tmp/login-h.txt \
  --data-urlencode "login=REAL_USER@example.com" \
  --data-urlencode "password=REAL_PASSWORD" \
  "$BASE/action/doLogin"
grep -oE '"login-status":"[^"]*"' ~/tmp/login.html   # expect "logged-in"

# 3) Clear the Accept-Terms gate (one-time per account) — it's a GET form
curl -sS -L -b ~/tmp/cookies.txt -c ~/tmp/cookies.txt \
  -G -o ~/tmp/terms.html -D ~/tmp/terms-h.txt \
  --data-urlencode "accept-terms=true" \
  --data-urlencode "redirectUri=/" \
  "$BASE/action/acceptTerms"
grep -c 'name="accept-terms"' ~/tmp/terms.html       # expect 0

# 4) Upload — note the @ (attach file) and quoted absolute path (NOT ~)
curl -sS -L -b ~/tmp/cookies.txt -c ~/tmp/cookies.txt \
  -D ~/tmp/post-h.txt -o ~/tmp/post.html \
  -F format="Deposit ZIP submission" \
  -F file1=@"$ZIP" \
  "$BASE/action/directSubscriptionUpload"
grep -E '^HTTP/' ~/tmp/post-h.txt                    # want 200, not 302/403/500
grep -oE '"error":\{[^}]*\}' ~/tmp/post.html
```

`scripts/check_response.sh <headers-file> <body-file>` prints a one-line verdict
(which layer you're stuck at) — run it after any step instead of grepping by
hand.

## Gotchas that waste the most time

- **`-F file1=@~/path` does not work.** The shell only expands a leading,
  unquoted `~`; inside an `-F` value it stays literal. Use `$HOME` or an absolute
  path. And **without the `@`, curl sends the path as a literal string**, not the
  file — the tell is an upload byte count in the hundreds instead of the file
  size.
- **An empty (0-byte) response usually means an unfollowed redirect.** If you
  omit `-L`, a `302` writes nothing to the body. Add `-L` and `-D` and look at
  the `location:` header — it's very often `/action/acceptTerms`.
- **The visible error text lies; the `"error":{...}` block and HTTP status don't.**
  A page can render "Error 400 / Invalid page request" while the real status is
  `403` with `Service:directSubscriptionUpload`. Trust the status line and the
  data-layer error block.
- **403 on both GET and POST = entitlement, full stop.** If a plain GET of the
  upload endpoint returns 403 and renders no upload form (no `type="file"`, no
  `format` field, no per-request `prg...=<uuid>` token), the account lacks the
  role. No curl change fixes this — it needs a server-side grant.
- **500 with a bare `500\n` body = you got *in*.** This is progress from 403: the
  request passed authorization and the deposit handler threw. Verify the ZIP is
  valid (`unzip -t`, expect `manifest.xml` at the root for a deposit package),
  then escalate with the request identifiers below — the stack trace is
  server-side only.
- **Placeholders stay placeholders.** `login=XXXXXXX@test.com` authenticates
  nothing; the resulting "failure" is just an unauthenticated session, not a
  server problem.

## Escalating a server-side 500 (or any opaque failure)

The client can't see the stack trace. Collect these from the headers so whoever
has Literatum log access can find the exact request:

```
endpoint + method  (e.g. POST /action/directSubscriptionUpload)
cf-ray:            <value>
x-webstats-respid: <value>
date:              <value>   # the server timestamp
```

Before escalating, rule out the cheap client-side cause: the `format=` field.
Sending the human label (`"Deposit ZIP submission"`) instead of the internal
option `value` the real UI form uses can cause an unchecked lookup to throw a
500. If you can reach the actual upload UI, read its `<option value="...">` and
send that literal value.

## A valid deposit ZIP, for reference

A well-formed Literatum "Deposit ZIP" has `manifest.xml` at the archive root plus
the content tree, e.g.:

```
manifest.xml
<issue-id>/issue-files/<issue-id>.xml
<issue-id>/<article-id>/<article-id>.xml
```

If `unzip -t` fails or `manifest.xml` isn't at the root, fix the package before
blaming the server.
