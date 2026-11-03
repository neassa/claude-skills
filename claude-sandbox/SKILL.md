---
name: claude-sandbox
description: Use whenever the claude-sandbox repo, its GitHub releases, or its installer comes up at all — fixing missing or broken release assets, uploading tarballs, updating README.md / MAINTAINING.md / release.sh, or testing install.sh without affecting the user's environment. Reach for this even on one-liner tasks like checking a release asset or re-uploading a tarball; it carries hard constraints (never run release.sh, never delete releases or the claude-home volume) that are easy to violate without it.
---

# claude-sandbox

Reference guide for working on the `ljanaideh/claude-sandbox` project.

## Key constraints

- **Never run `./scripts/release.sh`** — releases are human-triggered only
- **Never force-push or delete releases**
- **Only edit README.md, MAINTAINING.md, scripts/release.sh** for content updates unless explicitly told otherwise
- **Never touch `init-firewall.sh` directly** — patches must survive any sync

## Patch verification (pre-flight check)

`release.sh` will fail if either patch is missing from `init-firewall.sh`:

| Patch | Grep marker |
|---|---|
| A — DNS retry | `WARNING: Failed to resolve` |
| B — ipset dedup | `ipset add -exist allowed-domains` |

## Common tasks

**Update content files and push:**
```bash
# Edit README.md / MAINTAINING.md / scripts/release.sh
bash -n scripts/release.sh        # validate bash syntax before committing
git add README.md MAINTAINING.md scripts/release.sh
git commit -m "description"
git push
```

**Check release asset state:**
```bash
gh release view vX.Y.Z --repo ljanaideh/claude-sandbox --json assets --jq '.assets[] | .name'
```

**Fix partial release (assets missing, dist/ has tarballs):**
```bash
gh release upload vX.Y.Z \
    dist/claude-sandbox-amd64.tar.gz \
    dist/claude-sandbox-arm64.tar.gz \
    dist/SHA256SUMS \
    scripts/install.sh \
    scripts/install.ps1 \
    --repo ljanaideh/claude-sandbox --clobber
```
If `dist/` is empty — stop, report, let the human decide.

After uploading, re-run the asset check above and confirm all four assets are present with plausible sizes (see table below) — an interrupted upload can leave a truncated asset that `--clobber` masks.

**Test installer without touching user's shell profile:**
```bash
HOME=$(mktemp -d) bash scripts/install.sh
```
Docker image load and volume check still hit the real daemon — safe because both already exist.

## Release asset sizes (expected)

| Asset | Size |
|---|---|
| `claude-sandbox-amd64.tar.gz` | ~417 MB (v0.0.2: 437009439 B) |
| `claude-sandbox-arm64.tar.gz` | ~410 MB (v0.0.2: 429864675 B) |
| `SHA256SUMS` | ~190 B (from v0.0.2) |
| `install.sh` | ~3 KB |
| `install.ps1` | ~4 KB |

## What persists across updates

`claude-home` Docker volume (credentials, Figma MCP OAuth) — never deleted by installer or update.

## Full project context

See `CLAUDE.md` in the repo root for the complete file map, patch details, and recovery procedures.

## Known state (verified 2026-09-13)

- **Shipped image `claude-sandbox:v0.0.1` has the firewall DISABLED.** Its baked `/usr/local/bin/extra-allows.sh` still has the `iptables -I OUTPUT 1 -j ACCEPT` ALLOW-ALL line active (prints `WARNING: Firewall disabled`). The repo copy has it commented out — a new release fixes it. Check: `docker run --rm --entrypoint tail claude-sandbox -3 /usr/local/bin/extra-allows.sh`
- **Container does not trust corporate TLS-inspection CAs.** Host has Cloudflare WARP Gateway CA (`/etc/ssl/certs/managed-warp.pem`) and `Atypon-CA.pem`; the image has only the Debian bundle and `NODE_EXTRA_CA_CERTS` is unset. Whenever Gateway decrypts a connection, `claude` fails with `Unable to connect to API: SSL certificate verification failed`. Decryption is policy/time-dependent — host and container both saw the real Google Trust Services cert on 2026-09-13. **Fix COMMITTED to main 2026-09-13 (not yet released — needs `./scripts/release.sh` → v0.0.2):** `claude-docker` in install.sh/install.ps1 mounts the host trust store over `/etc/ssl/certs/ca-certificates.crt` (fixes curl/git too) and sets `NODE_EXTRA_CA_CERTS` to it. `CLAUDE_SANDBOX_CA_BUNDLE` overrides, `none` disables. Windows export (Cert: drive → PEM) is parse-checked only, never run on Windows.
  Evidence: via mitmproxy without the mount, `claude -p` prints the exact "Unable to connect to API: SSL certificate verification failed" and curl exits 60; with it claude reaches the API (401 = expired token). No regression without a proxy, firewall applied.
  Repro rig: `docker run -d --name mitm-test -v <dir>:/home/mitmproxy/.mitmproxy mitmproxy/mitmproxy mitmdump -q`; CA lands in `<dir>/mitmproxy-ca-cert.pem`; simulate "host bundle contains the interception CA" with `cat /etc/ssl/certs/ca-certificates.crt <dir>/mitmproxy-ca-cert.pem > bundle.crt`. **Do NOT pass `-e HTTPS_PROXY` to the whole container** — init-firewall.sh's sanity check then reaches example.com through the proxy and aborts the entrypoint; override the entrypoint, run the firewall, `ipset add allowed-domains <mitm ip>`, then export the proxy only for the claude/curl process. Remove the container afterwards.
- **Render the installer's shell block without running the installer** (avoids the 374 MB download): `VOLUME=claude-home IMAGE=<img> REPO=x; eval "$(sed -n '/^BLOCK=\$(cat/,/^BLOCK=\${BLOCK\/\/__REPO__/p' scripts/install.sh)"; echo "$BLOCK" > rendered.sh`. Run the real function under a pty with `script -qec "bash -c 'source rendered.sh; claude-docker -p ...'" /dev/null` (docker `-it` needs a TTY).
- **`pwsh` hangs on this laptop** even for `Write-Output`; parse-check install.ps1 in `mcr.microsoft.com/powershell:latest` instead (`[scriptblock]::Create(...)` on the file and on the Invoke-Expression-rendered `$block`).
- A stray **Draft v0.0.1 release** exists next to the published v0.0.1 (`gh release list`).
- **DNS warnings for `statsig.anthropic.com` / `cdn-lfs.huggingface.co` are benign** — Patch A / extra-allows retry working; statsig is NXDOMAIN even from the host, cdn-lfs has no A record. Not related to SSL failures.
- `scripts/install.sh` / `install.ps1` were untracked until 2026-09-13; now committed.

## Diagnostics that don't need the user's terminal

```bash
# TLS/DNS from inside the image, firewall applied, real credentials volume
docker run --rm --cap-add=NET_ADMIN --cap-add=NET_RAW -v claude-home:/home/dev --entrypoint sh claude-sandbox -c '
  sleep 2; /usr/local/bin/init-firewall.sh >/dev/null 2>&1; /usr/local/bin/extra-allows.sh >/dev/null 2>&1
  curl -sv -m 10 https://api.anthropic.com/ -o /dev/null 2>&1 | grep -E "issuer|SSL certificate"
  su dev -c "claude -p \"reply ok\" --output-format text"'   # 401 = expired OAuth, not a network problem
# Inspect the credentials volume read-only
docker run --rm -v claude-home:/home/dev:ro --entrypoint sh claude-sandbox -c 'cat /home/dev/.claude/settings.json; jq .env /home/dev/.claude.json'
```

## Windows / PowerShell gotchas (verified 2026-09-13 in `mcr.microsoft.com/powershell`)

- **Never document `... -O - | iex`**: the pipeline feeds Invoke-Expression one line at a time → `Cannot bind argument to parameter 'Command' because it is an empty string` on the first blank line, then `Unexpected attribute 'CmdletBinding'`. Use download-to-file + `powershell -ExecutionPolicy Bypass -File`. (`... | Out-String | iex` also works but see next point.)
- **`exit` inside anything run via `iex` closes the user's terminal** — install.ps1's `Fail` does `exit 1`. Running as a file in a child process isolates it.
- **Profile placement (changed 2026-09-13 afternoon)**: install.ps1 now writes the managed block to `$PROFILE.CurrentUserCurrentHost` (Microsoft.PowerShell_profile.ps1) — PowerShell loads it LAST (after AllUsers* and profile.ps1), so it beats stale `claude-docker` definitions elsewhere; also writes the other edition's (5.1 vs 7) current-host profile when its dir exists; removes old managed blocks from profile.ps1; WARNs `file:line` for any `function claude-*` outside a managed block; sets CurrentUser execution policy to RemoteSigned if nothing allows profiles to load. Reload command is now `. $PROFILE`. Symptom that drove this: fix works only in the session where the user dot-sourced, old SSL error in every new window = an older definition loading later.
- **Old end-marker bug**: the block ended with `# <<< claude-sandbox functions <` but the refresh regex wanted `<<<`, so every install appended another copy. Marker fixed to `<<<`; regex accepts `<+`.
- `gh release download -O <existing file>` needs `--clobber`.
- Teammates install from PS 5.1 (`powershell`), not `pwsh` — keep the scripts 5.1-compatible.
- **Download UX/loop (2026-09-13)**: curl `--progress-bar` (total-based, resumes at the right %; SHA256SUMS fetch uses `quiet`); `-w '%{http_code}'` is printed even when `-f` fails, so the loop stops at once on 4xx (except 408/429; 416 = already complete) instead of ~165 s of backoff. Test fixture gotcha: `rel.json` asset URLs go stale after `gh release upload --clobber` (new asset ids) → 404s; regenerate the fixture after any re-upload.
- **`local error: tls: bad record MAC` during `gh release download`** of the ~420 MB tarball = VPN / TLS-inspecting proxy killing gh's Go HTTP/2 stream, NOT auth. **Fixed 2026-09-13 in the v0.0.2 installer assets (re-uploaded with --clobber; the v0.0.2 git tag still points at the CA-fix commit c8a5a1f):** installers resolve the release via one `gh api` call, fetch the tarball with `curl -fsSL -C -` against the asset API url (token only to api.github.com; curl drops it on the CDN redirect, which the signed URL requires), resume from the last byte for up to 10 attempts (partial kept in `$TMPDIR/claude-sandbox-install/<tag>-<asset>`), then verify size + SHA256 against the `SHA256SUMS` asset (5th asset, generated by release.sh since this change). `-Tarball` / `TARBALL=` files are verified the same way. gh fallback only without curl, with `GODEBUG=http2client=0`. **Don't add `curl --retry`**: its internal retries restart from the first request's offset and discard progress; the outer loop must own resumption.
- Resume verified live: GitHub asset CDN (`release-assets.githubusercontent.com`) answers Range with 206; test by shadowing `curl` with a wrapper that adds `--max-time 8` on its first call — both installers resume from ~80 MB and pass SHA256. Test harness for bash needs `GH_TOKEN=$(gh auth token)` exported because `HOME=$(mktemp -d)` hides gh's own login (symptom: "gh is not authenticated" even though it is).

## Installer test harness (no network, no real docker)

Shadow `docker` and `gh` with fakes, then run the installer with a throwaway HOME. Bash: put fake scripts first on PATH (`docker version`/`load -i`/`images --format`/`tag`/`volume ls`; `gh release download` → print `local error: tls: bad record MAC`, exit 1; `gh auth status` → exit via `FAKE_GH_AUTH_EXIT`). PowerShell (in `mcr.microsoft.com/powershell`): define `function docker {...}` / `function gh {...}` in the calling script — functions shadow external commands; set `$LASTEXITCODE` with `& true` / `& false`. Scenarios: download fails 3x (authed / not authed), `-Tarball`/`TARBALL` path, missing tarball. Reference scripts lived in the session scratchpad (`fakebin/`, `pstest.ps1`) — recreate from this description.
