#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step7 recover/qa：恢复操作 + 索引重建 + 检索结果同步。

1) **恢复**：按 case.json 中的恢复请求（键 recovery / recover /
   recovery_tasks，条目为文件名字符串或
   {"file"/"filename"/"name"/"path"/"sha256"/"sha", "target"/"dest"} 字典），
   从内容寻址对象库 objects/ 中按 **sha256 前缀** 或 **文件名** 定位唯一对象，
   恢复（复制）到 library/tree/recovered/ 并**重新哈希校验**，
   全程记账到 library/recovery_log.jsonl（JSONL，一行一条）。
   冲突追加 __dupN，绝不覆盖；恢复出的文件同步登记进 index.json，
   保证 verify_cas.py 复核仍然一致。

2) **索引重建**：把恢复产生的新条目并入 index.json 并重算 stats
   （index.json 损坏/缺失时回退到 build_index 全量重建）；
   检索索引每次重建（search.py 运行时在内存中重建倒排索引）。

3) **检索结果同步**：若 case.json 含 searches/questions，调用基座
   search.run_search 重建检索索引，并把带 文件+行号+片段 证据的结果
   同步写到 <output>/search_results.json（顶层，便于评审查阅）。

单条恢复失败记账不崩溃；无任何恢复请求时仍执行索引重建与检索同步，
并在 recovery_log.jsonl 留下事件记录。
"""
import argparse
import os
import re
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cas_common import (append_jsonl, ensure_dir, is_probably_text, norm,
                        read_json, sha256_file, write_json)

SHA_RE = re.compile(r"^[0-9a-fA-F]{6,64}$")


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def extract_recovery_requests(case):
    """从 case.json 提取恢复请求，兼容 str / dict 条目。"""
    raw = []
    for key in ("recovery", "recover", "recovery_tasks"):
        v = case.get(key)
        if isinstance(v, list):
            raw.extend(v)
        elif v:
            raw.append(v)
    reqs = []
    for item in raw:
        if isinstance(item, str):
            reqs.append({"query": item, "target": None})
        elif isinstance(item, dict):
            q = None
            for k in ("sha256", "sha", "content_id", "file", "filename",
                      "name", "path", "target_file"):
                if isinstance(item.get(k), str) and item[k]:
                    q = item[k]
                    break
            tgt = item.get("target") or item.get("dest") \
                or item.get("restore_to")
            if q:
                reqs.append({"query": q,
                             "target": tgt if isinstance(tgt, str) else None})
    return reqs


def resolve_object(query, objects_dir, index):
    """按 sha256 前缀或文件名定位对象。
    返回 (content_id, object_path, matched_paths, reason)。"""
    q = norm(str(query)).strip()
    if SHA_RE.match(q):  # sha256 前缀（≥6 位十六进制）
        ql = q.lower()
        hits = []
        if os.path.isdir(objects_dir):
            for sub in sorted(os.listdir(objects_dir)):
                subdir = os.path.join(objects_dir, sub)
                if not os.path.isdir(subdir):
                    continue
                for name in sorted(os.listdir(subdir)):
                    if name.startswith(ql):
                        hits.append((name, os.path.join(subdir, name)))
        if len(hits) == 1:
            return hits[0][0], hits[0][1], [], None
        if not hits:
            return None, None, [], "对象库中无 sha256 前缀 %r 匹配" % q
        return None, None, [], ("sha256 前缀 %r 不唯一（%d 个匹配），"
                                "请提供更长的前缀" % (q, len(hits)))
    # 文件名匹配：比对 index 中 source_path / logical_path 的 basename
    base_q = os.path.basename(q)
    cands = {}
    for e in index.get("files", []):
        names = {os.path.basename(e.get("source_path") or ""),
                 os.path.basename(e.get("logical_path") or "")}
        if q in names or base_q in names:
            cands.setdefault(e["content_id"], set()).add(
                e.get("source_path") or "?")
    if len(cands) == 1:
        cid = next(iter(cands))
        obj = os.path.join(objects_dir, cid[:2], cid)
        if os.path.exists(obj):
            return cid, obj, sorted(cands[cid]), None
        return None, None, sorted(cands[cid]), "index 有登记但对象库缺失对象"
    if not cands:
        return None, None, [], "资料库中未找到文件名 %r" % q
    flat = sorted(p for ps in cands.values() for p in ps)
    return None, None, flat, ("文件名 %r 对应 %d 个不同内容（版本不同），"
                              "请改用 sha256 前缀指定" % (q, len(cands)))


def _dest_path(tree_root, target, query, used):
    """计算恢复目标路径（限定在 tree/recovered/ 内，冲突 __dupN）。"""
    name = norm(os.path.basename(target or query)) or "recovered.bin"
    rel = os.path.join("recovered", name)
    n = 1
    while rel in used or os.path.exists(os.path.join(tree_root, rel)):
        stem, ext = os.path.splitext(os.path.join("recovered", name))
        rel = "%s__dup%d%s" % (stem, n, ext)
        n += 1
    used.add(rel)
    return rel


def run_recovery(input_dir, work_dir, output_dir):
    """执行恢复 + 索引重建 + 检索同步。返回统计 dict。"""
    import build_index
    import search as search_mod

    library = ensure_dir(os.path.join(output_dir, "library"))
    objects_dir = os.path.join(library, "objects")
    tree_root = ensure_dir(os.path.join(library, "tree"))
    log_path = os.path.join(library, "recovery_log.jsonl")
    if os.path.exists(log_path):
        os.remove(log_path)
    case = read_json(os.path.join(input_dir, "case.json")) or {}
    index = read_json(os.path.join(library, "index.json"))

    stats = {"requests": 0, "restored": 0, "failed": 0,
             "index_rebuilt": False, "search_synced": False, "errors": []}

    if index is None:  # index.json 缺失/损坏 → 全量重建（含 tree checkout）
        append_jsonl(log_path, {"ts": _now(), "event": "rebuild_index",
                                "reason": "index.json 缺失或损坏，"
                                          "调用 build_index 全量重建"})
        try:
            build_index.build_index(input_dir, work_dir, output_dir)
            index = read_json(os.path.join(library, "index.json")) or {}
            stats["index_rebuilt"] = True
        except Exception as e:
            stats["errors"].append("全量重建索引失败: %s: %s"
                                   % (type(e).__name__, e))
            index = {"files": [], "stats": {}}

    # ---- 恢复请求
    used = {e.get("tree_path", "")[len("tree/"):] for e in index.get("files", [])
            if e.get("tree_path")}
    for req in extract_recovery_requests(case):
        stats["requests"] += 1
        rec = {"ts": _now(), "event": "restore", "request": req["query"]}
        cid, obj, matched, reason = resolve_object(
            req["query"], objects_dir, index)
        if cid is None:
            rec.update(status="failed", reason=reason, candidates=matched[:10])
            stats["failed"] += 1
            stats["errors"].append("%s: %s" % (req["query"], reason))
        else:
            rel = _dest_path(tree_root, req["target"], req["query"], used)
            dst = os.path.join(tree_root, rel)
            ensure_dir(os.path.dirname(dst))
            try:
                shutil.copyfile(obj, dst)
                os.chmod(dst, 0o644)
                digest = sha256_file(dst)  # 恢复后重新哈希校验
                if digest != cid:
                    raise ValueError("恢复后哈希不符: %s != %s"
                                     % (digest[:12], cid[:12]))
                st = os.stat(dst)
                rec.update(status="ok", content_id=cid,
                           object="objects/%s/%s" % (cid[:2], cid),
                           dest="tree/" + rel.replace(os.sep, "/"),
                           size=st.st_size, hash_verified=True)
                stats["restored"] += 1
                # 登记进 index.json：保证 verify_cas 复核一致
                base = os.path.basename(rel)
                index.setdefault("files", []).append({
                    "logical_path": ("recovered/" + base).replace(os.sep, "/"),
                    "tree_path": "tree/" + rel.replace(os.sep, "/"),
                    "content_id": cid,
                    "source_path": "recovered:%s" % req["query"],
                    "size": st.st_size, "mtime": st.st_mtime,
                    "permissions": "0o644", "origin": "recovery",
                    "category": build_index.categorize(base),
                    "is_text": is_probably_text(dst),
                    "metadata": build_index.parse_filename(base),
                    "notes": [], "recovered": True,
                })
                stats["index_rebuilt"] = True
            except (OSError, ValueError) as e:
                rec.update(status="failed",
                           reason="写入/校验失败: %s: %s"
                                  % (type(e).__name__, e))
                stats["failed"] += 1
                stats["errors"].append("%s: %s" % (req["query"], rec["reason"]))
        append_jsonl(log_path, rec)

    # ---- 索引重建（增量并入后重算 stats 并落盘）
    try:
        files = index.get("files", [])
        index["stats"] = dict(index.get("stats") or {}, **{
            "indexed_files": len(files),
            "unique_contents": len({x["content_id"] for x in files}),
            "recovered_files": sum(1 for x in files if x.get("recovered")),
        })
        write_json(os.path.join(library, "index.json"), index)
        append_jsonl(log_path, {"ts": _now(), "event": "rebuild_index",
                                "status": "ok", "indexed_files": len(files)})
    except Exception as e:
        stats["errors"].append("索引重建失败: %s: %s" % (type(e).__name__, e))

    # ---- 检索索引重建 + 结果同步到 <output>/search_results.json
    searches = case.get("searches") or []
    questions = case.get("questions") or []
    if searches or questions:
        try:
            search_mod.run_search(input_dir, work_dir, output_dir)
            src = os.path.join(library, "search_results.json")
            dst = os.path.join(output_dir, "search_results.json")
            shutil.copyfile(src, dst)
            stats["search_synced"] = True
            append_jsonl(log_path, {"ts": _now(), "event": "search_sync",
                                    "status": "ok",
                                    "dest": "search_results.json"})
        except Exception as e:
            stats["errors"].append("检索同步失败: %s: %s"
                                   % (type(e).__name__, e))
    else:
        append_jsonl(log_path, {"ts": _now(), "event": "search_sync",
                                "status": "skipped",
                                "reason": "case.json 无 searches/questions"})

    stats["errors"] = stats["errors"][:50]
    write_json(os.path.join(work_dir, "recover_summary.json"), stats)
    return stats


def main():
    ap = argparse.ArgumentParser(description="恢复 + 索引重建 + 检索同步")
    ap.add_argument("--input", default="/input")
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--output", default="/app/output")
    a = ap.parse_args()
    s = run_recovery(a.input, a.work, a.output)
    print("recover ok: requests=%(requests)d restored=%(restored)d "
          "failed=%(failed)d search_synced=%(search_synced)s" % s)


if __name__ == "__main__":
    main()
