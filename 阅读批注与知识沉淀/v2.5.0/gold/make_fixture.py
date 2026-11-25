#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
make_fixture.py — 金标准自测题集生成器（v2.5.0）

确定性生成一个**合成**测试材料库（与平台固定案例无关，仅用于复用与复跑验证）：
- 3 份含真实文本与 5 类批注的 PDF（v1 / v1 重复件 / v2 版本件 + 1 份额外高亮）
- 1 份双栏 PDF（跨行高亮，用于锚点校正验证）
- 1 份含真实 Word 批注（comments.xml + commentRange）的 docx
- 1 份 docx 网页剪藏、1 份散落笔记 md、空文件、断链符号链接、加密 PDF、损坏 PDF

依赖：matplotlib（生成文本页）+ pypdf（写批注）。缺失时明确报错退出 2。

用法：python3 make_fixture.py OUT_DIR
"""
import json
import os
import shutil
import sys
import zipfile

LINES = [
    "We present a graph neural network potential for lithium battery electrolytes.",
    "The model was trained with active learning on 12000 ab initio structures.",
    "Molecular dynamics simulations at 300 K reproduce the experimental viscosity within 5 percent.",
    "The conclusion supports the proposed mechanism, see also Smith et al., 2024.",
]
TWOCOL_L = ["The neural network potential was trained",
            "with active learning on lithium systems",
            "and validated at finite temperature."]
TWOCOL_R = ["Figure 1 shows the radial distribution",
            "function of the molten electrolyte",
            "at 300 K and 1 atm pressure."]


def build(out_dir):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from pypdf import PdfWriter, PdfReader
    from pypdf.generic import (DictionaryObject, ArrayObject, NameObject, NumberObject,
                               TextStringObject, FloatObject)

    M = os.path.join(out_dir, "materials")
    os.makedirs(M, exist_ok=True)

    def base_pdf(path, lines=LINES, twocol=False):
        fig = plt.figure(figsize=(8.27, 11.69))
        y = 0.92
        if twocol:
            y = 0.9
            for i in range(3):
                fig.text(0.07, y, TWOCOL_L[i], fontsize=10)
                fig.text(0.55, y, TWOCOL_R[i], fontsize=10)
                y -= 0.05
        else:
            for ln in lines:
                fig.text(0.1, y, ln, fontsize=11)
                y -= 0.06
        fig.savefig(path, format="pdf")
        plt.close(fig)

    def annot(subtype, rect, quads=None, contents=None, color=None, title=None):
        d = DictionaryObject()
        d[NameObject("/Type")] = NameObject("/Annot")
        d[NameObject("/Subtype")] = NameObject(subtype)
        d[NameObject("/Rect")] = ArrayObject([FloatObject(v) for v in rect])
        d[NameObject("/F")] = NumberObject(4)
        if quads:
            d[NameObject("/QuadPoints")] = ArrayObject([FloatObject(v) for v in quads])
        if contents:
            d[NameObject("/Contents")] = TextStringObject(contents)
        if color:
            d[NameObject("/C")] = ArrayObject([FloatObject(v) for v in color])
        if title:
            d[NameObject("/T")] = TextStringObject(title)
        return d

    def add_annots(path, extra=False):
        r = PdfReader(path)
        w = PdfWriter()
        w.append(r)
        page = w.pages[0]
        ann = [
            annot("/Highlight", [53, 45, 560, 80], [53, 80, 560, 80, 53, 45, 560, 45],
                  "关键方法: GNN potential + active learning", [1, 1, 0], "Researcher A"),
            annot("/Underline", [53, 95, 560, 130], [53, 130, 560, 130, 53, 95, 560, 95], None, [0, 0.6, 0]),
            annot("/Squiggly", [53, 148, 560, 180], [53, 180, 560, 180, 53, 148, 560, 148],
                  "结论: 300 K 下粘度误差 <5%"),
            annot("/FreeText", [420, 300, 570, 360], None, "待验证: baseline 是否公平? (doubt)", [0, 0.5, 1]),
            annot("/Text", [560, 55, 580, 75], None, "引用线索: doi:10.1021/acs.jpcc.9b01234"),
        ]
        if extra:
            ann.append(annot("/Highlight", [53, 198, 560, 230], [53, 230, 560, 230, 53, 198, 560, 198],
                             "结论: supports mechanism (Smith et al., 2024)", [1, 0.8, 0]))
        page[NameObject("/Annots")] = ArrayObject(ann)
        with open(path, "wb") as f:
            w.write(f)

    p1 = os.path.join(M, "paper_draft_v1.pdf")
    base_pdf(p1)
    add_annots(p1)
    shutil.copy(p1, os.path.join(M, "paper_draft_v1_copy.pdf"))
    p2 = os.path.join(M, "paper_draft_v2.pdf")
    base_pdf(p2)
    add_annots(p2, extra=True)

    # 双栏 + 跨行高亮
    pt = os.path.join(M, "twocol_paper.pdf")
    base_pdf(pt, twocol=True)
    r = PdfReader(pt)
    w = PdfWriter()
    w.append(r)
    page = w.pages[0]
    d = DictionaryObject()
    d[NameObject("/Type")] = NameObject("/Annot")
    d[NameObject("/Subtype")] = NameObject("/Highlight")
    d[NameObject("/Rect")] = ArrayObject([FloatObject(38), FloatObject(70), FloatObject(300), FloatObject(130)])
    d[NameObject("/QuadPoints")] = ArrayObject([
        FloatObject(38), FloatObject(88), FloatObject(300), FloatObject(88), FloatObject(38), FloatObject(70), FloatObject(300), FloatObject(70),
        FloatObject(38), FloatObject(130), FloatObject(300), FloatObject(130), FloatObject(38), FloatObject(112), FloatObject(300), FloatObject(112)])
    d[NameObject("/C")] = ArrayObject([FloatObject(1), FloatObject(1), FloatObject(0)])
    d[NameObject("/F")] = NumberObject(4)
    page[NameObject("/Annots")] = ArrayObject([d])
    with open(pt, "wb") as f:
        w.write(f)

    # docx：真实 Word 批注
    docxml = ('<?xml version="1.0"?>\n<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>\n'
              '<w:p><w:r><w:t>The viscosity model was validated against experimental data at 300 K.</w:t></w:r></w:p>\n'
              '<w:p><w:r><w:t>We used </w:t></w:r><w:commentRangeStart w:id="0"/><w:r><w:t>active learning to select 12000 structures</w:t></w:r><w:commentRangeEnd w:id="0"/><w:r><w:commentReference w:id="0"/></w:r><w:r><w:t> for training.</w:t></w:r></w:p>\n'
              '<w:p><w:r><w:t>Conclusion: the proposed mechanism holds. </w:t></w:r><w:commentRangeStart w:id="1"/><w:r><w:t>See also the baseline comparison in Table 2</w:t></w:r><w:commentRangeEnd w:id="1"/><w:r><w:commentReference w:id="1"/></w:r><w:r><w:t>.</w:t></w:r></w:p>\n'
              '</w:body></w:document>')
    comxml = ('<?xml version="1.0"?>\n<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">\n'
              '<w:comment w:id="0" w:author="Researcher B" w:date="2026-03-10T09:00:00Z"><w:p><w:r><w:t>关键方法：确认采样策略是否覆盖高温区间 (question)</w:t></w:r></w:p></w:comment>\n'
              '<w:comment w:id="1" w:author="Researcher B" w:date="2026-03-10T09:05:00Z"><w:p><w:r><w:t>待验证：baseline 的公平性需要独立核对</w:t></w:r></w:p></w:comment>\n'
              '</w:comments>')
    with zipfile.ZipFile(os.path.join(M, "reviewed_manuscript.docx"), "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="t"><Default Extension="xml"/></Types>')
        z.writestr("word/document.xml", docxml)
        z.writestr("word/comments.xml", comxml)

    # docx 网页剪藏（无批注）
    clipxml = ('<?xml version="1.0"?><w:document xmlns:w="w"><w:body>'
               '<w:p><w:r><w:t>网页剪藏: this method uses Monte Carlo sampling at 500 K.</w:t></w:r></w:p>'
               '<w:p><w:r><w:t>paper_draft_v1.pdf p.1 mentions active learning budget.</w:t></w:r></w:p></w:body></w:document>')
    with zipfile.ZipFile(os.path.join(M, "clip_about_methods.docx"), "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types xmlns="t"><Default Extension="xml"/></Types>')
        z.writestr("word/document.xml", clipxml)

    with open(os.path.join(M, "reading_notes.md"), "w") as f:
        f.write("# 阅读笔记\n\npaper_draft_v2.pdf p.1  says the model reaches 300 K stability.\n\n需要检查 baseline 是否公平比较 (question)\n")
    open(os.path.join(M, "empty.txt"), "w").close()
    os.symlink("missing_target.pdf", os.path.join(M, "broken_link.pdf"))
    ew = PdfWriter()
    ew.add_blank_page(width=595, height=842)
    with open(os.path.join(M, "secret.pdf"), "wb") as f:
        ew.encrypt("userpw", "ownerpw")
        ew.write(f)
    with open(os.path.join(M, "corrupted.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 garbage not a real pdf")

    case = {"case_id": "GOLD-SELFTEST-001", "materials_dir": M,
            "output_contract": {"inventory": "file list", "annotations": "extraction",
                                "notes": "structured notes", "index": "searchable index",
                                "status": "run status"}}
    with open(os.path.join(out_dir, "case.json"), "w", encoding="utf-8") as f:
        json.dump(case, f, ensure_ascii=False)
    return M


def main():
    if len(sys.argv) < 2:
        print("usage: make_fixture.py OUT_DIR")
        return 2
    try:
        import matplotlib  # noqa
        import pypdf  # noqa
    except ImportError as e:
        print(json.dumps({"status": "failed", "reason": "missing dependency: %s" % e}, ensure_ascii=False))
        return 2
    m = build(sys.argv[1])
    print(json.dumps({"status": "ok", "materials": m,
                      "files": len(os.listdir(m))}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
