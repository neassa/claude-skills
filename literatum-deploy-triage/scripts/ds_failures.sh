#!/usr/bin/env bash
# READ-ONLY: list failed Deploy Server actions for one account and fetch each one's log.
# Sends exactly what the Find Actions "Search" button sends (Status=Failure, Account=<account>,
# everything else "Please Select", Custom Search off, Repeatable Events off, Show Test off) —
# verified against the page's compiled client (serialize_219 / $onSearchClick / search_1).
# Only two kinds of request are sent:
#   1. POST /deployserver/deploy  -> GWT RPC Service.search(SearchRequest)   (SELECT only; cron=false, query=null)
#   2. GET  /info/<id>.txt        -> plain-text action log (saved locally, never printed)
# Output: one summary line per action id (header fields only) + candidate fatal lines with
# secret-bearing lines filtered out. Logs can contain credentials: keep OUT private, delete after use.
# Usage: ds_failures.sh <midtierbeta|staging> [out_dir]   (default out_dir: ${TMPDIR:-/tmp}/ds-triage-$USER; never inside a git repo)
set -euo pipefail
ACCOUNT="${1:?account: midtierbeta or staging}"
case "$ACCOUNT" in midtierbeta|staging) ;; *) echo "refusing: account must be midtierbeta or staging"; exit 1;; esac
STATUS="Failure"
BASE="https://deployserver.literatumonline.com"
MODULE="$BASE/deployserver/"
# These two hashes change whenever the Deploy Server is redeployed. Re-read them from
# $MODULE/deployserver.nocache.js (permutation names) and <perm>.cache.js (serializationPolicyName).
POLICY="99D654BD46404CA6D6F0EB8F10557400"
PERM="037BDEFA7FC4064CC1E8BB1656B0D50E"
OUT="${2:-${TMPDIR:-/tmp}/ds-triage-$USER}/$ACCOUNT"; mkdir -p "$OUT"; chmod 700 "$(dirname "$OUT")" "$OUT"   # outside any git repo: logs may contain secrets
# CLI_SECRET_RE is case-SENSITIVE on purpose: -P <password> / -u user:pw, not -p <product>
CLI_SECRET_RE=' -P ?[^ -]| -u [^ ]+:[^ ]'
SECRET_RE='pass|pwd|token|secret|api_?key|_key|license_?key|private[_ -]?(key|token)|salt|_auth|authorization|credential|cmdparams|://[^/ :]+:[^/ @]+@'

# String table, in the order the client adds strings:
#  1 module base  2 policy  3 interface  4 method  5 param/object type signature  6 account  7 ""  8 status
STRINGS="$MODULE|$POLICY|com.atypon.deployserver.client.Service|search|com.atypon.deployserver.shared.CmdIO\$SearchRequest/1272154236|$ACCOUNT||$STATUS|"
# Payload: module,policy,interface,method; param count 1; param type; object type; then SearchRequest
# fields alphabetically (serialize_219), then PagedQuery page,pageSize:
#   account=6 action=7("") cron=0 end=0(null) family=7 hideCompleted=0 host=7 product=7 query=0(null)
#   showBackground=0 showTest=0 start=0(null) status=8 user=7 page=0 pageSize=25
PAYLOAD="1|2|3|4|1|5|5|6|7|0|0|7|0|7|7|0|0|0|0|8|7|0|25|"
BODY="7|0|8|$STRINGS$PAYLOAD"

# Safety check (0-based token index): [9]=cron must be 0 (cron=true triggers a DELETE server-side),
# [15]=query must be 0/null (raw SQL WHERE), 23 tokens total.
IFS='|' read -r -a P <<< "$PAYLOAD"
[ "${#P[@]}" = "23" ] && [ "${P[9]}" = "0" ] && [ "${P[15]}" = "0" ] || { echo "refusing: payload shape / cron / query check failed"; exit 1; }

curl -sS -m 30 -X POST "${MODULE}deploy" \
  -H 'Content-Type: text/x-gwt-rpc; charset=utf-8' \
  -H "X-GWT-Module-Base: $MODULE" -H "X-GWT-Permutation: $PERM" \
  --data-binary "$BODY" -o "$OUT/search.rpc"
if ! grep -q '^//OK' "$OUT/search.rpc"; then
  echo "search did not return //OK (policy/permutation likely changed after a DS redeploy); stopping"; exit 1
fi

# Action ids are UUIDs in the response string table (includes parent ids; log header says which is which).
{ grep -oE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$OUT/search.rpc" || true; } | sort -u > "$OUT/ids.txt"
if [ ! -s "$OUT/ids.txt" ]; then echo "no failed actions for $ACCOUNT (search returned an empty list)"; exit 0; fi
echo "ids in response: $(wc -l < "$OUT/ids.txt")"

while read -r id; do
  f="$OUT/$id.txt"
  curl -sS -m 60 "$BASE/info/$id.txt" -o "$f" || { echo "$id | log fetch failed"; continue; }
  hdr=$(grep -m1 -oE "$id: [A-Za-z0-9]+ by [^ ]+\. Account=[^,]*, Product=[^,]*, Family=[^,]*, Host=[^,]*" "$f" || true)
  parent=$(grep -m1 -oE 'parentId=[^,]*' "$f" || true)
  last=$(grep -oE 'Status=[A-Za-z]+' "$f" | tail -1 || true)
  printf '%s | %s | %s | final %s\n' "$id" "${hdr#*: }" "$parent" "$last"
  if [ "$last" = "Status=Failure" ]; then
    grep -anE 'BUILD FAILED|What went wrong|Could not (resolve|find)|: error:|^error:|Aborting|KILLING THE SYSTEM|Caused by:|failed to execute|Error \[5[0-9]\]|fatal:|COMPLETED FAILURE|Permission denied|Exception|npm ERR! 404|Build Failed For' "$f" | grep -vE 'PKIX|SunCertPathBuilder|ValidatorException' \
      | grep -vE 'warning:|hint:' | grep -viE "$SECRET_RE" | grep -vE "$CLI_SECRET_RE" | cut -c1-240 | head -12 | sed 's/^/    /' || true
    # (|| true: with pipefail, head closing the pipe early (SIGPIPE, rc 141) used to kill the whole run after the first long log)
    # the real cause is usually the LAST "Caused by" (the first ones are often wrapper bean chains)
    lc=$(grep -n '^Caused by:' "$f" | grep -viE "$SECRET_RE" | grep -vE "$CLI_SECRET_RE" | grep -v 'org.gradle' | tail -1 | cut -c1-300 || true)
    [ -n "$lc" ] && echo "    LAST CAUSE -> $lc"
  fi
done < "$OUT/ids.txt"
# Completeness guard: a partial run must never look like "fewer failures" (2026-09-25: a run died after 3 of 12 ids).
n_ids=$(wc -l < "$OUT/ids.txt"); n_ok=0
while read -r id; do grep -q "$id: [A-Za-z0-9]* by " "$OUT/$id.txt" 2>/dev/null && n_ok=$((n_ok+1)); done < "$OUT/ids.txt"
echo "COMPLETENESS: $n_ok of $n_ids ids have a fetched log with a header"
[ "$n_ok" = "$n_ids" ] || echo "WARNING: INCOMPLETE LISTING - do not conclude that any failure cleared; re-run"
echo "logs saved under $OUT (may contain secrets; delete when done)"
