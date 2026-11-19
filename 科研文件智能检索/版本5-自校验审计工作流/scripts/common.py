#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""common.py — 科研文件智能检索 Skill 共享工具库（仅标准库依赖）。

所有脚本共用：日志、JSON 读写、哈希、文本规范化、运行日记。
设计原则：确定性、可复跑、失败诚实记录（绝不静默吞错）。
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

SKILL_VERSION = "core-1.0.0"

# ---------------------------------------------------------------- 运行日记

class Journal:
    """append-only JSONL 运行日记：每个操作一步，供复核。"""

    def __init__(self, path):
        self.path = path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        self._t0 = time.time()

    def log(self, step, action, status="ok", inputs=None, outputs=None, detail=None):
        rec = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "elapsed_s": round(time.time() - self._t0, 3),
            "step": step,
            "action": action,
            "status": status,          # ok | skipped | failed | recovered | partial
            "inputs": inputs or [],
            "outputs": outputs or [],
            "detail": detail,
        }
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        return rec


def load_journal(path):
    if not os.path.exists(path):
        return []
    out = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    out.append({"status": "corrupt", "raw": line[:120]})
    return out

# ---------------------------------------------------------------- JSON I/O

def read_json(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def write_json(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)
    return path


def append_jsonl(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

# ---------------------------------------------------------------- 哈希与文件

def sha256_file(path, _bufsize=1 << 20):
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(_bufsize)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except OSError:
        return None


def sniff_magic(path):
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return None
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04"):
        return "zip"     # docx/xlsx/pptx/jar…
    if head.startswith(b"\xd0\xcf\x11\xe0"):
        return "ole"     # 旧版 doc/xls/ppt
    if head.startswith(b"\x89PNG"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head.startswith(b"{\"") or head.startswith(b"{"):
        return "json-ish"
    return "unknown"

_EXT_CATEGORY = {
    ".pdf": "pdf", ".docx": "docx", ".doc": "doc-legacy", ".xlsx": "xlsx",
    ".xls": "xls-legacy", ".pptx": "pptx", ".ppt": "ppt-legacy",
    ".txt": "text", ".md": "text", ".markdown": "text", ".csv": "text",
    ".tsv": "text", ".json": "text", ".xml": "text", ".html": "text",
    ".htm": "text", ".tex": "text", ".log": "text", ".rtf": "text",
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".tif": "image",
    ".tiff": "image", ".bmp": "image", ".gif": "image",
    ".zip": "archive", ".tar": "archive", ".gz": "archive",
    ".eml": "email", ".bib": "text", ".ris": "text",
}


def categorize(path):
    ext = os.path.splitext(path)[1].lower()
    return _EXT_CATEGORY.get(ext, "other")


def which_tools():
    return {t: (shutil.which(t) or None)
            for t in ("pdftotext", "pdftoppm", "tesseract", "libreoffice",
                      "soffice", "antiword", "catdoc")}

# ---------------------------------------------------------------- 文本规范化

_WS_RE = re.compile(r"\s+")

def norm_text(s):
    """折叠空白后的规范化文本，用于逐字比对。"""
    if s is None:
        return ""
    return _WS_RE.sub(" ", s).strip()


_CJK_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
_LATIN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-']*")


def tokenize(s, bigram_cjk=True):
    """中英混合分词：拉丁词 + CJK bigram。返回小写 token 列表。"""
    s = s or ""
    tokens = []
    latin = [w.lower() for w in _LATIN_RE.findall(s)]
    tokens.extend(w for w in latin if len(w) >= 2 or w.isdigit())
    cjk_runs = []
    buf = []
    for ch in s:
        if _CJK_RE.match(ch):
            buf.append(ch)
        else:
            if buf:
                cjk_runs.append("".join(buf))
                buf = []
    if buf:
        cjk_runs.append("".join(buf))
    for run in cjk_runs:
        if bigram_cjk and len(run) >= 2:
            tokens.extend(run[i:i + 2] for i in range(len(run) - 1))
        else:
            tokens.append(run)
    return tokens


STOPWORDS = set("""
the a an of to and or in on for with by is are was were be been at as from
that this these those it its into not no over under between per via we our
you your he she they their can may will would should could also et al fig
figure table eq equation respectively using use used based where which when
whom whose what how why all both each such more most other than then thus
的 了 和 与 及 或 在 是 对 为 于 中 由 将 被 等 之 其 该 此 以及 通过 进行 相关 分别 其中 我们 本文 本研究
以及 一个 一些 如下 所示 见图 见表 所示 采用 使用 根据 结果 表明 方法 材料
""".split())

# ---------------------------------------------------------------- 版本/别名模式

_VERSION_RE = re.compile(
    r"(?i)(?:^|[^a-z0-9])"
    r"(v\d+(?:\.\d+)*|rev\.?\s?\d+|version\s?\d+(?:\.\d+)*|"
    r"第\s*\d+\s*版|修订版|修改版|终版|最终版|定稿|"
    r"final\d*|draft\d*|v_?\d+(?:\.\d+)*|"
    r"(?:19|20)\d{2}[-_.年]\d{1,2}[-_.月]?\d{0,2})")

_STAGE_RANK = [
    ("draft", 0), ("草稿", 0), ("初稿", 0),
    ("修订", 1), ("修改", 1), ("rev", 1),
    ("submission", 2), ("投稿", 2), ("submitted", 2),
    ("accept", 3), ("录用", 3),
    ("final", 4), ("终版", 4), ("最终", 4), ("定稿", 4),
]


def norm_basename(name):
    """文件名规范化：小写、去扩展名、去空白/分隔符/版本号，用于别名匹配。"""
    base = os.path.splitext(name)[0].lower()
    base = _VERSION_RE.sub("", base)
    base = re.sub(r"[\s\-_·.、()（）\[\]【】]+", "", base)
    return base


def version_tags(name):
    """从文件名抽取版本标签与日期。"""
    tags = []
    for m in _VERSION_RE.finditer(name):
        t = m.group(1).strip()
        tags.append(t)
    dates = re.findall(r"(19|20)\d{2}[-_.年]\d{1,2}[-_.月]?\d{0,2}", name)
    return tags, dates


def stage_rank(name):
    low = name.lower()
    best = -1
    for key, rank in _STAGE_RANK:
        if key in low:
            best = max(best, rank)
    return best

# ---------------------------------------------------------------- 证据锚点

def make_anchor(doc, para=None, section=None, quote=None, extra=None):
    """标准证据锚点：文件+版本+页码+章节+段落+原文片段。"""
    a = {
        "file_path": doc.get("path"),
        "doc_id": doc.get("doc_id"),
        "sha256": doc.get("sha256"),
        "version": (doc.get("metadata") or {}).get("version_tag"),
        "section_path": (section or {}).get("path") if section else (para or {}).get("section_path"),
        "section_title": (section or {}).get("title") if section else None,
        "paragraph_id": (para or {}).get("para_id"),
        "page": (para or {}).get("page") if para else (section or {}).get("page_start"),
        "printed_page": (para or {}).get("printed_page") if para else None,
        "quote": norm_text(quote) if quote else None,
    }
    if extra:
        a.update(extra)
    return a

# ---------------------------------------------------------------- 子进程

def run_cmd(argv, timeout=120, input_bytes=None):
    """运行外部命令，返回 (rc, stdout, stderr)。绝不抛异常到上层。"""
    try:
        p = subprocess.run(argv, capture_output=True, timeout=timeout,
                           input=input_bytes)
        return p.returncode, p.stdout.decode("utf-8", "replace"), \
            p.stderr.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return -9, "", "timeout after %ss" % timeout
    except FileNotFoundError:
        return -2, "", "command not found: %s" % argv[0]
    except Exception as e:  # noqa: BLE001
        return -1, "", repr(e)


def eprint(*a):
    print(*a, file=sys.stderr)
