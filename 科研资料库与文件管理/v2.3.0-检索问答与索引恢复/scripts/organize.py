#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step1 归位：把 /input 下的资料归位到 <output>/library/<项目>/<年份>/<类型>/。

产物：
  library/                  归位后的文件树（UTF-8 安全，特殊字符保留）
  inventory.jsonl           sha256 账本（追加式，每文件一条）
  duplicates.json           内容哈希去重结论（duplicate_of 指向规范副本）
  versions.json             版本链（superseded_by + difflib 差异摘要）
  manifest.json / manifest.csv  元数据（字段带出处 {field,value,source,evidence}）
  extracted.json            压缩包展开登记（含失败原因）
  organize_report.json      汇总统计（含跳过/空目录/不可读登记）

单文件失败不崩溃；不可读文件登记 readable=false + 原因，计"跳过"不静默。
"""
import argparse
import csv
import difflib
import json
import os
import re
import shutil
import sys
import time
import zipfile
import tarfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

SKIP_NAMES = {"case.json", "task.md"}


def load_context(input_dir, output_dir):
    case = lib.json_load(os.path.join(input_dir, "case.json"), default={}) or {}
    task_path = os.path.join(input_dir, "task.md")
    task_text = lib.read_text(task_path) or ""
    policy = lib.extract_policy(case, task_text)
    return case, task_text, policy


def rel_display(p):
    return p.replace(os.sep, "/")


def choose_dest(rel, ftype, mtime_year):
    parts = rel_display(rel).split("/")
    if len(parts) >= 2:
        project = parts[0]
    else:
        project = "default"
    year = str(mtime_year)
    dest_rel = "/".join([project, year, ftype] + parts[1:])
    return dest_rel


def diff_summary(text_a, text_b, max_lines=2000):
    """两文本差异摘要：新增/删除行数 + 首个差异上下文。"""
    if text_a is None or text_b is None:
        return {"added": None, "removed": None, "note": "非文本或不可读，无法 diff"}
    a = text_a.splitlines()[:max_lines]
    b = text_b.splitlines()[:max_lines]
    added = removed = 0
    first_ctx = None
    for line in difflib.unified_diff(a, b, lineterm="", n=1):
        if line.startswith("+") and not line.startswith("+++"):
            added += 1
            if first_ctx is None:
                first_ctx = line[:200]
        elif line.startswith("-") and not line.startswith("---"):
            removed += 1
            if first_ctx is None:
                first_ctx = line[:200]
    return {"added": added, "removed": removed, "first_change": first_ctx}


def extract_archive(src, dest_dir, rel):
    """stdlib 展开 zip/tar/tar.gz/tgz。返回 (extracted_files, error)。"""
    os.makedirs(dest_dir, exist_ok=True)
    extracted = []
    try:
        lower = src.lower()
        if lower.endswith(".zip"):
            with zipfile.ZipFile(src) as z:
                for info in z.infolist():
                    name = info.filename
                    # zip-slip 防护
                    target = os.path.realpath(os.path.join(dest_dir, name))
                    if not target.startswith(os.path.realpath(dest_dir) + os.sep):
                        return extracted, "zip-slip blocked: %s" % name
                z.extractall(dest_dir)
                extracted = [i.filename for i in z.infolist() if not i.is_dir()]
        elif lower.endswith((".tar", ".tgz", ".tar.gz", ".gz")):
            with tarfile.open(src) as t:
                for m in t.getmembers():
                    target = os.path.realpath(os.path.join(dest_dir, m.name))
                    if not target.startswith(os.path.realpath(dest_dir) + os.sep):
                        return extracted, "tar-slip blocked: %s" % m.name
                t.extractall(dest_dir)
                extracted = [m.name for m in t.getmembers() if m.isfile()]
        else:
            return extracted, "unsupported archive format (stdlib): %s" % rel
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as e:
        return extracted, "extract_failed: %s: %s" % (type(e).__name__, e)
    return extracted, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    input_dir = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)
    library = os.path.join(output_dir, "library")
    os.makedirs(library, exist_ok=True)

    case, task_text, policy = load_context(input_dir, output_dir)
    lib.json_dump({"case": case, "policy": policy},
                  os.path.join(output_dir, "context_snapshot.json"))

    # 账本重建（幂等）
    inventory_path = os.path.join(output_dir, "inventory.jsonl")
    if os.path.exists(inventory_path):
        os.remove(inventory_path)

    records = []
    skipped = []        # 不可读/失败登记
    empty_dirs = []
    extracted_log = []
    seen_dirs_with_files = set()

    for root, dirs, files in os.walk(input_dir):
        rel_root = os.path.relpath(root, input_dir)
        for d in dirs:
            full = os.path.join(root, d)
            rel_d = os.path.normpath(os.path.join(rel_root, d))
            # 空目录登记：现在无文件，稍后二次确认
            try:
                has_any = any(True for _ in os.scandir(full))
            except OSError:
                has_any = True  # 不可判定时不登记空目录
            if not has_any:
                empty_dirs.append(rel_display(rel_d))
        for fn in files:
            rel = os.path.normpath(os.path.join(rel_root, fn))
            rel_disp = rel_display(rel)
            if rel_disp in SKIP_NAMES or rel_disp.startswith(".."):
                continue
            src = os.path.join(input_dir, rel)
            rec = {"source_relpath": rel_disp, "readable": True,
                   "skipped": False, "reason": None}
            if not os.access(src, os.R_OK):
                rec["readable"] = False
                rec["skipped"] = True
                rec["reason"] = "no_read_permission"
                skipped.append(rec)
                lib.jsonl_append(inventory_path, rec)
                continue
            st = None
            try:
                st = os.stat(src)
            except OSError as e:
                rec["readable"] = False
                rec["skipped"] = True
                rec["reason"] = "stat_failed: %s" % e
                skipped.append(rec)
                lib.jsonl_append(inventory_path, rec)
                continue
            rec["size"] = st.st_size
            rec["mtime"] = int(st.st_mtime)
            rec["mode"] = oct(st.st_mode & 0o777)
            rec["ftype"] = lib.file_type(fn)
            digest, err = lib.sha256_file(src)
            if digest is None:
                rec["readable"] = False
                rec["skipped"] = True
                rec["reason"] = err
                skipped.append(rec)
                lib.jsonl_append(inventory_path, rec)
                continue
            rec["sha256"] = digest
            year = time.localtime(st.st_mtime).tm_year
            dest_rel = choose_dest(rel, rec["ftype"], year)
            dest = os.path.join(library, dest_rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            copy_err = None
            if not os.path.exists(dest) or \
                    lib.sha256_file(dest)[0] != digest:
                try:
                    shutil.copy2(src, dest)
                except OSError as e:
                    copy_err = str(e)
            if copy_err:
                rec["readable"] = False
                rec["skipped"] = True
                rec["reason"] = "copy_failed: %s" % copy_err
                skipped.append(rec)
                lib.jsonl_append(inventory_path, rec)
                continue
            rec["library_relpath"] = dest_rel
            rec["is_binary"] = lib.is_binary_path(dest)
            records.append(rec)
            lib.jsonl_append(inventory_path, rec)
            # 登记父链非空
            p = rel_root
            while p and p != ".":
                seen_dirs_with_files.add(p)
                p = os.path.dirname(p)

    # 去重（内容哈希）
    by_hash = {}
    for r in records:
        by_hash.setdefault(r["sha256"], []).append(r)
    duplicates = []
    canonical = {}
    bak_pat = re.compile(r"(\.bak\b|副本|备份|backup|~$)", re.IGNORECASE)

    def canon_key(r):
        # 规范副本优先：非备份名 > 路径字典序
        return (bool(bak_pat.search(os.path.basename(r["library_relpath"]))),
                r["library_relpath"])

    for digest, group in by_hash.items():
        group.sort(key=canon_key)
        canon = group[0]
        canonical[digest] = canon["library_relpath"]
        for g in group[1:]:
            duplicates.append({
                "sha256": digest,
                "duplicate_path": g["library_relpath"],
                "duplicate_source": g["source_relpath"],
                "duplicate_of": canon["library_relpath"],
                "decision": "kept_both_listed",
                "basis": "content_sha256",
            })
    lib.json_dump({"count": len(duplicates), "duplicates": duplicates},
                  os.path.join(output_dir, "duplicates.json"))

    # 版本链（按归一化主干 + 扩展名聚类；mtime 排序）
    groups = {}
    for r in records:
        base = os.path.basename(r["source_relpath"])
        stem_key, ext = lib.norm_stem(base)
        key = (stem_key, ext)
        groups.setdefault(key, []).append(r)
    versions = []
    for key, group in groups.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda r: (r["mtime"], r["library_relpath"]))
        chain = []
        for i, g in enumerate(group):
            entry = {
                "path": g["library_relpath"],
                "sha256": g["sha256"],
                "mtime": g["mtime"],
                "size": g["size"],
            }
            if i < len(group) - 1:
                nxt = group[i + 1]
                entry["superseded_by"] = nxt["library_relpath"]
                ta = lib.read_text(os.path.join(library, g["library_relpath"]))
                tb = lib.read_text(os.path.join(library, nxt["library_relpath"]))
                entry["diff_summary"] = diff_summary(ta, tb)
            chain.append(entry)
        versions.append({"group_key": "%s%s" % key, "chain": chain})
    lib.json_dump({"count": len(versions), "version_chains": versions},
                  os.path.join(output_dir, "versions.json"))

    # 压缩包展开（只对归位后的 archive 类型尝试）
    for r in list(records):
        if r["ftype"] != "archive":
            continue
        ext = os.path.splitext(r["source_relpath"])[1].lower()
        lower = r["source_relpath"].lower()
        if ext not in lib.ARCHIVE_EXTS and \
                not lower.endswith(".tar.gz"):
            extracted_log.append({
                "archive": r["library_relpath"],
                "status": "not_extracted",
                "reason": "unsupported format for stdlib extraction",
                "extracted_count": 0, "files": []})
            continue
        dest_dir = os.path.join(library, "_extracted", r["library_relpath"])
        files_out, err = extract_archive(
            os.path.join(library, r["library_relpath"]), dest_dir,
            r["library_relpath"])
        if err:
            extracted_log.append({
                "archive": r["library_relpath"], "status": "failed",
                "reason": err, "extracted_count": 0, "files": []})
        else:
            extracted_log.append({
                "archive": r["library_relpath"], "status": "ok",
                "reason": None,
                "extracted_count": len(files_out), "files": files_out})
            for f in files_out:
                full = os.path.join(dest_dir, f)
                if not os.path.isfile(full):
                    continue
                digest2, err2 = lib.sha256_file(full)
                lib.jsonl_append(inventory_path, {
                    "source_relpath": r["library_relpath"] + "!/" + f,
                    "library_relpath": "_extracted/" + r["library_relpath"]
                                       + "/" + f,
                    "sha256": digest2,
                    "readable": digest2 is not None,
                    "skipped": False,
                    "extracted_from": r["library_relpath"],
                    "reason": err2})
    lib.json_dump({"archives": extracted_log},
                  os.path.join(output_dir, "extracted.json"))

    # manifest.json / manifest.csv（字段带出处）
    prov = lambda f, v, s, e: {"field": f, "value": v, "source": s,
                               "evidence": e}
    manifest_files = []
    for r in records:
        src_evidence = "organize.py: os.walk(%s)" % r["source_relpath"]
        manifest_files.append({
            "path": r["library_relpath"],
            "size": r["size"],
            "sha256": r["sha256"],
            "type": r["ftype"],
            "is_binary": r["is_binary"],
            "mode": r["mode"],
            "mtime": r["mtime"],
            "provenance": [
                prov("sha256", r["sha256"], "organize.py:sha256_file",
                     src_evidence),
                prov("size", r["size"], "organize.py:os.stat", src_evidence),
                prov("retention", policy["retention"]["value"],
                     policy["retention"]["source"] or "organize.py:default",
                     policy["retention"]["evidence"] or
                     "未在 case.json/task.md 抽到，填 unspecified"),
                prov("access_level", policy["access_level"]["value"],
                     policy["access_level"]["source"] or "organize.py:default",
                     policy["access_level"]["evidence"] or
                     "未在 case.json/task.md 抽到，填 unspecified"),
            ],
        })
    manifest = {
        "generated_by": "organize.py",
        "input_root": input_dir,
        "library_root": library,
        "file_count": len(records),
        "skipped_count": len(skipped),
        "empty_dirs": sorted(empty_dirs),
        "retention": policy["retention"],
        "access_level": policy["access_level"],
        "files": manifest_files,
    }
    lib.json_dump(manifest, os.path.join(output_dir, "manifest.json"))
    with open(os.path.join(output_dir, "manifest.csv"), "w",
              encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["path", "size", "sha256", "type", "mode",
                    "retention", "retention_source",
                    "access_level", "access_level_source"])
        for r in records:
            w.writerow([r["library_relpath"], r["size"], r["sha256"],
                        r["ftype"], r["mode"],
                        policy["retention"]["value"],
                        policy["retention"]["source"] or "unspecified",
                        policy["access_level"]["value"],
                        policy["access_level"]["source"] or "unspecified"])

    report = {
        "files_processed": len(records),
        "skipped": len(skipped),
        "duplicates": len(duplicates),
        "version_chains": len(versions),
        "archives": len(extracted_log),
        "empty_dirs": sorted(empty_dirs),
        "library_root": library,
    }
    lib.json_dump(report, os.path.join(output_dir, "organize_report.json"))
    lib.log("organize: %s" % json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
