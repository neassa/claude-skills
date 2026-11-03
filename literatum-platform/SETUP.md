# Literatum skills: setup

Three Agent Skills for understanding and debugging the Atypon Literatum platform:

| Skill | Use it for |
|---|---|
| `literatum-platform` | **Start here.** How the repos connect, what runs where at runtime, how a change deploys. Holds 36 deep per-repo notes (`references/deep/`, index in `references/deep/README.md`). |
| `literatum-deploy-triage` | Failed Deploy Server actions (beta/stag): find every failure (current, cancelled, hung), walk the release tree upstream-first, map it to repo/branch/root cause, sweep for stopped hosts and blocked nightlies. Ships read-only scripts. |
| `literatum-patch-cassandra-failures` | ProductPatch / patch-VM failures involving Cassandra (`table … does not exist`, `KILLING THE SYSTEM`, driver classpath clashes). |

## Install

Skills use the open Agent Skills format (`SKILL.md` + `references/`, `scripts/`). No conversion needed.

- **Claude Code**: copy the three folders from `skills/` into `~/.claude/skills/` (personal) or `.claude/skills/` (project).
- **Cursor**: copy them into `~/.cursor/skills/` or `.cursor/skills/`. Cursor also reads `.claude/skills/`.
- Keep the three folders side by side: the triage and patch skills link to `../literatum-platform/references/deep/`.

## Prerequisites (check these first)

```bash
git --version && python3 --version && curl --version | head -1   # python3 ≥3.8, stdlib only (no pip modules)
gh auth status                      # must be logged in with read access to github.com/atypon
curl -sS -o /dev/null -w '%{http_code}\n' https://deployserver.literatumonline.com/   # network to the Deploy Server
```

- **Jira (optional):** LIT lives on `atypon.atlassian.net`. In Claude Code, use an Atlassian connector (cloudId `6bfba5f3-1c23-4def-98c0-c0592a82537c`, read-only JQL; keep `maxResults` ≤ 10). In Cursor or without a connector, open `https://atypon.atlassian.net/issues/?jql=…` in a browser, or skip the step: `literatum-platform/references/deep/14-jira-resolutions.md` holds the mined resolutions.

## Set up the repo clones

The notes' paths are relative to `LIT_REPOS`. Clones are **shallow and read-only**; never commit from them.

```bash
export LIT_REPOS=~/lit-repos && mkdir -p "$LIT_REPOS" && cd "$LIT_REPOS"
for r in literatum literatum-patch deployconf deployserver platform-tools opstool opscommon \
         ansible-inventory ansible-solr ansible-consumer ansible-cassandra ansible-redis ansible-gaia ansible-pugrenderer \
         ansible-zookeeper ansible-kafka ansible-atm ansible-mssql ansible-elk ansible-tools \
         ui-products ui-core styleguide-render-pug styleguide-bundler styleguide-bundle-configurations utypon-cli \
         gaia gaia-fe axel cms-root id-core id-search id-index solr-plugins root-pom platform-passport-cluster \
         qa-automation-xml testypon developer_productivity; do
  [ -d "$r/.git" ] || git clone -q --depth 1 --filter=blob:limit=2m "git@github.com:atypon/$r.git"
done
# Beta builds from lit-2610, not master: add a detached worktree for it (refresh it the same way later)
git -C literatum fetch -q --depth 50 origin lit-2610:refs/remotes/origin/lit-2610
git -C literatum worktree add -q --detach ../literatum-lit-2610 origin/lit-2610
```

- **Update before reading:** `git -C $LIT_REPOS/<r> fetch --depth 1 origin <default> && git -C $LIT_REPOS/<r> reset --hard FETCH_HEAD`.
- **Any other branch or tag** (stag/prod maint branches, ansible `deploy_version` branches): `gh api "repos/atypon/<repo>/contents/<path>?ref=<branch>" --jq .content | base64 -d | <skill>/scripts/safe_view.py -`, or `git fetch --depth 1 origin <branch>` then `git show FETCH_HEAD:<path> | safe_view.py -`. Which branch each env builds comes from deployconf (see `literatum-deploy-triage/references/repos-and-branches.md`).
- Something not in these clones? Everything is under github.com/atypon (1,200+ repos): search it before calling code missing (`gh search code "<symbol>" --owner atypon`).

## Scratch space and secrets (read this)

- The scripts store downloaded logs under `${TMPDIR:-/tmp}/ds-triage-$USER/` (mode 700). **Set `TMPDIR` to a private folder** outside any git repo. Logs there are reused: delete a file to re-fetch a live row's log, and delete the folder when you're done.
- **Repos, deployconf, props files and action logs contain plaintext credentials, often as bare literals no keyword filter catches.** Never `cat`/`grep`/`git grep` repo files directly: read them with `literatum-deploy-triage/scripts/safe_view.py FILE [START [END]]` and search with `safe_view.py --grep 'REGEX' PATH`; read logs with `ds_log.sh`. Example: a plain `grep` on `platform-tools/sync_branches.sh` prints a credential embedded in a clone URL.
- If you delegate to sub-agents, paste these rules word for word into their first prompt.

## If the Deploy Server scripts return `//EX`

The scripts replay the Deploy Server page's own read-only `search` call, which embeds two GWT hashes (policy and permutation) that change when the Deploy Server is redeployed. `ds_search.py` stops rather than guessing. To refresh: load `https://deployserver.literatumonline.com/deployserver/deployserver.nocache.js`, take the permutation name from it, open `<perm>.cache.js` and read `serializationPolicyName`; update the two constants at the top of `ds_search.py` and `ds_failures.sh`. Keep `cron=false` and `query=null` (both scripts check this): `cron=true` deletes rows server-side.

## Ground rules baked into the skills

- **Strictly read-only:** no creating, cancelling, rescheduling, restarting or unlocking Deploy Server actions; no UI Status dropdown; no DB access; no code changes.
- **Verify, don't assume:** each claim is marked checked (log / code at commit / live search) or inferred. A shorter failure list never means something cleared: confirm by a product-filtered search.
- Facts are dated (2026-09-24 → 27) and cite file:line@commit; branches and versions in deployconf move weekly, and logs expire after 15 days. Re-check before relying on a specific value.
