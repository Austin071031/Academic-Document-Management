#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step5b verify_cas：复跑核对（第三方可独立执行）。

重新哈希 library/tree/ 下每个文件，逐项检查：
1. tree 文件的内容哈希 == index.json 登记的 content_id；
2. 该哈希对应的对象确实存在于 library/objects/<前2位>/<sha256>；
3. 对象库中的对象数与"唯一内容数"一致（无丢失、无多余也如实报告）。

任何不一致都列入 mismatches，退出码 1；全部一致退出码 0。
报告写入 <output>/library/verify_report.json。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cas_common import read_json, sha256_file, write_json


def verify(input_dir, work_dir, output_dir):
    library = os.path.join(output_dir, "library")
    tree_root = os.path.join(library, "tree")
    objects_dir = os.path.join(library, "objects")
    index = read_json(os.path.join(library, "index.json")) or {}

    by_tree = {f.get("tree_path"): f for f in index.get("files", [])
               if f.get("tree_path")}
    mismatches, checked = [], 0

    # tree → 哈希 → 对象存在性
    seen_digests = set()
    if os.path.isdir(tree_root):
        for root, dirs, files in os.walk(tree_root):
            dirs.sort()
            files.sort()
            for name in files:
                full = os.path.join(root, name)
                rel = "tree/" + os.path.relpath(full, tree_root).replace(
                    os.sep, "/")
                checked += 1
                try:
                    digest = sha256_file(full)
                except OSError as e:
                    mismatches.append({"path": rel, "problem":
                                       "无法重新读取: %s" % e})
                    continue
                seen_digests.add(digest)
                entry = by_tree.pop(rel, None)
                if entry is None:
                    mismatches.append({"path": rel, "problem":
                                       "tree 文件未在 index.json 登记"})
                    continue
                if entry["content_id"] != digest:
                    mismatches.append({"path": rel, "problem":
                                       "哈希与 index 登记不符: %s != %s"
                                       % (digest[:12],
                                          entry["content_id"][:12])})
                obj = os.path.join(objects_dir, digest[:2], digest)
                if not os.path.exists(obj):
                    mismatches.append({"path": rel, "problem":
                                       "对象库缺失对象 %s" % digest[:12]})

    # index 登记了但 tree 缺失
    for rel in by_tree:
        mismatches.append({"path": rel, "problem": "index 登记但 tree 缺失"})

    # 对象库盘点
    object_count = 0
    if os.path.isdir(objects_dir):
        for sub in os.listdir(objects_dir):
            subdir = os.path.join(objects_dir, sub)
            if os.path.isdir(subdir):
                object_count += sum(
                    1 for x in os.listdir(subdir)
                    if os.path.isfile(os.path.join(subdir, x)))

    report = {
        "ok": not mismatches,
        "tree_files_checked": checked,
        "unique_contents_in_tree": len(seen_digests),
        "objects_in_store": object_count,
        "mismatches": mismatches[:100],
        "mismatch_count": len(mismatches),
    }
    write_json(os.path.join(library, "verify_report.json"), report)
    return report


def main():
    ap = argparse.ArgumentParser(description="复跑核对：tree 与对象库比对")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    r = verify(a.input, a.work, a.output)
    print("verify %s: checked=%d objects=%d mismatches=%d"
          % ("ok" if r["ok"] else "FAILED", r["tree_files_checked"],
             r["objects_in_store"], r["mismatch_count"]))
    sys.exit(0 if r["ok"] else 1)


if __name__ == "__main__":
    main()
