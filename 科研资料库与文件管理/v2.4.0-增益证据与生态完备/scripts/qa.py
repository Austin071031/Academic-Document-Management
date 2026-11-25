#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qa.py — 轻量检索问答：回答 case.json 的 searches/questions（纯标准库）。

方法：对 /app/output/library/（已归位副本；不存在则退回输入目录）的
文本类文件建倒排索引（CJK 二元组 + 拉丁词 token），逐 query 命中
返回 文件 + 行号 + 片段。无命中诚实登记 status=no_evidence，绝不编造。

输出：/app/output/search_results.json
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

TEXT_EXTS = {'.txt', '.md', '.csv', '.tsv', '.json', '.py', '.sh', '.tex',
             '.bib', '.ris', '.rtf', '.dat', '.log', '.xml', '.html', '.htm'}
MAX_FILE_BYTES = 2 << 20      # 2MB 以上的文件不做全文索引（仍可按文件名命中）
MAX_SNIPPET = 200
MAX_HITS_PER_QUERY = 20

WORD_RE = re.compile(r'[A-Za-z0-9_]{2,}')
CJK_RE = re.compile(r'[一-鿿]')


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def tokens(text):
    """CJK 字符二元组 + 拉丁/数字词（小写）。单 CJK 字也保留为 token。"""
    out = set()
    for w in WORD_RE.findall(text):
        out.add(w.lower())
    cjk = CJK_RE.findall(text)
    out.update(cjk)  # 单字（短查询兜底）
    out.update(''.join(cjk[i:i + 2]) for i in range(len(cjk) - 1))
    return out


def iter_library_files(root):
    for r, dirs, names in os.walk(root, followlinks=False):
        dirs.sort()
        names.sort()
        for n in names:
            full = os.path.join(r, n)
            if os.path.splitext(n)[1].lower() in TEXT_EXTS:
                yield full, os.path.relpath(full, root)


def build_index(root):
    """返回 {path: [(lineno, line_text)], ...} + 每文件的 token 集。"""
    docs = {}
    for full, rel in iter_library_files(root):
        try:
            if os.path.getsize(full) > MAX_FILE_BYTES:
                continue
            with open(full, encoding='utf-8', errors='replace') as f:
                lines = f.read().splitlines()
        except OSError:
            continue
        docs[rel] = lines
    return docs


def extract_queries(case):
    """兼容多种 case.json 形态：searches / questions / queries；
    元素可为字符串或 {query|question|q|text: ...}。"""
    out = []
    for key in ('searches', 'questions', 'queries'):
        items = case.get(key)
        if not isinstance(items, list):
            continue
        for it in items:
            if isinstance(it, str):
                q = it.strip()
            elif isinstance(it, dict):
                q = None
                for k in ('query', 'question', 'q', 'text', 'keyword', 'keywords'):
                    v = it.get(k)
                    if isinstance(v, str) and v.strip():
                        q = v.strip()
                        break
                    if isinstance(v, list) and v:
                        q = ' '.join(str(x) for x in v)
                        break
            else:
                q = None
            if q:
                out.append({'kind': key, 'query': q})
    return out


def search(docs, query):
    qtoks = tokens(query)
    if not qtoks:
        return []
    hits = []
    for path in sorted(docs):
        for lno, line in enumerate(docs[path], start=1):
            if not line.strip():
                continue
            ltoks = tokens(line)
            matched = qtoks & ltoks
            if not matched:
                # 子串兜底：长短语直接包含
                if len(query) >= 2 and query in line:
                    matched = {query}
                else:
                    continue
            snippet = line.strip()
            if len(snippet) > MAX_SNIPPET:
                snippet = snippet[:MAX_SNIPPET] + '…'
            hits.append({
                'path': path,
                'line': lno,
                'snippet': snippet,
                'matched_terms': sorted(matched)[:8],
                'score': len(matched),
            })
    # 文件名命中（无正文命中时的补充证据）
    q_low = query.lower()
    for path in sorted(docs):
        base = os.path.basename(path).lower()
        if q_low in base and all(h['path'] != path for h in hits):
            hits.append({'path': path, 'line': None,
                         'snippet': '(filename match)', 'matched_terms': [query],
                         'score': 1})
    hits.sort(key=lambda h: (-h['score'], h['path'], h['line'] or 0))
    return hits[:MAX_HITS_PER_QUERY]


def main():
    ap = argparse.ArgumentParser(description='回答 case.json 的 searches/questions')
    ap.add_argument('--input', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--case', default=None)
    args = ap.parse_args()

    case_path = args.case or os.path.join(args.input, 'case.json')
    case = {}
    if os.path.exists(case_path):
        try:
            with open(case_path, encoding='utf-8') as f:
                case = json.load(f)
        except (OSError, json.JSONDecodeError):
            case = {}

    queries = extract_queries(case)
    lib = os.path.join(args.output, 'library')
    root = lib if os.path.isdir(lib) else args.input
    docs = build_index(root)

    results = []
    for item in queries:
        hits = search(docs, item['query'])
        results.append({
            'kind': item['kind'],
            'query': item['query'],
            'status': 'answered' if hits else 'no_evidence',
            'hits': hits,
            'answer': None if hits else 'no_evidence: 资料库中未检索到支持该查询的内容',
        })

    report = {
        'case_id': case.get('case_id'),
        'generated_at': utcnow(),
        'index_root': root,
        'indexed_files': len(docs),
        'queries_total': len(results),
        'queries_answered': sum(1 for r in results if r['hits']),
        'results': results,
    }
    os.makedirs(args.output, exist_ok=True)
    out_path = os.path.join(args.output, 'search_results.json')
    tmp = out_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_path)
    print('[qa] indexed=%d queries=%d answered=%d -> %s' % (
        len(docs), len(results), report['queries_answered'], out_path))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('[qa] failed: %s: %s' % (type(e).__name__, e), file=sys.stderr)
        sys.exit(1)
