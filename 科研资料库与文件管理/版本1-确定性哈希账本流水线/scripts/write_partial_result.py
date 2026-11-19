#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
write_partial_result.py — 尽早生成诚实的 partial result.json。

读取 <input>/case.json 的 output_contract 字段，逐项生成占位；
status=partial；sources/uncertainty/change_records 先放已知事实。
Agent 之后可用 finalize_result.py 合并叙述字段。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def contract_fields(case):
    """output_contract 可能是 list[str] 或 dict，统一返回字段名列表。"""
    oc = case.get("output_contract")
    if isinstance(oc, dict):
        return list(oc.keys())
    if isinstance(oc, list):
        out = []
        for item in oc:
            if isinstance(item, str):
                out.append(item)
            elif isinstance(item, dict):
                out.append(item.get("name") or item.get("field") or str(item))
        return out
    if isinstance(oc, str):
        return [oc]
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    args = ap.parse_args()
    os.makedirs(args.output, exist_ok=True)

    case_path = os.path.join(args.input, "case.json")
    case = {}
    if os.path.exists(case_path):
        try:
            case = json.load(open(case_path, encoding="utf-8"))
        except Exception as exc:
            print("[write_partial_result] case.json unreadable: %s" % exc)
    fields = contract_fields(case)

    # 已知事实（脚本产物状态）
    facts = {"sources": [], "uncertainty": [], "change_records": []}
    for name, path in [("inventory.jsonl", os.path.join(args.work, "inventory.jsonl")),
                       ("operation_log.jsonl", os.path.join(args.output, "operation_log.jsonl")),
                       ("verify_report.json", os.path.join(args.output, "verify_report.json"))]:
        if os.path.exists(path):
            facts["sources"].append({"type": name, "path": path})
    log_path = os.path.join(args.output, "operation_log.jsonl")
    if os.path.exists(log_path):
        with open(log_path, encoding="utf-8") as fh:
            logs = [json.loads(l) for l in fh if l.strip()]
        facts["change_records"] = logs[-200:]
        skipped = [l for l in logs if l.get("status") == "skipped"]
        if skipped:
            facts["uncertainty"].append(
                " %d 个文件因权限/错误被跳过（见 operation_log.jsonl），未纳入 library。" % len(skipped))

    result = {
        "case_id": case.get("case_id"),
        "status": "partial",
        "generated_at": utcnow(),
        "pipeline": "research-library-ledger-pipeline-v1",
        "note": "auto-generated partial result: narrative fields pending agent review",
    }
    for f in fields:
        result[f] = None
    result["_pending_fields"] = fields
    result["sources"] = facts["sources"]
    result["uncertainty"] = facts["uncertainty"]
    result["change_records"] = facts["change_records"]

    out = os.path.join(args.output, "result.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("[write_partial_result] wrote %s (fields=%d)" % (out, len(fields)))


if __name__ == "__main__":
    main()
