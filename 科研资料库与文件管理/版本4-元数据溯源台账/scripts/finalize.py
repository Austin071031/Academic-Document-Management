#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py —— result.json 生成器。

--partial：尽早写出部分结果（status=partial，output_contract 字段先置 null）。
--final ：汇总全部产物。
  - case_id 与 output_contract 字段原样来自 /input/case.json；能映射到产物的填产物
    相对路径，映射不到的填 null 并在 uncertainty 中说明（绝不猜）。
  - status / sources / uncertainty / change_records 诚实生成。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

# output_contract 常见键 -> 产物相对路径（存在才填）
ARTIFACT_MAP = {
    "manifest": "manifest.json",
    "manifest_path": "manifest.json",
    "manifest_json": "manifest.json",
    "manifest_csv": "manifest.csv",
    "library": "library",
    "library_dir": "library",
    "duplicates": "duplicates.json",
    "duplicates_path": "duplicates.json",
    "versions": "versions.json",
    "versions_path": "versions.json",
    "provenance": "provenance.jsonl",       # 复制到 output 后有效
    "provenance_path": "provenance.jsonl",
    "coverage_report": "field_coverage_report.md",
    "coverage_report_path": "field_coverage_report.md",
    "field_coverage_report": "field_coverage_report.md",
}


def load_case(input_root):
    case = lc.jread(os.path.join(input_root, "case.json"), default=None)
    if isinstance(case, dict):
        return case
    return {}


def contract_keys(case):
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        return [str(k) for k in oc]
    return []


def collect_uncertainty(work, output):
    items = []
    for r in lc.jlines(os.path.join(work, "files.jsonl")) or []:
        if not r.get("readable"):
            items.append({"item": r["relpath"],
                          "reason": "unreadable: %s" % "; ".join(r.get("errors") or ["unknown"])})
    for r in lc.jlines(os.path.join(work, "content_unreadable.jsonl")) or []:
        items.append({"item": r.get("file"),
                      "reason": "content %s: %s" % (r.get("status"), r.get("reason"))})
    for r in lc.jlines(os.path.join(work, "companion_unmatched.jsonl")) or []:
        items.append({"item": "%s row %s (%s)" % (r.get("table"), r.get("row"), r.get("target", "")),
                      "reason": "companion row unmatched: %s" % r.get("reason")})
    adj = lc.jread(os.path.join(work, "adjudicate_summary.json"), default={}) or {}
    if adj.get("fields_with_conflicts"):
        items.append({"item": "adjudication",
                      "reason": "%d 个字段存在多来源冲突，已按优先级裁决，落选证据保留于 provenance.jsonl conflicts"
                                % adj["fields_with_conflicts"]})
    scan = lc.jread(os.path.join(work, "scan_summary.json"), default={}) or {}
    for d in scan.get("empty_dirs") or []:
        items.append({"item": d, "reason": "空目录，已登记，无元数据可抽取"})
    for ev in scan.get("archives") or []:
        if ev.get("status") != "ok":
            items.append({"item": ev.get("archive"),
                          "reason": "压缩包无法展开: %s" % "; ".join(ev.get("errors") or [])})
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--partial", action="store_true")
    g.add_argument("--final", action="store_true")
    a = ap.parse_args()

    os.makedirs(a.output, exist_ok=True)
    case = load_case(a.input)
    result = {"case_id": case.get("case_id")}

    keys = contract_keys(case)
    if a.partial:
        for k in keys:
            result[k] = None
        result.update({
            "status": "partial",
            "status_reason": "pipeline started; this file will be overwritten by --final",
            "sources": [],
            "uncertainty": [{"item": "pipeline", "reason": "still running"}],
            "change_records": [],
            "written_at": lc.now_iso(),
        })
        lc.jwrite(os.path.join(a.output, "result.json"), result)
        print("[finalize] partial result.json written")
        return 0

    # --final：把 provenance.jsonl 复制到 output，保证产物自包含
    prov_src = os.path.join(a.work, "provenance.jsonl")
    prov_dst = os.path.join(a.output, "provenance.jsonl")
    if os.path.exists(prov_src):
        try:
            with open(prov_src, encoding="utf-8") as fi, \
                 open(prov_dst, "w", encoding="utf-8") as fo:
                fo.write(fi.read())
        except OSError as e:
            sys.stderr.write("[finalize] copy provenance failed: %s\n" % e)

    steps = lc.jread(os.path.join(a.work, "pipeline_steps.json"), default=None)
    all_ok = steps.get("all_ok") if steps else None

    for k in keys:
        if k in ("case_id", "status", "sources", "uncertainty", "change_records"):
            continue
        rel = ARTIFACT_MAP.get(k) or ARTIFACT_MAP.get(k.lower())
        if rel and os.path.exists(os.path.join(a.output, rel)):
            result[k] = rel
        else:
            result[k] = None

    sources = [f for f in ("manifest.json", "manifest.csv", "duplicates.json",
                           "versions.json", "provenance.jsonl",
                           "field_coverage_report.md", "library")
               if os.path.exists(os.path.join(a.output, f))]
    uncertainty = collect_uncertainty(a.work, a.output)
    for k in keys:
        if result.get(k) is None and k not in ("status",):
            uncertainty.append({"item": "output_contract.%s" % k,
                                "reason": "无对应产物可填，置 null（绝不猜测）"})

    change_records = list(lc.jlines(os.path.join(a.work, "change_log.jsonl")) or [])
    # 不可读输入已被登记处理，不算管线失败；只有步骤非零退出才 partial
    status = "complete" if all_ok else "partial"
    result.update({
        "status": status,
        "status_reason": "all pipeline steps ok; unreadable inputs (if any) are registered in uncertainty"
                         if all_ok else
                         "one or more pipeline steps exited non-zero; see uncertainty",
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": change_records,
        "written_at": lc.now_iso(),
    })
    lc.jwrite(os.path.join(a.output, "result.json"), result)
    lc.log_change(a.work, "finalize", "result.json", "aggregate work artifacts",
                  "status=%s, %d sources, %d uncertainty items"
                  % (status, len(sources), len(uncertainty)))
    print("[finalize] final result.json status=%s" % status)
    return 0


if __name__ == "__main__":
    sys.exit(main())
