#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""orchestrate.py — 【v2.0.0-A 旗舰】多问题覆盖编排器。

平台案例常含多个检索问题（case.json 的 questions/searches/queries 字段，
或 task.md 的编号问句）。本模块：
1. 从 case.json + task.md 抽取全部问题（含每问自带的条件短语）；
2. 对每问调用 retrieve.py（子进程）得到逐问命中，调用 verify 校验；
3. 生成覆盖矩阵 coverage.json：
   question × {命中数, verified 数, 最佳锚点, 状态}，
   并计算 completeness_self_score（已校验回答的问题占比）；
4. 合并 hits 写回 hits.json（每问 top-N 合并去重），供后续 report 使用。

用法: python3 orchestrate.py --input-root /input --work-dir /app/work --topk 5
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Journal, read_json, write_json

QUESTION_KEYS = ("questions", "searches", "queries", "tasks", "items")
RE_NUMQ = re.compile(r"^\s*(?:\d{1,2}[.、)]|[-*•]|[（(]\d{1,2}[)）]|Q\d*[:：])\s*(.{6,200})$")
RE_QMARK = re.compile(r"[?？]\s*$")


def collect_questions(case, task_text):
    qs = []
    seen = set()

    def add(text, source):
        t = re.sub(r"\s+", " ", (text or "").strip())
        if len(t) < 6 or t.lower() in seen:
            return
        seen.add(t.lower())
        qs.append({"qid": "q%02d" % (len(qs) + 1), "text": t, "source": source})

    def dig(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k.lower() in QUESTION_KEYS and isinstance(v, list):
                    for it in v:
                        if isinstance(it, str):
                            add(it, "case.json:%s" % k)
                        elif isinstance(it, dict):
                            q = (it.get("question") or it.get("query")
                                 or it.get("q") or it.get("text") or "")
                            if q:
                                add(q, "case.json:%s" % k)
                            if it.get("filters") or it.get("constraints"):
                                qs[-1]["constraints"] = it.get("filters") \
                                    or it.get("constraints")
                elif k.lower() in ("question", "query") and isinstance(v, str):
                    add(v, "case.json:%s" % k)
                elif isinstance(v, (dict, list)):
                    dig(v)
        elif isinstance(obj, list):
            for x in obj:
                dig(x)

    dig(case)
    for line in (task_text or "").splitlines():
        m = RE_NUMQ.match(line)
        cand = m.group(1).strip() if m else None
        if cand and (RE_QMARK.search(cand) or len(cand) > 10):
            add(cand, "task.md")
    if not qs and case.get("task"):
        add(case["task"], "case.json:task")
    return qs


def per_question_filter(q, base_filter):
    flt = dict(base_filter or {})
    c = q.get("constraints")
    if isinstance(c, dict):
        flt.update(c)
    return flt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--topk", type=int, default=5)
    ap.add_argument("--filter", default=None)
    a = ap.parse_args()

    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    case = read_json(os.path.join(a.input_root, "case.json"), {}) or {}
    task_text = ""
    tf = os.path.join(a.input_root, "task.md")
    if os.path.exists(tf):
        task_text = open(tf, encoding="utf-8", errors="replace").read()

    questions = collect_questions(case, task_text)
    journal.log("3.1-orchestrate", "questions=%d" % len(questions))
    if not questions:
        write_json(os.path.join(a.work_dir, "coverage.json"), {
            "questions": [], "note": "no questions parsed; agent must identify "
            "the question(s) from task.md and run retrieve.py manually",
            "completeness_self_score": None})
        print("no questions parsed; manual retrieval required")
        return 0

    base_filter = {}
    if a.filter:
        raw = open(a.filter, encoding="utf-8").read() \
            if os.path.exists(a.filter) else a.filter
        base_filter = json.loads(raw)

    script_dir = os.path.dirname(os.path.abspath(__file__))
    merged, coverage = [], []
    for q in questions:
        hits_path = os.path.join(a.work_dir, "hits_%s.json" % q["qid"])
        flt = per_question_filter(q, base_filter)
        cmd = [sys.executable, os.path.join(script_dir, "retrieve.py"),
               "--work-dir", a.work_dir, "--query", q["text"],
               "--topk", str(a.topk), "--hits-out", hits_path]
        if flt:
            cmd += ["--filter", json.dumps(flt, ensure_ascii=False)]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        data = read_json(hits_path, {}) or {}
        hits = data.get("hits", [])
        for h in hits:
            h["qid"] = q["qid"]
        merged.extend(hits)
        coverage.append({
            "qid": q["qid"], "question": q["text"], "source": q.get("source"),
            "constraints": q.get("constraints"),
            "hits": len(hits), "verified": 0, "status": "candidates_only",
            "top_anchor": hits[0]["anchor"] if hits else None,
            "filter_applied": flt or None,
            "retrieve_stderr": (r.stderr or "")[:200] if r.returncode else None,
        })
        journal.log("3.1-orchestrate", "%s: %d hits" % (q["qid"], len(hits)),
                    status="ok" if hits else "partial")

    # 合并去重写回 hits.json，随后统一机器校验再回填覆盖状态
    dedup, seen = [], set()
    for h in sorted(merged, key=lambda x: -x.get("score", 0)):
        akey = json.dumps(h.get("anchor", {}).get("file_path")) + \
            str(h.get("anchor", {}).get("paragraph_id")) + (h.get("qid") or "")
        if akey in seen:
            continue
        seen.add(akey)
        dedup.append(h)
    write_json(os.path.join(a.work_dir, "hits.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "query": "multi-question (%d)" % len(questions),
        "questions": [q["text"] for q in questions],
        "filter": base_filter,
        "hits": dedup,
        "stats": {"questions": len(questions), "hits": len(dedup)},
    })

    subprocess.run([sys.executable, os.path.join(script_dir, "verify.py"),
                    "--work-dir", a.work_dir], capture_output=True, text=True,
                   timeout=300)
    verified_hits = (read_json(os.path.join(a.work_dir, "hits.json"), {})
                     or {}).get("hits", [])
    by_qid = {}
    for h in verified_hits:
        if h.get("verified"):
            by_qid.setdefault(h.get("qid"), []).append(h)
    for c in coverage:
        vh = by_qid.get(c["qid"], [])
        c["verified"] = len(vh)
        if vh:
            c["status"] = "answered"
            c["top_anchor"] = vh[0]["anchor"]
        elif c["hits"] == 0:
            c["status"] = "unanswered"

    answered = sum(1 for c in coverage if c["status"] == "answered")
    score = round(answered / len(coverage), 3) if coverage else None
    write_json(os.path.join(a.work_dir, "coverage.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "questions": coverage,
        "totals": {"questions": len(coverage), "answered": answered,
                   "candidates_only": sum(1 for c in coverage
                                          if c["status"] == "candidates_only"),
                   "unanswered": sum(1 for c in coverage
                                     if c["status"] == "unanswered")},
        "completeness_self_score": score,
        "policy": "每个问题必须至少一条 verified 证据才算 answered；"
                  "未达的问题在 answer 中逐项说明原因",
    })
    journal.log("3.1-orchestrate", "coverage score=%s (%d/%d)"
                % (score, answered, len(coverage)),
                status="ok" if score == 1.0 else "partial")
    print("questions=%d answered=%d score=%s" % (len(coverage), answered, score))
    return 0


if __name__ == "__main__":
    sys.exit(main())
