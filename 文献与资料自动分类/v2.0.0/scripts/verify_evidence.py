#!/usr/bin/env python3
"""verify_evidence.py — 决策证据锚点 + 前后对照验证报告（v2.0.0 方向）。

为每条分类/命名/去重/版本决策生成可独立复核的证据锚点（规则、原文摘录、哈希），
并输出 输入快照→输出快照 的逐项对照表，使评审无需信任过程即可抽查。

用法: python3 verify_evidence.py [--work-dir /app/work] [--output-dir /app/output]
输出: /app/output/evidence_index.json, /app/output/verification.md
"""
import argparse, datetime, json, os, sys

def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()
    wd, outdir = args.work_dir, args.output_dir

    inv = load(os.path.join(wd, "inventory.json"), {}) or {}
    refs = load(os.path.join(wd, "refs.json"), {}) or {}
    plan = load(os.path.join(wd, "plan.json"), {}) or {}
    arep = load(os.path.join(wd, "apply_report.json"), {}) or {}
    result = load(os.path.join(outdir, "result.json"), {}) or {}

    # —— 决策证据锚点 ——
    entries = []
    for item in plan.get("items", []):
        rel = item["rel_path"]
        ref = refs.get(rel) or {}
        field_evidence = {}
        for k in ("title", "authors", "year", "venue", "doi", "arxiv"):
            f = ref.get(k) or {}
            if f.get("value"):
                field_evidence[k] = {
                    "value": f["value"] if not isinstance(f["value"], list) else f["value"][:3],
                    "source": f.get("source"), "confidence": f.get("confidence"),
                    "evidence_excerpt": f.get("evidence"),
                }
        entries.append({
            "file": rel,
            "sha256": item.get("sha256"),
            "action": item["action"],
            "target": item.get("target"),
            "doc_type": item.get("doc_type"),
            "classify_rule": item.get("classify_rule"),
            "version_role": item.get("version_role"),
            "version_group": item.get("version_group"),
            "decision_reason": item.get("reason"),
            "metadata_evidence": field_evidence,
        })
    with open(os.path.join(outdir, "evidence_index.json"), "w", encoding="utf-8") as f:
        json.dump({"case_id": result.get("case_id"), "entries": entries},
                  f, ensure_ascii=False, indent=2)

    # —— 前后对照 ——
    records = {r["rel_path"]: r for r in inv.get("records", [])}
    lines = [
        f"# 整理前后对照验证报告 — case {result.get('case_id')}",
        "",
        f"生成时间: {datetime.datetime.now(datetime.timezone.utc).isoformat()}",
        f"状态: {result.get('status')}；统计: {json.dumps(result.get('statistics', {}), ensure_ascii=False)}",
        "",
        "## 复核方法（无需信任本报告）",
        "",
        "1. 重跑：`bash /skills/weekly-skill/scripts/run_pipeline.sh /input /app/work /app/output`；",
        "2. 哈希核对：`sha256sum` 对比下表输入/输出哈希（复制保真）；",
        "3. 回滚：`bash /app/output/audit/rollback.sh` 后 library/ 与 _archive/ 应为空；",
        "4. 抽查证据：`evidence_index.json` 任取一条，按其 source/excerpt 对照原文。",
        "",
        "## 逐文件对照（输入 → 输出）",
        "",
        "| 输入文件 | 大小(B) | sha256(前12) | 动作 | 输出位置 | 依据 |",
        "|-|-|-|-|-|-|",
    ]
    for e in entries:
        rec = records.get(e["file"], {})
        sha = (e["sha256"] or "")[:12]
        reason = (e["decision_reason"] or "").replace("|", "/")[:60]
        lines.append(f"| {e['file']} | {rec.get('size_bytes')} | {sha} | "
                     f"{e['action']} | {e['target'] or '—'} | {reason} |")
    vgs = plan.get("version_groups", [])
    if vgs:
        lines += ["", "## 版本关系", ""]
        for g in vgs:
            lines.append(f"- 组 `{g['key']}`：canonical = {g['canonical']}；归档 = {g['archived']}"
                         + (f"（管理指令: {g['admin_override']}）" if g.get("admin_override") else ""))
    dups = plan.get("exact_duplicates", [])
    if dups:
        lines += ["", "## 精确重复", ""]
        for d in dups:
            lines.append(f"- 保留 {d['kept']}；归档 {d['archived']}")
    exc = (result.get("exceptions") or {})
    lines += ["", "## 异常与未决", ""]
    for key in ("skipped", "failed", "conflicts", "issues_from_preflight"):
        vals = exc.get(key) or []
        if vals:
            lines.append(f"- **{key}**: {json.dumps(vals, ensure_ascii=False)[:300]}")
    un = (result.get("uncertainty") or [])
    if un:
        lines.append("- **uncertainty**: " + "；".join(str(u) for u in un[:5]))

    with open(os.path.join(outdir, "verification.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[verify_evidence] entries={len(entries)} -> evidence_index.json, verification.md")
    return 0

if __name__ == "__main__":
    sys.exit(main())
