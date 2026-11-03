#!/usr/bin/env bash
# READ-ONLY: fetch a ProductRelease and ALL its children, in execution order, and check
# every step (green ones too) for known silent-failure signatures — upstream first.
# Why: a green upstream step can be the real cause (e.g. ProductBuild Success but the
# LIT-656000 build-time patch failed and was reverted → unpatched WAR → bks crash, LIT-683431).
#
# Requests: GWT RPC search (via ds_search.py: account + product, any status) and
#           GET /info/<id>.txt per action. Nothing else.
# Usage: ds_release_tree.sh <account midtierbeta|staging> <product> <releaseId>
# Output: one line per child (seq, time, action, host, status) + flagged lines, secrets filtered.
set -uo pipefail   # no -e: empty greps are normal here
ACCOUNT="${1:?account}"; PRODUCT="${2:?product}"; REL="${3:?ProductRelease id}"
case "$ACCOUNT" in midtierbeta|staging) ;; *) echo "refusing: account must be midtierbeta or staging"; exit 1;; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
BASE="https://deployserver.literatumonline.com"
OUT="${TMPDIR:-/tmp}/ds-triage-$USER/tree-$REL"; mkdir -p "$OUT"; chmod 700 "$(dirname "$OUT")" "$OUT"
# CLI_SECRET_RE is case-SENSITIVE on purpose: -P <password> / -u user:pw, not -p <product>
CLI_SECRET_RE=' -P ?[^ -]| -u [^ ]+:[^ ]'
SECRET_RE='pass|pwd|token|secret|api_?key|_key|license_?key|private[_ -]?(key|token)|salt|_auth|authorization|credential|cmdparams|://[^/ :]+:[^/ @]+@'

# Silent-failure / key-evidence signatures, checked in EVERY child log (not only failed ones).
SIG='LIT-656000|PATCH (common|master|for 2610 and master) applied OK|patch failed, reverting|LIT BRANCH :|PATCH BRANCH:|The revision =|BUILD SUCCESSFUL|BUILD FAILED|: error:|No warfile was found|Failed to aqcuire build-lock|All Products Have been Built Successfully|Failed to Build The Product|BUILD COMPLETED|styleguide_new_|WARN \[Skipping updating the repo\.\]|SYNC \[|Error \[5[0-9]\]|COMPLETED (SUCCESS|FAILURE)|fatal:|failed=[1-9]|Finished deploying product|Java Result:|process is running|err\.DeployErr|Executing patch|failed to execute|Patch complete|KILLING THE SYSTEM|ERROR LOADING PRODUCT|Patch failed!|Patched Successfully|not found in deployconf|please add .--families|Not Production, Exiting|Could not connect|Connection refused|timed out|Permission denied'

# 1) child ids: the release's own "created child actions" list + any auto-added steps
#    (e.g. ProductBuildStyleguide, HostDeployStyleguide) found by a product search whose log has parentId=<release>
curl -sS -m 60 "$BASE/info/$REL.txt" -o "$OUT/$REL.txt" || { echo "cannot fetch release log"; exit 1; }
grep -oE '^ *[0-9]+ - [0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' "$OUT/$REL.txt" | awk '{print $3}' > "$OUT/listed.txt" || true
python3 "$HERE/ds_search.py" "$ACCOUNT" "" "" 300 "$PRODUCT" > "$OUT/ids.txt" || true
cat "$OUT/listed.txt" "$OUT/ids.txt" | sort -u | grep -vx "$REL" > "$OUT/cand.txt" || true
# current DB status of every row of this product (the log's last header can be stale, e.g. after a workflow restart)
: > "$OUT/now.txt"
for st in Failure Scheduled Executing Cancelled Success; do
  python3 "$HERE/ds_search.py" "$ACCOUNT" "$st" "" 500 "$PRODUCT" 2>/dev/null | sed "s/$/|$st/" >> "$OUT/now.txt" || true
done
# was this release created by a repeatable (nightly) template? Templates are Scheduled ProductRelease rows whose log lists "CREATED ACTION : <id>"
TEMPLATE=""
# (the action filter "ProductRelease" does not match templates, so check every Scheduled row of the product that isn't one of this release's children)
# A ProductRefreshDeploy-type template creates a row that is then CONVERTED into a ProductRelease with a NEW id
# (ProductReleaseConverter), so "CREATED ACTION : <id>" may not name this release. Fall back to matching the
# creation minute: template line "[ 24Sep 01:01.05 - deployd ] CREATED ACTION" vs this release's createDate.
REL_CD=$(grep -a -m1 -oE 'createDate=[^,]+' "$OUT/$REL.txt" | cut -d= -f2)
REL_MIN=$(python3 -c "import datetime,sys; d=datetime.datetime.strptime(sys.argv[1][:16],'%Y-%m-%d %H:%M'); print(d.strftime('%d%b %H:%M'))" "$REL_CD" 2>/dev/null)
for t in $(grep '|Scheduled$' "$OUT/now.txt" | cut -d'|' -f1 | grep -vxF -f "$OUT/listed.txt" | grep -vx "$REL"); do
  tf="$OUT/tmpl-$t.txt"
  if [ ! -s "$tf" ]; then for try in 1 2 3; do curl -sS -m 40 "$BASE/info/$t.txt" -o "$tf" && break; sleep 1; done; fi
  [ -s "$tf" ] || continue
  grep -aq 'CREATED ACTION' "$tf" || continue
  if grep -aq "CREATED ACTION : $REL" "$tf" || { [ -n "$REL_MIN" ] && grep -aE "^\[ $REL_MIN\.[0-9]+ - deployd \] CREATED ACTION" "$tf" | grep -aq .; }; then
    TEMPLATE="$t ($(grep -ac 'CREATED ACTION' "$tf") runs; last $(grep -a 'CREATED ACTION' "$tf" | tail -1 | grep -oE '^\[ [^]]+\]'))"; break
  fi
done
: > "$OUT/children.tsv"
while read -r id; do
  f="$OUT/$id.txt"; [ -s "$f" ] || curl -sS -m 60 "$BASE/info/$id.txt" -o "$f" || continue
  if ! grep -aq "$id: [A-Za-z0-9]* by .*parentId=$REL" "$f"; then
    # listed by the release but no log yet (Scheduled/blocked, never ran): take the row from the release's list
    line=$(grep -m1 -E "^ *[0-9]+ - $id: " "$OUT/$REL.txt") || continue
    act=$(echo "$line" | grep -oE "$id: [A-Za-z0-9]+" | awk '{print $2}'); host=$(echo "$line" | grep -oE 'Host=[^,]*' | head -1 | cut -d= -f2)
    n=$(echo "$line" | awk '{print $1}')
    printf '%s|%s|%s|%s|%s|%s|%s|%s|%s\n' "9999999$(printf %03d $n)" "-" "$act" "${host:--}" "not-run(no log)" "" "$id" "" "" >> "$OUT/children.tsv"; continue
  fi
  seq=$(grep -a -m1 -oE 'sequenceNum=[0-9]+' "$f" | cut -d= -f2)
  act=$(grep -a -m1 -oE "$id: [A-Za-z0-9]+ by" "$f" | awk '{print $2}')
  host=$(grep -a -m1 -oE "$id: [A-Za-z0-9]+ by .*" "$f" | grep -oE 'Host=[^,]*' | head -1 | cut -d= -f2)
  ran=$(grep -a -m1 -oE '^\[ [0-9]{2}[A-Za-z]{3} [0-9:.]+ - [^]]+\] runAction>' "$f" | grep -oE '[0-9]{2}[A-Za-z]{3} [0-9:.]+')
  st=$(grep -a -oE "$id: [A-Za-z0-9]+ by .*" "$f" | grep -oE 'Status=[A-Za-z]+' | tail -1 | cut -d= -f2)
  cb=$(grep -a -oE "$id: [A-Za-z0-9]+ by .*" "$f" | grep -oE 'canceledBy=[^,]*' | tail -1 | cut -d= -f2)
  blk=$(grep -a -oE "$id: [A-Za-z0-9]+ by .*" "$f" | grep -oE 'blockedId=[^,]*' | tail -1 | cut -d= -f2)
  [ "$blk" = "null" ] && blk=""
  prev=""
  if [ "$act" = "ProductBuild" ]; then
    for n in 1 2 3; do
      g="$OUT/$id.txt_$n"; [ -s "$g" ] || curl -sS -m 60 -f "$BASE/info/$id.txt_$n" -o "$g" 2>/dev/null || { rm -f "$g"; continue; }
      grep -q "$id: [A-Za-z0-9]* by " "$g" || { rm -f "$g"; continue; }   # an empty/error page is not an attempt
      t=$(grep -m1 -oE '^\[ [0-9]{2}[A-Za-z]{3} [0-9:.]+ - [^]]+\] runAction>' "$g" | grep -oE '[0-9]{2}[A-Za-z]{3} [0-9:.]+')
      prev="$prev;attempt_$n@${t:-?}"
    done
    # .txt_1 is the most recent superseded attempt (highest N = oldest); print oldest first
    [ -n "$prev" ] && prev=$(echo "$prev" | tr ';' '\n' | grep . | tac | paste -sd';' | sed 's/;/; /g')
  fi
  printf '%s|%s|%s|%s|%s|%s|%s|%s|%s\n' "${seq:-0}" "${ran:--}" "$act" "${host:--}" "${st:-?}" "${cb:-}" "$id" "$blk" "$prev" >> "$OUT/children.tsv"
done < "$OUT/cand.txt"
[ -s "$OUT/children.tsv" ] || { echo "no children found for release $REL (logs may be purged, or product/account wrong)"; exit 0; }

# 2) print in execution order with flagged lines
echo "release $REL (account $ACCOUNT, product $PRODUCT)${TEMPLATE:+ — created by repeatable template $TEMPLATE}"
echo "columns: seq | run time | action | host | log status | id(8) | flags.  times are Deploy Server time (US Pacific). 'now=' = current status from search when it differs from the log (log header can be stale)."
sort -t"|" -k1,1n "$OUT/children.tsv" | while IFS='|' read -r seq ran act host st cb id blk prev; do
  now=$(grep -m1 "^$id|" "$OUT/now.txt" | cut -d'|' -f2)
  flag=""; [ "$st" = "Failure" ] && flag="  <<< FAILED"
  # canceledBy in the log header is written before the cancel and is ~always null, so it can't show 'auto'.
  # A Cancelled step whose log shows it actually ran (runAction> + ssh output) is treated as a possible failure.
  if [ "$st" = "Cancelled" ] && grep -q ' runAction> ' "$OUT/$id.txt" && grep -q '(ssh) ' "$OUT/$id.txt"; then flag="  <<< CANCELLED AFTER RUNNING (check: auto-cancel = failure)"; fi
  [ -n "$now" ] && [ "$now" != "$st" ] && ! { [ "$st" = "not-run(no log)" ] && [ "$now" = "Scheduled" ]; } && flag="$flag  [now=$now]"
  [ -n "$blk" ] && flag="$flag  [blockedBy=$blk]"
  [ -n "$prev" ] && flag="$flag  [earlier, oldest first: $prev]"
  [ "${seq:0:7}" = 9999999 ] && seq="(later)"; printf '%-10s %-16s %-28s %-24s %-9s %-8s%s\n' "$seq" "$ran" "$act" "$host" "$st" "${id:0:8}" "$flag"
  grep -anE "$SIG" "$OUT/$id.txt" | grep -viE "$SECRET_RE" | grep -vE "$CLI_SECRET_RE" | grep -vE '^\s*[0-9]+:\s*(CMD [0-9]+ \$|.*validate-txt|.*cmdTemplate)' \
    | sed -E 's/\x1b\[[0-9;?]*[a-zA-Z]//g' | cut -c1-170 | awk '!seen[substr($0,index($0,":")+1)]++' | head -8 | sed 's/^/      /'
done
echo "logs: $OUT (may contain secrets; private, outside git)"
