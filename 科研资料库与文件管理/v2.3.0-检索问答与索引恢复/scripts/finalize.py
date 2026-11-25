#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize：写 result.json（step0 可先写 partial，step6 写完整）。

result.json 字段：
  case_id / status / sources / uncertainty / change_records
  output_contract: 对 case.json 中 output_contract 的逐字段回应
    （必填产物给 路径+exists:true；无法满足的字段诚实标注 not_satisfied+原因）
  deliverables: 关键产物路径清单
  verify: 校验结论摘要（verify_report.json 回填）
  searches: search_results.json 摘要

诚实原则：不编造；抽不到的信息标 unspecified 并写入 uncertainty。
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

STD_DELIVERABLES = [
    ("archive", "archive/{case_id}_archive.tar.gz"),
    ("sha256sums", "archive/SHA256SUMS"),
    ("manifest", "archive/MANIFEST.json"),
    ("handoff_readme", "archive/HANDOFF_README.md"),
    ("verify_report", "verify_report.json"),
    ("library", "library/"),
    ("index_db", "library/index/library_index.db"),
    ("inventory", "inventory.jsonl"),
    ("duplicates", "duplicates.json"),
    ("versions", "versions.json"),
    ("manifest_full", "manifest.json"),
    ("search_results", "search_results.json"),
    ("organize_report", "organize_report.json"),
]


def contract_result(case, output_dir):
    """逐字段回应 output_contract。"""
    contract = case.get("output_contract")
    out = {"raw": contract, "fields": {}}
    if contract is None:
        out["note"] = "case.json 无 output_contract 字段，交付默认清单"
        contract = {"required_deliverables": "default"}
    case_id = str(case.get("case_id", "unknown_case"))

    def check(rel_tpl):
        rel = rel_tpl.format(case_id=case_id)
        full = os.path.join(output_dir, rel.rstrip("/"))
        exists = os.path.isdir(full) if rel.endswith("/") else os.path.isfile(full)
        return {"path": rel, "exists": bool(exists)}

    if isinstance(contract, dict):
        for k, v in contract.items():
            lk = str(k).lower()
            if lk in ("required_files", "files", "deliverables",
                      "required_deliverables", "outputs", "artifacts"):
                wanted = v if isinstance(v, (list, tuple)) else [v]
                out["fields"][k] = {"requested": list(wanted),
                                    "resolved": [check(str(x))
                                                 if "{" in str(x) else
                                                 {"path": str(x),
                                                  "exists": os.path.isfile(
                                                      os.path.join(output_dir,
                                                                   str(x)))}
                                                 for x in wanted]}
            else:
                out["fields"][k] = {"value": v, "handled": "passthrough",
                                    "note": "非产物清单型字段，原样回应"}
    elif isinstance(contract, (list, tuple)):
        out["fields"]["required"] = {
            "requested": [str(x) for x in contract],
            "resolved": [check(str(x)) for x in contract]}
    else:
        out["fields"]["value"] = {"value": contract,
                                  "note": "output_contract 非结构化，原样回应"}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--partial", action="store_true",
                    help="写 partial 结果（step0，产物尚不全）")
    ap.add_argument("--status", default=None)
    args = ap.parse_args()
    input_dir = os.path.abspath(args.input)
    work_dir = os.path.abspath(args.work)
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    case = lib.json_load(os.path.join(input_dir, "case.json"), default={}) or {}
    case_id = str(case.get("case_id", "unknown_case"))

    # change_records：各步骤追加的 work/change_records.jsonl + 本步骤
    changes = []
    cr_path = os.path.join(work_dir, "change_records.jsonl")
    if os.path.isfile(cr_path):
        with open(cr_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        changes.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    deliverables = {}
    for name, rel_tpl in STD_DELIVERABLES:
        rel = rel_tpl.format(case_id=case_id)
        full = os.path.join(output_dir, rel.rstrip("/"))
        exists = os.path.isdir(full) if rel.endswith("/") else os.path.isfile(full)
        deliverables[name] = {"path": rel, "exists": bool(exists)}

    verify = lib.json_load(os.path.join(output_dir, "verify_report.json"))
    searches = lib.json_load(os.path.join(output_dir, "search_results.json"))
    organize = lib.json_load(os.path.join(output_dir, "organize_report.json"))

    sources = [
        {"source": "input/case.json", "role": "评测输入与 output_contract"},
        {"source": "input/task.md", "role": "任务说明与可能的期限/密级"},
        {"source": "input/ 资料库文件", "role": "被整理归档的原始资料"},
        {"source": "organize.py", "role": "归位/账本/去重/版本链"},
        {"source": "build_index.py + query_index.py",
         "role": "检索库与检索回答"},
        {"source": "make_archive.py + verify_archive.py",
         "role": "归档打包与独立校验"},
    ]

    uncertainty = []
    ctx = lib.json_load(os.path.join(output_dir, "context_snapshot.json"),
                        default={}) or {}
    policy = ctx.get("policy") or {}
    for fld in ("retention", "access_level"):
        if policy.get(fld, {}).get("value") in (None, "unspecified"):
            uncertainty.append(
                "%s 未在 case.json/task.md 中抽到，已填 unspecified，"
                "需人工补录" % fld)

    missing = [k for k, v in deliverables.items() if not v["exists"]]
    if args.partial:
        status = "partial"
        uncertainty.append("partial：pipeline 仍在执行，产物未全部生成")
    elif args.status:
        status = args.status
    elif missing or not verify or verify.get("status") != "ok":
        status = "partial"
        uncertainty.append("部分交付物缺失或校验未通过: %s" % missing)
    else:
        status = "complete"
    if verify and verify.get("status") not in ("ok", None):
        uncertainty.append("归档校验状态: %s（详见 verify_report.json）" %
                           verify.get("status"))

    result = {
        "case_id": case_id,
        "status": status,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "partial": bool(args.partial),
        "output_contract": contract_result(case, output_dir),
        "deliverables": deliverables,
        "sources": sources,
        "uncertainty": uncertainty,
        "change_records": changes,
        "summary": {
            "organize": organize,
            "verify": None if verify is None else {
                "status": verify.get("status"),
                "counts": verify.get("counts")},
            "searches": None if searches is None else {
                "queries": len(searches.get("results", [])),
                "answered": sum(1 for r in searches.get("results", [])
                                if r.get("answered"))},
        },
    }
    lib.json_dump(result, os.path.join(output_dir, "result.json"))
    lib.log("finalize: status=%s partial=%s missing=%s" %
            (status, args.partial, missing))
    return 0


if __name__ == "__main__":
    sys.exit(main())
