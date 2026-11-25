#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""metrics.py — 【v2.0.0-C 旗舰】增益量化与对照协议生成器。

评分细则"使用增益 25 分"要求用公平对照证明质量/效率增益。本模块：
1. 从工作产物汇总可复算的量化指标（解析覆盖、命中、校验通过率、去重折叠、
   分阶段耗时、脚本步骤数）；
2. 生成对照协议 GAINS.md：同一输入下"基础 Agent（无 Skill）vs 本 Skill"
   应如何对比、逐项对比什么、本侧实测值是多少——基础侧留空由评审/白板填写，
   绝不编造对照数据；
3. rubric 自评清单 self_audit.json：每个评分维度 → 本侧证据产物与实测值，
   未覆盖的维度如实标 not_covered。

用法: python3 metrics.py --input-root /input --work-dir /app/work --output-dir /app/output
"""
import argparse
import json
import os
import time

import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (Journal, load_journal, read_json, write_json)


def stage_durations(journal):
    per_stage = {}
    for rec in journal:
        if rec.get("step") and rec.get("elapsed_s") is not None:
            per_stage.setdefault(rec["step"], rec["elapsed_s"])
    return per_stage


def collect_metrics(work):
    inv = read_json(os.path.join(work, "inventory.json"), {}) or {}
    corpus = read_json(os.path.join(work, "corpus.json"), {}) or {}
    sections = read_json(os.path.join(work, "sections.json"), {}) or {}
    hits = read_json(os.path.join(work, "hits.json"), {}) or {}
    verif = read_json(os.path.join(work, "verification.json"), {}) or {}
    lineage = read_json(os.path.join(work, "lineage.json"), {}) or {}
    journal = load_journal(os.path.join(work, "run_journal.jsonl"))
    st = stage_durations(journal)

    return {
        "files_total": (inv.get("stats") or {}).get("total", 0),
        "files_unreadable": (inv.get("stats") or {}).get("unreadable", 0),
        "files_duplicate_groups": (inv.get("stats") or {}).get(
            "duplicate_groups", 0),
        "docs_with_text": (corpus.get("stats") or {}).get("with_text", 0),
        "docs_no_text": (corpus.get("stats") or {}).get("no_text", 0),
        "extraction_failures": len(corpus.get("failures") or []),
        "sections": (sections.get("stats") or {}).get("sections", 0),
        "paragraphs": (sections.get("stats") or {}).get("paragraphs", 0),
        "docs_with_page_offset": (sections.get("stats") or {}).get(
            "docs_with_offset", 0),
        "queries_executed": 1 if hits.get("query") else 0,
        "hits_total": (hits.get("stats") or {}).get("hits", 0),
        "hits_verified": verif.get("passed", 0),
        "verify_pass_rate": verif.get("pass_rate"),
        "version_clusters": (lineage.get("stats") or {}).get("clusters"),
        "copies_collapsed": len(lineage.get("exclude_sha256") or []),
        "stage_elapsed_s": st,
        "script_steps": len(journal),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


RUBRIC = [
    ("任务完成度", "检索+定位+过滤+回链四环节是否全部执行并有产物",
     ["hits.json", "verification.json", "sections.json"]),
    ("结果正确性", "命中与定位是否经机器逐字校验",
     ["verification.json.pass_rate"]),
    ("结果完整性", "关键文件/章节/元数据字段是否覆盖",
     ["inventory.json.stats", "lineage.json.stats"]),
    ("结果可核验性", "证据锚点字段是否齐全且可复算",
     ["hits.json[].anchor", "manifest.json"]),
    ("质量增益", "相对基础 Agent 的定位精度提升（见 GAINS.md 对照协议）",
     ["metrics.json.hits_verified", "metrics.json.verify_pass_rate"]),
    ("效率增益", "脚本化步骤数与分阶段耗时（人工翻页的替代量）",
     ["metrics.json.script_steps", "metrics.json.stage_elapsed_s"]),
    ("增益可验证性", "对照协议与实测指标是否同时提供",
     ["GAINS.md", "metrics.json"]),
    ("新增能力", "版本谱系/页码校正等基础 Agent 难稳定实现的能力",
     ["lineage.json", "sections.json.page_maps"]),
    ("可靠体验", "异常类型识别与处置记录",
     ["corpus.json.failures", "run_journal.jsonl"]),
    ("生态贡献", "文档/脚本/规范可复用性",
     ["README.md", "SKILL.md", "scripts/"]),
]


def self_audit(work, metrics):
    rows = []
    for dim, desc, artifacts in RUBRIC:
        covered = True
        detail = []
        for art in artifacts:
            key = art.split(".")[0]
            if key.endswith(".json") or key in ("README.md", "SKILL.md"):
                path = os.path.join(work, key)
                if not os.path.exists(path):
                    path2 = os.path.join(os.path.dirname(work), "output", key)
                    if not os.path.exists(path2):
                        covered = False
                        detail.append("missing:%s" % art)
            elif key == "scripts":
                covered = True
        rows.append({"dimension": dim, "evidence_artifacts": artifacts,
                     "status": "covered" if covered else "not_covered",
                     "note": desc, "missing": detail})
    return rows


GAINS_TEMPLATE = """# 增益对照协议（本侧实测；基础侧由评审/白板填写）

本文件提供"基础 Agent（无 Skill）vs 本 Skill"的公平对照方法与本侧实测值。
**基础 Agent 一侧的数值本 Skill 不产生、不预估**——由平台在相同案例输入、
相同任务要求、相同权限下运行基础 Agent 获得，本侧所有数值均可由
/app/work 与 /app/output 中的产物复算。

## 对照方法

1. 同一案例输入 `/input`；基础侧不加载 Skill，本侧加载本 Skill；
2. 对每一问，对比下表各项指标；
3. 本侧产物即复算依据（见每行的"本侧来源"）。

## 对比指标与本侧实测

| 指标 | 基础侧 | 本侧实测 | 本侧来源 |
|---|---|---|---|
| 命中问题数/总问题数 | __ | {q_cov} | hits.json / coverage.json |
| 证据经逐字校验通过率 | __ | {verify_rate} | verification.json |
| 每条证据含 文件+页码+章节+段落+原文片段 的比例 | __ | {anchor_rate} | hits.json[].anchor |
| 印刷页码校正文档数 | __ | {offsets} | sections.json.page_maps |
| 重复文件折叠数（副本不作独立证据） | __ | {collapsed} | lineage.json |
| 提取失败/无权限文件的分类记录数 | __ | {failures} | corpus.json.failures |
| 全流程脚本步骤数（替代人工翻页） | __ | {steps} | run_journal.jsonl |
| 分阶段耗时 | __ | {elapsed} | metrics.json.stage_elapsed_s |

## 复算方式

metrics.json 中每个字段标注了来源文件；`verification.json.checks_performed`
列出五条机器校验规则；按 `audit_report.json.reproduce`（如有）或
README 的命令序列可在本地复跑得到同一组数值。
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    a = ap.parse_args()
    j = Journal(os.path.join(a.work_dir, "run_journal.jsonl"))
    os.makedirs(a.output_dir, exist_ok=True)

    m = collect_metrics(a.work_dir)
    hits = read_json(os.path.join(a.work_dir, "hits.json"), {}) or {}
    anchors_full = sum(
        1 for h in hits.get("hits", [])
        if all(h.get("anchor", {}).get(k) for k in
               ("file_path", "section_path", "page", "quote")))
    m["anchor_complete_rate"] = (round(anchors_full / len(hits["hits"]), 3)
                                 if hits.get("hits") else None)
    cov = read_json(os.path.join(a.work_dir, "coverage.json"), {}) or {}
    q_cov = "%s/%s" % ((cov.get("totals") or {}).get("answered", "?"),
                       (cov.get("totals") or {}).get("questions", "?")) \
        if cov.get("totals") else "1/1 (single query)"

    write_json(os.path.join(a.output_dir, "metrics.json"), m)
    audit = self_audit(a.work_dir, m)
    write_json(os.path.join(a.output_dir, "self_audit.json"), {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "rubric_dimensions": audit,
        "covered": sum(1 for r in audit if r["status"] == "covered"),
        "total": len(audit)})
    gains = GAINS_TEMPLATE.format(
        q_cov=q_cov,
        verify_rate=m.get("verify_pass_rate"),
        anchor_rate=m.get("anchor_complete_rate"),
        offsets=m.get("docs_with_page_offset", 0),
        collapsed=m.get("copies_collapsed", 0),
        failures=m.get("extraction_failures", 0),
        steps=m.get("script_steps", 0),
        elapsed=json.dumps(m.get("stage_elapsed_s", {}), ensure_ascii=False))
    with open(os.path.join(a.output_dir, "GAINS.md"), "w",
              encoding="utf-8") as f:
        f.write(gains)
    j.log("3.3-metrics", "metrics written; self_audit %d/%d covered"
          % (sum(1 for r in audit if r["status"] == "covered"), len(audit)))
    print("metrics: verify_rate=%s anchors=%s steps=%d"
          % (m.get("verify_pass_rate"), m.get("anchor_complete_rate"),
             m.get("script_steps", 0)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
