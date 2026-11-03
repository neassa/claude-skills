---
name: focus-regional-availability-testing
description: Use when testing, verifying, or diagnosing the focus regional-availability (geo-blocking) feature — REQ-043a/b, QA tickets AIDAFOCUS-342/343/344, region 403s ("content is unavailable in your region"), CF-IPCountry handling, or the regional denial logs on the focus-poc env.
---

# Testing focus regional availability (geo-blocking)

All facts verified live 2026-09-06 on focus-poc (MVP). Implementation: `custom/sites/focus/src/utils/regional-availability.ts` (+ spec `custom/docs/specs/regional-availability/tech.md`, unit tests `tests/unit/regional-availability.test.ts`).

## How it works (30 seconds)

Cloudflare geolocates the visitor's IP and attaches `CF-IPCountry` to the origin request; the app's `resolveVisitorLocation()` reads ONLY that header. Valid ISO alpha-2 → resolved; anything else → `undetermined` with a reason: `missing-ip` (no IP headers at all), `provider-unavailable` (IP present, no CF-IPCountry), `provider-unknown` (`XX`, `T1`, malformed like `DEU` — validated against a known set so bad codes fail CLOSED, never open). Undetermined + ANY active restriction (block OR allow list) → the same 403 as a confirmed block. Crawler UAs bypass the block but restricted responses always get `cache-control: private, no-store`. Preview bypasses entirely.

## Two test lanes — never confuse them

**Back door (simulation — you play Cloudflare):** the ALB is internet-facing (`http://focus-poc-node-nonprod-alb-1921061428.us-east-1.elb.amazonaws.com`), the app trusts `CF-IPCountry` from anyone. Works only while PR `#397` (CF-only ingress SG) stays unapplied — which is also a real bypass vulnerability, flagged on the tickets.

```bash
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Host: sciences-focus-poc.literatum.com" \
  -H "CF-IPCountry: DE" \
  "http://focus-poc-node-nonprod-alb-1921061428.us-east-1.elb.amazonaws.com/key-opinion/farah-31082026"
```

GOTCHA: `Host` must be the bare hostname — a scheme prefix or trailing space makes the app 404 (the posted AIDAFOCUS-343 comment carries this bug).

**Front door (real path — Cloudflare plays itself):** `https://<site>-focus-poc.literatum.com`. CF's own verdict is client-visible at `/cdn-cgi/trace` (`loc=JO`); `CF-IPCountry` itself is request-side only — no response ever shows it. Client-supplied `CF-IPCountry` through CF is OVERWRITTEN (verified: forged `US` from JO still 403'd, and the denial logged `outcome: 'JO'`). Use this lane for: what-CF-returns validation (VPN per country), the forgery/spoof security test.

**`missing-ip` is unreachable live**: the ALB stamps `X-Forwarded-For` on everything, and the task SG accepts only ALB traffic (direct-to-task port-forward connects but drops). Covered by the unit suite — cite it, don't chase it.

## Fixtures (sciences site unless noted)

- `key-opinion/farah-31082026` — action=block (JO/DE/GB/CN blocked; **US allowed** — that asymmetry is what makes the `USA`-invalid and lowercase-`us` tests decisive)
- `key-opinion/ko-sample-sci-protein-science-3799` — action=allow, JO only
- `key-opinion/therapies-for-diabetic-retinopathy…` — unrestricted control, **medicine** site
- `qa-test-item-req-043c-001` — 404s on both hosts (missing site assignment), don't use

Verify by BODY, never status alone: 403 → `error__heading` ("The content is unavailable in your region"); 200 → `article-page__title`. A tiny body = CF's own error, not the app's.

## Denial logs (AIDAFOCUS-344)

Only denials are logged: `[regional-availability] access denied { contentId, outcome (code|undetermined), reason, resolutionReason (only when undetermined), action }` — never the IP, by construction. Log group `/focus-poc-node/nonprod/focus-app`.

- Pretty table: `~/Downloads/projects/emdash-bench/bench/regional-denials.sh [minutes]` (needs AWS_PROFILE; SRE works for logs).
- CW GOTCHA: each line of the console.log object is a SEPARATE CloudWatch event — `--filter-pattern` returns only the header line; the script stitches header→`}`. Raw `--output text` looks scrambled; that's why.
- PII assertion runs on the RAW stream (a field-extract could hide things): `aws logs filter-log-events … --query 'events[].message' --output text | grep -oE '\b([0-9]{1,3}\.){3}[0-9]{1,3}\b'` → must be empty. Inject a marker (`X-Forwarded-For: 203.0.113.77`) on one denied request first.
- Scope caveats for the ticket: guarantee is app-level only (ALB access logs + CF logs do record IPs); denials-only = block counts, not a false-block rate.
- The `[csp] context.csp` WARNs flooding this log are unrelated Astro config noise — separate ticket.

## Ticket split as posted (2026-09-06)

342 = what CF returns (front door: trace + behavior, VPN per country — Farah). 343 = the full ALB simulation suite (resolved + undetermined). 344 = logging. Explainer artifacts: 342 https://claude.ai/code/artifact/9852d825-bfc9-41ba-a7f3-133c15699b25 · 343 https://claude.ai/code/artifact/fce1f48b-ef98-4be6-886f-906d0f0680eb

Related: `focus-poc-envs` (env facts, `#397`, GatingDebug env var `FOCUS_GATING_DEBUG=1` — not set as of 2026-09-06), `focus-node-db-access` (fixture queries), memory `req-043-geo-blocking-testability`.
