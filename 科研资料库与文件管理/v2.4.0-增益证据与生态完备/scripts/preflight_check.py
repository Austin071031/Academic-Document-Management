#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preflight_check.py — 提交契约自检（纯标准库）。

对 Skill 目录逐项核验平台提交约束：
  * SKILL.md frontmatter 合法（--- 包裹、name/description 存在、
    description UTF-8 字节数 ≤ 900）
  * 文件总数 ≤ 50
  * 单文件 ≤ 500KB；总大小 ≤ 2MB
  * 全部 UTF-8 可解码文本（无二进制）
  * 无符号链接
  * 无疑似 token/密钥模式

用法：
  python3 scripts/preflight_check.py [--root SKILL_ROOT] [--out preflight_report.json]
退出码：0 全部通过；1 存在 fail 项。
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

MAX_FILES = 50
MAX_FILE_BYTES = 500 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024
MAX_DESC_BYTES = 900

SECRET_RE = re.compile(
    r'(?i)(api[_-]?key|secret|token|password|passwd|access[_-]?key)'
    r'\s*[:=]\s*["\']?[A-Za-z0-9_\-]{16,}')


def utcnow():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def check_frontmatter(root):
    p = os.path.join(root, 'SKILL.md')
    res = {'file': 'SKILL.md', 'status': 'fail', 'detail': ''}
    try:
        with open(p, 'rb') as f:
            raw = f.read()
        text = raw.decode('utf-8')
    except (OSError, UnicodeDecodeError) as e:
        res['detail'] = 'cannot read as UTF-8: %s' % e
        return res
    lines = text.splitlines()
    if not lines or lines[0].strip() != '---':
        res['detail'] = 'frontmatter must start with --- on line 1'
        return res
    try:
        end = lines[1:].index('---') + 1
    except ValueError:
        res['detail'] = 'frontmatter closing --- not found'
        return res
    fm = {}
    for ln in lines[1:end]:
        if ':' in ln and not ln.startswith((' ', '\t')):
            k, _, v = ln.partition(':')
            fm[k.strip()] = v.strip().strip('"').strip("'")
    name = fm.get('name')
    desc = fm.get('description')
    problems = []
    if not name:
        problems.append('missing name')
    if not desc:
        problems.append('missing description')
    else:
        nbytes = len(desc.encode('utf-8'))
        if nbytes > MAX_DESC_BYTES:
            problems.append('description %d bytes > %d' % (nbytes, MAX_DESC_BYTES))
    if problems:
        res['detail'] = '; '.join(problems)
        return res
    res['status'] = 'pass'
    res['detail'] = 'name=%r description=%d bytes (<= %d)' % (
        name, len(desc.encode('utf-8')), MAX_DESC_BYTES)
    return res


def main():
    ap = argparse.ArgumentParser(description='Skill 提交契约自检')
    ap.add_argument('--root', default=None)
    ap.add_argument('--out', default=None)
    args = ap.parse_args()

    root = args.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    root = os.path.abspath(root)
    out_path = args.out or os.path.join(root, 'preflight_report.json')

    checks = []
    files, symlinks, non_utf8, oversized, secrets = [], [], [], [], []
    total = 0
    for r, dirs, names in os.walk(root, followlinks=False):
        dirs.sort()
        names.sort()
        # __pycache__ 等缓存目录不进提交包，跳过但登记
        dirs[:] = [d for d in dirs if d != '__pycache__']
        for n in names:
            full = os.path.join(r, n)
            rel = os.path.relpath(full, root)
            if os.path.islink(full):
                symlinks.append(rel)
                continue
            try:
                size = os.path.getsize(full)
            except OSError:
                non_utf8.append(rel + ' (stat failed)')
                continue
            total += size
            files.append((rel, size))
            if size > MAX_FILE_BYTES:
                oversized.append('%s (%d bytes)' % (rel, size))
            try:
                with open(full, 'rb') as f:
                    raw = f.read()
                text = raw.decode('utf-8')
            except UnicodeDecodeError:
                non_utf8.append(rel + ' (not UTF-8)')
                continue
            except OSError:
                non_utf8.append(rel + ' (read failed)')
                continue
            if '\x00' in text:
                non_utf8.append(rel + ' (contains NUL byte)')
            for m in SECRET_RE.finditer(text):
                secrets.append('%s: pattern %r' % (rel, m.group(1)))
                break

    checks.append(check_frontmatter(root))
    checks.append({'check': 'file_count', 'status': 'pass' if len(files) <= MAX_FILES else 'fail',
                   'detail': '%d files (<= %d)' % (len(files), MAX_FILES)})
    checks.append({'check': 'file_size', 'status': 'pass' if not oversized else 'fail',
                   'detail': 'all files <= 500KB' if not oversized
                   else 'oversized: ' + '; '.join(oversized)})
    checks.append({'check': 'total_size', 'status': 'pass' if total <= MAX_TOTAL_BYTES else 'fail',
                   'detail': '%d bytes (<= %d)' % (total, MAX_TOTAL_BYTES)})
    checks.append({'check': 'utf8_text', 'status': 'pass' if not non_utf8 else 'fail',
                   'detail': 'all files UTF-8 text' if not non_utf8
                   else '; '.join(non_utf8)})
    checks.append({'check': 'no_symlinks', 'status': 'pass' if not symlinks else 'fail',
                   'detail': 'no symlinks' if not symlinks
                   else '; '.join(symlinks)})
    checks.append({'check': 'no_secrets', 'status': 'pass' if not secrets else 'fail',
                   'detail': 'no token/secret patterns' if not secrets
                   else '; '.join(secrets)})

    ok = all(c['status'] == 'pass' for c in checks)
    report = {
        'generated_at': utcnow(),
        'root': root,
        'overall': 'pass' if ok else 'fail',
        'file_count': len(files),
        'total_bytes': total,
        'checks': checks,
        'files': [{'path': rel, 'bytes': s} for rel, s in sorted(files)],
    }
    tmp = out_path + '.tmp'
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(tmp, out_path)
    print('[preflight] overall=%s files=%d total=%dB -> %s' % (
        report['overall'], len(files), total, out_path))
    for c in checks:
        mark = 'OK ' if c['status'] == 'pass' else 'FAIL'
        print('[preflight] %s %s: %s' % (mark, c.get('check', 'frontmatter'), c['detail']))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
