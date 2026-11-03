#!/usr/bin/env python3
"""READ-ONLY Deploy Server search: list action ids for <account> [status] [action].

Sends exactly the GWT RPC the Find Actions "Search" button sends (Service.search), built
with the page's own serializer order (serialize_219). cron=false and query=null are
enforced (cron=true makes the server DELETE from action_black_list; query is raw SQL).
Prints one id per line (includes parent ids — read each log header to tell them apart).

Use it to compare a failure with successes of the same step elsewhere, e.g.
  ds_search.py midtierbeta Success ProductPatch   → did the same patch pass on other sites?

Usage: ds_search.py <account> [status=Failure] [action=""] [pageSize=100] [product=""] [user=""]
The POLICY/PERM hashes change when the Deploy Server is redeployed (see SKILL.md step 1).
"""
import sys, subprocess, re, tempfile, os

MODULE = "https://deployserver.literatumonline.com/deployserver/"
POLICY = "99D654BD46404CA6D6F0EB8F10557400"
PERM = "037BDEFA7FC4064CC1E8BB1656B0D50E"

def body(account, status, action, page_size, product="", user=""):
    table, idx, enc = [], {}, []
    def add(s):
        if s is None: return 0
        if s in idx: return idx[s]
        table.append(s); idx[s] = len(table); return idx[s]
    ws = lambda s: enc.append(str(add(s)))
    ap = lambda t: enc.append(str(t))
    ws(MODULE); ws(POLICY); ws("com.atypon.deployserver.client.Service"); ws("search"); ap(1)
    sig = "com.atypon.deployserver.shared.CmdIO$SearchRequest/1272154236"
    ap(add(sig)); ap(add(sig))
    # account action cron end family hideCompleted host product query showBackground showTest start status user | page pageSize
    ws(account); ws(action); ap(0); ws(None); ws(""); ap(0); ws(""); ws(product); ws(None); ap(0); ap(0); ws(None); ws(status); ws(user); ap(0); ap(page_size)
    assert len(enc) == 23 and enc[9] == "0" and enc[15] == "0", "refusing: cron/query must be 0"
    return "7|0|%d|%s%s" % (len(table), "".join(s + "|" for s in table), "".join(t + "|" for t in enc))

def main():
    if len(sys.argv) < 2: sys.exit(__doc__)
    account = sys.argv[1]
    if account not in ("midtierbeta", "staging"): sys.exit("refusing: account must be midtierbeta or staging")
    status = sys.argv[2] if len(sys.argv) > 2 else "Failure"
    action = sys.argv[3] if len(sys.argv) > 3 else ""
    page_size = int(sys.argv[4]) if len(sys.argv) > 4 else 100
    product = sys.argv[5] if len(sys.argv) > 5 else ""
    user = sys.argv[6] if len(sys.argv) > 6 else ""
    with tempfile.NamedTemporaryFile("w", delete=False) as f:
        f.write(body(account, status, action, page_size, product, user)); path = f.name
    try:
        out = subprocess.run(["curl", "-sS", "-m", "30", "-X", "POST", MODULE + "deploy",
                              "-H", "Content-Type: text/x-gwt-rpc; charset=utf-8",
                              "-H", "X-GWT-Module-Base: " + MODULE, "-H", "X-GWT-Permutation: " + PERM,
                              "--data-binary", "@" + path], capture_output=True, text=True, check=True).stdout
    finally:
        os.unlink(path)
    if not out.startswith("//OK"):
        sys.exit("search did not return //OK (policy/permutation hash likely changed)")
    for i in sorted(set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", out))):
        print(i)

if __name__ == "__main__":
    main()
