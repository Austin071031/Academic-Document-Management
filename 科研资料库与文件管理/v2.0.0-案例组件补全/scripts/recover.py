#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
recover.py — 恢复 / 重建索引操作组件（版本2 新增）。

恢复：给定目标（文件名 / sha256 前缀 / 别名），依次从以下来源定位并
把文件恢复到 <output>/library/ 指定位置：
  1. 内容寻址账本：work/inventory.jsonl 的同 sha256 组（含改名副本/别名）；
  2. 压缩包展开登记：scan 阶段安全展开到 work/extracted/ 的 archive_member；
  3. 源目录备份：输入目录中仍然存在的原始文件。
每次恢复写 <output>/recovery_log.jsonl（来源、依据、恢复路径、sha256 校验），
append-only；目标已存在且同哈希记 already_present，绝不覆盖，冲突用 __dupN。

重建索引：--target rebuild-index（或 --rebuild-index）重建 manifest（调
library_pipeline.py report）、检索索引（调 qa.py --index-only）并重跑 verify，
全部写入 recovery_log.jsonl。

CLI：
  python3 scripts/recover.py --input /input --work /app/work --output /app/output \
      --target "关键词或sha256前缀" [--restore-to "项目/年份/类型/文件名"]
  python3 scripts/recover.py --input ... --work ... --output ... --from-case
  python3 scripts/recover.py --work ... --output ... --rebuild-index

仅用 Python 标准库。单条任务失败只记录、不中断（失败记账不崩溃）。
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from datetime import datetime, timezone

CHUNK = 1024 * 1024
REBUILD_ALIASES = {"rebuild-index", "rebuild_index", "rebuild index",
                   "rebuild", "重建索引", "重建"}
CASE_RECOVERY_KEYS = ("recovery", "recover", "recovery_tasks", "restore", "restore_tasks")
HEX_RE = re.compile(r"^[0-9a-fA-F]{6,64}$")


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def safe_print(*args):
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    try:
        print(*args)
    except Exception as exc:
        print("[print-error]", exc)


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            chunk = fh.read(CHUNK)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def nfc(s):
    return unicodedata.normalize("NFC", str(s))


def sanitize(name, max_len=120):
    name = nfc(name)
    name = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", name)
    name = name.strip().strip(".")
    return (name or "unnamed")[:max_len]


def load_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def load_inventory(work_dir, output_dir):
    """优先 work 账本，缺失时退回 output 审计副本。"""
    for cand in (os.path.join(work_dir, "inventory.jsonl"),
                 os.path.join(output_dir, "inventory.jsonl")):
        entries = load_jsonl(cand)
        if entries:
            return entries, cand
    return [], None


def load_plan(work_dir):
    path = os.path.join(work_dir, "plan.json")
    if os.path.exists(path):
        try:
            return json.load(open(path, encoding="utf-8"))
        except Exception:
            return {}
    return {}


class RecoveryLogger:
    def __init__(self, output_dir):
        self.path = os.path.join(output_dir, "recovery_log.jsonl")
        self.count = {"recovered": 0, "already_present": 0,
                      "not_found": 0, "failed": 0, "rebuilt": 0}

    def log(self, **rec):
        rec.setdefault("time", utcnow())
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
        status = rec.get("status")
        if status in self.count:
            self.count[status] += 1
        safe_print("[recover] %s target=%r -> %s"
                   % (status, rec.get("target"), rec.get("restored_to") or rec.get("detail")))


def find_candidates(entries, target):
    """按 sha256 前缀 → 文件名精确 → 路径子串 的优先级返回匹配账本条目。"""
    t = nfc(target).strip()
    tlow = t.lower()
    if HEX_RE.match(t):
        m = [e for e in entries if (e.get("sha256") or "").lower().startswith(tlow)]
        if m:
            return m, "sha256 prefix match"
    exact = [e for e in entries
             if os.path.basename(nfc(e.get("path") or "")).lower() == tlow]
    if exact:
        return exact, "exact basename match"
    sub = [e for e in entries
           if tlow in os.path.basename(nfc(e.get("path") or "")).lower()
           or tlow in nfc(e.get("path") or "").lower()]
    if sub:
        return sub, "substring match on path"
    # 别名回退：duplicates.json 的 canonical/aliases 中按名字命中 → 取同哈希组
    return [], None


def alias_group_candidates(output_dir, entries, target):
    """目标名只在 duplicates.json 里作为别名出现时，用同哈希组兜底。"""
    dup_path = os.path.join(output_dir, "duplicates.json")
    if not os.path.exists(dup_path):
        return [], None
    try:
        dups = json.load(open(dup_path, encoding="utf-8"))
    except Exception:
        return [], None
    tlow = nfc(target).strip().lower()
    for g in dups.get("groups", []):
        names = [g.get("canonical") or ""] + list(g.get("aliases") or [])
        if any(tlow in os.path.basename(nfc(n)).lower() for n in names):
            sha = g.get("sha256")
            group = [e for e in entries if e.get("sha256") == sha]
            if group:
                return group, "content-addressed alias group (sha256 %s…)" % (sha or "")[:12]
    return [], None


def resolve_source(candidates):
    """按 源目录备份 → 压缩包展开 → 内容寻址同哈希组 的顺序找一个可读来源。"""
    readable = [e for e in candidates if e.get("readable") and e.get("sha256")]
    for e in readable:
        abs_path = e.get("abs_path")
        if e.get("kind") in ("file", "archive") and abs_path and os.path.exists(abs_path):
            return abs_path, "source_backup", e
    for e in readable:
        abs_path = e.get("abs_path")
        if e.get("kind") == "archive_member" and abs_path and os.path.exists(abs_path):
            return abs_path, "archive_extraction", e
    for e in readable:  # 同哈希组任意现存成员（内容寻址账本）
        abs_path = e.get("abs_path")
        if abs_path and os.path.exists(abs_path):
            return abs_path, "content_addressed_ledger", e
    return None, None, None


def plan_target_for(plan_doc, entry_path):
    for p in plan_doc.get("entries", []):
        if p.get("src") == entry_path and p.get("action") == "copy" and p.get("target"):
            return p["target"]
    return None


def unique_dest(lib_root, rel_target, expected_sha):
    """冲突消解：同名同哈希 -> already_present；同名异哈希 -> __dupN，绝不覆盖。"""
    dest = os.path.join(lib_root, rel_target)
    if not os.path.exists(dest):
        return rel_target, None
    try:
        if expected_sha and sha256_file(dest) == expected_sha:
            return rel_target, "already_present"
    except Exception:
        pass
    stem, ext = os.path.splitext(rel_target)
    n = 1
    while True:
        cand = "%s__dup%d%s" % (stem, n, ext)
        if not os.path.exists(os.path.join(lib_root, cand)):
            return cand, None
        n += 1


def do_recover(work_dir, output_dir, target, restore_to, logger):
    plan_doc = load_plan(work_dir)
    entries, ledger_path = load_inventory(work_dir, output_dir)
    base_rec = {"action": "recover", "target": target}
    if not entries:
        logger.log(**dict(base_rec, status="failed",
                          detail="inventory.jsonl 缺失或为空，无法定位来源"))
        return False

    candidates, basis = find_candidates(entries, target)
    if not candidates:
        candidates, basis = alias_group_candidates(output_dir, entries, target)
    if not candidates:
        logger.log(**dict(base_rec, status="not_found",
                          detail="账本/压缩包登记/别名组中均无 %r 的匹配" % target))
        return False

    src_abs, source_kind, src_entry = resolve_source(candidates)
    if src_abs is None:
        logger.log(**dict(base_rec, status="not_found", basis=basis,
                          matched=[c.get("path") for c in candidates][:10],
                          detail="账本有登记但所有来源副本当前均不可读/不存在"))
        return False

    expected_sha = src_entry.get("sha256")
    lib_root = os.path.join(output_dir, "library")
    os.makedirs(lib_root, exist_ok=True)
    if restore_to:
        rel_target = sanitize_path(restore_to)
    else:
        rel_target = plan_target_for(plan_doc, src_entry.get("path")) \
            or "recovered/%s" % sanitize(os.path.basename(src_abs))
    rel_target, note = unique_dest(lib_root, rel_target, expected_sha)
    dest = os.path.join(lib_root, rel_target)
    rec = dict(base_rec, basis=basis, source=src_abs, source_kind=source_kind,
               matched_entry=src_entry.get("path"), restored_to="library/" + rel_target,
               sha256_expected=expected_sha)
    if note == "already_present":
        rec["status"] = "already_present"
        rec["detail"] = "目标位置已存在同哈希文件，未覆盖"
        rec["sha256_actual"] = expected_sha
        logger.log(**rec)
        return True
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(src_abs, dest)
        actual = sha256_file(dest)
        rec["sha256_actual"] = actual
        if expected_sha and actual != expected_sha:
            rec["status"] = "failed"
            rec["detail"] = "恢复后 sha256 与账本不符"
            logger.log(**rec)
            return False
        rec["status"] = "recovered"
        rec["detail"] = "sha256 校验一致"
        logger.log(**rec)
        return True
    except Exception as exc:
        rec["status"] = "failed"
        rec["detail"] = "%s: %s" % (type(exc).__name__, exc)
        logger.log(**rec)
        return False


def sanitize_path(rel):
    """把 restore_to 规范为 library/ 内的安全相对路径（防穿越）。"""
    rel = nfc(rel).replace("\\", "/")
    parts = [sanitize(p) for p in rel.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." for p in rel.split("/")):
        return "recovered/" + sanitize(os.path.basename(rel) or "restored")
    return "/".join(parts)


def do_rebuild_index(args, logger):
    """重建 manifest 与检索索引，并重跑 verify；每步记账、失败不崩溃。"""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    steps = [
        ("rebuild_manifest", os.path.join(script_dir, "library_pipeline.py"),
         ["report", "--input", args.input, "--work", args.work, "--output", args.output]),
        ("rebuild_search_index", os.path.join(script_dir, "qa.py"),
         ["--input", args.input, "--work", args.work, "--output", args.output, "--index-only"]),
        ("verify_after_rebuild", os.path.join(script_dir, "library_pipeline.py"),
         ["verify", "--input", args.input, "--work", args.work, "--output", args.output]),
    ]
    ok_all = True
    for name, script, extra in steps:
        rec = {"action": "rebuild_index", "step": name, "target": "rebuild-index"}
        if not os.path.exists(script):
            logger.log(**dict(rec, status="failed", detail="script missing: %s" % script))
            ok_all = False
            continue
        try:
            r = subprocess.run([sys.executable, script] + extra, check=False)
            if r.returncode == 0:
                logger.log(**dict(rec, status="rebuilt",
                                  detail="%s 完成（returncode=0）" % name))
            else:
                logger.log(**dict(rec, status="failed",
                                  detail="%s returncode=%d" % (name, r.returncode)))
                ok_all = False
        except Exception as exc:
            logger.log(**dict(rec, status="failed",
                              detail="%s: %s" % (type(exc).__name__, exc)))
            ok_all = False
    return ok_all


def collect_recovery_tasks(case):
    """从 case.json 收集恢复任务，兼容 str 或 dict 条目。"""
    tasks = []
    for key in CASE_RECOVERY_KEYS:
        val = case.get(key)
        if not val:
            continue
        if isinstance(val, (str, dict)):
            val = [val]
        for item in val:
            if isinstance(item, str) and item.strip():
                tasks.append({"target": item.strip(), "restore_to": None})
            elif isinstance(item, dict):
                target = item.get("target") or item.get("file") or item.get("name") \
                    or item.get("filename") or item.get("sha256") or item.get("alias") \
                    or item.get("query")
                restore_to = item.get("restore_to") or item.get("destination") \
                    or item.get("dest") or item.get("restore_path")
                if target and str(target).strip():
                    tasks.append({"target": str(target).strip(),
                                  "restore_to": str(restore_to).strip() if restore_to else None})
    return tasks


def main(argv=None):
    ap = argparse.ArgumentParser(description="恢复 / 重建索引操作（内容寻址账本 + 压缩包登记 + 源备份）")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    ap.add_argument("--target", default=None, help="文件名 / sha256 前缀 / 别名，或 rebuild-index")
    ap.add_argument("--restore-to", default=None, help="library/ 内的目标相对路径")
    ap.add_argument("--from-case", action="store_true", help="从 case.json 读取全部恢复任务")
    ap.add_argument("--rebuild-index", action="store_true", help="重建 manifest 与检索索引")
    args = ap.parse_args(argv)

    args.work = os.path.abspath(args.work)
    args.output = os.path.abspath(args.output)
    os.makedirs(args.output, exist_ok=True)
    logger = RecoveryLogger(args.output)
    ok = True

    if args.rebuild_index or (args.target and args.target.strip().lower() in REBUILD_ALIASES):
        ok = do_rebuild_index(args, logger) and ok

    targets = []
    if args.target and args.target.strip().lower() not in REBUILD_ALIASES:
        targets.append({"target": args.target.strip(), "restore_to": args.restore_to})
    if args.from_case:
        case_path = os.path.join(os.path.abspath(args.input), "case.json")
        if os.path.exists(case_path):
            try:
                case = json.load(open(case_path, encoding="utf-8"))
                targets.extend(collect_recovery_tasks(case))
            except Exception as exc:
                logger.log(action="recover", target="--from-case", status="failed",
                           detail="case.json unreadable: %s" % exc)
                ok = False
        else:
            logger.log(action="recover", target="--from-case", status="not_found",
                       detail="case.json 不存在，无恢复任务")

    for task in targets:
        t = task["target"]
        if t.strip().lower() in REBUILD_ALIASES:
            ok = do_rebuild_index(args, logger) and ok
            continue
        try:
            ok = do_recover(args.work, args.output, t, task.get("restore_to"), logger) and ok
        except Exception as exc:  # 最后防线：单任务失败不中断
            logger.log(action="recover", target=t, status="failed",
                       detail="%s: %s" % (type(exc).__name__, exc))
            ok = False

    if not targets and not args.rebuild_index:
        safe_print("[recover] nothing to do (no --target/--from-case/--rebuild-index)")
    safe_print("[recover] summary: %s log=%s" % (logger.count, logger.path))
    return 0 if ok else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        safe_print("[recover][FATAL] %s: %s" % (type(exc).__name__, exc))
        sys.exit(2)
