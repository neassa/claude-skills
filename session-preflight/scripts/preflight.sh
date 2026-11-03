#!/usr/bin/env bash
# One line of orientation. Prints where you are, what branch, whether it is a linked
# worktree, how dirty it is, and any credential profile in the environment.
# Fast enough (about 25ms) to run on every prompt via a hook. Never fails.
set +e
cwd="$(pwd)"; out="${cwd/#$HOME/\~}"

if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  br="$(git rev-parse --abbrev-ref HEAD 2>/dev/null)"
  dirty="$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
  wt=""
  case "$(git rev-parse --git-dir 2>/dev/null)" in *"/worktrees/"*) wt=" (linked worktree)";; esac
  out="${out} @ ${br}${wt}"
  [ "$dirty" != "0" ] && out="${out}, ${dirty} uncommitted"
  up="$(git rev-parse --abbrev-ref '@{upstream}' 2>/dev/null)"
  if [ -n "$up" ]; then
    ab="$(git rev-list --left-right --count "${up}...HEAD" 2>/dev/null)"
    behind="${ab%%	*}"; ahead="${ab##*	}"
    [ "${behind:-0}" != "0" ] && out="${out}, ${behind} behind ${up}"
    [ "${ahead:-0}" != "0" ] && out="${out}, ${ahead} ahead"
  fi
else
  out="${out} (not a git repo)"
fi

# credential / target context, only what is actually set
for v in AWS_PROFILE AWS_REGION GOOGLE_CLOUD_PROJECT AZURE_SUBSCRIPTION_ID KUBECONFIG NODE_ENV; do
  [ -n "${!v}" ] && out="${out} | ${v}=${!v}"
done
kctx="$(kubectl config current-context 2>/dev/null)"
[ -n "$kctx" ] && out="${out} | kube=${kctx}"

echo "preflight: ${out}"
exit 0
