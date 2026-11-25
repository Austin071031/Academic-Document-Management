#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""提交契约自检（v2.3.0 新增）。

对本 Skill 提交目录做硬约束核验，输出 preflight_report.json：
  - SKILL.md frontmatter 合法（--- 块、name、description 存在）
    且 description UTF-8 编码 ≤900B；
  - 文件总数 ≤50；单文件 ≤500KB；总大小 ≤2MB；
  - 全部文件为 UTF-8 文本（无二进制）；
  - 无符号链接。

用法：
  python3 scripts/preflight_check.py [--root <提交目录>] \
      [--report <preflight_report.json 路径>]
退出码 0=全部通过，1=存在违例。
"""
import argparse
import json
import os
import re
import sys
import time

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_DESC_BYTES = 900


def check_frontmatter(skill_path):
    """解析 SKILL.md frontmatter，返回 (checks, problems)。"""
    checks = {"frontmatter_present": False, "name_present": False,
              "description_present": False,
              "description_bytes": None,
              "description_within_900B": False}
    problems = []
    try:
        with open(skill_path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError) as e:
        problems.append("SKILL.md 读取失败: %s" % e)
        return checks, problems
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        problems.append("SKILL.md 缺少合法 frontmatter（--- 块）")
        return checks, problems
    checks["frontmatter_present"] = True
    fm = m.group(1)
    name_m = re.search(r"^name\s*:\s*(\S+)\s*$", fm, re.MULTILINE)
    if name_m:
        checks["name_present"] = True
        checks["name"] = name_m.group(1)
    else:
        problems.append("frontmatter 缺少 name 字段")
    desc_m = re.search(r"^description\s*:\s*(.+?)\s*$", fm, re.MULTILINE)
    if desc_m:
        checks["description_present"] = True
        nbytes = len(desc_m.group(1).encode("utf-8"))
        checks["description_bytes"] = nbytes
        checks["description_within_900B"] = nbytes <= MAX_DESC_BYTES
        if nbytes > MAX_DESC_BYTES:
            problems.append("description %dB 超过 900B 上限" % nbytes)
    else:
        problems.append("frontmatter 缺少 description 字段")
    return checks, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None,
                    help="提交目录（默认：本脚本所在 scripts/ 的上级）")
    ap.add_argument("--report", default=None,
                    help="报告输出路径（默认 <root>/preflight_report.json）")
    args = ap.parse_args()
    root = os.path.abspath(args.root) if args.root else \
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    report_path = args.report or os.path.join(root,
                                              "preflight_report.json")

    report = {"root": root,
              "checked_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                           time.gmtime()),
              "limits": {"max_files": MAX_FILES,
                         "max_file_bytes": MAX_FILE_BYTES,
                         "max_total_bytes": MAX_TOTAL_BYTES,
                         "max_description_bytes": MAX_DESC_BYTES},
              "checks": {}, "violations": [], "pass": False}

    files = []
    symlinks = []
    total = 0
    non_utf8 = []
    oversize = []
    for dirpath, dirnames, filenames in os.walk(root):
        for d in list(dirnames):
            full_d = os.path.join(dirpath, d)
            if os.path.islink(full_d):
                symlinks.append(os.path.relpath(full_d, root))
                dirnames.remove(d)
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.islink(full):
                symlinks.append(rel)
                continue
            try:
                size = os.path.getsize(full)
            except OSError as e:
                report["violations"].append(
                    {"file": rel, "check": "stat", "detail": str(e)})
                continue
            files.append((rel, size))
            total += size
            if size > MAX_FILE_BYTES:
                oversize.append({"file": rel, "bytes": size})
            try:
                with open(full, "r", encoding="utf-8") as f:
                    f.read()
            except (UnicodeDecodeError, OSError) as e:
                non_utf8.append({"file": rel,
                                 "detail": "%s: %s" % (type(e).__name__, e)})

    # 报告自身不纳入计数（写报告前先统计）
    report["checks"] = {
        "file_count": {"value": len(files), "limit": MAX_FILES,
                       "pass": len(files) <= MAX_FILES},
        "total_bytes": {"value": total, "limit": MAX_TOTAL_BYTES,
                        "pass": total <= MAX_TOTAL_BYTES},
        "oversize_files": {"count": len(oversize), "items": oversize,
                           "pass": not oversize},
        "all_utf8": {"pass": not non_utf8, "non_utf8_files": non_utf8},
        "no_symlinks": {"pass": not symlinks, "symlinks": symlinks},
    }
    fm_checks, fm_problems = check_frontmatter(
        os.path.join(root, "SKILL.md"))
    report["checks"]["frontmatter"] = dict(fm_checks)
    report["checks"]["frontmatter"]["pass"] = (
        fm_checks["frontmatter_present"] and fm_checks["name_present"]
        and fm_checks["description_present"]
        and fm_checks["description_within_900B"])

    for p in fm_problems:
        report["violations"].append({"file": "SKILL.md",
                                     "check": "frontmatter", "detail": p})
    if len(files) > MAX_FILES:
        report["violations"].append(
            {"check": "file_count",
             "detail": "%d files > %d" % (len(files), MAX_FILES)})
    if total > MAX_TOTAL_BYTES:
        report["violations"].append(
            {"check": "total_bytes",
             "detail": "%d bytes > %d" % (total, MAX_TOTAL_BYTES)})
    for item in oversize:
        report["violations"].append(
            {"file": item["file"], "check": "file_size",
             "detail": "%d bytes > %d" % (item["bytes"], MAX_FILE_BYTES)})
    for item in non_utf8:
        report["violations"].append(
            {"file": item["file"], "check": "utf8",
             "detail": item["detail"]})
    for s in symlinks:
        report["violations"].append({"file": s, "check": "symlink",
                                     "detail": "symbolic link not allowed"})

    report["pass"] = (not report["violations"]) and all(
        c.get("pass", True) for c in report["checks"].values())
    tmp = report_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
        f.write("\n")
    os.replace(tmp, report_path)
    print("[preflight] pass=%s files=%d total=%dB violations=%d" % (
        report["pass"], len(files), total, len(report["violations"])))
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
