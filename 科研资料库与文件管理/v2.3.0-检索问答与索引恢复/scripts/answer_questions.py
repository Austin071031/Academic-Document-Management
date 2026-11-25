#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索问答链路（v2.3.0 新增，对应案例 searches/questions 考点）。

读取 case.json 的 searches/questions/queries（兼容字符串与对象两种
形态），用 library/index/library_index.db 检索，输出：

  <output>/search_results.json
    {case_id, generated_utc, results: [
      {question, answer, hits: [{path, line, snippet}],
       evidence_complete: true/false, no_evidence_reason,
       answered, mode, elapsed_ms}]}
  <output>/query_log.jsonl   查询语句/耗时/命中数（供效率核验）

原则：无命中绝不编答案——answer 置 null 并给出 no_evidence_reason。
管理性问题（保存期限/密级）优先引用 context_snapshot 中带来源的
policy 值，证据不完整时如实标注。
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import query_index

MAX_SNIPPETS = 5
SNIPPET_LEN = 300
MAX_FALLBACK = 24

# 疑问词尾（剥离后重查）：自然语言问题 -> 可命中子串
INTERROG = re.compile(
    r"(是多少|是什么|为什么|怎么[样来办]|哪些|多少|多久|何时|何地|哪里|"
    r"哪个|谁|吗|呢|吧|[？?！!。.，,；;：:\s])+$")
CJK_RUN = re.compile(r"[一-鿿㐀-䶿]{3,}")


def fallback_queries(q):
    """主查询无命中时的退化查询序列：剥疑问词尾 -> CJK 串后缀收缩。"""
    cands = []
    base = q.strip()
    stripped = INTERROG.sub("", base).strip()
    if stripped and stripped != base:
        cands.append(stripped)
    for run in CJK_RUN.findall(stripped or base):
        for k in range(1, len(run) - 1):
            sub = run[:-k]
            if len(sub) >= 2 and sub not in cands and sub != base:
                cands.append(sub)
        if len(cands) >= MAX_FALLBACK:
            break
    return cands[:MAX_FALLBACK]


def collect_questions(case):
    """兼容字符串与对象两种形态，保留原始形态供溯源。"""
    qs = []
    for key in ("searches", "questions", "queries"):
        v = case.get(key)
        if v is None:
            continue
        items = v if isinstance(v, (list, tuple)) else [v]
        for item in items:
            if isinstance(item, str):
                if item.strip():
                    qs.append({"question": item.strip(), "raw": item,
                               "source_key": key})
            elif isinstance(item, dict):
                q = (item.get("q") or item.get("query") or
                     item.get("question") or item.get("search"))
                if q:
                    qs.append({"question": str(q).strip(), "raw": item,
                               "source_key": key})
    return qs


def policy_answer(question, ctx):
    """保存期限/密级类管理问题：引用带 {value,source,evidence} 的抽取值。"""
    policy = (ctx or {}).get("policy") or {}
    out = []
    pats = (("retention", ("保存期限", "留存期", "retention", "保存多久",
                           "存多久")),
            ("access_level", ("密级", "权限", "access", "保密")))
    for field, keys in pats:
        if not any(k in question for k in keys):
            continue
        p = policy.get(field) or {}
        val = p.get("value")
        if val and val != "unspecified":
            out.append("%s：%s（来源 %s，依据：%s）" % (
                field, val, p.get("source") or "unknown",
                (p.get("evidence") or "")[:80]))
        else:
            out.append("%s：未在 case.json/task.md 中声明"
                       "（unspecified，不编造）" % field)
    return "；".join(out) if out else None


def answer_one(db, library_root, q_text, ctx, limit=10):
    t0 = time.time()
    entry = {"question": q_text, "answer": None, "hits": [],
             "evidence_complete": False, "no_evidence_reason": None,
             "answered": False}
    if not os.path.isfile(db):
        entry["no_evidence_reason"] = "index db missing: %s" % db
        entry["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
        return entry
    def _run(qs):
        return query_index.query(db, qs, limit=limit,
                                 library_root=library_root)
    try:
        r = _run(q_text)
        query_used = q_text
        if not r.get("hits"):
            # 退化重查：自然语言问题逐步收缩为可命中子串
            for cand in fallback_queries(q_text):
                r2 = _run(cand)
                if r2.get("hits"):
                    r = r2
                    query_used = cand
                    break
    except Exception as e:
        entry["no_evidence_reason"] = "query_error: %s: %s" % (
            type(e).__name__, e)
        entry["elapsed_ms"] = round((time.time() - t0) * 1000, 1)
        return entry
    entry["mode"] = r.get("mode")
    if query_used != q_text:
        entry["query_used"] = query_used
    hits = []
    for h in r.get("hits", []):
        ev = h.get("evidence") or []
        if not ev:
            continue
        for e in ev[:2]:
            hits.append({"path": h.get("path"), "line": e.get("line"),
                         "snippet": (e.get("text") or "")[:SNIPPET_LEN]})
            if len(hits) >= MAX_SNIPPETS:
                break
        if len(hits) >= MAX_SNIPPETS:
            break
    entry["hits"] = hits
    elapsed = round((time.time() - t0) * 1000, 1)
    entry["elapsed_ms"] = elapsed
    entry["_hit_files"] = r.get("hit_count", 0)

    if hits:
        # 抽取式答案：证据行 + 出处（文件:行号），不添油加醋
        parts = ["%s（%s:%s）" % (h["snippet"].strip(), h["path"], h["line"])
                 for h in hits[:3]]
        entry["answer"] = "；".join(parts)
        entry["evidence_complete"] = True
        entry["answered"] = True
    else:
        pol = policy_answer(q_text, ctx)
        if pol:
            entry["answer"] = pol
            entry["answered"] = True
            entry["evidence_complete"] = "unspecified" not in pol
            if not entry["evidence_complete"]:
                entry["no_evidence_reason"] = \
                    "管理字段未在输入中声明，已如实标注 unspecified"
        else:
            entry["answer"] = None
            entry["no_evidence_reason"] = \
                "索引无命中且非管理性字段问题；无证据不编造答案"
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--db", default=None)
    ap.add_argument("--limit", type=int, default=10)
    args = ap.parse_args()
    input_dir = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)
    os.makedirs(output_dir, exist_ok=True)

    case = lib.json_load(os.path.join(input_dir, "case.json"),
                         default={}) or {}
    case_id = str(case.get("case_id", "unknown_case"))
    ctx = lib.json_load(os.path.join(output_dir, "context_snapshot.json"),
                        default={}) or {}
    db = args.db or os.path.join(output_dir, "library", "index",
                                 "library_index.db")
    library_root = os.path.join(output_dir, "library")
    qlog_path = os.path.join(output_dir, "query_log.jsonl")

    results = []
    for item in collect_questions(case):
        entry = answer_one(db, library_root, item["question"], ctx,
                           limit=args.limit)
        entry["source_key"] = item["source_key"]
        hit_files = entry.pop("_hit_files", 0)
        results.append(entry)
        lib.jsonl_append(qlog_path, {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "query": item["question"],
            "query_used": entry.get("query_used", item["question"]),
            "source_key": item["source_key"],
            "mode": entry.get("mode"), "elapsed_ms": entry["elapsed_ms"],
            "hit_files": hit_files, "hit_snippets": len(entry["hits"]),
            "evidence_complete": entry["evidence_complete"]})

    n_ok = sum(1 for r in results if r["evidence_complete"])
    lib.json_dump({
        "case_id": case_id,
        "generated_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "question_count": len(results),
        "evidence_complete_count": n_ok,
        "results": results},
        os.path.join(output_dir, "search_results.json"))
    lib.log("answer_questions: %d questions, %d evidence-complete" %
            (len(results), n_ok))
    return 0


if __name__ == "__main__":
    sys.exit(main())
