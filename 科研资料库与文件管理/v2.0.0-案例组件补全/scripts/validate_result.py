#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_result.py — 校验 result.json 含 case_id 与 output_contract 全部字段。

退出码：0=通过；1=失败（缺失字段或 JSON 非法）。
"""
import argparse
import json
import os
import sys


def contract_fields(case):
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
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--result", default=None)
    args = ap.parse_args()

    case_path = os.path.join(args.input, "case.json")
    case = json.load(open(case_path, encoding="utf-8")) if os.path.exists(case_path) else {}
    result_path = args.result or os.path.join(args.output, "result.json")

    problems = []
    try:
        result = json.load(open(result_path, encoding="utf-8"))
    except Exception as exc:
        print("[validate_result] FAIL: result.json unreadable: %s" % exc)
        return 1

    if not result.get("case_id"):
        problems.append("missing case_id")
    elif case.get("case_id") and result["case_id"] != case["case_id"]:
        problems.append("case_id mismatch: %s vs %s" % (result["case_id"], case["case_id"]))
    for f in contract_fields(case):
        if f not in result:
            problems.append("missing output_contract field: %s" % f)
    if not result.get("status"):
        problems.append("missing status")

    if problems:
        for p in problems:
            print("[validate_result] FAIL: %s" % p)
        return 1
    print("[validate_result] OK: case_id=%s fields=%d status=%s" %
          (result.get("case_id"), len(contract_fields(case)), result.get("status")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
