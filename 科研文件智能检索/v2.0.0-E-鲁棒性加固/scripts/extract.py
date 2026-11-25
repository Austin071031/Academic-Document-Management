#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract.py — 从各类文件中提取带页码的文本（v2.0.0-E 加固版）。

在核心版基础上增加：RTF 控制字剥离、EML 正文解析（email 标准库）、
zip/tar 归档受控解包（≤20 个文本类成员、单成员≤2MiB）、
OCR 语言包回退（eng+chi_sim 失败自动改 eng）、损坏 PDF 恢复链
（pdftotext 失败后尝试 mutool/qpdf，再失败如实记录）。

策略：
- PDF: pdftotext -layout，按 \f 分页；文本过少判为扫描件，若存在
  tesseract+pdftoppm 则 OCR（页数上限可配），否则诚实记录 no_text_layer。
- DOCX/PPTX/XLSX: 标准库 zipfile+ElementTree 解析 OOXML。
- 纯文本类: 直接读取。
- 任何失败都写入 failures，绝不静默跳过。

用法: python3 extract.py --input-root /input --work-dir /app/work [--ocr-max-pages 40]
输出: <work-dir>/corpus.json
"""
import argparse
import json
import os
import re
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Journal, categorize, norm_text, read_json, run_cmd,
                    which_tools, write_json)

OCR_MIN_CHARS_PER_PAGE = 20   # 低于此均值判为无文本层
DEFAULT_OCR_MAX_PAGES = 40


def extract_pdf(path, tools, ocr_max_pages):
    """返回 (pages, meta, failures)。pages: [{page, text}]。"""
    failures = []
    pages = []
    rc, out, err = run_cmd(["pdftotext", "-enc", "UTF-8", "-layout", path, "-"],
                           timeout=180)
    if rc == 0 and out.strip():
        raw_pages = out.split("\f")
        for i, t in enumerate(raw_pages, 1):
            if i == len(raw_pages) and not t.strip():
                continue
            pages.append({"page": i, "text": t.rstrip("\n")})
    elif rc == 0:
        # 命令成功但无文本输出：无文本层（扫描件）
        meta = {"avg_chars_per_page": 0.0, "page_count": 0}
        meta["scanned"] = True
        if tools.get("tesseract") and tools.get("pdftoppm"):
            ocr_pages, ocr_fail = ocr_pdf(path, ocr_max_pages)
            if ocr_pages:
                meta["ocr_applied"] = True
                meta["ocr_pages"] = len(ocr_pages)
                pages = ocr_pages
            failures.extend(ocr_fail)
        else:
            failures.append({"type": "no_text_layer_ocr_unavailable",
                             "detail": "pdftotext returned no text (scanned) "
                                       "and tesseract/pdftoppm not available"})
        return pages, meta, failures
    elif rc == -2:
        failures.append({"type": "extractor_unavailable",
                         "tool": "pdftotext", "detail": err.strip()[:200]})
    else:
        failures.append({"type": "extract_failed", "tool": "pdftotext",
                         "detail": (err or out).strip()[:200]})
        for tool in ("mutool", "qpdf"):
            tpath = tools.get(tool)
            if not tpath:
                continue
            if tool == "mutool":
                rc2, out2, err2 = run_cmd([tpath, "draw", "-F", "txt", path],
                                          timeout=180)
            else:
                rc2, out2, err2 = run_cmd([tpath, "--qdf", "--object-streams=disable",
                                           path, "-"], timeout=180)
            if rc2 == 0 and out2 and len(out2.strip()) > 20:
                text = out2 if tool == "mutool" else _qdf_text(out2)
                if text.strip():
                    pages.append({"page": 1, "text": text,
                                  "source": tool + "_recovery"})
                    failures.append({"type": "recovered_via_" + tool,
                                     "detail": "pdftotext failed; %s fallback succeeded"
                                               % tool})
                    break

    total_chars = sum(len(p["text"].strip()) for p in pages)
    avg = total_chars / max(1, len(pages))
    meta = {"avg_chars_per_page": round(avg, 1), "page_count": len(pages)}

    if pages and avg < OCR_MIN_CHARS_PER_PAGE:
        meta["scanned"] = True
        if tools.get("tesseract") and tools.get("pdftoppm"):
            ocr_pages, ocr_fail = ocr_pdf(path, ocr_max_pages)
            if ocr_pages:
                meta["ocr_applied"] = True
                meta["ocr_pages"] = len(ocr_pages)
                pages = ocr_pages
            failures.extend(ocr_fail)
        else:
            failures.append({"type": "no_text_layer_ocr_unavailable",
                             "detail": "scanned PDF and tesseract/pdftoppm "
                                       "not available"})
    elif not pages and not failures:
        meta["scanned"] = True
    return pages, meta, failures


def ocr_pdf(path, max_pages):
    failures, pages = [], []
    with tempfile.TemporaryDirectory() as td:
        rc, out, err = run_cmd(["pdftoppm", "-r", "150", "-png", path,
                                os.path.join(td, "pg")], timeout=300)
        if rc != 0:
            return pages, [{"type": "ocr_render_failed",
                            "detail": (err or out)[:200]}]
        imgs = sorted(f for f in os.listdir(td) if f.endswith(".png"))
        for i, img in enumerate(imgs[:max_pages], 1):
            rc, out, err = run_cmd(["tesseract", os.path.join(td, img),
                                    "stdout", "-l", "eng+chi_sim"],
                                   timeout=120)
            if rc != 0 and "Failed loading language" in err:
                rc, out, err = run_cmd(["tesseract", os.path.join(td, img),
                                        "stdout", "-l", "eng"], timeout=120)
                if rc == 0:
                    ocr_lang_note = "chi_sim unavailable; fell back to eng"
            if rc == 0:
                pages.append({"page": i, "text": out, "source": "ocr"})
            else:
                failures.append({"type": "ocr_page_failed", "page": i,
                                 "detail": err[:120]})
        if len(imgs) > max_pages:
            failures.append({"type": "ocr_truncated",
                             "detail": "OCR limited to %d of %d pages"
                                       % (max_pages, len(imgs))})
    return pages, failures


_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_A = "{http://schemas.openxmlformats.org/drawingml/2006/main}"


def _text_of(elem, tag_ns):
    return "".join(t.text or "" for t in elem.iter(tag_ns))


def extract_docx(path):
    units, failures = [], []
    try:
        z = zipfile.ZipFile(path)
        xml = z.read("word/document.xml")
        root = ET.fromstring(xml)
        paras = []
        for p in root.iter(_W + "p"):
            t = _text_of(p, _W + "t")
            if t.strip():
                paras.append(t)
        if paras:
            units.append({"page": 1, "text": "\n".join(paras)})
        else:
            failures.append({"type": "no_text_extracted", "detail": "empty docx body"})
    except Exception as e:  # noqa: BLE001
        failures.append({"type": "extract_failed", "detail": repr(e)[:200]})
    return units, failures


def extract_pptx(path):
    units, failures = [], []
    try:
        z = zipfile.ZipFile(path)
        slides = sorted(n for n in z.namelist()
                        if re.match(r"ppt/slides/slide\d+\.xml$", n))
        for i, name in enumerate(slides, 1):
            root = ET.fromstring(z.read(name))
            texts = [t.text or "" for t in root.iter(_A + "t")]
            body = "\n".join(x for x in texts if x.strip())
            units.append({"page": i, "text": body, "unit": name})
        if not units:
            failures.append({"type": "no_text_extracted", "detail": "empty pptx"})
    except Exception as e:  # noqa: BLE001
        failures.append({"type": "extract_failed", "detail": repr(e)[:200]})
    return units, failures


_SS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def extract_xlsx(path):
    units, failures = [], []
    try:
        z = zipfile.ZipFile(path)
        shared = []
        if "xl/sharedStrings.xml" in z.namelist():
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.iter(_SS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(_SS + "t")))
        sheets = sorted(n for n in z.namelist()
                        if re.match(r"xl/worksheets/sheet\d+\.xml$", n))
        for i, name in enumerate(sheets, 1):
            root = ET.fromstring(z.read(name))
            rows = []
            for row in root.iter(_SS + "row"):
                cells = []
                for c in row.iter(_SS + "c"):
                    ctype = c.get("t")
                    if ctype == "inlineStr":
                        is_elem = c.find(_SS + "is")
                        if is_elem is not None:
                            cells.append("".join(t.text or ""
                                                 for t in is_elem.iter(_SS + "t")))
                        continue
                    v = c.find(_SS + "v")
                    if v is None or v.text is None:
                        continue
                    if ctype == "s":
                        idx = int(v.text)
                        cells.append(shared[idx] if idx < len(shared) else v.text)
                    else:
                        cells.append(v.text)
                if any(x.strip() for x in cells):
                    rows.append("\t".join(cells))
            units.append({"page": i, "text": "\n".join(rows), "unit": name})
        if not units:
            failures.append({"type": "no_text_extracted", "detail": "empty xlsx"})
    except Exception as e:  # noqa: BLE001
        failures.append({"type": "extract_failed", "detail": repr(e)[:200]})
    return units, failures


def _qdf_text(qdf_out):
    """从 qpdf --qdf 输出中粗提文本流（恢复路径，尽力而为）。"""
    import re as _re
    chunks = _re.findall(r"\((.*?)\)\s*Tj", qdf_out)
    if not chunks:
        return ""
    return "\n".join(c.replace("\\)", ")").replace("\\(", "(")
                      for c in chunks)


_RE_RTF_CTRL = re.compile(r"\\[a-zA-Z]+-?\d* ?|[{}]")
_RE_RTF_HEX = re.compile(r"\\'([0-9a-fA-F]{2})")


def extract_rtf(path):
    try:
        with open(path, "rb") as f:
            raw = f.read(4 << 20)
        text = raw.decode("latin-1", "replace")
        text = _RE_RTF_HEX.sub(lambda m: bytes.fromhex(m.group(1))
                               .decode("cp1252", "replace"), text)
        text = text.replace("\\par", "\n").replace("\\line", "\n")
        text = _RE_RTF_CTRL.sub("", text)
        return [{"page": 1, "text": text}], []
    except Exception as e:  # noqa: BLE001
        return [], [{"type": "extract_failed", "detail": repr(e)[:200]}]


def extract_eml(path):
    import email
    try:
        with open(path, "rb") as f:
            msg = email.message_from_bytes(f.read(8 << 20))
        parts = []
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                if payload:
                    parts.append(payload.decode("utf-8", "replace"))
        head = "From: %s\nSubject: %s\nDate: %s\n" % (
            msg.get("From"), msg.get("Subject"), msg.get("Date"))
        if parts or msg.get("Subject"):
            return [{"page": 1, "text": head + "\n".join(parts)}], []
        return [], [{"type": "no_text_extracted", "detail": "eml has no text/plain"}]
    except Exception as e:  # noqa: BLE001
        return [], [{"type": "extract_failed", "detail": repr(e)[:200]}]


ARCHIVE_MAX_MEMBERS = 20
ARCHIVE_MAX_BYTES = 2 << 20


def extract_archive(path, rel_hint=""):
    """受控解包 zip/tar 中的文本类成员，成员以 '归档::成员' 虚路径记录。"""
    import tarfile
    units, failures = [], []
    try:
        if zipfile.is_zipfile(path):
            names = [i for i in zipfile.ZipFile(path).infolist()
                     if not i.is_dir()]
            with zipfile.ZipFile(path) as z:
                for info in names[:ARCHIVE_MAX_MEMBERS]:
                    if info.file_size > ARCHIVE_MAX_BYTES:
                        continue
                    cat = categorize(info.filename)
                    if cat != "text":
                        continue
                    try:
                        t = z.read(info).decode("utf-8", "replace")
                        units.append({"page": 1, "text": t,
                                      "unit": info.filename})
                    except Exception:  # noqa: BLE001
                        continue
            total = len(names)
        elif tarfile.is_tarfile(path):
            total = 0
            with tarfile.open(path) as t:
                members = [m for m in t.getmembers() if m.isfile()]
                total = len(members)
                for m in members[:ARCHIVE_MAX_MEMBERS]:
                    if m.size > ARCHIVE_MAX_BYTES or categorize(m.name) != "text":
                        continue
                    fh = t.extractfile(m)
                    if fh:
                        units.append({"page": 1,
                                      "text": fh.read().decode("utf-8", "replace"),
                                      "unit": m.name})
        else:
            return [], [{"type": "archive_format_unknown",
                         "detail": "not zip/tar"}]
        if len(units) < total:
            failures.append({"type": "archive_partial_extract",
                             "detail": "%d of %d members listed; text members "
                                       "within budget extracted" % (len(units), total)})
        if not units:
            failures.append({"type": "archive_no_text_members",
                             "detail": "no text-like members within budget"})
        return units, failures
    except Exception as e:  # noqa: BLE001
        return [], [{"type": "archive_extract_failed", "detail": repr(e)[:200]}]


def extract_text(path):
    try:
        size = os.path.getsize(path)
        with open(path, encoding="utf-8", errors="replace") as f:
            t = f.read(2 << 20)  # 单文件上限 2MB
        fails = []
        if size > (2 << 20):
            fails.append({"type": "text_truncated",
                          "detail": "read first 2MiB of %d bytes" % size})
        return [{"page": 1, "text": t}], fails
    except Exception as e:  # noqa: BLE001
        return [], [{"type": "extract_failed", "detail": repr(e)[:200]}]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--ocr-max-pages", type=int, default=DEFAULT_OCR_MAX_PAGES)
    a = ap.parse_args()

    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    inv = read_json(os.path.join(a.work_dir, "inventory.json"), {}) or {}
    tools = inv.get("tools") or which_tools()
    root = inv.get("input_root", a.input_root)

    docs, failures = [], []
    files = inv.get("files") or []
    if not files:
        # 无 inventory 时自行扫描（容错路径）
        for dp, dn, fn in os.walk(root):
            for f in sorted(fn):
                files.append({"path": os.path.relpath(os.path.join(dp, f), root),
                              "category": "text", "readable": True})
        journal.log("1-extract", "no inventory.json; ad-hoc scan",
                    status="recovered")

    for i, rec in enumerate(files, 1):
        path = rec["path"]
        cat = rec.get("category", "other")
        if not rec.get("readable", True):
            failures.append({"type": "no_permission", "path": path})
            continue
        full = os.path.join(root, path)
        doc = {"doc_id": "d%03d" % i, "path": path, "name": rec.get("name"),
               "category": cat, "sha256": rec.get("sha256"),
               "size_bytes": rec.get("size_bytes"),
               "version_tags": rec.get("version_tags") or [],
               "pages": [], "meta": {}}
        if cat == "pdf":
            doc["pages"], doc["meta"], f = extract_pdf(full, tools, a.ocr_max_pages)
            failures.extend(dict(x, path=path) for x in f)
        elif cat == "docx":
            doc["pages"], f = extract_docx(full)
            failures.extend(dict(x, path=path) for x in f)
        elif cat == "pptx":
            doc["pages"], f = extract_pptx(full)
            failures.extend(dict(x, path=path) for x in f)
        elif cat == "xlsx":
            doc["pages"], f = extract_xlsx(full)
            failures.extend(dict(x, path=path) for x in f)
        elif cat == "text" and path.lower().endswith(".rtf"):
            doc["pages"], f = extract_rtf(full)
            failures.extend(dict(x, path=path) for x in f)
        elif cat == "email":
            doc["pages"], f = extract_eml(full)
            failures.extend(dict(x, path=path) for x in f)
        elif cat == "archive":
            doc["pages"], f = extract_archive(full)
            failures.extend(dict(x, path=path) for x in f)
        elif cat == "text":
            doc["pages"], f = extract_text(full)
            failures.extend(dict(x, path=path) for x in f)
        elif cat == "doc-legacy" and tools.get("antiword"):
            rc, out, err = run_cmd(["antiword", full], timeout=60)
            if rc == 0:
                doc["pages"] = [{"page": 1, "text": out}]
            else:
                failures.append({"type": "extract_failed", "path": path,
                                 "detail": "antiword: " + err[:120]})
        elif cat.endswith("legacy"):
            failures.append({"type": "legacy_format_unsupported",
                             "path": path,
                             "detail": "legacy binary Office format; no converter"})
        elif cat == "image":
            failures.append({"type": "image_not_ocred", "path": path,
                             "detail": "standalone image; not OCRed by default"})
        else:
            doc["pages"], f = extract_text(full)
            failures.extend(dict(x, path=path) for x in f)
        doc["char_total"] = sum(len(p.get("text", "")) for p in doc["pages"])
        if not doc["pages"]:
            doc["meta"]["no_text"] = True
        docs.append(doc)
        journal.log("1-extract", "extracted %s (%d chars)" %
                    (path, doc["char_total"]),
                    status="ok" if doc["pages"] else "failed")

    corpus = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "docs": docs,
        "failures": failures,
        "stats": {
            "docs": len(docs),
            "with_text": sum(1 for d in docs if d["char_total"] > 0),
            "no_text": sum(1 for d in docs if d["char_total"] == 0),
            "total_chars": sum(d["char_total"] for d in docs),
        },
    }
    out = write_json(os.path.join(a.work_dir, "corpus.json"), corpus)
    journal.log("1-extract", "done: %d docs, %d with text, %d failures"
                % (len(docs), corpus["stats"]["with_text"], len(failures)),
                outputs=[out])
    print(json.dumps(corpus["stats"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
