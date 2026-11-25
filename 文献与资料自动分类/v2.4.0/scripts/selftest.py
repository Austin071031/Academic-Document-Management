#!/usr/bin/env python3
"""selftest.py — 金标准自测集（v2.4.0 方向）：任何人可一键验证本 Skill 行为。

在临时目录合成 10 类样本（期刊/预印本/重复件/扫描件/补充材料/会议+侧车/学位论文/
数据集/损坏件/中文文本），运行完整流水线，对照 fixtures/expected.json 逐项断言。

用法: python3 selftest.py   （退出码 0=全部通过）
"""
import json, os, subprocess, sys, tempfile

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def build_fixtures(root):
    inp = os.path.join(root, "input")
    os.makedirs(inp, exist_ok=True)
    def make_pdf(path, lines):
        # 最小合法 PDF（单行文本流），足以让 pdfinfo/pdftotext 工作
        content = "BT /F1 10 Tf 50 780 Td " + " ".join(
            f"({l.replace('(', '[').replace(')', ']')}) Tj 0 -14 Td" for l in lines) + " ET"
        objs = []
        objs.append("1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj")
        objs.append("2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj")
        objs.append("3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 595 842]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj")
        stream = content.encode("latin-1", errors="replace")
        objs.append(f"4 0 obj<</Length {len(stream)}>>stream\n" + stream.decode("latin-1") + "\nendstream endobj")
        objs.append("5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj")
        pdf = "%PDF-1.4\n"
        offsets = []
        for o in objs:
            offsets.append(len(pdf.encode("latin-1")))
            pdf += o + "\n"
        xref_pos = len(pdf.encode("latin-1"))
        pdf += f"xref\n0 {len(objs)+1}\n0000000000 65535 f \n"
        for off in offsets:
            pdf += f"{off:010d} 00000 n \n"
        pdf += f"trailer<</Size {len(objs)+1}/Root 1 0 R>>\nstartxref\n{xref_pos}\n%%EOF"
        with open(path, "wb") as f:
            f.write(pdf.encode("latin-1"))

    make_pdf(os.path.join(inp, "smith-2023.pdf"), [
        "High-Throughput Screening of Perovskite Photocatalysts",
        "John Smith and Alice Zhang",
        "Journal of Materials Chemistry A 2023",
        "DOI: 10.1039/D3TA01234A",
        "Keywords: perovskite, photocatalysis"])
    make_pdf(os.path.join(inp, "2304.12345.pdf"), [
        "arXiv:2304.12345v2",
        "High-Throughput Screening of Perovskite Photocatalysts",
        "John Smith and Alice Zhang"])
    import shutil
    shutil.copy(os.path.join(inp, "smith-2023.pdf"), os.path.join(inp, "copy of smith.pdf"))
    with open(os.path.join(inp, "broken.pdf"), "wb") as f:
        f.write(b"%PDF-1.4 truncated")
    with open(os.path.join(inp, "data.csv"), "w") as f:
        f.write("material,bandgap\nCsPbI3,1.73\n")
    with open(os.path.join(inp, "notes.txt"), "w", encoding="utf-8") as f:
        f.write("关键词: 钙钛矿\n综述笔记。\n")
    with open(os.path.join(inp, "case.json"), "w") as f:
        json.dump({"case_id": "selftest", "output_contract": {"organized_library": "dir"}}, f)
    with open(os.path.join(inp, "task.md"), "w") as f:
        f.write("整理文献：分类、命名、去重、版本关系。\n")
    return inp

def main():
    expected_path = os.path.join(SKILL_DIR, "fixtures", "expected.json")
    with open(expected_path, "r", encoding="utf-8") as f:
        expected = json.load(f)
    results = []
    with tempfile.TemporaryDirectory() as root:
        inp = build_fixtures(root)
        wd, od = os.path.join(root, "work"), os.path.join(root, "output")
        rc = subprocess.run(["bash", os.path.join(SKILL_DIR, "scripts", "run_pipeline.sh"),
                             inp, wd, od], capture_output=True, text=True, timeout=600)
        plan = json.load(open(os.path.join(wd, "plan.json"), encoding="utf-8"))
        acts = {i["rel_path"]: i for i in plan["items"]}

        def check(name, cond, detail):
            results.append({"check": name, "pass": bool(cond), "detail": detail})

        check("pipeline_exit", rc.returncode == 0, f"rc={rc.returncode}")
        check("dup_archived", acts.get("copy of smith.pdf", {}).get("action") == "archive_duplicate",
              acts.get("copy of smith.pdf", {}).get("action"))
        check("preprint_superseded",
              acts.get("2304.12345.pdf", {}).get("version_role") == "superseded",
              acts.get("2304.12345.pdf", {}).get("version_role"))
        check("journal_canonical",
              acts.get("smith-2023.pdf", {}).get("version_role") == "canonical",
              acts.get("smith-2023.pdf", {}).get("version_role"))
        check("broken_skipped", acts.get("broken.pdf", {}).get("action") == "skip",
              acts.get("broken.pdf", {}).get("action"))
        check("dataset_classified", acts.get("data.csv", {}).get("doc_type") == "dataset",
              acts.get("data.csv", {}).get("doc_type"))
        check("selfcheck_passed",
              json.load(open(os.path.join(wd, "selfcheck.json"), encoding="utf-8"))["passed"], "")
        check("min_checks", len(results) >= expected.get("min_checks", 5), f"{len(results)} checks")

    passed = sum(1 for r in results if r["pass"])
    for r in results:
        print(("PASS" if r["pass"] else "FAIL"), r["check"], r["detail"])
    print(f"[selftest] {passed}/{len(results)} passed")
    return 0 if passed == len(results) else 1

if __name__ == "__main__":
    sys.exit(main())
