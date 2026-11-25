#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
qa.py — 轻量检索问答组件（版本2 新增）。

能力：
  1. 对 <output>/library/ 下的文本文件建倒排索引：
     term -> [(path, line, snippet)]；ASCII 词按整词，中文按 bigram 兜底。
  2. 回答 <input>/case.json 中的 searches / questions / queries：
     每条命中给出 文件路径+行号+原文片段 的证据定位；
     无命中诚实写 status=no_evidence 并说明缺什么。
  3. 输出 <output>/search_results.json；索引持久化到 <work>/search_index.json。

CLI：
  python3 scripts/qa.py --input /input --work /app/work --output /app/output
  python3 scripts/qa.py --work /app/work --output /app/output --index-only
  python3 scripts/qa.py --work /app/work --output /app/output --query "关键词"

仅用 Python 标准库。单文件失败只记录、不中断。
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from datetime import datetime, timezone

MAX_INDEX_FILE = 5 * 1024 * 1024   # 单文件 >5MB 不建索引（仍登记 skipped）
MAX_LINE = 4000                    # 超长行截断建索引
SNIPPET_LEN = 160                  # 命中片段长度
MAX_HITS_PER_QUERY = 50
MAX_POSTINGS_PER_TERM = 500
ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")
TEXT_EXTS = {
    ".txt", ".md", ".csv", ".tsv", ".json", ".jsonl", ".log", ".tex",
    ".py", ".sh", ".r", ".c", ".cpp", ".h", ".java", ".js", ".sql",
    ".xml", ".yaml", ".yml", ".ini", ".cfg", ".bib", ".rtf", ".html",
    ".htm", ".dat", ".ndjson", ".srt",
}
TOKEN_RE = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")
CASE_SEARCH_KEYS = ("searches", "questions", "queries")


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_print(*args):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    try:
        print(*args)
    except Exception as exc:
        print("[print-error]", exc)


def read_text_tolerant(path):
    for enc in ENCODINGS:
        try:
            with open(path, "r", encoding=enc, errors="strict") as fh:
                return fh.read()
        except Exception:
            continue
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return None


def tokens_of(text):
    """ASCII 词整词入索引；CJK 连续段按 bigram 兜底（单字保留单字）。"""
    toks = []
    for m in TOKEN_RE.finditer(unicodedata.normalize("NFC", text).lower()):
        t = m.group(0)
        if re.fullmatch(r"[a-z0-9_]+", t):
            toks.append(t)
        elif len(t) == 1:
            toks.append(t)
        else:
            toks.extend(t[i:i + 2] for i in range(len(t) - 1))
    return toks


def build_index(lib_root):
    """返回 (index, lines_by_path, stats)。lines_by_path 供原文片段定位。"""
    index = {}
    lines_by_path = {}
    stats = {"indexed_files": 0, "indexed_lines": 0, "terms": 0,
             "skipped": [], "library_root": lib_root}
    if not os.path.isdir(lib_root):
        stats["skipped"].append({"path": lib_root, "reason": "library/ 不存在"})
        return index, lines_by_path, stats
    for root, _dirs, files in os.walk(lib_root):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, lib_root).replace(os.sep, "/")
            try:
                if os.path.islink(fpath):
                    stats["skipped"].append({"path": rel, "reason": "symbolic link"})
                    continue
                size = os.path.getsize(fpath)
                if size > MAX_INDEX_FILE:
                    stats["skipped"].append({"path": rel, "reason": "size>%d bytes" % MAX_INDEX_FILE})
                    continue
                ext = os.path.splitext(fname.lower())[1]
                if ext and ext not in TEXT_EXTS:
                    stats["skipped"].append({"path": rel, "reason": "non-text extension %s" % ext})
                    continue
                text = read_text_tolerant(fpath)
                if text is None:
                    stats["skipped"].append({"path": rel, "reason": "undecodable"})
                    continue
                lines = text.splitlines()
                lines_by_path[rel] = [l[:MAX_LINE] for l in lines]
                # 路径也入索引（line=0 表示"文件名命中"而非内容命中）
                for term in set(tokens_of(rel.replace("/", " ").replace(".", " "))):
                    posting = index.setdefault(term, [])
                    if len(posting) < MAX_POSTINGS_PER_TERM:
                        posting.append([rel, 0, "(文件名) " + rel])
                for lineno, line in enumerate(lines_by_path[rel], 1):
                    snippet = line.strip()[:SNIPPET_LEN]
                    for term in set(tokens_of(line)):
                        posting = index.setdefault(term, [])
                        if len(posting) < MAX_POSTINGS_PER_TERM:
                            posting.append([rel, lineno, snippet])
                    stats["indexed_lines"] += 1
                stats["indexed_files"] += 1
            except Exception as exc:
                stats["skipped"].append({"path": rel, "reason": "%s: %s" % (type(exc).__name__, exc)})
    stats["terms"] = len(index)
    return index, lines_by_path, stats


def make_snippet(line, query=None):
    s = line.strip()
    if len(s) <= SNIPPET_LEN:
        return s
    if query:
        pos = s.lower().find(query.lower())
        if pos >= 0:
            start = max(0, pos - SNIPPET_LEN // 3)
            return ("…" if start else "") + s[start:start + SNIPPET_LEN]
    return s[:SNIPPET_LEN] + "…"


def search_query(index, lines_by_path, query):
    """先精确子串匹配（大小写不敏感、NFC），无命中再按 term 集合匹配兜底。"""
    query_nfc = unicodedata.normalize("NFC", str(query)).strip()
    hits = []
    if query_nfc:
        qlow = query_nfc.lower()
        for rel in sorted(lines_by_path):
            if qlow in unicodedata.normalize("NFC", rel).lower():
                hits.append({"path": rel, "line": 0,
                             "snippet": "(文件名) " + rel,
                             "match": "filename"})
                continue
            for lineno, line in enumerate(lines_by_path[rel], 1):
                if qlow in unicodedata.normalize("NFC", line).lower():
                    hits.append({"path": rel, "line": lineno,
                                 "snippet": make_snippet(line, query_nfc),
                                 "match": "substring"})
                    if len(hits) >= MAX_HITS_PER_QUERY:
                        break
            if len(hits) >= MAX_HITS_PER_QUERY:
                break
    if not hits:
        qterms = sorted(set(tokens_of(query_nfc)))
        if qterms:
            need = len(qterms) if len(qterms) <= 4 else max(1, int(len(qterms) * 0.6 + 0.999))
            scored = {}
            for term in qterms:
                for rel, lineno, _snip in index.get(term, []):
                    key = (rel, lineno)
                    scored.setdefault(key, set()).add(term)
            ranked = sorted(((-len(terms), rel, lineno) for (rel, lineno), terms in scored.items()
                             if len(terms) >= need))
            for _neg, rel, lineno in ranked[:MAX_HITS_PER_QUERY]:
                if lineno == 0:
                    snippet = "(文件名) " + rel
                else:
                    snippet = make_snippet(lines_by_path[rel][lineno - 1])
                hits.append({"path": rel, "line": lineno,
                             "snippet": snippet,
                             "match": "terms(%d/%d)" % (len(scored[(rel, lineno)]), len(qterms))})
    return hits


def answer_one(query, kind, hits):
    files = sorted({h["path"] for h in hits})
    if hits:
        locs = ", ".join("%s:%d" % (h["path"], h["line"]) for h in hits[:10])
        answer = "命中 %d 处（%d 个文件）：%s%s" % (
            len(hits), len(files), locs, " 等" if len(hits) > 10 else "")
        return {"query": query, "type": kind, "status": "answered",
                "answer": answer, "hit_count": len(hits), "files": files, "hits": hits}
    return {"query": query, "type": kind, "status": "no_evidence",
            "answer": None, "hit_count": 0, "files": [], "hits": [],
            "missing": ("library/ 文本索引中未找到与 %r 相关的任何行；"
                        "可能原因：目标文件未入库（不可读/损坏/非文本格式如 pdf/docx 未解析）、"
                        "或关键词与实际措辞不一致。已如实登记，未做任何猜测。" % query)}


def collect_queries(case):
    """从 case.json 收集 searches / questions / queries，兼容 str 或 dict 条目。"""
    out = []
    for key in CASE_SEARCH_KEYS:
        val = case.get(key)
        if not val:
            continue
        if isinstance(val, str):
            val = [val]
        for item in val:
            if isinstance(item, str) and item.strip():
                out.append((item.strip(), "question" if key == "questions" else "search"))
            elif isinstance(item, dict):
                q = item.get("query") or item.get("q") or item.get("keyword") \
                    or item.get("question") or item.get("text") or item.get("term")
                if q and str(q).strip():
                    out.append((str(q).strip(), "question" if key == "questions" else "search"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description="轻量检索问答（倒排索引 + 行号证据）")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--index-only", action="store_true", help="只重建索引，不回答问题")
    ap.add_argument("--query", default=None, help="临时单条查询")
    args = ap.parse_args(argv)

    lib_root = os.path.join(os.path.abspath(args.output), "library")
    os.makedirs(os.path.abspath(args.work), exist_ok=True)
    os.makedirs(os.path.abspath(args.output), exist_ok=True)
    index, lines_by_path, stats = build_index(lib_root)
    stats["built_at"] = utcnow()

    # 索引持久化（幂等：整本重建）
    index_path = os.path.join(os.path.abspath(args.work), "search_index.json")
    with open(index_path, "w", encoding="utf-8") as fh:
        json.dump({"built_at": stats["built_at"], "stats": stats, "index": index},
                  fh, ensure_ascii=False)
    safe_print("[qa] index: files=%d lines=%d terms=%d skipped=%d -> %s"
               % (stats["indexed_files"], stats["indexed_lines"], stats["terms"],
                  len(stats["skipped"]), index_path))

    if args.index_only:
        return 0

    queries = []
    if args.query:
        queries.append((args.query, "search"))
    case_path = os.path.join(os.path.abspath(args.input), "case.json")
    if os.path.exists(case_path):
        try:
            case = json.load(open(case_path, encoding="utf-8"))
            queries.extend(collect_queries(case))
        except Exception as exc:
            safe_print("[qa] case.json unreadable: %s" % exc)
    # 去重保持顺序
    seen = set()
    uniq = []
    for q, k in queries:
        if q not in seen:
            seen.add(q)
            uniq.append((q, k))

    results = [answer_one(q, k, search_query(index, lines_by_path, q)) for q, k in uniq]
    doc = {
        "generated_at": utcnow(),
        "generator": "qa.py (inverted index; CJK bigram fallback; line-number evidence)",
        "index_stats": stats,
        "total_queries": len(results),
        "answered": sum(1 for r in results if r["status"] == "answered"),
        "no_evidence": sum(1 for r in results if r["status"] == "no_evidence"),
        "results": results,
    }
    out_path = os.path.join(os.path.abspath(args.output), "search_results.json")
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2)
    safe_print("[qa] queries=%d answered=%d no_evidence=%d -> %s"
               % (doc["total_queries"], doc["answered"], doc["no_evidence"], out_path))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        safe_print("[qa][FATAL] %s: %s" % (type(exc).__name__, exc))
        sys.exit(2)
