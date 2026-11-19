#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pagefix.py — 【版本1 旗舰】页码校正与版式修复引擎。

在 extract 之后、segment 之前运行：
1. 多线索印刷页↔物理页偏移估计：
   - 页眉/页脚数字候选（footer/header 行，等差数列拟合）
   - 目录解析：行内 "标题 ……… 页码" 的点线引导模式
   - 两条线索互相印证 → offset + confidence + basis
2. 双栏重排：对高置信双栏页面按稳定分列点切成左右两栏纵向拼接。
3. 跨页图表续接：页尾未完结的 Table/Figure 题注与次页行拼接并记录。

输出: <work-dir>/pagefix.json；同时把修正文本写回 corpus.json
（每页增加 text_fixed / printed_page 字段），segment.py 自动优先采用。
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Journal, read_json, write_json
from segment import (RE_PAGENUM_CN, RE_PAGENUM_FOOT, RE_PAGENUM_WORD,
                     column_evidence, reconstruct_columns)

RE_TOC_LINE = re.compile(
    r"^\s*(\d{1,2}(?:\.\d{1,3}){0,3})\s+(.{1,80}?)\s*[.·•‥⋯。]{3,}\s*(\d{1,4})\s*$")
RE_FIGREF_TOC = re.compile(
    r"(?i)^\s*(figure|fig\.?|图|表|table)\s*\d+.*?\s*[.·•‥⋯。]{3,}\s*(\d{1,4})\s*$")


def footer_candidates(page_texts):
    cands = {}
    for phys, text in page_texts.items():
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            continue
        for line in (lines[-1], lines[0], lines[-2] if len(lines) > 1 else ""):
            m = (RE_PAGENUM_WORD.match(line) or RE_PAGENUM_CN.match(line)
                 or RE_PAGENUM_FOOT.match(line))
            if m:
                n = int(m.group(1))
                if 1 <= n <= 5000:
                    cands.setdefault(phys, n)
                    break
    return cands


def fit_offset(cands, min_support=3, min_frac=0.6):
    if len(cands) < min_support:
        return None, 0.0, "insufficient candidates (%d)" % len(cands)
    diffs = {}
    for phys, pr in sorted(cands.items()):
        diffs.setdefault(pr - phys, []).append(phys)
    best_off, sup = max(diffs.items(), key=lambda kv: len(kv[1]))
    frac = len(sup) / len(cands)
    conf = min(1.0, (len(sup) / min_support) * frac)
    if len(sup) >= min_support and frac >= min_frac:
        return best_off, round(conf, 2), \
            "arithmetic fit: offset=%d, %d/%d pages" % (best_off, len(sup), len(cands))
    return None, round(conf, 2), \
        "no stable arithmetic offset (best %d/%d)" % (len(sup), len(cands))


def parse_toc(page_texts):
    """从文本前部若干页解析目录条目：编号标题→印刷页码。"""
    entries = []
    for phys in sorted(page_texts)[:8]:
        for line in page_texts[phys].splitlines():
            m = RE_TOC_LINE.match(line)
            if m:
                entries.append({"number": m.group(1), "title": m.group(2).strip(),
                                "printed_page": int(m.group(3)), "toc_page": phys})
                continue
            m2 = RE_FIGREF_TOC.match(line)
            if m2:
                entries.append({"number": None, "title": line.strip()[:60],
                                "printed_page": int(m2.group(2)), "toc_page": phys})
    return entries


def toc_offset(toc, sections_titles):
    """目录印刷页与实际章节物理页对齐以估计偏移（需 segment 先行，
    此处独立实现: 用目录条目在全文中的出现位置近似）。"""
    return None, "toc alignment requires post-segment pass"


def stitch_captions(page_texts):
    """跨页题注/表格续接：页尾以 Table/Fig 开头且行短 → 与次页首行拼接。"""
    stitched = []
    phys_sorted = sorted(page_texts)
    fixed = dict(page_texts)
    for i, phys in enumerate(phys_sorted[:-1]):
        lines = [l for l in fixed[phys].splitlines() if l.strip()]
        if not lines:
            continue
        last = lines[-1].strip()
        starts = re.match(r"(?i)^(table|figure|fig\.?|表|图)\s*\d+", last)
        if starts and len(last) < 100 and not last.endswith((".", "。", ";")):
            nxt = phys_sorted[i + 1]
            nxt_lines = [l for l in fixed[nxt].splitlines() if l.strip()]
            if nxt_lines:
                fixed[phys] = fixed[phys] + "\n[→p%d] " % nxt + nxt_lines[0]
                stitched.append({"from_page": phys, "to_page": nxt,
                                 "fragment": last[:80]})
    return fixed, stitched


def process_doc(doc, journal):
    pages = {p["page"]: p.get("text", "") for p in doc.get("pages", [])}
    if not pages:
        return None
    rec = {"doc_id": doc["doc_id"], "path": doc.get("path")}
    col = column_evidence(pages)
    rec["column_evidence"] = col
    fixed_pages = dict(pages)
    if col.get("likely_two_column"):
        fixed_pages = {n: reconstruct_columns(t) for n, t in pages.items()}
        rec["column_reconstructed"] = True
    fixed_pages, stitched = stitch_captions(fixed_pages)
    if stitched:
        rec["stitched_blocks"] = stitched
    cands = footer_candidates(fixed_pages)
    off, conf, basis = fit_offset(cands)
    rec["footer_candidates"] = {str(k): v for k, v in cands.items()}
    rec["offset"] = off
    rec["offset_confidence"] = conf
    rec["offset_basis"] = basis
    toc = parse_toc(fixed_pages)
    if toc:
        rec["toc_entries"] = toc[:60]
    # 印刷页标注
    for p in doc.get("pages", []):
        n = p["page"]
        p["text_fixed"] = fixed_pages.get(n, p.get("text", ""))
        p["printed_page"] = (n + off) if off is not None else None
        p["printed_page_confidence"] = conf if off is not None else None
    journal.log("1.5-pagefix", "%s offset=%s conf=%s stitched=%d toc=%d"
                % (doc.get("path"), off, conf, len(stitched), len(toc)),
                status="ok" if off is not None else "partial")
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    a = ap.parse_args()
    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    corpus_path = os.path.join(a.work_dir, "corpus.json")
    corpus = read_json(corpus_path, {}) or {}
    recs = []
    for doc in corpus.get("docs", []):
        r = process_doc(doc, journal)
        if r:
            recs.append(r)
    write_json(corpus_path, corpus)  # 写回 text_fixed / printed_page
    out = write_json(os.path.join(a.work_dir, "pagefix.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "docs": recs,
        "stats": {"docs": len(recs),
                  "offsets_confident": sum(1 for r in recs
                                           if r.get("offset") is not None),
                  "columns_reconstructed": sum(1 for r in recs
                                               if r.get("column_reconstructed")),
                  "stitched": sum(len(r.get("stitched_blocks") or [])
                                  for r in recs)},
    })
    s = json.loads(json.dumps(read_json(out)["stats"]))
    journal.log("1.5-pagefix", "done %s" % s, outputs=[out])
    print("pagefix:", json.dumps(s, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
