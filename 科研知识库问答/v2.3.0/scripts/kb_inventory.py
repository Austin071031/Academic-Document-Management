#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_inventory.py -- 盘点科研资料库：文件清单、哈希、权限、类型、可读性。

用法:
  python3 kb_inventory.py --roots /input/library /input --work /app/work [--json /app/work/inventory.json]

输出:
  <work>/inventory.json   完整清单（文件、目录、哈希、权限、类型、可读性、抽样预览）
  <work>/inventory_summary.txt  人读摘要

设计原则: 只依赖 Python 标准库; 不追随符号链接; 不因单个文件失败而中断;
所有结果可复跑(记录扫描根、时间戳、文件数、哈希算法)。
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import time

CHUNK = 1 << 20
TEXT_EXT = {".txt", ".md", ".markdown", ".rst", ".csv", ".tsv", ".bib", ".tex",
            ".json", ".xml", ".html", ".htm", ".py", ".yaml", ".yml", ".log",
            ".ini", ".cfg", ".nt"}
DOC_EXT = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".xlsx", ".xls", ".odt", ".ods", ".odp"}
IMG_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".tif", ".tiff", ".bmp"}


def sha256_of(path, max_bytes=None):
    h = hashlib.sha256()
    n = 0
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
            n += len(b)
            if max_bytes and n >= max_bytes:
                break
    return h.hexdigest()


def classify(ext):
    e = ext.lower()
    if e == ".pdf":
        return "pdf"
    if e in (".docx",):
        return "docx"
    if e in (".pptx",):
        return "pptx"
    if e in (".xlsx",):
        return "xlsx"
    if e in (".doc", ".ppt", ".xls"):
        return "legacy-office"
    if e in TEXT_EXT:
        return "text"
    if e in IMG_EXT:
        return "image"
    if e == "":
        return "no-extension"
    return "other"


def preview_text(path, limit=400):
    try:
        with open(path, "rb") as f:
            raw = f.read(limit * 4)
        return raw.decode("utf-8", errors="replace")[:limit]
    except Exception as exc:  # noqa: BLE001
        return "<preview failed: %s>" % exc


def file_record(root, dirpath, name):
    p = os.path.join(dirpath, name)
    rel = os.path.relpath(p, root)
    rec = {"path": rel.replace(os.sep, "/"), "name": name, "is_symlink": os.path.islink(p)}
    try:
        st = os.lstat(p)
        rec.update({
            "size": st.st_size,
            "mtime": int(st.st_mtime),
            "uid": st.st_uid,
            "gid": st.st_gid,
            "mode": oct(stat.S_IMODE(st.st_mode)),
        })
    except OSError as exc:
        rec["stat_error"] = "%s: %s" % (type(exc).__name__, exc)
        return rec
    ext = os.path.splitext(name)[1]
    rec["ext"] = ext.lower()
    rec["type"] = classify(ext)
    rec["readable"] = os.access(p, os.R_OK)
    rec["writable"] = os.access(p, os.W_OK)
    if rec["is_symlink"]:
        try:
            rec["link_target"] = os.readlink(p)
        except OSError:
            pass
        rec["hash"] = None
        rec["hash_note"] = "symlink not followed"
        return rec
    if not rec["readable"]:
        rec["hash"] = None
        rec["hash_note"] = "not readable (permission)"
        return rec
    if not os.path.isfile(p):
        rec["hash"] = None
        rec["hash_note"] = "not a regular file"
        return rec
    try:
        rec["hash"] = sha256_of(p)
    except OSError as exc:
        rec["hash"] = None
        rec["hash_error"] = "%s: %s" % (type(exc).__name__, exc)
    if rec["type"] == "text" and st.st_size <= 2 * 1024 * 1024:
        rec["preview"] = preview_text(p)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--roots", nargs="+", required=True,
                    help="待盘点的一个或多个目录(通常先 /input 下的资料库目录)")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--json", default=None)
    args = ap.parse_args()

    os.makedirs(args.work, exist_ok=True)
    out_path = args.json or os.path.join(args.work, "inventory.json")

    files, dirs, errors = [], [], []
    for root in args.roots:
        if not os.path.isdir(root):
            errors.append({"root": root, "error": "not a directory or missing"})
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            rel_dir = os.path.relpath(dirpath, root)
            dirs.append({"root": root, "path": rel_dir.replace(os.sep, "/"),
                         "file_count": len(filenames)})
            if not filenames and rel_dir != ".":
                dirs[-1]["note"] = "empty directory"
            for name in sorted(filenames):
                try:
                    files.append(file_record(root, dirpath, name))
                except Exception as exc:  # noqa: BLE001
                    errors.append({"root": root, "path": os.path.join(rel_dir, name),
                                   "error": "%s: %s" % (type(exc).__name__, exc)})

    inv = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": "kb_inventory.py",
        "hash_algorithm": "sha256",
        "roots": args.roots,
        "counts": {
            "files": len(files),
            "directories": len(dirs),
            "unreadable": sum(1 for f in files if f.get("readable") is False),
            "symlinks": sum(1 for f in files if f.get("is_symlink")),
            "by_type": {},
        },
        "directories": dirs,
        "files": files,
        "errors": errors,
    }
    for f in files:
        t = f.get("type", "unknown")
        inv["counts"]["by_type"][t] = inv["counts"]["by_type"].get(t, 0) + 1

    with open(out_path, "w", encoding="utf-8") as fp:
        json.dump(inv, fp, ensure_ascii=False, indent=1)

    lines = ["# 资料库盘点摘要 (%s)" % inv["generated_at"],
             "roots: %s" % ", ".join(args.roots),
             "files: %d  directories: %d  unreadable: %d  symlinks: %d  errors: %d"
             % (len(files), len(dirs), inv["counts"]["unreadable"],
                inv["counts"]["symlinks"], len(errors)),
             "by_type: " + json.dumps(inv["counts"]["by_type"], ensure_ascii=False)]
    for e in errors:
        lines.append("ERROR %s: %s" % (e.get("path"), e.get("error")))
    summary = "\n".join(lines) + "\n"
    with open(os.path.join(args.work, "inventory_summary.txt"), "w", encoding="utf-8") as fp:
        fp.write(summary)
    sys.stdout.write(summary)


if __name__ == "__main__":
    main()
