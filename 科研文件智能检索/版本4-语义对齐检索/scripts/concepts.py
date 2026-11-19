#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""concepts.py — 【版本4 旗舰】跨文件概念对齐与语义规范化层。

功能：
1. 加载对照表 aliases.txt（中英/同义/上下位），构建双向概念映射。
2. 从语料自动抽取缩写—全称对（"缩写 (全称)"、"全称（缩写）"），
   与人工词表合并为 concepts.json 供 retrieve.py --concepts 扩展查询。
3. 概念命中统计：每个概念在哪些文档/章节出现，形成跨文件概念索引
   concept_index.json，回答"这个概念在哪几个文件里出现过"。
4. 查询语言检测：中/英查询均可命中另一语言的文档（经别名映射）。

用法: python3 concepts.py --work-dir /app/work [--aliases aliases.txt]
输出: concepts.json, concept_index.json
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Journal, STOPWORDS, read_json, tokenize, write_json)
from retrieve import RE_ACRO, RE_ACRO2


def load_aliases(path):
    table = {}
    if not path or not os.path.exists(path):
        return table
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, rest = line.split("=", 1)
            key = key.strip()
            aliases = [x.strip() for x in rest.split("|") if x.strip()]
            table[key] = aliases
    return table


def build_concepts(table, acro):
    """概念映射: 概念词(中英) → 词项 token 集合（双向）。"""
    concepts = {}
    for key, aliases in table.items():
        group = [key] + aliases
        toks = set()
        for g in group:
            toks.update(t for t in tokenize(g.lower()) if t not in STOPWORDS)
        for g in group:
            concepts[g.lower()] = sorted(toks)
    for a, full in (acro or {}).items():
        toks = sorted(set(t for t in tokenize((full or "").lower())
                           if t not in STOPWORDS) | {a})
        concepts[a] = toks
        concepts[(full or "").lower()] = toks
    return concepts


def build_concept_index(concepts, corpus, sections):
    """概念 × 文档/段落 出现矩阵（取每个概念的代表 token 集合）。"""
    pars = sections.get("paragraphs", [])
    doc_by_id = {d["doc_id"]: d for d in corpus.get("docs", [])}
    sec_by_id = {s["section_id"]: s for s in sections.get("sections", [])}
    index = {}
    for cname, toks in concepts.items():
        if not toks:
            continue
        entries = []
        tset = set(toks)
        for p in pars:
            ptoks = set(tokenize(p["text"]))
            hit = tset & ptoks
            if not hit:
                continue
            doc = doc_by_id.get(p["doc_id"], {})
            sec = sec_by_id.get(p.get("section_id"), {})
            entries.append({
                "doc_id": p["doc_id"], "path": doc.get("path"),
                "section_path": p.get("section_path"),
                "page": p.get("page"), "printed_page": p.get("printed_page"),
                "matched_terms": sorted(hit),
                "first_sentence": p.get("first_sentence"),
            })
        if entries:
            index[cname] = {"doc_count": len({e["doc_id"] for e in entries}),
                            "occurrences": len(entries),
                            "entries": entries[:50]}
    return index


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--aliases", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "aliases.txt"))
    a = ap.parse_args()
    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    corpus = read_json(os.path.join(a.work_dir, "corpus.json"), {}) or {}
    sections = read_json(os.path.join(a.work_dir, "sections.json"), {}) or {}

    table = load_aliases(a.aliases)
    text_all = "\n".join(p.get("text", "") for d in corpus.get("docs", [])
                         for p in d.get("pages", []))
    acro = {}
    for m, full in RE_ACRO.findall(text_all):
        acro.setdefault(m.lower(), full.strip())
    for full, m in RE_ACRO2.findall(text_all):
        acro.setdefault(m.lower(), full.strip())

    concepts = build_concepts(table, acro)
    write_json(os.path.join(a.work_dir, "concepts.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "alias_pairs": len(table), "auto_acronyms": len(acro),
        "concepts": concepts})

    index = build_concept_index(concepts, corpus, sections)
    write_json(os.path.join(a.work_dir, "concept_index.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "concepts_indexed": len(index),
        "index": index})
    journal.log("2.7-concepts", "alias=%d acronyms=%d concepts=%d"
                % (len(table), len(acro), len(index)),
                outputs=[os.path.join(a.work_dir, "concepts.json"),
                         os.path.join(a.work_dir, "concept_index.json")])
    print("concepts=%d indexed=%d" % (len(concepts), len(index)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
