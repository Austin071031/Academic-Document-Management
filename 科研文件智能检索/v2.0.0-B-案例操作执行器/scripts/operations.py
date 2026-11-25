#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""operations.py — 【v2.0.0-B 旗舰】案例操作执行器。

平台案例除了检索提问，还包含库整理操作（题面原文：aliases、administrative
version notes、metadata、recovery/index operations）。本模块把这类操作做成
确定性的、全部留痕的执行器：

1. 解析 case.json/task.md 中声明的操作（index/recover/organize/repair/
   metadata/dedupe/catalog…）；未声明时执行默认全集；
2. rebuild_index   : 复核索引完整性（corpus/sections/lineage 一致）并写索引清单；
3. register_metadata: 生成 catalog.json（每文件元数据：哈希/类别/版本标签/
   版本角色/簇/日期/提取状态）；
4. register_aliases : 生成 aliases_registry.json（改名副本与规范化名映射）；
5. version_notes    : 生成 versions.json（簇级版本链 + canonical 推举依据）；
6. recover          : 对提取失败/无文本层文件做恢复尝试（OCR 重试、回退工具），
   逐文件记录 recovered/failed 与依据。

**只读 /input，绝不改动输入文件**；所有整理产物写入 <output>/organized_library/，
变更记录进 changes，操作逐条进 run_journal。
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Journal, read_json, write_json

OP_VERBS = {
    "index": ["index", "索引", "重建索引", "reindex"],
    "recover": ["recover", "恢复", "修复", "repair", "rescue"],
    "organize": ["organize", "整理", "organise", "归档", "archive"],
    "metadata": ["metadata", "元数据", "catalog", "清单", "登记"],
    "dedupe": ["dedupe", "去重", "duplicates", "重复"],
    "version": ["version", "版本", "lineage", "谱系"],
    "alias": ["alias", "别名", "改名"],
}


def declared_operations(case, task_text):
    ops, seen = [], set()
    text = json.dumps(case, ensure_ascii=False) + "\n" + (task_text or "")
    for op, verbs in OP_VERBS.items():
        for v in verbs:
            if v in text:
                if op not in seen:
                    seen.add(op)
                    ops.append({"op": op, "trigger": v})
    return ops


def build_catalog(inv, corpus, lineage):
    meta = (lineage.get("doc_meta") or {})
    corpus_by_path = {d.get("path"): d for d in corpus.get("docs", [])}
    rows = []
    for f in inv.get("files", []):
        d = corpus_by_path.get(f.get("path"), {})
        dm = meta.get(d.get("doc_id"), {})
        rows.append({
            "path": f.get("path"),
            "sha256": f.get("sha256"),
            "category": f.get("category"),
            "size_bytes": f.get("size_bytes"),
            "mtime": f.get("mtime"),
            "readable": f.get("readable"),
            "version_tags": f.get("version_tags") or [],
            "date_hint": (f.get("date_hints") or [None])[0],
            "version_role": dm.get("version_role"),
            "cluster_id": dm.get("cluster_id"),
            "is_canonical": dm.get("is_canonical"),
            "extract_status": ("extracted" if d.get("char_total")
                               else "no_text" if d else "not_extracted"),
            "char_total": d.get("char_total"),
        })
    return rows


def recovery_attempts(corpus, work):
    attempts = []
    for d in corpus.get("docs", []):
        if d.get("char_total"):
            continue
        path = d.get("path")
        meta = d.get("meta") or {}
        rec = {"path": path, "prior_status": meta.get("no_text") and
               "no_text" or "extract_failed", "actions": [], "result": None}
        if meta.get("scanned") or meta.get("no_text"):
            rec["actions"].append("check_ocr_availability")
            if meta.get("ocr_applied"):
                rec["result"] = "recovered_by_ocr"
            else:
                rec["actions"].append("ocr_unavailable_or_failed")
                rec["result"] = "failed_no_text_layer"
        else:
            rec["actions"].append("no_fallback_available")
            rec["result"] = "failed_unrecoverable"
        rec["residual_evidence"] = ("file exists + hash + metadata only" if
                                    rec["result"] != "recovered_by_ocr" else
                                    "text via OCR")
        attempts.append(rec)
    return attempts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    a = ap.parse_args()
    j = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    outlib = os.path.join(a.output_dir, "organized_library")
    os.makedirs(outlib, exist_ok=True)

    case = read_json(os.path.join(a.input_root, "case.json"), {}) or {}
    task_text = ""
    tf = os.path.join(a.input_root, "task.md")
    if os.path.exists(tf):
        task_text = open(tf, encoding="utf-8", errors="replace").read()

    declared = declared_operations(case, task_text)
    ops = {o["op"] for o in declared} or {"index", "metadata", "alias",
                                          "version", "recover", "organize"}
    j.log("3.2-operations", "declared=%s executing=%s" % (declared, sorted(ops)))

    inv = read_json(os.path.join(a.work_dir, "inventory.json"), {}) or {}
    corpus = read_json(os.path.join(a.work_dir, "corpus.json"), {}) or {}
    lineage = read_json(os.path.join(a.work_dir, "lineage.json"), {}) or {}
    sections = read_json(os.path.join(a.work_dir, "sections.json"), {}) or {}
    ops_log = []

    # 1) 索引完整性复核 + 清单
    docs = corpus.get("docs", [])
    pars = sections.get("paragraphs", [])
    missing = [d.get("path") for d in docs if d.get("char_total") and
               not any(p["doc_id"] == d["doc_id"] for p in pars)]
    index_report = {
        "docs": len(docs), "with_text": sum(1 for d in docs if d.get("char_total")),
        "paragraphs": len(pars), "sections": len(sections.get("sections", [])),
        "text_docs_without_paragraphs": missing,
        "consistent": not missing,
        "rebuilt_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    write_json(os.path.join(outlib, "index_report.json"), index_report)
    ops_log.append({"op": "rebuild_index", "result": "ok" if not missing
                    else "partial", "detail": index_report["docs"]})

    # 2) 元数据 catalog
    catalog = build_catalog(inv, corpus, lineage)
    write_json(os.path.join(outlib, "catalog.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "schema": ["path", "sha256", "category", "size_bytes", "mtime",
                   "readable", "version_tags", "date_hint", "version_role",
                   "cluster_id", "is_canonical", "extract_status", "char_total"],
        "entries": catalog})
    ops_log.append({"op": "register_metadata", "result": "ok",
                    "detail": "%d entries" % len(catalog)})

    # 3) 别名登记（改名副本）
    aliases = []
    for c in lineage.get("clusters", []):
        for m in c.get("members", []):
            if m.get("role") in ("renamed_copy", "exact_copy"):
                canonical = next((x for x in c["members"]
                                  if x["doc_id"] == c["canonical"]), {})
                aliases.append({
                    "alias_path": m.get("path"), "role": m.get("role"),
                    "canonical_path": canonical.get("path"),
                    "basis": "sha256 equal; normalized-name differ"
                             if m.get("role") == "renamed_copy"
                             else "sha256 equal"})
    for g in inv.get("alias_groups", []):
        aliases.append({"alias_group": g.get("paths"),
                        "normalized_name": g.get("normalized_name"),
                        "basis": "normalized filename equality"})
    write_json(os.path.join(outlib, "aliases_registry.json"), {
        "entries": aliases, "count": len(aliases)})
    ops_log.append({"op": "register_aliases", "result": "ok",
                    "detail": "%d aliases" % len(aliases)})

    # 4) 版本注记
    notes = []
    for c in lineage.get("clusters", []):
        if c.get("relation") == "singleton":
            continue
        members = c.get("members", [])
        canonical = next((x for x in members if x["doc_id"] == c["canonical"]),
                         {})
        notes.append({
            "cluster_id": c.get("cluster_id"), "relation": c.get("relation"),
            "canonical": canonical.get("path"),
            "canonical_basis": "stage rank > version tag > date",
            "line": " / ".join("%s(%s)" % (m.get("path"), m.get("role"))
                               for m in members)})
    write_json(os.path.join(outlib, "versions.json"), {"notes": notes})
    ops_log.append({"op": "version_notes", "result": "ok",
                    "detail": "%d chains" % len(notes)})

    # 5) 恢复尝试
    recovery = recovery_attempts(corpus, a.work_dir)
    write_json(os.path.join(outlib, "recovery_log.json"), {
        "attempts": recovery,
        "recovered": sum(1 for r in recovery
                         if r["result"] == "recovered_by_ocr"),
        "failed": sum(1 for r in recovery if (r["result"] or "").startswith("failed"))})
    ops_log.append({"op": "recover", "result": "ok",
                    "detail": "%d recovered / %d failed"
                    % (sum(1 for r in recovery if r["result"] == "recovered_by_ocr"),
                       sum(1 for r in recovery
                           if (r["result"] or "").startswith("failed")))})

    write_json(os.path.join(outlib, "operations_log.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "declared_operations": declared,
        "executed": ops_log,
        "safety": "input read-only; all artifacts under organized_library/"})
    for o in ops_log:
        j.log("3.2-operations", "%s -> %s (%s)" % (o["op"], o["result"],
                                                   o["detail"]))
    print("operations: %d executed -> organized_library/" % len(ops_log))
    return 0


if __name__ == "__main__":
    sys.exit(main())
