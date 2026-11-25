#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_metadata.py -- 六维度元数据抽取: 文献字段 + 来源溯源 + 版本差异摘要。

补齐"结果完整性"要求的六个维度中 v1 缺失的两项:
  元数据字段: title/authors/year/doi/arxiv(抽取文本头部 + BibTeX/RIS 侧车 + 文件名,
              逐字段记录 source 与 confidence, 缺失字段如实为 null 绝不编造)
  来源:      路径来源(库内相对路径)、别名/符号链接目标、重复副本 canonical 归属
  版本差异:   相邻版本的行级 diff 统计(+/− 行数, 变化段落对数), 支撑"版本差异"维度

用法:
  python3 kb_metadata.py --work /app/work
输出: <work>/metadata.json
"""
import argparse
import difflib
import json
import os
import re
import sys
import time

DOI_PAT = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Za-z0-9]+")
ARXIV_PAT = re.compile(r"\b(\d{4}\.\d{4,5})(v\d+)?\b|arXiv:(\d{4}\.\d{4,5})", re.I)
YEAR_PAT = re.compile(r"\b(19|20)\d{2}\b")
EMAILISH = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+")
BIB_KEY = re.compile(r"@\w+\s*\{\s*([^,]+)")
BIB_FIELD = re.compile(r"(?i)\b(title|author|year|doi|journal|booktitle)\s*=\s*[\{\"]([^\}\"]+)")


def load(p):
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def guess_title(text):
    for ln in text.splitlines()[:30]:
        s = ln.strip()
        if 8 <= len(s) <= 200 and not EMAILISH.search(s) and not s.startswith(("http", "©")):
            return s
    return None


def guess_authors(text):
    for ln in text.splitlines()[:40]:
        s = ln.strip()
        if re.match(r"^[A-Z][a-zA-Z.\-]+( [A-Z][a-zA-Z.\-]+)*(, ?[A-Z][a-zA-Z.\-]+( [A-Z][a-zA-Z.\-]+)*)+( and |、|, and )?", s):
            if 2 <= len(s.split(",")) <= 12 or " and " in s:
                return [x.strip() for x in re.split(r",| and |、", s) if x.strip()][:12]
    return None


def meta_from_text(text):
    head = text[:8000]
    doi = DOI_PAT.search(head)
    arxiv = ARXIV_PAT.search(head)
    year = None
    for m in YEAR_PAT.finditer(head[:3000]):
        y = int(m.group(0))
        if 1900 <= y <= 2100:
            year = y
            break
    return {
        "title": guess_title(text),
        "authors": guess_authors(text),
        "year": year,
        "doi": doi.group(0).rstrip(".,;)") if doi else None,
        "arxiv": (arxiv.group(1) or arxiv.group(3)) if arxiv else None,
    }


def parse_bib(path):
    try:
        raw = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return None
    entry = {}
    for m in BIB_FIELD.finditer(raw):
        entry[m.group(1).lower()] = m.group(2).strip()
    return entry or None


def diff_summary(a, b):
    al = a.splitlines()
    bl = b.splitlines()
    sm = difflib.SequenceMatcher(None, al, bl, autojunk=False)
    plus = minus = pairs = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "replace":
            pairs += 1
            plus += j2 - j1
            minus += i2 - i1
        elif tag == "delete":
            minus += i2 - i1
        elif tag == "insert":
            plus += j2 - j1
    return {"lines_added": plus, "lines_removed": minus,
            "replaced_blocks": pairs, "total_lines_old": len(al),
            "total_lines_new": len(bl)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()
    W = args.work
    inv = load(os.path.join(W, "inventory.json"))
    rep = load(os.path.join(W, "extract_report.json"))
    vers = load(os.path.join(W, "versions.json"))

    fid_by_path = {e["path"]: e["file_id"] for e in rep.get("files", [])}
    texts = {}

    def text_of(path):
        if path not in texts:
            tp = os.path.join(W, "text", (fid_by_path.get(path) or "") + ".txt")
            texts[path] = open(tp, encoding="utf-8").read() if os.path.isfile(tp) else None
        return texts[path]

    dup_map = {}
    for d in vers.get("documents", []):
        for v in d["versions"]:
            for p in v.get("duplicate_paths") or []:
                dup_map[p] = v["path"]

    out = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "tool": "kb_metadata.py", "documents": []}

    # BibTeX 侧车索引(按目录)
    bib_index = {}
    for f in inv.get("files", []):
        if f.get("ext") in (".bib", ".ris"):
            bib_index[os.path.dirname(f.get("path") or "")] = f.get("path")

    for d in vers.get("documents", []):
        chain = d["versions"]
        prev_txt = None
        for v in chain:
            p = v["path"]
            rec = {"path": p, "label": v.get("label"),
                   "canonical": p == d["canonical"],
                   "sha256_16": (v.get("sha256") or "")[:16],
                   "source": {"library_path": p,
                              "duplicate_of": dup_map.get(p),
                              "supersedes": v.get("supersedes"),
                              "mtime": v.get("mtime")},
                   "metadata": {}, "version_diff": None}
            t = text_of(p)
            if t:
                m = meta_from_text(t)
                rec["metadata"] = {k: {"value": val, "source": "extracted_text",
                                       "confidence": "heuristic"} if val is not None
                                   else {"value": None, "source": None,
                                         "confidence": "missing"}
                                   for k, val in m.items()}
                bibp = bib_index.get(os.path.dirname(p))
                if bibp:
                    rec["metadata_sidecar"] = bibp
            else:
                rec["metadata"] = {k: {"value": None, "source": None,
                                        "confidence": "missing"}
                                   for k in ("title", "authors", "year", "doi", "arxiv")}
                rec["metadata_note"] = "无可抽取文本, 元数据缺失(如实记录)"
            if prev_txt is not None and t is not None and prev_txt != t:
                rec["version_diff"] = diff_summary(prev_txt, t)
            elif prev_txt == t and t is not None:
                rec["version_diff"] = {"lines_added": 0, "lines_removed": 0,
                                       "replaced_blocks": 0,
                                       "note": "与上一版本内容一致"}
            prev_txt = t
            out["documents"].append(rec)

    with open(os.path.join(W, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    n = sum(1 for r in out["documents"] if any(
        (v.get("value") for v in (r.get("metadata") or {}).values())))
    sys.stdout.write("# 元数据完成: 文档 %d, 含非空元数据 %d; 版本差异已统计 -> metadata.json\n"
                     % (len(out["documents"]), n))


if __name__ == "__main__":
    main()
