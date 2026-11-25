#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""deliver.py — 【v2.0.0-D 旗舰】交付物生成与渲染预览。

运行契约要求："Editable Office/slide/diagram outputs should also have real
rendered PDF/PNG previews for inspection"。本模块：

1. 生成组织化交付物（catalog.json/csv/md、retrieval_report.md、versions.md）
   与可复用资源（templates/目录规范.md、metadata_schema.json）；
2. 若任务/契约要求 Office 交付物（output_contract 字段名或任务文本含
   xlsx/docx/pptx/Excel/Word/幻灯片 等），用标准库直接写出真实 OOXML 文件；
3. 对每个可编辑交付物渲染预览：soffice/libreoffice → PDF，pdftoppm → PNG；
   工具缺失时如实记录 preview_unavailable（绝不伪造预览）；
4. 全部产物登记 deliverables.json（report finalize 会再算哈希清单）。
"""
import argparse
import csv
import io
import json
import os
import sys
import time
import xml.sax.saxutils as sx
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Journal, read_json, run_cmd, which_tools, write_json


def build_catalog_rows(inv, corpus, lineage):
    meta = lineage.get("doc_meta") or {}
    corpus_by_path = {d.get("path"): d for d in corpus.get("docs", [])}
    rows = []
    for f in inv.get("files", []):
        d = corpus_by_path.get(f.get("path"), {})
        dm = meta.get(d.get("doc_id"), {})
        rows.append({
            "path": f.get("path"), "sha256": f.get("sha256"),
            "category": f.get("category"), "size_bytes": f.get("size_bytes"),
            "mtime": f.get("mtime"),
            "version_tags": ";".join(f.get("version_tags") or []),
            "version_role": dm.get("version_role"),
            "cluster_id": dm.get("cluster_id"),
            "is_canonical": dm.get("is_canonical"),
            "extract_status": "extracted" if d.get("char_total")
            else "no_text" if d else "not_extracted"})
    return rows


def write_csv(rows, path):
    if not rows:
        return None
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return path


def catalog_md(rows, title):
    lines = ["# %s" % title, "", "| 路径 | 类型 | 大小(B) | 版本标签 | "
             "版本角色 | 提取状态 |", "|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            r["path"], r["category"], r["size_bytes"],
            r["version_tags"] or "-", r["version_role"] or "-",
            r["extract_status"]))
    return "\n".join(lines)


def report_md(hits, query):
    lines = ["# 检索结果报告", "", "**查询**: %s" % (query or "(未指定)"), "",
             "| # | 分数 | 文件 | 页(物理/印刷) | 章节 | 校验 | 原文片段 |",
             "|---|---|---|---|---|---|---|"]
    for i, h in enumerate(hits.get("hits", []), 1):
        a = h.get("anchor", {})
        lines.append("| %d | %.2f | %s | %s/%s | %s | %s | %s |" % (
            i, h.get("score", 0), a.get("file_path"), a.get("page"),
            a.get("printed_page") or "-", (a.get("section_path") or "-")[:40],
            "✓" if h.get("verified") else "✗",
            (a.get("quote") or "")[:60].replace("|", "\\|")))
    return "\n".join(lines)


def versions_md(lineage):
    lines = ["# 版本关系注记", ""]
    for c in lineage.get("clusters", []):
        if c.get("relation") == "singleton":
            continue
        canonical = next((m for m in c.get("members", [])
                          if m["doc_id"] == c["canonical"]), {})
        lines.append("## %s（%s）" % (c.get("cluster_id"), c.get("relation")))
        lines.append("- canonical: `%s`" % canonical.get("path"))
        for m in c.get("members", []):
            lines.append("- %s — %s（相似度 %s）"
                         % (m.get("path"), m.get("role"),
                            m.get("similarity_to_canonical")))
        lines.append("")
    if len(lines) == 2:
        lines.append("（未发现重复或多版本簇。）")
    return "\n".join(lines)


_CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/'
       'content-types"><Default Extension="rels" ContentType="application/'
       'vnd.openxmlformats-package.relationships+xml"/><Default '
       'Extension="xml" ContentType="application/xml"/>%s</Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/'
         '2006/relationships"><Relationship Id="rId1" Type="http://schemas.'
         'openxmlformats.org/officeDocument/2006/relationships/%s" '
         'Target="%s"/></Relationships>')


def write_xlsx(rows, path):
    def colname(i):
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s
    sheet_rows = []
    headers = list(rows[0].keys()) if rows else []
    for ri, vals in enumerate([headers] + [[r.get(h) for h in headers]
                                           for r in rows], 1):
        cells = "".join(
            '<c r="%s%d" t="inlineStr"><is><t>%s</t></is></c>'
            % (colname(ci), ri, sx.escape(str(v if v is not None else "")))
            for ci, v in enumerate(vals))
        sheet_rows.append('<row r="%d">%s</row>' % (ri, cells))
    sheet_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                 '<worksheet xmlns="http://schemas.openxmlformats.org/'
                 'spreadsheetml/2006/main"><sheetData>%s</sheetData></worksheet>'
                 % "".join(sheet_rows))
    wb_xml = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<workbook xmlns="http://schemas.openxmlformats.org/'
              'spreadsheetml/2006/main" xmlns:r="http://schemas.openxml.'
              'formats.org/officeDocument/2006/relationships"><sheets>'
              '<sheet name="catalog" sheetId="1" r:id="rId1"/></sheets>'
              '</workbook>')
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", _CT % (
            '<Override PartName="/xl/workbook.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType='
            '"application/vnd.openxmlformats-officedocument.spreadsheetml.'
            'worksheet+xml"/>'))
        z.writestr("_rels/.rels", _RELS % ("officeDocument", "xl/workbook.xml"))
        z.writestr("xl/workbook.xml", wb_xml)
        z.writestr("xl/_rels/workbook.xml.rels", _RELS % (
            "worksheet", "worksheets/sheet1.xml"))
        z.writestr("xl/worksheets/sheet1.xml", sheet_xml)


def write_docx(title, paragraphs, path):
    ns = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<w:document xmlns:w="http://schemas.openxmlformats.org/'
          'wordprocessingml/2006/main"><w:body>')
    body = '<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>' % \
        sx.escape(title)
    for p in paragraphs:
        body += ('<w:p><w:r><w:t xml:space="preserve">%s</w:t></w:r></w:p>'
                 % sx.escape(p))
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", _CT % (
            '<Override PartName="/word/document.xml" ContentType="application/'
            'vnd.openxmlformats-officedocument.wordprocessingml.document.'
            'main+xml"/>'))
        z.writestr("_rels/.rels", _RELS % ("officeDocument",
                                           "word/document.xml"))
        z.writestr("word/document.xml", ns + body + "</w:body></w:document>")


def render_preview(path, outdir, tools):
    """Office → PDF → PNG；任一步不可用则如实返回状态。"""
    soffice = tools.get("soffice") or tools.get("libreoffice")
    if not soffice:
        return {"file": path, "preview": None,
                "status": "preview_unavailable_no_soffice"}
    rc, out, err = run_cmd([soffice, "--headless", "--convert-to", "pdf",
                            "--outdir", outdir, path], timeout=180)
    pdf = os.path.join(outdir, os.path.splitext(os.path.basename(path))[0]
                       + ".pdf")
    if rc != 0 or not os.path.exists(pdf):
        return {"file": path, "preview": None,
                "status": "preview_failed_soffice",
                "detail": (err or out)[:200]}
    previews = {"file": path, "pdf": pdf, "status": "ok"}
    if tools.get("pdftoppm"):
        rc2, _, err2 = run_cmd(["pdftoppm", "-png", "-r", "100", "-f", "1",
                                "-l", "3", pdf,
                                os.path.join(outdir, "preview")], timeout=120)
        if rc2 == 0:
            previews["png"] = sorted(f for f in os.listdir(outdir)
                                     if f.startswith("preview"))
        else:
            previews["png_status"] = "pdftoppm_failed"
    return previews


def needs_office(case, task_text):
    text = json.dumps(case, ensure_ascii=False) + (task_text or "")
    keys = {"xlsx": ["xlsx", "excel", "电子表格", "表格交付"],
            "docx": ["docx", "word", "文档交付"],
            "pptx": ["pptx", "幻灯片", "slides"]}
    return [k for k, vs in keys.items() if any(v in text.lower()
                                               for v in vs)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    a = ap.parse_args()
    j = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    out = a.output_dir
    os.makedirs(out, exist_ok=True)
    tools = which_tools()

    inv = read_json(os.path.join(a.work_dir, "inventory.json"), {}) or {}
    corpus = read_json(os.path.join(a.work_dir, "corpus.json"), {}) or {}
    lineage = read_json(os.path.join(a.work_dir, "lineage.json"), {}) or {}
    hits = read_json(os.path.join(a.work_dir, "hits.json"), {}) or {}
    case = read_json(os.path.join(a.input_root, "case.json"), {}) or {}
    task_text = ""
    tf = os.path.join(a.input_root, "task.md")
    if os.path.exists(tf):
        task_text = open(tf, encoding="utf-8", errors="replace").read()

    deliverables = []
    rows = build_catalog_rows(inv, corpus, lineage)
    write_json(os.path.join(out, "catalog.json"), {"entries": rows})
    deliverables.append("catalog.json")
    if rows:
        write_csv(rows, os.path.join(out, "catalog.csv"))
        deliverables.append("catalog.csv")
        with open(os.path.join(out, "catalog.md"), "w", encoding="utf-8") as f:
            f.write(catalog_md(rows, "文件库清单（元数据 + 版本角色）"))
        deliverables.append("catalog.md")
    with open(os.path.join(out, "retrieval_report.md"), "w",
              encoding="utf-8") as f:
        f.write(report_md(hits, hits.get("query")))
    deliverables.append("retrieval_report.md")
    with open(os.path.join(out, "versions.md"), "w", encoding="utf-8") as f:
        f.write(versions_md(lineage))
    deliverables.append("versions.md")

    # 可复用资源（生态贡献）
    tpl_dir = os.path.join(out, "templates")
    os.makedirs(tpl_dir, exist_ok=True)
    with open(os.path.join(tpl_dir, "科研文件库目录规范.md"), "w",
              encoding="utf-8") as f:
        f.write("# 科研文件库目录规范（模板）\n\n"
                "项目根/ {项目编号_项目名}/ {子课题}/ {YYYY-MM}/ 文件\n\n"
                "- 命名： 主题_版本标签_日期.ext（例: XT报告_v2_2023-05.pdf）\n"
                "- 改名副本： 禁止平级存放，登记于 aliases_registry\n"
                "- 元数据必填： sha256、版本标签、日期、版本角色、提取状态\n")
    write_json(os.path.join(tpl_dir, "metadata_schema.json"), {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "科研文件元数据字段规范",
        "type": "object",
        "required": ["path", "sha256", "category", "version_tags",
                     "version_role", "extract_status"],
        "properties": {k: {"type": t} for k, t in [
            ("path", "string"), ("sha256", "string"), ("category", "string"),
            ("size_bytes", "integer"), ("mtime", "string"),
            ("version_tags", "array"), ("date_hint", "string"),
            ("version_role", "string"), ("cluster_id", "string"),
            ("is_canonical", "boolean"), ("extract_status", "string")]}})
    deliverables += ["templates/科研文件库目录规范.md",
                     "templates/metadata_schema.json"]

    # Office 交付物（仅当任务/契约要求）
    previews = []
    for kind in needs_office(case, task_text):
        if kind == "xlsx":
            p = os.path.join(out, "catalog.xlsx")
            write_xlsx(rows, p)
        elif kind == "docx":
            p = os.path.join(out, "检索结果报告.docx")
            paras = [report_md(hits, hits.get("query")).replace("|", "  ")
                     .splitlines()[0]] + \
                [l for l in report_md(hits, hits.get("query")).splitlines()
                 if l.startswith("| ")]
            write_docx("检索结果报告", paras, p)
        else:
            continue
        previews.append(render_preview(p, out, tools))
        deliverables.append(os.path.basename(p))

    write_json(os.path.join(out, "deliverables.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "deliverables": deliverables, "office_previews": previews,
        "tools": {k: v for k, v in tools.items() if k in
                  ("soffice", "libreoffice", "pdftoppm")}})
    j.log("3.4-deliver", "%d deliverables, %d office previews"
          % (len(deliverables), len(previews)))
    print("deliverables=%d office_previews=%d" % (len(deliverables),
                                                  len(previews)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
