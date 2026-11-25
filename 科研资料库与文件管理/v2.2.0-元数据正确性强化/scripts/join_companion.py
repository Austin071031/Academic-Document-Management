#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""join_companion.py —— 伴随元数据表（CSV/TSV）join。

识别伴随表：可读 csv/tsv，且满足其一：
  (a) 文件名含 元数据/metadata/伴随/companion/清单/manifest/台账/ledger；
  (b) 表头含文件名类列（文件名/file/路径/path...）且至少另有一列可映射到字段字典。
排除管理性备注表（表头含 原文件/新文件/替代/replaced 等，交给 parse_admin_notes）。
匹配方式：按文件名主干归一化（norm_key）或相对路径后缀匹配到扫描到的文件，
每行其余列经 field_aliases 映射后产出 source=companion_table 候选。
未匹配的行登记到 companion_unmatched.jsonl，不静默。
"""
import argparse
import csv
import io
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

NAME_HINTS = ["元数据", "metadata", "伴随", "companion", "清单", "manifest",
              "台账", "ledger", "索引", "index"]
FILENAME_HEADERS = ["文件名", "文件", "file", "filename", "name", "路径", "path",
                    "relpath", "附件"]
ADMIN_HEADERS = ["原文件", "新文件", "旧文件", "替代", "replaced", "superseded",
                 "old_file", "new_file"]


def detect_table(path):
    """返回 (dialect_delimiter, header, rows, encoding) 或 None。"""
    try:
        text, enc, warn = lc.read_text_head(path, limit=512 * 1024)
    except OSError:
        return None
    sample = text[:4096]
    if not sample.strip():
        return None
    delim = "\t" if sample.splitlines()[0].count("\t") > sample.splitlines()[0].count(",") else ","
    try:
        rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    except csv.Error:
        return None
    rows = [r for r in rows if any(c.strip() for c in r)]
    if len(rows) < 1:
        return None
    return delim, [c.strip() for c in rows[0]], rows[1:], enc


def is_admin_table(basename, header):
    low = basename.lower() + " " + " ".join(h.lower() for h in header)
    return any(k in low for k in ADMIN_HEADERS) and not any(
        k in low for k in NAME_HINTS)


def looks_companion(basename, header):
    low = basename.lower()
    if any(k in low for k in NAME_HINTS):
        return True
    hset = {h.lower() for h in header}
    return bool(hset & {h.lower() for h in FILENAME_HEADERS}) and len(header) >= 2


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    dictionary = lc.load_dictionary(a.work, a.config)
    amap = lc.alias_map(dictionary)

    files = list(lc.jlines(os.path.join(a.work, "files.jsonl")) or [])
    by_key = {}
    for r in files:
        if r.get("readable"):
            by_key.setdefault(lc.norm_key(r["basename"]), []).append(r)
            by_key.setdefault(lc.norm_key(r["relpath"]), []).append(r)

    cands, unmatched, tables = [], [], 0
    for rec in files:
        if not rec.get("readable") or rec.get("ext") not in ("csv", "tsv"):
            continue
        path = rec.get("abspath") or os.path.join(a.input, rec["relpath"])
        got = detect_table(path)
        if not got:
            continue
        delim, header, rows, enc = got
        if is_admin_table(rec["basename"], header):
            continue  # 管理备注表交给 parse_admin_notes
        if not looks_companion(rec["basename"], header):
            continue
        tables += 1
        # 找文件名类列
        hlow = [h.lower() for h in header]
        fcol = None
        for cand_h in FILENAME_HEADERS:
            if cand_h.lower() in hlow:
                fcol = hlow.index(cand_h.lower())
                break
        if fcol is None:
            fcol = 0  # 文件名提示型表默认首列
        # 其余列 -> 字段
        col_field = {}
        for i, h in enumerate(header):
            if i == fcol:
                continue
            f = amap.get(h.lower())
            if f:
                col_field[i] = f
        if not col_field:
            unmatched.append({"table": rec["relpath"], "row": "(header)",
                              "reason": "no column maps to field dictionary"})
            continue
        for ridx, row in enumerate(rows, start=2):
            if fcol >= len(row):
                continue
            target = row[fcol].strip()
            if not target:
                continue
            hits = by_key.get(lc.norm_key(target)) or []
            if not hits and "/" in target.replace("\\", "/"):
                hits = by_key.get(lc.norm_key(target.replace("\\", "/").split("/")[-1])) or []
            if not hits:
                unmatched.append({"table": rec["relpath"], "row": ridx,
                                  "target": target, "reason": "no scanned file matches"})
                continue
            for hit in hits:
                if hit["relpath"] == rec["relpath"]:
                    continue  # 表自身不注解自身
                for i, field in col_field.items():
                    if i >= len(row):
                        continue
                    val = row[i].strip()
                    if not val:
                        continue
                    cands.append(lc.candidate(
                        hit["relpath"], field, val, "companion_table",
                        "companion '%s' row %d col '%s' (encoding=%s, matched '%s')"
                        % (rec["relpath"], ridx, header[i], enc, target)))

    lc.jappend(os.path.join(a.work, "candidates.jsonl"), cands)
    lc.jappend(os.path.join(a.work, "companion_unmatched.jsonl"), unmatched)
    lc.log_change(a.work, "join_companion", "candidates.jsonl",
                  "csv/tsv header mapping + normalized-stem join",
                  "%d tables, %d candidates, %d unmatched rows"
                  % (tables, len(cands), len(unmatched)))
    print("[companion] tables=%d candidates=%d unmatched=%d" % (tables, len(cands), len(unmatched)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
