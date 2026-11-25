#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recover.py — 【v2.0.0-E 旗舰】降级保底装配器。

保证无论流水线哪一环中断，/app/output 里始终存在一份**诚实的** result.json：
1. 检查六个关键产物（inventory/corpus/sections/hits/verification/lineage），
   缺失的按序重跑一次（每步限一次，防死循环）；
2. 仍缺失的在 degraded_report.json 中如实记录阶段缺失与原因；
3. 强制装配 result.json（skeleton → 若无答案则填 degraded 说明 → finalize），
   status 依缺失阶段定为 partial 或 failed，绝不留空结果。
"""
import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Journal, read_json, write_json

STAGES = [
    ("inventory.json", "inventory.py", ["--input-root", None, "--work-dir", None]),
    ("corpus.json", "extract.py", ["--input-root", None, "--work-dir", None]),
    ("sections.json", "segment.py", ["--work-dir", None]),
    ("lineage.json", "lineage.py", ["--work-dir", None]),
    ("hits.json", None, []),          # 需 query，缺则不重跑，记 degraded
    ("verification.json", "verify.py", ["--work-dir", None]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    a = ap.parse_args()
    j = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(a.output_dir, exist_ok=True)

    degraded, recovered = [], []
    for artifact, script, args in STAGES:
        path = os.path.join(a.work_dir, artifact)
        if os.path.exists(path):
            continue
        if script:
            cmd = [sys.executable, os.path.join(script_dir, script)]
            for i, v in enumerate(args):
                cmd.append(a.input_root if v is None and args[i - 1] ==
                           "--input-root" else (a.work_dir if v is None else v))
            r = subprocess.run(cmd, capture_output=True, text=True,
                               timeout=300)
            if os.path.exists(path):
                recovered.append({"artifact": artifact, "via": script})
                j.log("5.5-recover", "rerun %s -> ok" % script,
                      status="recovered")
                continue
            degraded.append({"artifact": artifact, "stage": script,
                             "rerun_rc": r.returncode,
                             "stderr": (r.stderr or "")[:300]})
        else:
            degraded.append({"artifact": artifact,
                             "stage": "retrieve (requires query)",
                             "note": "未提供查询问题；如需检索请手动运行 "
                                     "retrieve.py --query <问题>"})
        j.log("5.5-recover", "missing %s" % artifact, status="failed")

    write_json(os.path.join(a.output_dir, "degraded_report.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "recovered_stages": recovered, "degraded_stages": degraded,
        "policy": "缺失阶段如实报告；result.json 一定落盘，status 不为 success"})

    # 强制装配 result.json
    rpath = os.path.join(a.output_dir, "result.json")
    subprocess.run([sys.executable, os.path.join(script_dir, "report.py"),
                    "--skeleton", "--input-root", a.input_root,
                    "--work-dir", a.work_dir, "--output-dir", a.output_dir],
                   capture_output=True, text=True, timeout=120)
    result = read_json(rpath, {}) or {}
    if degraded and not result.get("answer"):
        result["answer"] = None
        result["degraded"] = True
        result["empty_reason"] = ("流水线阶段缺失: %s；已尽力恢复: %d 个" %
                                  ([d["artifact"] for d in degraded],
                                   len(recovered)))
        if not result.get("status"):
            result["status"] = "failed" if not recovered and len(degraded) >= 4 \
                else "partial"
        unc = result.get("uncertainty") or []
        unc.append("degraded mode: " + result["empty_reason"])
        result["uncertainty"] = unc
        write_json(rpath, result)
    subprocess.run([sys.executable, os.path.join(script_dir, "report.py"),
                    "--finalize", "--input-root", a.input_root,
                    "--work-dir", a.work_dir, "--output-dir", a.output_dir],
                   capture_output=True, text=True, timeout=120)
    j.log("5.5-recover", "degraded=%d recovered=%d result written"
          % (len(degraded), len(recovered)),
          status="partial" if degraded else "ok")
    print("degraded=%d recovered=%d" % (len(degraded), len(recovered)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
