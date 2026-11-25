#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_index.py -- 段落级索引: 为每个可检索文本块生成可定位锚点。

锚点坐标: {anchor_id, file_id, path, doc_base, version_label, canonical,
           page, para_index, char_start, char_end}
  - PDF 文本以 \f 分页, page 取段首所在页(1 起)
  - 其他文本 page=null, 以 para_index + char 偏移定位
  - 默认只索引 canonical 版本, --all-versions 可索引全部(用于版本对比题)

用法:
  python3 kb_index.py --work /app/work [--all-versions]

输入: inventory.json / extract_report.json / versions.json / text/*.txt
输出: <work>/index.jsonl  (每行一个锚点, 含截断至 2000 字符的段落文本)
"""
import argparse
import json
import os
import sys
import time


def iter_paragraphs(txt):
    """yield (page, para_index, char_start, char_end, paragraph_text)"""
    page = 1
    pos = 0
    pidx = 0
    for block in txt.split("\f"):
        block_start = pos
        chunks = [c for c in block.split("\n\n") if c.strip()]
        # 兼容没有空行分隔的抽取文本: 退化为按行聚合成 <=500 字符的段
        if not chunks:
            lines = [ln for ln in block.splitlines() if ln.strip()]
            buf, buf_start = [], None
            for ln in lines:
                if buf_start is None:
                    buf_start = block_start
                buf.append(ln)
                if sum(len(x) + 1 for x in buf) >= 500:
                    t = "\n".join(buf)
                    yield page, pidx, buf_start, buf_start + len(t), t.strip()
                    pidx += 1
                    buf, buf_start = [], None
            if buf:
                t = "\n".join(buf)
                yield page, pidx, block_start, block_start + len(t), t.strip()
                pidx += 1
        else:
            off = block_start
            for c in chunks:
                start = off
                t = c.strip()
                yield page, pidx, start, start + len(c), t
                pidx += 1
                off = start + len(c) + 2
        pos += len(block) + 1
        page += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--all-versions", action="store_true")
    ap.add_argument("--max-chars", type=int, default=2000)
    args = ap.parse_args()

    W = args.work
    inv = json.load(open(os.path.join(W, "inventory.json"), encoding="utf-8"))
    rep = json.load(open(os.path.join(W, "extract_report.json"), encoding="utf-8"))
    vers = json.load(open(os.path.join(W, "versions.json"), encoding="utf-8"))

    canonical = {}
    docbase = {}
    dups = set()
    for d in vers.get("documents", []):
        canonical[d["canonical"]] = True
        for v in d["versions"]:
            docbase[v["path"]] = d["doc_base"]
            dups.update(v.get("duplicate_paths") or [])

    status_by_path = {e["path"]: e for e in rep.get("files", [])}
    n = 0
    out_path = os.path.join(W, "index.jsonl")
    with open(out_path, "w", encoding="utf-8") as out:
        for e in rep.get("files", []):
            if e["status"] != "ok":
                continue
            if e["path"] in dups:
                continue  # 重复副本不入索引(已由原版本代表)
            if not args.all_versions and e["path"] not in canonical:
                continue
            tp = os.path.join(W, "text", e["file_id"] + ".txt")
            if not os.path.isfile(tp):
                continue
            txt = open(tp, encoding="utf-8").read()
            stem = os.path.splitext(os.path.basename(e["path"]))[0]
            for page, pidx, cs, ce, para in iter_paragraphs(txt):
                if not para:
                    continue
                rec = {
                    "anchor_id": "a%06d" % n,
                    "file_id": e["file_id"],
                    "path": e["path"],
                    "doc_base": docbase.get(e["path"], stem.lower()),
                    "canonical": e["path"] in canonical,
                    "page": page,
                    "para_index": pidx,
                    "char_start": cs,
                    "char_end": ce,
                    "text": para[: args.max_chars],
                }
                out.write(json.dumps(rec, ensure_ascii=False) + "\n")
                n += 1

    meta = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "tool": "kb_index.py", "anchors": n,
            "scope": "all-versions" if args.all_versions else "canonical-only",
            "out": out_path}
    with open(os.path.join(W, "index_meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    sys.stdout.write("# 索引完成: %d anchors (%s)\n" % (n, meta["scope"]))


if __name__ == "__main__":
    main()
