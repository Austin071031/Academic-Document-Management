#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""organize.py — 主入口：模板规则引擎驱动的科研资料库组织。

用法：
  python3 scripts/organize.py --input /input --work /app/work \
      --output /app/output [--rules config/layout_template.json]

执行协议（全部确定性，零模型请求）：
  step0 检查 /input 是否存在；写 partial result.json（任何时刻 result.json 可用）
  step1 若 case.json/task.md 指定不同目录约定 → 翻译进配置（规则即约定）
  step2 plan.py dry-run 生成 plan.json / duplicates.json / versions.json
  step3 apply.py 落地到 /app/output/library/ 并写 journal.jsonl
  step4 audit.py 重哈希核对 + 规则覆盖率
  step5 finalize.py 写最终 result.json
  step6 qa.py 回答 case.json 的 searches/questions（search_results.json）
  step7 recover.py 按文件名/哈希恢复并校验（recovery_log.jsonl）
  step8 gain_report.py 可机检增益度量（gain_report.md + gain_metrics.json）
step6–8 为 v2.4.0 增量，全部 tolerate_failure：失败只登记，不影响 step0–5 结论。
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone

SCRIPTS = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPTS)
DEFAULT_RULES = os.path.join(SKILL_ROOT, 'config', 'layout_template.json')

FIELD_TOKEN_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def log(msg):
    print('[organize %s] %s' % (utcnow(), msg), flush=True)


STEP_TIMES = {}


def run_step(script, args, tolerate_failure=False):
    cmd = [sys.executable, os.path.join(SCRIPTS, script)] + args
    log('run: %s' % ' '.join(os.path.basename(x) for x in cmd))
    t0 = time.monotonic()
    p = subprocess.run(cmd)
    STEP_TIMES[script] = round(STEP_TIMES.get(script, 0.0) + time.monotonic() - t0, 3)
    if p.returncode != 0 and not tolerate_failure:
        raise RuntimeError('step failed: %s (exit %d)' % (script, p.returncode))
    return p.returncode


# ------------------------------------------------------- step1 约定翻译

def detect_convention(input_dir):
    """从 task.md / case.json 中找目录模板约定（如 {topic}/{year}/{kind}）。"""
    candidates = []
    for fname in ('task.md', 'case.json'):
        path = os.path.join(input_dir, fname)
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding='utf-8', errors='replace') as f:
                text = f.read()
        except OSError:
            continue
        if fname == 'case.json':
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                data = {}
            for key in ('layout', 'directory_convention', 'template', 'layout_template'):
                v = data.get(key)
                if isinstance(v, str) and '/' in v:
                    candidates.append(v)
        for m in re.finditer(r'\{[a-zA-Z_][a-zA-Z0-9_]*\}(?:/\{[a-zA-Z_][a-zA-Z0-9_]*\})+', text):
            candidates.append(m.group(0))
    return candidates


def translate_convention(template, base_rules_path, out_path):
    """把题目目录约定翻译进规则配置：替换模板、按 token 补字段字典。"""
    with open(base_rules_path, encoding='utf-8') as f:
        cfg = json.load(f)
    cfg['template'] = template
    fields = cfg.setdefault('fields', {})
    for token in FIELD_TOKEN_RE.findall(template):
        if token == 'name':
            fields.setdefault('name', {'description': 'normalized file name', 'pattern': '.{1,240}'})
        else:
            fields.setdefault(token, {
                'description': 'translated from task convention; values from metadata or filename',
                'pattern': r'^[\w\u4e00-\u9fff][\w\u4e00-\u9fff .-]{0,80}$',
                'fallback': 'unknown-' + token,
            })
    cfg['default_rule']['target_template'] = template
    for rule in cfg.get('route_rules', []):
        rule.setdefault('target_template', template)
    # 路由规则一律改用题目模板：字段由 rule_engine 推导（含同义别名镜像），
    # 规则只负责"匹配哪些文件"，目录结构完全由题目约定决定。
    for rule in cfg.get('route_rules', []):
        rule['target_template'] = template
    cfg['default_rule']['target_template'] = template
    cfg['rules_version'] = str(cfg.get('rules_version', '3.0.0')) + '+convention'
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    return out_path


def main():
    pipeline_t0 = time.monotonic()
    ap = argparse.ArgumentParser(description='模板规则引擎驱动的资料库组织主入口')
    ap.add_argument('--input', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--rules', default=None)
    ap.add_argument('--case', default=None)
    args = ap.parse_args()

    case_path = args.case or os.path.join(args.input, 'case.json')
    rules_path = args.rules or DEFAULT_RULES

    os.makedirs(args.work, exist_ok=True)
    os.makedirs(args.output, exist_ok=True)

    # ---- step0：检查输入，先写 partial result.json --------------------
    if not os.path.isdir(args.input):
        log('step0: input dir missing: %s' % args.input)
        run_step('finalize.py', ['--case', case_path, '--work', args.work,
                                 '--output', args.output, '--partial'],
                 tolerate_failure=True)
        return 1
    log('step0: input OK, partial result.json written')
    run_step('finalize.py', ['--case', case_path, '--work', args.work,
                             '--output', args.output, '--partial'],
             tolerate_failure=True)

    # ---- step1：题目约定 → 规则配置 -----------------------------------
    effective_rules = rules_path
    conventions = detect_convention(args.input)
    if conventions:
        tmpl = conventions[0]
        with open(rules_path, encoding='utf-8') as f:
            current = json.load(f).get('template')
        if tmpl != current:
            effective_rules = os.path.join(args.work, 'layout_template.effective.json')
            translate_convention(tmpl, rules_path, effective_rules)
            log('step1: convention %r translated -> %s' % (tmpl, effective_rules))
        else:
            log('step1: convention matches default template, no rewrite')
    else:
        log('step1: no convention found in task inputs, using default rules')

    # ---- step2：plan dry-run ------------------------------------------
    run_step('plan.py', ['--input', args.input, '--work', args.work,
                         '--rules', effective_rules, '--case', case_path,
                         '--dry-run'])
    log('step2: plan.json ready for review (--dry-run only)')

    # ---- step3：apply ---------------------------------------------------
    rc = run_step('apply.py', ['--input', args.input, '--work', args.work,
                               '--output', args.output], tolerate_failure=True)
    log('step3: apply finished rc=%d' % rc)

    # ---- step4：audit ---------------------------------------------------
    run_step('audit.py', ['--work', args.work, '--output', args.output],
             tolerate_failure=True)
    log('step4: audit finished')

    # ---- step5：finalize -------------------------------------------------
    run_step('finalize.py', ['--case', case_path, '--work', args.work,
                             '--output', args.output], tolerate_failure=True)
    log('step5: final result.json written')

    # ---- step6：检索问答（v2.4.0） ---------------------------------------
    run_step('qa.py', ['--input', args.input, '--work', args.work,
                       '--output', args.output, '--case', case_path],
             tolerate_failure=True)
    log('step6: search_results.json written (if case.json has searches/questions)')

    # ---- step7：恢复操作（v2.4.0） ---------------------------------------
    run_step('recover.py', ['--input', args.input, '--work', args.work,
                            '--output', args.output, '--case', case_path],
             tolerate_failure=True)
    log('step7: recovery_log.jsonl written (if case.json has recovery requests)')

    # ---- step8：增益度量（v2.4.0） ---------------------------------------
    timing = {'generated_at': utcnow(),
              'total_seconds': round(time.monotonic() - pipeline_t0, 3),
              'steps': dict(STEP_TIMES)}
    with open(os.path.join(args.work, 'run_timing.json'), 'w', encoding='utf-8') as f:
        json.dump(timing, f, ensure_ascii=False, indent=2)
    run_step('gain_report.py', ['--input', args.input, '--work', args.work,
                                '--output', args.output, '--rules', effective_rules,
                                '--case', case_path],
             tolerate_failure=True)
    log('step8: gain_report.md + gain_metrics.json written')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:  # 兜底：尽力留下 partial result.json
        print('[organize] fatal: %s: %s' % (type(e).__name__, e), file=sys.stderr)
        try:
            import finalize
            os.makedirs('/app/work', exist_ok=True)
            os.makedirs('/app/output', exist_ok=True)
            result = finalize.build_result(None, None, '/app/work',
                                           '/app/output', partial=True)
            result['uncertainty'].insert(0, 'fatal error: %s: %s' % (type(e).__name__, e))
            with open('/app/output/result.json', 'w', encoding='utf-8') as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
        sys.exit(2)
