#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report.py — 组装最终交付：严格镜像 case.json 的 output_contract。

两个阶段：
  --skeleton : 读取 /input/case.json 的 output_contract 与任务参数，
               结合 work 产物预填结构化字段，答案类字段留 null 并给出
               fill_hint，写入 /app/output/result.json（半成品也落盘）。
  --finalize : 校验 result.json（contract 字段齐全、证据均通过校验、
               状态诚实、无未解释 null），写 manifest 与变更记录。

字段预填启发式（字段名命中即填，未命中保持 null+hint）：
  files/inventory → inventory.files；evidence/citations/hits → 已校验命中；
  versions/duplicates → 版本关系；failures/skipped → 失败记录；
  filters → 过滤审计；manifest/checksum → 输出哈希清单。
"""
import argparse
import json
import os
import re
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import (SKILL_VERSION, Journal, read_json, sha256_file,
                    write_json)

FILL_PATTERNS = [
    (r"files|inventory|file_list|document_list", "files"),
    (r"evidence|citations?|hits|sources|anchors?", "evidence"),
    (r"versions?|duplicates?|lineage", "versions"),
    (r"failures?|errors?|skipped|exceptions?", "failures"),
    (r"filters?|constraints?|conditions?", "filters"),
    (r"manifest|checksums?|hashes", "manifest"),
    (r"metadata", "metadata"),
    (r"sections?|toc|structure", "sections"),
    (r"answers?|results?|conclusions?|findings", "answer"),
    (r"query|question", "query"),
    (r"status|state", "status"),
    (r"summary|abstract|overview", "summary"),
]


def contract_fields(case):
    oc = case.get("output_contract") or case.get("outputContract") or {}
    if isinstance(oc, list):
        return {f: None for f in oc}, "list"
    if isinstance(oc, dict):
        if "properties" in oc:  # JSON schema
            req = oc.get("required") or []
            props = oc.get("properties") or {}
            return ({k: ("required" if k in req else "optional")
                     for k in props}, "schema")
        return {k: (v if isinstance(v, str) else "specified")
                for k, v in oc.items()}, "dict"
    return {}, "none"


def guess_kind(field_name):
    low = field_name.lower()
    for pat, kind in FILL_PATTERNS:
        if re.search(pat, low):
            return kind
    return None


def build_payloads(work):
    inv = read_json(os.path.join(work, "inventory.json"), {}) or {}
    hits = read_json(os.path.join(work, "hits.json"), {}) or {}
    corpus = read_json(os.path.join(work, "corpus.json"), {}) or {}
    sections = read_json(os.path.join(work, "sections.json"), {}) or {}
    lineage = (read_json(os.path.join(work, "lineage.json"), {}) or {})
    verif = read_json(os.path.join(work, "verification.json"), {}) or {}
    audit = (read_json(os.path.join(work, "filter_audit.json"), {})
             or hits.get("filter_audit") or {})

    evidence = []
    for h in hits.get("hits", []):
        if h.get("verified"):
            evidence.append(h.get("anchor"))
    failures = list(inv.get("failures") or []) + list(corpus.get("failures") or [])
    return {
        "files": [{"path": f.get("path"), "category": f.get("category"),
                   "sha256": f.get("sha256"), "size_bytes": f.get("size_bytes"),
                   "readable": f.get("readable")} for f in inv.get("files", [])],
        "evidence": evidence,
        "versions": lineage.get("clusters") or lineage.get("version_graph") or [],
        "failures": failures,
        "filters": {"applied": hits.get("filter") or {},
                    "audit": audit},
        "manifest": None,  # finalize 阶段填充
        "metadata": {"docs_parsed": corpus.get("stats"),
                     "sections_found": sections.get("stats")},
        "sections": sections.get("sections", [])[:200],
        "answer": None,     # 由 Agent 依据 evidence 撰写
        "query": hits.get("query"),
        "status": None,
        "summary": None,
    }


def skeleton(args):
    work, outdir = args.work_dir, args.output_dir
    journal = Journal(os.path.join(work, "run_journal.jsonl"))
    case = read_json(os.path.join(args.input_root, "case.json"), {}) or {}
    fields, kind = contract_fields(case)
    payloads = build_payloads(work)

    result = {"case_id": case.get("case_id") or case.get("id"),
              "_contract_kind": kind, "_contract_fields": fields}
    hints = {}
    for fname in fields:
        k = guess_kind(fname)
        if k and payloads.get(k) is not None:
            result[fname] = payloads[k]
        else:
            result[fname] = None
            hints[fname] = ("agent_fill: 依据 hits.json 中 verified=true 的证据"
                            "填写；无法确定时保持 null 并在 uncertainty 说明" if k in
                            ("answer", "summary", "status") else
                            "no_source: 工作产物中无对应数据，保持 null 并说明")
    result["_fill_hints"] = hints
    result["uncertainty"] = []
    os.makedirs(outdir, exist_ok=True)
    write_json(os.path.join(outdir, "result.json"), result)
    journal.log("6-report", "skeleton written, contract fields=%d" % len(fields),
                outputs=[os.path.join(outdir, "result.json")])
    print("skeleton: %d contract fields -> %s" % (len(fields), outdir))
    return 0


def finalize(args):
    work, outdir = args.work_dir, args.output_dir
    journal = Journal(os.path.join(work, "run_journal.jsonl"))
    rpath = os.path.join(outdir, "result.json")
    result = read_json(rpath, {}) or {}
    case = read_json(os.path.join(args.input_root, "case.json"), {}) or {}
    fields, _ = contract_fields(case)
    verif = read_json(os.path.join(work, "verification.json"), {}) or {}
    problems = []

    for fname, req in fields.items():
        if fname not in result:
            problems.append("missing_contract_field:%s" % fname)
            result[fname] = None
        if result.get(fname) is None and req in ("required", "specified"):
            hint = (result.get("_fill_hints") or {}).get(fname, "")
            if "agent_fill" not in hint and "no_source" not in hint:
                problems.append("null_required_field:%s" % fname)
    for h in read_json(os.path.join(work, "hits.json"), {}).get("hits", []):
        if not h.get("verified"):
            problems.append("unverified_evidence_kept:%s"
                            % h.get("anchor", {}).get("file_path"))
    fails = result.get("failures") or []
    status = result.get("status")
    if fails and status == "success":
        problems.append("status_success_but_failures_present")
    if not result.get("case_id"):
        problems.append("missing_case_id")

    result["_final_check"] = {
        "checked_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "problems": problems,
        "verification_pass_rate": verif.get("pass_rate"),
        "skill_version": SKILL_VERSION,
    }
    result.pop("_fill_hints", None)
    result.pop("_contract_kind", None)
    write_json(rpath, result)

    # 输出清单（哈希）+ 变更记录；清单自身与变更记录不计入哈希（避免自引用）
    BOOKKEEPING = {"manifest.json", "changes.json"}
    manifest = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "outputs": []}
    for dp, dn, fn in os.walk(outdir):
        for f in sorted(fn):
            if f in BOOKKEEPING:
                continue
            p = os.path.join(dp, f)
            manifest["outputs"].append({"path": os.path.relpath(p, outdir),
                                        "sha256": sha256_file(p),
                                        "size_bytes": os.path.getsize(p)})
    write_json(os.path.join(outdir, "manifest.json"), manifest)
    prev = read_json(os.path.join(work, "prev_manifest.json"))
    changes = {"previous": prev, "current": manifest["outputs"]}
    write_json(os.path.join(outdir, "changes.json"), changes)
    write_json(os.path.join(work, "prev_manifest.json"), manifest["outputs"])

    journal.log("6-report", "finalize: problems=%d" % len(problems),
                outputs=[rpath, os.path.join(outdir, "manifest.json")])
    print("finalize: %d problem(s)" % len(problems))
    for p in problems:
        print("  -", p)
    return 0 if not problems else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input-root", default="/input")
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    ap.add_argument("--skeleton", action="store_true")
    ap.add_argument("--finalize", action="store_true")
    a = ap.parse_args()
    if a.finalize:
        return finalize(a)
    return skeleton(a)


if __name__ == "__main__":
    sys.exit(main())
