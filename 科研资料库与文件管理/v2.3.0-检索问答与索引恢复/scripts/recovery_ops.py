#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""恢复/索引操作工作流（v2.3.0 新增）。

对应案例画像中的 "actual recovery/index operations"：真实执行恢复与
索引重建，而不是只写计划。

能力：
  1) 恢复：按 文件名 / 别名(alias) / sha256 前缀 定位目标，依次从
     a. 归档包 archive/<case_id>_archive.tar.gz
     b. 账本 inventory.jsonl（source_relpath 指向 /input 原件）
     c. 压缩包登记 extracted.json + library/_extracted/ 展开结果
     d. /input 原始资料树
     恢复文件到 library/，并逐字节校验（恢复后 sha256 与来源一致）。
  2) 索引重建：重建 library/index/library_index.db
     （FTS5 bigram 模式；无 FTS5 退化 LIKE 并在 meta 表登记 degraded）。
  3) 全部操作写 <output>/recovery_log.jsonl：
     {ts, op, target, source_basis, source_path, result,
      sha256_expected, sha256_actual, verified, reason}。

CLI（独立可调）：
  python3 scripts/recovery_ops.py --output /app/output --rebuild-index
  python3 scripts/recovery_ops.py --input /input --output /app/output \
      --restore "实验记录_v1.txt" --restore "a1b2c3d4"
  python3 scripts/recovery_ops.py --input /input --output /app/output
      # 无 --restore 时读取 case.json 的 recovery/recovery_tasks/restore 任务

单任务失败记账不崩溃；无任何恢复任务时登记 noop 并正常退出。
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

HERE = os.path.dirname(os.path.abspath(__file__))
RECOVERY_KEYS = ("recovery", "recovery_tasks", "restore", "restores",
                 "recovery_ops", "index_operations")
HEX_PREFIX = re.compile(r"^[0-9a-fA-F]{8,64}$")


def now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def collect_recovery_tasks(case):
    """从 case.json 抽取恢复任务，兼容字符串与对象两种形态。

    返回 [{target, action, dest, raw}]。
    """
    tasks = []
    for key in RECOVERY_KEYS:
        v = case.get(key)
        if v is None:
            continue
        items = v if isinstance(v, (list, tuple)) else [v]
        for item in items:
            if isinstance(item, str):
                tasks.append({"target": item, "action": "restore",
                              "dest": None, "raw": item})
            elif isinstance(item, dict):
                target = (item.get("target") or item.get("file") or
                          item.get("name") or item.get("alias") or
                          item.get("path") or item.get("filename") or
                          item.get("sha256") or item.get("sha256_prefix"))
                action = str(item.get("action") or item.get("type") or
                             item.get("op") or "restore").lower()
                if not target and action in ("rebuild_index", "reindex",
                                             "rebuild", "index"):
                    target = "library_index.db"
                if target:
                    tasks.append({
                        "target": str(target), "action": action,
                        "dest": item.get("dest") or item.get("destination"),
                        "raw": item})
    return tasks


def load_aliases(case):
    """别名表：case.json aliases（dict 或 [{alias,target}]）。"""
    aliases = {}
    v = case.get("aliases") or case.get("alias_map")
    if isinstance(v, dict):
        for k, val in v.items():
            aliases[str(k)] = str(val)
    elif isinstance(v, (list, tuple)):
        for item in v:
            if isinstance(item, dict):
                a = item.get("alias") or item.get("name")
                t = item.get("target") or item.get("file") or \
                    item.get("path")
                if a and t:
                    aliases[str(a)] = str(t)
    return aliases


def norm_target(t):
    return os.path.basename(str(t).strip())


def is_sha_prefix(t):
    return bool(HEX_PREFIX.match(str(t).strip()))


def find_in_inventory(inventory_path, target, alias_names):
    """在账本里按 sha256 前缀 / 文件名 / 别名 找候选记录。"""
    cands = []
    if not os.path.isfile(inventory_path):
        return cands
    want = str(target).strip().lower()
    names = {norm_target(target).lower()}
    names |= {norm_target(a).lower() for a in alias_names}
    with open(inventory_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            sha = (rec.get("sha256") or "").lower()
            src = str(rec.get("source_relpath") or "")
            lib_rel = str(rec.get("library_relpath") or "")
            base = os.path.basename(src).lower()
            base_l = os.path.basename(lib_rel).lower()
            hit = False
            basis = None
            if is_sha_prefix(target) and sha.startswith(want):
                hit, basis = True, "sha256_prefix"
            elif base in names or base_l in names:
                hit, basis = True, "filename_or_alias"
            if hit:
                cands.append({"record": rec, "basis": basis})
    return cands


def copy_verified(src, dest, expect_sha=None):
    """逐字节复制并校验。返回 (ok, actual_sha, reason)。"""
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
    except OSError as e:
        return False, None, "copy_failed: %s" % e
    actual, err = lib.sha256_file(dest)
    if actual is None:
        return False, None, err
    if expect_sha and actual != expect_sha:
        return False, actual, "sha256_mismatch_after_copy"
    # 逐字节比对（双保险）
    try:
        with open(src, "rb") as a, open(dest, "rb") as b:
            while True:
                ba, bb = a.read(lib.CHUNK), b.read(lib.CHUNK)
                if ba != bb:
                    return False, actual, "byte_compare_mismatch"
                if not ba:
                    break
    except OSError as e:
        return False, actual, "byte_compare_failed: %s" % e
    return True, actual, None


def restore_from_tar(tar_path, target, alias_names, dest, log_rec):
    """从归档 tar.gz 中按文件名/别名恢复成员。"""
    names = {norm_target(target).lower()}
    names |= {norm_target(a).lower() for a in alias_names}
    try:
        with tarfile.open(tar_path, "r:gz") as tf:
            for m in tf.getmembers():
                if not m.isfile():
                    continue
                if os.path.basename(m.name).lower() in names:
                    f = tf.extractfile(m)
                    if f is None:
                        continue
                    data = f.read()
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as out:
                        out.write(data)
                    sha = lib.sha256_bytes(data)
                    log_rec["source_basis"] = "archive_tar_member"
                    log_rec["source_path"] = "%s!/%s" % (
                        os.path.basename(tar_path), m.name)
                    log_rec["sha256_actual"] = sha
                    return True, sha, None
    except (tarfile.TarError, EOFError, OSError) as e:
        return False, None, "tar_read_failed: %s: %s" % (type(e).__name__, e)
    return False, None, "member_not_found_in_archive"


def rebuild_index(output_dir, log_rec):
    """重建 library_index.db（调用 build_index.py，幂等）。"""
    db = os.path.join(output_dir, "library", "index", "library_index.db")
    t0 = time.time()
    try:
        p = subprocess.run(
            [sys.executable, os.path.join(HERE, "build_index.py"),
             "--output", output_dir],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=300)
        log_rec["duration_s"] = round(time.time() - t0, 3)
        log_rec["source_basis"] = "build_index.py subprocess"
        log_rec["source_path"] = os.path.relpath(db, output_dir)
        if p.returncode != 0 or not os.path.isfile(db):
            log_rec["reason"] = "build_index rc=%s: %s" % (
                p.returncode, p.stdout.decode("utf-8", "replace")[-400:])
            return False
        # 读取重建后的模式（fts5_bigram / like_fallback+degraded）
        import sqlite3
        con = sqlite3.connect(db)
        try:
            mode = con.execute(
                "SELECT v FROM meta WHERE k='mode'").fetchone()
            deg = con.execute(
                "SELECT v FROM meta WHERE k='degraded'").fetchone()
            n = con.execute(
                "SELECT v FROM meta WHERE k='indexed_files'").fetchone()
            log_rec["index_mode"] = mode[0] if mode else "unknown"
            log_rec["degraded"] = (deg[0] if deg else "unknown")
            log_rec["indexed_files"] = int(n[0]) if n else None
        finally:
            con.close()
        return True
    except Exception as e:
        log_rec["reason"] = "%s: %s" % (type(e).__name__, e)
        return False


def resolve_alias_target(target, aliases):
    """目标若为别名，返回 (真实名, 全部候选名列表)。"""
    t = str(target)
    names = [t]
    if t in aliases:
        names.append(aliases[t])
    # 反向：target 是真实名时，把所有指向它的别名也作为候选
    for a, real in aliases.items():
        if real == t and a not in names:
            names.append(a)
    return names


def resolve_dest(library, dest_rel, expect_sha):
    """冲突不覆盖：目标已存在且内容不同 -> __dupN 后缀。

    返回 (dest_full_path, conflict_renamed)。已存在同哈希副本时直接复用。
    """
    dest = os.path.join(library, dest_rel)
    if not os.path.exists(dest):
        return dest, False
    exist_sha, _e = lib.sha256_file(dest)
    if expect_sha and exist_sha == expect_sha:
        return dest, False  # 内容一致，幂等复用
    base, ext = os.path.splitext(dest)
    n = 1
    while os.path.exists("%s__dup%d%s" % (base, n, ext)):
        n += 1
    return "%s__dup%d%s" % (base, n, ext), True


def do_restore(target, dest_hint, case, aliases, input_dir, output_dir,
               log_path):
    """执行单个恢复任务，逐级尝试来源，写 recovery_log.jsonl。"""
    rec = {"ts": now(), "op": "restore", "target": target,
           "source_basis": None, "source_path": None, "result": "failed",
           "sha256_expected": None, "sha256_actual": None,
           "verified": False, "reason": None}
    names = resolve_alias_target(target, aliases)
    library = os.path.join(output_dir, "library")
    inventory = os.path.join(output_dir, "inventory.jsonl")
    inv_cands = find_in_inventory(inventory, target, names)
    # 同哈希多副本时优先非备份名（.bak/副本/backup 排后）
    bak_pat = re.compile(r"(\.bak\b|副本|备份|backup|~$)", re.IGNORECASE)
    inv_cands.sort(key=lambda c: bool(bak_pat.search(os.path.basename(
        str(c["record"].get("source_relpath") or "")))))
    # sha256 前缀定位时，以来源记录的真实文件名命名恢复目标
    dest_name = norm_target(names[-1])
    if is_sha_prefix(target) and inv_cands:
        dest_name = os.path.basename(str(
            inv_cands[0]["record"].get("source_relpath") or dest_name))
    dest_rel = dest_hint or os.path.join("_restored", dest_name)
    expect_sha = None
    for c in inv_cands:
        r = c["record"]
        if r.get("sha256"):
            expect_sha = r["sha256"]
            rec["sha256_expected"] = expect_sha
            break
    dest, renamed = resolve_dest(library, dest_rel, expect_sha)
    if renamed:
        rec["conflict"] = "dest_existed_different_content_renamed___dupN"
    rec["dest"] = os.path.relpath(dest, output_dir).replace(os.sep, "/")

    # 来源 b：账本 -> input 原件 或 library 内既有副本
    for c in inv_cands:
        r = c["record"]
        for cand_path, basis in (
                (os.path.join(input_dir, str(r.get("source_relpath") or "")),
                 "inventory:input_original"),
                (os.path.join(library, str(r.get("library_relpath") or "")),
                 "inventory:library_copy")):
            if not cand_path or not os.path.isfile(cand_path):
                continue
            ok, actual, err = copy_verified(
                cand_path, dest, expect_sha if is_sha_prefix(target) or
                expect_sha else None)
            if ok:
                rec.update(source_basis=basis, source_path=cand_path,
                           result="ok", verified=True,
                           sha256_actual=actual)
                lib.jsonl_append(log_path, rec)
                return rec
            rec["reason"] = err

    # 来源 a：归档包
    case_id = str(case.get("case_id", "unknown_case"))
    tar_path = os.path.join(output_dir, "archive",
                            "%s_archive.tar.gz" % case_id)
    if os.path.isfile(tar_path):
        ok, sha, err = restore_from_tar(tar_path, target, names, dest, rec)
        if ok:
            if expect_sha and sha != expect_sha:
                rec.update(result="failed", verified=False,
                           reason="sha256_mismatch_vs_inventory")
            else:
                rec.update(result="ok", verified=True)
            lib.jsonl_append(log_path, rec)
            return rec
        rec["reason"] = err

    # 来源 c：压缩包登记 extracted.json + _extracted/
    ext_log = lib.json_load(os.path.join(output_dir, "extracted.json"),
                            default={}) or {}
    low_names = {n.lower() for n in
                 [norm_target(x) for x in names]}
    for a in ext_log.get("archives", []):
        if a.get("status") != "ok":
            continue
        for f in a.get("files", []):
            if os.path.basename(f).lower() in low_names:
                src = os.path.join(library, "_extracted",
                                   a.get("archive", ""), f)
                if os.path.isfile(src):
                    ok, actual, err = copy_verified(src, dest, expect_sha)
                    if ok:
                        rec.update(source_basis="extracted_archive_member",
                                   source_path=src, result="ok",
                                   verified=True, sha256_actual=actual)
                        lib.jsonl_append(log_path, rec)
                        return rec
                    rec["reason"] = err

    # 来源 d：/input 原始树按名/别名/sha256 前缀扫描
    for root, _dirs, files in os.walk(input_dir):
        for fn in files:
            full = os.path.join(root, fn)
            matched = fn.lower() in low_names
            basis = "input_tree:filename_or_alias"
            if not matched and is_sha_prefix(target):
                sha, _e = lib.sha256_file(full)
                if sha and sha.startswith(str(target).strip().lower()):
                    matched = True
                    basis = "input_tree:sha256_prefix"
                    expect_sha = expect_sha or sha
                    rec["sha256_expected"] = expect_sha
            if matched:
                ok, actual, err = copy_verified(full, dest, expect_sha)
                if ok:
                    rec.update(source_basis=basis, source_path=full,
                               result="ok", verified=True,
                               sha256_actual=actual)
                    lib.jsonl_append(log_path, rec)
                    return rec
                rec["reason"] = err

    if rec["reason"] is None:
        rec["reason"] = "target_not_found_in_any_source"
    lib.jsonl_append(log_path, rec)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default=None,
                    help="含 case.json 的输入目录（恢复任务来源）")
    ap.add_argument("--output", required=True)
    ap.add_argument("--restore", action="append", default=[],
                    help="恢复目标（文件名/别名/sha256 前缀），可多次")
    ap.add_argument("--rebuild-index", action="store_true",
                    help="重建 library_index.db（FTS5 bigram，"
                         "无 FTS5 退化 LIKE 并登记）")
    args = ap.parse_args()
    output_dir = os.path.abspath(args.output)
    input_dir = os.path.abspath(args.input) if args.input else None
    os.makedirs(output_dir, exist_ok=True)
    log_path = os.path.join(output_dir, "recovery_log.jsonl")

    case = {}
    aliases = {}
    tasks = []
    if input_dir:
        case = lib.json_load(os.path.join(input_dir, "case.json"),
                             default={}) or {}
        aliases = load_aliases(case)
        tasks = collect_recovery_tasks(case)
    for t in args.restore:
        tasks.append({"target": t, "action": "restore", "dest": None,
                      "raw": t})

    n_ok = n_fail = 0
    did_restore = False
    if not tasks and not args.rebuild_index:
        lib.jsonl_append(log_path, {
            "ts": now(), "op": "noop",
            "target": None, "source_basis": None, "source_path": None,
            "result": "ok", "verified": False,
            "reason": "case.json 无 recovery 任务且未指定 "
                      "--restore/--rebuild-index"})

    need_index_rebuild = args.rebuild_index
    for t in tasks:
        action = t["action"]
        if action in ("rebuild_index", "reindex", "rebuild", "index",
                      "index_rebuild"):
            need_index_rebuild = True
            continue
        if input_dir is None:
            lib.jsonl_append(log_path, {
                "ts": now(), "op": "restore", "target": t["target"],
                "result": "failed", "verified": False,
                "reason": "no --input given, cannot resolve sources"})
            n_fail += 1
            continue
        r = do_restore(t["target"], t.get("dest"), case, aliases,
                       input_dir, output_dir, log_path)
        did_restore = True
        if r["result"] == "ok":
            n_ok += 1
        else:
            n_fail += 1
    # 恢复过文件就联动重建索引，保证恢复内容立即可检索
    if did_restore and n_ok > 0:
        need_index_rebuild = True

    if need_index_rebuild:
        rec = {"ts": now(), "op": "rebuild_index",
               "target": "library/index/library_index.db",
               "source_basis": None, "source_path": None,
               "result": "failed", "verified": False, "reason": None}
        ok = rebuild_index(output_dir, rec)
        rec["result"] = "ok" if ok else "failed"
        rec["verified"] = ok
        lib.jsonl_append(log_path, rec)
        n_ok += 1 if ok else 0
        n_fail += 0 if ok else 1

    lib.log("recovery_ops: ok=%d failed=%d log=%s" %
            (n_ok, n_fail, log_path))
    return 0 if n_fail == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
