#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共享工具库：流式哈希、安全路径、JSON IO、六要素抽取。

仅使用 Python 3 标准库。所有函数对单文件失败不崩溃，错误以
(reason, exception) 形式返回或登记。
"""
import hashlib
import json
import os
import re
import sys

CHUNK = 1024 * 1024  # 1 MiB 分块


def sha256_file(path, chunk=CHUNK):
    """流式计算 sha256。失败返回 (None, reason)。"""
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(chunk)
                if not b:
                    break
                h.update(b)
        return h.hexdigest(), None
    except OSError as e:
        return None, "sha256_failed: %s" % e


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def json_dump(obj, path):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, path)


def json_load(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def jsonl_append(path, record):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


def read_text(path, limit=2 * 1024 * 1024):
    """读取文本，失败返回 None。限幅防止超大文件撑爆内存。"""
    try:
        with open(path, "rb") as f:
            data = f.read(limit + 1)
        if len(data) > limit:
            data = data[:limit]
        return data.decode("utf-8", errors="replace")
    except OSError:
        return None


def is_binary_path(path):
    """读前 8192 字节判断是否含 NUL。失败按二进制处理（安全默认）。"""
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
        if b"\x00" in head:
            return True
        # 含大量不可打印字符也视为二进制
        if head:
            bad = sum(1 for b in head if b < 9 or (13 < b < 32))
            return bad > len(head) * 0.10
        return False
    except OSError:
        return True


TYPE_BY_EXT = {
    ".txt": "text", ".md": "text", ".markdown": "text", ".log": "text",
    ".tex": "text", ".rst": "text",
    ".csv": "data", ".tsv": "data", ".json": "data", ".jsonl": "data",
    ".yaml": "data", ".yml": "data", ".xml": "data", ".ini": "data",
    ".xls": "data", ".xlsx": "data",
    ".py": "code", ".sh": "code", ".r": "code", ".ipynb": "code",
    ".c": "code", ".cpp": "code", ".h": "code", ".js": "code",
    ".pdf": "doc", ".doc": "doc", ".docx": "doc", ".ppt": "doc",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
    ".tif": "image", ".tiff": "image", ".bmp": "image", ".svg": "image",
    ".zip": "archive", ".tar": "archive", ".tgz": "archive",
    ".gz": "archive", ".7z": "archive", ".rar": "archive",
}
TEXT_EXTS = {".txt", ".md", ".markdown", ".log", ".tex", ".rst", ".csv",
             ".tsv", ".json", ".jsonl", ".yaml", ".yml", ".xml", ".ini",
             ".py", ".sh", ".r", ".c", ".cpp", ".h", ".js", ".ipynb"}
ARCHIVE_EXTS = {".zip", ".tar", ".tgz", ".gz"}


def file_type(path):
    ext = os.path.splitext(path)[1].lower()
    return TYPE_BY_EXT.get(ext, "other")


def cjk_bigrams(text):
    """中文按字二元组切词；ASCII 单词整体作为词元；其他单字丢弃。

    FTS5 默认分词器不识别中文，bigram 可保证子串级命中。
    """
    tokens = []
    buf_word = []
    buf_cjk = []

    def flush():
        if buf_word:
            tokens.append("".join(buf_word))
            del buf_word[:]
        if buf_cjk:
            if len(buf_cjk) == 1:
                tokens.append(buf_cjk[0])
            else:
                tokens.extend(buf_cjk[i] + buf_cjk[i + 1]
                              for i in range(len(buf_cjk) - 1))
            del buf_cjk[:]

    for ch in text:
        o = ord(ch)
        if ch.isascii() and (ch.isalnum() or ch in "_-."):
            buf_word.append(ch.lower())
        elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF or \
                0xF900 <= o <= 0xFAFF or 0x3040 <= o <= 0x30FF or \
                0xAC00 <= o <= 0xD7AF:
            if buf_word:
                tokens.append("".join(buf_word))
                del buf_word[:]
            buf_cjk.append(ch)
        else:
            flush()
    flush()
    return tokens


def extract_policy(case, task_text):
    """从 case.json 与 task.md 抽取 保存期限(retention) 与 密级(access_level)。

    返回 dict，含 value / source / evidence；抽不到填 "unspecified"。
    """
    result = {"retention": {"value": "unspecified", "source": None,
                            "evidence": None},
              "access_level": {"value": "unspecified", "source": None,
                               "evidence": None}}
    patterns = [
        ("retention", [
            r"保存期限\s*[:：]\s*([^\n，。;；]{1,40})",
            r"留存期\s*[:：]\s*([^\n，。;；]{1,40})",
            r"retention\s*[:：]\s*([^\n,;]{1,40})",
        ]),
        ("access_level", [
            r"密级\s*[:：]\s*([^\n，。;；]{1,40})",
            r"权限级别\s*[:：]\s*([^\n，。;；]{1,40})",
            r"access[_ ]level\s*[:：]\s*([^\n,;]{1,40})",
        ]),
    ]
    corpus = []
    if isinstance(case, dict):
        corpus.append(("case.json", json.dumps(case, ensure_ascii=False)))
    if task_text:
        corpus.append(("task.md", task_text))
    for field, pats in patterns:
        for src_name, text in corpus:
            for pat in pats:
                m = re.search(pat, text, re.IGNORECASE)
                if m:
                    val = m.group(1).strip()
                    if val:
                        result[field]["value"] = val
                        result[field]["source"] = src_name
                        result[field]["evidence"] = m.group(0)[:120]
                        break
            if result[field]["source"]:
                break
    return result


def norm_stem(name):
    """归一化文件名主干以聚类版本：剥离常见版本/备份后缀。"""
    stem, ext = os.path.splitext(name)
    s = stem
    for pat in (r"[ _-]v\d+(\.\d+)?$", r"[ _-]V\d+(\.\d+)?$",
                r"[ _-]ver\d+(\.\d+)?$", r"[ _-]\d{1,2}$",
                r" \(\d+\)$", r"（\d+）$", r"[- _]copy\d*$",
                r"[- _]?副本\d*$", r"[- _]?备份\d*$", r"[- _]bak\d*$",
                r"[- _]backup\d*$", r"~$", r"\.bak\d*$", r"[- _]final\d*$",
                r"[- _]old$", r"[- _]new$"):
        s2 = re.sub(pat, "", s)
        if s2 != s:
            s = s2
    return s.strip(), ext.lower()


def log(msg):
    print("[archive-pipeline] %s" % msg, flush=True)


def eprint(msg):
    print(msg, file=sys.stderr, flush=True)
