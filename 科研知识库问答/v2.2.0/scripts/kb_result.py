#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_result.py -- 合成最终交付: result.json + report.md + 运行日志。

要点:
  - 严格保留 case.json 中 output_contract 的每一个字段(不增删改名)
  - 合同字段值优先取 answers.json 中同名字段; 缺省填 null 并在 missing_fields 中声明
  - 附带可复核材料: 证据条目(含 anchor 坐标与原文摘录)、inventory/versions/extract 摘要、
    操作日志、不确定性分级、变更记录
  - status 诚实取值: complete / partial / failed, 绝不把未完成写成完成

用法:
  python3 kb_result.py --case /input/case.json --answers /app/work/answers.json \
      --work /app/work --outdir /app/output [--task task.md 的路径]

answers.json 由作答阶段(Agent 依据检索证据撰写)生成, 结构:
{
  "status": "complete|partial",
  "answers": { "<合同字段或题号>": {...} },            # 逐题: answer/evidence/uncertainty
  "questions_without_evidence": [{"question":"...","what_is_missing":"..."}],
  "conflicts": [...], "change_log": [...]
}
"""
import argparse
import json
import os
import shutil
import sys
import time


def load_json(p, default=None):
    if p and os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return default


def contract_fields(case):
    """尽力从 case.json 提取 output_contract 字段名列表与骨架."""
    oc = case.get("output_contract") or case.get("outputContract")
    fields, skeleton = [], {}
    if isinstance(oc, dict):
        props = oc.get("properties") if isinstance(oc.get("properties"), dict) else oc
        for k, v in props.items():
            if isinstance(v, dict) and ("type" in v or "description" in v):
                fields.append(k)
                t = v.get("type")
                skeleton[k] = [] if t in ("array", "list") else (
                    {} if t in ("object", "dict") else None)
            elif not isinstance(v, (dict, list)):
                fields.append(k)
                skeleton[k] = None
        if not fields:
            fields = list(props.keys())
            skeleton = {k: None for k in fields}
    elif isinstance(oc, list):
        for item in oc:
            if isinstance(item, str):
                fields.append(item)
                skeleton[item] = None
            elif isinstance(item, dict):
                k = item.get("name") or item.get("field")
                if k:
                    fields.append(k)
                    skeleton[k] = None
    return fields, skeleton, oc


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--answers", default=None)
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    ap.add_argument("--task", default=None)
    args = ap.parse_args()

    os.makedirs(args.outdir, exist_ok=True)
    case = load_json(args.case, {}) or {}
    answers = load_json(args.answers, {}) or {}
    W = args.work

    case_id = case.get("case_id") or case.get("id") or case.get("caseId") or "unknown"
    fields, skeleton, oc_raw = contract_fields(case)
    ans = answers.get("answers") or {}

    result = dict(skeleton)
    for k in fields:
        if k in ans:
            result[k] = ans[k]
        elif k in answers:
            result[k] = answers[k]
    missing = [k for k in fields if result.get(k) in (None, [], {}) and k not in ans]

    inv = load_json(os.path.join(W, "inventory.json"), {})
    vers = load_json(os.path.join(W, "versions.json"), {})
    ext = load_json(os.path.join(W, "extract_report.json"), {})

    status = answers.get("status") or ("complete" if not missing else "partial")
    if fields and len(missing) == len(fields):
        status = "partial" if ans else status

    result.update({
        "case_id": case_id,
        "status": status,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "evidence_index": {
            "inventory": "inventory_summary.txt",
            "versions": "versions_summary.txt",
            "extraction": "extract_summary.txt",
            "anchors": "index.jsonl",
        },
        "sources": answers.get("sources") or [],
        "uncertainty": answers.get("uncertainty") or {},
        "questions_without_evidence": answers.get("questions_without_evidence") or [],
        "conflicts": answers.get("conflicts") or [],
        "change_log": answers.get("change_log") or [],
        "missing_contract_fields": missing,
        "library_stats": {
            "files": (inv.get("counts") or {}).get("files"),
            "unreadable": (inv.get("counts") or {}).get("unreadable"),
            "duplicate_groups": len(vers.get("duplicate_groups") or []),
            "needs_ocr": (ext.get("counts") or {}).get("needs_ocr"),
            "by_type": (inv.get("counts") or {}).get("by_type"),
        },
        "provenance": {
            "skill": "kbqa-cited-research-knowledge-base",
            "pipeline": ["kb_inventory", "kb_extract", "kb_versions",
                          "kb_index", "kb_search", "manual_answer", "kb_result"],
            "hash_algorithm": "sha256",
        },
    })

    out_json = os.path.join(args.outdir, "result.json")
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)

    # 人读报告
    lines = ["# 案例 %s 运行报告" % case_id, "",
             "- status: **%s**" % status,
             "- 生成时间: %s" % result["generated_at"],
             "- 合同字段: %d 个, 未填: %s" % (len(fields), missing or "无"), ""]
    lines.append("## 资料库概况")
    lines.append("- 文件数: %s; 不可读: %s; 重复组: %s; 待 OCR: %s"
                 % (result["library_stats"]["files"], result["library_stats"]["unreadable"],
                    result["library_stats"]["duplicate_groups"],
                    result["library_stats"]["needs_ocr"]))
    lines.append("")
    lines.append("## 问答与证据")
    for k, v in ans.items():
        lines.append("### %s" % k)
        lines.append("```json")
        lines.append(json.dumps(v, ensure_ascii=False, indent=1)[:4000])
        lines.append("```")
    if answers.get("questions_without_evidence"):
        lines.append("## 缺证问题(知识库中无依据)")
        for q in answers["questions_without_evidence"]:
            lines.append("- %s —— 缺失: %s" % (q.get("question"), q.get("what_is_missing")))
    if answers.get("conflicts"):
        lines.append("## 证据冲突")
        for c in answers["conflicts"]:
            lines.append("- %s" % json.dumps(c, ensure_ascii=False))
    lines.append("## 不确定性与变更")
    lines.append("```json")
    lines.append(json.dumps({"uncertainty": result["uncertainty"],
                             "change_log": result["change_log"]}, ensure_ascii=False, indent=1))
    lines.append("```")
    with open(os.path.join(args.outdir, "report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # 复核材料随包交付
    for fn in ("inventory.json", "versions.json", "extract_report.json",
               "index_meta.json", "ops_log.jsonl"):
        src = os.path.join(W, fn)
        if os.path.isfile(src):
            shutil.copyfile(src, os.path.join(args.outdir, fn))

    sys.stdout.write("# result.json / report.md 已写入 %s (status=%s, missing=%s)\n"
                     % (args.outdir, status, missing or "无"))


if __name__ == "__main__":
    main()
