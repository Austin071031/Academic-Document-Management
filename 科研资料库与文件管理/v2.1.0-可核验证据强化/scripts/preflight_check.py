#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step8 preflight_check：提交契约自检（针对 Skill 包自身）。

检查项（全部硬约束，任一不过 → ok=false、退出码 1）：
1. SKILL.md frontmatter 合法：以 --- 开头、含 name 与 description，
   且 description ≤ 900 字节（UTF-8）；
2. 文件总数 ≤ 50（不含 __pycache__ 缓存与 VCS 元数据）；
3. 单文件 ≤ 500 KB；
4. 总大小 ≤ 2 MB；
5. 全部文件为合法 UTF-8 文本（无二进制）；
6. 无符号链接。

产物：preflight_report.json（默认写 --report 指定路径；
cas_run 调用时写 <output>/preflight_report.json）。
仅标准库；自检本身绝不因单个文件异常崩溃（异常计为失败项）。
"""
import argparse
import json
import os
import sys

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_DESC_BYTES = 900
IGNORE_DIRS = {"__pycache__", ".git", ".hg", ".svn"}


def skill_root():
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def check(root):
    root = os.path.abspath(root)
    report = {"root": root, "ok": True, "checks": [], "violations": []}

    def add(name, ok, detail):
        report["checks"].append({"check": name, "ok": bool(ok),
                                 "detail": detail})
        if not ok:
            report["ok"] = False
            report["violations"].append("%s: %s" % (name, detail))

    # ---- 收集文件（跳过缓存/VCS；符号链接单独记录）
    files, symlinks = [], []
    for r, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in IGNORE_DIRS
                         and not os.path.islink(os.path.join(r, d)))
        if os.path.islink(r):
            continue
        for n in sorted(names):
            full = os.path.join(r, n)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if os.path.islink(full):
                symlinks.append(rel)
            else:
                files.append((rel, full))

    # ---- 1) frontmatter
    skill_md = os.path.join(root, "SKILL.md")
    try:
        with open(skill_md, "r", encoding="utf-8") as f:
            text = f.read()
        fm_ok, fm_msg = False, "frontmatter 缺失"
        if text.startswith("---"):
            end = text.find("\n---", 3)
            if end > 0:
                block = text[3:end]
                name = None
                desc = None
                for line in block.splitlines():
                    if line.startswith("name:"):
                        name = line.split(":", 1)[1].strip()
                    elif line.startswith("description:"):
                        desc = line.split(":", 1)[1].strip()
                dlen = len((desc or "").encode("utf-8"))
                if name and desc is not None and dlen <= MAX_DESC_BYTES:
                    fm_ok, fm_msg = True, ("name=%s, description=%dB ≤ %dB"
                                           % (name, dlen, MAX_DESC_BYTES))
                elif not name:
                    fm_msg = "frontmatter 缺 name"
                elif desc is None:
                    fm_msg = "frontmatter 缺 description"
                else:
                    fm_msg = ("description 超长: %dB > %dB"
                              % (dlen, MAX_DESC_BYTES))
        add("frontmatter", fm_ok, fm_msg)
    except (OSError, UnicodeDecodeError) as e:
        add("frontmatter", False, "SKILL.md 读取失败: %s: %s"
            % (type(e).__name__, e))

    # ---- 2) 文件数
    add("file_count", len(files) <= MAX_FILES,
        "%d 个文件（上限 %d）" % (len(files), MAX_FILES))

    # ---- 3/4) 单文件与总大小；5) UTF-8
    total, oversize, non_utf8 = 0, [], []
    for rel, full in files:
        try:
            size = os.path.getsize(full)
            total += size
            if size > MAX_FILE_BYTES:
                oversize.append("%s (%dB)" % (rel, size))
            with open(full, "rb") as f:
                f.read().decode("utf-8")
        except UnicodeDecodeError:
            non_utf8.append(rel)
        except OSError as e:
            non_utf8.append("%s (读取失败: %s)" % (rel, e))
    add("single_file_size", not oversize,
        "全部 ≤ 500KB" if not oversize
        else "超限: %s" % "; ".join(oversize[:10]))
    add("total_size", total <= MAX_TOTAL_BYTES,
        "%dB（上限 %dB）" % (total, MAX_TOTAL_BYTES))
    add("utf8_only", not non_utf8,
        "全部 UTF-8 文本" if not non_utf8
        else "非 UTF-8/不可读: %s" % "; ".join(non_utf8[:10]))

    # ---- 6) 符号链接
    add("no_symlinks", not symlinks,
        "无符号链接" if not symlinks
        else "存在符号链接: %s" % "; ".join(symlinks[:10]))

    report["stats"] = {"files": len(files), "total_bytes": total,
                       "symlinks": len(symlinks)}
    return report


def main():
    ap = argparse.ArgumentParser(description="Skill 提交契约自检")
    ap.add_argument("--root", default=None,
                    help="Skill 根目录（默认取 scripts/ 的父目录）")
    ap.add_argument("--report", default=None,
                    help="preflight_report.json 输出路径（默认仅打印）")
    ap.add_argument("--input", default="/input")   # 与流水线签名对齐
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    root = a.root or skill_root()
    report = check(root)
    out = a.report
    if out is None and a.output:
        out = os.path.join(a.output, "preflight_report.json")
    if out:
        os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
        with open(out, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    print("preflight %s: files=%d total=%dB violations=%d"
          % ("ok" if report["ok"] else "FAILED",
             report["stats"]["files"], report["stats"]["total_bytes"],
             len(report["violations"])))
    sys.exit(0 if report["ok"] else 1)


if __name__ == "__main__":
    main()
