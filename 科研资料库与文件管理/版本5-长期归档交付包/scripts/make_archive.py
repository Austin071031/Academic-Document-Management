#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""step4 打包：library/ -> archive/<case_id>_archive.tar.gz + 三件套。

产出（archive/ 四件套）：
  <case_id>_archive.tar.gz  归档包（library/ 全量，UTF-8 名安全）
  SHA256SUMS                逐文件哈希清单（相对 library/ 根）
  MANIFEST.json             归档清单（路径/大小/sha256/来源/权限/retention/access_level）
  HANDOFF_README.md         交接说明（内容清单/校验方法/恢复步骤/期限与权限）
"""
import argparse
import os
import stat
import sys
import tarfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def build_sha256sums(library, out_path, errors):
    lines = []
    for root, _dirs, files in os.walk(library):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, library).replace(os.sep, "/")
            digest, err = lib.sha256_file(full)
            if digest is None:
                errors.append({"path": rel, "reason": err})
                continue
            lines.append("%s  %s" % (digest, rel))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines else ""))
    return lines


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True)
    args = ap.parse_args()
    input_dir = os.path.abspath(args.input)
    output_dir = os.path.abspath(args.output)
    library = os.path.join(output_dir, "library")
    archive_dir = os.path.join(output_dir, "archive")
    os.makedirs(archive_dir, exist_ok=True)

    case = lib.json_load(os.path.join(input_dir, "case.json"), default={}) or {}
    case_id = str(case.get("case_id", "unknown_case"))
    task_text = lib.read_text(os.path.join(input_dir, "task.md")) or ""
    policy = lib.extract_policy(case, task_text)
    manifest_in = lib.json_load(os.path.join(output_dir, "manifest.json"),
                                default={}) or {}

    tar_path = os.path.join(archive_dir, "%s_archive.tar.gz" % case_id)
    # tar 打包 library 下所有文件（不含 index/*.db 的瞬态锁？保留，保证可独立校验）
    n_members = 0
    pack_errors = []
    try:
        with tarfile.open(tar_path, "w:gz") as tf:
            for root, dirs, files in os.walk(library):
                dirs.sort()
                for fn in sorted(files):
                    full = os.path.join(root, fn)
                    rel = os.path.relpath(full, library).replace(os.sep, "/")
                    try:
                        ti = tf.gettarinfo(full, arcname=rel)
                        ti.uid = ti.gid = 0
                        ti.uname = ti.gname = ""
                        with open(full, "rb") as f:
                            tf.addfile(ti, f)
                        n_members += 1
                    except OSError as e:
                        pack_errors.append({"path": rel, "reason": str(e)})
    except OSError as e:
        lib.log("make_archive: tar 创建失败: %s" % e)
        lib.json_dump({"status": "failed", "reason": str(e)},
                      os.path.join(archive_dir, "archive_build_error.json"))
        return 1

    sums_path = os.path.join(archive_dir, "SHA256SUMS")
    hash_errors = []
    hash_lines = build_sha256sums(library, sums_path, hash_errors)

    # MANIFEST.json
    files_meta = []
    for root, _dirs, files in os.walk(library):
        for fn in sorted(files):
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, library).replace(os.sep, "/")
            st = None
            try:
                st = os.stat(full)
            except OSError:
                pass
            digest, _e = lib.sha256_file(full)
            source = None
            for m in (manifest_in.get("files") or []):
                if m.get("path") == rel:
                    prov = {p["field"]: p for p in m.get("provenance", [])}
                    source = {
                        "original_relpath": rel,
                        "provenance": m.get("provenance", [])}
                    break
            files_meta.append({
                "path": rel,
                "size": st.st_size if st else None,
                "sha256": digest,
                "mode": oct(st.st_mode & 0o777) if st else None,
                "source": source,
                "retention": policy["retention"]["value"],
                "retention_source": policy["retention"]["source"],
                "access_level": policy["access_level"]["value"],
                "access_level_source": policy["access_level"]["source"],
            })
    manifest = {
        "case_id": case_id,
        "archive_format": "tar.gz",
        "archive_file": os.path.basename(tar_path),
        "created_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file_count": len(files_meta),
        "member_count": n_members,
        "retention": policy["retention"],
        "access_level": policy["access_level"],
        "pack_errors": pack_errors + hash_errors,
        "files": files_meta,
    }
    lib.json_dump(manifest, os.path.join(archive_dir, "MANIFEST.json"))

    # HANDOFF_README.md
    total_size = sum(m["size"] or 0 for m in files_meta)
    readme = """# HANDOFF README — 归档交接说明

## 归档标识
- case_id: {case_id}
- 归档包: {archive_file}
- 打包时间(UTC): {created_utc}
- 文件数: {file_count}（tar 成员 {member_count}），总大小 {total_size} 字节

## 内容清单
本归档包含 library/ 全量内容，按 项目/年份/类型 层级组织：
- 数据与文本、代码、文档、图片等按扩展名归入 type 层；
- _extracted/ 为压缩包展开结果（见 extracted.json 登记）；
- index/ 为 sqlite3 检索库（可整包迁移，query_index.py 可独立查询）。

## 校验方法
在含归档的目录执行（需 coreutils）：
```
sha256sum -c SHA256SUMS
```
或交由 scripts/verify_archive.py 独立校验（解包到临时目录逐文件比对，
输出 verify_report.json，含 match/mismatch/missing/extra 统计）。

## 恢复步骤
```
mkdir -p restore && tar -xzf {archive_file} -C restore
# 恢复后 library/ 树与 SHA256SUMS 清单应逐文件一致
```

## 保存期限与权限范围
- 保存期限(retention): {retention}
  - 出处: {retention_src}
- 密级/权限(access_level): {access_level}
  - 出处: {access_src}
- 以上若显示 unspecified，表示输入 case.json/task.md 未给出，
  由接收方按制度补齐，不得据此推断。

## 备注
- 打包期错误（若有）: {pack_errors}
- 逐文件元数据见 MANIFEST.json；账本见 output/inventory.jsonl。
""".format(
        case_id=case_id,
        archive_file=os.path.basename(tar_path),
        created_utc=manifest["created_utc"],
        file_count=len(files_meta),
        member_count=n_members,
        total_size=total_size,
        retention=policy["retention"]["value"],
        retention_src=policy["retention"]["source"] or "unspecified",
        access_level=policy["access_level"]["value"],
        access_src=policy["access_level"]["source"] or "unspecified",
        pack_errors=json.dumps(pack_errors + hash_errors, ensure_ascii=False)
        if (pack_errors or hash_errors) else "无",
    )
    with open(os.path.join(archive_dir, "HANDOFF_README.md"), "w",
              encoding="utf-8") as f:
        f.write(readme)

    lib.log("make_archive: members=%d files=%d tar=%s" %
            (n_members, len(files_meta), tar_path))
    return 0


if __name__ == "__main__":
    sys.exit(main())
