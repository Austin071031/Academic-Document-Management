#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step5 finalize：合并生成最终 result.json。

result.json 必含：case.json 中 output_contract 的全部字段 + case_id，
并有诚实的 status、sources/evidence、uncertainty、change_records。
本模块在 ingest 完成后也会被立即调用一次（stage=partial），先写
status="partial" 的 result.json，防止后续步骤失败时没有任何产出。

契约字段填充策略：按字段名启发式映射到已计算产物；无法映射的字段
置 null 并在 uncertainty 中如实说明原因，绝不编造。
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cas_common import load_jsonl, read_json, write_json


def _short(s, n=400):
    s = str(s)
    return s if len(s) <= n else s[:n] + "…"


def _fill_field(name, ctx):
    """按字段名把 output_contract 字段映射到已计算产物。"""
    n = str(name).lower()
    idx = ctx.get("index") or {}
    ver = ctx.get("versions") or {}
    sea = ctx.get("search") or {}
    ing = ctx.get("ingest") or {}
    files = idx.get("files", [])

    wants_count = any(k in n for k in ("count", "num", "total", "数", "数量"))
    if n in ("status", "状态"):
        return ctx["status"], None
    if any(k in n for k in ("file", "文件")) and not any(
            k in n for k in ("tree", "struct", "结构")):
        if wants_count:
            return idx.get("stats", {}).get("indexed_files",
                                            ing.get("files_seen", 0)), None
        return [{"path": f["source_path"], "logical_path": f["logical_path"],
                 "sha256": f["content_id"], "size": f.get("size"),
                 "mtime": f.get("mtime")} for f in files], None
    if "dup" in n or "重复" in n or "别名" in n or "alias" in n:
        groups = ver.get("duplicate_groups", [])
        if wants_count:
            return len(groups), None
        return groups, None
    if any(k in n for k in ("version", "版本", "lineage", "谱系", "chain")):
        if wants_count:
            return ver.get("stats", {}).get("version_clusters", 0), None
        return {"nodes": ver.get("nodes", []), "edges": ver.get("edges", []),
                "clusters": ver.get("clusters", [])}, None
    if any(k in n for k in ("search", "检索", "查询", "keyword")):
        return sea.get("searches", []), None
    if any(k in n for k in ("question", "问题", "answer", "答案", "qa")):
        return sea.get("questions", []), None
    if any(k in n for k in ("tree", "struct", "结构", "目录", "hierarch")):
        return sorted({"/".join(f["logical_path"].split("/")[:-1])
                       for f in files}), None
    if any(k in n for k in ("index", "索引")):
        return {"path": "library/index.json",
                "stats": idx.get("stats", {})}, None
    if any(k in n for k in ("summary", "摘要", "概览", "overview")):
        return _short(
            "入库 %s 个文件（唯一内容 %s 个，去重 %s 次）；"
            "精确重复组 %s 个；版本簇 %s 个、supersedes 边 %s 条；"
            "检索 %s 条共 %s 次命中；跳过 %s 个不可读项。" % (
                idx.get("stats", {}).get("indexed_files", 0),
                idx.get("stats", {}).get("unique_contents", 0),
                ing.get("dedup_hits", 0),
                ver.get("stats", {}).get("duplicate_groups", 0),
                ver.get("stats", {}).get("version_clusters", 0),
                ver.get("stats", {}).get("supersedes_edges", 0),
                sea.get("stats", {}).get("queries", 0),
                sea.get("stats", {}).get("total_hits", 0),
                idx.get("stats", {}).get("skipped_files", 0))), None
    return None, "无法将契约字段 %r 映射到已计算产物；已置 null（不编造）" % name


def build_result(input_dir, work_dir, output_dir, stage="final",
                 run_errors=None):
    case = read_json(os.path.join(input_dir, "case.json")) or {}
    library = os.path.join(output_dir, "library")
    ctx = {
        "ingest": read_json(os.path.join(work_dir, "ingest_summary.json")) or {},
        "index": read_json(os.path.join(library, "index.json")) or {},
        "versions": read_json(os.path.join(library, "versions.json")) or {},
        "search": read_json(os.path.join(library, "search_results.json")) or {},
    }
    errors = list(run_errors or [])
    for b in ctx["index"].get("broken_archives", []):
        errors.append("坏压缩包: %s (%s)" % (b.get("path"), b.get("reason")))

    if stage == "partial":
        status = "partial"
    elif errors:
        status = "complete_with_warnings"
    else:
        status = "complete"
    ctx["status"] = status

    # ---- output_contract 字段全量填充
    contract = case.get("output_contract", [])
    if isinstance(contract, dict):
        fields = list(contract.keys())
    elif isinstance(contract, list):
        fields = []
        for f in contract:
            if isinstance(f, str):
                fields.append(f)
            elif isinstance(f, dict):
                fields.append(f.get("field") or f.get("name") or str(f))
    else:
        fields = []

    uncertainty = []
    result = {"case_id": case.get("case_id", "unknown"), "status": status}
    for name in fields:
        if name in ("case_id", "status"):
            continue
        value, warn = _fill_field(name, ctx)
        result[name] = value
        if warn:
            uncertainty.append(warn)

    # ---- sources：全部输入文件 + sha256 前缀（可追溯）
    ledger = load_jsonl(os.path.join(library, "objects.jsonl"))
    result["sources"] = [
        {"path": e["path"], "sha256": (e.get("sha256") or "")[:16],
         "origin": e.get("origin", "direct"),
         "readable": bool(e.get("readable"))}
        for e in ledger if e.get("type") == "file"]

    # ---- evidence：关键证据指针（抽样，完整数据在 library/ 下）
    ver, sea = ctx["versions"], ctx["search"]
    evidence = []
    for g in ver.get("duplicate_groups", [])[:5]:
        evidence.append("精确重复(内容相同): %s → sha256=%s…"
                        % (" = ".join(g["paths"][:3]), g["sha256"][:12]))
    for e in ver.get("edges", [])[:5]:
        evidence.append("版本取代: %s… supersedes %s… (sim=%s, +%d/-%d 行)"
                        % (e["from"][:12], e["to"][:12], e["similarity"],
                           e["diff_summary"]["lines_added"],
                           e["diff_summary"]["lines_removed"]))
    for s in sea.get("searches", [])[:10]:
        evidence.append("检索 %r: %d 次命中" % (s["query"], s["hit_count"]))
    result["evidence"] = evidence

    # ---- uncertainty：不可读项、坏包、跳过项、步骤错误
    for s in ctx["index"].get("skipped", []):
        uncertainty.append("跳过(未完成): %s — %s" % (s.get("path"),
                                                      s.get("reason")))
    uncertainty.extend("步骤异常: %s" % e for e in errors[:20])
    result["uncertainty"] = uncertainty

    # ---- change_records：本次运行对数据做的全部动作流水
    ing, idx_stats = ctx["ingest"], ctx["index"].get("stats", {})
    result["change_records"] = [
        "ingest: 扫描 %s 个文件，对象库新增 %s 个对象，内容去重命中 %s 次" % (
            ing.get("files_seen", 0), ing.get("objects_stored", 0),
            ing.get("dedup_hits", 0)),
        "ingest: 压缩包 %s 个（坏包 %s 个），展开成员 %s 个；跳过 %s 项" % (
            ing.get("archives", 0), ing.get("broken_archives", 0),
            ing.get("archive_members", 0), ing.get("skipped", 0)),
        "build_index: 建立逻辑树 %s 个条目，命名冲突改名 __dupN %s 次"
        "（绝不覆盖）" % (idx_stats.get("indexed_files", 0),
                          idx_stats.get("tree_conflicts_renamed", 0)),
        "lineage: 精确重复组 %s 个，版本簇 %s 个，supersedes 边 %s 条" % (
            ver.get("stats", {}).get("duplicate_groups", 0),
            ver.get("stats", {}).get("version_clusters", 0),
            ver.get("stats", {}).get("superseded_edges",
                                     ver.get("stats", {}).get(
                                         "supersedes_edges", 0))),
        "search: 回答检索 %s 条、问题 %s 条，总命中 %s 次" % (
            sea.get("stats", {}).get("queries", 0),
            sea.get("stats", {}).get("questions", 0),
            sea.get("stats", {}).get("total_hits", 0)),
        "finalize: 写入 result.json (stage=%s)" % stage,
    ]

    result["artifacts"] = {
        "objects": "library/objects/",
        "objects_ledger": "library/objects.jsonl",
        "index": "library/index.json",
        "tree": "library/tree/",
        "versions": "library/versions.json",
        "versions_dot": "library/versions.dot",
        "search_results": "library/search_results.json",
    }
    write_json(os.path.join(output_dir, "result.json"), result)
    return status


def main():
    ap = argparse.ArgumentParser(description="生成最终 result.json")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--stage", default="final",
                    choices=["partial", "final"])
    a = ap.parse_args()
    status = build_result(a.input, a.work, a.output, stage=a.stage)
    print("finalize ok: status=%s" % status)


if __name__ == "__main__":
    main()
