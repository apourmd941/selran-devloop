#!/usr/bin/env python3
"""Apply team suppressions (.greenloopignore + inline markers) to greenloop findings.

Every mature analyzer lets a team durably say "we accept this" — but most
ignore-files live forever and quietly rot into blind spots. Greenloop's
suppressions are *governed*: every suppression needs a reason, suppressions on
Critical findings need an expiry date, expired suppressions stop suppressing,
and each run meta-audits the suppression set itself (expired / stale / invalid
/ over-broad). Suppressed findings are never deleted — they move to
status "suppressed", stay visible in status.json, the dashboard, and SARIF
(as suppression objects), and the CI merge gate skips them by construction
because they leave the "open" counts.

.greenloopignore format (repo root; one suppression per line):

    # comment
    <path-glob>[:<line>] [<rule-glob>] -- <reason ...> [expires:YYYY-MM-DD] [owner:<name>]

    vendor/**                    -- third-party code, not ours
    src/legacy/** cat6/*         -- legacy subsystem, sunset planned expires:2026-09-30 owner:aidin
    api/search.py:41 cat3/sql-injection -- FP: value comes from a closed enum expires:2026-12-01

Inline marker (same line as the finding, or the line directly above):

    // greenloop:ignore[cat3/secret-in-log] prefix is redacted upstream expires:2026-12-01
    #  greenloop:ignore[*] test fixture, intentionally vulnerable

Rule-globs match against the finding's rule id tail `cat<N>/<class>` (same ids
SARIF uses); omitted rule = `*`. Usage:

    greenloop-suppress.py --status .audit/status.json --ignore .greenloopignore \
        --repo . --scan-inline --out .audit/status.json

Stdlib only. Exit 0 always — governance reports, it doesn't break the build;
the merge gate reads the resulting open counts.
"""
import argparse
import datetime
import fnmatch
import json
import os
import re
import sys

TODAY = datetime.date.today()
MARKER = re.compile(r"greenloop:ignore\[([^\]]*)\]\s*(.*)")
EXPIRES = re.compile(r"\bexpires:(\d{4}-\d{2}-\d{2})\b")
OWNER = re.compile(r"\bowner:(\S+)\b")


def rule_tail(f):
    cat = f.get("category", "x")
    cls = (f.get("class") or f.get("type") or "finding")
    return f"cat{cat}/{cls}".replace(" ", "-")


def split_location(loc):
    m = re.match(r"^(.*?):(\d+)(?:-\d+)?$", str(loc or "").strip())
    return (m.group(1), int(m.group(2))) if m else (str(loc or "").strip(), None)


def parse_meta(text):
    """Pull expires:/owner: out of a reason string -> (reason, expires_date|None, owner|None, bad_expiry)."""
    expires = owner = None
    bad = False
    m = EXPIRES.search(text)
    if m:
        try:
            expires = datetime.date.fromisoformat(m.group(1))
        except ValueError:
            bad = True
        text = EXPIRES.sub("", text)
    m = OWNER.search(text)
    if m:
        owner = m.group(1)
        text = OWNER.sub("", text)
    return text.strip(), expires, owner, bad


def parse_ignore_file(path):
    """-> (entries, invalid). entry: dict(path_glob, line, rule_glob, reason, expires, owner, lineno, raw)."""
    entries, invalid = [], []
    if not os.path.isfile(path):
        return entries, invalid
    for lineno, raw in enumerate(open(path), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "--" not in line:
            invalid.append({"lineno": lineno, "raw": line, "why": "no '-- reason' — a suppression without a reason is invalid and does not suppress"})
            continue
        head, reason_part = line.split("--", 1)
        toks = head.split()
        if not toks:
            invalid.append({"lineno": lineno, "raw": line, "why": "missing path glob"})
            continue
        path_tok = toks[0]
        rule_glob = toks[1] if len(toks) > 1 else "*"
        if len(toks) > 2:
            invalid.append({"lineno": lineno, "raw": line, "why": "too many fields before '--' (want: path [rule] -- reason)"})
            continue
        pglob, pline = split_location(path_tok) if ":" in path_tok.split("/")[-1] else (path_tok, None)
        reason, expires, owner, bad = parse_meta(reason_part)
        if bad:
            invalid.append({"lineno": lineno, "raw": line, "why": "malformed expires: date (want YYYY-MM-DD)"})
            continue
        if not reason:
            invalid.append({"lineno": lineno, "raw": line, "why": "empty reason — a suppression without a reason is invalid"})
            continue
        entries.append({"path_glob": pglob, "line": pline, "rule_glob": rule_glob,
                        "reason": reason, "expires": expires, "owner": owner,
                        "lineno": lineno, "raw": line, "matched": 0})
    return entries, invalid


def find_inline(repo, f):
    """Look for a greenloop:ignore marker on the finding's line or the line above."""
    path, line = split_location(f.get("location"))
    if not path or not line:
        return None
    fp = os.path.join(repo, path)
    if not os.path.isfile(fp):
        return None
    try:
        lines = open(fp, errors="replace").read().splitlines()
    except OSError:
        return None
    for idx in (line - 1, line - 2):  # 0-based: same line, then line above
        if 0 <= idx < len(lines):
            m = MARKER.search(lines[idx])
            if m:
                rule_glob = m.group(1).strip() or "*"
                reason, expires, owner, bad = parse_meta(m.group(2))
                if bad or not reason:
                    return {"invalid": True, "why": "inline marker missing reason or has malformed expires:",
                            "at": f"{path}:{idx+1}"}
                return {"rule_glob": rule_glob, "reason": reason, "expires": expires,
                        "owner": owner, "source": f"inline {path}:{idx+1}"}
    return None


def entry_matches(e, f):
    path, line = split_location(f.get("location"))
    if not path:
        return False
    if not (fnmatch.fnmatch(path, e["path_glob"]) or fnmatch.fnmatch(path, e["path_glob"].rstrip("/") + "/*")):
        return False
    if e["line"] is not None and line != e["line"]:
        return False
    tail = rule_tail(f)
    return fnmatch.fnmatch(tail, e["rule_glob"]) or fnmatch.fnmatch("greenloop/" + tail, e["rule_glob"])


def apply(status, entries, invalid, repo, scan_inline):
    report = {"suppressed": 0, "expired": [], "invalid": [e["why"] + f" (line {e['lineno']})" for e in invalid],
              "critical_without_expiry": [], "stale": [], "over_broad": []}
    findings = status.get("findings_list") or []

    for f in findings:
        if f.get("status") not in (None, "open"):
            continue
        hit = None
        for e in entries:
            if entry_matches(e, f):
                hit = dict(e, source=f".greenloopignore:{e['lineno']}")
                e["matched"] += 1
                break
        if hit is None and scan_inline:
            inline = find_inline(repo, f)
            if inline and inline.get("invalid"):
                report["invalid"].append(f"{inline['why']} at {inline['at']}")
            elif inline and (fnmatch.fnmatch(rule_tail(f), inline["rule_glob"])
                             or inline["rule_glob"] == "*"):
                hit = inline
        if hit is None:
            continue

        sev = (f.get("severity") or "").lower()
        if hit.get("expires") and hit["expires"] < TODAY:
            report["expired"].append(f"{f.get('id','?')} @ {f.get('location','?')} — suppression expired {hit['expires']} ({hit.get('source','?')}); finding is OPEN again")
            continue
        if sev == "critical" and not hit.get("expires"):
            report["critical_without_expiry"].append(
                f"{f.get('id','?')} @ {f.get('location','?')} — Critical findings can be paused, not buried: suppression needs expires: ({hit.get('source','?')})")
            continue

        f["status"] = "suppressed"
        f["suppression"] = {"reason": hit["reason"], "source": hit.get("source", "?"),
                            "expires": hit["expires"].isoformat() if hit.get("expires") else None,
                            "owner": hit.get("owner")}
        report["suppressed"] += 1

    # meta-audit of the file entries themselves
    for e in entries:
        if e["matched"] == 0:
            report["stale"].append(f"line {e['lineno']}: '{e['raw']}' matched 0 findings — stale, remove it")
        if e["matched"] > 10:
            report["over_broad"].append(f"line {e['lineno']}: '{e['raw']}' suppressed {e['matched']} findings — over-broad, narrow it")

    # recount severity x status buckets
    sevs = ["critical", "high", "medium", "low", "info"]
    counts = {st: {s: 0 for s in sevs} for st in ("open", "fixed", "deferred", "dismissed", "suppressed")}
    for f in findings:
        st = f.get("status", "open")
        sv = (f.get("severity") or "info").lower()
        if st in counts and sv in sevs:
            counts[st][sv] += 1
    if "findings" in status or findings:
        status["findings"] = counts
    status["suppressions"] = {
        "applied": report["suppressed"],
        "expired": len(report["expired"]),
        "invalid": len(report["invalid"]),
        "stale_entries": len(report["stale"]),
        "over_broad": len(report["over_broad"]),
        "critical_blocked": len(report["critical_without_expiry"]),
    }
    return report


def main():
    ap = argparse.ArgumentParser(description="apply .greenloopignore + inline suppressions to status.json")
    ap.add_argument("--status", required=True)
    ap.add_argument("--ignore", default=".greenloopignore")
    ap.add_argument("--repo", default=".", help="repo root for inline-marker scanning")
    ap.add_argument("--scan-inline", action="store_true", help="also honor greenloop:ignore[...] comments at finding sites")
    ap.add_argument("--out", help="write updated status.json here (default: stdout)")
    args = ap.parse_args()

    with open(args.status) as fh:
        status = json.load(fh)
    entries, invalid = parse_ignore_file(args.ignore)
    report = apply(status, entries, invalid, args.repo, args.scan_inline)

    out = json.dumps(status, indent=2)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(out + "\n")
    else:
        print(out)

    p = lambda *a: print(*a, file=sys.stderr)
    p(f"suppressions applied: {report['suppressed']}")
    for key, label in (("expired", "EXPIRED (no longer suppressing)"), ("invalid", "INVALID (ignored)"),
                       ("critical_without_expiry", "CRITICAL WITHOUT EXPIRY (not suppressed)"),
                       ("stale", "STALE entries"), ("over_broad", "OVER-BROAD entries")):
        for item in report[key]:
            p(f"  [{label}] {item}")


if __name__ == "__main__":
    main()
