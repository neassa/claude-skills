#!/usr/bin/env bash
# check_response.sh <headers-file> <body-file>
# Reads a saved Literatum curl response (headers + body) and prints a one-line
# verdict about WHICH layer failed, so you fix the right thing.
set -euo pipefail

H="${1:-}"; B="${2:-}"
if [[ -z "$H" || -z "$B" ]]; then
  echo "usage: check_response.sh <headers-file> <body-file>" >&2
  exit 2
fi

status=$(grep -aoE '^HTTP/[0-9.]+ [0-9]+' "$H" | tail -1 | grep -oE '[0-9]+$' || true)
loc=$(grep -aiE '^location:' "$H" | tail -1 | sed 's/^[Ll]ocation:[[:space:]]*//; s/\r$//' || true)
size=$(wc -c < "$B" | tr -d ' ')
login=$(grep -aoE '"login-status":"[^"]*"' "$B" | head -1 | sed 's/.*:"//; s/"//' || true)
errblk=$(grep -aoE '"error":\{[^}]*\}' "$B" | head -1 || true)
pbpage=$(grep -aoE 'page:string:[^;"]*' "$B" | head -1 | sed 's/page:string://' || true)
terms=$(grep -aoc 'name="accept-terms"' "$B" || true)

echo "status=${status:-?}  size=${size}B  login-status=${login:-?}  page=${pbpage:-?}"
[[ -n "$loc" ]]    && echo "redirect -> $loc"
[[ -n "$errblk" ]] && echo "error-block: $errblk"

verdict() { echo ">> VERDICT: $*"; }

if [[ "$login" == "guest" ]]; then
  verdict "AUTH — session is guest. Log in with real credentials (layer 1)."
elif [[ -n "$loc" && "$loc" == *acceptTerms* ]] || [[ "${terms:-0}" -gt 0 ]]; then
  verdict "TERMS GATE — accept terms: GET /action/acceptTerms?accept-terms=true&redirectUri=/ (layer 3)."
elif [[ "$status" == "403" ]]; then
  verdict "AUTHORIZATION — account not entitled to this service. Needs a server-side role grant (layer 4)."
elif [[ "$status" == "500" ]]; then
  verdict "SERVER ERROR — request reached the handler and threw. Check ZIP validity + escalate with cf-ray/x-webstats-respid (layer 5)."
elif [[ "$size" -lt 50 && -z "$loc" ]]; then
  verdict "EMPTY BODY — likely an unfollowed redirect. Re-run with -L and -D and inspect location header."
elif [[ "$status" == "200" && -z "$errblk" ]]; then
  verdict "OK — 200 with no error block. Confirm this is a deposit receipt, not just a rendered page."
else
  verdict "Unclear — inspect the body manually (status=$status)."
fi
