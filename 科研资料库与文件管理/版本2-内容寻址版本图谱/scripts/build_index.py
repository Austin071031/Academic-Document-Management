#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step2 build_index：逻辑索引 + 规范工作树 checkout。

产物：
- <output>/library/index.json  逻辑路径 → 对象哈希 → 源路径/mtime/权限/来源
- <output>/library/tree/       从对象库 checkout 出的规范工作树
                               （按 `项目/年份/类型/规范文件名` 组织；
                                文件名冲突追加 __dupN，绝不覆盖）

元数据字段一律带出处：
  {field, value, source: filename|content|companion_table|admin_note|agent_inference,
   evidence}
抽不到则为 null + 原因，绝不猜。文件名模式（项目号_作者_年份_类型.ext）优先，
伴随表格（CSV）与管理备注（md/txt）按文件名 join。
"""
import argparse
import csv
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cas_common import (ensure_dir, is_probably_text, load_jsonl, norm,
                        read_text, write_json)

YEAR_RE = re.compile(r"(?:19|20)\d{2}")
ADMIN_HINTS = ("备注", "说明", "版本", "管理", "笔记", "note", "readme",
               "changelog", "manifest")
NAME_KEYS = ("文件名", "文件", "名称", "路径", "filename", "file", "path",
             "name")

CATEGORY_MAP = [
    ("论文文档", {".pdf", ".doc", ".docx", ".tex", ".bib", ".rtf", ".odt"}),
    ("表格数据", {".csv", ".tsv", ".xls", ".xlsx", ".ods"}),
    ("数据文件", {".json", ".jsonl", ".xml", ".yaml", ".yml", ".dat",
                  ".npy", ".npz", ".h5", ".mat", ".pkl"}),
    ("代码脚本", {".py", ".r", ".sh", ".bash", ".ipynb", ".java", ".c",
                  ".h", ".cpp", ".js", ".ts", ".sql", ".m"}),
    ("笔记文本", {".md", ".markdown", ".txt", ".rst", ".log"}),
    ("图片图形", {".png", ".jpg", ".jpeg", ".gif", ".svg", ".tif",
                  ".tiff", ".bmp", ".eps"}),
    ("压缩包", {".zip", ".tar", ".gz", ".tgz", ".bz2", ".xz"}),
]


def categorize(name):
    ext = os.path.splitext(norm(name))[1].lower()
    for cat, exts in CATEGORY_MAP:
        if ext in exts:
            return cat
    return "其他"


def parse_filename(name):
    """解析 `项目号_作者_年份_类型.ext` 类文件名模式。
    返回 {field: {value, source, evidence}}，抽不到的字段为
    {value: None, source: None, evidence: 原因}。"""
    base = norm(os.path.basename(name))
    stem, ext = os.path.splitext(base)
    segs = [s for s in re.split(r"[_\-—－]+", stem) if s]
    fields = {}

    def put(field, value, source, evidence):
        fields[field] = {"field": field, "value": value,
                         "source": source, "evidence": evidence}

    year = None
    for s in segs:
        m = YEAR_RE.search(s)
        if m:
            year = m.group(0)
            break
    if year is None:
        m = YEAR_RE.search(stem)
        year = m.group(0) if m else None
    put("year", year, "filename" if year else None,
        ("文件名段含年份: %s" % base) if year else "文件名中未发现 19xx/20xx 年份")

    project = segs[0] if len(segs) >= 2 else None
    put("project", project, "filename" if project else None,
        ("首段为项目号: %s" % base) if project else "文件名无分隔段，无法识别项目号")

    author = None
    if len(segs) >= 3:
        cand = segs[1]
        if not YEAR_RE.fullmatch(cand):
            author = cand
    put("author", author, "filename" if author else None,
        ("第二段为作者: %s" % base) if author else "文件名段数不足，无法识别作者")

    put("doc_type", segs[-1] if len(segs) >= 2 else None,
        "filename" if len(segs) >= 2 else None,
        ("末段为类型: %s" % base) if len(segs) >= 2 else "无类型段")
    put("extension", ext.lower() or None, "filename" if ext else None,
        base if ext else "无扩展名")
    return fields


def collect_metadata_sources(input_dir, ledger_files):
    """解析伴随元数据表（CSV）与管理性版本备注（md/txt）。
    返回 (companion: {basename: [记录]}, admin: {basename: [记录]})。"""
    companion, admin = {}, {}
    for e in ledger_files:
        base = norm(os.path.basename(e["path"]))
        ext = os.path.splitext(base)[1].lower()
        src_disk = os.path.join(input_dir, e["path"]) \
            if e.get("origin") == "direct" else None
        if not src_disk or not os.path.exists(src_disk):
            continue
        if ext == ".csv":
            try:
                text = read_text(src_disk, max_bytes=1048576)
                rows = list(csv.reader(text.splitlines()))
            except Exception:
                continue
            if len(rows) < 2:
                continue
            header = [h.strip() for h in rows[0]]
            key_idx = None
            for i, h in enumerate(header):
                if h.lower() in NAME_KEYS or any(k in h for k in NAME_KEYS):
                    key_idx = i
                    break
            if key_idx is None:
                continue
            for row in rows[1:]:
                if key_idx >= len(row):
                    continue
                key = norm(os.path.basename(row[key_idx].strip()))
                if not key:
                    continue
                rec = {"source": "companion_table",
                       "evidence": "%s: %s" % (base, " | ".join(row)),
                       "row": {header[i]: row[i] for i in
                               range(min(len(header), len(row)))}}
                companion.setdefault(key, []).append(rec)
        elif ext in (".md", ".txt") and any(h in base.lower()
                                            for h in ADMIN_HINTS):
            try:
                text = read_text(src_disk, max_bytes=1048576)
            except Exception:
                continue
            for line in text.splitlines():
                line = line.strip().lstrip("#-*• ")
                if not line or len(line) < 3:
                    continue
                # 行内出现的任何已知文件名都建立关联
                for f in ledger_files:
                    fb = norm(os.path.basename(f["path"]))
                    fstem = os.path.splitext(fb)[0]
                    if fb != base and (fb in line or
                                       (len(fstem) >= 4 and fstem in line)):
                        rec = {"source": "admin_note",
                               "evidence": "%s: %s" % (base, line[:300])}
                        admin.setdefault(fb, []).append(rec)
    return companion, admin


def checkout(object_path, tree_root, logical_rel, used):
    """把对象 checkout 到 tree/<logical_rel>；冲突追加 __dupN，绝不覆盖。"""
    rel = logical_rel
    n = 1
    while rel in used or os.path.exists(os.path.join(tree_root, rel)):
        stem, ext = os.path.splitext(logical_rel)
        rel = "%s__dup%d%s" % (stem, n, ext)
        n += 1
    used.add(rel)
    dst = os.path.join(tree_root, rel)
    ensure_dir(os.path.dirname(dst))
    # 复制（而非硬链接）出工作树：防止对 tree 的误写通过共享 inode
    # 污染对象库；对象库是唯一真相源。
    try:
        shutil.copy2(object_path, dst)
    except OSError:
        os.link(object_path, dst)
    return rel


def build_index(input_dir, work_dir, output_dir):
    library = os.path.join(output_dir, "library")
    objects_dir = os.path.join(library, "objects")
    ledger = load_jsonl(os.path.join(library, "objects.jsonl"))
    files = [e for e in ledger if e.get("type") == "file"
             and e.get("readable") and e.get("sha256")]
    skipped = [e for e in ledger if e.get("skipped")]
    dirs = [e for e in ledger if e.get("type") == "dir"]
    broken = [e for e in ledger if e.get("broken")]

    companion, admin = collect_metadata_sources(input_dir, files)

    tree_root = ensure_dir(os.path.join(library, "tree"))
    used = set()
    entries = []
    conflicts = 0
    for e in files:
        if e.get("role") == "control":
            continue
        base = norm(os.path.basename(e["path"]))
        meta = parse_filename(base)
        project = meta["project"]["value"] or "未识别项目"
        year = meta["year"]["value"] or "未知年份"
        category = categorize(base)
        logical_rel = norm(os.path.join(str(project), str(year),
                                        category, base))

        notes = []
        for rec in companion.get(base, []) + \
                companion.get(os.path.splitext(base)[0], []):
            notes.append(rec)
            for k, v in rec.get("row", {}).items():
                fk = "table_" + k.strip()
                if fk not in meta and v:
                    meta[fk] = {"field": fk, "value": v,
                                "source": "companion_table",
                                "evidence": rec["evidence"]}
        for rec in admin.get(base, []):
            notes.append(rec)

        digest = e["sha256"]
        object_path = os.path.join(objects_dir, digest[:2], digest)
        if not os.path.exists(object_path):
            object_path = None
        tree_rel = None
        if object_path:
            tree_rel = checkout(object_path, tree_root, logical_rel, used)
            if tree_rel != logical_rel:
                conflicts += 1
        entries.append({
            "logical_path": logical_rel.replace(os.sep, "/"),
            "tree_path": ("tree/" + tree_rel.replace(os.sep, "/"))
            if tree_rel else None,
            "content_id": digest,
            "source_path": e["path"],
            "size": e.get("size"),
            "mtime": e.get("mtime"),
            "permissions": e.get("permissions"),
            "origin": e.get("origin", "direct"),
            "category": category,
            "is_text": is_probably_text(
                os.path.join(tree_root, tree_rel)) if tree_rel else False,
            "metadata": meta,
            "notes": notes,
        })

    index = {
        "version": 2,
        "files": entries,
        "stats": {
            "indexed_files": len(entries),
            "unique_contents": len({x["content_id"] for x in entries}),
            "tree_conflicts_renamed": conflicts,
            "skipped_files": len(skipped),
            "empty_dirs": len(dirs),
            "broken_archives": len(broken),
            "companion_tables_used": len({r["evidence"].split(":")[0]
                                          for v in companion.values()
                                          for r in v}),
            "admin_notes_used": len({r["evidence"].split(":")[0]
                                     for v in admin.values() for r in v}),
        },
        "skipped": [{"path": s["path"], "reason": s.get("reason")}
                    for s in skipped],
        "empty_dirs": [d["path"] for d in dirs if d.get("empty")],
        "broken_archives": [{"path": b["path"], "reason": b.get("reason")}
                            for b in broken],
    }
    write_json(os.path.join(library, "index.json"), index)
    return index["stats"]


def main():
    ap = argparse.ArgumentParser(description="建立逻辑索引与工作树")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    s = build_index(a.input, a.work, a.output)
    print("index ok: indexed=%(indexed_files)d unique=%(unique_contents)d "
          "conflicts=%(tree_conflicts_renamed)d" % s)


if __name__ == "__main__":
    main()
