#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_manifest.py —— 组织输出库 + 清单 + 重复/版本判定 + 字段覆盖率报告。

- 重复：按内容 sha256 分组（size>0），同哈希多文件 → duplicates.json（保留路径最短者为主副本）。
- 版本：管理备注 facts.jsonl 的 superseded_by 事实 + 归一化主干相同但哈希不同的启发式
  （剥离 vN/日期/副本/backup/final/最终版 等标记后同 key）→ versions.json，
  含 superseded_by 与差异摘要（文本：行数与增删行数；二进制：大小/mtime 差）。
- 组织：复制可读文件到 <output>/library/<project|未标注项目>/<year|未知年份>/原名，
  重名追加 __N；路径组件做分隔符清洗；复制失败登记不崩溃。
- 产物：manifest.json、manifest.csv（每字段带 __source 出处列）、
  field_coverage_report.md（字段填充率统计）。
"""
import argparse
import csv
import difflib
import os
import re
import shutil
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

COPY_MARKERS = re.compile(
    r"(副本|拷贝|备份|复件|copy|backup|bak|final|最终版|最新版|定稿|v\d+(?:\.\d+)*)",
    re.IGNORECASE)
TEXT_EXTS = {"txt", "md", "csv", "json", "log", "rst", "tex", "yaml", "yml",
             "xml", "tsv", "ini", "cfg", ""}


def sanitize(component):
    s = str(component).replace("/", "／").replace("\\", "＼").strip().strip(".")
    return s[:80] if s else "未标注"


def version_group_key(stem):
    s = COPY_MARKERS.sub("", stem)
    return lc.norm_key(s)


def text_diff_summary(path_a, path_b):
    try:
        ta, enca, _ = lc.read_text_head(path_a)
        tb, encb, _ = lc.read_text_head(path_b)
    except OSError as e:
        return "diff unavailable: %s" % e
    la, lb = ta.splitlines(), tb.splitlines()
    sm = difflib.SequenceMatcher(None, la, lb, autojunk=False)
    added = sum(j2 - j1 for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag == "insert")
    removed = sum(i2 - i1 for tag, i1, i2, j1, j2 in sm.get_opcodes() if tag == "delete")
    changed = sum(max(i2 - i1, j2 - j1) for tag, i1, i2, j1, j2 in sm.get_opcodes()
                  if tag == "replace")
    return ("lines %d→%d, +%d/-%d/~%d lines (first 64KB, %s vs %s)"
            % (len(la), len(lb), added, removed, changed, enca, encb))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    dictionary = lc.load_dictionary(a.work, a.config)
    dict_fields = list((dictionary.get("fields") or {}).keys())
    required_fields = [f for f, d in (dictionary.get("fields") or {}).items()
                       if d.get("required")]

    files = list(lc.jlines(os.path.join(a.work, "files.jsonl")) or [])
    prov = defaultdict(dict)  # relpath -> {field: record}
    for r in lc.jlines(os.path.join(a.work, "provenance.jsonl")) or []:
        prov[r["file"]][r["field"]] = r
    facts = list(lc.jlines(os.path.join(a.work, "facts.jsonl")) or [])

    by_rel = {r["relpath"]: r for r in files}

    # ---------- 重复判定（内容哈希） ----------
    hash_groups = defaultdict(list)
    for r in files:
        if r.get("readable") and r.get("sha256") and (r.get("size") or 0) > 0:
            hash_groups[r["sha256"]].append(r["relpath"])
    duplicates = []
    canonical = {}  # relpath -> canonical relpath
    for h, rels in hash_groups.items():
        if len(rels) < 2:
            continue
        rels_sorted = sorted(rels, key=lambda x: (len(x), x))
        keep = rels_sorted[0]
        for x in rels_sorted:
            canonical[x] = keep
        duplicates.append({
            "sha256": h,
            "size": by_rel[keep].get("size"),
            "files": rels_sorted,
            "keep": keep,
            "note": "内容哈希一致判定为重复；按路径最短者保留主副本",
        })

    # ---------- 版本链 ----------
    # 1) 管理备注事实（最高权威）
    def resolve(name):
        hits = [r["relpath"] for r in files
                if r.get("readable") and lc.norm_key(r["basename"]) == lc.norm_key(name)]
        if not hits:
            hits = [r["relpath"] for r in files
                    if r.get("readable") and lc.norm_key(r["relpath"]) == lc.norm_key(name)]
        return hits[0] if hits else None

    superseded = {}   # old_rel -> new_rel
    version_evidence = {}
    for fct in facts:
        if fct.get("type") != "superseded_by":
            continue
        old_rel = resolve(fct["old"])
        new_rel = resolve(fct["new"])
        if old_rel and new_rel and old_rel != new_rel:
            superseded[old_rel] = new_rel
            version_evidence[(old_rel, new_rel)] = fct.get("evidence")
    # 2) 启发式：剥离版本/副本标记后同主干、哈希不同
    vgroups = defaultdict(list)
    for r in files:
        if not r.get("readable") or not r.get("sha256"):
            continue
        vgroups[version_group_key(r["stem"])].append(r)
    for key, rs in vgroups.items():
        uniq_hash = {r["sha256"] for r in rs}
        if len(rs) < 2 or len(uniq_hash) < 2:
            continue  # 哈希全同属于 duplicates，不算版本
        rs_sorted = sorted(rs, key=lambda r: (r.get("mtime") or 0, r["relpath"]))
        for i in range(len(rs_sorted) - 1):
            o, n = rs_sorted[i], rs_sorted[i + 1]
            if o["relpath"] in superseded:
                continue  # 管理备注已裁决
            superseded[o["relpath"]] = n["relpath"]
            version_evidence[(o["relpath"], n["relpath"])] = (
                "heuristic: same normalized stem '%s', ordered by mtime" % key)

    versions = []
    for old, new in sorted(superseded.items()):
        ro, rn = by_rel.get(old), by_rel.get(new)
        if not ro or not rn:
            continue
        if ro.get("ext") in TEXT_EXTS and ro.get("abspath") and rn.get("abspath"):
            diff = text_diff_summary(ro["abspath"], rn["abspath"])
        else:
            diff = ("size %s→%s bytes, mtime %s→%s" % (
                ro.get("size"), rn.get("size"), ro.get("mtime"), rn.get("mtime")))
        versions.append({
            "old": old, "new": new, "superseded_by": new,
            "diff_summary": diff,
            "evidence": version_evidence.get((old, new)),
        })

    # ---------- 组织 library ----------
    lib_root = os.path.join(a.output, "library")
    os.makedirs(lib_root, exist_ok=True)
    manifest_entries, copy_errors = [], []
    used_names = defaultdict(int)
    for r in files:
        fields = {f: prec["value"] for f, prec in prov.get(r["relpath"], {}).items()}
        entry = {
            "relpath": r["relpath"],
            "origin": r.get("origin", "input"),
            "readable": r.get("readable", False),
            "size": r.get("size"),
            "sha256": r.get("sha256"),
            "fields": fields,
            "provenance": {f: {"source": p["source"], "confidence": p["confidence"],
                               "evidence": p["evidence"],
                               "conflicts": p.get("conflicts") or []}
                           for f, p in prov.get(r["relpath"], {}).items()},
            "errors": r.get("errors") or [],
            "duplicate_of": canonical.get(r["relpath"])
            if canonical.get(r["relpath"]) != r["relpath"] else None,
            "superseded_by": superseded.get(r["relpath"]),
            "library_path": None,
        }
        if not r.get("readable"):
            entry["library_path"] = None
            manifest_entries.append(entry)
            continue
        if r.get("origin") == "harness":
            entry["library_path"] = None
            entry["errors"].append("harness file (case.json/task.md): 扫描留痕，不组织进 library")
            manifest_entries.append(entry)
            continue
        proj = sanitize(fields.get("project") or "未标注项目")
        year = sanitize(fields.get("year") or "未知年份")
        dest_dir = os.path.join(lib_root, proj, year)
        os.makedirs(dest_dir, exist_ok=True)
        base = r["basename"]
        key = (proj, year, base.lower())
        used_names[key] += 1
        if used_names[key] > 1:
            stem, ext = os.path.splitext(base)
            base = "%s__%d%s" % (stem, used_names[key], ext)
        dest = os.path.join(dest_dir, base)
        src = r.get("abspath") or os.path.join(a.input, r["relpath"])
        try:
            shutil.copy2(src, dest)
            entry["library_path"] = os.path.relpath(dest, a.output)
        except OSError as e:
            copy_errors.append({"file": r["relpath"], "error": str(e)})
            entry["errors"].append("copy failed: %s" % e)
        manifest_entries.append(entry)

    # ---------- manifest.json / manifest.csv ----------
    lc.jwrite(os.path.join(a.output, "manifest.json"), {
        "generated_at": lc.now_iso(),
        "dictionary_version": dictionary.get("dictionary_version"),
        "priority_rule": lc.PRIORITY_RULE_STR,
        "entries": manifest_entries,
    })
    csv_path = os.path.join(a.output, "manifest.csv")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as fcsv:
        cols = (["relpath", "library_path", "readable", "size", "sha256",
                 "duplicate_of", "superseded_by"]
                + [c for f in dict_fields for c in (f, f + "__source")])
        w = csv.DictWriter(fcsv, fieldnames=cols)
        w.writeheader()
        for e in manifest_entries:
            row = {k: e.get(k) for k in
                   ("relpath", "library_path", "readable", "size", "sha256",
                    "duplicate_of", "superseded_by")}
            for f in dict_fields:
                row[f] = e["fields"].get(f)
                p = e["provenance"].get(f)
                row[f + "__source"] = p["source"] if p else None
            w.writerow(row)

    # ---------- duplicates.json / versions.json ----------
    lc.jwrite(os.path.join(a.output, "duplicates.json"), {
        "generated_at": lc.now_iso(),
        "method": "streaming sha256 content hash, size>0",
        "groups": duplicates,
    })
    lc.jwrite(os.path.join(a.output, "versions.json"), {
        "generated_at": lc.now_iso(),
        "method": "admin_note superseded_by facts first; normalized-stem + mtime heuristic second",
        "chains": versions,
    })

    # ---------- field_coverage_report.md ----------
    total = len(manifest_entries)
    lines = ["# 字段覆盖率报告", "",
             "- 生成时间：%s" % lc.now_iso(),
             "- 文件总数：%d（可读 %d，不可读 %d）" % (
                 total,
                 sum(1 for e in manifest_entries if e["readable"]),
                 sum(1 for e in manifest_entries if not e["readable"])),
             "- 裁决规则：%s" % lc.PRIORITY_RULE_STR, "",
             "| 字段 | 必填 | 填充数 | 填充率 | 各来源计数 |",
             "| --- | --- | --- | --- | --- |"]
    for f in dict_fields:
        d = (dictionary.get("fields") or {}).get(f, {})
        filled = [e for e in manifest_entries if e["fields"].get(f) not in (None, "")]
        srcs = defaultdict(int)
        for e in filled:
            p = e["provenance"].get(f) or {}
            srcs[p.get("source", "?")] += 1
        rate = ("%.1f%%" % (100.0 * len(filled) / total)) if total else "n/a"
        lines.append("| %s | %s | %d/%d | %s | %s |" % (
            f, "是" if d.get("required") else "否", len(filled), total, rate,
            ", ".join("%s:%d" % (k, v) for k, v in sorted(srcs.items())) or "-"))
    lines += ["", "## 未覆盖说明", ""]
    for f in required_fields:
        missing = [e["relpath"] for e in manifest_entries
                   if e["fields"].get(f) in (None, "")]
        if missing:
            lines.append("- 必填字段 `%s` 缺失 %d 个：%s" % (
                f, len(missing), "、".join(missing[:10])
                + (" …" if len(missing) > 10 else "")))
    if copy_errors:
        lines += ["", "## 复制失败", ""]
        for ce in copy_errors:
            lines.append("- %s: %s" % (ce["file"], ce["error"]))
    lines.append("")
    with open(os.path.join(a.output, "field_coverage_report.md"), "w", encoding="utf-8") as fr:
        fr.write("\n".join(lines))

    lc.log_change(a.work, "build_manifest", "output",
                  "adjudicated provenance + sha256 + facts",
                  "%d entries, %d duplicate groups, %d version links, %d copy errors"
                  % (total, len(duplicates), len(versions), len(copy_errors)))
    print("[manifest] entries=%d dup_groups=%d versions=%d copy_errors=%d"
          % (total, len(duplicates), len(versions), len(copy_errors)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
