#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_admin_notes.py —— 管理性版本备注（CSV/md/txt）解析器。

识别：文件名含 备注/版本/说明/notes/admin/changelog/更名/替代/作废，
或正文含 替代/已被/改名/作废/replaced/superseded/renamed。
产出两类事实写入 work/facts.jsonl：
  - superseded_by：A 已被 B 替代 / B 替代了 A / A replaced by B / CSV 原文件-新文件 行
  - alias：A 改名为 B / A renamed to B
同时把备注中的“字段: 值”行解析为 source=admin_note 的字段候选（最高优先级）。
"""
import argparse
import csv
import io
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

NOTE_NAME_HINTS = ["备注", "版本", "说明", "notes", "note", "admin", "changelog",
                   "更名", "改名", "替代", "作废", "readme"]
NOTE_TEXT_HINTS = ["替代", "已被", "改名", "更名", "作废", "replaced", "superseded",
                   "renamed", "deprecated"]

# 文本行模式：尽量宽松，token 允许中文/特殊字符文件名
LINE_PATTERNS = [
    ("superseded_by", re.compile(
        r"[「\"'`]?([^「」\"'`\s，。；;:：]+?)[」\"'`]?\s*已被\s*[「\"'`]?([^「」\"'`\s，。；;]+?)[」\"'`]?\s*替代")),
    ("superseded_by", re.compile(
        r"[「\"'`]?([^「」\"'`\s，。；;:：]+?)[」\"'`]?\s*替代了?\s*[「\"'`]?([^「」\"'`\s，。；;]+?)[」\"'`]?",
        0), "reverse"),  # new 替代 old
    ("superseded_by", re.compile(
        r"([^\s,;]+?)\s+(?:is\s+)?(?:replaced|superseded)\s+by\s+([^\s,;]+)", re.IGNORECASE)),
    ("superseded_by", re.compile(
        r"([^\s,;]+?)\s+(?:replaces|supersedes)\s+([^\s,;]+)", re.IGNORECASE), "reverse"),
    ("alias", re.compile(
        r"[「\"'`]?([^「」\"'`\s，。；;:：]+?)[」\"'`]?\s*(?:改名|更名)为?\s*[「\"'`]?([^「」\"'`\s，。；;]+?)[」\"'`]?$")),
    ("alias", re.compile(
        r"([^\s,;]+?)\s+renamed\s+to\s+([^\s,;]+)", re.IGNORECASE)),
]

FIELD_LINE = re.compile(r"^\s*([一-龥A-Za-z_]{1,12})\s*[:：]\s*(.{1,120}?)\s*$")


def clean(tok):
    return tok.strip().strip("「」\"'`（）()，。；;:：、")


def parse_text_lines(text, origin, facts, cands, amap, known_fields):
    for ln, line in enumerate(text.splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith(("#", "//")):
            continue
        for pat in LINE_PATTERNS:
            kind, rx = pat[0], pat[1]
            reverse = len(pat) > 2 and pat[2] == "reverse"
            m = rx.search(s)
            if not m:
                continue
            a_, b_ = clean(m.group(1)), clean(m.group(2))
            if not a_ or not b_ or a_ == b_:
                continue
            old, new = (b_, a_) if reverse else (a_, b_)
            facts.append({
                "type": kind, "old": old, "new": new,
                "source": "admin_note",
                "evidence": "%s line %d: '%s'" % (origin, ln, s[:120]),
                "ts": lc.now_iso(),
            })
            break
        else:
            m = FIELD_LINE.match(s)
            if m:
                f = amap.get(m.group(1).lower())
                if f and (not known_fields or f in known_fields):
                    cands.append((f, m.group(2).strip(),
                                  "%s line %d: '%s'" % (origin, ln, s[:120])))


def parse_csv_rows(text, origin, facts, cands, amap, known_fields):
    try:
        rows = list(csv.reader(io.StringIO(text)))
    except csv.Error:
        return
    rows = [r for r in rows if any(c.strip() for c in r)]
    if not rows:
        return
    header = [h.strip().lower() for h in rows[0]]
    old_i = new_i = None
    for i, h in enumerate(header):
        if h in ("原文件", "旧文件", "old_file", "old", "被替代文件"):
            old_i = i
        if h in ("新文件", "替代文件", "new_file", "new", "replacement"):
            new_i = i
    if old_i is not None and new_i is not None:
        for ridx, row in enumerate(rows[1:], start=2):
            if max(old_i, new_i) >= len(row):
                continue
            old, new = clean(row[old_i]), clean(row[new_i])
            if old and new and old != new:
                facts.append({
                    "type": "superseded_by", "old": old, "new": new,
                    "source": "admin_note",
                    "evidence": "%s csv row %d (%s -> %s)" % (origin, ridx, old, new),
                    "ts": lc.now_iso(),
                })
        return
    # 无明确新旧列：退回逐行文本模式
    for ridx, row in enumerate(rows, start=1):
        parse_text_lines(", ".join(row), "%s csv row %d" % (origin, ridx),
                         facts, cands, amap, known_fields)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    dictionary = lc.load_dictionary(a.work, a.config)
    amap = lc.alias_map(dictionary)
    known_fields = set((dictionary.get("fields") or {}).keys())

    files = list(lc.jlines(os.path.join(a.work, "files.jsonl")) or [])
    by_key = {}
    for r in files:
        if r.get("readable"):
            by_key.setdefault(lc.norm_key(r["basename"]), []).append(r)

    facts, raw_cands, notes_found = [], [], 0
    for rec in files:
        if not rec.get("readable") or rec.get("ext") not in ("csv", "md", "txt", "tsv", ""):
            continue
        path = rec.get("abspath") or os.path.join(a.input, rec["relpath"])
        try:
            text, enc, warn = lc.read_text_head(path, limit=512 * 1024)
        except OSError:
            continue
        name_hit = any(k in rec["basename"].lower() for k in NOTE_NAME_HINTS)
        text_hit = any(k in text for k in NOTE_TEXT_HINTS)
        if not (name_hit or text_hit):
            continue
        notes_found += 1
        if rec.get("ext") in ("csv", "tsv"):
            parse_csv_rows(text, rec["relpath"], facts, raw_cands, amap, known_fields)
            if rec.get("ext") == "tsv":
                parse_text_lines(text.replace("\t", ", "), rec["relpath"],
                                 facts, raw_cands, amap, known_fields)
        else:
            parse_text_lines(text, rec["relpath"], facts, raw_cands, amap, known_fields)

    # 备注中的“字段: 值”候选挂到备注同目录/同名主干文件上挂不到则挂全局（file="*"）
    cands = []
    for field, val, ev in raw_cands:
        cands.append(lc.candidate("*", field, val, "admin_note", ev))

    # 事实去重
    seen, uniq = set(), []
    for f in facts:
        k = (f["type"], lc.norm_key(f["old"]), lc.norm_key(f["new"]))
        if k not in seen:
            seen.add(k)
            uniq.append(f)

    lc.jappend(os.path.join(a.work, "facts.jsonl"), uniq)
    lc.jappend(os.path.join(a.work, "candidates.jsonl"), cands)
    lc.log_change(a.work, "parse_admin_notes", "facts.jsonl",
                  "line patterns + csv old/new columns",
                  "%d note files, %d facts, %d admin-note field candidates"
                  % (notes_found, len(uniq), len(cands)))
    print("[admin_notes] files=%d facts=%d candidates=%d" % (notes_found, len(uniq), len(cands)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
