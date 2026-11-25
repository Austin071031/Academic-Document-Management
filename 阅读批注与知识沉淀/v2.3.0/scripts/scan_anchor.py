#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scan_anchor.py — 批注锚点校正模块（v2.3.0 方向）

覆盖题面两类锚点错位痛点：
1. 双栏排版被串行读取：pdftotext 内容流顺序把左右栏同行文字交错拼接，
   跨行引文的锚点校验失败。column_reorder() 按 x 坐标直方图分栏、栏内按
   阅读顺序重排，给出"分栏校正后页文本"用于二次校验。
2. 无文本层扫描件：tesseract 可用时渲染页 + TSV 取词（含坐标），把批注
   quad（PDF 坐标）映射到 OCR 词，恢复引文（置信度较低，明确标注）；
   tesseract 不可用时如实降级为"仅几何锚点"，不编造文字。

用法（库）：
  from scan_anchor import column_reorder, words_to_text, ocr_page_words
"""
import os
import re
import shutil
import subprocess


def _line_key(w):
    return (round(w[1], 1), w[0])


def detect_columns(words, page_width, min_gap_ratio=0.08):
    """按词块 x 区间聚栏。返回 [(x0,x1), ...] 栏边界（按 x 升序）。单栏返回 None。"""
    if not words or not page_width:
        return None
    xs = sorted((w[0], w[2]) for w in words)
    # 行间 x 覆盖投影：统计每个词 x0 的分布，找中部大间隙
    starts = sorted(w[0] for w in words)
    gaps = []
    for i in range(1, len(starts)):
        gaps.append((starts[i] - starts[i - 1], (starts[i - 1] + starts[i]) / 2))
    big = [g for g in gaps if g[0] > page_width * min_gap_ratio and page_width * 0.25 < g[1] < page_width * 0.75]
    if not big:
        return None
    split = max(big)[1]
    return [(0.0, split), (split, page_width)]


def column_reorder(words, page_width):
    """双栏校正：若检测到分栏，先左栏后右栏各自按阅读顺序排序，返回重排词列表。"""
    cols = detect_columns(words, page_width)
    if not cols:
        return None  # 单栏：无需校正
    out = []
    for x0, x1 in cols:
        col = [w for w in words if (w[0] + w[2]) / 2 >= x0 and (w[0] + w[2]) / 2 < x1]
        col.sort(key=_line_key)
        out.extend(col)
    return out


def words_to_text(words):
    """词列表 → 文本。**按输入顺序**处理（column_reorder 的输出顺序即阅读顺序），
    仅按 y 相邻度分行，不重排序——重排会把分栏顺序再次打散。"""
    lines = []
    cur_y, cur = None, []
    for w in words:
        if cur_y is None or abs(w[1] - cur_y) <= 2.0:
            cur.append(w[4])
            cur_y = w[1] if cur_y is None else (cur_y + w[1]) / 2
        else:
            lines.append(" ".join(cur))
            cur, cur_y = [w[4]], w[1]
    if cur:
        lines.append(" ".join(cur))
    return "\n".join(lines)


def ocr_page_words(pdf_path, pno, dpi=200, events=None):
    """扫描页 OCR：渲染整页 → tesseract TSV → [(x0,y0,x1,y1,text), ...]（PDF 点坐标）。
    tesseract 不可用返回 (None, 'unavailable')；失败返回 (None, reason)。"""
    tess = shutil.which("tesseract")
    if not tess:
        return None, "tesseract unavailable"
    import tempfile
    scale = dpi / 72.0
    with tempfile.TemporaryDirectory() as td:
        prefix = os.path.join(td, "pg")
        try:
            subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-f", str(pno + 1),
                            "-l", str(pno + 1), pdf_path, prefix],
                           check=True, capture_output=True, timeout=180)
            png = "%s-%d.png" % (prefix, pno + 1)
            r = subprocess.run([tess, png, "stdout", "-l", "eng+chi_sim", "tsv"],
                               capture_output=True, timeout=180)
            tsv = r.stdout.decode("utf-8", "replace")
        except Exception as e:
            return None, "ocr failed: %s" % e
    words = []
    for line in tsv.splitlines()[1:]:
        parts = line.split("\t")
        if len(parts) == 12 and parts[11].strip():
            try:
                x, y, w, h = (float(parts[6]), float(parts[7]), float(parts[8]), float(parts[9]))
                conf = float(parts[10])
            except ValueError:
                continue
            if conf < 0:
                continue
            words.append((x / scale, y / scale, (x + w) / scale, (y + h) / scale,
                          parts[11].strip(), conf))
    return words, "tesseract-tsv"
