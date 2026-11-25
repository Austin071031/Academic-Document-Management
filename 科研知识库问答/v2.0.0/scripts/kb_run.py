#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_run.py -- 一键流水线: 从 case.json 直达检索命中包, 再组装交付骨架。

只读输入, 全自动执行阶段 1-5(盘点/抽取/去重版本/索引/检索), 生成:
  <work>/answers.json    预填骨架: 每题已有检索命中(evidence 候选坐标+摘录),
                         Agent 只需逐题核对命中段落并撰写 answer/claims/uncertainty
  <work>/ops_log.jsonl   每阶段自动追加一条 JSON 日志
  <work>/stage_report.txt 阶段摘要汇总

用法:
  python3 kb_run.py --case /input/case.json --work /app/work --outdir /app/output \
      [--rules /app/work/version_rules.json] [--all-versions]
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))


def log(work, step, command, status, notes=""):
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "step": step, "command": command, "status": status, "notes": notes}
    with open(os.path.join(work, "ops_log.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def run(work, step, argv, report):
    cmd_str = " ".join(argv)
    t0 = time.time()
    r = subprocess.run([sys.executable] + argv, capture_output=True, timeout=600)
    dt = time.time() - t0
    out = (r.stdout or b"").decode("utf-8", "replace")
    report.append("### %s (%.1fs, rc=%d)\n%s" % (step, dt, r.returncode, out))
    log(work, step, cmd_str, "ok" if r.returncode == 0 else "failed",
        out.strip().splitlines()[0] if out.strip() else "")
    return r.returncode == 0, out


def find_library(case, default="/input"):
    for k in ("library", "library_root", "documents", "docs_dir", "input_dir", "data_dir"):
        v = case.get(k)
        if isinstance(v, str) and os.path.isdir(v):
            return v
    # 回退: /input 下除 case.json/task.md 外最大的目录
    cands = [os.path.join(default, d) for d in sorted(os.listdir(default))
             if os.path.isdir(os.path.join(default, d))]
    return cands[0] if cands else default


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--library", default=None)
    ap.add_argument("--rules", default=None)
    ap.add_argument("--all-versions", action="store_true")
    ap.add_argument("--topk", type=int, default=8)
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.outdir, exist_ok=True)
    W, S = args.work, os.path.join(HERE)

    case = {}
    if os.path.isfile(args.case):
        with open(args.case, encoding="utf-8") as f:
            case = json.load(f)
    case_id = case.get("case_id") or case.get("id") or "unknown"
    lib = args.library or find_library(case)
    report = ["# kb_run 阶段报告 case_id=%s library=%s" % (case_id, lib), ""]

    # 阶段 0: result.json 骨架先行
    oc = case.get("output_contract") or case.get("outputContract") or []
    fields = ([k for k, v in oc.items()] if isinstance(oc, dict)
              else [x if isinstance(x, str) else x.get("name", "?") for x in oc])
    skeleton = {"case_id": case_id, "status": "partial"}
    skeleton.update({k: None for k in fields})
    skeleton_path = os.path.join(args.outdir, "result.json")
    if not os.path.isfile(skeleton_path):
        with open(skeleton_path, "w", encoding="utf-8") as f:
            json.dump(skeleton, f, ensure_ascii=False, indent=1)
    log(W, "stage0", "skeleton result.json", "ok", "fields=%d" % len(fields))

    # 问题清单: case.questions 或 task 字段中的列表
    questions = case.get("questions") or case.get("queries") or []
    if isinstance(questions, dict):
        questions = [{"id": k, "question": v} for k, v in questions.items()]
    elif isinstance(questions, list):
        questions = [q if isinstance(q, dict) else {"id": "q%d" % (i + 1), "question": q}
                     for i, q in enumerate(questions)]

    inv_ok, _ = run(W, "inventory",
                    [os.path.join(S, "kb_inventory.py"), "--roots", lib, "--work", W], report)
    if inv_ok:
        run(W, "extract",
            [os.path.join(S, "kb_extract.py"), "--inventory", os.path.join(W, "inventory.json"),
             "--root", lib, "--work", W], report)
        ver_argv = [os.path.join(S, "kb_versions.py"), "--inventory",
                    os.path.join(W, "inventory.json"), "--work", W]
        if args.rules and os.path.isfile(args.rules):
            ver_argv += ["--rules", args.rules]
        run(W, "versions", ver_argv, report)
        idx_argv = [os.path.join(S, "kb_index.py"), "--work", W]
        if args.all_versions:
            idx_argv.append("--all-versions")
        run(W, "index", idx_argv, report)
        if questions:
            qp = os.path.join(W, "questions.json")
            with open(qp, "w", encoding="utf-8") as f:
                json.dump(questions, f, ensure_ascii=False, indent=1)
            run(W, "search",
                [os.path.join(S, "kb_search.py"), "--work", W, "--questions", qp,
                 "--topk", str(args.topk)], report)

    # 预填 answers.json 骨架(含每题命中候选, Agent 据此核对撰写)
    hits_path = os.path.join(W, "hits.json")
    hits = {}
    if os.path.isfile(hits_path):
        with open(hits_path, encoding="utf-8") as f:
            hits = (json.load(f).get("questions") or {})
    answers = {"status": "partial", "answers": {}, "sources": [],
               "questions_without_evidence": [], "conflicts": [],
               "change_log": [], "uncertainty": {}}
    for q in questions:
        qid = q.get("id")
        cand = []
        for h in (hits.get(qid) or {}).get("hits", []):
            cand.append({"path": h["path"], "page": h.get("page"),
                         "para_index": h.get("para_index"),
                         "anchor_id": h["anchor_id"], "score": h["score"],
                         "exact_quote_candidate": h["text"][:200]})
        answers["answers"][qid] = {
            "question": q.get("question"),
            "answer": "<TODO: 依据下方命中候选核对原文后撰写, 每条论断挂证据>",
            "claims": [], "evidence": [],
            "uncertainty": "<A|B|C|D>",
            "searched": {"queries": [q.get("question")], "scope": "canonical",
                          "hits_considered": len(cand)},
            "_hit_candidates": cand,
        }
        if not cand:
            answers["questions_without_evidence"].append({
                "question": q.get("question"),
                "what_is_missing": "<TODO: 说明检索范围与缺失内容>"})
    ans_path = os.path.join(W, "answers.json")
    with open(ans_path, "w", encoding="utf-8") as f:
        json.dump(answers, f, ensure_ascii=False, indent=1)

    with open(os.path.join(W, "stage_report.txt"), "w", encoding="utf-8") as f:
        f.write("\n\n".join(report))

    sys.stdout.write("# kb_run 完成: case_id=%s questions=%d\n"
                     "# 下一步: 阅读 %s 逐题核对 _hit_candidates 撰写答案,\n"
                     "# 然后 python3 kb_result.py 合成, python3 kb_selfcheck.py 自检。\n"
                     % (case_id, len(questions), ans_path))


if __name__ == "__main__":
    main()
