#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
preflight_check.py — Skill 提交契约自检（版本2 新增）。

对 Skill 根目录（默认取本脚本的上上级目录）检查：
  1. SKILL.md frontmatter 存在且为合法 key: value 形态；
     name 匹配 ^[a-z0-9]+(-[a-z0-9]+)*$；description ≤900 UTF-8 字节（>600 告警）。
  2. 文件数 ≤50；单文件 ≤500KB；总大小 ≤2MB。
  3. 全部文件 UTF-8 可解码；无符号链接。
  4. 常见密钥/token 模式扫描（ghp_/AKIA/sk-/PRIVATE KEY/api_key=... 形态）。

产出 preflight_report.json（默认 <root>/preflight_report.json，可用 --report 指定）。
退出码：0=PASS，1=FAIL，2=自检自身异常。
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
DESC_HARD_BYTES = 900
DESC_WARN_BYTES = 600
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
SECRET_PATTERNS = [
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("aws_akid", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("generic_secret", re.compile(
        r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*[\"'][A-Za-z0-9_\-]{8,}[\"']")),
]


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_print(*args):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    print(*args)


def check_frontmatter(root, problems, warnings):
    path = os.path.join(root, "SKILL.md")
    if not os.path.exists(path):
        problems.append("SKILL.md 不存在")
        return {}
    text = open(path, "r", encoding="utf-8").read()
    if not text.startswith("---"):
        problems.append("SKILL.md 缺少 frontmatter（未以 --- 开头）")
        return {}
    end = text.find("\n---", 3)
    if end < 0:
        problems.append("SKILL.md frontmatter 未闭合")
        return {}
    block = text[3:end].strip("\n")
    meta = {}
    for line in block.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = re.match(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$", line)
        if not m:
            problems.append("frontmatter 非法行（非 key: value）：%r" % line[:60])
            continue
        meta[m.group(1)] = m.group(2).strip().strip('"').strip("'")
    name = meta.get("name")
    if not name:
        problems.append("frontmatter 缺少 name")
    elif not NAME_RE.match(name):
        problems.append("frontmatter name 非法：%r（需 ^[a-z0-9]+(-[a-z0-9]+)*$）" % name)
    desc = meta.get("description")
    if desc is None:
        problems.append("frontmatter 缺少 description")
    else:
        nbytes = len(desc.encode("utf-8"))
        if nbytes > DESC_HARD_BYTES:
            problems.append("description %dB 超过硬上限 %dB" % (nbytes, DESC_HARD_BYTES))
        elif nbytes > DESC_WARN_BYTES:
            warnings.append("description %dB 超过建议余量 %dB（平台疑似上限 1024B）"
                            % (nbytes, DESC_WARN_BYTES))
    return {"name": name, "description_bytes": len((desc or "").encode("utf-8"))}


def main(argv=None):
    ap = argparse.ArgumentParser(description="Skill 提交契约自检")
    ap.add_argument("--root", default=None, help="Skill 根目录（默认：本脚本上上级）")
    ap.add_argument("--report", default=None, help="preflight_report.json 输出路径")
    args = ap.parse_args(argv)

    root = os.path.abspath(args.root) if args.root else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report_path = args.report or os.path.join(root, "preflight_report.json")
    problems, warnings = [], []

    file_count = 0
    total_bytes = 0
    largest = {"path": None, "bytes": 0}
    self_name = os.path.basename(os.path.abspath(__file__))

    for dirpath, dirs, files in os.walk(root):
        dirs.sort()
        for d in list(dirs):
            if os.path.islink(os.path.join(dirpath, d)):
                problems.append("符号链接目录：%s" % os.path.relpath(os.path.join(dirpath, d), root))
                dirs.remove(d)
        for fname in sorted(files):
            fpath = os.path.join(dirpath, fname)
            rel = os.path.relpath(fpath, root).replace(os.sep, "/")
            if os.path.islink(fpath):
                problems.append("符号链接文件：%s" % rel)
                continue
            file_count += 1
            size = os.path.getsize(fpath)
            total_bytes += size
            if size > largest["bytes"]:
                largest = {"path": rel, "bytes": size}
            if size > MAX_FILE_BYTES:
                problems.append("单文件超限：%s（%dB > %dB）" % (rel, size, MAX_FILE_BYTES))
            try:
                with open(fpath, "r", encoding="utf-8", errors="strict") as fh:
                    text = fh.read()
            except Exception as exc:
                problems.append("非 UTF-8 或不可读：%s（%s）" % (rel, exc))
                continue
            if rel == "preflight_report.json":
                continue  # 上次自检报告可能含问题样例文本，跳过
            if fname == self_name:
                continue  # 跳过自检脚本自身（含密钥模式字面量）
            for label, pat in SECRET_PATTERNS:
                m = pat.search(text)
                if m:
                    problems.append("疑似密钥/token（%s）：%s 命中 %r"
                                    % (label, rel, m.group(0)[:12] + "…"))

    if file_count > MAX_FILES:
        problems.append("文件数超限：%d > %d" % (file_count, MAX_FILES))
    if total_bytes > MAX_TOTAL_BYTES:
        problems.append("总大小超限：%dB > %dB" % (total_bytes, MAX_TOTAL_BYTES))

    fm = check_frontmatter(root, problems, warnings)

    report = {
        "generated_at": utcnow(),
        "root": root,
        "verdict": "PASS" if not problems else "FAIL",
        "totals": {"files": file_count, "bytes": total_bytes,
                   "max_files": MAX_FILES, "max_file_bytes": MAX_FILE_BYTES,
                   "max_total_bytes": MAX_TOTAL_BYTES},
        "largest_file": largest,
        "frontmatter": fm,
        "problems": problems,
        "warnings": warnings,
    }
    with open(report_path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    safe_print("[preflight] verdict=%s files=%d bytes=%d desc=%sB problems=%d warnings=%d -> %s"
               % (report["verdict"], file_count, total_bytes,
                  fm.get("description_bytes"), len(problems), len(warnings), report_path))
    for p in problems:
        safe_print("[preflight] FAIL: %s" % p)
    for w in warnings:
        safe_print("[preflight] WARN: %s" % w)
    return 0 if not problems else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        safe_print("[preflight][FATAL] %s: %s" % (type(exc).__name__, exc))
        sys.exit(2)
