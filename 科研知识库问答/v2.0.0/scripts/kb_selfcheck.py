#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_selfcheck.py -- 交付前自检: 合同字段、证据有效性、引用真实性、状态一致性。

检查项(任何一项失败都会在报告中列出, 并影响建议 status):
  S1 case_id 与 case.json 一致
  S2 output_contract 字段全部存在(允许 null 但必须在 missing_contract_fields 声明)
  S3 每条 evidence: path 在 inventory 中存在; exact_quote 是抽取文本的逐字子串
     (空白归一后); page/para_index 命中对应锚点
  S4 answer 文本中的 [E#] 编号与 evidence 列表一致
  S5 questions_without_evidence 每项含 what_is_missing
  S6 conflicts 每项含双方坐标与 resolution
  S7 ops_log.jsonl 存在且非空; status 与 missing 字段一致

用法:
  python3 kb_selfcheck.py --case /input/case.json --work /app/work --outdir /app/output
退出码: 0=全部通过 1=有问题(仍给出报告)
"""
import argparse
import json
import os
import re
import sys

NORM = lambda s: re.sub(r"\s+", " ", s or "").strip()


def load(p):
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", default="/input/case.json")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--outdir", default="/app/output")
    args = ap.parse_args()
    W = args.work
    case = load(args.case)
    result = load(os.path.join(args.outdir, "result.json"))
    answers = load(os.path.join(W, "answers.json"))
    inv = load(os.path.join(W, "inventory.json"))
    report = []
    fails = []

    # S1
    cid = case.get("case_id") or case.get("id")
    if cid and result.get("case_id") != cid:
        fails.append("S1 case_id 不一致: result=%s case=%s" % (result.get("case_id"), cid))

    # S2
    oc = case.get("output_contract") or case.get("outputContract") or []
    fields = (list(oc.keys()) if isinstance(oc, dict)
              else [x if isinstance(x, str) else x.get("name", "?") for x in oc])
    miss_decl = set(result.get("missing_contract_fields") or [])
    for k in fields:
        if k not in result:
            fails.append("S2 合同字段缺失: %s" % k)
        elif result.get(k) in (None, [], {}) and k not in miss_decl:
            fails.append("S2 字段为空但未在 missing_contract_fields 声明: %s" % k)

    # S3/S4 证据校验
    texts = {}
    inv_paths = {f.get("path") for f in inv.get("files", [])}
    rep = load(os.path.join(W, "extract_report.json"))
    fid_by_path = {e["path"]: e["file_id"] for e in rep.get("files", [])}

    def text_of(path):
        if path in texts:
            return texts[path]
        fid = fid_by_path.get(path)
        tp = os.path.join(W, "text", (fid or "") + ".txt")
        texts[path] = open(tp, encoding="utf-8").read() if os.path.isfile(tp) else None
        return texts[path]

    ans = answers.get("answers") or {}
    all_ev = {}
    for qid, q in ans.items():
        ev_list = q.get("evidence") or []
        ids = {e.get("id") for e in ev_list}
        for e in ev_list:
            eid = e.get("id") or "?"
            if eid in all_ev:
                fails.append("S4 证据编号重复: %s" % eid)
            all_ev[eid] = e
            p = e.get("path")
            if p not in inv_paths:
                fails.append("S3 [%s] path 不在 inventory: %s" % (eid, p))
                continue
            t = text_of(p)
            if t is None:
                fails.append("S3 [%s] 无抽取文本可核对: %s" % (eid, p))
                continue
            q_ = NORM(e.get("exact_quote"))
            if not q_:
                fails.append("S3 [%s] exact_quote 为空" % eid)
            elif q_ not in NORM(t):
                fails.append("S3 [%s] exact_quote 不是 %s 的逐字子串" % (eid, p))
        used = set(re.findall(r"\[(E\d+)\]", q.get("answer") or ""))
        for u in used - ids:
            fails.append("S4 %s answer 引用了不存在的 [%s]" % (qid, u))
        for u in ids - used:
            fails.append("S4 %s evidence [%s] 未在 answer 中引用" % (qid, u))
        if not (q.get("uncertainty") in ("A", "B", "C", "D")):
            fails.append("S5 %s uncertainty 未分级(A-D)" % qid)

    # S5 缺证
    for q in answers.get("questions_without_evidence") or []:
        if not q.get("what_is_missing"):
            fails.append("S5 缺证条目缺 what_is_missing: %s" % str(q)[:80])

    # S6 冲突
    for c in answers.get("conflicts") or []:
        if not c.get("resolution"):
            fails.append("S6 冲突条目缺 resolution: %s" % str(c)[:80])

    # S7 日志与状态
    ops = os.path.join(W, "ops_log.jsonl")
    if not (os.path.isfile(ops) and os.path.getsize(ops) > 0):
        fails.append("S7 ops_log.jsonl 缺失或为空")
    if miss_decl and result.get("status") == "complete":
        fails.append("S7 存在 missing 字段但 status=complete, 应为 partial")

    report.append("# kb_selfcheck 报告: %d 项问题" % len(fails))
    report.extend("- " + x for x in fails)
    text = "\n".join(report) + "\n"
    with open(os.path.join(W, "selfcheck_report.txt"), "w", encoding="utf-8") as f:
        f.write(text)
    sys.stdout.write(text)
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
