#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_skill_install.py — 提交契约预检（弃权型失分防线）

读取同目录 ../direction.json 的参数（frontmatter_max_bytes、resource_limits 等），
对本 Skill 目录做提交前合规检查，产出 preflight_report.json：

  1. SKILL.md 存在且 frontmatter 含合法 name/description（非空、单行、YAML 安全）
  2. description 字节数 ≤ direction.json.frontmatter_max_bytes（历史教训：疑似上限违规导致评测弃权）
  3. 全部资源文件为 UTF-8 文本（评测契约要求 "UTF-8 text files"）
  4. 文件总数 / 单文件大小 / 总量 / 符号链接 符合 resource_limits
  5. GITHUB_URL.txt 存在且首行为 http(s) 链接

用法：
  python3 scripts/check_skill_install.py [--skill-dir DIR] [--report preflight_report.json]
退出码：0 = pass；1 = fail（报告仍写出）。
"""
import argparse
import json
import os
import re
import sys

DEFAULTS = {
    "frontmatter_max_bytes": 1024,
    "resource_limits": {
        "max_files": 50, "max_file_bytes": 500 * 1024,
        "max_total_bytes": 2 * 1024 * 1024, "no_symlinks": True,
    },
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--skill-dir", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    ap.add_argument("--report", default=None)
    args = ap.parse_args()
    root = os.path.abspath(args.skill_dir)
    report_path = args.report or os.path.join(root, "preflight_report.json")

    # 读取 direction.json（参数必须真被读取：上限值全部来自这里，缺省才用 DEFAULTS）
    cfg = dict(DEFAULTS)
    dj_path = os.path.join(root, "direction.json")
    cfg_source = "defaults"
    if os.path.exists(dj_path):
        try:
            with open(dj_path, encoding="utf-8") as f:
                dj = json.load(f)
            if "frontmatter_max_bytes" in dj:
                cfg["frontmatter_max_bytes"] = dj["frontmatter_max_bytes"]
            if isinstance(dj.get("resource_limits"), dict):
                cfg["resource_limits"].update(dj["resource_limits"])
            cfg_source = "direction.json"
        except Exception as e:
            pass  # 下方检查会独立发现 direction.json 的问题
    lim = cfg["resource_limits"]

    checks = []
    def add(name, ok, detail):
        checks.append({"check": name, "ok": bool(ok), "detail": detail})

    # 1-2. frontmatter
    sk = os.path.join(root, "SKILL.md")
    if not os.path.exists(sk):
        add("skill_md_exists", False, "SKILL.md 不存在")
        name_v, desc_b = None, None
    else:
        add("skill_md_exists", True, sk)
        t = open(sk, encoding="utf-8").read()
        m = re.match(r"^---\n(.*?)\n---\n", t, re.S)
        if not m:
            add("frontmatter_block", False, "缺少 --- 包裹的 frontmatter")
            name_v, desc_b = None, None
        else:
            fm = m.group(1)
            mn = re.search(r"(?m)^name:\s*(\S+)\s*$", fm)
            md = re.search(r"(?m)^description:\s*(.+?)\s*$", fm)
            name_v = mn.group(1) if mn else None
            desc_b = len(md.group(1).encode("utf-8")) if md else None
            add("frontmatter_name", bool(name_v) and re.fullmatch(r"[a-z0-9-]+", name_v or ""),
                "name=%r（需小写字母/数字/连字符）" % name_v)
            add("frontmatter_description_bytes",
                desc_b is not None and 0 < desc_b <= cfg["frontmatter_max_bytes"],
                "description=%s bytes，上限 %s bytes（来源：%s）" % (desc_b, cfg["frontmatter_max_bytes"], cfg_source))

    # 3-4. 资源约束
    files, non_utf8, symlinks = [], [], []
    total = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and d != ".git"]
        for fn in filenames:
            p = os.path.join(dirpath, fn)
            if os.path.islink(p):
                symlinks.append(p)
                continue
            rel = os.path.relpath(p, root)
            if rel in ("preflight_report.json",):
                continue
            files.append(rel)
            total += os.path.getsize(p)
            try:
                with open(p, "rb") as f:
                    f.read().decode("utf-8")
            except Exception:
                non_utf8.append(rel)
            if os.path.getsize(p) > lim["max_file_bytes"]:
                add("file_size_limit", False, "%s 超过单文件上限" % rel)
    add("resource_file_count", len(files) <= lim["max_files"], "%d/%d 个文件" % (len(files), lim["max_files"]))
    add("resource_total_bytes", total <= lim["max_total_bytes"], "%d/%d bytes" % (total, lim["max_total_bytes"]))
    add("resource_utf8_only", not non_utf8, "非 UTF-8 文件：%s" % (non_utf8 or "无"))
    add("resource_no_symlinks", not symlinks or not lim["no_symlinks"], "符号链接：%s" % (symlinks or "无"))

    # 5. GITHUB_URL.txt
    gu = os.path.join(root, "GITHUB_URL.txt")
    if os.path.exists(gu):
        first = open(gu, encoding="utf-8").readline().strip()
        add("github_url", first.startswith("http"), "首行=%s" % first[:80])
    else:
        add("github_url", False, "GITHUB_URL.txt 缺失（可选但影响 +5 附加分）")

    verdict = "pass" if all(c["ok"] for c in checks) else "fail"
    report = {
        "skill_dir": root, "config_source": cfg_source,
        "config": {"frontmatter_max_bytes": cfg["frontmatter_max_bytes"], "resource_limits": lim},
        "description_bytes": desc_b, "file_count": len(files), "total_bytes": total,
        "checks": checks, "verdict": verdict,
    }
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": verdict, "description_bytes": desc_b,
                      "failed": [c["check"] for c in checks if not c["ok"]]}, ensure_ascii=False))
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
