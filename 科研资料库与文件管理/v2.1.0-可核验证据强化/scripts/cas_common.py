#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享工具函数（仅 Python3 标准库）。
流式 sha256、JSONL 账本、UTF-8/NFC 文件名安全、文本判定。
"""
import hashlib
import json
import os
import unicodedata

CHUNK = 1024 * 1024  # 1 MiB 流式分块

TEXT_EXTS = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".jsonl",
    ".py", ".r", ".sh", ".bash", ".tex", ".bib", ".xml", ".html",
    ".htm", ".log", ".yaml", ".yml", ".ini", ".cfg", ".sql",
    ".java", ".c", ".h", ".cpp", ".js", ".ts", ".ipynb", ".rst",
}

ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz", ".tar.bz2",
                    ".tbz2", ".tar.xz", ".txz")


def norm(s):
    """文件名/路径统一 NFC 规范化，中文与特殊字符全程安全。"""
    return unicodedata.normalize("NFC", str(s))


def sha256_file(path, limit=None):
    """流式 sha256，1 MiB 分块；limit 限制最多读取字节数。"""
    h = hashlib.sha256()
    read = 0
    with open(path, "rb") as f:
        while True:
            want = CHUNK if limit is None else min(CHUNK, limit - read)
            if want <= 0:
                break
            buf = f.read(want)
            if not buf:
                break
            h.update(buf)
            read += len(buf)
    return h.hexdigest()


def is_archive(name):
    n = norm(name).lower()
    return any(n.endswith(s) for s in ARCHIVE_SUFFIXES)


def is_probably_text(path, sniff=True):
    """按扩展名 + 内容嗅探判定是否为可读文本。"""
    ext = os.path.splitext(norm(path))[1].lower()
    if ext in TEXT_EXTS:
        return True
    if ext and not sniff:
        return False
    try:
        with open(path, "rb") as f:
            chunk = f.read(4096)
    except OSError:
        return False
    if not chunk:
        return True
    if b"\x00" in chunk:
        return False
    try:
        chunk.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def read_text(path, max_bytes=262144):
    """读取文本（截断到 max_bytes），非法字节替换，不抛异常解码错误。"""
    with open(path, "rb") as f:
        data = f.read(max_bytes)
    return data.decode("utf-8", errors="replace")


def read_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def append_jsonl(path, record):
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def load_jsonl(path):
    out = []
    if not os.path.exists(path):
        return out
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    continue
    return out


def ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path
