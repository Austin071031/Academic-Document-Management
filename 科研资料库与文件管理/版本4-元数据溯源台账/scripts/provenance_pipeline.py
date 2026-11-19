#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""provenance_pipeline.py —— 元数据溯源台账管线（版本4）编排器。

用法：
    python3 scripts/provenance_pipeline.py --input /input --work /app/work --output /app/output

步骤：
  step0  finalize --partial（尽早写出 partial result.json）
  step1  合并评测题目指定必需字段（/input/case.json 的 required_fields）→ work/field_dictionary.json
  step2a 扫描 /input：流式哈希、无权限登记 readable=false、空目录登记、zip/tar 展开登记
  step2b 依次以子进程运行各阶段脚本（单阶段失败不拖垮整体）：
         extract_from_filename → extract_from_content → join_companion
         → parse_admin_notes → adjudicate → build_manifest
  step4  finalize --final
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ledger_common as lc  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CONFIG = os.path.normpath(os.path.join(HERE, "..", "config", "field_dictionary.json"))

STEPS = [
    "extract_from_filename.py",
    "extract_from_content.py",
    "join_companion.py",
    "parse_admin_notes.py",
    "adjudicate.py",
    "build_manifest.py",
]

ARCHIVE_EXTS = {"zip", "tar", "gz", "tgz", "bz2", "xz"}
MAX_EXTRACT = 2000          # 单个压缩包最多展开条目数
MAX_MEMBER_BYTES = 200 * 1024 * 1024  # 单条目上限，防解压炸弹


def _safe_member(name):
    n = name.replace("\\", "/")
    if n.startswith("/") or ".." in n.split("/"):
        return None
    return n


def expand_archive(rec, input_root, extract_dir, next_index):
    """展开 zip/tar（stdlib），坏包登记不崩溃。返回 (新文件记录列表, 事件)。"""
    ap = os.path.join(input_root, rec["relpath"])
    new_records = []
    event = {"archive": rec["relpath"], "status": "ok", "members": 0, "errors": []}
    try:
        if rec["ext"] == "zip" or zipfile.is_zipfile(ap):
            with zipfile.ZipFile(ap) as zf:
                infos = zf.infolist()[:MAX_EXTRACT]
                for info in infos:
                    safe = _safe_member(info.filename)
                    if safe is None or info.is_dir():
                        continue
                    if info.file_size > MAX_MEMBER_BYTES:
                        event["errors"].append("skip oversized member: %s" % info.filename)
                        continue
                    try:
                        data = zf.read(info)
                    except Exception as e:  # 单条目坏不拖垮整包
                        event["errors"].append("member %s: %s" % (info.filename, e))
                        continue
                    dest = os.path.join(extract_dir, "%04d" % next_index, safe)
                    next_index += 1
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        f.write(data)
                    new_records.append(_record_for(dest, rec, "zip:%s" % rec["relpath"]))
                    event["members"] += 1
        elif tarfile.is_tarfile(ap):
            with tarfile.open(ap) as tf:
                count = 0
                for m in tf:
                    if count >= MAX_EXTRACT:
                        break
                    safe = _safe_member(m.name)
                    if safe is None or not m.isfile() or m.size > MAX_MEMBER_BYTES:
                        continue
                    src = tf.extractfile(m)
                    if src is None:
                        continue
                    dest = os.path.join(extract_dir, "%04d" % next_index, safe)
                    next_index += 1
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as f:
                        shutil.copyfileobj(src, f, 256 * 1024)
                    new_records.append(_record_for(dest, rec, "tar:%s" % rec["relpath"]))
                    count += 1
                    event["members"] += 1
        else:
            event["status"] = "unreadable"
            event["errors"].append("not a recognized zip/tar archive (bad or unsupported)")
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as e:
        event["status"] = "unreadable"
        event["errors"].append("%s: %s" % (type(e).__name__, e))
    return new_records, event, next_index


def _record_for(path, parent_rec, origin):
    name = os.path.basename(path)
    rec = {
        "relpath": "%s::%s" % (parent_rec["relpath"], name),
        "abspath": path,
        "basename": name,
        "stem": lc.stem_of(name),
        "ext": os.path.splitext(name)[1].lower().lstrip("."),
        "readable": True,
        "errors": [],
        "origin": origin,
    }
    try:
        st = os.stat(path)
        rec["size"] = st.st_size
        rec["mtime"] = st.st_mtime
        rec["sha256"] = lc.sha256_file(path)
    except Exception as e:
        rec["readable"] = False
        rec["errors"].append("extracted record: %s" % e)
    return rec


def scan(input_root, work):
    """遍历输入目录：哈希、无权限登记、空目录登记、压缩包展开登记。"""
    files, empty_dirs, walk_errors, archive_events = [], [], [], []
    extract_dir = os.path.join(work, "extracted")
    next_index = 0

    def onerror(e):
        walk_errors.append({"path": getattr(e, "filename", None), "error": str(e)})

    for dirpath, dirnames, filenames in os.walk(input_root, onerror=onerror):
        rel_dir = os.path.relpath(dirpath, input_root)
        if not filenames and not dirnames:
            empty_dirs.append(rel_dir)
        for name in filenames:
            ap = os.path.join(dirpath, name)
            rel = os.path.relpath(ap, input_root)
            rec = {
                "relpath": rel, "abspath": ap, "basename": name,
                "stem": lc.stem_of(name),
                "ext": os.path.splitext(name)[1].lower().lstrip("."),
                "readable": True, "errors": [], "origin": "input",
            }
            if rel_dir == "." and name.lower() in ("case.json", "task.md"):
                rec["origin"] = "harness"  # 评测壳文件：扫描留痕但不组织进 library
            try:
                st = os.stat(ap)
                rec["size"] = st.st_size
                rec["mtime"] = st.st_mtime
            except OSError as e:
                rec.update(readable=False, size=None, mtime=None)
                rec["errors"].append("stat failed: %s" % e)
                files.append(rec)
                continue
            if os.path.islink(ap):
                rec["errors"].append("symlink: hashed target content")
            try:
                rec["sha256"] = lc.sha256_file(ap)
            except PermissionError:
                rec["readable"] = False
                rec["errors"].append("read failed: PermissionError (无权限)")
                files.append(rec)
                continue
            except OSError as e:
                rec["readable"] = False
                rec["errors"].append("read failed: %s" % e)
                files.append(rec)
                continue
            files.append(rec)
            if rec["ext"] in ARCHIVE_EXTS:
                new_recs, event, next_index = expand_archive(rec, input_root, extract_dir, next_index)
                archive_events.append(event)
                if event["status"] != "ok":
                    rec["errors"].append("archive unreadable: %s" % "; ".join(event["errors"]))
                files.extend(new_recs)

    lc.jappend(os.path.join(work, "files.jsonl"), files)
    summary = {
        "input_root": input_root,
        "files_total": len(files),
        "files_readable": sum(1 for r in files if r["readable"]),
        "files_unreadable": sum(1 for r in files if not r["readable"]),
        "empty_dirs": empty_dirs,
        "walk_errors": walk_errors,
        "archives": archive_events,
        "scanned_at": lc.now_iso(),
    }
    lc.jwrite(os.path.join(work, "scan_summary.json"), summary)
    lc.log_change(work, "scan", input_root,
                  "os.walk + streaming sha256 + stdlib zip/tar expand",
                  "%d files (%d unreadable), %d empty dirs, %d archives"
                  % (summary["files_total"], summary["files_unreadable"],
                     len(empty_dirs), len(archive_events)))
    return summary


def merge_required_fields(input_root, work, config_path):
    """step1：评测题目若指定必需字段清单，合并进字典 required=true 后写入 work 副本。"""
    dictionary = lc.jread(config_path, default={}) or {}
    case = lc.jread(os.path.join(input_root, "case.json"), default={}) or {}
    required = case.get("required_fields") or []
    if isinstance(required, str):
        required = [x.strip() for x in required.split(",") if x.strip()]
    if required:
        fields = dictionary.setdefault("fields", {})
        for f in required:
            if f in fields:
                fields[f]["required"] = True
            else:
                fields[f] = {
                    "definition": "由评测题目 case.json 指定的必需字段",
                    "legal_sources": lc.SOURCE_PRIORITY,
                    "format": "非空字符串",
                    "required": True,
                    "example": "",
                }
        lc.log_change(work, "merge_required_fields", "field_dictionary",
                      "case.json required_fields", ",".join(required))
    lc.jwrite(os.path.join(work, "field_dictionary.json"), dictionary)
    return dictionary


def run_step(script, args, work):
    """以子进程运行单阶段脚本；失败记录但不中断管线。"""
    cmd = [sys.executable, os.path.join(HERE, script)] + args
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    except Exception as e:
        lc.log_change(work, "run_step", script, "subprocess", "crash: %s" % e)
        return {"script": script, "returncode": -1, "stderr": str(e)}
    out_tail = (p.stdout or "")[-2000:]
    err_tail = (p.stderr or "")[-2000:]
    if p.returncode != 0:
        lc.log_change(work, "run_step", script, "subprocess",
                      "exit=%d" % p.returncode, note=err_tail[-500:])
    return {"script": script, "returncode": p.returncode,
            "stdout_tail": out_tail, "stderr_tail": err_tail}


def main():
    ap = argparse.ArgumentParser(description="元数据溯源台账管线（版本4）")
    ap.add_argument("--input", required=True)
    ap.add_argument("--work", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--config", default=DEFAULT_CONFIG)
    a = ap.parse_args()

    os.makedirs(a.work, exist_ok=True)
    os.makedirs(a.output, exist_ok=True)
    step_args = ["--input", a.input, "--work", a.work, "--output", a.output,
                 "--config", a.config]

    # step0：尽早写 partial result.json
    run_step("finalize.py", step_args + ["--partial"], a.work)

    # step1：合并必需字段清单
    merge_required_fields(a.input, a.work, a.config)

    # step2a：扫描
    scan(a.input, a.work)

    # step2b：各抽取/裁决/组织阶段
    step_results = []
    for script in STEPS:
        step_results.append(run_step(script, step_args, a.work))

    # 先落盘阶段结果，供 finalize --final 判定 status
    lc.jwrite(os.path.join(a.work, "pipeline_steps.json"),
              {"steps": step_results,
               "all_ok": all(r["returncode"] == 0 for r in step_results),
               "finished_at": lc.now_iso()})

    # step4：最终化
    fin = run_step("finalize.py", step_args + ["--final"], a.work)
    step_results.append(fin)
    lc.jwrite(os.path.join(a.work, "pipeline_steps.json"),
              {"steps": step_results,
               "all_ok": all(r["returncode"] == 0 for r in step_results),
               "finished_at": lc.now_iso()})
    ok = all(r["returncode"] == 0 for r in step_results)
    print("[pipeline] finished, all_ok=%s" % ok)
    for r in step_results:
        print("  - %s rc=%s" % (r["script"], r["returncode"]))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
