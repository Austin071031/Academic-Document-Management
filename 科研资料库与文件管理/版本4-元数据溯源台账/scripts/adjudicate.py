#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""adjudicate.py —— 冲突裁决器。

同一 (file, field) 存在多来源候选时，按优先级
    admin_note > companion_table > content > filename > agent_inference
取最高优先级；同级冲突取置信度高者，再平则按证据字符串字典序取确定性第一个，
并把所有落选候选记入 conflicts（绝不丢弃证据）。
file="*" 的候选视为库级默认：仅当某文件该字段无任何候选时补用，置信度 ×0.9。
同时合并 Agent 后续写入的 work/agent_candidates.jsonl（source=agent_inference，
永远最低优先级，允许被任何证据来源覆盖）。
输出 work/provenance.jsonl：逐字段一条台账记录。
"""
import argparse
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402


def prio(source):
    try:
        return lc.SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(lc.SOURCE_PRIORITY)


def pick(cands):
    """返回 (winner, conflicts)。"""
    ordered = sorted(cands,
                     key=lambda c: (prio(c.get("source")),
                                    -float(c.get("confidence", 0.5)),
                                    str(c.get("evidence", ""))))
    winner = ordered[0]
    conflicts = [
        {"value": c.get("value"), "source": c.get("source"),
         "evidence": c.get("evidence"), "confidence": c.get("confidence")}
        for c in ordered[1:]
        if c.get("value") != winner.get("value")
    ]
    # 同值多来源不算冲突，但保留在 winner.evidence 中说明
    same = [c for c in ordered[1:] if c.get("value") == winner.get("value")]
    if same:
        winner = dict(winner)
        winner["evidence"] = "%s | corroborated by: %s" % (
            winner.get("evidence"),
            "; ".join(sorted({c.get("source", "?") for c in same})))
    return winner, conflicts


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    a = ap.parse_args()

    dictionary = lc.load_dictionary(a.work, a.config)
    known_fields = set((dictionary.get("fields") or {}).keys())

    groups = defaultdict(list)     # (file, field) -> [cand]
    global_cands = defaultdict(list)  # field -> [cand]
    n_total = 0
    for c in lc.jlines(os.path.join(a.work, "candidates.jsonl")) or []:
        if not c.get("field") or c.get("value") in (None, ""):
            continue
        if known_fields and c["field"] not in known_fields:
            continue
        n_total += 1
        if c.get("file") == "*":
            global_cands[c["field"]].append(c)
        else:
            groups[(c["file"], c["field"])].append(c)
    # 合并 Agent 补录（最低优先级）
    agent_path = os.path.join(a.work, "agent_candidates.jsonl")
    n_agent = 0
    for c in lc.jlines(agent_path) or []:
        c = dict(c)
        c["source"] = "agent_inference"
        c.setdefault("confidence", lc.SOURCE_CONFIDENCE["agent_inference"])
        if not c.get("field") or c.get("value") in (None, ""):
            continue
        if known_fields and c["field"] not in known_fields:
            continue
        n_agent += 1
        groups[(c.get("file"), c["field"])].append(c)

    files = [r["relpath"] for r in lc.jlines(os.path.join(a.work, "files.jsonl")) or []]

    # 库级默认补用
    for field, gc in global_cands.items():
        for f in files:
            if (f, field) not in groups:
                w, _ = pick(gc)
                w = dict(w)
                w["file"] = f
                w["confidence"] = round(float(w.get("confidence", 0.9)) * 0.9, 3)
                w["evidence"] = "library-wide default applied | " + str(w.get("evidence"))
                groups[(f, field)].append(w)

    records, n_conflict = [], 0
    for (f, field) in sorted(groups.keys()):
        winner, conflicts = pick(groups[(f, field)])
        if conflicts:
            n_conflict += 1
        records.append({
            "file": f,
            "field": field,
            "value": winner.get("value"),
            "source": winner.get("source"),
            "evidence": winner.get("evidence"),
            "confidence": winner.get("confidence"),
            "conflicts": conflicts,
            "rule": "priority: " + lc.PRIORITY_RULE_STR,
            "adjudicated_at": lc.now_iso(),
        })

    # 覆盖式重写（adjudicate 可重入：Agent 补录后再跑一次）
    out_path = os.path.join(a.work, "provenance.jsonl")
    if os.path.exists(out_path):
        os.remove(out_path)
    lc.jappend(out_path, records)
    lc.jwrite(os.path.join(a.work, "adjudicate_summary.json"), {
        "candidates_in": n_total,
        "agent_candidates_in": n_agent,
        "records_out": len(records),
        "fields_with_conflicts": n_conflict,
        "rule": lc.PRIORITY_RULE_STR,
        "adjudicated_at": lc.now_iso(),
    })
    lc.log_change(a.work, "adjudicate", "provenance.jsonl",
                  lc.PRIORITY_RULE_STR,
                  "%d records, %d fields had conflicts" % (len(records), n_conflict))
    print("[adjudicate] records=%d conflicts=%d" % (len(records), n_conflict))
    return 0


if __name__ == "__main__":
    sys.exit(main())
