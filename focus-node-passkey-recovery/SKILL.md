---
name: focus-node-passkey-recovery
description: Use when a focus-poc-node admin user is locked out, can't sign in, or passkey enrollment fails (500 "Invalid origin" / PASSKEY_REGISTER_ERROR). Covers break-glass login links and the origin root cause.
---

# focus-poc-node passkey / login recovery

The node env has **no email provider**, so passkey resets and invites can't be self-served — an admin issues links by hand. WebAuthn `verify` has no email/feature gate, so you insert a token row directly.

**REQUIRED:** DB access via the `focus-node-db-access` skill (SSM tunnel + `focus_app`). All steps are DML only (never DDL).

## A. Locked out / lost passkey → issue a recovery link

```bash
cd ~/Downloads/projects/emdash-bench/bench
./focus-node-db.sh --profile … --exec python3 focus-node-passkey-recover.py user@wiley.com --clear-passkeys
# flags: --clear-passkeys (wipe old key), --expires-hours H (default 1), --print-only, --site medicine|science
```
Mints a single-use `recovery` magic-link → `…/_emdash/api/auth/magic-link/verify?token=…`. Token hashing must match EmDash: `hash = base64url_nopadding(sha256(raw 32 bytes))`, token = `base64url_nopadding(raw)`; expiry is an ISO string. Script's site map points at the **post-cutover hosts** (`medicine-focus-poc.literatum.com` / `sciences-focus-poc.literatum.com`). Passkeys live in table `credentials` (not "passkeys"); tokens in `auth_tokens`.

**Bulk re-mint** (used 2026-09-01 twice — hostname cutover, then again same evening after SafeLinks ate the first batch): one `--exec bash -c 'for e in …; do python3 focus-node-passkey-recover.py "$e" --clear-passkeys --expires-hours 24; done'` over a single tunnel. Re-minting a user invalidates their previous link. **Before any bulk `--clear-passkeys`, list who already re-enrolled** — `SELECT u.email, count(c.*) FROM users u LEFT JOIN credentials c ON c.user_id=u.id GROUP BY u.email;` — and exclude users with passkeys, or you lock them out again.

**Delivery format Laith uses (approved 2026-09-01):** never send clickable URLs. Hand out `user: <token>` per line plus ONE template line `https://medicine-focus-poc.literatum.com/_emdash/api/auth/magic-link/verify?token=TOKEN` — recipients assemble and PASTE into the browser.

**"Invalid token" / "keeps landing on the sign-in page"** = the single-use token was consumed or expired. At Wiley the culprit is **Microsoft Defender SafeLinks** (Outlook/Teams) or Slack unfurl fetching the URL first — confirmed live 2026-09-01: a 1h token's `auth_tokens` row was gone within minutes of being sent via Teams. Triage order: (1) verify the link is self-consistent locally — `base64url_nopad(sha256(base64url_decode(token)))` must equal the inserted `hash` (script bug if not); (2) `SELECT … FROM auth_tokens WHERE user_id='…'` — **0 rows = consumed** (bot or an earlier click), row present = the person is clicking a STALE link (each re-mint deletes prior links) or it expired. Re-mint and use the delivery format above.

## B. New user → delete + invite

`createInvite` rejects existing users, so to re-invite you must delete first. Pre-check dependents (bylines/comments SET NULL, credentials/api_tokens/oauth CASCADE), then `DELETE FROM users WHERE email ILIKE '…';` and invite from the admin UI (**Users → Invite**; no email provider → it returns a shareable link).

## C. Origin / rpId model (updated 2026-09-01, post-cutover)

TLS terminates upstream (Cloudflare https → AWS http), so the node server needs the origin pinned: task-def env `EMDASH_SITE_URL=https://medicine-focus-poc.literatum.com` (+`EMDASH_ALLOWED_ORIGINS` http+https of the same host) — this is now the **adopted permanent mechanism** (PR #301, per-request scheme detection, was closed unmerged). Set via terraform `30-node-app` variables, applied 2026-09-01 (AIDAFOCUS-360 #381: node env serves ONLY the poc hostnames; `-node`/`-poc2`/`-hd` aliases removed from sites.json). Consequences:
- The pinned host is also the WebAuthn **rpId** → passkeys enroll/sign-in on the **medicine host only**; sciences users rely on magic-link.
- **Changing the canonical hostname invalidates every existing passkey** (happened at the 2026-09-01 cutover — all 13 users re-onboarded via bulk re-mint above).
- Enrollment 500 `Invalid origin` now = the deployed task-def env doesn't match the browser origin (e.g. old task still running).

## D. Sessions (updated 2026-09-01)

Sessions are now **shared via Postgres** (AIDAFOCUS-253, site migration `0007_astro_sessions.sql`) — the old per-container-filesystem limitation (keep `desired_count=1` during auth work; task roll wipes sessions) no longer applies on current deploys.

Related: `focus-node-db-access`, `focus-bench-load-test`; memory `[[focus-poc-node-passkey-recovery]]`, `[[focus-poc-node-env]]`.
