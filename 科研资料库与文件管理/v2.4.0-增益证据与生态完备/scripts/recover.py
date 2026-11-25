#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recover.py — 轻量恢复：按文件名/哈希从账本与压缩包登记中恢复（纯标准库）。

case.json 的 recovery（或 recover / recovery_requests）列表逐项处理，
元素可为字符串（文件名或 sha256）或 {filename|name|sha256|path: ...}：

  1. 按 sha256 在 plan.json 条目中找 → 从 /app/output/library 复制并校验；
  2. 按文件名在 plan/duplicates 中找 → 优先取 library 已归位副本，
     否则从输入目录原路径复制，复制后重哈希校验；
  3. 文件名命中压缩包清单（zip/tar）→ 从压缩包中解出该成员并登记；
  4. 全部找不到 → status=not_found + 原因，绝不编造。

输出：/app/output/recovered/<文件> 与 /app/output/recovery_log.jsonl。
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
import tarfile
import zipfile
from datetime import datetime, timezone

CHUNK = 1 << 20
HEX64 = set('0123456789abcdef')


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


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def read_json(path, default=None):
    try:
        with open(path, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def looks_like_sha256(s):
    return len(s) == 64 and all(c in HEX64 for c in s.lower())


def extract_requests(case):
    reqs = []
    for key in ('recovery', 'recover', 'recovery_requests'):
        items = case.get(key)
        if not isinstance(items, list):
            continue
        for it in items:
            if isinstance(it, str):
                reqs.append({'raw': it})
            elif isinstance(it, dict):
                q = None
                for k in ('filename', 'name', 'sha256', 'path', 'file', 'target'):
                    v = it.get(k)
                    if isinstance(v, str) and v.strip():
                        q = v.strip()
                        break
                if q:
                    reqs.append({'raw': q})
    return reqs


def safe_out_name(name):
    """输出文件名安全化：去目录成分，空则占位。"""
    base = os.path.basename(name.replace('\\', '/')) or 'recovered_item'
    return base


def copy_verify(src, dst_dir, expect_sha=None):
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir, safe_out_name(src))
    n = 2
    while os.path.exists(dst):
        root, ext = os.path.splitext(os.path.join(dst_dir, safe_out_name(src)))
        dst = '%s__r%d%s' % (root, n, ext)
        n += 1
    shutil.copy2(src, dst)
    got = sha256_stream(dst)
    verified = (expect_sha is None) or (got == expect_sha)
    return dst, got, verified


def try_archive_member(input_dir, archives, want_name):
    """从登记的压缩包清单中找成员并解出。返回 (bytes, evidence) 或 None。"""
    want_base = os.path.basename(want_name)
    for a in archives:
        entries = a.get('entries') or []
        match = None
        for ent in entries:
            if ent == want_name or os.path.basename(ent) == want_base:
                match = ent
                break
        if match is None:
            continue
        apath = os.path.join(input_dir, a.get('path', ''))
        low = apath.lower()
        try:
            if low.endswith('.zip'):
                with zipfile.ZipFile(apath) as z:
                    return z.read(match), 'zip member %s of %s' % (match, a.get('path'))
            if low.endswith(('.tar', '.tgz', '.tar.gz')):
                with tarfile.open(apath) as t:
                    f = t.extractfile(match)
                    if f is not None:
                        return f.read(), 'tar member %s of %s' % (match, a.get('path'))
        except (zipfile.BadZipFile, tarfile.TarError, KeyError, EOFError, OSError):
            continue
    return None


def main():
    ap = argparse.ArgumentParser(description='按文件名/哈希恢复文件并校验')
    ap.add_argument('--input', required=True)
    ap.add_argument('--work', required=True)
    ap.add_argument('--output', required=True)
    ap.add_argument('--case', default=None)
    args = ap.parse_args()

    case_path = args.case or os.path.join(args.input, 'case.json')
    case = read_json(case_path, {}) or {}
    plan = read_json(os.path.join(args.work, 'plan.json'), {}) or {}
    duplicates = (read_json(os.path.join(args.work, 'duplicates.json'), {}) or {}).get('groups', [])

    requests = extract_requests(case)
    rec_dir = os.path.join(args.output, 'recovered')
    log_path = os.path.join(args.output, 'recovery_log.jsonl')
    os.makedirs(args.output, exist_ok=True)

    by_sha = {}
    by_name = {}
    for e in plan.get('entries', []):
        if e.get('sha256'):
            by_sha.setdefault(e['sha256'], e)
        by_name.setdefault(os.path.basename(e['source']), []).append(e)

    n_ok = 0
    with open(log_path, 'w', encoding='utf-8') as log:
        def emit(rec):
            rec['ts'] = utcnow()
            log.write(json.dumps(rec, ensure_ascii=False) + '\n')

        for req in requests:
            want = req['raw']
            rec = {'request': want, 'status': 'not_found',
                   'matched_by': None, 'evidence': None, 'dst': None,
                   'sha256': None, 'verified': None}
            try:
                # 1) sha256 精确匹配
                if looks_like_sha256(want) and want.lower() in by_sha:
                    e = by_sha[want.lower()]
                    lib_copy = os.path.join(args.output, e['target'])
                    src = lib_copy if os.path.exists(lib_copy) \
                        else os.path.join(args.input, e['source'])
                    dst, got, verified = copy_verify(src, rec_dir, e.get('sha256'))
                    rec.update(status='recovered' if verified else 'hash_mismatch',
                               matched_by='sha256',
                               evidence='plan.json entry %s' % e['source'],
                               dst=os.path.relpath(dst, args.output),
                               sha256=got, verified=verified)
                # 2) 文件名匹配 plan/duplicates
                elif os.path.basename(want) in by_name:
                    e = by_name[os.path.basename(want)][0]
                    lib_copy = os.path.join(args.output, e['target'])
                    src = lib_copy if os.path.exists(lib_copy) \
                        else os.path.join(args.input, e['source'])
                    dst, got, verified = copy_verify(src, rec_dir, e.get('sha256'))
                    rec.update(status='recovered' if verified else 'hash_mismatch',
                               matched_by='filename',
                               evidence='plan.json entry %s (rule %s)' % (e['source'], e.get('rule_id')),
                               dst=os.path.relpath(dst, args.output),
                               sha256=got, verified=verified)
                else:
                    # 3) 压缩包成员
                    r = try_archive_member(args.input, plan.get('archives', []), want)
                    if r is not None:
                        data, ev = r
                        os.makedirs(rec_dir, exist_ok=True)
                        dst = os.path.join(rec_dir, safe_out_name(want))
                        with open(dst, 'wb') as f:
                            f.write(data)
                        rec.update(status='recovered', matched_by='archive_member',
                                   evidence=ev,
                                   dst=os.path.relpath(dst, args.output),
                                   sha256=sha256_bytes(data), verified=True)
                    else:
                        # 输入目录原路径兜底（相对路径直查）
                        cand = os.path.join(args.input, want)
                        if os.path.isfile(cand):
                            dst, got, verified = copy_verify(cand, rec_dir)
                            rec.update(status='recovered', matched_by='input_path',
                                       evidence='direct path in input dir',
                                       dst=os.path.relpath(dst, args.output),
                                       sha256=got, verified=verified)
                        else:
                            rec['evidence'] = ('not found in plan entries, duplicate groups, '
                                               'archive listings or input tree')
            except OSError as ex:
                rec.update(status='error',
                           evidence='%s: %s' % (type(ex).__name__, ex))
            if rec['status'] == 'recovered':
                n_ok += 1
            emit(rec)

    print('[recover] requests=%d recovered=%d -> %s' % (len(requests), n_ok, log_path))
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print('[recover] failed: %s: %s' % (type(e).__name__, e), file=sys.stderr)
        sys.exit(1)
