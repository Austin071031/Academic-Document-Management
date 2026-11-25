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

v2.1.0 增量（可核验证据强化，仅追加，基座步骤不变）：
step6  render_evidence  版本谱系/目录树 → 真实 SVG 证据图（+matplotlib PNG 尽力）；
step7  recover_qa       按 case.json 恢复请求从对象库恢复并校验哈希、
                        重建索引、检索结果同步写 <output>/search_results.json；
step7b verify（复核）   恢复文件进 tree 后重跑核对，保持 verify_report 一致；
step8  preflight        提交契约自检 → <output>/preflight_report.json；
step9  merge            把证据图/恢复/自检摘要并入 result.json。

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

    # ================= v2.1.0 增量：可核验证据强化 =================
    pre_extra_errors = len(run_log["errors"])  # 用于新步骤失败时降级 status
    import render_evidence
    import recover as recover_mod
    import preflight_check
    from cas_common import read_json, write_json

    # ---- step6 证据图渲染（SVG 必须；PNG 视 matplotlib 可用性尽力，
    #      缺失时登记 "matplotlib unavailable, SVG only"，绝不崩溃）
    run_step("render_evidence", render_evidence.render,
             input_dir, work_dir, output_dir)
    # ---- step7 恢复/QA：对象库恢复 + 哈希校验 + 索引重建 + 检索同步
    run_step("recover_qa", recover_mod.run_recovery,
             input_dir, work_dir, output_dir)
    # ---- step7b 恢复后复核：tree 新增恢复文件，重跑核对保持报告一致
    run_step("verify_after_recover", verify_cas.verify,
             input_dir, work_dir, output_dir)

    # ---- step8 提交契约自检（针对 Skill 包自身）
    def _preflight():
        rep = preflight_check.check(preflight_check.skill_root())
        write_json(os.path.join(output_dir, "preflight_report.json"), rep)
        return rep["stats"]

    run_step("preflight", _preflight)

    # ---- step9 把证据图/恢复/自检摘要并入 result.json（不改 finalize 逻辑，
    #      仅追加 artifacts/uncertainty/change_records 条目）
    def _merge_evidence():
        rp = os.path.join(output_dir, "result.json")
        result = read_json(rp)
        if not result:
            return None
        art = result.setdefault("artifacts", {})
        unc = result.setdefault("uncertainty", [])
        cr = result.setdefault("change_records", [])
        # 新增步骤若有失败且原状态为 complete，诚实降级
        new_errors = run_log["errors"][pre_extra_errors:]
        if new_errors and result.get("status") == "complete":
            result["status"] = "complete_with_warnings"
        rs = read_json(os.path.join(work_dir, "render_summary.json")) or {}
        for k, v in (rs.get("artifacts") or {}).items():
            art["evidence_" + k] = v
        for w in rs.get("warnings") or []:
            unc.append("render_evidence: %s" % w)
        cr.append("render_evidence: 证据图产物 %s；渲染警告 %d 条" % (
            sorted((rs.get("artifacts") or {}).keys()),
            len(rs.get("warnings") or [])))
        rc = read_json(os.path.join(work_dir, "recover_summary.json")) or {}
        art["recovery_log"] = "library/recovery_log.jsonl"
        if rc.get("search_synced"):
            art["search_results_top"] = "search_results.json"
        cr.append("recover_qa: 恢复请求 %s 条（成功 %s、失败 %s）；"
                  "索引重建=%s；检索结果同步=%s" % (
                      rc.get("requests", 0), rc.get("restored", 0),
                      rc.get("failed", 0), rc.get("index_rebuilt"),
                      rc.get("search_synced")))
        for e in (rc.get("errors") or [])[:10]:
            unc.append("recover_qa: %s" % e)
        pf = read_json(os.path.join(output_dir, "preflight_report.json")) or {}
        art["preflight_report"] = "preflight_report.json"
        if pf:
            if not pf.get("ok", True):
                unc.append("preflight: 提交契约自检未通过: %s"
                           % "; ".join(pf.get("violations", [])[:5]))
            cr.append("preflight: 提交契约自检%s（文件 %s 个，共 %sB）" % (
                "通过" if pf.get("ok") else "未通过",
                pf.get("stats", {}).get("files", "?"),
                pf.get("stats", {}).get("total_bytes", "?")))
        write_json(rp, result)
        return {"merged": True}

    run_step("merge_evidence", _merge_evidence)

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
