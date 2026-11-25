#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""gain_report.py — 可机检的增益度量报告（纯标准库）。

输出：
  /app/output/gain_metrics.json   结构化度量（全部来自真实运行计数）
  /app/output/gain_report.md      人读报告（含"前后对照"小节）

度量原则：每一个数字都能在工作区工件（plan.json / journal.jsonl /
audit.json / duplicates.json / versions.json / run_timing.json /
search_results.json / recovery_log.jsonl）中找到来源，绝不编造。

幂等验证：用同一输入目录 + 同一份规则配置在内存中重建一次计划，
比较规范化条目哈希（source→target→sha256 序列）。一致即确定性成立。
"""
import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_engine as re_eng  # noqa: E402
import plan as plan_mod  # noqa: E402


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def read_jsonl(path):
    rows = []
    try:
        with open(path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        rows.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    except OSError:
        pass
    return rows


def entries_digest(entries):
    """规范化条目哈希：只含确定性内容（不含时间戳）。"""
    canon = json.dumps(
        [[e.get('source'), e.get('target'), e.get('sha256'), e.get('rule_id')]
         for e in entries],
        ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(canon.encode('utf-8')).hexdigest()


# ------------------------------------------------------- 整理前混乱度

def before_metrics(plan):
    """从 plan.json 推导"整理前"状态（输入目录的真实混乱度）。"""
    entries = plan.get('entries', [])
    skipped = plan.get('skipped', [])
    duplicates = plan.get('__duplicates__', [])  # 由 main 注入
    # 根目录散落文件：source 不含路径分隔符
    root_scattered = sum(1 for e in entries if '/' not in e['source'].replace('\\', '/'))
    # 重名组：规范化前文件名相同的多组（改名副本、不同目录同名文件）
    by_name = {}
    for e in entries:
        by_name.setdefault(os.path.basename(e['source']), []).append(e['source'])
    same_name_groups = sum(1 for v in by_name.values() if len(v) > 1)
    # 无出处字段：project/year 走了 fallback（provenance 中无该字段）
    fields_no_source = 0
    fields_total = 0
    for e in entries:
        prov = e.get('metadata_provenance', {})
        for f in ('project', 'year'):
            fields_total += 1
            if f not in prov:
                fields_no_source += 1
    exact_dup_extra = sum(max(0, len(g.get('paths', [])) - 1) for g in duplicates)
    return {
        'root_scattered_files': root_scattered,
        'same_name_groups': same_name_groups,
        'exact_duplicate_extra_copies': exact_dup_extra,
        'fields_without_source': fields_no_source,
        'fields_checked': fields_total,
        'skipped_items': len(skipped),
    }


# ------------------------------------------------------- 整理后质量

def after_metrics(plan, audit, duplicates, versions):
    entries = plan.get('entries', [])
    counts = plan.get('counts', {})
    files_total = counts.get('files_total', len(entries))
    planned = counts.get('planned', len(entries))
    placed_rate = (planned / files_total) if files_total else None
    # 字段填充率：project/year 有真实出处（非 fallback）的比例
    filled, total = 0, 0
    for e in entries:
        prov = e.get('metadata_provenance', {})
        for f in ('project', 'year'):
            total += 1
            if f in prov:
                filled += 1
    field_fill_rate = (filled / total) if total else None
    verified = (audit or {}).get('verified', 0)
    verifiable_rate = (verified / planned) if planned else None
    return {
        'placed_entries': planned,
        'placement_rate': placed_rate,
        'fields_filled_with_provenance': filled,
        'fields_checked': total,
        'field_fill_rate': field_fill_rate,
        'hash_verified_files': verified,
        'verifiable_rate': verifiable_rate,
        'audit_all_match': bool((audit or {}).get('all_match')),
    }


def main():
    ap = argparse.ArgumentParser(description='生成可机检增益度量报告')
    ap.add_argument('--input', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--rules', default=None, help='生效的规则配置（幂等复算用）')
    ap.add_argument('--case', default=None)
    args = ap.parse_args()

    work, out = args.work, args.output
    plan = read_json(os.path.join(work, 'plan.json'), {}) or {}
    audit = read_json(os.path.join(work, 'audit.json'), {}) or {}
    duplicates = (read_json(os.path.join(work, 'duplicates.json'), {}) or {}).get('groups', [])
    versions = (read_json(os.path.join(work, 'versions.json'), {}) or {}).get('groups', [])
    timing = read_json(os.path.join(work, 'run_timing.json'), {}) or {}
    search = read_json(os.path.join(out, 'search_results.json'), {}) or {}
    recovery = read_jsonl(os.path.join(out, 'recovery_log.jsonl'))
    journal = read_jsonl(os.path.join(work, 'journal.jsonl'))
    plan['__duplicates__'] = duplicates

    # ---- 计数（全部来自工件） ----------------------------------------
    counts = plan.get('counts', {})
    version_edges = sum(max(0, g.get('count', 1) - 1) for g in versions)
    dedup_merged = sum(max(0, len(g.get('paths', [])) - 1) for g in duplicates)
    ops = [j for j in journal if j.get('op') in
           ('copy', 'quarantine_empty_dir', 'copy_failed', 'skip')]
    searches = search.get('results', [])
    search_answered = sum(1 for r in searches if r.get('hits'))
    recovered_ok = sum(1 for r in recovery if r.get('status') == 'recovered')

    before = before_metrics(plan)
    after = after_metrics(plan, audit, duplicates, versions)

    # ---- 幂等验证：同输入同配置重建计划，比较条目哈希 ------------------
    rules_path = args.rules
    if not rules_path:
        eff = os.path.join(work, 'layout_template.effective.json')
        rules_path = eff if os.path.exists(eff) else os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'config', 'layout_template.json')
    idem = {'checked': False, 'idempotent': None, 'reason': None}
    try:
        cfg = re_eng.load_rules(rules_path)
        plan2, dups2, vers2 = plan_mod.build_plan(args.input, cfg)
        h1 = entries_digest(plan.get('entries', []))
        h2 = entries_digest(plan2.get('entries', []))
        idem = {
            'checked': True,
            'idempotent': h1 == h2,
            'first_run_entries_sha256': h1,
            'rerun_entries_sha256': h2,
            'method': 'same input + same rules rebuilt in-process; '
                      'canonical (source,target,sha256,rule_id) digest compared',
        }
        if h1 != h2:
            idem['reason'] = 'digest mismatch (non-determinism or input changed)'
    except Exception as e:  # 复算失败不崩溃，诚实登记
        idem['reason'] = 'rerun failed: %s: %s' % (type(e).__name__, e)

    metrics = {
        'case_id': plan.get('case_id'),
        'generated_at': utcnow(),
        'model_calls': 0,  # 确定性流水线事实：全流程零模型请求
        'counts': {
            'files_processed': counts.get('files_total', 0),
            'placed_entries': counts.get('planned', 0),
            'skipped_entries': counts.get('skipped', 0),
            'exact_dedup_merged_entries': dedup_merged,
            'version_chain_edges': version_edges,
            'duplicate_groups': counts.get('duplicate_groups', 0),
            'version_groups': counts.get('version_groups', 0),
            'journal_operations': len(ops),
            'search_queries': len(searches),
            'search_answered': search_answered,
            'recovery_requests': len(recovery),
            'recovery_succeeded': recovered_ok,
        },
        'efficiency': {
            'pipeline_wall_seconds': timing.get('total_seconds'),
            'step_seconds': timing.get('steps', {}),
            'manual_items_avoided': counts.get('files_total', 0) + dedup_merged
            + version_edges + len(searches) + len(recovery),
            'note': 'manual_items_avoided = 若人工处理需逐项归位/比对/检索/恢复的条目数',
        },
        'before_after': {'before': before, 'after': after},
        'idempotency': idem,
        'evidence_files': {
            'plan': os.path.join(work, 'plan.json'),
            'journal': os.path.join(work, 'journal.jsonl'),
            'audit': os.path.join(work, 'audit.json'),
            'duplicates': os.path.join(work, 'duplicates.json'),
            'versions': os.path.join(work, 'versions.json'),
            'timing': os.path.join(work, 'run_timing.json'),
            'search_results': os.path.join(out, 'search_results.json'),
            'recovery_log': os.path.join(out, 'recovery_log.jsonl'),
        },
    }

    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, 'gain_metrics.json'), 'w', encoding='utf-8') as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    # ---- 人读报告 ------------------------------------------------------
    c = metrics['counts']
    eff = metrics['efficiency']
    b, a = before, after

    def pct(x):
        return 'n/a' if x is None else '%.1f%%' % (x * 100)

    lines = [
        '# 增益度量报告（gain report）',
        '',
        '- case_id: `%s`' % metrics['case_id'],
        '- 生成时间: %s' % metrics['generated_at'],
        '- 模型调用数: **%d**（全流程确定性脚本，零模型请求）' % metrics['model_calls'],
        '- 流水线总耗时: `%s` 秒；单文件平均: `%s` 秒' % (
            eff['pipeline_wall_seconds'],
            round(eff['pipeline_wall_seconds'] / c['files_processed'], 3)
            if isinstance(eff['pipeline_wall_seconds'], (int, float))
            and c['files_processed'] else 'n/a'),
        '',
        '## 可机检计数',
        '',
        '| 指标 | 值 | 含义 |',
        '|---|---|---|',
        '| 处理文件数 | %d | 输入盘点到的全部文件 |' % c['files_processed'],
        '| 归位条目数 | %d | 实际复制进 library 的条目 |' % c['placed_entries'],
        '| 精确去重合并条目数 | %d | 内容哈希相同的冗余副本（人工需逐个比对） |' % c['exact_dedup_merged_entries'],
        '| 版本链边数 | %d | superseded_by 链上的版本关系 |' % c['version_chain_edges'],
        '| 跳过条目数 | %d | 不可读/任务输入等（均带原因） |' % c['skipped_entries'],
        '| 账本操作数 | %d | journal.jsonl 中 copy/quarantine/skip 记录 |' % c['journal_operations'],
        '| 检索/问答数（命中） | %d（%d） | case.json searches/questions |' % (c['search_queries'], c['search_answered']),
        '| 恢复请求（成功） | %d（%d） | recovery_log.jsonl |' % (c['recovery_requests'], c['recovery_succeeded']),
        '',
        '**人工对照口径**：若人工完成同等整理，至少需处理 %d 个条目'
        '（= 文件逐项归位 %d + 去重逐个比对 %d + 版本链梳理 %d + 检索 %d + 恢复 %d）。'
        '本流水线自动完成，脚本总耗时 %s 秒，模型调用 0 次。' % (
            eff['manual_items_avoided'], c['files_processed'],
            c['exact_dedup_merged_entries'], c['version_chain_edges'],
            c['search_queries'], c['recovery_requests'],
            eff['pipeline_wall_seconds']),
        '',
        '## 前后对照（同输入同权限同批次）',
        '',
        '### 整理前（输入目录真实混乱度）',
        '',
        '| 指标 | 值 |',
        '|---|---|',
        '| 根目录散落文件数 | %d |' % b['root_scattered_files'],
        '| 重名文件组数 | %d |' % b['same_name_groups'],
        '| 精确重复冗余副本数 | %d |' % b['exact_duplicate_extra_copies'],
        '| 无出处字段数（project/year，共查 %d） | %d |' % (b['fields_checked'], b['fields_without_source']),
        '',
        '### 整理后（输出可核验质量）',
        '',
        '| 指标 | 值 |',
        '|---|---|',
        '| 归位率（归位/处理） | %s（%d/%d） |' % (pct(a['placement_rate']), a['placed_entries'], c['files_processed']),
        '| 字段填充率（有真实出处） | %s（%d/%d） |' % (pct(a['field_fill_rate']), a['fields_filled_with_provenance'], a['fields_checked']),
        '| 可校验文件比例（重哈希一致） | %s（%d/%d） |' % (pct(a['verifiable_rate']), a['hash_verified_files'], a['placed_entries']),
        '| audit 全量核对 | %s |' % ('全部一致' if a['audit_all_match'] else '存在不一致，见 audit.json'),
        '',
        '## 幂等重跑验证',
        '',
        '- 方法：%s' % (idem.get('method') or idem.get('reason') or '未执行'),
        '- 首次条目哈希: `%s`' % idem.get('first_run_entries_sha256'),
        '- 复算条目哈希: `%s`' % idem.get('rerun_entries_sha256'),
        '- 结论: **%s**' % ('一致（幂等成立）' if idem.get('idempotent') is True
                            else ('不一致' if idem.get('idempotent') is False else '未能验证')),
        '',
        '## 证据文件',
        '',
    ]
    for k, v in metrics['evidence_files'].items():
        lines.append('- `%s`: %s' % (k, v))
    lines.append('')
    lines.append('> 所有数字均由脚本从上述工件实时计数生成，无手工填写。')

    with open(os.path.join(out, 'gain_report.md'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')

    # ---- 回链 result.json（只增不改既有字段） ---------------------------
    result_path = os.path.join(out, 'result.json')
    result = read_json(result_path)
    if isinstance(result, dict):
        arts = result.setdefault('artifacts', {})
        arts.setdefault('gain_report', os.path.join(out, 'gain_report.md'))
        arts.setdefault('gain_metrics', os.path.join(out, 'gain_metrics.json'))
        if searches:
            arts.setdefault('search_results', os.path.join(out, 'search_results.json'))
        if recovery:
            arts.setdefault('recovery_log', os.path.join(out, 'recovery_log.jsonl'))
        tmp = result_path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.replace(tmp, result_path)

    print('[gain_report] files=%d placed=%d dedup=%d ver_edges=%d ops=%d '
          'search=%d/%d recovery=%d/%d idempotent=%s' % (
              c['files_processed'], c['placed_entries'],
              c['exact_dedup_merged_entries'], c['version_chain_edges'],
              c['journal_operations'], c['search_answered'], c['search_queries'],
              c['recovery_succeeded'], c['recovery_requests'],
              idem.get('idempotent')))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        # 增益报告失败绝不影响主流程结论
        print('[gain_report] failed: %s: %s' % (type(e).__name__, e), file=sys.stderr)
        sys.exit(1)
