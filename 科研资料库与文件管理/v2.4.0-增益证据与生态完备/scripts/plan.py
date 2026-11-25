#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plan.py — 盘点 + dry-run 计划生成（纯标准库）。

输入目录逐项盘点：流式 sha256、可读性登记、zip/tar 展开登记、
空目录登记、重复（内容哈希）与多版本（基础名+不同哈希）识别、
三路元数据解析（文件名模式 / 伴随 CSV / 管理备注 md，带出处合并），
最后由 rule_engine 逐文件计算目标路径，生成 plan.json。

单文件失败不崩溃：任何异常被捕获并登记到 skipped 或 notes。
"""
import argparse
import csv
import hashlib
import json
import os
import re
import sys
import tarfile
import zipfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rule_engine as re_eng  # noqa: E402

CHUNK = 1 << 20
TASK_INPUTS = {'case.json', 'task.md'}
ARCHIVE_EXTS = {'.zip', '.tar', '.tgz', '.tar.gz', '.gz', '.rar', '.7z'}
MAX_SIDECAR_BYTES = 1 << 16


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def sha256_stream(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def list_archive(path):
    """展开登记压缩包内容；损坏/不支持的格式返回 error，不崩溃。"""
    low = path.lower()
    try:
        if low.endswith('.zip'):
            with zipfile.ZipFile(path) as z:
                bad = z.testzip()
                return {'format': 'zip', 'entries': z.namelist(),
                        'corrupt_member': bad}
        if low.endswith(('.tar', '.tgz', '.tar.gz')):
            with tarfile.open(path) as t:
                return {'format': 'tar', 'entries': t.getnames()}
        return {'format': os.path.splitext(low)[1].lstrip('.'),
                'entries': [], 'error': 'unsupported archive format (not extracted)'}
    except (zipfile.BadZipFile, tarfile.TarError, EOFError, OSError) as e:
        return {'format': os.path.splitext(low)[1].lstrip('.'),
                'entries': [], 'error': '%s: %s' % (type(e).__name__, e)}


# ------------------------------------------------------- 三路元数据解析

def parse_filename_metadata(filename, patterns):
    for pat in patterns:
        try:
            m = re.match(pat, filename)
        except re.error:
            continue
        if m:
            return {k: v for k, v in m.groupdict().items() if v}
    return {}


def parse_sidecar_csv(csv_path, basename):
    """伴随表格：任一单元格等于文件名（或 filename/name 列匹配）的行 → 字段。"""
    out = {}
    try:
        with open(csv_path, 'r', encoding='utf-8-sig', errors='replace') as f:
            reader = csv.reader(f)
            rows = list(reader)
    except OSError:
        return out
    if not rows:
        return out
    header = [h.strip() for h in rows[0]]
    name_idx = [i for i, h in enumerate(header)
                if h.lower() in ('filename', 'file', 'name', '文件名', '文件')]
    for rno, row in enumerate(rows[1:], start=2):
        cells = [c.strip() for c in row]
        hit = basename in cells
        if not hit and name_idx:
            hit = any(cells[i] == basename for i in name_idx if i < len(cells))
        if hit:
            for i, h in enumerate(header):
                if h and i < len(cells) and cells[i] and h.lower() not in ('filename', 'file', 'name', '文件名', '文件'):
                    out[h] = cells[i]
            if out:
                out['_evidence'] = 'row %d of %s' % (rno, os.path.basename(csv_path))
                return out
    return {}


def parse_notes_md(md_path, basename):
    """管理备注 md：行内提及文件名且含 key:value（或 key：value）→ 字段。"""
    out = {}
    try:
        with open(md_path, 'r', encoding='utf-8', errors='replace') as f:
            text = f.read(MAX_SIDECAR_BYTES)
    except OSError:
        return out
    kv_re = re.compile(r'(?<![A-Za-z0-9_.])([A-Za-z_][A-Za-z0-9_]{1,31})\s*[:=：]\s*([^，,、;；]+)')
    for lno, line in enumerate(text.splitlines(), start=1):
        if basename not in line:
            continue
        for m in kv_re.finditer(line):
            key, val = m.group(1), m.group(2).strip()
            if key and val and not re.fullmatch(r'(19|20)\d{2}', key):
                out[key] = val
    if out:
        out['_evidence'] = 'lines mentioning %s in %s' % (basename, os.path.basename(md_path))
    return out


def merge_metadata(filename, parent_dir, cfg):
    """三路合并：文件名模式 → 管理备注 md → 伴随 CSV（后者优先）。

    返回 (values, provenance)；provenance: {field: {value, source, evidence}}。
    """
    prov = {}
    values = {}

    def apply(src, d):
        ev = d.pop('_evidence', src)
        for k, v in d.items():
            values[k] = v
            prov[k] = {'value': v, 'source': src, 'evidence': ev}

    apply('filename_pattern',
          parse_filename_metadata(filename, cfg.get('filename_patterns', [])))
    try:
        sibs = sorted(os.listdir(parent_dir))
    except OSError:
        sibs = []
    for s in sibs:
        if s == filename:
            continue
        sp = os.path.join(parent_dir, s)
        if s.lower().endswith('.md') and os.path.isfile(sp):
            d = parse_notes_md(sp, filename)
            if d:
                apply('notes_md', d)
    for s in sibs:
        if s == filename:
            continue
        sp = os.path.join(parent_dir, s)
        if s.lower().endswith('.csv') and os.path.isfile(sp):
            d = parse_sidecar_csv(sp, filename)
            if d:
                apply('sidecar_csv', d)
    return values, prov


# ---------------------------------------------------------------- 盘点

def inventory(input_dir, cfg):
    files, skipped, archives, errors = [], [], [], []
    walk_errors = []

    def _on_walk_error(e):
        walk_errors.append({'path': getattr(e, 'filename', str(e)),
                            'error': '%s: %s' % (type(e).__name__, e)})

    for root, dirs, names in os.walk(input_dir, onerror=_on_walk_error, followlinks=False):
        dirs.sort()
        names.sort()
        for name in names:
            full = os.path.join(root, name)
            rel = os.path.relpath(full, input_dir)
            if rel in TASK_INPUTS:
                skipped.append({'path': rel, 'reason': 'task input file, not library content'})
                continue
            rec = {'rel': rel, 'filename': name, 'ext': name.rpartition('.')[2] if '.' in name else ''}
            try:
                st = os.stat(full)
                rec['size'] = st.st_size
                rec['mtime'] = datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(timespec='seconds')
                rec['sha256'] = sha256_stream(full)
                rec['readable'] = True
                rec['read_error'] = None
            except OSError as e:
                rec['size'] = None
                rec['sha256'] = None
                rec['readable'] = False
                rec['read_error'] = '%s: %s' % (type(e).__name__, e)
                skipped.append({'path': rel, 'reason': 'unreadable: ' + rec['read_error'],
                                'readable': False})
            low = name.lower()
            if any(low.endswith(a) for a in ARCHIVE_EXTS):
                info = list_archive(full) if rec['readable'] else {'entries': [], 'error': rec['read_error']}
                info['path'] = rel
                archives.append(info)
                if info.get('error'):
                    errors.append({'path': rel, 'error': info['error']})
            files.append(rec)
    # 无权限目录显式登记（os.walk 默认静默跳过，绝不静默）
    for we in walk_errors:
        skipped.append({'path': os.path.relpath(we['path'], input_dir)
                        if os.path.isabs(we['path']) else we['path'],
                        'reason': 'unreadable directory: ' + we['error'],
                        'readable': False})
    # 空目录登记
    empty_dirs = []
    for root, dirs, names in os.walk(input_dir, onerror=_on_walk_error, followlinks=False):
        if not dirs and not names:
            empty_dirs.append(os.path.relpath(root, input_dir))
    return files, skipped, archives, empty_dirs, errors


def find_duplicates(files):
    """内容哈希完全相同的文件分组（改名备份副本 = 别名）。"""
    by_hash = {}
    for f in files:
        if f.get('sha256') and f.get('size'):
            by_hash.setdefault(f['sha256'], []).append(f['rel'])
    return [{'sha256': h, 'paths': sorted(v)}
            for h, v in sorted(by_hash.items()) if len(v) > 1]


def find_versions(files):
    """同一文档多历史版本：基础名相同 + 扩展名相同 + 内容哈希不同。"""
    groups = {}
    for f in files:
        stem = f['filename'].rsplit('.', 1)[0] if '.' in f['filename'] else f['filename']
        base, ver = re_eng.version_key(stem)
        key = (f['ext'].lower(), base.lower())
        groups.setdefault(key, []).append(f)
    out = []
    for (ext, base), members in sorted(groups.items()):
        hashes = {m.get('sha256') for m in members if m.get('sha256')}
        if len(members) > 1 and len(hashes) > 1:
            members_sorted = sorted(
                members,
                key=lambda m: (m.get('mtime') or '', m['rel']))
            chain = []
            for i, m in enumerate(members_sorted):
                nxt = members_sorted[i + 1]['rel'] if i + 1 < len(members_sorted) else None
                chain.append({
                    'path': m['rel'],
                    'version_token': re_eng.version_key(
                        m['filename'].rsplit('.', 1)[0])[1],
                    'size': m.get('size'),
                    'sha256': m.get('sha256'),
                    'superseded_by': nxt,
                })
            sizes = {m.get('size') for m in members}
            out.append({
                'base': base, 'ext': ext, 'count': len(members),
                'size_delta_bytes': max(sizes) - min(sizes) if None not in sizes else None,
                'versions': chain,
            })
    return out


def build_plan(input_dir, cfg, case_id=None):
    files, skipped, archives, empty_dirs, errors = inventory(input_dir, cfg)
    duplicates = find_duplicates(files)
    versions = find_versions(files)

    used = set()
    entries = []
    coverage = {}
    for f in files:
        if not f['readable']:
            continue
        values, prov = merge_metadata(f['filename'], os.path.join(input_dir, os.path.dirname(f['rel'])), cfg)
        res = re_eng.compute_target(f, values, cfg)
        target = re_eng.unique_path(res['target'], used)
        used.add(target)
        coverage[res['rule_id']] = coverage.get(res['rule_id'], 0) + 1
        entries.append({
            'source': f['rel'],
            'target': 'library/' + target,
            'action': 'copy',
            'rule_id': res['rule_id'],
            'reason': res['reason'],
            'size': f['size'],
            'sha256': f['sha256'],
            'mtime': f.get('mtime'),
            'metadata': values,
            'metadata_provenance': prov,
            'field_values': res['field_values'],
            'notes': res['notes'],
        })

    plan = {
        'case_id': case_id,
        'generated_at': utcnow(),
        'rules_version': cfg.get('rules_version'),
        'template': cfg.get('template'),
        'input_dir': input_dir,
        'counts': {
            'files_total': len(files),
            'planned': len(entries),
            'skipped': len(skipped),
            'archives': len(archives),
            'empty_dirs': len(empty_dirs),
            'duplicate_groups': len(duplicates),
            'version_groups': len(versions),
            'errors': len(errors),
        },
        'rule_coverage': coverage,
        'entries': entries,
        'skipped': skipped,
        'archives': archives,
        'empty_dirs': empty_dirs,
        'errors': errors,
    }
    return plan, duplicates, versions


def main():
    ap = argparse.ArgumentParser(description='dry-run 生成组织计划 plan.json')
    ap.add_argument('--input', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--rules', default=None)
    ap.add_argument('--case', default=None, help='case.json 路径（提取 case_id）')
    ap.add_argument('--dry-run', action='store_true', help='只生成计划不落地')
    args = ap.parse_args()

    skill_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rules_path = args.rules or os.path.join(skill_root, 'config', 'layout_template.json')
    cfg = re_eng.load_rules(rules_path)

    case_id = None
    if args.case and os.path.exists(args.case):
        try:
            with open(args.case, encoding='utf-8') as f:
                case_id = json.load(f).get('case_id')
        except (OSError, json.JSONDecodeError):
            pass

    plan, duplicates, versions = build_plan(args.input, cfg, case_id)
    os.makedirs(args.work, exist_ok=True)
    with open(os.path.join(args.work, 'plan.json'), 'w', encoding='utf-8') as f:
        json.dump(plan, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.work, 'duplicates.json'), 'w', encoding='utf-8') as f:
        json.dump({'case_id': case_id, 'generated_at': utcnow(),
                   'groups': duplicates}, f, ensure_ascii=False, indent=2)
    with open(os.path.join(args.work, 'versions.json'), 'w', encoding='utf-8') as f:
        json.dump({'case_id': case_id, 'generated_at': utcnow(),
                   'groups': versions}, f, ensure_ascii=False, indent=2)

    c = plan['counts']
    print('[plan] files=%d planned=%d skipped=%d archives=%d empty_dirs=%d dup_groups=%d ver_groups=%d errors=%d' % (
        c['files_total'], c['planned'], c['skipped'], c['archives'],
        c['empty_dirs'], c['duplicate_groups'], c['version_groups'], c['errors']))
    print('[plan] coverage: %s' % json.dumps(plan['rule_coverage'], ensure_ascii=False))
    if args.dry_run:
        print('[plan] dry-run: nothing applied.')


if __name__ == '__main__':
    main()
