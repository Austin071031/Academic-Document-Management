#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preflight_check.py —— 提交契约自检（v2.2.0 新增）。

在提交前对技能目录（默认 scripts/ 的上一级）做机器 gate：
  gate1  SKILL.md frontmatter 合法：以 --- 起止、含 name 与 description、
         description UTF-8 字节数 ≤ --desc-max（默认 900B）；
  gate2  文件总数 ≤ --max-files（默认 50，含 preflight_report.json 自身豁免前）；
  gate3  单文件 ≤ --max-file-bytes（默认 500KB）；
  gate4  目录总大小 ≤ --max-total-bytes（默认 2MB）；
  gate5  全部文件可 UTF-8 解码（纯文本，无二进制）；
  gate6  无符号链接；
  gate7  无 token/密钥模式（ghp_/sk-/AKIA/私钥头/api_key=… 等）。
结果写 preflight_report.json（默认 <root>/preflight_report.json），
全部通过退出码 0，任一失败退出码 1（并逐项给出 detail）。
"""
import argparse
import json
import os
import re
import sys

SECRET_PATTERNS = [
    ("github_pat", re.compile(r"ghp_[A-Za-z0-9]{20,}")),
    ("openai_key", re.compile(r"sk-[A-Za-z0-9]{20,}")),
    ("aws_akid", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("private_key_header", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("generic_secret", re.compile(
        r"(?i)(api[_-]?key|secret|access[_-]?token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_\-\.]{16,}")),
]

SELF_NAME = "preflight_report.json"


def parse_frontmatter(text):
    """简陋 YAML frontmatter 解析（仅取 name/description，标准库实现）。"""
    if not text.startswith("---"):
        return None, "SKILL.md 不以 --- 开头"
    lines = text.splitlines()
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return None, "frontmatter 缺少结束 ---"
    meta = {}
    for line in lines[1:end]:
        m = re.match(r"^([A-Za-z_\-]+)\s*:\s*(.*)$", line)
        if m:
            meta[m.group(1).strip()] = m.group(2).strip().strip('"').strip("'")
    return meta, None


def main():
    ap = argparse.ArgumentParser(description="提交契约自检（v2.2.0）")
    ap.add_argument("--root", default=os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")),
        help="技能根目录（默认 scripts/ 上一级）")
    ap.add_argument("--output", default=None,
                    help="报告输出路径（默认 <root>/preflight_report.json）")
    ap.add_argument("--desc-max", type=int, default=900)
    ap.add_argument("--max-files", type=int, default=50)
    ap.add_argument("--max-file-bytes", type=int, default=500 * 1024)
    ap.add_argument("--max-total-bytes", type=int, default=2 * 1024 * 1024)
    a = ap.parse_args()

    root = os.path.abspath(a.root)
    out_path = a.output or os.path.join(root, SELF_NAME)

    files, symlinks, binaries, oversize = [], [], [], []
    total_bytes = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in sorted(filenames):
            ap_ = os.path.join(dirpath, name)
            rel = os.path.relpath(ap_, root)
            if os.path.islink(ap_):
                symlinks.append(rel)
                continue
            if rel == SELF_NAME:
                continue  # 报告自身豁免
            try:
                size = os.path.getsize(ap_)
            except OSError:
                continue
            total_bytes += size
            files.append({"path": rel, "bytes": size})
            if size > a.max_file_bytes:
                oversize.append({"path": rel, "bytes": size})
            try:
                with open(ap_, "rb") as f:
                    data = f.read()
                data.decode("utf-8")
            except (UnicodeDecodeError, ValueError):
                binaries.append(rel)

    # gate1 frontmatter
    checks = []
    skill_md = os.path.join(root, "SKILL.md")
    if not os.path.exists(skill_md):
        checks.append({"gate": "frontmatter", "ok": False,
                       "detail": "SKILL.md 不存在"})
    else:
        with open(skill_md, encoding="utf-8") as f:
            meta, err = parse_frontmatter(f.read())
        if err:
            checks.append({"gate": "frontmatter", "ok": False, "detail": err})
        else:
            desc = meta.get("description") or ""
            desc_bytes = len(desc.encode("utf-8"))
            ok = bool(meta.get("name")) and bool(desc) and desc_bytes <= a.desc_max
            checks.append({
                "gate": "frontmatter", "ok": ok,
                "detail": "name=%r, description=%dB (上限 %dB)%s"
                          % (meta.get("name"), desc_bytes, a.desc_max,
                             "" if ok else " —— 缺 name/description 或超长")})

    checks.append({"gate": "file_count", "ok": len(files) <= a.max_files,
                   "detail": "%d 个文件（上限 %d）" % (len(files), a.max_files)})
    checks.append({"gate": "single_file_size", "ok": not oversize,
                   "detail": "超限: %s" % oversize if oversize
                   else "全部 ≤ %dB" % a.max_file_bytes})
    checks.append({"gate": "total_size", "ok": total_bytes <= a.max_total_bytes,
                   "detail": "%dB（上限 %dB）" % (total_bytes, a.max_total_bytes)})
    checks.append({"gate": "utf8_only", "ok": not binaries,
                   "detail": "非 UTF-8: %s" % binaries if binaries
                   else "全部可 UTF-8 解码"})
    checks.append({"gate": "no_symlinks", "ok": not symlinks,
                   "detail": "符号链接: %s" % symlinks if symlinks else "无"})

    # gate7 secrets
    secret_hits = []
    for frec in files:
        ap_ = os.path.join(root, frec["path"])
        try:
            with open(ap_, encoding="utf-8") as f:
                text = f.read()
        except (OSError, UnicodeDecodeError):
            continue
        for pname, rx in SECRET_PATTERNS:
            if rx.search(text):
                secret_hits.append({"path": frec["path"], "pattern": pname})
    checks.append({"gate": "no_secrets", "ok": not secret_hits,
                   "detail": "命中: %s" % secret_hits if secret_hits else "未发现 token/密钥模式"})

    ok_all = all(c["ok"] for c in checks)
    report = {
        "root": root,
        "limits": {"desc_max_bytes": a.desc_max, "max_files": a.max_files,
                   "max_file_bytes": a.max_file_bytes,
                   "max_total_bytes": a.max_total_bytes},
        "stats": {"files": len(files), "total_bytes": total_bytes},
        "checks": checks,
        "ok": ok_all,
    }
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print("[preflight] %s — %d files, %dB -> %s"
          % ("PASS" if ok_all else "FAIL", len(files), total_bytes, out_path))
    for c in checks:
        print("  %s %s: %s" % ("OK " if c["ok"] else "FAIL", c["gate"], c["detail"]))
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
