#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""rule_engine.py — 声明式模板 + 规则引擎（纯标准库）。

职责：
  * load_rules()            读取布局模板配置
  * normalize_component()   NFKC + 非法字符替换 + 空白折叠 + 截断（UTF-8 安全）
  * normalize_filename()    文件名级规范化
  * derive_fields()         从元数据/文件名推导模板字段，带字段字典校验
  * compute_target()        逐文件路由：按优先级第一条匹配生效 + 默认兜底
  * version_key()           版本/副本别名识别（内容哈希判重由 plan.py 完成）
  * unique_path()           目标冲突 __dupN，绝不覆盖
"""
import json
import os
import re
import unicodedata

ILLEGAL_CHARS = '<>:"/\\|?*'
FIELD_RE = re.compile(r'\{([a-zA-Z_][a-zA-Z0-9_]*)\}')
YEAR_RE = re.compile(r'(19|20)\d{2}')

# 版本/改名副本 token：v2 / r3 / 2024 / 副本 / copy / backup / bak / final / 修订 …
VER_RE = re.compile(
    r'(?i)[ _\-.]?('
    r'v\d+|r\d+|ver\d+|rev\d+|版本\d*|第\d+版|'
    r'copy\d*|副本\d*|复件\d*|'
    r'backup\d*|bak\d*|'
    r'final\d*|修订\d*|改\d*|'
    r'old|new|原始|旧版|新版|最新'
    r')$'
)


def load_rules(path):
    with open(path, 'r', encoding='utf-8') as f:
        cfg = json.load(f)
    cfg.setdefault('template', '{project}/{year}/{type}/{name}')
    cfg.setdefault('fields', {})
    cfg.setdefault('ext_type_map', {})
    cfg.setdefault('route_rules', [])
    cfg.setdefault('default_rule', {
        'id': 'DEFAULT',
        'reason': '默认兜底规则',
        'target_template': cfg['template'],
    })
    cfg.setdefault('naming', {})
    cfg.setdefault('filename_patterns', [])
    for r in cfg.get('route_rules', []):
        r.setdefault('priority', 0)
        r.setdefault('when', {})
        r.setdefault('target_template', cfg['template'])
    # 稳定排序：priority 降序，同优先级按 id 字典序保证确定性
    cfg['route_rules'].sort(key=lambda r: (-r['priority'], str(r['id'])))
    return cfg


# ---------------------------------------------------------------- 命名规范化

def normalize_component(s, max_len=80):
    """单路径分量规范化：NFKC、非法字符→'_'、空白折叠、首尾点空格裁剪、截断。"""
    if s is None:
        s = ''
    s = unicodedata.normalize('NFKC', str(s))
    s = ''.join('_' if c in ILLEGAL_CHARS else c for c in s)
    s = re.sub(r'\s+', ' ', s).strip(' .')
    if not s:
        s = '_'
    if len(s) > max_len:
        s = s[:max_len].rstrip(' ._') or '_'
    return s


def normalize_filename(name, naming=None):
    """文件名规范化（保留扩展名），同时规避 Windows 保留名。"""
    naming = naming or {}
    maxc = int(naming.get('max_component_chars', 80))
    reserved = {r.upper() for r in naming.get('reserved_windows_names', [])}
    stem, dot, ext = name.rpartition('.')
    if not dot:
        stem, ext = name, ''
    stem = normalize_component(stem, maxc)
    if stem.upper() in reserved:
        stem = '_' + stem
    if ext:
        ext = normalize_component(ext, 16).lstrip('_') or 'bin'
        return '%s.%s' % (stem, ext)
    return stem


def version_key(stem):
    """返回 (base, version_token)。识别改名备份副本与历史版本命名习惯。"""
    m = VER_RE.search(stem)
    if m:
        base = stem[:m.start()].rstrip(' _-.')
        return (base or stem), m.group(1)
    return stem, None


def unique_path(path, used):
    """path 冲突时追加 __dupN（N 从 2 递增），绝不覆盖既有目标。"""
    if path not in used:
        return path
    root, ext = os.path.splitext(path)
    n = 2
    while True:
        cand = '%s__dup%d%s' % (root, n, ext)
        if cand not in used:
            return cand
        n += 1


# ---------------------------------------------------------------- 字段推导

def _field_allowed(value, fcfg):
    """按字段字典校验；返回 (accepted_value, note_or_None)。"""
    if not fcfg:
        return value, None
    vals = fcfg.get('values')
    pat = fcfg.get('pattern')
    fb = fcfg.get('fallback', '_other')
    if vals and value not in vals:
        return fb, 'value %r not in field dictionary; fallback %r' % (value, fb)
    if pat and not re.match(pat, value):
        return fb, 'value %r fails pattern %r; fallback %r' % (value, pat, fb)
    return value, None


def derive_fields(filename, ext, metadata, cfg):
    """从（已合并的）元数据 + 文件名推导模板字段。

    metadata: {field: value}（来源与证据在 plan.py 侧保留）。
    返回 (values, notes)；抽不到的字段使用 fallback 并记 note，绝不猜。
    """
    fields_cfg = cfg.get('fields', {})
    ext_map = cfg.get('ext_type_map', {})
    values = {}
    notes = []

    def put(field, value, note=None):
        if value is None or str(value) == '':
            return
        fcfg = fields_cfg.get(field, {})
        acc, n = _field_allowed(str(value), fcfg)
        values[field] = acc
        for x in (note, n):
            if x:
                notes.append('%s: %s' % (field, x))

    put('project', metadata.get('project'))
    put('year', metadata.get('year'))
    put('type', metadata.get('type'))
    put('name', metadata.get('name'))

    if 'year' not in values:
        m = YEAR_RE.search(filename)
        if m:
            put('year', m.group(0), 'year extracted from filename')
    if 'type' not in values:
        put('type', ext_map.get(ext.lower(), 'other'),
            'type inferred from extension' if ext.lower() in ext_map else None)
    if 'project' not in values:
        notes.append('project: not found in any source; fallback')
    if 'year' not in values:
        notes.append('year: not found in any source; fallback')

    # 常见同义字段：模板用 {topic}/{kind} 等写法时从规范字段镜像，不猜值。
    aliases = {'topic': 'project', 'subject': 'project',
               'kind': 'type', 'category': 'type', 'doc_type': 'type',
               'date': 'year'}
    for alias, canonical in aliases.items():
        if alias not in values and canonical in values:
            values[alias] = values[canonical]
            notes.append('%s: mirrored from %s' % (alias, canonical))
    return values, notes


# ---------------------------------------------------------------- 规则匹配

def _rule_matches(rule, rec, metadata):
    """rec: {filename, ext, size, rel}; metadata: {field: value}。"""
    w = rule.get('when', {})
    if not w:
        return True
    if 'ext_in' in w:
        if rec['ext'].lower() not in set(e.lower() for e in w['ext_in']):
            return False
    if 'ext_not_in' in w:
        if rec['ext'].lower() in set(e.lower() for e in w['ext_not_in']):
            return False
    if 'name_regex' in w:
        if not re.search(w['name_regex'], rec['filename']):
            return False
    if 'rel_regex' in w:
        if not re.search(w['rel_regex'], rec['rel']):
            return False
    if 'min_size' in w and not (rec.get('size') is not None and rec['size'] >= w['min_size']):
        return False
    if 'max_size' in w and not (rec.get('size') is not None and rec['size'] <= w['max_size']):
        return False
    if 'metadata_has' in w:
        for f in w['metadata_has']:
            if f not in metadata or metadata[f] in (None, ''):
                return False
    if 'metadata' in w:
        for f, cond in w['metadata'].items():
            v = metadata.get(f)
            if isinstance(cond, dict):
                if 'regex' in cond:
                    if v is None or not re.search(cond['regex'], str(v)):
                        return False
                elif 'value' in cond:
                    if str(v) != str(cond['value']):
                        return False
            else:
                if str(v) != str(cond):
                    return False
    return True


def compute_target(rec, metadata, cfg):
    """逐文件计算目标路径。第一条匹配生效（已按 priority 排序），默认兜底。

    返回 {target, rule_id, reason, notes}；target 为相对 library 根的路径。
    """
    naming = cfg.get('naming', {})
    values, notes = derive_fields(rec['filename'], rec['ext'], metadata, cfg)
    values['name'] = normalize_filename(rec['filename'], naming)

    matched = None
    for rule in cfg.get('route_rules', []):
        if _rule_matches(rule, rec, metadata):
            matched = rule
            break
    if matched is None:
        matched = cfg['default_rule']

    tmpl = matched.get('target_template') or cfg['template']
    total_max = int(naming.get('max_total_chars', 240))

    def repl(m):
        f = m.group(1)
        if f in values:
            return values[f]
        fb = cfg.get('fields', {}).get(f, {}).get('fallback')
        notes.append('field %s missing; fallback %r' % (f, fb))
        return fb if fb is not None else '_unknown'

    rel = FIELD_RE.sub(repl, tmpl)
    parts = [normalize_component(p) for p in rel.split('/')]
    rel = '/'.join(parts)[:total_max]
    return {
        'target': rel,
        'rule_id': matched.get('id', 'DEFAULT'),
        'reason': matched.get('reason', ''),
        'notes': notes,
        'field_values': values,
    }
