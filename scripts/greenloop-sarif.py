#!/usr/bin/env python3
"""Convert a greenloop .audit/status.json into SARIF 2.1.0 (or GitLab Code Quality).

SARIF (Static Analysis Results Interchange Format) is the lingua franca for
analysis findings: GitHub code-scanning renders it inline on PRs and in the
Security tab, VS Code's SARIF viewer shows it in the Problems panel, and most
CI platforms ingest it. Emitting SARIF puts greenloop findings *where
developers already look* without us building any UI. GitLab uses its own Code
Quality JSON for inline-on-MR rendering, so `--gitlab-codequality` emits that
shape from the same input.

Input is status.json's `findings_list` (the per-finding array; see
workflow-reporting.md §1). Findings with a `file:line` location become SARIF
results with a physical location; locationless findings still emit (no region).

  greenloop-sarif.py --status .audit/status.json --out greenloop.sarif
  greenloop-sarif.py --status .audit/status.json --gitlab-codequality cq.json
  greenloop-sarif.py --status .audit/status.json            # SARIF to stdout

Stdlib only.
"""
import argparse
import json
import re
import sys

SCHEMA = "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/sarif-2.1.0.json"
# SARIF level is a fixed 4-value enum; greenloop's 5 severities collapse onto it.
SEV_TO_LEVEL = {"critical": "error", "high": "error", "medium": "warning",
                "low": "note", "info": "none"}
# security-severity is a GitHub convention (0.0-10.0) driving code-scanning sort/alerts.
SEV_TO_SCORE = {"critical": "9.5", "high": "8.0", "medium": "5.0", "low": "3.0", "info": "0.0"}


def parse_location(loc):
    """'auth/refresh.ts:88' or 'auth/refresh.ts:88-92' -> (path, start_line, end_line)."""
    if not loc:
        return None, None, None
    m = re.match(r"^(.*?):(\d+)(?:-(\d+))?$", str(loc).strip())
    if not m:
        return str(loc).strip(), None, None  # a bare path, no line
    path, a, b = m.group(1), int(m.group(2)), m.group(3)
    return path, a, int(b) if b else a


def rule_id(f):
    cat = f.get("category", "x")
    cls = (f.get("class") or f.get("type") or "finding")
    return f"greenloop/cat{cat}/{cls}".replace(" ", "-")


def to_sarif(status):
    findings = status.get("findings_list") or []
    rules, rule_index = [], {}
    results = []

    for f in findings:
        rid = rule_id(f)
        if rid not in rule_index:
            rule_index[rid] = len(rules)
            rules.append({
                "id": rid,
                "name": rid.replace("/", "_"),
                "shortDescription": {"text": f.get("class") or f.get("type") or "finding"},
                "defaultConfiguration": {"level": SEV_TO_LEVEL.get((f.get("severity") or "info").lower(), "warning")},
                "properties": {
                    "category": f.get("category"),
                    "security-severity": SEV_TO_SCORE.get((f.get("severity") or "info").lower(), "0.0"),
                    "tags": ["greenloop", f"category-{f.get('category')}"],
                },
            })

        sev = (f.get("severity") or "info").lower()
        result = {
            "ruleId": rid,
            "ruleIndex": rule_index[rid],
            "level": SEV_TO_LEVEL.get(sev, "warning"),
            "message": {"text": f.get("title") or f.get("class") or "greenloop finding"},
            "properties": {
                "severity": sev,
                "confidence": f.get("confidence"),
                "provenance": f.get("provenance"),
                "greenloop-id": f.get("id"),
                "status": f.get("status", "open"),
            },
        }
        # partialFingerprints make GitHub de-dupe alerts across re-runs even if lines shift.
        fp_basis = f"{rid}|{f.get('id','')}|{f.get('location','')}"
        result["partialFingerprints"] = {"greenloopFindingId/v1": fp_basis}

        # Team suppressions (greenloop-suppress.py) become SARIF suppression
        # objects — platforms show the alert as dismissed-with-reason instead of
        # the finding silently vanishing from the report.
        sup = f.get("suppression")
        if sup:
            result["suppressions"] = [{
                "kind": "external",
                "justification": f"{sup.get('reason','')}"
                                 + (f" (expires {sup['expires']})" if sup.get("expires") else "")
                                 + (f" [{sup.get('source','')}]" if sup.get("source") else ""),
            }]

        path, start, end = parse_location(f.get("location"))
        if path:
            ploc = {"artifactLocation": {"uri": path}}
            if start:
                ploc["region"] = {"startLine": start, "endLine": end or start}
            result["locations"] = [{"physicalLocation": ploc}]
        results.append(result)

    versions = status.get("skills") or {}
    return {
        "$schema": SCHEMA,
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "greenloop",
                "informationUri": "https://github.com/apourmd941/selran-devloop",
                "version": str(versions.get("app-audit", status.get("round", "1"))),
                "rules": rules,
            }},
            "automationDetails": {"id": f"greenloop/round/{status.get('round','?')}"},
            "results": results,
            "properties": {
                "repo": status.get("repo"),
                "round": status.get("round"),
                "head": status.get("head"),
                "scope": status.get("scope"),
            },
        }],
    }


# GitLab Code Quality severity enum: info | minor | major | critical | blocker.
SEV_TO_GITLAB = {"critical": "critical", "high": "major", "medium": "minor",
                 "low": "info", "info": "info"}


def to_gitlab_codequality(status):
    out = []
    for f in status.get("findings_list") or []:
        path, start, _ = parse_location(f.get("location"))
        sev = (f.get("severity") or "info").lower()
        entry = {
            "description": f.get("title") or f.get("class") or "greenloop finding",
            "check_name": rule_id(f),
            "fingerprint": f"{rule_id(f)}|{f.get('id','')}|{f.get('location','')}",
            "severity": SEV_TO_GITLAB.get(sev, "minor"),
        }
        if path:
            entry["location"] = {"path": path, "lines": {"begin": start or 1}}
        else:
            # GitLab requires a location; locationless findings anchor to the repo root marker.
            entry["location"] = {"path": "AUDIT_LOG.md", "lines": {"begin": 1}}
        out.append(entry)
    return out


def main():
    ap = argparse.ArgumentParser(description="greenloop status.json -> SARIF 2.1.0 / GitLab Code Quality")
    ap.add_argument("--status", required=True, help="path to .audit/status.json")
    ap.add_argument("--out", help="output .sarif (default: stdout)")
    ap.add_argument("--gitlab-codequality", metavar="FILE", help="also emit GitLab Code Quality JSON to FILE")
    args = ap.parse_args()

    with open(args.status) as f:
        status = json.load(f)
    if "findings_list" not in status:
        print("warning: status.json has no findings_list — emitting an empty SARIF run "
              "(add findings_list per workflow-reporting.md §1 for inline annotations)",
              file=sys.stderr)

    if args.gitlab_codequality:
        cq = to_gitlab_codequality(status)
        with open(args.gitlab_codequality, "w") as f:
            json.dump(cq, f, indent=2)
            f.write("\n")
        print(f"wrote {args.gitlab_codequality}: {len(cq)} Code Quality entr(ies)", file=sys.stderr)
        if not args.out:
            return  # gitlab-only run

    sarif = to_sarif(status)
    text = json.dumps(sarif, indent=2)
    if args.out:
        with open(args.out, "w") as f:
            f.write(text + "\n")
        n = len(sarif["runs"][0]["results"])
        print(f"wrote {args.out}: {n} result(s), {len(sarif['runs'][0]['tool']['driver']['rules'])} rule(s)",
              file=sys.stderr)
    else:
        print(text)


if __name__ == "__main__":
    main()
