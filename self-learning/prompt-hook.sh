#!/bin/bash
# UserPromptSubmit hook: fires ONLY on correction-shaped prompts, nudging
# self-learning pass 1 at exactly the moment a lesson appears. Silent otherwise.
prompt=$(jq -r '.prompt // empty' 2>/dev/null) || exit 0
if printf '%s' "$prompt" | grep -qiE "^(no[,. ]|no$|nope|actually|wrong|stop |don'?t |not like|i said|again[,. ])|that'?s (wrong|not what)|you (just )?(did|said|missed|forgot)|(^|[ ])keep (using|the original)"; then
  echo "self-learning pass 1: this looks like a correction — capture it to disk (skill/memory) before continuing."
fi
exit 0
