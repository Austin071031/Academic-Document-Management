#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit.py — 【版本5 旗舰】自校验审计与可复跑工作流。

交付前自动执行五道 gate，任何一道不过即如实降级状态：
  gate1 证据校验   : hits.json 中保留的证据必须 verified=true。
  gate2 契约完备   : result.json 含 output_contract 全部字段，必需字段非 null
                     （或带明确 uncertainty 说明）。
  gate3 状态诚实   : failures 非空时 status 不得为 success；
                     空结果集必须给出 empty_reason。
  gate4 清单一致   : manifest.json 中每个输出文件的 sha256 与实际一致。
  gate5 过程留痕   : run_journal.jsonl 覆盖盘点→抽取→切分→检索→校验→报告
                     六个阶段，缺段即 partial。

输出: <output>/audit_report.json（逐 gate 结果与局限声明），
并依据 gate 结果修正 result.json 的 status。
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (SKILL_VERSION, Journal, load_journal, read_json,
                    sha256_file, write_json)

STEPS = ["0-inventory", "1-extract", "1.5-pagefix", "2-segment", "2.5-lineage",
         "2.7-concepts", "3-retrieve", "3.5-constraints", "4-verify",
         "6-report"]


def run_gates(work, outdir, case):
    checks = []
    result_path = os.path.join(outdir, "result.json")
    result = read_json(result_path, {}) or {}
    hits = read_json(os.path.join(work, "hits.json"), {}) or {}
    journal = load_journal(os.path.join(work, "run_journal.jsonl"))

    # gate1
    kept = [h for h in hits.get("hits", [])]
    bad = [h for h in kept if not h.get("verified")]
    checks.append({"gate": 1, "name": "evidence_verified",
                   "passed": not bad,
                   "detail": "%d evidence, %d unverified" % (len(kept), len(bad)),
                   "unverified": [b.get("anchor", {}).get("file_path")
                                  for b in bad][:10]})

    # gate2
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, list):
        fields = {f: "required" for f in oc}
    elif isinstance(oc, dict) and "properties" in oc:
        fields = {k: ("required" if k in (oc.get("required") or []) else "optional")
                  for k in (oc.get("properties") or {})}
    elif isinstance(oc, dict):
        fields = {k: "specified" for k in oc}
    else:
        fields = {}
    missing = [f for f in fields if f not in result]
    uncertainty = result.get("uncertainty") or []
    null_required = [f for f, req in fields.items()
                     if req in ("required", "specified") and result.get(f) is None]
    checks.append({"gate": 2, "name": "contract_complete",
                   "passed": not missing and (not null_required or bool(uncertainty)),
                   "detail": "fields=%d missing=%d null_required=%d uncertainty_notes=%d"
                             % (len(fields), len(missing), len(null_required),
                                len(uncertainty)),
                   "missing": missing, "null_required": null_required})

    # gate3
    fails = result.get("failures") or []
    status = result.get("status")
    ok3 = status in ("success", "partial", "failed")
    if not ok3:
        detail = "status not set (%r)" % status
    else:
        detail = "status=%s failures=%d" % (status, len(fails))
        if fails and status == "success":
            ok3 = False
            detail += "; failures present but status=success"
        if not (result.get("evidence") or hits.get("hits")) \
                and not result.get("empty_reason"):
            ok3 = False
            detail += "; empty result without empty_reason"
    checks.append({"gate": 3, "name": "status_honest", "passed": ok3,
                   "detail": detail})

    # gate4
    manifest = read_json(os.path.join(outdir, "manifest.json"), {}) or {}
    mismatch = []
    for item in manifest.get("outputs", []):
        p = os.path.join(outdir, item.get("path", ""))
        if not os.path.exists(p) or sha256_file(p) != item.get("sha256"):
            mismatch.append(item.get("path"))
    checks.append({"gate": 4, "name": "manifest_consistent",
                   "passed": not mismatch,
                   "detail": "outputs=%d mismatch=%d"
                             % (len(manifest.get("outputs", [])), len(mismatch)),
                   "mismatch": mismatch})

    # gate5
    covered = set()
    for rec in journal:
        for s in STEPS:
            if str(rec.get("step", "")).startswith(s.split("-")[0]) or \
               rec.get("step", "").startswith(s):
                covered.add(s.split("-")[0])
    core = {"0", "1", "2", "3", "4", "6"}
    missing_steps = sorted(core - covered)
    checks.append({"gate": 5, "name": "journal_coverage",
                   "passed": not missing_steps,
                   "detail": "core steps covered: %d/%d"
                             % (len(core & covered), len(core)),
                   "missing_steps": missing_steps})

    overall = all(c["passed"] for c in checks)
    return checks, overall


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    ap.add_argument("--input-root", default="/input")
    a = ap.parse_args()
    j = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    case = read_json(os.path.join(a.input_root, "case.json"), {}) or {}

    checks, overall = run_gates(a.work_dir, a.output_dir, case)
    limitations = []
    for c in checks:
        if not c["passed"]:
            limitations.append("gate%d %s: %s" % (c["gate"], c["name"],
                                                  c["detail"]))

    report = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "skill_version": SKILL_VERSION,
        "overall": "pass" if overall else "fail",
        "gates": checks,
        "limitations": limitations,
        "reproduce": {
            "steps": [
                "python3 scripts/inventory.py --input-root /input --work-dir /app/work",
                "python3 scripts/extract.py --input-root /input --work-dir /app/work",
                "python3 scripts/segment.py --work-dir /app/work",
                "python3 scripts/retrieve.py --work-dir /app/work --query '<问题>'",
                "python3 scripts/verify.py --work-dir /app/work",
                "python3 scripts/report.py --skeleton && 补全答案 && python3 scripts/report.py --finalize",
            ],
            "inputs_sha256_source": "/app/work/inventory.json",
            "journal": "/app/work/run_journal.jsonl",
        },
    }
    write_json(os.path.join(a.output_dir, "audit_report.json"), report)

    # 依据 gate 修正 status
    rpath = os.path.join(a.output_dir, "result.json")
    result = read_json(rpath, {}) or {}
    if result:
        if overall and result.get("status") not in ("success", "partial", "failed"):
            result["status"] = "success"
        elif not overall and result.get("status") == "success":
            result["status"] = "partial"
        result["audit"] = {"overall": report["overall"],
                           "failed_gates": [c["gate"] for c in checks
                                            if not c["passed"]]}
        write_json(rpath, result)
    j.log("7-audit", "overall=%s limitations=%d" % (report["overall"],
                                                    len(limitations)),
          status="ok" if overall else "partial",
          outputs=[os.path.join(a.output_dir, "audit_report.json")])
    print("audit overall=%s" % report["overall"])
    for c in checks:
        print("  gate%d %-20s %s — %s" % (c["gate"], c["name"],
                                          "PASS" if c["passed"] else "FAIL",
                                          c["detail"]))
    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
