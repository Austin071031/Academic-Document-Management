#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
docx_annotations.py — Word（.docx）批注提取（v2.1.0 方向：多载体批注覆盖）

从 docx 包内提取真实 Word 批注（word/comments.xml）并恢复其锚定原文：
- comments.xml：comment id / author / date / 批注文字
- document.xml：commentRangeStart/commentRangeEnd 界定的锚定区间，
  恢复锚定引文及其 段落号 + 段内字符偏移（确定性 XML 定位，非 OCR 估计）

无 comments.xml 的 docx 返回空列表并如实标注（not_present）。
也可提取 document.xml 中的 <w:ins>/<w:del> 修订标记（type=revision）。

用法（库）：from docx_annotations import extract_docx_annotations
用法（CLI）：python3 docx_annotations.py FILE.docx [--json]
"""
import json
import re
import sys
import zipfile

W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def _text_of(elem):
    return "".join(t.text or "" for t in elem.iter(W + "t"))


def _parse_comments_xml(xml):
    """返回 {comment_id: {author, date, text}}"""
    import xml.etree.ElementTree as ET
    out = {}
    root = ET.fromstring(xml)
    for c in root.iter(W + "comment"):
        cid = c.get(W + "id")
        out[cid] = {
            "author": c.get(W + "author"),
            "date": c.get(W + "date"),
            "initials": c.get(W + "initials"),
            "text": re.sub(r"\s+", " ", _text_of(c)).strip(),
        }
    return out


def _anchor_ranges(document_xml):
    """遍历段落，返回 {comment_id: {paragraph, char_start, char_end, quote}} 与修订标记列表。"""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(document_xml)
    anchors = {}
    revisions = []
    p_idx = 0
    for p in root.iter(W + "p"):
        p_idx += 1
        # 段落内顺序遍历：记录字符游标与各 comment range 的开闭
        cursor = 0
        open_ranges = {}
        para_text_parts = []
        def walk(e):
            nonlocal cursor
            tag = e.tag
            if tag == W + "commentRangeStart":
                cid = e.get(W + "id")
                open_ranges[cid] = cursor
                return
            if tag == W + "commentRangeEnd":
                cid = e.get(W + "id")
                if cid in open_ranges:
                    anchors[cid] = {"paragraph": p_idx,
                                    "char_start": open_ranges.pop(cid),
                                    "char_end": cursor}
                return
            if tag == W + "ins":
                txt = _text_of(e)
                revisions.append({"type": "insert", "paragraph": p_idx,
                                  "author": e.get(W + "author"), "date": e.get(W + "date"),
                                  "text": txt})
            if tag == W + "del":
                txt = "".join(t.text or "" for t in e.iter(W + "delText"))
                revisions.append({"type": "delete", "paragraph": p_idx,
                                  "author": e.get(W + "author"), "date": e.get(W + "date"),
                                  "text": txt})
                # del 文本不计入正文游标
                for child in e:
                    walk(child)
                return
            if tag == W + "t":
                txt = e.text or ""
                para_text_parts.append(txt)
                cursor += len(txt)
                return
            for child in e:
                walk(child)
        walk(p)
        para_text = "".join(para_text_parts)
        for cid, a in anchors.items():
            if a.get("paragraph") == p_idx and "quote" not in a:
                a["quote"] = para_text[a["char_start"]:a["char_end"]]
    return anchors, revisions


def extract_docx_annotations(path):
    """返回 {status, comments: [...], revisions: [...], note}。"""
    try:
        z = zipfile.ZipFile(path)
        names = set(z.namelist())
    except Exception as e:
        return {"status": "failed", "comments": [], "revisions": [], "note": "docx open failed: %s" % e}
    if "word/comments.xml" not in names:
        rev_note = None
        revisions = []
        if "word/document.xml" in names:
            try:
                _, revisions = _anchor_ranges(z.read("word/document.xml").decode("utf-8", "replace"))
            except Exception:
                pass
        return {"status": "ok", "comments": [], "revisions": revisions,
                "note": "word/comments.xml not present: 该 docx 不含 Word 批注"}
    comments = _parse_comments_xml(z.read("word/comments.xml").decode("utf-8", "replace"))
    anchors, revisions = {}, []
    if "word/document.xml" in names:
        try:
            anchors, revisions = _anchor_ranges(z.read("word/document.xml").decode("utf-8", "replace"))
        except Exception as e:
            pass
    out = []
    for cid, c in sorted(comments.items(), key=lambda x: int(x[0]) if str(x[0]).isdigit() else 0):
        a = anchors.get(cid)
        out.append({
            "comment_id": cid,
            "type": "docx_comment",
            "author": c.get("author"),
            "date": c.get("date"),
            "note_text": c.get("text"),
            "anchor": a,
            "anchor_verified": bool(a and a.get("quote") is not None),
            "confidence": 0.95 if a and a.get("quote") is not None else 0.5,
            "method": "docx-comments.xml+commentRange",
        })
    return {"status": "ok", "comments": out, "revisions": revisions, "note": None}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    res = extract_docx_annotations(sys.argv[1])
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
