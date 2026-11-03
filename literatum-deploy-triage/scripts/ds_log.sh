#!/usr/bin/env bash
# READ-ONLY: fetch one Deploy Server action log and print it MASKED (via safe_view.py), optionally filtered.
# Usage: ds_log.sh <actionId> [grep-regex] [context-lines]
#   ds_log.sh 3a234861-842f-4e8f-8dad-3264c69474b0 'Caused by|Exception in thread' 2
#   ds_log.sh <id>                      # whole log, masked
# Also fetches earlier ProductBuild attempts if present: ds_log.sh <id>.txt_1
# Nothing else is requested; the raw log is kept under ${TMPDIR:-/tmp}/ds-triage-$USER/logs (mode 700).
set -uo pipefail
ID="${1:?actionId}"; RE="${2:-}"; CTX="${3:-0}"
HERE="$(cd "$(dirname "$0")" && pwd)"; BASE="https://deployserver.literatumonline.com"
OUT="${TMPDIR:-/tmp}/ds-triage-$USER/logs"; mkdir -p "$OUT"; chmod 700 "$(dirname "$OUT")" "$OUT"
case "$ID" in *.txt_*) f="$OUT/$ID"; url="$BASE/info/$ID";; *) f="$OUT/$ID.txt"; url="$BASE/info/$ID.txt";; esac
if [ ! -s "$f" ]; then
  for try in 1 2 3; do curl -sS -m 60 -f "$url" -o "$f" && break; sleep 2; done
  [ -s "$f" ] || { echo "no log for $ID (purged after 15 days, never ran, or DS slow — retried 3x)"; exit 1; }
fi
hdr=$(grep -a -m1 -oE "${ID%%.txt_*}: [A-Za-z0-9]+ by [^ ]+\. .*" "$f" | sed -E 's/ by [^.]+\./ by <user>./' | cut -c1-200)
echo "# $hdr"
echo "# $(wc -l < "$f") lines; local copy from $(stat -c %y "$f" | cut -c1-16) (delete it to re-fetch); times are Deploy Server time (US Pacific). Masked output; secret-bearing values shown as ***."
if [ -n "$RE" ]; then
  grep -anE -B"$CTX" -A"$CTX" "$RE" "$f" | sed -E 's/\x1b\[[0-9;?]*[a-zA-Z]//g' | python3 "$HERE/safe_view.py" - | sed -E 's/^[0-9]+: //'
else
  sed -E 's/\x1b\[[0-9;?]*[a-zA-Z]//g' "$f" | python3 "$HERE/safe_view.py" -
fi
