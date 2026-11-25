#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step6 render_evidence：把版本谱系与整理结果渲染成**真实可检查的证据图**。

动机：基座只输出 versions.dot（Graphviz 文本），评测环境大概率没有
graphviz，文字版谱系图无法作为视觉证据。本模块**纯标准库手写 SVG**
（XML 文本，UTF-8，中文安全，本身就是可编辑矢量图源）：

- <output>/library/evidence/lineage.svg       版本谱系 DAG（必须产出）
- <output>/library/evidence/tree_overview.svg 规范目录树概览（必须产出）
- <output>/library/evidence/lineage.png       PNG 预览（尽力：
  仅当环境装有 matplotlib 时渲染；缺失时登记
  "matplotlib unavailable, SVG only" 进 warnings → uncertainty/result.json，
  绝不报错崩溃）

任何单图失败都被捕获并记入返回的 warnings，不影响其它产物。
"""
import argparse
import os
import sys
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cas_common import ensure_dir, read_json

MAX_TREE_LINES = 300
NODE_H = 46
NODE_PAD = 14
CHAR_W_ASCII = 7.5
CHAR_W_WIDE = 14.0


def text_width(s):
    """按字符粗略估算像素宽（CJK/全角按宽字符计）。"""
    w = 0.0
    for ch in str(s):
        w += CHAR_W_WIDE if ord(ch) > 0x2E80 else CHAR_W_ASCII
    return w


def _t(x, y, s, size=12, anchor="start", fill="#222", mono=False, extra=""):
    fam = "monospace" if mono else "sans-serif"
    return ('<text x="%.1f" y="%.1f" font-size="%d" font-family="%s" '
            'text-anchor="%s" fill="%s" %s>%s</text>'
            % (x, y, size, fam, anchor, fill, extra, escape(str(s))))


def _svg_doc(width, height, body):
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d">\n'
            '<rect width="%d" height="%d" fill="#ffffff"/>\n%s\n</svg>\n'
            % (width, height, width, height, width, height, "\n".join(body)))


def render_lineage_svg(versions):
    """版本谱系 DAG → SVG。节点按簇分行、簇内按 mtime 旧→新排列，
    supersedes 边由新节点指向旧节点（箭头朝旧）。"""
    nodes = {n["content_id"]: n for n in versions.get("nodes", [])}
    edges = versions.get("edges", [])
    clusters = versions.get("clusters", [])
    dup_groups = versions.get("duplicate_groups", [])

    body, pos = [], {}
    y = 56
    body.append(_t(20, 30, "版本谱系 DAG（content-addressed lineage）",
                   size=18, fill="#111"))
    body.append(_t(20, 48,
                   "节点=唯一内容(sha256)；实线箭头=supersedes（新→旧）；"
                   "簇内按 mtime 旧→新 排列", size=11, fill="#666"))

    cluster_ids = [c["cluster_id"] for c in clusters]
    for ci, cid in enumerate(cluster_ids):
        members = clusters[ci]["members"]
        x = 30.0
        row_y = y
        body.append(_t(20, row_y - 14, "版本簇 %s（%d 个版本）"
                       % (cid, len(members)), size=12, fill="#0b5cad"))
        max_label_w = 0.0
        for mid in members:
            n = nodes.get(mid)
            if not n:
                continue
            base = os.path.basename(n.get("path") or mid[:12])
            alias = len(n.get("all_paths", [])) or 1
            label1 = "%s…" % mid[:12]
            label2 = base[:38] + ("  [别名×%d]" % alias if alias > 1 else "")
            w = max(text_width(label1), text_width(label2)) + 2 * NODE_PAD
            w = max(w, 130)
            max_label_w = max(max_label_w, w)
            pos[mid] = (x, row_y, w)
            x += w + 110  # 边 label 空间
        y = row_y + NODE_H + 64

    if not clusters:
        body.append(_t(20, y - 20, "（未检测到多版本簇；全部内容均为唯一版本）",
                       size=12, fill="#888"))
        y += 30

    # 节点矩形
    for mid, (x, ry, w) in pos.items():
        n = nodes[mid]
        base = os.path.basename(n.get("path") or mid[:12])
        alias = len(n.get("all_paths", [])) or 1
        label2 = base[:38] + ("  [别名×%d]" % alias if alias > 1 else "")
        body.append('<rect x="%.1f" y="%.1f" width="%.1f" height="%d" rx="6" '
                    'fill="#eef4ff" stroke="#0b5cad" stroke-width="1.4"/>'
                    % (x, ry, w, NODE_H))
        body.append(_t(x + w / 2, ry + 18, "%s…" % mid[:12], size=11,
                       anchor="middle", mono=True, fill="#0b3d79"))
        body.append(_t(x + w / 2, ry + 36, label2, size=11, anchor="middle"))

    # supersedes 边（新 → 旧，箭头朝左/旧）
    for e in edges:
        if e["from"] not in pos or e["to"] not in pos:
            continue
        xf, yf, wf = pos[e["from"]]
        xt, yt, wt = pos[e["to"]]
        x1, y1 = xf, yf + NODE_H / 2
        x2, y2 = xt + wt, yt + NODE_H / 2
        mx = (x1 + x2) / 2
        body.append('<path d="M %.1f %.1f C %.1f %.1f, %.1f %.1f, %.1f %.1f" '
                    'fill="none" stroke="#c0392b" stroke-width="1.6" '
                    'marker-end="url(#arr)"/>' % (x1, y1, mx, y1, mx, y2,
                                                  x2 + 2, y2))
        lab = "supersedes sim=%s +%d/-%d" % (
            e.get("similarity"), e.get("diff_summary", {}).get("lines_added", 0),
            e.get("diff_summary", {}).get("lines_removed", 0))
        body.append(_t(mx, min(y1, y2) - 8, lab, size=10, anchor="middle",
                       fill="#c0392b"))

    # 精确重复组清单（别名证据）
    if dup_groups:
        y += 6
        body.append(_t(20, y, "精确重复组（内容相同、文件名不同；sha256 一致）",
                       size=13, fill="#6c3483"))
        y += 20
        for g in dup_groups[:20]:
            paths = " = ".join(os.path.basename(p) for p in g.get("paths", []))
            body.append(_t(30, y, "sha256=%s… ×%d: %s"
                           % (g.get("sha256", "")[:12], g.get("count", 0),
                              paths[:110]), size=11, mono=True, fill="#444"))
            y += 17

    height = int(y + 30)
    width = int(max([650] + [v[0] + v[2] + 40 for v in pos.values()]))
    defs = ('<defs><marker id="arr" markerWidth="9" markerHeight="9" refX="7" '
            'refY="4.5" orient="auto"><path d="M0,0 L8,4.5 L0,9 z" '
            'fill="#c0392b"/></marker></defs>')
    return _svg_doc(width, height, [defs] + body)


def render_tree_svg(index):
    """规范目录树概览 → SVG（等宽缩进树形文本，含统计头）。"""
    files = index.get("files", [])
    stats = index.get("stats", {})
    tree = {}
    for f in files:
        tp = f.get("tree_path")
        if not tp:
            continue
        parts = tp[len("tree/"):] if tp.startswith("tree/") else tp
        node = tree
        for seg in parts.split("/"):
            node = node.setdefault(seg, {})

    lines = ["tree/"]
    truncated = [False]

    def walk(node, prefix, depth):
        if len(lines) >= MAX_TREE_LINES:
            truncated[0] = True
            return
        keys = sorted(node.keys(),
                      key=lambda k: (bool(node[k]), k))
        for i, k in enumerate(keys):
            last = i == len(keys) - 1
            lines.append(prefix + ("└── " if last else "├── ") + k)
            if node[k]:
                walk(node[k], prefix + ("    " if last else "│   "),
                     depth + 1)

    walk(tree, "", 0)
    if truncated[0]:
        lines.append("……（超出 %d 行，已截断；完整见 library/index.json）"
                     % MAX_TREE_LINES)

    header = ["规范目录树概览（library/tree/）",
              "已索引文件 %s · 唯一内容 %s · 冲突改名 __dupN %s · 跳过 %s"
              % (stats.get("indexed_files", 0), stats.get("unique_contents", 0),
                 stats.get("tree_conflicts_renamed", 0),
                 stats.get("skipped_files", 0))]
    body = [_t(20, 30, header[0], size=18, fill="#111"),
            _t(20, 50, header[1], size=11, fill="#666")]
    y = 76
    for ln in lines:
        body.append(_t(20, y, ln, size=12, mono=True,
                       fill="#222" if ln.endswith("/") or "├──" in ln
                       or "└──" in ln else "#333"))
        y += 17
    width = int(max([640] + [text_width(l) + 60 for l in lines])) 
    return _svg_doc(min(width, 2400), y + 20, body)


def render_lineage_png(versions, png_path):
    """尽力用 matplotlib 渲染 PNG 预览。成功返回 None，失败返回原因字符串。"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception:
        return "matplotlib unavailable, SVG only"
    try:
        for fam in ("Noto Sans CJK SC", "WenQuanYi Zen Hei",
                    "Microsoft YaHei", "SimHei", "Arial Unicode MS"):
            try:
                from matplotlib import font_manager
                if any(f.name == fam for f in font_manager.fontManager.ttflist):
                    plt.rcParams["font.family"] = fam
                    break
            except Exception:
                break
        nodes = {n["content_id"]: n for n in versions.get("nodes", [])}
        edges = versions.get("edges", [])
        clusters = versions.get("clusters", [])
        pos = {}
        fig, ax = plt.subplots(figsize=(max(8, 3 * max(1, max(
            (len(c["members"]) for c in clusters), default=1))),
            max(4, 1.6 * max(1, len(clusters)))))
        for row, c in enumerate(clusters):
            for col, mid in enumerate(c["members"]):
                pos[mid] = (col, -row)
        for mid, (x, y) in pos.items():
            n = nodes.get(mid, {})
            base = os.path.basename(n.get("path") or mid[:12])
            ax.add_patch(plt.Rectangle((x - 0.42, y - 0.2), 0.84, 0.4,
                                       facecolor="#eef4ff",
                                       edgecolor="#0b5cad"))
            ax.text(x, y + 0.06, "%s…" % mid[:10], ha="center", fontsize=7,
                    family="monospace")
            ax.text(x, y - 0.09, base[:26], ha="center", fontsize=7)
        for e in edges:
            if e["from"] in pos and e["to"] in pos:
                x1, y1 = pos[e["from"]]
                x2, y2 = pos[e["to"]]
                ax.annotate("", xy=(x2 + 0.44, y2), xytext=(x1 - 0.44, y1),
                            arrowprops=dict(arrowstyle="->", color="#c0392b"))
                ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.14,
                        "sim=%s" % e.get("similarity"), fontsize=6,
                        color="#c0392b", ha="center")
        ax.set_title("版本谱系 DAG / lineage (supersedes: new -> old)")
        ax.autoscale_view()
        ax.set_axis_off()
        import warnings
        with warnings.catch_warnings():  # 缺 CJK 字体时的字形告警不刷屏
            warnings.simplefilter("ignore")
            fig.savefig(png_path, dpi=150, bbox_inches="tight")
        plt.close(fig)
        return None
    except Exception as e:  # 渲染失败不崩溃，登记原因
        return "matplotlib render failed: %s: %s" % (type(e).__name__, e)


def render(input_dir, work_dir, output_dir):
    """渲染全部证据图。返回 {artifacts, warnings}（warnings 供 uncertainty）。"""
    library = os.path.join(output_dir, "library")
    ev_dir = ensure_dir(os.path.join(library, "evidence"))
    versions = read_json(os.path.join(library, "versions.json")) or {}
    index = read_json(os.path.join(library, "index.json")) or {}
    artifacts, warnings = {}, []

    try:
        svg = render_lineage_svg(versions)
        p = os.path.join(ev_dir, "lineage.svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(svg)
        artifacts["lineage_svg"] = "library/evidence/lineage.svg"
    except Exception as e:
        warnings.append("lineage.svg 渲染失败: %s: %s" % (type(e).__name__, e))

    try:
        svg = render_tree_svg(index)
        p = os.path.join(ev_dir, "tree_overview.svg")
        with open(p, "w", encoding="utf-8") as f:
            f.write(svg)
        artifacts["tree_overview_svg"] = "library/evidence/tree_overview.svg"
    except Exception as e:
        warnings.append("tree_overview.svg 渲染失败: %s: %s"
                        % (type(e).__name__, e))

    err = render_lineage_png(versions, os.path.join(ev_dir, "lineage.png"))
    if err is None:
        artifacts["lineage_png"] = "library/evidence/lineage.png"
    else:
        warnings.append(err)

    stats = {"artifacts": artifacts, "warnings": warnings,
             "nodes": len(versions.get("nodes", [])),
             "edges": len(versions.get("edges", [])),
             "duplicate_groups": len(versions.get("duplicate_groups", []))}
    from cas_common import write_json
    write_json(os.path.join(work_dir, "render_summary.json"), stats)
    return stats


def main():
    ap = argparse.ArgumentParser(description="渲染版本谱系/目录树证据图")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    s = render(a.input, a.work, a.output)
    print("render ok: artifacts=%s warnings=%s"
          % (sorted(s["artifacts"]), s["warnings"]))


if __name__ == "__main__":
    main()
