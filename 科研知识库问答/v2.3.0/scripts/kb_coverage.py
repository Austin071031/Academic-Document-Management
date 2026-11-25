#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_coverage.py -- 缺证判据的覆盖证明: 说"知识库没有"之前先证明"查过了"。

对每个问题生成 coverage_proof:
  - searched_queries: 实际用过的全部检索词(来自 hits.json + 补充查询)
  - docs_in_scope: 本次检索覆盖的 canonical 文档清单(路径+版本)
  - docs_excluded: 被排除的文档及原因(旧版本/重复副本/不可读/无文本层/OCR)
  - anchors_total / hits_considered: 索引规模与命中数
  - verdict_hint: sufficient_coverage | partial_coverage(存在不可读/未索引文档)

用法:
  python3 kb_coverage.py --work /app/work [--extra-queries q1:"词1 词2"]
输出: <work>/coverage_proof.json (撰写 questions_without_evidence 时整段引用)
"""
import argparse
import json
import os
import sys
import time


def load(p):
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    W = args.work

    hits = load(os.path.join(W, "hits.json"))
    rep = load(os.path.join(W, "extract_report.json"))
    vers = load(os.path.join(W, "versions.json"))
    idx_meta = load(os.path.join(W, "index_meta.json"))

    canonical = {d["canonical"] for d in vers.get("documents", [])}
    excluded = []
    for e in rep.get("files", []):
        p = e["path"]
        if p in canonical and e["status"] == "ok":
            continue
        reason = None
        if e["status"] != "ok":
            reason = "extraction:%s(%s)" % (e["status"], e.get("reason", ""))
        elif p not in canonical:
            reason = "非 canonical(旧版本或重复副本)"
        if reason:
            excluded.append({"path": p, "reason": reason})

    docs_in_scope = sorted(canonical)
    anchors_total = idx_meta.get("anchors")
    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "tool": "kb_coverage.py", "questions": {}}
    qs = hits.get("questions") or {}
    for qid, q in qs.items():
        hard_blockers = [x for x in excluded if x["reason"].startswith("extraction:")]
        verdict = "partial_coverage" if hard_blockers else "sufficient_coverage"
        out["questions"][qid] = {
            "query": q.get("query"),
            "searched_queries": q.get("terms") or [],
            "docs_in_scope": docs_in_scope,
            "anchors_total": anchors_total,
            "candidates_scored": q.get("total_candidates"),
            "hits_considered": len(q.get("hits") or []),
            "docs_excluded": excluded,
            "verdict_hint": verdict,
        }
    with open(os.path.join(W, "coverage_proof.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    sys.stdout.write("# 覆盖证明完成: %d questions, scope=%d canonical docs, excluded=%d\n"
                     % (len(qs), len(docs_in_scope), len(excluded)))


if __name__ == "__main__":
    main()
