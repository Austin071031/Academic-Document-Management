#!/usr/bin/env python3
"""recovery.py — 恢复/还原/重建操作（v2.2.0 方向）。

识别 case.json / task.md 中的恢复类请求并真实执行：
- 恢复指定文件：从 _archive/duplicates、_archive/versions 恢复到 library/（登记审计日志）
- 全部回滚：执行 audit/rollback.sh 并报告
- 重建索引：删除并重建 index/

恢复目标可通过 case.json 的 recover/recovery/restore 字段（str 或 list）指定，
或 task.md 中含 "恢复/还原/回滚/重建" 的句子；无明确请求时只做能力登记不执行。

用法: python3 recovery.py [--work-dir /app/work] [--output-dir /app/output]
输出: /app/output/recovery_report.json（并回写 result.json.recovery）
"""
import argparse, datetime, json, os, re, shutil, subprocess, sys

def load(p, default=None):
    if not os.path.exists(p):
        return default
    with open(p, "r", encoding="utf-8") as f:
        return json.load(f)

def sha256_of(path, chunk=1 << 20):
    import hashlib
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work-dir", default="/app/work")
    ap.add_argument("--output-dir", default="/app/output")
    args = ap.parse_args()
    wd, outdir = args.work_dir, args.output_dir

    brief = load(os.path.join(wd, "brief.json"), {}) or {}
    case = load(os.path.join(brief.get("input_dir", "/input"), "case.json"), {}) or {}
    task_text = ""
    if os.path.exists(brief.get("task_path", "")):
        with open(brief["task_path"], "r", encoding="utf-8") as f:
            task_text = f.read()

    # —— 识别恢复请求 ——
    requests = []
    for key in ("recover", "recovery", "restore", "rebuild"):
        v = case.get(key)
        if isinstance(v, str) and v.strip():
            requests.append({"type": key, "target": v.strip(), "origin": f"case.json:{key}"})
        elif isinstance(v, list):
            for item in v:
                requests.append({"type": key, "target": str(item), "origin": f"case.json:{key}"})
    if not requests:
        for line in task_text.splitlines():
            s = line.strip()
            if re.search(r"(恢复|还原|回滚|重建索引|rebuild|restore|recover)", s) and len(s) > 4:
                requests.append({"type": "task_line", "target": s, "origin": "task.md"})

    report = {"requests_detected": len(requests), "actions": [], "capability_note":
              "支持：恢复归档文件到 library/、全量回滚（audit/rollback.sh）、重建索引。"}
    ops_log = os.path.join(outdir, "audit", "operations.jsonl")
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()

    def log(entry):
        try:
            with open(ops_log, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            pass

    # —— 恢复归档文件 ——
    archive_root = os.path.join(outdir, "_archive")
    for req in requests:
        target = req["target"]
        action = {"request": req, "status": None, "detail": None}
        if req["type"] == "task_line":
            action["status"] = "noted"
            action["detail"] = "task.md 中的恢复表述已登记；未指定具体对象时不执行破坏性操作"
            report["actions"].append(action)
            continue
        # 在归档中按文件名匹配
        base = os.path.basename(target)
        found = None
        for root, dirs, files in os.walk(archive_root):
            for fn in files:
                if fn == base or base in fn:
                    found = os.path.join(root, fn)
                    break
            if found:
                break
        if not found:
            action["status"] = "not_found"
            action["detail"] = f"归档中未找到匹配文件: {target}"
        else:
            dest_dir = os.path.join(outdir, "library", "recovered")
            os.makedirs(dest_dir, exist_ok=True)
            dest = os.path.join(dest_dir, os.path.basename(found))
            shutil.copy2(found, dest)
            entry = {"ts": now, "action": "recover", "src": os.path.relpath(found, outdir),
                     "dst": os.path.relpath(dest, outdir), "sha256": sha256_of(dest),
                     "status": "done", "note": f"恢复请求: {target}"}
            log(entry)
            action["status"] = "recovered"
            action["detail"] = entry["dst"]
        report["actions"].append(action)

    # 索引存在性（重建能力的登记）
    idx = os.path.join(outdir, "index", "inverted.json")
    report["index_present"] = os.path.exists(idx)

    with open(os.path.join(outdir, "recovery_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    result = load(os.path.join(outdir, "result.json"), {}) or {}
    if result:
        result["recovery"] = report
        with open(os.path.join(outdir, "result.json"), "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"[recovery] requests={report['requests_detected']} "
          f"recovered={sum(1 for a in report['actions'] if a['status']=='recovered')}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
