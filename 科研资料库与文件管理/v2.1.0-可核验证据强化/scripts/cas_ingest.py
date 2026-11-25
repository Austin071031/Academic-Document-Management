#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step1 cas_ingest：内容寻址入库。

把每个输入文件以 sha256 内容寻址存入
  <output>/library/objects/<sha256前2位>/<sha256>
对象只存一份（硬链接优先、复制兜底），内容相同名字不同的文件天然去重。
同时生成对象账本 <output>/library/objects.jsonl（一行一条 JSON）。

原则：
- 单文件失败不崩溃：捕获、记账、继续。
- 不可读/无权限文件登记 readable=false + 原因，计为"跳过"。
- 符号链接不跟随，登记为 skipped。
- zip/tar 用 stdlib 展开到 work 目录并逐个入库（登记 origin）。
- 空目录也登记。
"""
import argparse
import os
import shutil
import stat
import sys
import tarfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cas_common import (CHUNK, append_jsonl, ensure_dir, is_archive, norm,
                        sha256_file, write_json)

CONTROL_FILES = {"case.json", "task.md"}
MAX_ARCHIVE_DEPTH = 2


def store_object(src_path, digest, objects_dir):
    """把文件存入对象库（已存在则跳过）。返回 (对象路径, 是否新建)。"""
    sub = ensure_dir(os.path.join(objects_dir, digest[:2]))
    dst = os.path.join(sub, digest)
    if os.path.exists(dst):
        return dst, False
    try:
        os.link(src_path, dst)
    except OSError:
        shutil.copy2(src_path, dst)
    try:
        os.chmod(dst, 0o444)  # 对象只读，表达不可变语义（best-effort）
    except OSError:
        pass
    return dst, True


def ingest_file(full_path, display_path, objects_dir, ledger_path,
                origin="direct", role="data"):
    """单文件入库；任何失败都记账而非抛出。返回账本条目。"""
    entry = {"path": norm(display_path), "type": "file",
             "origin": origin, "role": role}
    try:
        st = os.stat(full_path)
        entry["size"] = st.st_size
        entry["mtime"] = st.st_mtime
        entry["permissions"] = oct(stat.S_IMODE(st.st_mode))
    except OSError as e:
        entry.update(readable=False, skipped=True,
                     reason="stat 失败: %s: %s" % (type(e).__name__, e))
        append_jsonl(ledger_path, entry)
        return entry
    try:
        digest = sha256_file(full_path)
    except (PermissionError, OSError) as e:
        entry.update(readable=False, skipped=True,
                     reason="读取失败: %s: %s" % (type(e).__name__, e))
        append_jsonl(ledger_path, entry)
        return entry
    entry["readable"] = True
    entry["sha256"] = digest
    _, created = store_object(full_path, digest, objects_dir)
    entry["object_created"] = created
    append_jsonl(ledger_path, entry)
    return entry


def fix_zip_name(name):
    """老式 zip 未置 UTF-8 标志时成员名被按 cp437 误解码 → 还原 UTF-8。"""
    try:
        return name.encode("cp437").decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return name


def safe_member_name(name):
    """压缩包成员名安全化：去绝对路径与 ..，防目录穿越。"""
    name = norm(name).replace("\\", "/").lstrip("/")
    parts = [p for p in name.split("/") if p not in ("", ".", "..")]
    return "/".join(parts)


def expand_archive(arc_path, dest_root):
    """展开 zip/tar 到 dest_root。返回 (解出文件列表, 错误列表)。坏包不崩溃。"""
    extracted, errors = [], []
    lower = norm(arc_path).lower()
    n = 0
    try:
        if lower.endswith(".zip"):
            with zipfile.ZipFile(arc_path) as zf:
                bad = zf.testzip()
                if bad:
                    errors.append({"archive": norm(arc_path),
                                   "error": "zip CRC 校验失败成员: %s" % bad})
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    rel = safe_member_name(fix_zip_name(info.filename))
                    if not rel:
                        continue
                    dst = os.path.join(dest_root, "%04d_%s"
                                       % (n, rel.replace("/", "__")))
                    n += 1
                    try:
                        with zf.open(info) as src, open(dst, "wb") as out:
                            shutil.copyfileobj(src, out, CHUNK)
                        extracted.append((dst, rel))
                    except Exception as e:  # 单成员失败不拖垮整包
                        errors.append({"archive": norm(arc_path),
                                       "member": rel,
                                       "error": "%s: %s" % (type(e).__name__, e)})
        else:
            with tarfile.open(arc_path) as tf:
                for m in tf.getmembers():
                    if not m.isfile():
                        continue
                    rel = safe_member_name(m.name)
                    if not rel:
                        continue
                    dst = os.path.join(dest_root, "%04d_%s"
                                       % (n, rel.replace("/", "__")))
                    n += 1
                    try:
                        src = tf.extractfile(m)
                        if src is None:
                            continue
                        with src, open(dst, "wb") as out:
                            shutil.copyfileobj(src, out, CHUNK)
                        extracted.append((dst, rel))
                    except Exception as e:
                        errors.append({"archive": norm(arc_path),
                                       "member": rel,
                                       "error": "%s: %s" % (type(e).__name__, e)})
    except (zipfile.BadZipFile, tarfile.TarError, OSError, EOFError,
            ValueError, RuntimeError) as e:
        errors.append({"archive": norm(arc_path),
                       "error": "压缩包无法展开: %s: %s" % (type(e).__name__, e)})
    return extracted, errors


def ingest(input_dir, work_dir, output_dir):
    """全量入库。返回统计 dict。"""
    library = ensure_dir(os.path.join(output_dir, "library"))
    objects_dir = ensure_dir(os.path.join(library, "objects"))
    ledger_path = os.path.join(library, "objects.jsonl")
    if os.path.exists(ledger_path):
        os.remove(ledger_path)
    extract_root = ensure_dir(os.path.join(work_dir, "extracted"))

    stats = {"files_seen": 0, "objects_stored": 0, "dedup_hits": 0,
             "skipped": 0, "dirs": 0, "empty_dirs": 0, "symlinks": 0,
             "archives": 0, "archive_members": 0, "broken_archives": 0,
             "errors": []}

    archive_entries = []
    for root, dirs, files in os.walk(input_dir, followlinks=False):
        dirs.sort()
        files.sort()
        if not dirs and not files:
            stats["empty_dirs"] += 1
            append_jsonl(ledger_path, {
                "path": norm(os.path.relpath(root, input_dir)),
                "type": "dir", "empty": True, "readable": True})
        stats["dirs"] += len(dirs)
        for name in files:
            stats["files_seen"] += 1
            full = os.path.join(root, name)
            rel = norm(os.path.relpath(full, input_dir))
            if os.path.islink(full):
                stats["symlinks"] += 1
                stats["skipped"] += 1
                append_jsonl(ledger_path, {
                    "path": rel, "type": "symlink", "readable": False,
                    "skipped": True, "reason": "符号链接不跟随（安全策略）"})
                continue
            role = "control" if os.path.basename(rel) in CONTROL_FILES \
                and os.sep not in rel else "data"
            entry = ingest_file(full, rel, objects_dir, ledger_path,
                                origin="direct", role=role)
            if entry.get("skipped"):
                stats["skipped"] += 1
                stats["errors"].append({"path": rel,
                                        "reason": entry.get("reason")})
            elif entry.get("object_created"):
                stats["objects_stored"] += 1
            else:
                stats["dedup_hits"] += 1
            if entry.get("readable") and is_archive(rel):
                archive_entries.append((full, rel))

    # 展开压缩包并把成员逐个入库（嵌套包限深）
    queue = [(p, r, 0) for p, r in archive_entries]
    stats["archives"] = len(archive_entries)
    arc_idx = 0
    while queue:
        arc_path, arc_rel, depth = queue.pop(0)
        if depth >= MAX_ARCHIVE_DEPTH:
            stats["errors"].append({"path": arc_rel,
                                    "reason": "嵌套压缩包超过深度限制，未展开"})
            continue
        dest = ensure_dir(os.path.join(extract_root, "arc%03d" % arc_idx))
        arc_idx += 1
        extracted, errors = expand_archive(arc_path, dest)
        stats["errors"].extend(errors)
        if errors and not extracted:
            stats["broken_archives"] += 1
            append_jsonl(ledger_path, {
                "path": arc_rel, "type": "archive", "readable": True,
                "broken": True,
                "reason": "; ".join(e["error"] for e in errors)})
        for member_path, member_rel in extracted:
            stats["archive_members"] += 1
            display = "%s::%s" % (arc_rel, member_rel)
            entry = ingest_file(
                member_path, display, objects_dir, ledger_path,
                origin="archive:%s" % arc_rel, role="data")
            if entry.get("skipped"):
                stats["skipped"] += 1
            elif entry.get("object_created"):
                stats["objects_stored"] += 1
            else:
                stats["dedup_hits"] += 1
            if entry.get("readable") and is_archive(member_rel):
                queue.append((member_path, display, depth + 1))

    stats["errors"] = stats["errors"][:200]
    write_json(os.path.join(work_dir, "ingest_summary.json"), stats)
    return stats


def main():
    ap = argparse.ArgumentParser(description="内容寻址入库")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    s = ingest(a.input, a.work, a.output)
    print("ingest ok: seen=%(files_seen)d stored=%(objects_stored)d "
          "dedup=%(dedup_hits)d skipped=%(skipped)d" % s)


if __name__ == "__main__":
    main()
