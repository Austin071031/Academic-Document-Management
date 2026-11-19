#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_from_content.py —— 内容嗅探器。

- 文本类（txt/md/csv/json/log/rst/tex/yaml/yml/xml/tsv/无扩展名）：只读前 64KB，
  编码按 utf-8-sig/utf-8/gb18030/utf-16 依次尝试并记录实际使用编码；
  按字段字典 content_sniffers 正则嗅探 DOI/日期/项目号/仪器型号等；
  md 的 '# ' 标题行、或首条 <=120 字符非空行产出 title 候选（置信度下调）。
- PDF：环境有 pdftotext 则 subprocess 调用（前 3 页），套用同一组嗅探器；
  找不到则登记 source=content, status=unreadable（绝不静默跳过）。
- 其他二进制：登记 skipped，不猜。
单文件失败不崩溃。
"""
import argparse
import os
import re
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

TEXT_EXTS = {"txt", "md", "csv", "json", "log", "rst", "tex", "yaml", "yml",
             "xml", "tsv", "ini", "cfg", ""}
FLAGS = {"IGNORECASE": re.IGNORECASE, "MULTILINE": re.MULTILINE}


def compile_sniffers(dictionary):
    out = []
    for s in dictionary.get("content_sniffers") or []:
        fl = 0
        for f in s.get("flags") or []:
            fl |= FLAGS.get(f, 0)
        try:
            out.append((s["field"], re.compile(s["regex"], fl), int(s.get("group", 1))))
        except (re.error, KeyError, ValueError) as e:
            sys.stderr.write("[content] bad sniffer %s: %s\n" % (s.get("field"), e))
    return out


def sniff_text(text, sniffers, relpath, via):
    """对一段文本套用全部嗅探器 + 标题行启发式，返回候选列表。"""
    cands = []
    for field, rx, grp in sniffers:
        m = rx.search(text)
        if not m:
            continue
        try:
            val = m.group(grp)
        except IndexError:
            continue
        if val is None:
            continue
        val = val.strip().strip("，。；; ")
        if not val:
            continue
        cands.append(lc.candidate(
            relpath, field, val, "content",
            "sniffer regex on first 64KB of content (%s): /%s/" % (via, rx.pattern)))
    # 标题行启发式：md '# ' 优先，其次首条短非空行
    title, tline = None, None
    for line in text.splitlines()[:40]:
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            tline = s.lstrip("#").strip()
            title = tline
            break
        if title is None and len(s) <= 120 and not s.startswith(("{", "[", "<")):
            title = s
            tline = s
        if title:
            break
    if title:
        c = lc.candidate(relpath, "title", title, "content",
                         "first title-like line (%s): '%s'" % (via, (tline or "")[:80]))
        c["confidence"] = 0.65  # 启发式标题，低于结构化嗅探
        cands.append(c)
    return cands


def pdf_text(path):
    """调用 pdftotext（若存在）抽取前 3 页文本；返回 (text_or_None, note)。"""
    exe = shutil.which("pdftotext")
    if not exe:
        return None, "pdftotext not found in PATH"
    try:
        p = subprocess.run([exe, "-l", "3", path, "-"],
                           capture_output=True, timeout=60)
    except Exception as e:
        return None, "pdftotext invocation failed: %s" % e
    if p.returncode != 0:
        return None, "pdftotext exit=%d: %s" % (p.returncode,
                                                p.stderr.decode("utf-8", "replace")[:200])
    text, enc, warn = lc.decode_bytes(p.stdout[:lc.SNIFF_BYTES])
    note = "pdftotext first 3 pages, decoded as %s" % enc
    if warn:
        note += " (%s)" % warn
    if not text.strip():
        return None, "pdftotext produced empty text (可能无文本层/扫描件)"
    return text, note


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    dictionary = lc.load_dictionary(a.work, a.config)
    sniffers = compile_sniffers(dictionary)
    cands, unreadable, skipped = [], [], []

    for rec in lc.jlines(os.path.join(a.work, "files.jsonl")):
        if not rec.get("readable"):
            continue
        path = rec.get("abspath") or os.path.join(a.input, rec["relpath"])
        ext = rec.get("ext", "")
        try:
            if ext == "pdf":
                text, note = pdf_text(path)
                if text is None:
                    unreadable.append({"file": rec["relpath"], "source": "content",
                                       "status": "unreadable", "reason": note})
                    continue
                cands.extend(sniff_text(text, sniffers, rec["relpath"], "pdf:" + note))
            elif ext in TEXT_EXTS:
                try:
                    text, enc, warn = lc.read_text_head(path)
                except OSError as e:
                    unreadable.append({"file": rec["relpath"], "source": "content",
                                       "status": "unreadable", "reason": "read: %s" % e})
                    continue
                via = "text decoded as %s" % enc + (" (%s)" % warn if warn else "")
                cands.extend(sniff_text(text, sniffers, rec["relpath"], via))
            else:
                skipped.append({"file": rec["relpath"], "source": "content",
                                "status": "skipped",
                                "reason": "binary/unsupported ext '.%s'，不猜测内容" % ext})
        except Exception as e:  # 单文件失败不崩溃
            unreadable.append({"file": rec["relpath"], "source": "content",
                               "status": "unreadable",
                               "reason": "%s: %s" % (type(e).__name__, e)})

    lc.jappend(os.path.join(a.work, "candidates.jsonl"), cands)
    lc.jappend(os.path.join(a.work, "content_unreadable.jsonl"), unreadable)
    lc.jappend(os.path.join(a.work, "content_skipped.jsonl"), skipped)
    lc.log_change(a.work, "extract_content", "candidates.jsonl",
                  "first-64KB sniffing; pdftotext optional",
                  "%d candidates; %d unreadable; %d skipped"
                  % (len(cands), len(unreadable), len(skipped)))
    print("[content] candidates=%d unreadable=%d skipped=%d"
          % (len(cands), len(unreadable), len(skipped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
