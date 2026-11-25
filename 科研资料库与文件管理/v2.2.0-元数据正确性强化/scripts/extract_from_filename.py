#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_from_filename.py —— 文件名模式解析器。

读取字段字典中的可配置正则集（filename_patterns），对每个文件 basename 逐一尝试，
命中即产出 source=filename 的字段候选，追加到 work/candidates.jsonl。
绝不猜测：未命中任何模式则不产出该字段候选。
"""
import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

FLAGS = {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE}


def compile_patterns(dictionary):
    pats = []
    for p in dictionary.get("filename_patterns") or []:
        fl = 0
        for f in p.get("flags") or []:
            fl |= FLAGS.get(f, 0)
        try:
            pats.append((p["name"], re.compile(p["regex"], fl), p.get("map") or {}))
        except (re.error, KeyError) as e:
            sys.stderr.write("[filename] bad pattern %s: %s\n" % (p.get("name"), e))
    return pats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    dictionary = lc.load_dictionary(a.work, a.config)
    pats = compile_patterns(dictionary)
    known_fields = set((dictionary.get("fields") or {}).keys())

    out, matched_files = [], 0
    for rec in lc.jlines(os.path.join(a.work, "files.jsonl")):
        if not rec.get("readable"):
            continue
        base = rec["basename"]
        hit = False
        for name, rx, gmap in pats:
            m = rx.search(base)
            if not m:
                continue
            for gkey, field in gmap.items():
                if known_fields and field not in known_fields:
                    continue
                try:
                    val = m.group(int(gkey)) if str(gkey).isdigit() else m.group(gkey)
                except Exception:
                    val = None
                if val is None:
                    continue
                val = val.strip().strip("._- ")
                if not val:
                    continue
                hit = True
                out.append(lc.candidate(
                    rec["relpath"], field, val, "filename",
                    "pattern '%s' group '%s' on basename '%s'" % (name, gkey, base)))
        if hit:
            matched_files += 1

    lc.jappend(os.path.join(a.work, "candidates.jsonl"), out)
    lc.log_change(a.work, "extract_filename", "candidates.jsonl",
                  "%d configured patterns" % len(pats),
                  "%d candidates from %d/%d files" % (
                      len(out), matched_files,
                      sum(1 for _ in lc.jlines(os.path.join(a.work, "files.jsonl")) or [])))
    print("[filename] candidates=%d" % len(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
