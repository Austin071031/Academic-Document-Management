#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检索：CLI 查询索引库，输出带 文件+行号 证据的命中。

用法：
  python3 scripts/query_index.py --db <library_index.db> --q "关键词" [--limit N]

FTS5 模式：查询经 cjk_bigrams 切词后 AND 组装；无 FTS5 的退化模式：
LIKE 匹配 docs_plain。两种模式最终都在原文里定位命中行，行号 1 起。
输出 JSON 到 stdout。
"""
import argparse
import json
import os
import re
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

MAX_HIT_LINES = 20


def line_evidence(path, terms, max_lines=MAX_HIT_LINES):
    """在原文中定位含全部词元的行，返回 [{line, text}]。"""
    full = path
    text = lib.read_text(full)
    if text is None:
        return []
    hits = []
    low_terms = [t.lower() for t in terms if t]
    for i, line in enumerate(text.splitlines(), 1):
        low = line.lower()
        if all(t in low for t in low_terms):
            hits.append({"line": i, "text": line[:300]})
            if len(hits) >= max_lines:
                break
    return hits


def query(db_path, q, limit=10, library_root=None):
    q = (q or "").strip()
    if not q:
        return {"query": q, "hits": [], "note": "empty query"}
    con = sqlite3.connect(db_path)
    cur = con.cursor()
    mode = "like_fallback"
    try:
        row = cur.execute("SELECT v FROM meta WHERE k='mode'").fetchone()
        if row:
            mode = row[0]
    except sqlite3.Error:
        pass
    terms = [t for t in re.split(r"\s+", q) if t]
    matched_paths = []
    if mode == "fts5_bigram":
        toks = lib.cjk_bigrams(q)
        if toks:
            expr = " AND ".join('"%s"' % t.replace('"', '') for t in toks)
            try:
                rows = cur.execute(
                    "SELECT path FROM docs WHERE docs MATCH ? "
                    "ORDER BY rank LIMIT ?", (expr, limit * 4)).fetchall()
                matched_paths = [r[0] for r in rows]
            except sqlite3.Error as e:
                mode += " (match_error: %s)" % e
    else:
        like = "%" + q.replace("%", "\\%").replace("_", "\\_") + "%"
        try:
            rows = cur.execute(
                "SELECT path FROM docs_plain WHERE content LIKE ? ESCAPE "
                "'\\' LIMIT ?", (like, limit * 4)).fetchall()
            matched_paths = [r[0] for r in rows]
        except sqlite3.Error:
            pass
    hits = []
    if library_root is None:
        library_root = os.path.dirname(os.path.dirname(db_path))
    for rel in matched_paths:
        full = os.path.join(library_root, rel)
        ev = line_evidence(full, terms)
        if ev:
            hits.append({"path": rel, "evidence": ev})
        else:
            hits.append({"path": rel, "evidence": [],
                         "note": "命中文件但行定位失败（可能为二进制或无该行）"})
        if len(hits) >= limit:
            break
    con.close()
    return {"query": q, "mode": mode, "hit_count": len(hits), "hits": hits}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--q", required=True)
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--library-root", default=None)
    args = ap.parse_args()
    result = query(args.db, args.q, args.limit, args.library_root)
    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
