---
name: reading-code-without-secrets
description: >-
  Use before reading repositories, config files, deploy logs or build output that may
  contain credentials (ops scripts, CI config, props/yaml/xml config, infrastructure
  repos), and before dispatching sub-agents to read them. Use when the user says "do not
  read secrets", when a tool printed something that looked like a credential, or when
  building a filter to hide secrets.
---

# Reading code without reading secrets

## When this applies

Any read of files that humans wrote credentials into. Ops repos, deploy scripts, config
overlays and job logs contain plaintext passwords, tokens and keys, often as bare
literals. The rule is "never **read** them", not "never repeat them": once printed, the
value is in the transcript.

## What to do

1. **Read through a masking viewer, never `cat`/`grep` directly.** Use
   `scripts/safe_view.py FILE [START [END]]`, `safe_view.py --grep REGEX PATH`, and
   `git show <ref>:<path> | safe_view.py -`. It *masks* values rather than dropping
   lines, so code stays readable.
2. **For config files, look at key names first.** Open a value only when the key is
   plainly harmless: host, port, version, branch, path.
3. **Test a filter by counting, never by printing.** Check "is the known-secret line
   changed by the mask?" as a boolean. Printing the line to see if it's masked leaks it
   when the mask fails.
4. **After every filter change, run a regression over every line that ever leaked, plus
   a sweep of a whole repo:** count secret-named lines left unmasked. Zero is the pass
   mark.
5. **Don't add bare words to log filters.** Words like `private` or `auth` hide real
   evidence: `private access` compile errors, `author`. And `-P` matched
   case-insensitively hides every `-p <product>` argument. Put command-line credential
   patterns in a separate case-sensitive filter.
6. **Sub-agents get the rules word for word in their FIRST prompt**, and may not start
   their own helpers unless they pass the rules on verbatim. A correction relayed mid-run
   arrives too late.
7. **Report locations, not values:** "secret-bearing line at file:line". List exposed
   credentials for the owner to rotate. Never paste raw logs into tickets.

## Shapes a keyword filter misses (all seen in real repos)

| Shape | Example of the pattern |
|---|---|
| A key name your list doesn't cover | `newrelic_license_key: …`, `auth_basic: "…"` |
| A bare quoted literal with no keyword nearby | `user <name> '<password>'` in a shell script |
| Credentials as positional arguments | `Factory.getInstance("<url>", "<user>", "<password>")` |
| Secret-ish name in an attribute | `<string name="secretKey">value</string>` |
| XML element text | `<sslpass>value</sslpass>` |
| A password after a short flag | `tool -x <password>` |
| Base64 blobs | service-account JSON embedded in a props file |
| A credential inside a clone URL | `https://user:token@host/repo.git` |

A real secret scanner (gitleaks, trufflehog) run before reading catches what patterns
miss. Ask the user before installing one.

## Founding failure

Over three days, read-only reader agents printed eight distinct credentials into their
transcripts, through six generations of keyword filter. Each fix caught the last shape
and missed the next. One exposure came from the agent itself, printing a test line to
check whether the new mask worked. Another came from a reader's own helper agent, which
had never been given the rules. Masking values, testing by counting, and a regression
sweep stopped the new leaks. A proper scanner would have been better from the start.
