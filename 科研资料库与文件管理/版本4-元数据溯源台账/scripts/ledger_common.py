#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger_common.py —— 元数据溯源台账（版本4）共享工具层。

仅 Python3 标准库。提供：
- 流式 sha256（大文件安全）
- UTF-8/GBK/UTF-16 依次尝试的编码探测（chardet 不可用时的降级策略）
- JSONL 台账读写、JSON 读写
- 文件名主干归一化（跨来源匹配用）
- 来源优先级 / 置信度口径常量
- change_log（六要素：时间/动作/对象/依据/结果/备注）
"""
import datetime
import hashlib
import json
import os
import unicodedata

CHUNK = 256 * 1024
SNIFF_BYTES = 64 * 1024  # 内容嗅探只读前 64KB

# 裁决优先级（序号越小越优先）与基准置信度；与 config/field_dictionary.json 保持一致
SOURCE_PRIORITY = ["admin_note", "companion_table", "content", "filename", "agent_inference"]
SOURCE_CONFIDENCE = {
    "admin_note": 0.95,
    "companion_table": 0.85,
    "content": 0.75,
    "filename": 0.60,
    "agent_inference": 0.50,
}
PRIORITY_RULE_STR = "admin_note > companion_table > content > filename > agent_inference"


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def sha256_file(path):
    """流式 sha256，单块 256KB，避免大文件撑爆内存。"""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(CHUNK)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def decode_bytes(data):
    """依次尝试 utf-8-sig / utf-8 / gb18030 / utf-16。

    返回 (text, encoding_used, warning_or_None)。全部失败时 utf-8+replace 并给出告警。
    """
    for enc in ("utf-8-sig", "utf-8", "gb18030", "utf-16"):
        try:
            return data.decode(enc), enc, None
        except (UnicodeDecodeError, ValueError):
            continue
    return (data.decode("utf-8", errors="replace"), "utf-8(replace)",
            "all codec attempts failed; replacement characters used")


def read_text_head(path, limit=SNIFF_BYTES):
    """读取文件前 limit 字节并探测编码，返回 (text, encoding, warning)。"""
    with open(path, "rb") as f:
        data = f.read(limit)
    return decode_bytes(data)


def jwrite(path, obj):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def jread(path, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def jlines(path):
    """逐行读 JSONL，坏行跳过不崩溃。"""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def jappend(path, records):
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def stem_of(basename):
    return os.path.splitext(basename)[0]


def norm_key(name):
    """文件名主干归一化：NFC、去扩展名、小写、去空白与常见分隔符。

    用于 伴随表行/管理备注条目 -> 实际文件 的宽松匹配。
    """
    s = unicodedata.normalize("NFC", str(name))
    s = stem_of(s).lower()
    for ch in " _-—–()（）[]【】{}.,，、'\"'":
        s = s.replace(ch, "")
    return s


def load_dictionary(work, config_path):
    """优先读 work 目录下被管线合并过 required 字段的字典副本，否则读原始配置。"""
    wk = os.path.join(work, "field_dictionary.json") if work else None
    if wk and os.path.exists(wk):
        d = jread(wk)
        if d:
            return d
    return jread(config_path, default={}) or {}


def alias_map(dictionary):
    """表头/键名 -> 规范字段名。"""
    m = {}
    for field, aliases in (dictionary.get("field_aliases") or {}).items():
        m[field.lower()] = field
        for a in aliases:
            m[str(a).lower()] = field
    return m


def log_change(work, action, obj, evidence, result, note=None):
    """六要素变更记录：时间/动作/对象/依据/结果/备注。"""
    rec = {
        "time": now_iso(),
        "action": action,
        "object": obj,
        "evidence": evidence,
        "result": result,
        "note": note,
    }
    jappend(os.path.join(work, "change_log.jsonl"), [rec])
    return rec


def candidate(file_rel, field, value, source, evidence, confidence=None):
    """构造一条字段候选记录（写入 candidates.jsonl）。"""
    if confidence is None:
        confidence = SOURCE_CONFIDENCE.get(source, 0.5)
    return {
        "file": file_rel,
        "field": field,
        "value": value,
        "source": source,
        "evidence": evidence,
        "confidence": confidence,
        "ts": now_iso(),
    }
