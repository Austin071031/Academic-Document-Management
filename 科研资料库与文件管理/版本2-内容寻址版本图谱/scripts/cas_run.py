#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""cas_run：全链路编排入口。

  python3 cas_run.py --input /input --work /app/work --output /app/output

step0  检查 /input 可读性；
step1  cas_ingest   内容寻址入库（对象库 + 账本）；
step1b finalize     立即写 status=partial 的 result.json（保底产出）；
step2  build_index  逻辑索引 + tree/ 工作树；
step3  lineage      版本谱系图谱 versions.json/.dot；
step4  search       倒排索引回答 keyword searches；
step5  finalize     写最终 result.json；
step5b verify_cas   复跑核对 tree 与对象库。

每个步骤独立 try/except：单步失败记账并继续，绝不让整个流程崩溃。
"""
import argparse
import json
import os
import sys
import time
import traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description="内容寻址科研资料库全链路")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    input_dir, work_dir, output_dir = a.input, a.work, a.output
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    import cas_ingest
    import build_index
    import lineage
    import search as search_mod
    import finalize
    import verify_cas

    run_log = {"started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime()),
               "steps": [], "errors": []}

    # ---- step0：检查 /input
    step0 = {"step": "check_input", "ok": True}
    if not os.path.isdir(input_dir):
        step0["ok"] = False
        step0["error"] = "输入目录不存在: %s" % input_dir
        run_log["errors"].append(step0["error"])
    elif not os.path.exists(os.path.join(input_dir, "case.json")):
        step0["warning"] = "未找到 case.json，将仅做通用整理"
    run_log["steps"].append(step0)

    def run_step(name, fn, *args):
        t0 = time.time()
        rec = {"step": name}
        try:
            rec["result"] = fn(*args)
            rec["ok"] = True
        except Exception as e:  # 单步失败记账继续
            rec["ok"] = False
            rec["error"] = "%s: %s" % (type(e).__name__, e)
            rec["traceback"] = traceback.format_exc()[-2000:]
            run_log["errors"].append("%s: %s" % (name, rec["error"]))
        rec["seconds"] = round(time.time() - t0, 2)
        run_log["steps"].append(rec)
        print("[cas_run] %-12s %s (%.1fs)"
              % (name, "ok" if rec["ok"] else "FAILED: %s" % rec["error"],
                 rec["seconds"]))
        return rec["ok"]

    # ---- step1 入库
    run_step("ingest", cas_ingest.ingest, input_dir, work_dir, output_dir)
    # ---- step1b 保底 partial result.json
    run_step("partial_result", finalize.build_result,
             input_dir, work_dir, output_dir, "partial",
             list(run_log["errors"]))
    # ---- step2 索引与工作树
    run_step("build_index", build_index.build_index,
             input_dir, work_dir, output_dir)
    # ---- step3 版本谱系
    run_step("lineage", lineage.build_lineage, input_dir, work_dir,
             output_dir)
    # ---- step4 检索
    run_step("search", search_mod.run_search, input_dir, work_dir,
             output_dir)
    # ---- step5 最终 result.json
    run_step("finalize", finalize.build_result,
             input_dir, work_dir, output_dir, "final",
             list(run_log["errors"]))
    # ---- step5b 复跑核对
    run_step("verify", verify_cas.verify, input_dir, work_dir, output_dir)

    run_log["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime())
    with open(os.path.join(work_dir, "run_log.json"), "w",
              encoding="utf-8") as f:
        json.dump(run_log, f, ensure_ascii=False, indent=2)

    result_path = os.path.join(output_dir, "result.json")
    print("[cas_run] done. result.json=%s errors=%d"
          % (os.path.exists(result_path), len(run_log["errors"])))
    return 0 if os.path.exists(result_path) else 1


if __name__ == "__main__":
    sys.exit(main())
