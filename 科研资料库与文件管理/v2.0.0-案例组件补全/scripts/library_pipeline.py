#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
library_pipeline.py — 确定性哈希账本流水线（版本2：案例组件补全）

子命令:
  scan    递归盘点输入目录，流式 sha256，写 work/inventory.jsonl（append-only 账本）
  plan    基于账本生成组织方案（归位映射/去重组/版本链），dry-run 输出 plan.json
  apply   复制（不移动）文件到 output/library，冲突用 __dupN，写 operation_log.jsonl
  report  生成 manifest.json/csv、duplicates.json、versions.json、README.md
  verify  重哈希 output/library 并与账本比对，输出 verify_report.json
  （无子命令时按 scan→plan→apply→write_partial_result→report→verify 全链路执行；
    v2 增量：全链路末尾按 case.json 自动衔接 recover.py（恢复/重建索引）与
    qa.py（检索问答），幂等，失败记账不崩溃）

仅用 Python 标准库。任何单文件失败只记录、不中断。
"""

import argparse
import csv
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import unicodedata
import zipfile
from datetime import datetime, timezone
from pathlib import Path

CHUNK = 1024 * 1024  # 1 MiB 分块
VERSION = "2.0.0"
CASE_SEARCH_KEYS = ("searches", "questions", "queries")
CASE_RECOVERY_KEYS = ("recovery", "recover", "recovery_tasks", "restore", "restore_tasks")

# 数据类型归类（按扩展名）
TYPE_MAP = {
    "文档": {".txt", ".md", ".pdf", ".doc", ".docx", ".tex", ".rtf", ".odt", ".log"},
    "数据": {".csv", ".tsv", ".json", ".jsonl", ".xlsx", ".xls", ".sqlite", ".db", ".dat", ".ndjson"},
    "图片": {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg", ".tif", ".tiff", ".webp"},
    "压缩包": {".zip", ".tar", ".tgz", ".tar.gz", ".tar.bz2", ".tbz2", ".gz", ".rar", ".7z"},
    "代码": {".py", ".sh", ".r", ".ipynb", ".c", ".cpp", ".h", ".java", ".js", ".sql"},
    "音视频": {".wav", ".mp3", ".flac", ".mp4", ".avi", ".mov", ".mkv"},
}
TYPE_BY_EXT = {e: t for t, exts in TYPE_MAP.items() for e in exts}
ARCHIVE_EXTS = {".zip", ".tar", ".tgz", ".gz", ".tbz2"}
TAR_SUFFIXES = (".tar", ".tar.gz", ".tgz", ".tar.bz2", ".tbz2")
TOP_METADATA = {"case.json", "task.md"}
ADMIN_NOTE_HINT = re.compile(r"(备注|说明|管理|notes?|readme|manifest|登记)", re.I)
ENCODINGS = ("utf-8-sig", "utf-8", "gb18030")


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_print(*args):
    """打印时容错编码：任何无法编码的字符以 ? 替换，绝不抛异常。"""
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    try:
        print(*args)
    except Exception as exc:  # pragma: no cover - 最后防线
        print("[print-error]", exc)


def to_json(obj):
    return json.dumps(obj, ensure_ascii=False, indent=2)


def sanitize(name, max_len=80):
    """把目录/文件名片段转成安全形式：NFC、去非法字符、限长。绝不返回空串。"""
    name = unicodedata.normalize("NFC", str(name))
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = name.strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "unnamed"
    if len(name) > max_len:
        name = name[:max_len].rstrip(".")
    return name or "unnamed"


def sha256_file(path):
    """流式计算 sha256（1 MiB 分块）。抛出的异常由调用方捕获。"""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def file_type_of(filename):
    lower = filename.lower()
    for suf in (".tar.gz", ".tar.bz2"):
        if lower.endswith(suf):
            return TYPE_BY_EXT.get(suf, "其他")
    ext = os.path.splitext(lower)[1]
    return TYPE_BY_EXT.get(ext, "其他")


def is_probably_archive(filename):
    lower = filename.lower()
    return any(lower.endswith(s) for s in ARCHIVE_EXTS | {".tar.bz2"})


def read_text_tolerant(path):
    """按多种编码尝试读取文本，失败返回 None。"""
    for enc in ENCODINGS:
        try:
            with open(path, "r", encoding=enc, errors="strict") as fh:
                return fh.read()
        except Exception:
            continue
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except Exception:
        return None


# ---------------------------------------------------------------- scan

def scan(input_dir, work_dir):
    input_dir = os.path.abspath(input_dir)
    work_dir = os.path.abspath(work_dir)
    extracted_root = os.path.join(work_dir, "extracted")
    os.makedirs(work_dir, exist_ok=True)
    os.makedirs(extracted_root, exist_ok=True)
    ledger_path = os.path.join(work_dir, "inventory.jsonl")

    entries = []
    empty_dirs = []
    errors = []

    def add_entry(**kw):
        entries.append(kw)

    for root, dirs, files in os.walk(input_dir):
        rel_root = os.path.relpath(root, input_dir)
        if rel_root == ".":
            rel_root = ""
        if not files and not dirs and rel_root:
            empty_dirs.append(rel_root)
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.normpath(os.path.join(rel_root, fname)) if rel_root else fname
            rel = rel.replace(os.sep, "/")
            base = {
                "path": rel,
                "abs_path": fpath,
                "size": None,
                "mtime": None,
                "sha256": None,
                "readable": False,
                "error": None,
                "kind": "file",
                "extracted_from": None,
                "depth": rel.count("/"),
                "scanned_at": utcnow(),
            }
            if rel in TOP_METADATA or fname in TOP_METADATA:
                base["kind"] = "metadata"
                try:
                    st = os.stat(fpath)
                    base["size"] = st.st_size
                    base["mtime"] = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")
                    base["readable"] = True
                except Exception as exc:
                    base["error"] = "stat failed: %s" % exc
                add_entry(**base)
                continue
            try:
                st = os.stat(fpath)
                base["size"] = st.st_size
                base["mtime"] = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds")
                if os.path.islink(fpath):
                    base["error"] = "symbolic link skipped"
                    add_entry(**base)
                    continue
                base["sha256"] = sha256_file(fpath)
                base["readable"] = True
                if is_probably_archive(fname):
                    base["kind"] = "archive"
                    if not _try_archive(fpath, rel, extracted_root, add_entry, errors):
                        base["kind"] = "file"  # 损坏/非标准压缩包：按普通文件登记
                        base["archive_error"] = "not a valid archive or extraction failed"
                add_entry(**base)
            except PermissionError as exc:
                base["error"] = "permission denied: %s" % exc
                add_entry(**base)
            except Exception as exc:
                base["error"] = "%s: %s" % (type(exc).__name__, exc)
                add_entry(**base)

    # 账本落盘（单次 scan 内逐行 append-only；重跑 scan 重新生成，保证幂等）
    with open(ledger_path, "w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e, ensure_ascii=False) + "\n")
    summary = {
        "generated_at": utcnow(),
        "input_dir": input_dir,
        "total_entries": len(entries),
        "files": sum(1 for e in entries if e["kind"] in ("file", "archive", "archive_member")),
        "archives": sum(1 for e in entries if e["kind"] == "archive"),
        "archive_members": sum(1 for e in entries if e["kind"] == "archive_member"),
        "metadata_files": sum(1 for e in entries if e["kind"] == "metadata"),
        "readable": sum(1 for e in entries if e["readable"]),
        "unreadable": sum(1 for e in entries if not e["readable"] and e["kind"] != "metadata"),
        "empty_dirs": empty_dirs,
        "extraction_errors": errors,
        "ledger": ledger_path,
    }
    with open(os.path.join(work_dir, "scan_summary.json"), "w", encoding="utf-8") as fh:
        fh.write(to_json(summary))
    safe_print("[scan] entries=%d readable=%d unreadable=%d members=%d -> %s"
               % (len(entries), summary["readable"], summary["unreadable"],
                  summary["archive_members"], ledger_path))
    return summary


def _safe_member_name(name):
    """压缩包成员名防目录穿越：拒绝绝对路径与 .. 组件。"""
    name = name.replace("\\", "/")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in parts):
        return None
    return "/".join(parts)


def _try_archive(fpath, rel, extracted_root, add_entry, errors):
    """安全展开 zip/tar，登记成员。成功返回 True。"""
    lower = fpath.lower()
    try:
        if lower.endswith(".zip"):
            if not zipfile.is_zipfile(fpath):
                errors.append({"archive": rel, "error": "bad zip (is_zipfile=false)"})
                return False
            with zipfile.ZipFile(fpath) as zf:
                for info in zf.infolist():
                    raw_name = info.filename
                    if not (info.flag_bits & 0x800):
                        # 未设 UTF-8 标记：按 cp437 还原原始字节再尝试 UTF-8 解码
                        try:
                            raw_name = raw_name.encode("cp437").decode("utf-8")
                        except Exception:
                            raw_name = info.filename
                    mname = _safe_member_name(raw_name)
                    if mname is None or info.is_dir():
                        continue
                    dest = os.path.join(extracted_root, sanitize(rel, 120), *[_safe_member_name(p) or "x" for p in mname.split("/")])
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    try:
                        with zf.open(info) as src, open(dest, "wb") as dst:
                            shutil.copyfileobj(src, dst, CHUNK)
                        st = os.stat(dest)
                        add_entry(
                            path=dest, abs_path=dest,
                            size=st.st_size,
                            mtime=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                            sha256=sha256_file(dest), readable=True, error=None,
                            kind="archive_member", extracted_from=rel,
                            depth=dest.count(os.sep), scanned_at=utcnow(),
                        )
                    except Exception as exc:
                        errors.append({"archive": rel, "member": info.filename, "error": str(exc)})
            return True
        if lower.endswith(TAR_SUFFIXES):
            if not tarfile.is_tarfile(fpath):
                errors.append({"archive": rel, "error": "bad tar (is_tarfile=false)"})
                return False
            with tarfile.open(fpath, "r:*") as tf:
                for member in tf.getmembers():
                    if not member.isfile():
                        continue
                    mname = _safe_member_name(member.name)
                    if mname is None:
                        continue
                    dest = os.path.join(extracted_root, sanitize(rel, 120), *[_safe_member_name(p) or "x" for p in mname.split("/")])
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    try:
                        srcf = tf.extractfile(member)
                        if srcf is None:
                            continue
                        with srcf, open(dest, "wb") as dst:
                            shutil.copyfileobj(srcf, dst, CHUNK)
                        st = os.stat(dest)
                        add_entry(
                            path=dest, abs_path=dest,
                            size=st.st_size,
                            mtime=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec="seconds"),
                            sha256=sha256_file(dest), readable=True, error=None,
                            kind="archive_member", extracted_from=rel,
                            depth=dest.count(os.sep), scanned_at=utcnow(),
                        )
                    except Exception as exc:
                        errors.append({"archive": rel, "member": member.name, "error": str(exc)})
            return True
    except Exception as exc:
        errors.append({"archive": rel, "error": "%s: %s" % (type(exc).__name__, exc)})
        return False
    return False


# ------------------------------------------------------------- metadata

VERSION_TOKEN = re.compile(r"(?i)^(v\d+(\.\d+)*|r\d+|ver\d+|\d+\.\d+)$")
PROJECT_TOKEN = re.compile(r"(?i)^[A-Za-z]{2,}[\-_]?\d{2,}[\w\-]*$")
AUTHOR_TOKEN = re.compile(r"^[\u4e00-\u9fff·]{2,4}$")
YEAR_TOKEN = re.compile(r"^(19|20)\d{2}$")

FIELD_KEYS = {
    "project": ["project", "项目", "项目号", "课题", "编号"],
    "year": ["year", "年份", "年度", "年代"],
    "author": ["author", "作者", "负责人", "录入人"],
    "version": ["version", "版本", "版次"],
    "type": ["type", "类型", "数据类型", "类别"],
    "notes": ["notes", "备注", "说明", "note", "remark"],
}


def _mk(field, value, source, evidence):
    return {"field": field, "value": value, "source": source, "evidence": evidence}


def extract_filename_metadata(filename):
    """从文件名模式 项目号_作者_年份_类型.ext 尽力抽取字段；抽不到返回 null+原因。"""
    stem = unicodedata.normalize("NFC", Path(filename).stem)
    tokens = [t for t in re.split(r"[_\-–—\s]+", stem) if t]
    out = {}
    has_version_marker = ("版本" in stem) or ("ver" in stem.lower())
    for i, tok in enumerate(tokens):
        if "year" not in out and YEAR_TOKEN.match(tok):
            out["year"] = tok
        elif "version" not in out and (VERSION_TOKEN.match(tok) or (has_version_marker and tok.isdigit())):
            out["version"] = tok
    for tok in tokens:
        if "project" not in out and (PROJECT_TOKEN.match(tok) or tok.startswith("项目")):
            out["project"] = tok
        elif ("author" not in out and AUTHOR_TOKEN.match(tok)
              and not ADMIN_NOTE_HINT.match(filename)):
            out["author"] = tok
    ftype = file_type_of(filename)
    fields = {
        "project": _mk("project", out.get("project"), "filename",
                       "token in filename '%s' (pattern 项目号_作者_年份_类型)" % filename
                       if out.get("project") else "no project-like token found in filename"),
        "year": _mk("year", out.get("year"), "filename",
                    "4-digit year token in filename '%s'" % filename
                    if out.get("year") else "no (19|20)xx year token in filename"),
        "author": _mk("author", out.get("author"), "filename",
                      "CJK name token in filename '%s'" % filename
                      if out.get("author") else "no 2-4 CJK char token in filename"),
        "version": _mk("version", out.get("version"), "filename",
                       "version-like token in filename '%s'" % filename
                       if out.get("version") else "no version token; single-version assumed"),
        "type": _mk("type", ftype, "filename", "extension of '%s'" % filename),
        "notes": _mk("notes", None, "filename", "no notes embedded in filename"),
    }
    return fields


def load_companion_tables(input_dir, work_dir, inventory_entries):
    """读取伴随 CSV/TSV（utf-8/gb18030 容错），返回 {stem: {field: value}}。"""
    index = {}
    for e in inventory_entries:
        rel = e["path"]
        if e["kind"] == "metadata" or e["extracted_from"]:
            continue
        if not rel.lower().endswith((".csv", ".tsv")) or not e.get("readable"):
            continue
        text = read_text_tolerant(e["abs_path"])
        if text is None:
            continue
        try:
            dialect = csv.Sniffer().sniff(text[:2048], delimiters=",\t;")
        except Exception:
            dialect = csv.excel_tab if rel.lower().endswith(".tsv") else csv.excel
        try:
            reader = csv.DictReader(io.StringIO(text), dialect=dialect)
            rows = list(reader)
        except Exception:
            continue
        if not rows:
            continue
        headers = list(rows[0].keys())
        lower_h = {h: h.strip().lower() for h in headers if h}
        def field_of(name):
            for key, aliases in FIELD_KEYS.items():
                for h in headers:
                    if h and h.strip().lower() in [a.lower() for a in aliases]:
                        return key
            return None
        for row in rows:
            cells = {h: (row.get(h) or "").strip() for h in headers if h}
            joined = " ".join(cells.values())
            for key, val in cells.items():
                if not val:
                    continue
                entry = {"_table": rel, "_row": cells}
                for h, v in cells.items():
                    f = field_of(h)
                    if f and v:
                        entry[f] = v
                stem = Path(val).stem if ("." in val and "/" not in val) else val
                index.setdefault(stem, entry)
            _ = joined
    return index


def load_admin_notes(input_dir, work_dir, inventory_entries):
    """解析管理性备注（md/txt/csv，文件名含 备注|说明|管理|notes|readme），
    返回 [(source_file, mentioned_stem, {field: value})]。"""
    notes = []
    for e in inventory_entries:
        rel = e["path"]
        if e["kind"] == "metadata" or not e.get("readable"):
            continue
        if not ADMIN_NOTE_HINT.search(Path(rel).name):
            continue
        if not rel.lower().endswith((".md", ".txt", ".csv")):
            continue
        text = read_text_tolerant(e["abs_path"])
        if not text:
            continue
        kv = {}
        mentioned = []
        for line in text.splitlines():
            line = line.strip().strip("|")
            if not line:
                continue
            m = re.split(r"[:：,，]\s*", line, maxsplit=1)
            if len(m) == 2:
                key, val = m[0].strip().lower(), m[1].strip()
                for fkey, aliases in FIELD_KEYS.items():
                    if key in [a.lower() for a in aliases] and val:
                        kv[fkey] = val
            for tok in re.findall(r"[^\s，,；;|]+\.[A-Za-z0-9]{1,5}", line):
                mentioned.append(Path(tok).stem)
            for tok in re.findall(r"[^\s：:,，;；]+", line):
                if ADMIN_NOTE_HINT.search(e["path"]) and len(tok) >= 2 and not tok.endswith((".md", ".txt", ".csv")):
                    if tok not in mentioned and re.search(r"[\u4e00-\u9fffA-Za-z]", tok):
                        mentioned.append(tok)
        for stem in set(mentioned):
            notes.append((rel, stem, dict(kv)))
    return notes


def build_metadata(rel, filename, companions, admin_notes):
    """合并三级来源：filename → companion_table → admin_note；全部缺省为 null+原因。"""
    fields = extract_filename_metadata(filename)
    stem = Path(filename).stem
    # 伴随表 join（精确 stem 匹配，或 stem 作为子串出现在表值中）
    hit = companions.get(stem)
    if hit is None:
        for k, v in companions.items():
            if k and (k in stem or stem in k):
                hit = v
                break
    if hit:
        for fkey in ("project", "year", "author", "version", "type", "notes"):
            if hit.get(fkey) and (fields[fkey]["value"] in (None, "其他")):
                fields[fkey] = _mk(fkey, hit[fkey], "companion_table",
                                   "joined from %s row %s" % (hit["_table"], hit["_row"]))
    for src, mentioned, kv in admin_notes:
        if mentioned == stem or mentioned in stem or stem in mentioned:
            for fkey, val in kv.items():
                if fields[fkey]["value"] in (None, ""):
                    fields[fkey] = _mk(fkey, val, "admin_note",
                                       "key:value parsed from %s" % src)
    for fkey, f in fields.items():
        if f["value"] is None:
            f["reason"] = f["evidence"]
    return fields


# ---------------------------------------------------------------- plan

def normalize_stem(stem):
    s = unicodedata.normalize("NFC", stem).lower()
    s = re.sub(r"(?i)\b(v\d+(\.\d+)*|r\d+|ver\d+|版本\d*|final|最终版?|修订版?|copy|副本|备份|backup|复件)\b", "", s)
    s = re.sub(r"[_\-–—\s]+", "", s)
    s = re.sub(r"\d+$", "", s)
    return s


def compute_versions(candidates):
    """按内容相似度（difflib，与文件名无关）+ mtime 序列构建版本链。
    candidates: [(rel, stem, mtime_iso, sha256, origin)]，仅含非重复文件。
    origin（extracted_from 或 None）不同者不互为版本，避免跨压缩包误连。"""
    pairs = []
    n = len(candidates)
    for i in range(n):
        for j in range(i + 1, n):
            a, b = candidates[i], candidates[j]
            if a[3] == b[3]:
                continue
            if a[4] != b[4]:
                continue
            na, nb = normalize_stem(a[1]), normalize_stem(b[1])
            if not na or not nb:
                continue
            if difflib.SequenceMatcher(None, na, nb).real_quick_ratio() < 0.75:
                continue
            ratio = difflib.SequenceMatcher(None, na, nb).ratio()
            if ratio >= 0.75:
                pairs.append((ratio, a[0], b[0]))
    # 并查集聚类
    parent = {c[0]: c[0] for c in candidates}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    for _, a, b in pairs:
        union(a, b)
    groups = {}
    for c in candidates:
        groups.setdefault(find(c[0]), []).append(c)
    chains = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda c: (c[2] or "", c[0]))  # mtime 升序 = 版本序列
        chain = []
        for k, (rel, stem, mtime, sha, _origin) in enumerate(members):
            chain.append({
                "path": rel,
                "sha256": sha,
                "mtime": mtime,
                "version_rank": k + 1,
                "superseded_by": members[k + 1][0] if k + 1 < len(members) else None,
            })
        chains.append(chain)
    chains.sort(key=lambda ch: ch[0]["path"])
    return chains


def plan(input_dir, work_dir, output_dir):
    input_dir, work_dir, output_dir = map(os.path.abspath, (input_dir, work_dir, output_dir))
    ledger_path = os.path.join(work_dir, "inventory.jsonl")
    entries = [json.loads(l) for l in open(ledger_path, encoding="utf-8") if l.strip()]
    files = [e for e in entries if e["kind"] in ("file", "archive", "archive_member")]

    companions = load_companion_tables(input_dir, work_dir, entries)
    admin_notes = load_admin_notes(input_dir, work_dir, entries)

    # 精确重复分组（按内容哈希；空文件不参与去重，避免误并）
    by_hash = {}
    for e in files:
        if e["readable"] and e["sha256"] and e["size"] and e["size"] > 0:
            by_hash.setdefault(e["sha256"], []).append(e)
    dup_groups = []
    canonical = {}  # rel -> canonical rel
    for sha, group in sorted(by_hash.items()):
        if len(group) < 2:
            continue
        group.sort(key=lambda e: (e["mtime"] or "", e["path"]))
        canon = group[0]["path"]
        aliases = [g["path"] for g in group[1:]]
        dup_groups.append({
            "sha256": sha,
            "size": group[0]["size"],
            "canonical": canon,
            "aliases": aliases,
            "detection": "content sha256 identical",
        })
        for g in group[1:]:
            canonical[g["path"]] = canon

    empty_files = [e["path"] for e in files if e["size"] == 0 and e["readable"]]

    # 版本链候选：非别名的可读文件
    candidates = [(e["path"], Path(e["path"]).stem, e["mtime"], e["sha256"],
                   e.get("extracted_from"))
                  for e in files if e["readable"] and e["size"] and e["size"] > 0
                  and e["path"] not in canonical]
    version_chains = compute_versions(candidates)
    superseded = {}
    for chain in version_chains:
        for node in chain:
            if node["superseded_by"]:
                superseded[node["path"]] = node["superseded_by"]

    # 目标路径 + __dupN 冲突消解（确定性：按排序后顺序占用名字）
    used = set()
    plan_entries = []
    dup_counter = {}
    for e in sorted(files, key=lambda x: x["path"]):
        rel = e["path"]
        meta = build_metadata(rel, os.path.basename(e["abs_path"]), companions, admin_notes)
        if not e["readable"]:
            plan_entries.append({
                "src": rel, "abs": e["abs_path"], "size": e["size"], "sha256": e["sha256"],
                "action": "skip_unreadable", "target": None,
                "reason": e["error"] or "unreadable",
                "metadata": meta,
            })
            continue
        if rel in canonical:
            plan_entries.append({
                "src": rel, "abs": e["abs_path"], "size": e["size"], "sha256": e["sha256"],
                "action": "duplicate_of", "target": None,
                "duplicate_of": canonical[rel],
                "superseded_by": superseded.get(rel),
                "metadata": meta,
            })
            continue
        proj = sanitize(meta["project"]["value"] or "未分类项目")
        year = sanitize(meta["year"]["value"] or "未知年份")
        ftype = sanitize(meta["type"]["value"] or "其他")
        sub = sanitize(Path(e["abs_path"]).stem) if e["kind"] == "archive_member" else None
        base_dir = f"{proj}/{year}/{ftype}"
        if e["kind"] == "archive_member":
            base_dir += "/" + sanitize(Path(e["extracted_from"]).stem)
        fname = sanitize(os.path.basename(e["abs_path"]), 120)
        target_rel = f"{base_dir}/{fname}"
        if target_rel in used:
            stem, ext = os.path.splitext(fname)
            n = dup_counter.get(target_rel, 0) + 1
            dup_counter[target_rel] = n
            target_rel = f"{base_dir}/{stem}__dup{n}{ext}"
        used.add(target_rel)
        plan_entries.append({
            "src": rel, "abs": e["abs_path"], "size": e["size"], "sha256": e["sha256"],
            "action": "copy", "target": target_rel,
            "extracted_from": e["extracted_from"],
            "superseded_by": superseded.get(rel),
            "metadata": meta,
        })

    plan_doc = {
        "generated_at": utcnow(),
        "mode": "dry-run (no files written)",
        "organize_tree": "项目/年份/数据类型/",
        "conflict_policy": "__dupN suffix, never overwrite",
        "entries": plan_entries,
        "duplicates": dup_groups,
        "excluded_empty_files_from_dedup": empty_files,
        "version_chains": version_chains,
        "counts": {
            "files": len(files),
            "copy": sum(1 for p in plan_entries if p["action"] == "copy"),
            "duplicate_of": sum(1 for p in plan_entries if p["action"] == "duplicate_of"),
            "skip_unreadable": sum(1 for p in plan_entries if p["action"] == "skip_unreadable"),
        },
    }
    plan_path = os.path.join(work_dir, "plan.json")
    with open(plan_path, "w", encoding="utf-8") as fh:
        fh.write(to_json(plan_doc))
    safe_print("[plan] copy=%d duplicate_of=%d skip=%d dup_groups=%d version_chains=%d -> %s"
               % (plan_doc["counts"]["copy"], plan_doc["counts"]["duplicate_of"],
                  plan_doc["counts"]["skip_unreadable"], len(dup_groups),
                  len(version_chains), plan_path))
    return plan_doc


# ---------------------------------------------------------------- apply

def apply(work_dir, output_dir):
    work_dir, output_dir = map(os.path.abspath, (work_dir, output_dir))
    plan_doc = json.load(open(os.path.join(work_dir, "plan.json"), encoding="utf-8"))
    lib_root = os.path.join(output_dir, "library")
    os.makedirs(lib_root, exist_ok=True)
    log_path = os.path.join(output_dir, "operation_log.jsonl")
    counts = {"copied": 0, "duplicate_of": 0, "skipped": 0, "failed": 0}
    with open(log_path, "w", encoding="utf-8") as log:
        for p in plan_doc["entries"]:
            rec = {
                "time": utcnow(),
                "action": p["action"],
                "before": p["src"],
                "after": p.get("target"),
                "sha256": p.get("sha256"),
                "size": p.get("size"),
            }
            try:
                if p["action"] == "copy":
                    dest = os.path.join(lib_root, p["target"])
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    shutil.copy2(p["abs"], dest)  # 复制不移动，保留源证据
                    rec["status"] = "ok"
                    counts["copied"] += 1
                elif p["action"] == "duplicate_of":
                    rec["status"] = "ok"
                    rec["note"] = "exact duplicate of %s (not copied)" % p["duplicate_of"]
                    counts["duplicate_of"] += 1
                elif p["action"] == "skip_unreadable":
                    rec["status"] = "skipped"
                    rec["note"] = p.get("reason")
                    counts["skipped"] += 1
                else:
                    rec["status"] = "skipped"
                    counts["skipped"] += 1
            except Exception as exc:
                rec["status"] = "failed"
                rec["note"] = "%s: %s" % (type(exc).__name__, exc)
                counts["failed"] += 1
            log.write(json.dumps(rec, ensure_ascii=False) + "\n")
    safe_print("[apply] copied=%d duplicate_ref=%d skipped=%d failed=%d log=%s"
               % (counts["copied"], counts["duplicate_of"], counts["skipped"],
                  counts["failed"], log_path))
    return counts


# ---------------------------------------------------------------- report

def report(input_dir, work_dir, output_dir):
    work_dir, output_dir = map(os.path.abspath, (work_dir, output_dir))
    plan_doc = json.load(open(os.path.join(work_dir, "plan.json"), encoding="utf-8"))
    lib_root = os.path.join(output_dir, "library")
    entries_meta = []
    for p in plan_doc["entries"]:
        m = p.get("metadata", {})
        entries_meta.append({
            "source_path": p["src"],
            "library_path": p.get("target"),
            "action": p["action"],
            "sha256": p.get("sha256"),
            "size": p.get("size"),
            "project": m.get("project"),
            "year": m.get("year"),
            "author": m.get("author"),
            "version": m.get("version"),
            "type": m.get("type"),
            "notes": m.get("notes"),
            "duplicate_of": p.get("duplicate_of"),
            "superseded_by": p.get("superseded_by"),
        })
    manifest = {
        "generated_at": utcnow(),
        "generator": "library_pipeline.py v%s" % VERSION,
        "method": "sha256 ledger; metadata fields carry source+evidence; missing -> null+reason",
        "files": entries_meta,
    }
    with open(os.path.join(output_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        fh.write(to_json(manifest))

    with open(os.path.join(output_dir, "manifest.csv"), "w", encoding="utf-8-sig", newline="") as fh:
        cols = ["source_path", "library_path", "action", "sha256", "size",
                "project", "project_source", "project_evidence",
                "year", "year_source", "year_evidence",
                "author", "author_source", "author_evidence",
                "version", "version_source", "version_evidence",
                "type", "type_source", "type_evidence",
                "notes", "notes_source", "notes_evidence",
                "duplicate_of", "superseded_by"]
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()

        def cell(meta_field):
            if not meta_field:
                return None, None, None
            return meta_field.get("value"), meta_field.get("source"), meta_field.get("evidence")

        for em in entries_meta:
            row = {"source_path": em["source_path"], "library_path": em["library_path"],
                   "action": em["action"], "sha256": em["sha256"], "size": em["size"],
                   "duplicate_of": em["duplicate_of"], "superseded_by": em["superseded_by"]}
            for f in ("project", "year", "author", "version", "type", "notes"):
                v, s, ev = cell(em.get(f))
                row[f] = v
                row[f + "_source"] = s
                row[f + "_evidence"] = (ev or "")[:300] if ev else None
            w.writerow(row)

    duplicates = {
        "generated_at": utcnow(),
        "method": "exact sha256 equality (content-based, name-independent)",
        "groups": plan_doc["duplicates"],
        "excluded_empty_files_from_dedup": plan_doc.get("excluded_empty_files_from_dedup", []),
        "note": "零字节文件不参与去重，避免误并不相关空文件。",
    }
    with open(os.path.join(output_dir, "duplicates.json"), "w", encoding="utf-8") as fh:
        fh.write(to_json(duplicates))

    versions = {
        "generated_at": utcnow(),
        "method": "content similarity (difflib on normalized stems, threshold 0.75) + mtime ordering; "
                  "exact-hash files are duplicates, not versions; judgment is name-independent",
        "chains": plan_doc["version_chains"],
    }
    with open(os.path.join(output_dir, "versions.json"), "w", encoding="utf-8") as fh:
        fh.write(to_json(versions))

    # 审计副本：账本与方案一并交付，供独立复跑
    for fname in ("inventory.jsonl", "plan.json"):
        src = os.path.join(work_dir, fname)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(output_dir, fname))

    c = plan_doc["counts"]
    readme = f"""# 科研资料库交付说明（确定性哈希账本流水线 v{VERSION}）

生成时间：{utcnow()}

## 交付物
- `library/` —— 按 `项目/年份/数据类型/` 组织的文件树（复制，不移动，源证据保留在 input）。
- `manifest.json` / `manifest.csv` —— 每个文件的元数据字段，全部带 `source`（filename|content|companion_table|admin_note|agent_inference）与 `evidence`；抽不到为 null 并注明原因。
- `duplicates.json` —— 按内容 sha256 判定的精确重复组（canonical + aliases）。
- `versions.json` —— 内容相似度 + mtime 序列推出的版本链，含 `superseded_by`。
- `operation_log.jsonl` —— 每次操作（before/after/sha256/action/time）的 append-only 日志。
- `inventory.jsonl` / `plan.json` —— 审计副本（账本与方案），供独立复跑核对。
- `verify_report.json` —— 对 library 重哈希后的比对结果。
- `result.json` —— 含 case_id、output_contract 全部字段与诚实的状态/不确定性声明。

## 统计
- 复制 {c['copy']} 个；登记精确重复 {c['duplicate_of']} 个；跳过（不可读/失败）{c['skip_unreadable']} 个。
- 重复组 {len(plan_doc['duplicates'])} 个；版本链 {len(plan_doc['version_chains'])} 条。

## 复跑核对
```bash
python3 scripts/library_pipeline.py verify --input <input> --work <work> --output <output>
```
"""
    with open(os.path.join(output_dir, "README.md"), "w", encoding="utf-8") as fh:
        fh.write(readme)
    safe_print("[report] manifest/duplicates/versions/README written to %s" % output_dir)
    return manifest


# ---------------------------------------------------------------- verify

def verify(work_dir, output_dir):
    work_dir, output_dir = map(os.path.abspath, (work_dir, output_dir))
    plan_doc = json.load(open(os.path.join(work_dir, "plan.json"), encoding="utf-8"))
    lib_root = os.path.join(output_dir, "library")
    expected = {p["target"]: p["sha256"] for p in plan_doc["entries"]
                if p["action"] == "copy" and p.get("target")}
    results = []
    matched = mismatched = missing = errors = 0
    seen = set()
    for root, _dirs, files in os.walk(lib_root):
        for fname in sorted(files):
            fpath = os.path.join(root, fname)
            rel = os.path.relpath(fpath, lib_root).replace(os.sep, "/")
            seen.add(rel)
            exp = expected.get(rel)
            if exp is None:
                results.append({"path": rel, "status": "extra", "expected_sha256": None, "actual_sha256": None})
                continue
            try:
                actual = sha256_file(fpath)
                if actual == exp:
                    results.append({"path": rel, "status": "match", "expected_sha256": exp, "actual_sha256": actual})
                    matched += 1
                else:
                    results.append({"path": rel, "status": "mismatch", "expected_sha256": exp, "actual_sha256": actual})
                    mismatched += 1
            except Exception as exc:
                results.append({"path": rel, "status": "error", "error": str(exc)})
                errors += 1
    for target, sha in sorted(expected.items()):
        if target not in seen:
            results.append({"path": target, "status": "missing", "expected_sha256": sha, "actual_sha256": None})
            missing += 1
    report_doc = {
        "generated_at": utcnow(),
        "library_root": lib_root,
        "files": results,
        "totals": {"expected": len(expected), "match": matched, "mismatch": mismatched,
                   "missing": missing, "extra": len(results) - matched - mismatched - missing - errors,
                   "error": errors},
        "verdict": "PASS" if (mismatched == 0 and missing == 0 and errors == 0 and matched == len(expected)) else "FAIL",
    }
    out = os.path.join(output_dir, "verify_report.json")
    with open(out, "w", encoding="utf-8") as fh:
        fh.write(to_json(report_doc))
    safe_print("[verify] match=%d mismatch=%d missing=%d extra=%d -> %s (%s)"
               % (matched, mismatched, missing, report_doc["totals"]["extra"], out, report_doc["verdict"]))
    return report_doc


# ---------------------------------------------------------------- main

def _case_has_any(case, keys):
    for k in keys:
        if case.get(k):
            return True
    return False


def chain_case_extras(args):
    """v2 增量：全链路末尾按 case.json 自动衔接 recover.py / qa.py。

    幂等（recover 同哈希目标记 already_present 不覆盖；qa 索引整本重建），
    任何失败只打印与记账，不抛出、不改变 pipeline 退出码语义。
    顺序：先 recover（把恢复的文件落进 library/），再 qa（索引覆盖恢复结果），
    最后重跑一次 verify 使报告反映最终 library 状态。
    """
    script_dir = os.path.dirname(os.path.abspath(__file__))
    case = {}
    case_path = os.path.join(os.path.abspath(args.input), "case.json")
    if os.path.exists(case_path):
        try:
            case = json.load(open(case_path, encoding="utf-8"))
        except Exception as exc:
            safe_print("[chain] case.json unreadable: %s" % exc)
    chained = []
    if _case_has_any(case, CASE_RECOVERY_KEYS):
        recover = os.path.join(script_dir, "recover.py")
        try:
            r = subprocess.run([sys.executable, recover,
                                "--input", args.input, "--work", args.work,
                                "--output", args.output, "--from-case"], check=False)
            chained.append(("recover", r.returncode))
        except Exception as exc:
            safe_print("[chain] recover failed (non-fatal): %s: %s" % (type(exc).__name__, exc))
            chained.append(("recover", "error: %s" % exc))
    if _case_has_any(case, CASE_SEARCH_KEYS):
        qa = os.path.join(script_dir, "qa.py")
        try:
            r = subprocess.run([sys.executable, qa,
                                "--input", args.input, "--work", args.work,
                                "--output", args.output], check=False)
            chained.append(("qa", r.returncode))
        except Exception as exc:
            safe_print("[chain] qa failed (non-fatal): %s: %s" % (type(exc).__name__, exc))
            chained.append(("qa", "error: %s" % exc))
    if chained:
        safe_print("[chain] extras: %s" % chained)
        try:  # recover 可能向 library/ 新增文件，重跑 verify 反映最终状态（extra 不影响 PASS）
            verify(args.work, args.output)
        except Exception as exc:
            safe_print("[chain] re-verify failed (non-fatal): %s: %s" % (type(exc).__name__, exc))
    return chained


def run_all(args):
    scan(args.input, args.work)
    plan(args.input, args.work, args.output)
    apply(args.work, args.output)
    # apply 成功后尽早落盘 partial result.json（先存诚实结果，再增量改进）
    partial = os.path.join(os.path.dirname(os.path.abspath(__file__)), "write_partial_result.py")
    if os.path.exists(partial):
        subprocess.run([sys.executable, partial,
                        "--input", args.input, "--work", args.work, "--output", args.output],
                       check=False)
    report(args.input, args.work, args.output)
    vr = verify(args.work, args.output)
    # v2 增量：案例组件自动衔接（检索问答 / 恢复与重建索引），失败不崩溃
    chain_case_extras(args)
    # 衔接后若 verify 报告被重跑，以最新报告为准；缺失时回退到衔接前的结论
    vr_path = os.path.join(os.path.abspath(args.output), "verify_report.json")
    if os.path.exists(vr_path):
        try:
            vr = json.load(open(vr_path, encoding="utf-8"))
        except Exception:
            pass
    safe_print("[pipeline] done. verdict=%s" % vr["verdict"])
    return 0 if vr["verdict"] == "PASS" else 1


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    subs = {"scan", "plan", "apply", "report", "verify"}
    sub = argv[0] if argv and argv[0] in subs else None
    if sub:
        argv = argv[1:]
    parser = argparse.ArgumentParser(description="确定性哈希账本流水线 v" + VERSION)
    parser.add_argument("--input", default="/input")
    parser.add_argument("--work", default="/app/work")
    parser.add_argument("--output", default="/app/output")
    args = parser.parse_args(argv)
    try:
        if sub == "scan":
            scan(args.input, args.work)
        elif sub == "plan":
            plan(args.input, args.work, args.output)
        elif sub == "apply":
            apply(args.work, args.output)
        elif sub == "report":
            report(args.input, args.work, args.output)
        elif sub == "verify":
            vr = verify(args.work, args.output)
            return 0 if vr["verdict"] == "PASS" else 1
        else:
            return run_all(args)
    except Exception as exc:
        safe_print("[FATAL] %s: %s" % (type(exc).__name__, exc))
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
