#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply.py — 按计划落地到 /app/output/library/，写 journal.jsonl（可回滚）。

* 复制（绝不移动/删除源文件），目标冲突追加 __dupN，绝不覆盖。
* 空目录移入 quarantine（带 journal 反向记录）。
* 单文件失败不崩溃：登记 failed 并继续。
"""
import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_engine as re_eng  # noqa: E402


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def main():
    ap = argparse.ArgumentParser(description='把 plan.json 落地到输出目录')
    ap.add_argument('--input', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    with open(os.path.join(args.work, 'plan.json'), encoding='utf-8') as f:
        plan = json.load(f)
    with open(os.path.join(args.work, 'duplicates.json'), encoding='utf-8') as f:
        duplicates = json.load(f)
    with open(os.path.join(args.work, 'versions.json'), encoding='utf-8') as f:
        versions = json.load(f)

    lib_root = os.path.join(args.output, 'library')
    quarantine_root = os.path.join(args.output, 'quarantine')
    os.makedirs(lib_root, exist_ok=True)
    os.makedirs(args.work, exist_ok=True)
    journal_path = os.path.join(args.work, 'journal.jsonl')

    used = set()
    applied, failed = [], []
    with open(journal_path, 'w', encoding='utf-8') as j:
        def log(rec):
            j.write(json.dumps(rec, ensure_ascii=False) + '\n')

        log({'ts': utcnow(), 'op': 'begin_apply',
             'entries': len(plan['entries'])})

        for e in plan['entries']:
            src = os.path.join(args.input, e['source'])
            dst = os.path.join(args.output, e['target'])
            try:
                dst_final = dst
                if dst_final in used or os.path.exists(dst_final):
                    dst_final = os.path.join(
                        args.output,
                        re_eng.unique_path(e['target'], used))
                used.add(dst_final)
                os.makedirs(os.path.dirname(dst_final), exist_ok=True)
                shutil.copy2(src, dst_final)
                got = os.path.getsize(dst_final)
                if e['size'] is not None and got != e['size']:
                    raise IOError('size mismatch after copy: %d != %d' % (got, e['size']))
                rec = {'ts': utcnow(), 'op': 'copy', 'src': e['source'],
                       'dst': os.path.relpath(dst_final, args.output),
                       'bytes': got, 'sha256': e['sha256'], 'rule_id': e['rule_id'],
                       'reverse': {'op': 'remove', 'path': os.path.relpath(dst_final, args.output)}}
                log(rec)
                applied.append(rec)
            except OSError as ex:
                rec = {'ts': utcnow(), 'op': 'copy_failed', 'src': e['source'],
                       'dst': e['target'], 'error': '%s: %s' % (type(ex).__name__, ex)}
                log(rec)
                failed.append(rec)

        # 空目录：移入 quarantine（显式处理，可回滚）
        quarantined = []
        for d in plan.get('empty_dirs', []):
            if d in ('.', ''):
                continue
            src = os.path.join(args.input, d)
            dst = os.path.join(quarantine_root, d)
            try:
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                shutil.move(src, dst)
                rec = {'ts': utcnow(), 'op': 'quarantine_empty_dir', 'src': d,
                       'dst': os.path.relpath(dst, args.output),
                       'reverse': {'op': 'move_back', 'from': os.path.relpath(dst, args.output), 'to': d}}
                log(rec)
                quarantined.append(d)
            except OSError as ex:
                rec = {'ts': utcnow(), 'op': 'quarantine_failed', 'src': d,
                       'error': '%s: %s' % (type(ex).__name__, ex)}
                log(rec)
                failed.append(rec)

        # 跳过项（不可读等）显式登记
        for s in plan.get('skipped', []):
            log({'ts': utcnow(), 'op': 'skip', 'path': s['path'], 'reason': s['reason']})

        log({'ts': utcnow(), 'op': 'end_apply', 'applied': len(applied),
             'failed': len(failed), 'quarantined': len(quarantined)})

    # 工作区留档
    for name, obj in (('duplicates.json', duplicates), ('versions.json', versions)):
        with open(os.path.join(args.work, name), 'w', encoding='utf-8') as f:
            json.dump(obj, f, ensure_ascii=False, indent=2)

    print('[apply] applied=%d failed=%d quarantined=%d journal=%s' % (
        len(applied), len(failed), len(quarantined), journal_path))
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
