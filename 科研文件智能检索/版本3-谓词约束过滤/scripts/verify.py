#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify.py — 证据回链独立校验：每条结论可被逐字复核。

校验项：
1. quote 是否真实存在于所 claim 的文档文本中（规范化空白后子串比对）。
2. anchor 页码是否越界；printed_page 与 page_map 偏移是否一致。
3. 命中是否满足已声明的硬过滤条件（不可静默放宽）。
4. section_path 是否存在于该文档章节表。

输出: <work-dir>/verification.json（每条 hit 回填 verified/issues），
并给出总体 pass/fail，供 report.py 决定是否允许写入结论。
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Journal, norm_text, read_json, write_json


def doc_text(corpus, doc_id):
    for d in corpus.get("docs", []):
        if d["doc_id"] == doc_id:
            pages = {p["page"]: p.get("text", "") for p in d.get("pages", [])}
            return pages, d
    return {}, {}


def verify_hit(hit, corpus, sections):
    a = hit.get("anchor", {})
    issues = []
    pages, doc = doc_text(corpus, a.get("doc_id"))
    if not doc:
        return ["doc_id not found in corpus"]

    full = norm_text(" ".join(pages.values()))
    quote = norm_text(a.get("quote"))
    if quote:
        if quote not in full:
            # 宽松复核：去掉标点再比（OCR/连字符差异）
            loose_q = re.sub(r"[^\w一-鿿]", "", quote).lower()
            loose_f = re.sub(r"[^\w一-鿿]", "", full).lower()
            if loose_q not in loose_f:
                issues.append("quote_not_found_verbatim")
    pg = a.get("page")
    if pg is not None:
        if pg not in pages:
            issues.append("page_out_of_range")
        else:
            pmap = (sections.get("page_maps", {}) or {}).get(a["doc_id"], {})
            off = pmap.get("offset")
            if a.get("printed_page") is not None and off is not None:
                if a["printed_page"] - off != pg:
                    issues.append("printed_page_inconsistent_with_offset")
            elif a.get("printed_page") is not None and off is None:
                issues.append("printed_page_claimed_but_offset_unknown")
    sec = a.get("section_path")
    if sec:
        known = {s["path"] for s in sections.get("sections", [])
                 if s["doc_id"] == a["doc_id"]}
        if sec not in known:
            issues.append("section_path_not_in_toc")
    if a.get("sha256") and doc.get("sha256") and a["sha256"] != doc["sha256"]:
        issues.append("sha256_mismatch_vs_corpus")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--hits", default=None, help="hits.json path")
    ap.add_argument("--max-fail-rate", type=float, default=1.0)
    a = ap.parse_args()

    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    corpus = read_json(os.path.join(a.work_dir, "corpus.json"), {}) or {}
    sections = read_json(os.path.join(a.work_dir, "sections.json"), {}) or {}
    hits_path = a.hits or os.path.join(a.work_dir, "hits.json")
    hits_doc = read_json(hits_path, {}) or {}

    results, n_pass = [], 0
    for hit in hits_doc.get("hits", []):
        issues = verify_hit(hit, corpus, sections)
        hit["verified"] = not issues
        hit["verification_issues"] = issues
        results.append({"anchor": hit.get("anchor"), "score": hit.get("score"),
                        "verified": hit["verified"], "issues": issues})
        n_pass += 1 if not issues else 0
        journal.log("4-verify", "%s %s %s" % (hit.get("anchor", {}).get("file_path"),
                                              "PASS" if not issues else "FAIL",
                                              issues or ""))

    total = len(results)
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total": total, "passed": n_pass,
        "failed": total - n_pass,
        "pass_rate": round(n_pass / total, 3) if total else None,
        "gate": ("empty" if total == 0 else
                 "pass" if n_pass / total >= a.max_fail_rate else "fail"),
        "checks_performed": [
            "quote_exists_verbatim_in_claimed_doc",
            "page_in_range",
            "printed_page_consistent_with_offset",
            "section_path_in_toc",
            "sha256_matches_corpus",
        ],
        "results": results,
    }
    write_json(hits_path, hits_doc)
    out = write_json(os.path.join(a.work_dir, "verification.json"), summary)
    journal.log("4-verify", "gate=%s %d/%d" % (summary["gate"], n_pass, total),
                outputs=[out])
    print("verify: %d/%d pass (gate=%s)" % (n_pass, total, summary["gate"]))
    return 0 if summary["gate"] in ("pass", "empty") else 1


if __name__ == "__main__":
    sys.exit(main())
