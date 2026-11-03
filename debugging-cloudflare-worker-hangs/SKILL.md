---
name: debugging-cloudflare-worker-hangs
description: Use whenever a site hosted on Cloudflare Workers (or Pages Functions) intermittently hangs, freezes, or loads forever for a subset of users — even if the report is vague, like "the site sometimes just spins". Strong signals - nothing in the browser console, network panel, or worker logs; hangs affect only logged-in/cookied users while incognito works; invocations show outcome=canceled with near-zero CPU, multi-minute wall time, and logs=0; a redeploy temporarily fixes it but the hang keeps coming back. Missing log lines are part of the signature, so do not rule this skill out because "the worker never received the request".
---

# Debugging Cloudflare Worker Hangs (Isolate Poisoning)

## Overview

On Workers, a request cancelled mid-I/O (client navigated away, aborted) can leave a promise that **never settles** — it neither resolves nor rejects. If that promise is shared at isolate scope (module cache, singleton, shared session/DB read), every later request awaiting the same path parks forever. `try/catch` cannot help: nothing throws.

**Core principle:** worker log silence does not mean the request never arrived. Logs and invocation events flush only when an invocation *ends* — a parked request is invisible *while* it hangs, then surfaces minutes later as `outcome=canceled, cpuMs≈0, wallMs=200000+, logs=0`. That line IS the signature.

## Recognize the signature

| Observation | Meaning |
|---|---|
| `canceled`, ~0 CPU, multi-minute wall, `logs=0` | Parked on a pre-work await that never settled |
| Only logged-in users affected; incognito works until login; deleting session cookie cures it | The blocked await is on a cookie-gated path; cookie host-scoping explains "site A broken, site B fine" on the same worker |
| Redeploy fixes it for hours | Fresh isolates; the poison re-forms |
| Some route classes hang, others fine on the same worker | Different awaits: anonymous/replica reads vs singleton/primary DB vs KV session — probe each class separately |

## Discriminating probes (before touching code)

1. **Client-state A/B** — same URL, only the cookie differs:
   - `curl` with and without a (even fake) session cookie: `curl -b "astro-session=x" URL` vs plain.
   - In the hung browser tab's console: `fetch('/', {credentials:'omit'})` vs `fetch('/', {credentials:'include'})` — same connection, same isolate; if omit resolves and include never does, the session path is the block.
2. **Probe route classes**, not just the homepage: anonymous page, admin route, API status route. Which hang and which answer localizes the wedged await.
3. **Verify the deployed artifact, not git**: `GET /accounts/{id}/workers/scripts/{name}` (API, wrangler OAuth token) and grep the bundle for the symbols a supposed fix should contain. Forks revert and re-apply; the bundle is truth.
4. **Deterministic repro** — abort requests mid-I/O in a loop:
   `for i in $(seq 40); do curl -s -o /dev/null --max-time 0.2 URL_WITH_DB_QUERY; done` then probe: if canaries now hang, you can wedge and verify fixes on demand.

## The fix (two layers — both, in this order)

```ts
const call = inner.doIO(args);
// 1. PREVENTION: anchor via waitUntil so a cancelled request still drives
//    the call to completion — the shared promise settles, no poisoning.
//    A never-settling promise never rejects; cleanup-on-error can't fire.
after(() => call.then(() => undefined, () => undefined)); // after() = waitUntil wrapper
// 2. CONTAINMENT: bounded await — stall becomes a loud, attributable error.
return await Promise.race([call, timeoutRejecting(15_000, label)]);
```

Apply at the driver/adapter layer (covers all call sites), fail closed (timeout = unauthenticated/500, never grants privileges).

## Catch it next time

- Per-request watchdog: `setTimeout(() => console.warn("[watchdog] still running after 10s: " + path), 10_000)`, cleared in `finally` — flushes when the guard/cancel ends the invocation.
- Late-settle telemetry: after a guard timeout, keep watching the call; "settled LATE after Nms" = slow, no follow-up line = genuinely never settled (runtime bug evidence).
- Real-time alerting needs an **external** canary probe (cron + abort-timeout) — logs cannot escape a wedged worker in real time.

## Common mistakes

- Reading "no CF log events" as "request never reached the worker" — check for late `canceled` events first.
- Hunting server-side diffs when the working/broken split follows cookies, host-scoped logins, or browser profiles.
- Fixing with try/catch or cleanup-on-error — never-settling promises trigger neither.
- Verifying a fix by reading git history instead of the deployed bundle.
