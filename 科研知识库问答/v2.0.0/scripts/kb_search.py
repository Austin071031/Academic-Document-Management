#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_search.py -- 对段落索引做关键词检索, 支持中英文混合查询与元数据过滤。

检索特性:
  - 查询切词: 拉丁词(小写) + CJK 二元组 + 单字兜底, 去常见停用词
  - 评分: 词频加和 / sqrt(段落长度) 归一 + 短语邻接奖励
  - 过滤: --doc <doc_base> / --path 子串 / --file 精确路径 / --type 版本范围(latest|all)

用法:
  单查询:
    python3 kb_search.py --work /app/work --query "催化剂的转化率" [--topk 8]
  批量(案例问题清单):
    python3 kb_search.py --work /app/work --questions /app/work/questions.json [--topk 8]
  questions.json: [{"id":"q1","question":"...","filters":{"path":"paper_v2.pdf"}}]

输出:
  单查询 -> 命中段落(锚点 + 分数 + 全文)打到 stdout, 同时写 <work>/hits_<slug>.json
  批量   -> <work>/hits.json  {question_id: [hits...]}
"""
import argparse
import json
import math
import os
import re
import sys
import time

LATIN = re.compile(r"[a-zA-Z][a-zA-Z0-9_\-]*")
CJK = re.compile(r"[\u4e00-\u9fff]")
STOP = set("的 了 和 是 在 对 与 及 或 等 为 于 中 有 无 不 我 你 他 她 它 这 那 你 请 问 什么 如何 哪些 "
           "the a an of to in and or is are was were be been for on with by at from as it its this that "
           "what which how who whom whose when where why".split())


def tokenize(q):
    toks = []
    for m in LATIN.finditer(q):
        w = m.group(0).lower()
        if w not in STOP and len(w) > 1:
            toks.append(w)
    # CJK 连续段 -> 二元组 + 单字
    buf = []
    for ch in q:
        if CJK.match(ch):
            buf.append(ch)
        else:
            if buf:
                toks.extend(cjk_tokens(buf))
                buf = []
    if buf:
        toks.extend(cjk_tokens(buf))
    seen, out = set(), []
    for t in toks:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def cjk_tokens(buf):
    out = []
    if len(buf) == 1:
        return [buf[0]] if buf[0] not in STOP else []
    for i in range(len(buf) - 1):
        out.append(buf[i] + buf[i + 1])
    for i in range(0, len(buf), 2):
        if buf[i] not in STOP:
            out.append(buf[i])
    return out


def load_index(work):
    rows = []
    p = os.path.join(work, "index.jsonl")
    if not os.path.isfile(p):
        return rows
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def score_para(text, terms):
    tl = text.lower()
    s = 0.0
    hit_terms = []
    for t in terms:
        c = tl.count(t)
        if c:
            s += c
            hit_terms.append(t)
    if not hit_terms:
        return 0.0, []
    s = s / math.sqrt(max(len(text), 1) / 120.0 + 1)
    # 短语奖励: 若全部二元组命中且彼此邻近(简单近似: 命中词数 >= 3 且覆盖 >=60%)
    if len(hit_terms) >= 3 and len(hit_terms) >= 0.6 * max(len(terms), 1):
        s *= 1.5
    return s, hit_terms


def search(rows, query, topk, filters=None):
    terms = tokenize(query)
    filters = filters or {}
    cands = []
    for r in rows:
        if filters.get("doc") and r.get("doc_base") != filters["doc"]:
            continue
        if filters.get("path") and filters["path"] not in r.get("path", ""):
            continue
        if filters.get("file") and r.get("path") != filters["file"]:
            continue
        s, hits = score_para(r["text"], terms)
        if s > 0:
            cands.append((s, hits, r))
    cands.sort(key=lambda x: -x[0])
    out = []
    for s, hits, r in cands[:topk]:
        d = dict(r)
        d["score"] = round(s, 3)
        d["matched_terms"] = hits
        out.append(d)
    return {"query": query, "terms": terms, "hits": out,
            "total_candidates": len(cands)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--query", default=None)
    ap.add_argument("--questions", default=None)
    ap.add_argument("--topk", type=int, default=8)
    ap.add_argument("--doc", default=None)
    ap.add_argument("--path", default=None)
    ap.add_argument("--file", default=None)
    args = ap.parse_args()

    rows = load_index(args.work)
    if not rows:
        sys.stderr.write("ERROR: index.jsonl 为空, 先运行 kb_index.py\n")
        sys.exit(2)

    base_filters = {k: v for k, v in
                    (("doc", args.doc), ("path", args.path), ("file", args.file)) if v}

    if args.questions:
        qs = json.load(open(args.questions, encoding="utf-8"))
        result = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                  "tool": "kb_search.py", "questions": {}}
        for q in qs:
            fl = dict(base_filters)
            fl.update(q.get("filters") or {})
            r = search(rows, q.get("question", ""), args.topk, fl)
            result["questions"][q.get("id", q.get("question", "?"))] = r
        out = os.path.join(args.work, "hits.json")
        with open(out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=1)
        sys.stdout.write("# 批量检索完成: %d questions -> %s\n" % (len(qs), out))
        return

    if not args.query:
        sys.stderr.write("ERROR: 需要 --query 或 --questions\n")
        sys.exit(2)
    r = search(rows, args.query, args.topk, base_filters)
    slug = re.sub(r"[^a-z0-9]+", "_", args.query.lower())[:40] or "q"
    out = os.path.join(args.work, "hits_%s.json" % slug)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(r, f, ensure_ascii=False, indent=1)
    sys.stdout.write("# query=%s terms=%s candidates=%d -> %s\n"
                     % (args.query, r["terms"], r["total_candidates"], out))
    for h in r["hits"]:
        loc = "%s p%s ¶%s" % (h["path"], h.get("page"), h.get("para_index"))
        sys.stdout.write("## [%s] score=%.2f %s anchor=%s\n%s\n\n"
                         % (h["path"], h["score"], loc, h["anchor_id"], h["text"]))


if __name__ == "__main__":
    main()
