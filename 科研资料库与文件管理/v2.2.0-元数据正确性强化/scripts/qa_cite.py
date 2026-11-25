#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa_cite.py —— 检索问答与引用证据（v2.2.0 新增）。

对 <output>/library/ 下的文本文件建立倒排索引：
  - 拉丁/数字词整词切分；
  - 中文按连续 CJK 串取 bigram（单字词退化为 unigram），作为中文兜底；
  - 索引落盘 work/search_index.json（供 recover.py 索引重建复用）。

回答 /input/case.json 中的 searches / questions（条目可为字符串或
{"query"/"q"/"question"/"search"/"text": ...} 字典），输出
/app/output/search_results.json。每条答案的每个命中必须带引用证据：
  {"file": 库内相对路径, "line": 行号, "snippet": 原文片段,
   "metadata_provenance": {字段: {"value":…, "source":…}}}
其中 metadata_provenance 取自 manifest.json 中该文件已裁决字段的来源，
让"答案→原文行→元数据出处"三层证据链闭合。
查不到证据时诚实返回 status=no_evidence 并说明缺什么，绝不编造。

--index-only：只重建索引（供 recover.py 恢复后重建检索索引调用）。
幂等：每次运行整体覆盖重写 search_results.json / search_index.json。
单文件读取失败登记 work/qa_skipped.jsonl，不崩溃。
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

TEXT_EXTS = {"txt", "md", "csv", "json", "log", "rst", "tex", "yaml", "yml",
             "xml", "tsv", "ini", "cfg", ""}
MAX_FILE_BYTES = 1024 * 1024        # 单文件最多索引 1MB
MAX_POSTINGS_PER_TOKEN = 500        # 单 token 最多记录的 (doc,line) 数
TOP_N = 5                           # 每个查询最多返回的命中数
SNIPPET_CHARS = 200

RE_LATIN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_\-\./]*")
RE_CJK = re.compile(r"[一-鿿㐀-䶿]+")


def tokenize(text):
    """拉丁整词 + 中文 bigram（单字退 unigram）。"""
    tokens = []
    for m in RE_LATIN.finditer(text):
        tokens.append(m.group(0).lower())
    for m in RE_CJK.finditer(text):
        run = m.group(0)
        if len(run) == 1:
            tokens.append(run)
        else:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
    return tokens


def unigram_fallback(text):
    """中文单字兜底（bigram 无命中时使用）。"""
    tokens = []
    for m in RE_CJK.finditer(text):
        tokens.extend(list(m.group(0)))
    return tokens


def norm_text(s):
    return re.sub(r"\s+", "", str(s)).lower()


def build_index(lib_root, work):
    """遍历 library 文本文件建倒排索引。返回 (docs, postings, skipped)。"""
    docs = {}      # rel -> {"lines": [...], "encoding": enc}
    postings = {}  # token -> {rel: [line_numbers]}
    skipped = []
    if not os.path.isdir(lib_root):
        return docs, postings, skipped
    for dirpath, _dirnames, filenames in os.walk(lib_root):
        for name in sorted(filenames):
            ap = os.path.join(dirpath, name)
            rel = os.path.relpath(ap, lib_root)
            ext = os.path.splitext(name)[1].lower().lstrip(".")
            if ext not in TEXT_EXTS:
                skipped.append({"file": rel, "reason": "binary/unsupported ext '.%s'，不索引内容" % ext})
                continue
            try:
                with open(ap, "rb") as f:
                    data = f.read(MAX_FILE_BYTES)
                text, enc, warn = lc.decode_bytes(data)
            except OSError as e:
                skipped.append({"file": rel, "reason": "read failed: %s" % e})
                continue
            lines = text.splitlines()
            docs[rel] = {"lines": lines, "encoding": enc,
                         "truncated": warn is not None}
            seen_in_doc = {}
            for ln, line in enumerate(lines, start=1):
                for tok in set(tokenize(line)):
                    seen_in_doc.setdefault(tok, []).append(ln)
            for tok, lns in seen_in_doc.items():
                posting = postings.setdefault(tok, {})
                if sum(len(v) for v in posting.values()) < MAX_POSTINGS_PER_TOKEN:
                    posting[rel] = lns[:50]
    return docs, postings, skipped


def load_manifest_map(output):
    """library_rel -> 注解 {fields, superseded}；另给 basename 兜底映射（恢复副本用）。"""
    manifest = lc.jread(os.path.join(output, "manifest.json"), default={}) or {}
    by_rel, by_base = {}, {}
    for e in manifest.get("entries") or []:
        lp = e.get("library_path")
        if not lp:
            continue
        rel = os.path.relpath(lp, "library") if lp.startswith("library") else lp
        fields = {}
        for f, p in (e.get("provenance") or {}).items():
            val = (e.get("fields") or {}).get(f)
            if val not in (None, ""):
                fields[f] = {"value": val, "source": p.get("source")}
        anno = {"fields": fields,
                "superseded": bool(e.get("superseded_by")),
                "superseded_by": e.get("superseded_by")}
        by_rel[rel] = anno
        base = os.path.basename(lp)
        by_base.setdefault(base, []).append(anno)
    # basename 唯一时才兜底（避免同名歧义误挂出处）
    by_base = {b: v[0] for b, v in by_base.items() if len(v) == 1}
    return by_rel, by_base


def anno_for(rel, by_rel, by_base):
    a = by_rel.get(rel)
    if a is None:
        a = by_base.get(os.path.basename(rel),
                        {"fields": {}, "superseded": False, "superseded_by": None})
    return a


def extract_queries(case):
    """从 case.json 提取查询清单：searches + questions，兼容字符串/字典。"""
    queries = []

    def add(items, kind):
        if isinstance(items, (str, dict)):
            items = [items]
        if not isinstance(items, list):
            return
        for i, it in enumerate(items):
            if isinstance(it, str):
                text = it.strip()
                qid = "%s-%d" % (kind, i + 1)
            elif isinstance(it, dict):
                text = ""
                for k in ("query", "q", "question", "search", "text"):
                    if it.get(k):
                        text = str(it[k]).strip()
                        break
                qid = str(it.get("id") or it.get("name") or "%s-%d" % (kind, i + 1))
            else:
                continue
            if text:
                queries.append({"id": qid, "kind": kind, "query": text})

    add(case.get("searches"), "search")
    add(case.get("questions"), "question")
    return queries


def answer_query(query, docs, postings, by_rel, by_base, top_n=TOP_N):
    qtokens = sorted(set(tokenize(query)))
    used_fallback = False
    if qtokens:
        scores = {}
        for tok in qtokens:
            for rel, lns in (postings.get(tok) or {}).items():
                for ln in lns:
                    scores.setdefault((rel, ln), set()).add(tok)
    else:
        scores = {}
    if not scores:
        # 中文 bigram 无命中 → unigram 兜底
        uni = sorted(set(unigram_fallback(query)))
        for tok in uni:
            for rel, lns in (postings.get(tok) or {}).items():
                for ln in lns:
                    scores.setdefault((rel, ln), set()).add(tok)
        if scores:
            used_fallback = True
            qtokens = uni
    # 整句子串精确命中加权（归一化后包含查询串的行排最前）
    nq = norm_text(query)
    phrase_hits = set()
    if nq:
        for rel, d in docs.items():
            for ln, line in enumerate(d["lines"], start=1):
                if nq and nq in norm_text(line):
                    phrase_hits.add((rel, ln))
                    scores.setdefault((rel, ln), set()).update(qtokens or ["(phrase)"])
    if not scores:
        return {
            "status": "no_evidence",
            "answer": None,
            "missing": ("library 文本索引中没有任何行命中查询词 %s；"
                        "缺少含这些关键词的可读文本文件或关键词未出现在前 1MB 内容中"
                        % (qtokens or [query])),
            "hits": [],
        }
    # idf 加权：稀有词命中权重高，避免被"报告/记录"类高频词淹没
    df = {t: len(p) for t, p in postings.items()}

    def score_of(matched):
        return sum(1.0 / (1.0 + df.get(t, 1)) for t in matched)

    ranked = sorted(
        scores.items(),
        key=lambda kv: (kv[0] not in phrase_hits,
                        -score_of(kv[1]) * (0.5 if anno_for(kv[0][0], by_rel, by_base)["superseded"] else 1.0),
                        kv[0][0], kv[0][1]))
    hits = []
    for (rel, ln), matched in ranked[:top_n]:
        anno = anno_for(rel, by_rel, by_base)
        line = docs[rel]["lines"][ln - 1] if ln - 1 < len(docs[rel]["lines"]) else ""
        hit = {
            "file": "library/" + rel,
            "line": ln,
            "snippet": line.strip()[:SNIPPET_CHARS],
            "matched_terms": sorted(matched)[:20],
            "score": round(score_of(matched)
                           * (0.5 if anno["superseded"] else 1.0), 4),
            "metadata_provenance": anno["fields"],
        }
        if anno["superseded"]:
            hit["superseded_by"] = anno["superseded_by"]
            hit["note"] = "该文件已被新版本替代，排名已降权"
        hits.append(hit)
    seen_snip, uniq_snips = set(), []
    for h in hits:
        k = norm_text(h["snippet"])
        if h["snippet"] and k not in seen_snip:
            seen_snip.add(k)
            uniq_snips.append(h["snippet"])
        if len(uniq_snips) >= 3:
            break
    answer = " | ".join(uniq_snips)
    best = hits[0]
    return {
        "status": "answered",
        "answer": answer,
        "answer_basis": ("extractive: 前 %d 条命中行原文拼接，首条 %s 第 %d 行%s"
                         % (min(3, len(hits)), best["file"], best["line"],
                            "；整句精确命中" if (ranked[0][0] in phrase_hits)
                            else "；中文unigram兜底" if used_fallback else "")),
        "hits": hits,
    }


def main():
    ap = argparse.ArgumentParser(description="检索问答与引用证据（v2.2.0）")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--index-only", action="store_true",
                    help="只重建检索索引，不回答查询（recover.py 索引重建用）")
    a = ap.parse_args()

    lib_root = os.path.join(a.output, "library")
    docs, postings, skipped = build_index(lib_root, a.work)
    if skipped:
        lc.jappend(os.path.join(a.work, "qa_skipped.jsonl"), skipped)

    # 索引落盘（幂等覆盖）
    lc.jwrite(os.path.join(a.work, "search_index.json"), {
        "generated_at": lc.now_iso(),
        "library_root": "library",
        "docs": {rel: {"n_lines": len(d["lines"]), "encoding": d["encoding"]}
                 for rel, d in docs.items()},
        "postings": postings,
        "tokenizer": "latin words + CJK bigrams (unigram fallback)",
    })

    case = lc.jread(os.path.join(a.input, "case.json"), default={}) or {}
    queries = extract_queries(case)
    by_rel, by_base = load_manifest_map(a.output)

    results = []
    n_answered = n_no_evidence = 0
    if not a.index_only:
        for q in queries:
            try:
                ans = answer_query(q["query"], docs, postings, by_rel, by_base)
            except Exception as e:  # 单查询失败不崩溃
                ans = {"status": "no_evidence", "answer": None,
                       "missing": "query evaluation failed: %s: %s"
                                  % (type(e).__name__, e), "hits": []}
            if ans["status"] == "answered":
                n_answered += 1
            else:
                n_no_evidence += 1
            results.append({"id": q["id"], "kind": q["kind"],
                            "query": q["query"], **ans})

    out_obj = {
        "generated_at": lc.now_iso(),
        "method": ("inverted index over library/ text files "
                   "(latin words + CJK bigrams, unigram fallback); "
                   "extractive answers with {file,line,snippet} citations "
                   "+ per-file metadata provenance sources"),
        "index_stats": {"docs_indexed": len(docs),
                        "tokens": len(postings),
                        "files_skipped": len(skipped)},
        "n_queries": len(results),
        "n_answered": n_answered,
        "n_no_evidence": n_no_evidence,
        "results": results,
    }
    if a.index_only:
        # 索引重建模式：不触碰既有 search_results.json（避免抹掉已作答结果），
        # 仅在有新恢复文件且存在旧结果时提示需重跑问答
        prev = lc.jread(os.path.join(a.output, "search_results.json"),
                        default=None)
        if prev is not None and prev.get("index_stats", {}).get("docs_indexed") != len(docs):
            sys.stderr.write(
                "[qa_cite] index changed (%s -> %d docs); "
                "rerun without --index-only to refresh answers\n"
                % (prev.get("index_stats", {}).get("docs_indexed"), len(docs)))
    else:
        lc.jwrite(os.path.join(a.output, "search_results.json"), out_obj)
        lc.jwrite(os.path.join(a.work, "qa_summary.json"), {
            "n_queries": len(results), "n_answered": n_answered,
            "n_no_evidence": n_no_evidence,
            "no_evidence_queries": [r["query"] for r in results
                                    if r["status"] == "no_evidence"],
        })
    lc.log_change(a.work, "qa_cite", "search_results.json",
                  "inverted index over library + case.json searches/questions",
                  "%d queries: %d answered, %d no_evidence; %d docs indexed"
                  % (len(results), n_answered, n_no_evidence, len(docs)))
    print("[qa_cite] docs=%d tokens=%d queries=%d answered=%d no_evidence=%d"
          % (len(docs), len(postings), len(results), n_answered, n_no_evidence))
    return 0


if __name__ == "__main__":
    sys.exit(main())
