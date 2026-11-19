#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""audit.py — 重哈希核对 + 规则覆盖率报告。

* 对 /app/output/library/ 中每个落地文件重新流式 sha256，与 plan 记录比对。
* 规则覆盖率：多少文件命中哪条规则、多少落入 DEFAULT、多少跳过及原因。
* 输出 audit.json；存在不一致时进程退出码为 1（不崩溃，仅报告）。
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from plan import sha256_stream  # noqa: E402


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def main():
    ap = argparse.ArgumentParser(description='核对落地结果并生成覆盖率报告')
    ap.add_argument('--work', required=True)
    ap.add_argument('--output', required=True)
    args = ap.parse_args()

    with open(os.path.join(args.work, 'plan.json'), encoding='utf-8') as f:
        plan = json.load(f)

    mismatches, missing, verified = [], [], 0
    for e in plan['entries']:
        dst = os.path.join(args.output, e['target'])
        if not os.path.exists(dst):
            missing.append(e['target'])
            continue
        try:
            h = sha256_stream(dst)
        except OSError as ex:
            missing.append('%s (unreadable: %s)' % (e['target'], ex))
            continue
        if e['sha256'] and h != e['sha256']:
            mismatches.append({'target': e['target'], 'expected': e['sha256'], 'got': h})
        else:
            verified += 1

    skipped_reasons = {}
    for s in plan.get('skipped', []):
        key = s['reason'].split(':')[0]
        skipped_reasons[key] = skipped_reasons.get(key, 0) + 1

    audit = {
        'generated_at': utcnow(),
        'verified': verified,
        'mismatches': mismatches,
        'missing': missing,
        'rule_coverage': plan.get('rule_coverage', {}),
        'coverage_total': sum(plan.get('rule_coverage', {}).values()),
        'skipped_total': len(plan.get('skipped', [])),
        'skipped_by_reason': skipped_reasons,
        'all_match': (not mismatches) and (not missing),
    }
    with open(os.path.join(args.work, 'audit.json'), 'w', encoding='utf-8') as f:
        json.dump(audit, f, ensure_ascii=False, indent=2)

    print('[audit] verified=%d/%d mismatches=%d missing=%d all_match=%s' % (
        verified, len(plan['entries']), len(mismatches), len(missing), audit['all_match']))
    print('[audit] coverage: %s' % json.dumps(audit['rule_coverage'], ensure_ascii=False))
    print('[audit] skipped_by_reason: %s' % json.dumps(skipped_reasons, ensure_ascii=False))
    return 0 if audit['all_match'] else 1


if __name__ == '__main__':
    sys.exit(main())
