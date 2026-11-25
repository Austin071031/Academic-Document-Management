#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_extract.py -- 从资料库文件抽取纯文本, 生成逐文件抽取报告。

支持的类型与策略:
  pdf      -> 优先外部 pdftotext(如可用); 输出为空则标记 needs_ocr
  docx     -> zip + word/document.xml 去标签
  pptx     -> zip + 所有 slide XML 去标签
  xlsx     -> zip + sharedStrings.xml 与 sheet XML 去标签
  text     -> 直接按 UTF-8(容错)读取
  image    -> 无可抽文本, 标记 needs_ocr
  其他/失败 -> status=unsupported 或 error, 绝不静默跳过

用法:
  python3 kb_extract.py --inventory /app/work/inventory.json --root /input/library --work /app/work

输出:
  <work>/text/<file_id>.txt      抽取文本(\f 保留 PDF 分页)
  <work>/extract_report.json     每文件 status/chars/pages/方式
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import zipfile

XML_TAG = re.compile(r"<[^>]+>")
WS = re.compile(r"[ \t]+")


def which(cmd):
    for d in os.environ.get("PATH", "").split(os.pathsep):
        p = os.path.join(d, cmd)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


def strip_xml(raw):
    txt = raw.decode("utf-8", errors="replace")
    txt = txt.replace("</w:p>", "\n").replace("</a:p>", "\n").replace("<w:tab/>", "\t")
    txt = txt.replace("</si>", "\n").replace("</row>", "\n").replace("</v>", "\t")
    txt = XML_TAG.sub("", txt)
    import html
    txt = html.unescape(txt)
    lines = [WS.sub(" ", ln).strip() for ln in txt.splitlines()]
    return "\n".join(ln for ln in lines if ln)


def extract_zip_member(path, members):
    try:
        with zipfile.ZipFile(path) as z:
            names = z.namelist()
            picked = [n for n in names for m in members if re.fullmatch(m, n)]
            if not picked:
                return None, "no matching member (have: %s)" % ", ".join(names[:8])
            parts = []
            for n in sorted(picked):
                parts.append(strip_xml(z.read(n)))
            return "\n".join(p for p in parts if p), None
    except zipfile.BadZipFile as exc:
        return None, "bad zip (%s)" % exc
    except Exception as exc:  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, exc)


def extract_pdf(path, pdftotext):
    if not pdftotext:
        return None, "pdftotext not found in PATH", None
    out = path + ".kb.txt"
    try:
        r = subprocess.run([pdftotext, "-layout", path, out],
                           capture_output=True, timeout=120)
        if r.returncode != 0:
            return None, "pdftotext rc=%d: %s" % (r.returncode, r.stderr.decode("utf-8", "replace")[:300]), None
        with open(out, "rb") as f:
            txt = f.read().decode("utf-8", errors="replace")
        os.unlink(out)
        pages = txt.count("\f") + 1
        return txt, None, pages
    except subprocess.TimeoutExpired:
        return None, "pdftotext timeout(120s)", None
    except Exception as exc:  # noqa: BLE001
        return None, "%s: %s" % (type(exc).__name__, exc), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--root", required=True, help="inventory 中相对路径对应的实际根目录")
    ap.add_argument("--work", default="/app/work")
    args = ap.parse_args()

    with open(args.inventory, encoding="utf-8") as f:
        inv = json.load(f)

    text_dir = os.path.join(args.work, "text")
    os.makedirs(text_dir, exist_ok=True)
    pdftotext = which("pdftotext")

    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "tool": "kb_extract.py", "root": args.root, "files": []}
    n_ok = n_empty = n_ocr = n_err = n_unsup = 0

    for i, rec in enumerate(inv.get("files", [])):
        fid = "f%04d" % i
        entry = {"file_id": fid, "path": rec.get("path"), "type": rec.get("type"),
                 "sha256": rec.get("hash")}
        report["files"].append(entry)
        if rec.get("is_symlink"):
            entry.update(status="skipped", reason="symlink")
            continue
        if rec.get("readable") is False:
            entry.update(status="unreadable", reason="permission denied")
            n_err += 1
            continue
        t = rec.get("type")
        full = os.path.join(args.root, rec.get("path", ""))
        if not os.path.isfile(full):
            entry.update(status="missing", reason="file not found under root")
            n_err += 1
            continue
        try:
            if t == "pdf":
                txt, err, pages = extract_pdf(full, pdftotext)
                entry["pages"] = pages
                method = "pdftotext"
            elif t == "docx":
                txt, err = extract_zip_member(full, [r"word/document\.xml"])
                method = "docx-xml"
            elif t == "pptx":
                txt, err = extract_zip_member(full, [r"ppt/slides/slide\d+\.xml"])
                method = "pptx-xml"
            elif t == "xlsx":
                txt, err = extract_zip_member(full, [r"xl/sharedStrings\.xml", r"xl/worksheets/sheet\d+\.xml"])
                method = "xlsx-xml"
            elif t == "text":
                with open(full, "rb") as f:
                    txt = f.read().decode("utf-8", errors="replace")
                err = None
                method = "direct-read"
            elif t == "image":
                entry.update(status="needs_ocr", reason="image without text layer",
                             method="none")
                n_ocr += 1
                continue
            else:
                entry.update(status="unsupported", reason="no extractor for type '%s'" % t)
                n_unsup += 1
                continue
        except Exception as exc:  # noqa: BLE001
            entry.update(status="error", reason="%s: %s" % (type(exc).__name__, exc))
            n_err += 1
            continue
        if err:
            entry.update(status="error", reason=err, method=method)
            n_err += 1
            continue
        txt = txt or ""
        if len(txt.strip()) == 0:
            entry.update(status="needs_ocr", reason="no text layer (likely scanned)",
                         method=method, chars=0)
            n_ocr += 1
            continue
        with open(os.path.join(text_dir, fid + ".txt"), "w", encoding="utf-8") as f:
            f.write(txt)
        entry.update(status="ok", method=method, chars=len(txt))
        n_ok += 1
        n_empty += 0

    report["counts"] = {"ok": n_ok, "needs_ocr": n_ocr, "error": n_err,
                        "unsupported": n_unsup}
    with open(os.path.join(args.work, "extract_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)

    summary = ("# 文本抽取摘要: ok=%d needs_ocr=%d error=%d unsupported=%d (pdftotext=%s)\n"
               % (n_ok, n_ocr, n_err, n_unsup, pdftotext or "NOT FOUND"))
    for e in report["files"]:
        if e["status"] not in ("ok",):
            summary += "- %s [%s] %s: %s\n" % (e["path"], e["status"],
                                               e.get("method", ""), e.get("reason", ""))
    with open(os.path.join(args.work, "extract_summary.txt"), "w", encoding="utf-8") as f:
        f.write(summary)
    sys.stdout.write(summary)


if __name__ == "__main__":
    main()
