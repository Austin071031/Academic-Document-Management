#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""inventory.py — 盘点输入文件：清单、哈希、权限、重复与别名候选。

用法: python3 inventory.py --input-root /input --work-dir /app/work [--no-hash]
输出: <work-dir>/inventory.json
"""
import argparse
import json
import os
import stat
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Journal, categorize, norm_basename, sha256_file,
                    sniff_magic, version_tags, which_tools, write_json)


def walk_files(root):
    entries, failures = [], []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        for fn in sorted(filenames):
            p = os.path.join(dirpath, fn)
            rel = os.path.relpath(p, root)
            st = None
            rec = {"path": rel, "name": fn, "category": categorize(p),
                   "is_symlink": os.path.islink(p)}
            try:
                st = os.lstat(p)
                rec["size_bytes"] = st.st_size
                rec["mtime"] = time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                             time.gmtime(st.st_mtime))
                mode = stat.S_IMODE(st.st_mode)
                rec["readable"] = bool(mode & stat.S_IRUSR) or os.access(p, os.R_OK)
            except OSError as e:
                rec["readable"] = False
                rec["stat_error"] = "%s: %s" % (type(e).__name__, e)
            if rec.get("readable"):
                try:
                    with open(p, "rb") as f:
                        rec["magic"] = sniff_magic(p)
                except OSError as e:
                    rec["readable"] = False
                    rec["stat_error"] = str(e)
            rec["version_tags"], rec["date_hints"] = version_tags(fn)
            entries.append(rec)
    return entries, failures


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--no-hash", action="store_true")
    a = ap.parse_args()

    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    journal.log("0-inventory", "start", inputs=[a.input_root])

    if not os.path.isdir(a.input_root):
        write_json(os.path.join(a.work_dir, "inventory.json"), {
            "input_root": a.input_root, "root_exists": False, "files": [],
            "duplicates": [], "alias_groups": [], "failures": [
                {"type": "path_missing", "path": a.input_root,
                 "detail": "input root does not exist"}]})
        journal.log("0-inventory", "input root missing", status="failed")
        print("input root missing:", a.input_root)
        return 2

    entries, failures = walk_files(a.input_root)
    hash_groups = {}
    for e in entries:
        if e.get("readable") and not a.no_hash:
            h = sha256_file(os.path.join(a.input_root, e["path"]))
            e["sha256"] = h
            if h:
                hash_groups.setdefault(h, []).append(e["path"])

    duplicates = [{"sha256": h, "paths": ps} for h, ps in hash_groups.items()
                  if len(ps) > 1]

    alias_groups = {}
    for e in entries:
        key = norm_basename(e["name"])
        if len(key) >= 4:
            alias_groups.setdefault(key, []).append(e["path"])
    alias_groups = [{"normalized_name": k, "paths": v}
                    for k, v in alias_groups.items() if len(v) > 1]

    no_perm = [e for e in entries if not e.get("readable")]
    zero = [e for e in entries if e.get("size_bytes") == 0]

    inv = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_root": a.input_root,
        "root_exists": True,
        "tools": which_tools(),
        "file_count": len(entries),
        "files": entries,
        "duplicates": duplicates,
        "alias_groups": alias_groups,
        "failures": failures + [
            {"type": "no_permission", "path": e["path"]}
            for e in no_perm] + [
            {"type": "empty_file", "path": e["path"]} for e in zero],
        "stats": {
            "total": len(entries),
            "unreadable": len(no_perm),
            "empty": len(zero),
            "duplicate_groups": len(duplicates),
            "alias_groups": len(alias_groups),
            "by_category": _count_by(entries, "category"),
        },
    }
    out = write_json(os.path.join(a.work_dir, "inventory.json"), inv)
    journal.log("0-inventory", "scanned %d files, %d dup groups, %d unreadable"
                % (len(entries), len(duplicates), len(no_perm)),
                outputs=[out])
    print(json.dumps(inv["stats"], ensure_ascii=False))
    return 0


def _count_by(entries, key):
    d = {}
    for e in entries:
        d[e.get(key) or "unknown"] = d.get(e.get(key) or "unknown", 0) + 1
    return d


if __name__ == "__main__":
    sys.exit(main())
