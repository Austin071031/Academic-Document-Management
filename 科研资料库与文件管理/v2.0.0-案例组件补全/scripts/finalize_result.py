#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
finalize_result.py — 合并 Agent 叙述与脚本产物，生成最终 result.json。

用法：
  python3 finalize_result.py --input /input --work /app/work --output /app/output \
      [--agent work/result_agent.json]

若 work/result_agent.json（或 --agent 指定）存在，其中非 null 的顶层字段
覆盖 partial result.json 的同名字段；随后按 verify_report 自动修正 status：
  PASS -> success，存在 skipped/mismatch -> partial，verify 缺失 -> partial。
"""
import argparse
import json
import os
from datetime import datetime, timezone


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--agent", default=None)
    args = ap.parse_args()

    result_path = os.path.join(args.output, "result.json")
    result = {}
    if os.path.exists(result_path):
        result = json.load(open(result_path, encoding="utf-8"))

    agent_path = args.agent or os.path.join(args.work, "result_agent.json")
    if os.path.exists(agent_path):
        agent = json.load(open(agent_path, encoding="utf-8"))
        for k, v in agent.items():
            if v is not None and not k.startswith("_"):
                result[k] = v

    vr_path = os.path.join(args.output, "verify_report.json")
    verify_verdict = None
    if os.path.exists(vr_path):
        vr = json.load(open(vr_path, encoding="utf-8"))
        verify_verdict = vr.get("verdict")
        result["verify"] = {
            "verdict": vr.get("verdict"),
            "totals": vr.get("totals"),
            "report": "verify_report.json",
        }
    if verify_verdict == "PASS":
        result["status"] = "success"
    else:
        result.setdefault("status", "partial")
        if verify_verdict is None:
            result["uncertainty"] = (result.get("uncertainty") or []) + \
                ["verify 未运行或报告缺失，交付完整性未经独立复核。"]

    result["finalized_at"] = utcnow()
    with open(result_path, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print("[finalize_result] wrote %s status=%s verify=%s" %
          (result_path, result.get("status"), verify_verdict))


if __name__ == "__main__":
    main()
