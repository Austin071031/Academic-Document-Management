#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recover.py —— 文件恢复 + 索引重建（v2.2.0 新增）。

恢复操作：读取 /input/case.json 的 recovery / recover / recovery_requests
（条目可为文件名字符串，或 {"filename"/"file"/"name":…} / {"sha256":…} 字典）：
  1. 在扫描账本 work/files.jsonl 中按文件名（归一化主干匹配）或 sha256 找候选
     ——账本覆盖原始输入与 zip/tar 压缩包登记并展开的成员（work/extracted/ 下）；
  2. 恢复（复制）到 <output>/library/recovered/<原名>，重名不覆盖、加 __N；
  3. 恢复后重算 sha256 与账本/请求期望哈希比对校验；
  4. 全程写 recovery_log.jsonl（work 累积 + output 镜像），
     action ∈ restored / already_present / not_found / verify_failed / error；
     单条失败记账不崩溃，幂等（同哈希目标已存在则 already_present 不重复复制）。

索引重建：--rebuild-index 或实际发生恢复时，
  - 重跑 build_manifest.py 重建 manifest（含新恢复文件？不——manifest 基于
    输入扫描账本，恢复文件属派生物，因此重建 manifest 是幂等重放，
    保证任何前序中断后 manifest 与账本一致）；
  - 重跑 qa_cite.py --index-only 重建 work/search_index.json 检索索引
    （library/ 下含 recovered/ 目录，新恢复文件即刻可被检索问答命中）。
"""
import argparse
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def extract_requests(case):
    """从 case.json 提取恢复请求清单，兼容多种形状。"""
    raw = (case.get("recovery") or case.get("recover")
           or case.get("recovery_requests") or [])
    if isinstance(raw, (str, dict)):
        raw = [raw]
    if isinstance(raw, dict):  # {"files": [...]} 等
        raw = raw.get("files") or raw.get("items") or []
    requests = []
    if not isinstance(raw, list):
        return requests
    for i, it in enumerate(raw):
        req = {"id": "recovery-%d" % (i + 1), "filename": None, "sha256": None}
        if isinstance(it, str):
            req["filename"] = it.strip()
        elif isinstance(it, dict):
            for k in ("filename", "file", "name", "path", "target"):
                if it.get(k):
                    req["filename"] = str(it[k]).strip()
                    break
            if it.get("sha256") or it.get("hash"):
                req["sha256"] = str(it.get("sha256") or it.get("hash")).strip().lower()
            if it.get("id"):
                req["id"] = str(it["id"])
        if req["filename"] or req["sha256"]:
            requests.append(req)
    return requests


def find_candidates(req, ledger):
    """按 sha256 优先、文件名归一化匹配其次，在扫描账本中找恢复源。"""
    matches = []
    if req["sha256"]:
        matches = [r for r in ledger
                   if r.get("readable") and (r.get("sha256") or "").lower() == req["sha256"]]
    if not matches and req["filename"]:
        key = lc.norm_key(os.path.basename(req["filename"]))
        matches = [r for r in ledger
                   if r.get("readable") and lc.norm_key(r.get("basename", "")) == key]
        if not matches:  # 归一化相对路径兜底
            rkey = lc.norm_key(req["filename"])
            matches = [r for r in ledger
                       if r.get("readable") and lc.norm_key(r.get("relpath", "")) == rkey]
    # 确定性排序：优先非压缩包来源，再按路径最短
    matches.sort(key=lambda r: (str(r.get("origin", "")).startswith(("zip:", "tar:")),
                                len(r.get("relpath", "")), r.get("relpath", "")))
    return matches


def unique_dest(dest_dir, basename, expected_sha):
    """重名不覆盖：同哈希→幂等复用；不同哈希→__N 后缀。"""
    dest = os.path.join(dest_dir, basename)
    if not os.path.exists(dest):
        return dest, None
    if expected_sha and os.path.isfile(dest) and lc.sha256_file(dest) == expected_sha:
        return dest, "same"
    stem, ext = os.path.splitext(basename)
    n = 2
    while True:
        cand = os.path.join(dest_dir, "%s__%d%s" % (stem, n, ext))
        if not os.path.exists(cand):
            return cand, None
        if expected_sha and lc.sha256_file(cand) == expected_sha:
            return cand, "same"
        n += 1


def do_recover(requests, ledger, output, work):
    dest_dir = os.path.join(output, "library", "recovered")
    log_records, n_restored = [], 0
    for req in requests:
        rec = {"ts": lc.now_iso(), "request": req, "action": None}
        try:
            matches = find_candidates(req, ledger)
            if not matches:
                rec.update(action="not_found",
                           reason="扫描账本（含压缩包登记成员）中无匹配文件，无法恢复")
                log_records.append(rec)
                continue
            src_rec = matches[0]
            src = src_rec.get("abspath")
            if not src or not os.path.exists(src):
                rec.update(action="error", matched_source=src_rec.get("relpath"),
                           reason="账本记录的源路径不存在: %s" % src)
                log_records.append(rec)
                continue
            expected = (req["sha256"] or src_rec.get("sha256") or "").lower() or None
            os.makedirs(dest_dir, exist_ok=True)
            dest, state = unique_dest(dest_dir, os.path.basename(src), expected)
            if state == "same":
                rec.update(action="already_present", matched_source=src_rec["relpath"],
                           dest=os.path.relpath(dest, output),
                           sha256_expected=expected,
                           sha256_actual=expected,
                           reason="目标已存在且哈希一致（幂等，不重复复制）")
                log_records.append(rec)
                continue
            shutil.copy2(src, dest)
            actual = lc.sha256_file(dest)
            rec.update(matched_source=src_rec["relpath"],
                       dest=os.path.relpath(dest, output),
                       sha256_expected=expected, sha256_actual=actual)
            if expected and actual != expected:
                rec.update(action="verify_failed",
                           reason="恢复后 sha256 与期望不符，文件已保留待人工核对")
            else:
                rec.update(action="restored",
                           reason="sha256 校验一致" if expected
                           else "账本无期望哈希可比对，仅按文件名恢复")
                n_restored += 1
        except Exception as e:  # 单条失败记账不崩溃
            rec.update(action="error", reason="%s: %s" % (type(e).__name__, e))
        log_records.append(rec)
    # 幂等：每次运行以本轮记录整体重写 work 日志（请求集不变则结果可复现）
    wpath = os.path.join(work, "recovery_log.jsonl")
    if os.path.exists(wpath):
        os.remove(wpath)
    lc.jappend(wpath, log_records)
    all_logs = log_records
    lc.jwrite(os.path.join(output, "recovery_log.json"), {
        "generated_at": lc.now_iso(),
        "source_of_truth": "work/files.jsonl 扫描账本（含 zip/tar 登记展开成员）",
        "n_requests": len(requests),
        "n_restored_this_run": n_restored,
        "records": all_logs,
    })
    # 同步 jsonl 镜像便于机读
    with open(os.path.join(output, "recovery_log.jsonl"), "w", encoding="utf-8") as f:
        for r in all_logs:
            f.write(lc.json.dumps(r, ensure_ascii=False) + "\n")
    return log_records, n_restored


def run_rebuild(script, extra_args, base_args, work):
    cmd = [sys.executable, os.path.join(HERE, script)] + base_args + extra_args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        if p.returncode != 0:
            lc.log_change(work, "recover_rebuild", script, "subprocess",
                          "exit=%d" % p.returncode, note=(p.stderr or "")[-300:])
        return p.returncode
    except Exception as e:
        lc.log_change(work, "recover_rebuild", script, "subprocess", "crash: %s" % e)
        return -1


def main():
    ap = argparse.ArgumentParser(description="文件恢复 + 索引重建（v2.2.0）")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", required=True)
    ap.add_argument("--rebuild-index", action="store_true",
                    help="只重建 manifest 与检索索引，不处理恢复请求")
    a = ap.parse_args()

    case = lc.jread(os.path.join(a.input, "case.json"), default={}) or {}
    requests = [] if a.rebuild_index else extract_requests(case)
    ledger = list(lc.jlines(os.path.join(a.work, "files.jsonl")) or [])

    logs, n_restored = [], 0
    if requests:
        logs, n_restored = do_recover(requests, ledger, a.output, a.work)
    elif not a.rebuild_index:
        # 无恢复请求也落一个空日志，保证产物存在且诚实
        if not os.path.exists(os.path.join(a.output, "recovery_log.json")):
            lc.jwrite(os.path.join(a.output, "recovery_log.json"), {
                "generated_at": lc.now_iso(),
                "n_requests": 0, "n_restored_this_run": 0, "records": [],
                "note": "case.json 未提供 recovery 请求"})

    base_args = ["--input", a.input, "--work", a.work,
                 "--output", a.output, "--config", a.config]
    rcs = {}
    # 索引重建：manifest 幂等重放 + 检索索引重建（恢复后必须，显式请求亦然）
    if requests or a.rebuild_index:
        rcs["build_manifest.py"] = run_rebuild("build_manifest.py", [], base_args, a.work)
        # case 有检索问答时重跑完整 qa_cite（恢复的文件即刻进入答案），否则只重建索引
        if case.get("searches") or case.get("questions"):
            rcs["qa_cite.py"] = run_rebuild("qa_cite.py", [], base_args, a.work)
        else:
            rcs["qa_cite.py --index-only"] = run_rebuild(
                "qa_cite.py", ["--index-only"], base_args, a.work)

    n_fail = sum(1 for r in logs if r.get("action") in ("not_found", "verify_failed", "error"))
    lc.log_change(a.work, "recover", "library/recovered",
                  "case.json recovery requests + files.jsonl ledger",
                  "%d requests, %d restored, %d failed; rebuild rc=%s"
                  % (len(requests), n_restored, n_fail, rcs or "skipped"))
    print("[recover] requests=%d restored=%d failed=%d rebuild=%s"
          % (len(requests), n_restored, n_fail, rcs or "skipped"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
