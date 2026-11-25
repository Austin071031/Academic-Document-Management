#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step4 search：倒排索引检索，回答 case.json 中的 keyword searches。

对 <output>/library/tree/ 下的文本内容建立倒排索引（纯 stdlib）：
  term → [(path, line_no)]，term = 拉丁词（小写）+ CJK 单字 + CJK 二元组。
查询时先取候选行（倒排 posting 并集），再按子串/词元覆盖度排序。
每条命中带 文件 + 行号 + 片段 的证据定位。

产物：<output>/library/search_results.json
"""
import argparse
import json
import os
import re
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cas_common import is_probably_text, read_json, read_text, write_json

MAX_FILE_BYTES = 524288
MAX_HITS_PER_QUERY = 50
CJK_RE = re.compile(r"[一-鿿]+")
WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def tokenize(text):
    """拉丁词（小写）+ CJK 单字 + CJK 二元组。"""
    out = [w.lower() for w in WORD_RE.findall(text)]
    for seq in CJK_RE.findall(text):
        out.extend(seq)
        out.extend(seq[i:i + 2] for i in range(len(seq) - 1))
    return out


def build_inverted_index(tree_root):
    """返回 (index: term→[(path,lineno)], lines_cache: {path: [lines]})。"""
    index = defaultdict(list)
    lines_cache = {}
    for root, dirs, files in os.walk(tree_root):
        dirs.sort()
        files.sort()
        for name in files:
            full = os.path.join(root, name)
            if not is_probably_text(full):
                continue
            rel = os.path.relpath(full, tree_root).replace(os.sep, "/")
            try:
                lines = read_text(full, MAX_FILE_BYTES).splitlines()
            except OSError:
                continue
            lines_cache[rel] = lines
            for ln, line in enumerate(lines, 1):
                for tok in set(tokenize(line)):
                    index[tok].append((rel, ln))
    return index, lines_cache


def answer_query(query, index, lines_cache):
    """倒排候选 + 子串验证 + 词元覆盖排序。返回命中列表。"""
    qtokens = set(tokenize(query))
    candidates = set()
    for tok in qtokens:
        for rel, ln in index.get(tok, []):
            candidates.add((rel, ln))
    if not candidates:  # 查询词元不在索引里 → 全量子串兜底
        for rel, lines in lines_cache.items():
            for ln, line in enumerate(lines, 1):
                if query in line:
                    candidates.add((rel, ln))
    ql = query.lower()
    scored = []
    for rel, ln in candidates:
        line = lines_cache.get(rel, [""])[ln - 1] if ln - 1 < len(
            lines_cache.get(rel, [])) else ""
        ll = line.lower()
        exact = ql in ll or query in line
        cover = sum(1 for t in qtokens if t in ll)
        if exact or cover >= 1:
            scored.append((0 if exact else 1, -cover, rel, ln,
                           line.strip()[:240]))
    scored.sort()
    hits = [{"path": "tree/" + rel, "line": ln, "snippet": snip,
             "match": "exact" if rank == 0 else "token_coverage"}
            for rank, _, rel, ln, snip in scored[:MAX_HITS_PER_QUERY]]
    return hits


def extract_queries(case):
    """从 case.json 提取 searches / questions，兼容 str 或 dict 条目。"""
    searches, questions = [], []

    def pick(item):
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            for k in ("query", "keyword", "term", "q", "search", "text",
                      "question"):
                if isinstance(item.get(k), str):
                    return item[k]
        return None

    for item in case.get("searches") or []:
        q = pick(item)
        if q:
            searches.append(q)
    for item in case.get("questions") or []:
        q = pick(item)
        if q:
            questions.append(q)
    return searches, questions


def run_search(input_dir, work_dir, output_dir):
    library = os.path.join(output_dir, "library")
    tree_root = os.path.join(library, "tree")
    case = read_json(os.path.join(input_dir, "case.json")) or {}
    searches, questions = extract_queries(case)

    index, lines_cache = (defaultdict(list), {})
    if os.path.isdir(tree_root):
        index, lines_cache = build_inverted_index(tree_root)

    search_out = []
    for q in searches:
        hits = answer_query(q, index, lines_cache)
        search_out.append({"query": q, "hit_count": len(hits), "hits": hits})

    question_out = []
    for q in questions:
        hits = answer_query(q, index, lines_cache)
        question_out.append({
            "question": q,
            "evidence": hits[:5],
            "answer_note": "以下为资料库中定位到的相关证据片段（文件+行号）；"
                           "结论需由代理据片段归纳。"
            if hits else "资料库中未检索到与该问题相关的文本证据。",
        })

    result = {
        "searches": search_out,
        "questions": question_out,
        "stats": {"queries": len(searches), "questions": len(questions),
                  "files_indexed": len(lines_cache),
                  "total_hits": sum(s["hit_count"] for s in search_out)},
    }
    write_json(os.path.join(library, "search_results.json"), result)
    return result["stats"]


def main():
    ap = argparse.ArgumentParser(description="倒排索引检索")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    s = run_search(a.input, a.work, a.output)
    print("search ok: queries=%(queries)d questions=%(questions)d "
          "hits=%(total_hits)d" % s)


if __name__ == "__main__":
    main()
