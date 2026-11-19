#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_versions.py -- 去重、别名识别与版本链构造。

依据:
  1) sha256 完全相同 -> 重复副本 (同一内容的多个存放路径)
  2) 文件名版本模式 v1/v2/.../final/draft/revised/accepted/日期 -> 归入同一文档的版本链
  3) 大小写或扩展名不同但主干相同 -> 别名
  4) 可选 --rules rules.json: 人工/管理方规定的版本关系优先于启发式推断
     rules.json 例: {"canonical": {"path": "paper_final.pdf"},
                    "supersedes": {"paper_v2.pdf": "paper_v1.pdf"},
                    "notes": "来自管理员 version_notes.md 的规定"}

用法:
  python3 kb_versions.py --inventory /app/work/inventory.json --work /app/work [--rules rules.json]

输出:
  <work>/versions.json  文档/版本/别名/重复组结构
"""
import argparse
import json
import os
import re
import sys
import time

VER_PAT = re.compile(
    r"(?i)(?:^|[^a-z0-9])"
    r"(v(?:er(?:sion)?)?|rev|r|draft|preprint|submitted|accepted|revised|"
    r"final|published|supplementary|suppl|s\d+|"
    r"初稿|草稿|修订|修改稿|终稿|最终版|接受版|发表版|补充材料?)"
    r"[ _\-.]?(\d{1,3}|[a-z])?(?:[^a-z0-9]|$)")
DATE_PAT = re.compile(r"(?<!\d)(20\d{2}|19\d{2})[-_.]?(0[1-9]|1[0-2])[-_.]?(0[1-9]|[12]\d|3[01])(?!\d)|"
                      r"(?<!\d)(20\d{2}|19\d{2})(?!\d)")


def ver_key(stem):
    """从文件名主干提取 (base, version_label, sort_key)."""
    low = stem.lower()
    hits = []
    for m in VER_PAT.finditer(low):
        tag = (m.group(1) or "").lower()
        num = m.group(2)
        if tag in ("v", "ver", "version", "r", "rev"):
            order = ("num", int(num) if num and num.isdigit() else 0)
        elif tag and tag[0] == "s" and tag[1:].isdigit():
            order = ("num", int(tag[1:]))
        elif tag in ("draft", "preprint", "submitted", "初稿", "草稿"):
            order = ("stage", 0)
        elif tag in ("revised", "修订", "修改稿"):
            order = ("stage", 1)
        elif tag in ("accepted", "接受版"):
            order = ("stage", 2)
        elif tag in ("final", "published", "终稿", "最终版", "发表版"):
            order = ("stage", 3)
        elif tag in ("supplementary", "suppl", "补充材料?"):
            order = ("supp", 0)
        else:
            order = ("stage", 1)
        hits.append((m.start(), tag, num, order))
    date = None
    dm = DATE_PAT.search(low)
    if dm:
        date = (dm.group(1) or dm.group(4) or "") + (dm.group(2) or "") + (dm.group(3) or "")
    base = VER_PAT.sub(" ", low)
    base = DATE_PAT.sub(" ", base)
    base = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", base).strip()
    label = None
    sort_key = ("base", base, 0)
    if hits:
        hits.sort(key=lambda h: (h[3][0] != "num", h[0]))
        _, tag, num, order = hits[0]
        label = tag + (num or "")
        sort_key = ("num" if order[0] == "num" else "stage", base,
                    order[1] if isinstance(order[1], int) else 0)
    elif date:
        label = "date-" + date
        sort_key = ("date", base, int(date[:8]) if date[:8].isdigit() else 0)
    return base, label, sort_key, date


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--rules", default=None, help="人工规定的版本关系 JSON")
    args = ap.parse_args()

    with open(args.inventory, encoding="utf-8") as f:
        inv = json.load(f)
    rules = {}
    if args.rules and os.path.isfile(args.rules):
        with open(args.rules, encoding="utf-8") as f:
            rules = json.load(f)

    files = inv.get("files", [])
    by_hash = {}
    for i, rec in enumerate(files):
        h = rec.get("hash")
        if h:
            by_hash.setdefault(h, []).append(i)

    dup_groups = [{"sha256": h, "paths": [files[i]["path"] for i in idxs],
                   "canonical": rules.get("canonical", {}).get("paths")
                   if isinstance(rules.get("canonical"), dict) else None}
                  for h, idxs in sorted(by_hash.items()) if len(idxs) > 1]
    canonical_from_rules = set()
    if isinstance(rules.get("canonical"), dict):
        canonical_from_rules = set(v for v in rules["canonical"].values() if isinstance(v, str))
    for g in dup_groups:
        if g["canonical"] in g["paths"]:
            continue
        # 默认规范副本: 管理规则优先, 其次路径最短者
        cands = [p for p in g["paths"] if p in canonical_from_rules]
        g["canonical"] = min(cands or g["paths"], key=len)

    supersedes_rules = rules.get("supersedes", {}) if isinstance(rules.get("supersedes"), dict) else {}

    docs = {}
    for i, rec in enumerate(files):
        if rec.get("is_symlink") or not rec.get("hash"):
            continue
        stem = os.path.splitext(os.path.basename(rec["path"]))[0]
        base, label, sort_key, date = ver_key(stem)
        if not base:
            base = stem.lower()
        docs.setdefault(base, []).append({
            "idx": i, "path": rec["path"], "label": label or "unlabeled",
            "sort_key": list(sort_key), "sha256": rec.get("hash"),
            "mtime": rec.get("mtime"), "size": rec.get("size"), "date": date,
        })

    documents = []
    # 预计算: 被认领为重复副本的路径(其内容与某文档某版本完全一致)
    claimed = set()
    for base, vers in docs.items():
        own = {x["path"] for x in vers}
        for v in vers:
            for i in by_hash.get(v["sha256"], []):
                p = files[i]["path"]
                if p != v["path"] and p not in own:
                    claimed.add(p)
    for base, vers in sorted(docs.items()):
        if all(v["path"] in claimed for v in vers):
            continue  # 整组皆为重复副本, 归入原版本链, 不单独成文档
        vers.sort(key=lambda v: (v["sort_key"][0] != "num" and v["sort_key"][0] != "date",
                                 v["sort_key"][2] if len(v["sort_key"]) > 2 else 0,
                                 v["mtime"] or 0))
        chain = []
        for v in vers:
            entry = {"path": v["path"], "label": v["label"],
                     "sha256": v["sha256"], "mtime": v["mtime"],
                     "size": v["size"]}
            sibs = [p for p in sorted(claimed)
                    if p in {files[i]["path"] for i in by_hash.get(v["sha256"], [])}]
            if sibs:
                entry["duplicate_paths"] = sibs
            chain.append(entry)
        for j in range(1, len(chain)):
            chain[j]["supersedes"] = chain[j - 1]["path"]
        for j, v in enumerate(vers):
            sup = supersedes_rules.get(v["path"])
            if sup:
                chain[j]["supersedes"] = sup
                chain[j]["supersedes_source"] = "rules"
        canon = None
        rule_canon = rules.get("canonical")
        if isinstance(rule_canon, dict):
            canon = rule_canon.get(base) or rule_canon.get("base:" + base)
        if canon is None and chain:
            labeled = [c for c in chain if c.get("supersedes")]
            canon = (labeled[-1]["path"] if labeled else min(
                (c["path"] for c in chain), key=len))
        documents.append({"doc_base": base, "canonical": canon,
                          "versions": chain, "n_versions": len(chain)})

    # 别名: 忽略大小写与扩展名的同名文件
    by_stem = {}
    for rec in files:
        stem = os.path.splitext(os.path.basename(rec["path"]))[0].lower()
        by_stem.setdefault(stem, []).append(rec["path"])
    aliases = [{"stem": k, "paths": v} for k, v in by_stem.items() if len(v) > 1]

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "tool": "kb_versions.py",
        "rules_applied": bool(rules),
        "rules": rules,
        "duplicate_groups": dup_groups,
        "alias_groups": aliases,
        "documents": documents,
        "notes": rules.get("notes"),
    }
    out_path = os.path.join(args.work, "versions.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    multi = [d for d in documents if d["n_versions"] > 1]
    summary = ("# 版本/去重摘要: documents=%d 多版本文档=%d 重复组=%d 别名组=%d rules_applied=%s\n"
               % (len(documents), len(multi), len(dup_groups), len(aliases), bool(rules)))
    for d in multi:
        summary += "- %s -> canonical=%s (%d versions)\n" % (
            d["doc_base"], d["canonical"], d["n_versions"])
    for g in dup_groups:
        summary += "- duplicate %s... paths=%s canonical=%s\n" % (
            g["sha256"][:12], g["paths"], g["canonical"])
    with open(os.path.join(args.work, "versions_summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary)
    sys.stdout.write(summary)


if __name__ == "__main__":
    main()
