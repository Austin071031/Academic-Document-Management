#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""segment.py — 章节切分、段落锚点、印刷页↔物理页映射。

- 标题识别：编号式(2.3 / 2.3.1)、中文式(第X章/节)、全大写短行、Markdown #。
- 段落：空行分隔的文本块，记录 page / printed_page / section_path / 首句。
- 页码映射：页眉页脚中的数字或 "Page N" / "第 N 页" 模式，
  若构成等差数列则给出 offset=printed-physical；否则 printed_page=null。
- 双栏启发：检测稳定的多空格分列位置，给出 column_layout 证据。

用法: python3 segment.py --work-dir /app/work
输出: <work-dir>/sections.json
"""
import argparse
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Journal, norm_text, read_json, write_json

RE_NUMHEAD = re.compile(r"^(\d{1,2}(?:\.\d{1,3}){0,3})[.、\s]\s*(\S.{0,120})$")
RE_CNHEAD = re.compile(r"^(第[一二三四五六七八九十百\d]{1,6}[章节篇部])\s*(\S.{0,80})$")
RE_MDHEAD = re.compile(r"^(#{1,4})\s+(\S.{0,120})$")
RE_PAGENUM_FOOT = re.compile(r"^\s*(?:[-–—•·\s]*)?(\d{1,4})(?:[-–—•·\s]*)?$")
RE_PAGENUM_WORD = re.compile(r"(?i)^(?:page|p\.?)\s*(\d{1,4})\s*$")
RE_PAGENUM_CN = re.compile(r"^\s*第?\s*(\d{1,4})\s*页?\s*$")
RE_TABLE_START = re.compile(r"(?i)^(table|表)\s*\d+[:：.]?\s*\S")
RE_FIGCAP = re.compile(r"(?i)^(figure|fig\.?|图)\s*\d+")


def is_heading(line, prev_blank):
    s = line.strip()
    if not s or len(s) > 120:
        return None
    m = RE_MDHEAD.match(s)
    if m:
        return ("md", len(m.group(1)), m.group(2).strip())
    m = RE_NUMHEAD.match(s)
    if m and len(m.group(2)) > 1:
        depth = m.group(1).count(".") + 1
        return ("num", depth, s)
    m = RE_CNHEAD.match(s)
    if m:
        return ("cn", 1, s)
    letters = [c for c in s if c.isalpha()]
    if (letters and sum(c.isupper() for c in letters) / len(letters) > 0.85
            and len(s) <= 60 and not s.endswith((".", "。", ";", "；", ","))
            and prev_blank):
        return ("caps", 1, s)
    return None


def extract_page_numbers(page_texts):
    """从每页首/末行抽取候选印刷页码，返回 {physical: printed} 与可信度。"""
    cands = {}
    for phys, text in page_texts.items():
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        if not lines:
            continue
        for line in (lines[0], lines[-1], lines[1] if len(lines) > 1 else "",
                     lines[-2] if len(lines) > 2 else ""):
            m = (RE_PAGENUM_WORD.match(line) or RE_PAGENUM_CN.match(line)
                 or RE_PAGENUM_FOOT.match(line))
            if m:
                n = int(m.group(1))
                if 1 <= n <= 5000:
                    cands.setdefault(phys, n)
                    break
    return cands


def fit_page_offset(cands):
    """若 physical 与 printed 呈稳定等差关系则返回 offset 与证据。"""
    if len(cands) < 3:
        return None, "insufficient page-number candidates (%d)" % len(cands)
    diffs = {}
    for phys, pr in sorted(cands.items()):
        diffs.setdefault(pr - phys, []).append(phys)
    best_off, best_sup = max(diffs.items(), key=lambda kv: len(kv[1]))
    support = len(best_sup)
    frac = support / len(cands)
    if support >= 3 and frac >= 0.6:
        return best_off, "offset=%d supported by %d/%d pages" % (best_off, support, len(cands))
    return None, "no consistent offset (best %d/%d pages)" % (support, len(cands))


def column_evidence(page_texts):
    """双栏启发：统计含 3+ 空格分列的行及其分裂位置一致性。"""
    split_pos, multi = {}, 0
    total = 0
    for text in page_texts.values():
        for line in text.splitlines():
            if len(line.strip()) < 20:
                continue
            total += 1
            gaps = [m.start() for m in re.finditer(r" {3,}", line)]
            if len(gaps) == 1:
                multi += 1
                bucket = round(gaps[0] / 10) * 10
                split_pos[bucket] = split_pos.get(bucket, 0) + 1
    if total == 0:
        return {"likely_two_column": False, "basis": "no measurable lines"}
    frac = multi / total
    consistent = bool(split_pos) and max(split_pos.values()) >= max(3, multi * 0.5)
    return {"likely_two_column": frac > 0.25 and consistent,
            "multi_gap_line_fraction": round(frac, 3),
            "dominant_split_buckets": sorted(split_pos.items(),
                                             key=lambda kv: -kv[1])[:3],
            "basis": "share of lines with a single wide gap and position consistency"}


def reconstruct_columns(text):
    """把疑似双栏页面的行按分裂点切成左右两栏再纵向拼接。"""
    out_left, out_right = [], []
    for line in text.splitlines():
        m = re.search(r" {3,}", line)
        if m and len(line.strip()) >= 20:
            out_left.append(line[:m.start()].rstrip())
            out_right.append(line[m.end():].lstrip())
        else:
            out_left.append(line)
            out_right.append("")
    merged = []
    for l, r in zip(out_left, out_right):
        if l:
            merged.append(l)
    for r in out_right:
        if r:
            merged.append(r)
    return "\n".join(merged)


def segment_doc(doc, journal, pagefix_recs=None):
    """对单文档切分。返回 sections, paragraphs, page_map, notes。
    若 pagefix.json 提供修正文本与偏移（版本1旗舰），优先采用。"""
    pf = (pagefix_recs or {}).get(doc["doc_id"], {})
    if pf.get("column_reconstructed") or "text_fixed" in (doc.get("pages") or [{}])[0]:
        pages = {p["page"]: p.get("text_fixed") or p.get("text", "")
                 for p in doc.get("pages", [])}
        notes = {"column_evidence": pf.get("column_evidence"),
                 "column_source": "pagefix"}
    else:
        pages = {p["page"]: p.get("text", "") for p in doc.get("pages", [])}
        notes = {}
        col = column_evidence(pages)
        notes["column_evidence"] = col
        if col.get("likely_two_column"):
            pages = {n: reconstruct_columns(t) for n, t in pages.items()}
            notes["column_reconstructed"] = True
            journal.log("2-segment", "two-column reconstruction applied to %s"
                        % doc.get("path"), status="recovered")

    if pf.get("offset") is not None:
        offset = pf["offset"]
        off_basis = "pagefix: " + str(pf.get("offset_basis"))
        cands = pf.get("footer_candidates") or {}
    else:
        cands = extract_page_numbers(pages)
        offset, off_basis = fit_page_offset(cands)
    page_map = {"offset": offset, "basis": off_basis,
                "candidates": {str(k): v for k, v in cands.items()}}

    def printed(phys):
        return phys + offset if offset is not None else None

    sections, paragraphs = [], []
    sec_stack = []     # [(depth, number-or-title, section_id)]
    para_idx = 0
    cur_sec_id = None
    cur_path = ""
    cur_title = None
    buf, buf_start_page = [], None

    def flush(end_page):
        nonlocal buf, buf_start_page, para_idx
        if not buf:
            return
        text = "\n".join(buf)
        buf = []
        if not text.strip():
            buf_start_page = None
            return
        para_idx += 1
        sentences = re.split(r"(?<=[。！？.!?])\s*", text.strip())
        head = sentences[0][:80] if sentences else text[:80]
        paragraphs.append({
            "para_id": "%s-p%04d" % (doc["doc_id"], para_idx),
            "doc_id": doc["doc_id"],
            "section_id": cur_sec_id,
            "section_path": cur_path,
            "page": buf_start_page,
            "printed_page": printed(buf_start_page),
            "page_end": end_page,
            "first_sentence": norm_text(head),
            "text": text,
        })
        buf_start_page = None

    for phys in sorted(pages):
        text = pages[phys]
        prev_blank = True
        for line in text.splitlines():
            h = is_heading(line, prev_blank)
            if h:
                flush(phys)
                kind, depth, title = h
                sec_id = "%s-s%03d" % (doc["doc_id"], len(sections) + 1)
                while sec_stack and sec_stack[-1][0] >= depth:
                    sec_stack.pop()
                parent = sec_stack[-1][2] if sec_stack else None
                chain = [s[1] for s in sec_stack] + [title]
                sec = {"section_id": sec_id, "doc_id": doc["doc_id"],
                       "parent_id": parent, "level": depth,
                       "path": " > ".join(chain), "title": title,
                       "heading_kind": kind, "page": phys,
                       "printed_page": printed(phys)}
                sections.append(sec)
                sec_stack.append((depth, title, sec_id))
                cur_sec_id = sec_id
                cur_path = sec["path"]
                cur_title = title
                prev_blank = True
                continue
            if not line.strip():
                flush(phys)
                prev_blank = True
                continue
            if buf_start_page is None:
                buf_start_page = phys
            # 跨页图表题注拼接：行首 Table/Figure 且本行很短时暂存，下页续接
            buf.append(line)
            prev_blank = False
        flush(phys)

    for s in sections:  # 段落数与页范围
        pars = [p for p in paragraphs if p["section_id"] == s["section_id"]]
        s["para_count"] = len(pars)
        s["page_end"] = max([p["page_end"] or p["page"] for p in pars],
                            default=s["page"])
    return sections, paragraphs, page_map, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    a = ap.parse_args()
    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    corpus = read_json(os.path.join(a.work_dir, "corpus.json"), {}) or {}
    pagefix = read_json(os.path.join(a.work_dir, "pagefix.json"), {}) or {}
    pf_by_doc = {r["doc_id"]: r for r in pagefix.get("docs", [])}

    all_sec, all_par, maps, notes_all = [], [], {}, {}
    for doc in corpus.get("docs", []):
        if not doc.get("pages"):
            continue
        sec, par, pmap, notes = segment_doc(doc, journal, pf_by_doc)
        all_sec.extend(sec)
        all_par.extend(par)
        maps[doc["doc_id"]] = pmap
        notes_all[doc["doc_id"]] = notes
        journal.log("2-segment", "%s: %d sections, %d paragraphs, offset=%s"
                    % (doc.get("path"), len(sec), len(par), pmap["offset"]))

    out = write_json(os.path.join(a.work_dir, "sections.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "sections": all_sec, "paragraphs": all_par,
        "page_maps": maps, "notes": notes_all,
        "stats": {"sections": len(all_sec), "paragraphs": len(all_par),
                  "docs_with_offset": sum(1 for m in maps.values()
                                          if m.get("offset") is not None)},
    })
    journal.log("2-segment", "done", outputs=[out])
    print("sections=%d paragraphs=%d" % (len(all_sec), len(all_par)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
