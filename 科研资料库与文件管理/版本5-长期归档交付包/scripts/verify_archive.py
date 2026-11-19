#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step5 独立校验：解包 archive/*.tar.gz 到临时目录，逐文件比对 SHA256SUMS。

输出 <output>/verify_report.json：
  status: ok | mismatch | missing | extra | failed
  counts: {match, mismatch, missing, extra, unreadable}
  details: 每项差异的路径/期望/实际/原因
不谎报：任何不符都如实写入 status 与 details。
"""
import argparse
import json
import os
import shutil
import sys
import tarfile
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def parse_sums(path):
    entries = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip():
                continue
            # 格式 "<sha256>  <relpath>"（两空格分隔）
            parts = line.split("  ", 1)
            if len(parts) != 2:
                parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            entries[parts[1].strip()] = parts[0].strip()
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    input_dir = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)
    archive_dir = os.path.join(output_dir, "archive")

    case = lib.json_load(os.path.join(input_dir, "case.json"), default={}) or {}
    case_id = str(case.get("case_id", "unknown_case"))
    tar_path = os.path.join(archive_dir, "%s_archive.tar.gz" % case_id)
    sums_path = os.path.join(archive_dir, "SHA256SUMS")
    report_path = os.path.join(output_dir, "verify_report.json")

    report = {
        "case_id": case_id,
        "archive_file": os.path.basename(tar_path),
        "verified_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "status": "failed",
        "counts": {"match": 0, "mismatch": 0, "missing": 0, "extra": 0,
                   "unreadable": 0},
        "details": [],
        "method": "extract to tempdir, per-file sha256 vs SHA256SUMS",
    }

    if not os.path.isfile(tar_path):
        report["details"].append({
            "kind": "missing_archive", "path": tar_path,
            "reason": "archive tar.gz not found"})
        lib.json_dump(report, report_path)
        lib.log("verify_archive: archive 缺失")
        return 1
    if not os.path.isfile(sums_path):
        report["details"].append({
            "kind": "missing_sums", "path": sums_path,
            "reason": "SHA256SUMS not found"})
        lib.json_dump(report, report_path)
        return 1

    tmp = tempfile.mkdtemp(prefix="verify_")
    try:
        try:
            with tarfile.open(tar_path, "r:gz") as tf:
                for m in tf.getmembers():
                    target = os.path.realpath(os.path.join(tmp, m.name))
                    if not target.startswith(os.path.realpath(tmp) + os.sep):
                        report["details"].append({
                            "kind": "blocked", "path": m.name,
                            "reason": "path traversal blocked"})
                        continue
                tf.extractall(tmp)
        except (tarfile.TarError, EOFError, OSError) as e:
            report["details"].append({
                "kind": "extract_failed", "path": tar_path,
                "reason": "%s: %s" % (type(e).__name__, e)})
            lib.json_dump(report, report_path)
            return 1

        expected = parse_sums(sums_path)
        actual = {}
        for root, _dirs, files in os.walk(tmp):
            for fn in files:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, tmp).replace(os.sep, "/")
                digest, err = lib.sha256_file(full)
                if digest is None:
                    report["counts"]["unreadable"] += 1
                    report["details"].append({
                        "kind": "unreadable", "path": rel, "reason": err})
                    continue
                actual[rel] = digest

        for rel, want in expected.items():
            if rel not in actual:
                report["counts"]["missing"] += 1
                report["details"].append({
                    "kind": "missing", "path": rel,
                    "expected_sha256": want,
                    "reason": "in SHA256SUMS but not in extracted archive"})
            elif actual[rel] != want:
                report["counts"]["mismatch"] += 1
                report["details"].append({
                    "kind": "mismatch", "path": rel,
                    "expected_sha256": want, "actual_sha256": actual[rel]})
            else:
                report["counts"]["match"] += 1
        for rel in actual:
            if rel not in expected:
                report["counts"]["extra"] += 1
                report["details"].append({
                    "kind": "extra", "path": rel,
                    "reason": "in archive but not in SHA256SUMS"})
        c = report["counts"]
        if c["mismatch"] or c["missing"]:
            report["status"] = "mismatch" if c["mismatch"] else "missing"
        elif c["extra"]:
            report["status"] = "extra"
        else:
            report["status"] = "ok"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    lib.json_dump(report, report_path)
    lib.log("verify_archive: %s %s" %
            (report["status"], json.dumps(report["counts"])))
    return 0 if report["status"] == "ok" else 2


if __name__ == "__main__":
    sys.exit(main())
