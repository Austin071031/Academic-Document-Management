#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lineage.py — 【版本2 旗舰】版本谱系与重复检测引擎。

判定关系（对文档两两比较）：
- duplicate_exact : sha256 相同 → 逐字节重复，只算一份证据。
- renamed_copy    : 内容相同(哈希等)但文件名不同（改名副本）。
- revision_of     : 相似度≥0.60 且版本标签/日期可排序 → 旧版本修订链。
- related         : 相似度≥0.30（共享段落/数据说明）→ 弱关联。
每个簇推举 canonical 版本（版本标签最高、日期最新者优先），
检索时副本不作独立证据，报告中标注 version_role。

输出: <work-dir>/lineage.json
  - clusters: [{canonical, members:[{doc_id,path,role,version_tag,date,sha256,similarity_to_canonical}]}]
  - version_graph: {nodes, edges:[{a,b,relation,similarity,basis}]}
  - exclude_sha256: 副本/旧版本哈希清单（供检索 --filter 排除）
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Journal, norm_basename, read_json, stage_rank,
                    tokenize, version_tags, write_json)


def shingles(tokens, k=8):
    """词级 shingle 集合（拉丁词按 5-gram、CJK bigram 流按 10 窗）。"""
    lat = [t for t in tokens if t.isascii()]
    cjk = [t for t in tokens if not t.isascii()]
    s = set()
    for i in range(max(0, len(lat) - 4)):
        s.add("L:" + "|".join(lat[i:i + 5]))
    for i in range(max(0, len(cjk) - 9)):
        s.add("C:" + "|".join(cjk[i:i + 10]))
    return s


def jaccard(a, b):
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def doc_tokens(corpus, doc):
    text = "\n".join(p.get("text", "") for p in doc.get("pages", []))
    return tokenize(text)


def parse_date(name, mtime):
    m = re.search(r"(20\d{2})[-_.年](\d{1,2})[-_.月]?(\d{1,2})?", name)
    if m:
        d = m.group(3) or "01"
        return "%04d-%02d-%02d" % (int(m.group(1)), int(m.group(2)), int(d))
    m = re.search(r"(20\d{2})(\d{2})(\d{2})", name)
    if m:
        return "%s-%s-%s" % m.groups()
    return (mtime or "")[:10] or None


def version_sort_key(doc):
    tags = doc.get("version_tags") or []
    rank = stage_rank(doc.get("path", ""))
    ver = 0.0
    for t in tags:
        m = re.search(r"(\d+(?:\.\d+)*)", t)
        if m:
            try:
                ver = max(ver, float(m.group(1)))
            except ValueError:
                pass
    return (rank, ver, parse_date(doc.get("path", ""), doc.get("mtime")) or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--sim-rev", type=float, default=0.60)
    ap.add_argument("--sim-rel", type=float, default=0.30)
    a = ap.parse_args()

    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    corpus = read_json(os.path.join(a.work_dir, "corpus.json"), {}) or {}
    inv = read_json(os.path.join(a.work_dir, "inventory.json"), {}) or {}
    mtime_by_path = {f["path"]: f.get("mtime") for f in inv.get("files", [])}
    docs = corpus.get("docs", [])
    for d in docs:
        d["mtime"] = mtime_by_path.get(d.get("path"))

    # 1) 精确重复（哈希）
    by_hash = {}
    for d in docs:
        if d.get("sha256"):
            by_hash.setdefault(d["sha256"], []).append(d)

    edges = []
    clusters = []
    assigned = set()

    for h, members in by_hash.items():
        if len(members) < 2:
            continue
        ordered = sorted(members, key=version_sort_key, reverse=True)
        canonical = ordered[0]
        cluster = {"cluster_id": "c%03d" % (len(clusters) + 1),
                   "relation": "duplicate_exact",
                   "canonical": canonical["doc_id"],
                   "members": []}
        for m in ordered:
            role = "canonical" if m is canonical else \
                ("renamed_copy" if norm_basename(m["name"]) !=
                 norm_basename(canonical["name"]) else "exact_copy")
            cluster["members"].append({
                "doc_id": m["doc_id"], "path": m.get("path"),
                "sha256": h, "role": role,
                "version_tags": m.get("version_tags") or [],
                "date": parse_date(m.get("path", ""), m.get("mtime")),
                "similarity_to_canonical": 1.0})
            assigned.add(m["doc_id"])
            if m is not canonical:
                edges.append({"a": m["doc_id"], "b": canonical["doc_id"],
                              "relation": role, "similarity": 1.0,
                              "basis": "sha256 equal"})
        clusters.append(cluster)

    # 2) 内容相似（shingle Jaccard）
    tokens_of = {d["doc_id"]: doc_tokens(corpus, d) for d in docs
                 if d["doc_id"] not in assigned and d.get("char_total")}
    shingle_of = {k: shingles(v) for k, v in tokens_of.items()}
    ids = sorted(shingle_of)
    for i in range(len(ids)):
        for j in range(i + 1, len(ids)):
            sim = jaccard(shingle_of[ids[i]], shingle_of[ids[j]])
            if sim >= a.sim_rel:
                di = next(d for d in docs if d["doc_id"] == ids[i])
                dj = next(d for d in docs if d["doc_id"] == ids[j])
                if sim >= a.sim_rev:
                    rel = "revision_candidate"
                else:
                    rel = "related_content"
                edges.append({"a": ids[i], "b": ids[j], "relation": rel,
                              "similarity": round(sim, 3),
                              "basis": "shingle jaccard"})

    # 3) 修订链聚簇（连通分量，取相似度≥sim_rev 的边）
    parent = {k: k for k in ids}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    rev_edges = [e for e in edges if e["relation"] == "revision_candidate"]
    for e in rev_edges:
        ra, rb = find(e["a"]), find(e["b"])
        if ra != rb:
            parent[rb] = ra
    groups = {}
    for k in ids:
        groups.setdefault(find(k), []).append(k)
    for root, members in groups.items():
        if len(members) < 2:
            continue
        mdocs = sorted((next(d for d in docs if d["doc_id"] == m) for m in members),
                       key=version_sort_key, reverse=True)
        canonical = mdocs[0]
        sims = {e["a"]: e["similarity"] for e in rev_edges if e["b"] == canonical["doc_id"]}
        sims.update({e["b"]: e["similarity"] for e in rev_edges
                     if e["a"] == canonical["doc_id"]})
        cluster = {"cluster_id": "c%03d" % (len(clusters) + 1),
                   "relation": "revision_chain", "canonical": canonical["doc_id"],
                   "members": []}
        for m in mdocs:
            role = "canonical" if m is canonical else \
                ("older_revision" if m is mdocs[-1] else "intermediate_revision")
            cluster["members"].append({
                "doc_id": m["doc_id"], "path": m.get("path"),
                "sha256": m.get("sha256"), "role": role,
                "version_tags": m.get("version_tags") or [],
                "date": parse_date(m.get("path", ""), m.get("mtime")),
                "similarity_to_canonical": sims.get(m["doc_id"])})
            assigned.add(m["doc_id"])
        clusters.append(cluster)

    # 4) 孤立文档
    for d in docs:
        if d["doc_id"] not in assigned:
            clusters.append({"cluster_id": "c%03d" % (len(clusters) + 1),
                             "relation": "singleton",
                             "canonical": d["doc_id"],
                             "members": [{"doc_id": d["doc_id"],
                                          "path": d.get("path"),
                                          "sha256": d.get("sha256"),
                                          "role": "only_version",
                                          "version_tags": d.get("version_tags") or [],
                                          "date": parse_date(d.get("path", ""),
                                                             d.get("mtime")),
                                          "similarity_to_canonical": 1.0}]})

    exclude = []
    for c in clusters:
        for m in c["members"]:
            if m["role"] in ("exact_copy", "renamed_copy", "older_revision",
                             "intermediate_revision") and m.get("sha256"):
                exclude.append(m["sha256"])

    # 元数据字段（供清单/检索）
    meta = {}
    for c in clusters:
        for m in c["members"]:
            meta[m["doc_id"]] = {
                "version_role": m["role"],
                "cluster_id": c["cluster_id"],
                "is_canonical": m["doc_id"] == c["canonical"],
                "version_tag": (m["version_tags"] or [None])[0],
                "date": m["date"],
            }

    out = write_json(os.path.join(a.work_dir, "lineage.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "clusters": clusters,
        "version_graph": {"nodes": [d["doc_id"] for d in docs], "edges": edges},
        "exclude_sha256": sorted(set(exclude)),
        "doc_meta": meta,
        "stats": {"clusters": len(clusters),
                  "duplicate_pairs": sum(1 for e in edges
                                         if e["relation"] in
                                         ("exact_copy", "renamed_copy")),
                  "revision_edges": len(rev_edges),
                  "canonical_docs": len({c["canonical"] for c in clusters})},
    })
    journal.log("2.5-lineage", "clusters=%d revision_edges=%d"
                % (len(clusters), len(rev_edges)), outputs=[out])
    print(json.dumps(read_json(out)["stats"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
