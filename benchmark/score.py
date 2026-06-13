#!/usr/bin/env python3
"""Greenloop benchmark scorer — measure audit detection quality against seeded fixtures.

Reads a corpus of fixtures (each a directory holding a ground-truth.json) and a
findings file (a greenloop audit's output, normalized per fixture), then computes
recall / precision / false-positive rate / severity accuracy. Optionally gates a
run against a committed baseline so a skill edit that *lowers* quality fails CI.

Stdlib only — no dependencies.

  score.py --corpus corpus --findings examples/run-good.json
  score.py --corpus corpus --findings run.json --baseline baseline.json --gate
  score.py --corpus corpus --findings examples/run-good.json --baseline baseline.json --write-baseline

Findings file shape (what an agent running app-audit emits — see README.md):
  { "<fixture-name>": { "findings": [
      {"file": "app.py", "line": 8, "category": 3, "severity": "critical", "title": "..."} ] }, ... }
"""
import argparse
import json
import os
import sys

SEV = ["info", "low", "medium", "high", "critical"]
TOLERANCE = 3  # a finding within +/- this many lines of the seeded line counts as a hit


def sev_idx(s):
    s = (s or "").lower()
    return SEV.index(s) if s in SEV else -1


def base(path):
    return os.path.basename(str(path)).strip()


def load_corpus(corpus_dir):
    fixtures = {}
    for name in sorted(os.listdir(corpus_dir)):
        gt = os.path.join(corpus_dir, name, "ground-truth.json")
        if os.path.isfile(gt):
            with open(gt) as f:
                fixtures[name] = json.load(f)
    return fixtures


def matches_seed(finding, seed):
    if base(finding.get("file", "")) != base(seed["file"]):
        return False
    return abs(int(finding.get("line", -999)) - int(seed["line"])) <= TOLERANCE


def in_zone(finding, zone):
    if base(finding.get("file", "")) != base(zone["file"]):
        return False
    lo, hi = zone["lines"]
    return lo <= int(finding.get("line", -999)) <= hi


def score(fixtures, findings_by_fixture):
    total_seeded = found_seeded = 0
    tp = fp = extra = 0
    sev_ok = sev_total = 0
    total_findings = 0
    per_fixture = {}

    for name, gt in fixtures.items():
        seeds = gt.get("seeded", [])
        zones = gt.get("clean_zones", [])
        findings = (findings_by_fixture.get(name) or {}).get("findings", [])
        total_findings += len(findings)

        found_ids = []
        for seed in seeds:
            total_seeded += 1
            hit = next((f for f in findings if matches_seed(f, seed)), None)
            if hit:
                found_seeded += 1
                tp += 1
                sev_total += 1
                if abs(sev_idx(hit.get("severity")) - sev_idx(seed.get("severity"))) <= 1:
                    sev_ok += 1
                found_ids.append(seed["id"])

        f_fp = 0
        for f in findings:
            if any(matches_seed(f, s) for s in seeds):
                continue  # already counted as a true positive
            if any(in_zone(f, z) for z in zones):
                fp += 1
                f_fp += 1
            else:
                extra += 1  # unmatched and not in a clean zone — unscored (could be a real unseeded bug)

        per_fixture[name] = {
            "seeded": len(seeds),
            "found": found_ids,
            "missed": [s["id"] for s in seeds if s["id"] not in found_ids],
            "findings": len(findings),
            "false_positives": f_fp,
        }

    return {
        "recall": round(found_seeded / total_seeded, 4) if total_seeded else 1.0,
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else 1.0,
        "fp_rate": round(fp / total_findings, 4) if total_findings else 0.0,
        "severity_accuracy": round(sev_ok / sev_total, 4) if sev_total else 1.0,
        "seeded_total": total_seeded,
        "seeded_found": found_seeded,
        "false_positives": fp,
        "extra_findings": extra,
        "total_findings": total_findings,
        "per_fixture": per_fixture,
    }


def gate(current, baseline, recall_drop=0.05, fp_rise=0.05, precision_drop=0.05):
    fails = []
    if current["recall"] < baseline["recall"] - recall_drop:
        fails.append(f"recall {current['recall']} < baseline {baseline['recall']} - {recall_drop}")
    if current["precision"] < baseline["precision"] - precision_drop:
        fails.append(f"precision {current['precision']} < baseline {baseline['precision']} - {precision_drop}")
    if current["fp_rate"] > baseline["fp_rate"] + fp_rise:
        fails.append(f"fp_rate {current['fp_rate']} > baseline {baseline['fp_rate']} + {fp_rise}")
    return fails


def main():
    ap = argparse.ArgumentParser(description="Greenloop benchmark scorer")
    ap.add_argument("--corpus", required=True, help="corpus dir (subdirs with ground-truth.json)")
    ap.add_argument("--findings", required=True, help="normalized findings JSON, keyed by fixture")
    ap.add_argument("--baseline", help="baseline scorecard JSON")
    ap.add_argument("--gate", action="store_true", help="exit nonzero if current regresses vs baseline")
    ap.add_argument("--write-baseline", action="store_true", help="write current metrics to --baseline")
    args = ap.parse_args()

    fixtures = load_corpus(args.corpus)
    with open(args.findings) as f:
        findings_by_fixture = json.load(f)
    card = score(fixtures, findings_by_fixture)
    print(json.dumps(card, indent=2))

    if args.write_baseline:
        if not args.baseline:
            print("--write-baseline needs --baseline", file=sys.stderr)
            sys.exit(2)
        keep = ("recall", "precision", "fp_rate", "severity_accuracy")
        with open(args.baseline, "w") as f:
            json.dump({k: card[k] for k in keep}, f, indent=2)
            f.write("\n")
        print(f"\nbaseline written: {args.baseline}", file=sys.stderr)

    if args.gate:
        if not args.baseline or not os.path.isfile(args.baseline):
            print("gate: no baseline to compare against — skipping", file=sys.stderr)
            return
        with open(args.baseline) as f:
            base_card = json.load(f)
        fails = gate(card, base_card)
        if fails:
            print("\nGATE FAILED — quality regressed vs baseline:", file=sys.stderr)
            for x in fails:
                print("  -", x, file=sys.stderr)
            sys.exit(1)
        print("\ngate: PASS — no regression vs baseline", file=sys.stderr)


if __name__ == "__main__":
    main()
