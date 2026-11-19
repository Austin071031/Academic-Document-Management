#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""constraints.py — 【版本3 旗舰】约束编译器与硬过滤执行器。

把任务文本中的条件编译为强类型谓词并执行：
- year        : (19|20)XX 年、YYYY–YYYY、"近 N 年/内"
- project_id  : 项目/课题编号（字母+数字组合、"编号"引导串）
- doc_type    : PDF/Word/Excel/PPT/扫描件/补充材料 → 类别映射
- version     : 最新版/终版/修订版/vN/旧版（与 lineage 协作）
- permission  : 仅可读（默认硬约束：不可读文件一律排除并记录）
- path_scope  : 指定目录/子库名
- batch       : 批次号（batch/批次 + 字母数字）

执行结果:
- predicates.json : 每条谓词含 source_quote（任务原文片段）、status、matched/excluded 计数。
- filter.json     : 交给 retrieve.py 的机器可执行过滤条件。
- filter_audit.json: 逐文档决定与理由；不可满足时输出冲突诊断而非静默放宽。
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import Journal, read_json, write_json

DOC_TYPE_MAP = {
    "pdf": ["pdf"], "word": ["docx", "doc-legacy"], "doc": ["docx", "doc-legacy"],
    "excel": ["xlsx", "xls-legacy"], "xls": ["xlsx", "xls-legacy"],
    "ppt": ["pptx", "ppt-legacy"], "幻灯片": ["pptx", "ppt-legacy"],
    "扫描件": ["pdf"], "补充材料": None, "附件": None,
}


def compile_predicates(task_text, now_year=None):
    now_year = now_year or int(time.strftime("%Y"))
    preds = []
    t = task_text or ""

    def add(field, op, value, source, confidence=0.9):
        preds.append({"field": field, "op": op, "value": value,
                      "source_quote": source.strip()[:120],
                      "confidence": confidence})

    for m in re.finditer(r"(?<!\d)((?:19|20)\d{2})\s*[-–~至到]\s*((?:19|20)\d{2})(?!\d)", t):
        add("year", "between", [int(m.group(1)), int(m.group(2))], m.group(0))
    for m in re.finditer(r"(?<![\d\-])((?:19|20)\d{2})\s*年?(?!\d)", t):
        y = int(m.group(1))
        if not any(p["field"] == "year" and p["op"] == "between"
                   and p["value"][0] <= y <= p["value"][1] for p in preds):
            add("year", "in", [y], m.group(0), 0.75)
    m = re.search(r"近\s*(\d{1,2})\s*年", t)
    if m:
        add("year", "between", [now_year - int(m.group(1)), now_year],
            m.group(0), 0.8)

    for m in re.finditer(r"(?i)(?:项目|课题|基金|批准|任务)[编号]?\s*[:：]?\s*([A-Z]{1,6}[-_]?\d{3,8}[A-Z0-9-]*)", t):
        add("project_id", "contains", m.group(1).upper(), m.group(0))
    for m in re.finditer(r"(?i)\b([A-Z]{2,6}[-_]?\d{4,10})\b", t):
        s = m.group(1)
        if re.search(r"\d", s):
            add("project_id", "contains", s.upper(), m.group(0), 0.7)

    low = t.lower()
    for word, cats in DOC_TYPE_MAP.items():
        if word in low or word in t:
            if cats:
                add("doc_type", "in", cats, word, 0.85)
            else:
                add("doc_type_note", "flag", word, word, 0.6)

    if re.search(r"最新版|最新版本|终版|最终版|定稿", t):
        add("version", "is_canonical", True, "最新版/终版", 0.9)
    m = re.search(r"(?i)\bv\s?(\d+(?:\.\d+)*)", t)
    if m:
        add("version", "tag_prefix", "v" + m.group(1), m.group(0), 0.85)
    if re.search(r"旧版|早期版本|上一版", t):
        add("version", "is_canonical", False, "旧版", 0.8)

    for m in re.finditer(r"(?i)(?:batch|批次)\s*[:：]?\s*([A-Za-z0-9\-]{1,12})", t):
        add("batch", "contains", m.group(1).upper(), m.group(0))

    for m in re.finditer(r"[「\"']([^「」\"']{2,60})[」\"']", t):
        add("path_scope", "contains", m.group(1), m.group(0), 0.7)

    # 默认硬约束：仅处理可读文件（不解密、不越权）
    add("permission", "readable", True, "默认硬约束:仅可读文件", 1.0)
    return preds


def execute(predicates, work):
    corpus = read_json(os.path.join(work, "corpus.json"), {}) or {}
    inv = read_json(os.path.join(work, "inventory.json"), {}) or {}
    lineage = read_json(os.path.join(work, "lineage.json"), {}) or {}
    doc_meta = lineage.get("doc_meta", {})

    files_by_path = {f["path"]: f for f in inv.get("files", [])}
    docs = corpus.get("docs", [])

    # 年份元数据
    import retrieve as R
    meta = R.build_docmeta(corpus)

    def check(d, invf, p):
        f, op, v = p["field"], p["op"], p["value"]
        if f == "year":
            years = meta.get(d["doc_id"], {}).get("years_in_text") or []
            lo, hi = (v if isinstance(v, list) else [v, v])[:2]
            return bool(years) and lo <= max(years) and min(years) <= hi
        if f == "project_id":
            text = "\n".join(pg.get("text", "")[:30000]
                             for pg in d.get("pages", []))
            return v in text.upper()
        if f == "doc_type":
            return d.get("category") in v
        if f == "version":
            dm = doc_meta.get(d["doc_id"], {})
            if op == "is_canonical":
                return dm.get("is_canonical", True) == v
            if op == "tag_prefix":
                tags = ([dm["version_tag"]] if dm.get("version_tag") else []) \
                    + list(d.get("version_tags") or [])
                return any(str(t).startswith(v) for t in tags)
        if f == "permission":
            return bool(invf.get("readable", True))
        if f == "path_scope":
            return v in d.get("path", "")
        if f == "batch":
            text = "\n".join(pg.get("text", "")[:30000]
                             for pg in d.get("pages", []))
            return v in text.upper()
        if f == "doc_type_note":
            return True  # 语义备注：由 Agent 在答案中回应，不作硬排他
        return True

    decisions = {}
    per_pred_matched = {i: 0 for i in range(len(predicates))}
    for d in docs:
        invf = files_by_path.get(d.get("path"), {})
        kept, reasons = True, []
        for i, p in enumerate(predicates):
            ok = check(d, invf, p)
            if ok:
                per_pred_matched[i] += 1
            else:
                kept = False
                reasons.append("predicate %s %s %s not satisfied"
                               % (p["field"], p["op"], p["value"]))
        decisions[d["doc_id"]] = {"path": d.get("path"),
                                  "decision": "kept" if kept else "excluded",
                                  "reasons": reasons}

    summary = []
    for i, p in enumerate(predicates):
        matched = per_pred_matched[i]
        status = "satisfied" if matched > 0 else "unsatisfied"
        summary.append({**p, "docs_matched": matched, "status": status})
    return decisions, summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--task-file", default="/input/task.md")
    ap.add_argument("--query-text", default=None,
                    help="若无 task 文件，直接传入任务文本")
    a = ap.parse_args()

    journal = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    text = a.query_text
    if text is None and os.path.exists(a.task_file):
        with open(a.task_file, encoding="utf-8", errors="replace") as f:
            text = f.read()
    text = text or ""

    preds = compile_predicates(text)
    decisions, summary = execute(preds, a.work_dir)

    # 机器过滤条件（传给 retrieve.py）
    flt = {}
    for p in preds:
        if p["field"] == "year" and p["op"] == "between":
            flt["year"] = p["value"]
        elif p["field"] == "doc_type" and p["op"] == "in":
            flt["doc_type"] = sorted(set(flt.get("doc_type", [])) | set(p["value"]))
        elif p["field"] == "version" and p["op"] == "is_canonical" \
                and p["value"] is False:
            lineage = read_json(os.path.join(a.work_dir, "lineage.json"), {}) or {}
            flt["exclude_sha256"] = lineage.get("exclude_sha256", [])
    write_json(os.path.join(a.work_dir, "filter.json"), flt)

    unsatisfied = [p for p in summary if p["status"] == "unsatisfied"]
    write_json(os.path.join(a.work_dir, "filter_audit.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "predicates": summary,
        "decisions": decisions,
        "unsatisfied_constraints": unsatisfied,
        "policy": "hard_filter: 条件不满足的文档一律排除；绝不静默放宽；"
                  "全部谓词不可满足时结果集为空并在此说明原因",
    })
    write_json(os.path.join(a.work_dir, "predicates.json"), summary)
    journal.log("3.5-constraints", "predicates=%d unsatisfied=%d"
                % (len(summary), len(unsatisfied)),
                status="ok" if not unsatisfied else "partial")
    print("predicates=%d unsatisfied=%d" % (len(summary), len(unsatisfied)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
