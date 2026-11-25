#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_goldcheck.py — 金标准复跑校验（v2.5.0）

一键复跑：生成合成题集 → 跑 pipeline → 按 expected.json 逐项比对 → gold_report.json。

用法：
  python3 gold/run_goldcheck.py [--work DIR] [--keep]
  （在 Skill 根目录运行；--work 默认 <skill>/gold/_run）
退出码：0 = 全部强断言通过；1 = 有失败项（报告仍写出）。
"""
import argparse
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)


def get_path(obj, dotted):
    cur = obj
    for k in dotted.split("."):
        if isinstance(cur, dict):
            cur = cur.get(k)
        else:
            return None
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default=os.path.join(HERE, "_run"))
    ap.add_argument("--keep", action="store_true")
    args = ap.parse_args()
    os.makedirs(args.work, exist_ok=True)
    rep = {"steps": [], "assertions": [], "verdict": "pass"}

    # 1. 生成题集
    r = subprocess.run([sys.executable, os.path.join(HERE, "make_fixture.py"), args.work],
                       capture_output=True, text=True, timeout=300)
    rep["steps"].append({"step": "make_fixture", "returncode": r.returncode,
                         "stdout": r.stdout.strip()[:300]})
    if r.returncode != 0:
        rep["verdict"] = "fail"
        rep["reason"] = "fixture generation failed: %s" % (r.stdout + r.stderr)[-300:]
        json.dump(rep, open(os.path.join(HERE, "gold_report.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(json.dumps({"verdict": "fail", "reason": rep["reason"]}, ensure_ascii=False))
        return 1

    # 2. 跑 pipeline
    outdir = os.path.join(args.work, "output")
    r = subprocess.run([sys.executable, os.path.join(SKILL, "scripts", "pipeline.py"),
                        "--case", os.path.join(args.work, "case.json"),
                        "--materials", os.path.join(args.work, "materials"),
                        "--workdir", os.path.join(args.work, "work"),
                        "--outdir", outdir],
                       capture_output=True, text=True, timeout=600)
    rep["steps"].append({"step": "pipeline", "returncode": r.returncode,
                         "stdout_tail": r.stdout.strip()[-300:]})
    if r.returncode != 0:
        rep["verdict"] = "fail"
        rep["reason"] = "pipeline failed: %s" % (r.stderr or r.stdout)[-300:]
        json.dump(rep, open(os.path.join(HERE, "gold_report.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print(json.dumps({"verdict": "fail", "reason": rep["reason"]}, ensure_ascii=False))
        return 1

    result = json.load(open(os.path.join(outdir, "result_annotations.json"), encoding="utf-8"))
    notes = json.load(open(os.path.join(outdir, "notes.json"), encoding="utf-8"))
    expected = json.load(open(os.path.join(HERE, "expected.json"), encoding="utf-8"))

    # 3. 强断言
    sa = expected["strong_assertions"]
    def check(name, actual, want, cmp="eq"):
        if cmp == "eq":
            ok = actual == want
        elif cmp == "min":
            ok = actual is not None and actual >= want
        rep["assertions"].append({"name": name, "want": want, "actual": actual, "ok": bool(ok)})
        return ok

    allok = True
    allok &= check("summary.files", get_path(result, "summary.files"), sa["summary.files"])
    allok &= check("summary.pdfs_processed", get_path(result, "summary.pdfs_processed"), sa["summary.pdfs_processed"])
    allok &= check("summary.pdfs_failed", get_path(result, "summary.pdfs_failed"), sa["summary.pdfs_failed"])
    allok &= check("summary.annotations", get_path(result, "summary.annotations"), sa["summary.annotations"])
    allok &= check("summary.docx_comments", get_path(result, "summary.docx_comments"), sa["summary.docx_comments"])
    allok &= check("summary.duplicate_groups", get_path(result, "summary.duplicate_groups"), sa["summary.duplicate_groups"])
    allok &= check("summary.version_groups", get_path(result, "summary.version_groups"), sa["summary.version_groups"])
    allok &= check("summary.file_version_links", get_path(result, "summary.file_version_links"), sa["summary.file_version_links"])
    allok &= check("verification.anchor_verification_rate",
                   get_path(result, "verification.anchor_verification_rate"),
                   sa["verification.anchor_verification_rate"])
    allok &= check("verification.merged_annotation_clusters",
                   get_path(result, "verification.merged_annotation_clusters"),
                   sa["verification.merged_annotation_clusters"])
    corr = get_path(result, "verification.anchor_corrections") or []
    allok &= check("verification.anchor_corrections_min", len(corr),
                   sa["verification.anchor_corrections_min"], cmp="min")
    docx_ok = sum(1 for n in notes if n.get("derived_from") == "docx_annotation"
                  and n["source"].get("anchor_verified"))
    allok &= check("notes.docx_comment_anchor_verified_count", docx_ok,
                   sa["notes.docx_comment_anchor_verified_count"])
    allok &= check("status", get_path(result, "status"), sa["status"])

    # 弱断言（环境相关，仅记录不判死）
    twocol = [n for n in notes if "twocol" in (n["source"].get("file_name") or "")]
    rep["weak"] = {
        "fts5": get_path(result, "verification.fts5"),
        "twocol_anchor_match": twocol[0]["source"].get("anchor_match") if twocol else None,
    }

    rep["verdict"] = "pass" if allok else "fail"
    with open(os.path.join(HERE, "gold_report.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=1)
    print(json.dumps({"verdict": rep["verdict"],
                      "failed": [a["name"] for a in rep["assertions"] if not a["ok"]]},
                     ensure_ascii=False))
    if not args.keep:
        import shutil
        shutil.rmtree(args.work, ignore_errors=True)
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
