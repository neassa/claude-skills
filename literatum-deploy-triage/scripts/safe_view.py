#!/usr/bin/env python3
"""READ-ONLY safe viewer for repo files: prints lines with anything that looks like a
credential MASKED (not dropped), so code stays readable but values never reach the reader.

Usage:
  safe_view.py FILE [START [END]]          print lines START..END (1-based), masked
  git show <ref>:<path> | safe_view.py -   read a file at a git ref (or any stream) masked
  safe_view.py --grep REGEX PATH...         recursive grep (python re, case-insensitive), masked output
Why: name-based grep filters missed bare literals (SFTP password, Jira login, base64 GCP
service-account JSON, auth_basic, license keys) on 2026-09-25.
"""
import math, os, re, sys

KEYWORDS = re.compile(r'(pass(word|wd)?(?!port|age|ive|ing)|pwd|secret|token|api_?key|_key\b|license_?key|private_?key|salt|'
                      r'(?<!o)auth(?!or)\w*|oauth\w*(?:token|secret|key|pass)\w*|credential|bearer|basic\s|jdbc:|sftp|login|user(name)?\s*[:=]|client_id|'
                      r'aws_|access_key|session_key|cookie)', re.I)
PEM = re.compile(r'-----BEGIN [A-Z ]+-----')
URL_CRED = re.compile(r'(://)([^/\s:@]+):([^/\s@]+)@')
QUOTED = re.compile(r'''(["'])([^"'\s]{4,})\1''')
ASSIGN = re.compile(r'''([:=]\s*|\s-[pPu]\s+|--password[= ]\s*)([^\s,;)"'<>]{4,})''')
LONGTOK = re.compile(r'[A-Za-z0-9+/_\-]{24,}={0,2}')   # '=' only as trailing base64 padding, so key=value never fuses into one token

def entropy(s):
    if not s: return 0.0
    n = len(s); return -sum(c / n * math.log2(c / n) for c in (s.count(ch) for ch in set(s)))

def mask_tok(t):
    return t[:2] + '***' if len(t) > 2 else '***'

def mask_line(line):
    if PEM.search(line):
        return '[masked: PEM block marker]'
    line = URL_CRED.sub(lambda m: m.group(1) + m.group(2) + ':***@', line)
    # long high-entropy tokens anywhere (base64 blobs, keys) -- but keep paths/class names readable
    def _long(m):
        t = m.group(0)
        core = t.rstrip('=')                                  # base64 padding is not part of an identifier
        if core != t and re.fullmatch(r'(?:[A-Z]?[a-z]{2,}|[A-Z]{2,}|\d{1,8}|_|-)+', core):
            return t                                          # 'someKeyName=' : key followed by '=' in key=value
        t = core if core != t and not re.fullmatch(r'[A-Za-z0-9+/]+', core) else t
        if '/' in t and t.count('/') > 2: return m.group(0)  # file path
        if re.fullmatch(r'[a-z0-9_\-]+', t): return t        # lower-case identifiers
        if re.fullmatch(r'[a-z0-9_.\-]+(/[a-z0-9_.\-]+)+/?', t): return t   # registry key paths (frontend/nodejs/product-name)
        if re.fullmatch(r'(?:[A-Z]?[a-z]{2,}|[A-Z]{2,}|\d{1,8}|_|-)+', t): return t   # CamelCase / CONSTANT_NAMES / dotted-class parts
        return mask_tok(t) if entropy(t) > 3.6 else t
    line = LONGTOK.sub(_long, line)
    # password-shaped quoted literals anywhere: >=6 chars, no spaces, >=3 of 4 char classes
    def _pw(m):
        t = m.group(2)
        if re.fullmatch(r'[A-Za-z_$][\w$]*(\.[\w$]+)+', t) or re.fullmatch(r'v?\d+(\.\d+)+([.\-][\w]+)?', t):
            return m.group(0)                                 # dotted class/package names and version strings are not passwords
        if re.fullmatch(r'[a-z0-9_.-]+(/[a-z0-9_.-]+)+/?', t):
            return m.group(0)                                 # registry key paths like frontend/nodejs/product-version
        if t.startswith(('$', '-D', '-X', '--', '${')) or re.fullmatch(r'[A-Za-z_$][\w$]*', t):
            return m.group(0)                                 # shell variables, JVM/CLI flags, plain identifiers
        classes = sum(bool(re.search(c, t)) for c in (r'[a-z]', r'[A-Z]', r'[0-9]', r'[^A-Za-z0-9]'))
        if '\\' in t or re.search(r'[\[\](){}^$|?*+]{2,}', t):   # regex literals, not passwords
            return m.group(0)
        mixed = bool(re.search(r'[a-z]', t)) and bool(re.search(r'[A-Z]', t))
        if t.count(':') >= 3 or re.fullmatch(r'[a-z]+-\d[\w.\-]*', t):          # getopt specs, branch names like lit-2610
            return m.group(0)
        if len(t) >= 6 and classes >= 3 and (mixed or entropy(t) > 3.2) and not re.fullmatch(r'[\w.\-/:${}]+\.(java|xml|js|ts|py|sh|json|yml|yaml|html|css|scss)', t):
            return m.group(1) + mask_tok(t) + m.group(1)
        return m.group(0)
    line = QUOTED.sub(_pw, line)
    # Literatum props style: <string name="accessKey">v</string> -> secret-ish name attribute masks the text
    line = re.sub(r'''(<\w+[^>]*\bname\s*=\s*["'][^"']*(key|pass|pwd|secret|token|salt|auth|cred|private|signature)[^"']*["'][^>]*>)([^<]+)(</\w+>)''',
                  lambda m: m.group(1) + mask_tok(m.group(3).strip()) + m.group(4), line, flags=re.I)
    # XML element text whose tag name is secret-ish: <sslpass>v</sslpass>, <password>v</password>
    line = re.sub(r'(<([A-Za-z_:\-]*(pass|pwd|secret|token|key|salt|auth|cred)[A-Za-z_:\-]*)[^>]*>)([^<]+)(</\2>)',
                  lambda m: m.group(1) + mask_tok(m.group(4).strip()) + m.group(5), line, flags=re.I)
    # bare password-shaped value after a short flag: -x Val1d!Pw  (not $vars, paths or plain words)
    def _flagval(m):
        t = m.group(2)
        classes = sum(bool(re.search(c, t)) for c in (r'[a-z]', r'[A-Z]', r'[0-9]', r'[^A-Za-z0-9]'))
        if len(t) >= 6 and classes >= 3 and not t.startswith(('$', '/', '.', '-')) and '/' not in t:
            return m.group(1) + mask_tok(t)
        return m.group(0)
    line = re.sub(r'''(\s-[A-Za-z]\s+)([^\s"'$][^\s"']{5,})''', _flagval, line)
    multi_lit = len(re.findall(r'''["'][^"'\s]{3,}["']\s*,''', line)) >= 2          # f("a", "b", ...) credential-style calls
    # multi-literal calls alone no longer trigger blanket masking (they hid plain words in argv lists);
    # password-shaped literals in them are still caught by _pw above.
    if KEYWORDS.search(line) or re.search(r'\b(login|sftp|mysql|sqlcmd|curl -u|wget --user|jira|getInstance|connect)\b', line):
        line = QUOTED.sub(lambda m: m.group(1) + mask_tok(m.group(2)) + m.group(1), line)
        def _assign(m):
            v = m.group(2)
            key = re.findall(r'[\w.\-]+', line[:m.start()])
            if key and re.search(r'(pass(?!port|age|ive|ing)|pwd|secret|token|api_?key|_key$|key$|license|salt|auth(?!or)|cred|private_?key|bearer)', key[-1], re.I):
                return m.group(1) + mask_tok(v)          # the KEY itself is secret-ish: mask whatever the value looks like
            # keep code: identifiers, dotted calls, literals like null/true/new/this, numbers < 6 digits, ${vars}
            if re.fullmatch(r'(null|true|false|new|this|return|[A-Za-z_][\w.]*\(?|\d{1,5}|\d+(\.\d+){1,3}[A-Za-z0-9.\-]{0,12}|\$\{?[\w.]+\}?)[;,)]*', v):
                return m.group(0)
            return m.group(1) + mask_tok(v)
        line = ASSIGN.sub(_assign, line)
    return line

SKIP_NAMES = re.compile(r'(\.env$|\.pem$|\.key$|\.p12$|\.jks$|\.keystore$|id_rsa|vault|credentials|secrets?\.)', re.I)

def view(path, start=1, end=None):
    if path == '-':                      # stdin: e.g.  git show <ref>:<path> | safe_view.py -
        for i, l in enumerate(sys.stdin, 1):
            if i < start: continue
            if end and i > end: break
            print(f'{i}: {mask_line(l.rstrip())}')
        return
    if SKIP_NAMES.search(os.path.basename(path)):
        print(f'[refused: {path} looks like a credential file]'); return
    with open(path, errors='replace') as f:
        for i, l in enumerate(f, 1):
            if i < start: continue
            if end and i > end: break
            print(f'{i}: {mask_line(l.rstrip())}')

def grep(rx, paths):
    r = re.compile(rx, re.I)
    for p in paths:
        for root, dirs, files in os.walk(p) if os.path.isdir(p) else [(os.path.dirname(p), [], [os.path.basename(p)])]:
            dirs[:] = [d for d in dirs if d not in ('.git', 'node_modules', 'target', 'build')]
            for fn in files:
                fp = os.path.join(root, fn)
                if SKIP_NAMES.search(fn): continue
                try:
                    with open(fp, errors='replace') as f:
                        for i, l in enumerate(f, 1):
                            if r.search(l): print(f'{fp}:{i}: {mask_line(l.rstrip())[:300]}')
                except (IsADirectoryError, PermissionError, OSError):
                    pass

if __name__ == '__main__':
    a = sys.argv[1:]
    if not a: print(__doc__); sys.exit(1)
    if a[0] == '--grep': grep(a[1], a[2:] or ['.'])
    else: view(a[0], int(a[1]) if len(a) > 1 else 1, int(a[2]) if len(a) > 2 else None)
