#!/usr/bin/env bash
# READ-ONLY: list Deploy Server actions with their header facts, sorted by run time.
# Solves: "ds_search.py prints ids only", "a cancelled failure is invisible to ds_failures.sh",
# "what else ran at the same time?", "find a past failure by date".
#
# Requests: the search RPC via ds_search.py (cron=false, query=null enforced) + GET /info/<id>.txt per id.
# Usage: ds_list.sh <midtierbeta|staging> [product|""] [action|""] [status|""] [pageSize=300] [grep-regex on the line]
#   ds_list.sh staging hope "" ""                      # everything kept for hope on stag
#   ds_list.sh midtierbeta "" GaiaDeploy "" 300 '20Sep 23:'   # all GaiaDeploys that ran that hour (any product)
#   ds_list.sh staging gsl ProductBuild Cancelled     # cancelled builds only
# Output columns: run-time | createDate | Action | Product-Family | Host | log-final-status | now-status | parentId | id
set -uo pipefail
ACCOUNT="${1:?account}"; PRODUCT="${2:-}"; ACTION="${3:-}"; STATUS="${4:-}"; PAGE="${5:-300}"; FILTER="${6:-}"
case "$ACCOUNT" in midtierbeta|staging) ;; *) echo "refusing: account must be midtierbeta or staging"; exit 1;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"; BASE="https://deployserver.literatumonline.com"
ROOT="${TMPDIR:-/tmp}/ds-triage-$USER"; mkdir -p "$ROOT"; chmod 700 "$ROOT"; OUT=$(mktemp -d "$ROOT/list-$ACCOUNT-XXXX")   # per-run dir: parallel runs must not share files

if [ -n "$STATUS" ]; then
  python3 "$HERE/ds_search.py" "$ACCOUNT" "$STATUS" "$ACTION" "$PAGE" "$PRODUCT" | sed "s/\$/|$STATUS/" > "$OUT/ids.txt"
else
  : > "$OUT/ids.txt"
  for st in Failure Cancelled Scheduled Executing Success; do
    python3 "$HERE/ds_search.py" "$ACCOUNT" "$st" "$ACTION" "$PAGE" "$PRODUCT" 2>/dev/null | sed "s/\$/|$st/" >> "$OUT/ids.txt" || true
  done
fi
# one row per id: an id can appear under several status searches (search results also carry parentId/blockedId
# references), so join the statuses it was seen under; the log's own final status is the second opinion
python3 - "$OUT/ids.txt" <<'PY'
import sys,collections
p=sys.argv[1]; seen=collections.OrderedDict()
for l in open(p):
    l=l.strip()
    if '|' not in l: continue
    i,st=l.split('|',1); seen.setdefault(i,[]); st not in seen[i] and seen[i].append(st)
open(p,'w').write(''.join(f"{i}|{'/'.join(v)}\n" for i,v in seen.items()))
PY
[ -s "$OUT/ids.txt" ] || { echo "no actions found"; exit 0; }
N=$(wc -l < "$OUT/ids.txt")
if [ -z "$PRODUCT" ] && [ "$N" -gt 400 ]; then
  echo "NOTE: $N ids with no product filter = $N sequential log fetches (~1 s each). Narrow with a product, an action, a status or a smaller pageSize if you don't need all of them." >&2
fi
i=0

while IFS='|' read -r id now; do
  i=$((i+1)); [ $((i % 50)) -eq 0 ] && echo "progress: $i/$N" >&2
  f="$OUT/$id.txt"
  if [ ! -s "$f" ]; then
    for try in 1 2; do curl -sS -m 40 "$BASE/info/$id.txt" -o "$f" && break; sleep 1; done   # one retry: the DS is slow at times
    [ -s "$f" ] || { printf '%s|%-16s %-19s %-26s %-16s %-24s %-9s %-9s %s %s\n' "${cd_:-0000} ~" "-" "-" "(fetch failed)" "-" "-" "-" "$now" "-" "$id"; continue; }
  fi
  hdr=$(grep -a -m1 -oE "$id: [A-Za-z0-9]+ by [^ ]+\. .*" "$f")
  [ -n "$hdr" ] || { printf '%s|' "${cd_:-0000} ~"; printf '%-16s %-19s %-26s %-16s %-24s %-9s %-9s %s %s\n' "-" "-" "(empty log: never ran)" "-" "-" "-" "$now" "-" "$id"; continue; }
  act=$(echo "$hdr" | grep -oE "^$id: [A-Za-z0-9]+" | awk '{print $2}')
  prod=$(echo "$hdr" | grep -oE 'Product=[^,]*' | cut -d= -f2); fam=$(echo "$hdr" | grep -oE 'Family=[^,]*' | cut -d= -f2)
  host=$(echo "$hdr" | grep -oE 'Host=[^,]*' | cut -d= -f2); par=$(echo "$hdr" | grep -oE 'parentId=[^,]*' | cut -d= -f2)
  cd_=$(grep -a -m1 -oE 'createDate=[^,]+' "$f" | cut -d= -f2 | cut -c1-19)
  ran=$(grep -a -m1 -oE '^\[ [0-9]{2}[A-Za-z]{3} [0-9:.]+ - [^]]+\] runAction>' "$f" | grep -oE '[0-9]{2}[A-Za-z]{3} [0-9:.]+')
  last=$(grep -a -oE 'Status=[A-Za-z]+' "$f" | tail -1 | cut -d= -f2)
  # sort key: run date as YYYY-MM-DD (month from the DS "13Sep" stamp, year from createDate), then time; never-ran rows sort by createDate
  key=$(python3 - "$ran" "$cd_" <<'PY'
import sys,datetime
ran,cd=sys.argv[1],sys.argv[2]
try:
    d=datetime.datetime.strptime(ran[:5]+cd[:4],'%d%b%Y'); print(d.strftime('%Y-%m-%d')+' '+ran[6:])
except Exception: print((cd or '0000')+' ~')
PY
)
  printf '%s|%-16s %-19s %-26s %-16s %-24s %-9s %-9s %s %s\n' "$key" "${ran:--}" "${cd_:--}" "$act" "${prod:--}-${fam:--}" "${host:--}" "${last:-?}" "$now" "${par:-null}" "$id"
done < "$OUT/ids.txt" | sort -t'|' -k1,1 | cut -d'|' -f2- | { if [ -n "$FILTER" ]; then grep -E "$FILTER"; else cat; fi; }
n_ids=$(wc -l < "$OUT/ids.txt"); n_ok=$(ls "$OUT"/*.txt 2>/dev/null | grep -vc ids.txt)
echo "COMPLETENESS: $n_ok of $n_ids ids fetched (empty-log rows count as fetched; '(fetch failed)' rows were retried once — re-run for those)"
echo "columns: run-time(DS, US Pacific) | createDate | Action | Product-Family | Host | log-final-status | now(search; 'A/B' = id seen under both searches, trust the header) | parentId | id   — logs under $OUT (may contain secrets)"
