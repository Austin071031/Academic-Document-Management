#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""主入口：归档交付工作流（archive-first）。

  python3 scripts/archive_pipeline.py --input /input --work /app/work --output /app/output

步骤：
  step0 检查输入，写 partial result.json（磁盘不足也能先落清单）
  step1 organize.py   归位 + 账本 + 去重 + 版本链 + 元数据
  step2 build_index.py  建 sqlite 检索库
  step3 query_index.py  回答 case 检索问题 -> search_results.json
  step4 make_archive.py 打包四件套
  step5 verify_archive.py 独立校验，结论写回 verify_report.json
  step6 finalize.py   写完整 result.json

每一步异常都被捕获并登记 change_records，单步失败不阻断 partial 交付。
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

HERE = os.path.dirname(os.path.abspath(__file__))


def run_step(name, cmd, work_dir):
    t0 = time.time()
    logf = os.path.join(work_dir, "logs")
    os.makedirs(logf, exist_ok=True)
    out_path = os.path.join(logf, "%s.log" % name)
    rec = {"step": name, "cmd": cmd, "started_utc":
           time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    try:
        with open(out_path, "w", encoding="utf-8") as lf:
            p = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT,
                               timeout=600)
        rec["returncode"] = p.returncode
        rec["ok"] = p.returncode == 0
        with open(out_path, "r", encoding="utf-8", errors="replace") as lf:
            rec["log_tail"] = lf.read()[-2000:]
    except Exception as e:  # 超时/启动失败等
        rec["returncode"] = None
        rec["ok"] = False
        rec["log_tail"] = "%s: %s" % (type(e).__name__, e)
    rec["duration_s"] = round(time.time() - t0, 3)
    lib.jsonl_append(os.path.join(work_dir, "change_records.jsonl"), rec)
    lib.log("step %s -> rc=%s (%.1fs)" %
            (name, rec["returncode"], rec["duration_s"]))
    return rec["ok"]


def collect_questions(case):
    qs = []
    for key in ("searches", "questions", "queries"):
        v = case.get(key)
        if isinstance(v, str):
            qs.append(v)
        elif isinstance(v, (list, tuple)):
            for item in v:
                if isinstance(item, str):
                    qs.append(item)
                elif isinstance(item, dict):
                    q = item.get("q") or item.get("query") or \
                        item.get("question")
                    if q:
                        qs.append(str(q))
    return qs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    input_dir = os.path.abspath(args.input)
    work_dir = os.path.abspath(args.work)
    output_dir = os.path.abspath(args.output)
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    case = lib.json_load(os.path.join(input_dir, "case.json"), default={}) or {}
    case_id = str(case.get("case_id", "unknown_case"))
    py = sys.executable

    # step0：输入检查 + partial result
    checks = {
        "input_exists": os.path.isdir(input_dir),
        "case_json": os.path.isfile(os.path.join(input_dir, "case.json")),
        "task_md": os.path.isfile(os.path.join(input_dir, "task.md")),
        "output_writable": os.access(output_dir, os.W_OK),
    }
    lib.json_dump({"case_id": case_id, "checks": checks,
                   "checked_utc": time.strftime(
                       "%Y-%m-%dT%H:%M:%SZ", time.gmtime())},
                  os.path.join(output_dir, "step0_checks.json"))
    lib.jsonl_append(os.path.join(work_dir, "change_records.jsonl"),
                     {"step": "step0", "checks": checks})
    run_step("finalize_partial",
             [py, os.path.join(HERE, "finalize.py"), "--partial",
              "--input", input_dir, "--work", work_dir,
              "--output", output_dir], work_dir)

    # step1 organize
    if not run_step("organize",
                    [py, os.path.join(HERE, "organize.py"),
                     "--input", input_dir, "--output", output_dir],
                    work_dir):
        run_step("finalize_partial2",
                 [py, os.path.join(HERE, "finalize.py"), "--partial",
                  "--status", "partial",
                  "--input", input_dir, "--work", work_dir,
                  "--output", output_dir], work_dir)
        lib.log("organize 失败，已交付 partial 结果")
        return 2

    # step2 build_index
    run_step("build_index",
             [py, os.path.join(HERE, "build_index.py"),
              "--output", output_dir], work_dir)

    # step3 检索问题
    db = os.path.join(output_dir, "library", "index", "library_index.db")
    results = []
    for q in collect_questions(case):
        entry = {"question": q, "answered": False, "hits": []}
        if os.path.isfile(db):
            try:
                sys.path.insert(0, HERE)
                import query_index
                r = query_index.query(db, q, limit=10)
                entry["hits"] = r.get("hits", [])
                entry["mode"] = r.get("mode")
                entry["answered"] = True
            except Exception as e:
                entry["error"] = "%s: %s" % (type(e).__name__, e)
        else:
            entry["error"] = "index db missing"
        results.append(entry)
    lib.json_dump({"case_id": case_id, "results": results},
                  os.path.join(output_dir, "search_results.json"))
    lib.jsonl_append(os.path.join(work_dir, "change_records.jsonl"),
                     {"step": "step3", "queries": len(results),
                      "answered": sum(1 for r in results if r["answered"])})

    # step4 make_archive
    run_step("make_archive",
             [py, os.path.join(HERE, "make_archive.py"),
              "--input", input_dir, "--output", output_dir], work_dir)

    # step5 verify_archive
    verify_ok = run_step("verify_archive",
                         [py, os.path.join(HERE, "verify_archive.py"),
                          "--input", input_dir, "--output", output_dir],
                         work_dir)

    # step5a 恢复/索引操作（v2.3.0 增量）：case.json 的 recovery 任务 +
    # 恢复后联动索引重建；全部操作写 recovery_log.jsonl，失败记账不崩溃
    run_step("recovery_ops",
             [py, os.path.join(HERE, "recovery_ops.py"),
              "--input", input_dir, "--output", output_dir], work_dir)

    # step5b 检索问答（v2.3.0 增量）：兼容字符串/对象形态的
    # searches/questions -> search_results.json + query_log.jsonl，
    # 无命中绝不编答案
    run_step("answer_questions",
             [py, os.path.join(HERE, "answer_questions.py"),
              "--input", input_dir, "--output", output_dir], work_dir)

    # step6 finalize（完整）
    run_step("finalize",
             [py, os.path.join(HERE, "finalize.py"),
              "--input", input_dir, "--work", work_dir,
              "--output", output_dir,
              "--status", "complete" if verify_ok else "partial"],
             work_dir)

    # v2.3.0：把 recovery/QA 结果并入 result.json 的 sources 与 summary
    try:
        rpath = os.path.join(output_dir, "result.json")
        result = lib.json_load(rpath, {}) or {}
        srcs = result.get("sources") or []
        existing = {s.get("source") for s in srcs if isinstance(s, dict)}
        for s in ({"source": "recovery_ops.py",
                   "role": "恢复操作与索引重建（recovery_log.jsonl）"},
                  {"source": "answer_questions.py",
                   "role": "searches/questions 检索问答"
                           "（search_results.json + query_log.jsonl）"}):
            if s["source"] not in existing:
                srcs.append(s)
        result["sources"] = srcs
        summary = result.setdefault("summary", {})
        rec_counts = {"restore_ok": 0, "restore_failed": 0,
                      "rebuild_index_ok": 0, "rebuild_index_failed": 0}
        rlog = os.path.join(output_dir, "recovery_log.jsonl")
        if os.path.isfile(rlog):
            with open(rlog, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        lr = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    key = "%s_%s" % (lr.get("op"), lr.get("result"))
                    if key in rec_counts:
                        rec_counts[key] += 1
        summary["recovery"] = rec_counts
        sr = lib.json_load(os.path.join(output_dir, "search_results.json"),
                           default={}) or {}
        summary["qa"] = {
            "questions": sr.get("question_count"),
            "evidence_complete": sr.get("evidence_complete_count")}
        lib.json_dump(result, rpath)
    except Exception as e:
        lib.log("merge recovery/qa into result.json failed: %s" % e)

    result = lib.json_load(os.path.join(output_dir, "result.json"), {}) or {}
    lib.log("pipeline done: status=%s" % result.get("status"))
    return 0 if result.get("status") == "complete" else 2


if __name__ == "__main__":
    sys.exit(main())
