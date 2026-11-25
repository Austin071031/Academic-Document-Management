#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step3 lineage：版本谱系图谱（DAG）。

1) 按 sha256 分组 → 精确重复（别名/副本），内容级去重，与文件名无关。
2) 文本类文件两两 difflib 相似度 → 并查集聚类成版本簇。
3) 簇内按 mtime 排序建版本链，相邻版本之间生成谱系边：
   relation="supersedes"（from=新版本 → to=旧版本，新版本取代旧版本），
   附 inverse="superseded_by"、similarity、diff_summary（行增删数）。

产物：
- <output>/library/versions.json  nodes/edges/duplicate_groups/clusters
- <output>/library/versions.dot   Graphviz DOT 文本，可被第三方直接渲染复跑核对
"""
import argparse
import difflib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cas_common import read_text, write_json

SIM_THRESHOLD = 0.40
MAX_TEXT_BYTES = 262144


class UnionFind:
    def __init__(self):
        self.parent = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[ra] = rb


def diff_summary(old_lines, new_lines):
    """unified diff 的行增/删计数（不含 +++/--- 头）。"""
    added = removed = 0
    for line in difflib.unified_diff(old_lines, new_lines, lineterm=""):
        if line.startswith("+++") or line.startswith("---"):
            continue
        if line.startswith("+"):
            added += 1
        elif line.startswith("-"):
            removed += 1
    return {"lines_added": added, "lines_removed": removed}


def build_lineage(input_dir, work_dir, output_dir):
    import json
    library = os.path.join(output_dir, "library")
    index_path = os.path.join(library, "index.json")
    with open(index_path, "r", encoding="utf-8") as f:
        index = json.load(f)
    objects_dir = os.path.join(library, "objects")
    entries = index.get("files", [])

    # ---- 1) 精确重复分组（同一 content_id 的多个路径 = 别名/副本）
    by_content = {}
    for e in entries:
        by_content.setdefault(e["content_id"], []).append(e)
    duplicate_groups = []
    for cid, es in sorted(by_content.items()):
        if len(es) > 1:
            duplicate_groups.append({
                "content_id": cid,
                "sha256": cid,
                "paths": sorted(x["source_path"] for x in es),
                "tree_paths": sorted(x["tree_path"] for x in es
                                     if x.get("tree_path")),
                "count": len(es),
            })

    # ---- 2) 文本内容相似度聚类（按内容，不按文件名）
    texts = {}   # content_id -> lines
    rep = {}     # content_id -> representative entry
    for e in entries:
        cid = e["content_id"]
        if cid in rep or not e.get("is_text") or not e.get("tree_path"):
            continue
        obj = os.path.join(objects_dir, cid[:2], cid)
        if not os.path.exists(obj):
            continue
        try:
            texts[cid] = read_text(obj, MAX_TEXT_BYTES).splitlines()
            rep[cid] = e
        except OSError:
            continue

    cids = sorted(texts.keys())
    uf = UnionFind()
    sim_cache = {}
    for i in range(len(cids)):
        for j in range(i + 1, len(cids)):
            a, b = cids[i], cids[j]
            sm = difflib.SequenceMatcher(None, texts[a], texts[b])
            if sm.quick_ratio() < SIM_THRESHOLD:
                continue
            r = sm.ratio()
            if r >= SIM_THRESHOLD and r < 1.0:
                uf.union(a, b)
                sim_cache[(a, b)] = round(r, 4)

    clusters_map = {}
    for cid in cids:
        clusters_map.setdefault(uf.find(cid), []).append(cid)
    clusters = [sorted(v) for v in clusters_map.values() if len(v) > 1]

    # ---- 3) 簇内按 mtime 排序建链，生成谱系边
    nodes, edges = [], []
    cluster_records = []
    for ci, members in enumerate(sorted(clusters, key=len, reverse=True)):
        ordered = sorted(
            members,
            key=lambda c: (rep[c].get("mtime") is None,
                           rep[c].get("mtime") or 0,
                           rep[c]["source_path"]))
        cluster_records.append({"cluster_id": "cluster_%d" % ci,
                                "members": ordered})
        for cid in ordered:
            e = rep[cid]
            nodes.append({
                "content_id": cid,
                "sha256": cid,
                "path": e["source_path"],
                "all_paths": sorted(x["source_path"]
                                    for x in by_content.get(cid, [])),
                "mtime": e.get("mtime"),
                "size": e.get("size"),
                "cluster_id": "cluster_%d" % ci,
            })
        for k in range(len(ordered) - 1):
            older, newer = ordered[k], ordered[k + 1]
            sim = sim_cache.get((older, newer)) or sim_cache.get((newer, older))
            if sim is None:
                sim = round(difflib.SequenceMatcher(
                    None, texts[older], texts[newer]).ratio(), 4)
            edges.append({
                "from": newer,
                "to": older,
                "relation": "supersedes",
                "inverse": "superseded_by",
                "similarity": sim,
                "diff_summary": diff_summary(texts[older], texts[newer]),
                "cluster_id": "cluster_%d" % ci,
            })

    # ---- versions.dot（Graphviz 文本，第三方可直接渲染核对）
    dot = ["digraph versions {", "  rankdir=LR;",
           '  node [shape=box, fontname="sans-serif"];']
    for n in nodes:
        label = "%s…\\n%s" % (n["content_id"][:12],
                              n["path"].replace('"', "'"))
        dot.append('  "%s" [label="%s"];' % (n["content_id"], label))
    for e in edges:
        dot.append('  "%s" -> "%s" [label="supersedes\\nsim=%s +%d/-%d"];'
                   % (e["from"], e["to"], e["similarity"],
                      e["diff_summary"]["lines_added"],
                      e["diff_summary"]["lines_removed"]))
    dot.append("}")

    result = {
        "version": 2,
        "nodes": nodes,
        "edges": edges,
        "duplicate_groups": duplicate_groups,
        "clusters": cluster_records,
        "stats": {
            "duplicate_groups": len(duplicate_groups),
            "version_clusters": len(clusters),
            "supersedes_edges": len(edges),
            "text_contents_compared": len(cids),
        },
        "method": "sha256 精确去重 + difflib 行级相似度(>=0.40)聚类 + "
                  "mtime 排序建链；版本判断按内容不按文件名。",
    }
    write_json(os.path.join(library, "versions.json"), result)
    with open(os.path.join(library, "versions.dot"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(dot) + "\n")
    return result["stats"]


def main():
    ap = argparse.ArgumentParser(description="版本谱系图谱")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    s = build_lineage(a.input, a.work, a.output)
    print("lineage ok: dup_groups=%(duplicate_groups)d "
          "clusters=%(version_clusters)d edges=%(supersedes_edges)d" % s)


if __name__ == "__main__":
    main()
