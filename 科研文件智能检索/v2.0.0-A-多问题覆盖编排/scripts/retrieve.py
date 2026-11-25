#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""retrieve.py — 段落级检索（概念扩展 + BM25 打分 + 硬过滤）。

- 词项: 拉丁词 + CJK bigram（common.tokenize）。
- 查询扩展: --concepts 传入概念映射 {term: [alias...]}（版本4旗艦），
  缩写自动表 acronym_map.json 双向扩展。
- 硬过滤: --filter JSON，字段 year/doc_type/path_glob/exclude_sha256/version。
  不满足的文档直接排除并在 audit 中记录；绝不静默放宽。
- 输出每个命中段落的证据锚点候选（含 best-quote 窗口）。

用法: python3 retrieve.py --work-dir /app/work --query "..." [--topk 10]
       [--filter '{"year":[2020,2025]}'] [--concepts concepts.json]
输出: <work-dir>/hits.json
"""
import argparse
import json
import math
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (STOPWORDS, Journal, make_anchor, norm_text, read_json,
                    tokenize, write_json)

RE_ACRO = re.compile(r"\b([A-Z][A-Za-z0-9]{1,14})\s*[（(]([^（）()]{2,60})[)）]")
RE_ACRO2 = re.compile(r"([一-鿿][一-鿿A-Za-z0-9]{1,19})\s*[（(]([A-Z][A-Za-z0-9]{1,14})[)）]")


def build_acronym_map(corpus):
    m = {}
    for doc in corpus.get("docs", []):
        text = "\n".join(p.get("text", "") for p in doc.get("pages", []))
        for a, full in RE_ACRO.findall(text):
            m.setdefault(a.lower(), full.strip())
        for full, a in RE_ACRO2.findall(text):
            m.setdefault(a.lower(), full.strip())
    return m


def build_docmeta(corpus):
    meta = {}
    for doc in corpus.get("docs", []):
        text_head = ""
        for p in doc.get("pages", [])[:2]:
            text_head += p.get("text", "")[:2000]
        years = sorted(set(int(y) for y in
                           re.findall(r"(?<!\d)(19\d{2}|20\d{2})(?!\d)", text_head)))
        meta[doc["doc_id"]] = {
            "years_in_text": years,
            "version_tags": doc.get("version_tags") or [],
        }
    return meta


def load_concept_expansions(path):
    """支持两种格式: {term: [alias...]} 或 concepts.py 输出 {concepts: {term: [token...]}}。"""
    if not path:
        return {}
    data = read_json(path, {}) or {}
    if "concepts" in data and isinstance(data["concepts"], dict):
        data = data["concepts"]
    out = {}
    for term, aliases in data.items():
        if not isinstance(aliases, (list, tuple)):
            continue
        term = str(term).lower()
        strs = [str(x).lower() for x in aliases if isinstance(x, str)]
        if strs and all(len(x) <= 4 for x in strs):
            # 已 token 化的词项集合（concepts.py 输出）
            out[term] = set(strs)
        else:
            keys = [term] + strs
            toks = set()
            for k in keys:
                toks.update(t for t in tokenize(k) if t not in STOPWORDS)
            for k in keys:
                out[k] = toks
    return out


def expand_query_terms(query, acro, concepts):
    raw = [t for t in tokenize(query) if t not in STOPWORDS]
    terms = set(raw)
    qlow = query.lower()
    # 缩写双向扩展: 查询含缩写→展开全称词；含全称→缩写词
    for a, full in acro.items():
        if re.search(r"(?<![a-z0-9])%s(?![a-z0-9])" % re.escape(a), qlow):
            terms.update(t for t in tokenize(full) if t not in STOPWORDS)
        elif any(t in qlow for t in tokenize(full)):
            terms.update(t for t in tokenize(a) if t not in STOPWORDS)
    # 概念映射扩展
    for key, toks in (concepts or {}).items():
        if key in qlow:
            terms.update(toks)
    return terms, raw


def apply_filter(doc, docmeta, flt, inv_by_doc):
    """返回 (pass, [reasons])。硬过滤：不通过即排除，理由入审计。"""
    reasons = []
    inv = inv_by_doc.get(doc["doc_id"], {})
    years = flt.get("year")
    if years:
        lo, hi = (years if isinstance(years, list) else [years, years])[:2]
        cand = (docmeta.get(doc["doc_id"], {}).get("years_in_text")
                or [int(t) for t in inv.get("version_tags", [])
                    if str(t).isdigit() and len(str(t)) == 4]
                or [])
        if not cand or not (lo <= max(cand) and min(cand) <= hi):
            reasons.append("year filter [%s,%s] not matched (doc years=%s)"
                           % (lo, hi, cand))
    dtypes = flt.get("doc_type")
    if dtypes and doc.get("category") not in dtypes:
        reasons.append("doc_type filter %s excludes category %s"
                       % (dtypes, doc.get("category")))
    glob = flt.get("path_glob")
    if glob and not re.search(glob.replace("*", ".*"), doc.get("path", "")):
        reasons.append("path_glob %s not matched" % glob)
    exclude = flt.get("exclude_sha256") or []
    if doc.get("sha256") in exclude:
        reasons.append("sha256 excluded (duplicate/old version)")
    return (not reasons), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--query", required=True)
    ap.add_argument("--topk", type=int, default=10)
    ap.add_argument("--filter", default=None, help="JSON string or file path")
    ap.add_argument("--concepts", default=None)
    ap.add_argument("--hits-out", default=None, help="默认 <work-dir>/hits.json")
    a = ap.parse_args()

    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    corpus = read_json(os.path.join(a.work_dir, "corpus.json"), {}) or {}
    sections = read_json(os.path.join(a.work_dir, "sections.json"), {}) or {}
    acro = build_acronym_map(corpus)
    write_json(os.path.join(a.work_dir, "acronym_map.json"), acro)
    docmeta = build_docmeta(corpus)

    flt = {}
    if a.filter:
        raw = a.filter
        if os.path.exists(raw):
            raw = open(raw, encoding="utf-8").read()
        flt = json.loads(raw)
    concepts = load_concept_expansions(a.concepts)

    terms, raw_terms = expand_query_terms(a.query, acro, concepts)
    journal.log("3-retrieve", "query=%r terms=%s filter=%s"
                % (a.query, sorted(terms), flt))

    inv = read_json(os.path.join(a.work_dir, "inventory.json"), {}) or {}
    inv_by_doc = {}
    for d in corpus.get("docs", []):
        for f in inv.get("files", []):
            if f.get("path") == d.get("path"):
                inv_by_doc[d["doc_id"]] = f

    pars = sections.get("paragraphs", [])
    sec_by_id = {s["section_id"]: s for s in sections.get("sections", [])}
    doc_by_id = {d["doc_id"]: d for d in corpus.get("docs", [])}

    # 硬过滤审计：每个文档一条决定记录，绝不静默排除
    audit, kept_docs = {}, set()
    for doc in corpus.get("docs", []):
        ok, reasons = apply_filter(doc, docmeta, flt, inv_by_doc)
        if ok:
            kept_docs.add(doc["doc_id"])
        audit[doc["doc_id"]] = {"path": doc.get("path"),
                                "decision": "kept" if ok else "excluded",
                                "reasons": reasons}

    # 建立段落索引与 IDF
    N = max(1, len(pars))
    df = {}
    tok_of = {}
    for p in pars:
        if p["doc_id"] not in kept_docs:
            continue
        toks = set(t for t in tokenize(p["text"]) if t not in STOPWORDS)
        tok_of[p["para_id"]] = toks
        for t in toks:
            df[t] = df.get(t, 0) + 1

    hits = []
    for p in pars:
        toks = tok_of.get(p["para_id"])
        if not toks:
            continue
        score, matched = 0.0, set()
        for t in terms:
            if t in toks:
                idf = math.log(1 + N / (1 + df.get(t, 0)))
                tf = 1.0 + math.log(1 + p["text"].lower().count(t.lower()))
                score += tf * idf
                matched.add(t)
        if score <= 0:
            continue
        doc = doc_by_id[p["doc_id"]]
        sec = sec_by_id.get(p.get("section_id")) or {}
        quote = best_quote_window(p["text"], terms)
        hits.append({
            "score": round(score, 4),
            "matched_terms": sorted(matched),
            "anchor": make_anchor(doc, para=p, section=sec, quote=quote),
        })

    hits.sort(key=lambda h: -h["score"])
    hits = hits[:a.topk]
    for h in hits:
        h["verified"] = None  # 待 verify.py 回填

    out = write_json(a.hits_out or os.path.join(a.work_dir, "hits.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "query": a.query,
        "query_terms": sorted(terms),
        "filter": flt,
        "filter_audit": audit,
        "acronyms_used": {k: v for k, v in acro.items()
                          if k in str(sorted(terms)).lower()},
        "hits": hits,
        "stats": {"candidates": len(pars), "kept_docs": len(kept_docs),
                  "hits": len(hits)},
    })
    journal.log("3-retrieve", "%d hits / %d paragraphs" % (len(hits), len(pars)),
                outputs=[out])
    print("hits=%d kept_docs=%d" % (len(hits), len(kept_docs)))
    return 0


def best_quote_window(text, terms, width=220):
    """取覆盖最多查询词项的句子窗口作为引用片段。"""
    sents = re.split(r"(?<=[。！？.!?])\s+", text.strip())
    if not sents:
        return norm_text(text)[:width]
    best, best_n = None, -1
    for i, s in enumerate(sents):
        low = s.lower()
        n = sum(1 for t in terms if t.lower() in low)
        if n > best_n:
            best, best_n = s, n
    if best_n <= 0:
        best = sents[0]
    if len(best) > width:
        # 截取含最多词项的 width 窗口
        low = text.lower()
        pos = min([low.find(t.lower()) for t in terms if t.lower() in low]
                  or [0])
        lo = max(0, pos - width // 3)
        best = text[lo:lo + width]
    return norm_text(best)


if __name__ == "__main__":
    sys.exit(main())
