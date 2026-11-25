#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""finalize.py — 生成 /app/output/result.json。

包含：case_id、output_contract 要求字段、诚实的 status / sources /
uncertainty / change_records。apply 前先以 --partial 写最小可用结果，
任何时刻 /app/output/result.json 都存在且自洽。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

WORK_FILES = ('plan.json', 'audit.json', 'duplicates.json', 'versions.json')


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def contract_field_names(case):
    """兼容 output_contract 的多种形态：list / dict.required / dict.fields。"""
    oc = (case or {}).get('output_contract')
    if isinstance(oc, list):
        return [str(x) for x in oc]
    if isinstance(oc, dict):
        for k in ('required_fields', 'required', 'fields'):
            if isinstance(oc.get(k), list):
                return [str(x) for x in oc[k]]
        # dict 形态：键即字段名
        return list(oc.keys())
    return []


def build_result(case_id, case, work, output, partial=False):
    plan = read_json(os.path.join(work, 'plan.json')) or {}
    audit = read_json(os.path.join(work, 'audit.json')) or {}
    duplicates = read_json(os.path.join(work, 'duplicates.json')) or {}
    versions = read_json(os.path.join(work, 'versions.json')) or {}

    journal_path = os.path.join(work, 'journal.jsonl')
    journal = []
    if os.path.exists(journal_path):
        with open(journal_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        journal.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass

    change_records = [
        {'op': j['op'], 'src': j.get('src') or j.get('path'),
         'dst': j.get('dst'), 'reverse': j.get('reverse')}
        for j in journal if j.get('op') in ('copy', 'quarantine_empty_dir', 'copy_failed', 'skip')
    ]

    counts = plan.get('counts', {})
    sources = [
        {'source': 'input_filesystem', 'evidence': plan.get('input_dir'),
         'used_for': 'inventory, hashing, metadata extraction'},
        {'source': 'sidecar_tables_and_notes',
         'used_for': 'metadata fields with per-field provenance'},
        {'source': 'config/layout_template.json',
         'evidence': 'rules_version %s' % plan.get('rules_version'),
         'used_for': 'routing and naming decisions'},
    ]
    if case:
        sources.append({'source': 'case.json',
                        'evidence': 'case_id=%s' % case_id,
                        'used_for': 'output_contract compliance'})

    uncertainty = []
    for s in plan.get('skipped', []):
        uncertainty.append('skipped %s: %s' % (s['path'], s['reason']))
    for a in plan.get('archives', []):
        if a.get('error'):
            uncertainty.append('archive %s not expanded: %s' % (a['path'], a['error']))
    for m in audit.get('mismatches', []):
        uncertainty.append('hash mismatch at %s' % m['target'])
    for m in audit.get('missing', []):
        uncertainty.append('missing output file %s' % m)

    failed_ops = [j for j in journal if j.get('op', '').endswith('failed')]
    if failed_ops:
        uncertainty.append('%d operation(s) failed, see journal.jsonl' % len(failed_ops))

    if partial:
        status = 'partial'
    elif audit:
        status = 'complete' if audit.get('all_match') and not journal_failed(journal) \
            else 'complete_with_warnings'
    else:
        status = 'partial'

    result = {
        'case_id': case_id,
        'status': status,
        'generated_at': utcnow(),
        'skill': 'research-library-rule-engine-v3',
        'library_dir': os.path.join(output, 'library'),
        'quarantine_dir': os.path.join(output, 'quarantine'),
        'counts': counts,
        'duplicates': {
            'file': os.path.join(work, 'duplicates.json'),
            'groups': len(duplicates.get('groups', [])),
        },
        'versions': {
            'file': os.path.join(work, 'versions.json'),
            'groups': len(versions.get('groups', [])),
        },
        'artifacts': {
            'plan': os.path.join(work, 'plan.json'),
            'audit': os.path.join(work, 'audit.json'),
            'journal': journal_path,
            'duplicates': os.path.join(work, 'duplicates.json'),
            'versions': os.path.join(work, 'versions.json'),
        },
        'rule_coverage': audit.get('rule_coverage', plan.get('rule_coverage', {})),
        'sources': sources,
        'uncertainty': uncertainty,
        'change_records': change_records,
    }

    # output_contract 字段：能推导的如实填，不能的置 null 并记录 uncertainty
    known = {
        'case_id': case_id,
        'status': status,
        'library_dir': result['library_dir'],
        'library': result['library_dir'],
        'duplicates': result['duplicates'],
        'versions': result['versions'],
        'plan_file': result['artifacts']['plan'],
        'audit_file': result['artifacts']['audit'],
        'journal_file': journal_path,
        'rule_coverage': result['rule_coverage'],
        'change_records': change_records,
        'sources': sources,
        'uncertainty': uncertainty,
        'counts': counts,
    }
    for field in contract_field_names(case):
        if field in result:
            continue
        if field in known:
            result[field] = known[field]
        else:
            result[field] = None
            uncertainty.append('contract field %r not derivable from artifacts; set to null' % field)

    if not uncertainty:
        uncertainty.append('none: all files hashed and verified')
    return result


def journal_failed(journal):
    return any(j.get('op', '').endswith('failed') for j in journal)


def main():
    ap = argparse.ArgumentParser(description='写 result.json')
    ap.add_argument('--case', default=None)
    ap.add_argument('--work', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--partial', action='store_true', help='apply 前写最小可用结果')
    args = ap.parse_args()

    case = read_json(args.case) if args.case and os.path.exists(args.case) else {}
    case_id = (case or {}).get('case_id')
    result = build_result(case_id, case, args.work, args.output, partial=args.partial)

    os.makedirs(args.output, exist_ok=True)
    out = os.path.join(args.output, 'result.json')
    tmp = out + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out)  # 原子写，中途失败不留半截文件
    print('[finalize] %s result.json (status=%s, changes=%d, uncertainty=%d)' % (
        'partial' if args.partial else 'final', result['status'],
        len(result['change_records']), len(result['uncertainty'])))
    return 0


if __name__ == '__main__':
    sys.exit(main())
