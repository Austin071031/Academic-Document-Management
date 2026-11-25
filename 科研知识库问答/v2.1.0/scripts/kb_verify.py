#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_verify.py -- 证据逐条核验与自动修齐坐标。

对 answers.json 中每条 evidence:
  1. path 必须存在于 inventory.json(附 sha256 前 16 位)
  2. exact_quote 必须在抽取文本中逐字出现(空白归一后); 轻微空白差异自动修齐为
     原文精确子串并回填 exact_quote 与 char_start/char_end
  3. page/para_index 自动按锚点(index.jsonl)回填或校正
  4. 无法核验的证据标记 verified=false, 答案写作阶段必须删除或换证据,
     不允许携带 verified=false 的证据提交

输出: <work>/answers_verified.json(修齐后的 answers) + <work>/verify_report.json

用法:
  python3 kb_verify.py --work /app/work [--answers /app/work/answers.json]
"""
import argparse
import json
import os
import re
import sys
import time

NORM = lambda s: re.sub(r"\s+", " ", s or "").strip()


def load(p):
    if os.path.isfile(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def locate(raw, quote):
    """在原文 raw 中定位 quote(空白归一匹配), 返回 (精确子串, start, end) 或 None。"""
    if not quote:
        return None
    i = raw.find(quote)
    if i >= 0:
        return quote, i, i + len(quote)
    nq = NORM(quote)
    if len(nq) < 8:
        return None
    # 逐字符扫描: 建立归一化索引
    norm_map = []  # norm 字符位置 -> raw 位置
    norm_chars = []
    prev_ws = True
    for i, ch in enumerate(raw):
        if ch.isspace():
            if not prev_ws:
                norm_chars.append(" ")
                norm_map.append(i)
            prev_ws = True
        else:
            norm_chars.append(ch)
            norm_map.append(i)
            prev_ws = False
    norm = "".join(norm_chars).strip()
    j = norm.find(nq)
    if j < 0:
        return None
    start = norm_map[j]
    end = norm_map[min(j + len(nq) - 1, len(norm_map) - 1)] + 1
    return raw[start:end], start, end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--answers", default=None)
    args = ap.parse_args()
    W = args.work
    ans_path = args.answers or os.path.join(W, "answers.json")
    answers = load(ans_path)
    inv = load(os.path.join(W, "inventory.json"))
    rep = load(os.path.join(W, "extract_report.json"))
    index = {}
    ip = os.path.join(W, "index.jsonl")
    if os.path.isfile(ip):
        with open(ip, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                index.setdefault(r["path"], []).append(r)

    sha_by_path = {f.get("path"): (f.get("hash") or "")[:16] for f in inv.get("files", [])}
    fid_by_path = {e["path"]: e["file_id"] for e in rep.get("files", [])}
    texts = {}

    def text_of(path):
        if path not in texts:
            tp = os.path.join(W, "text", (fid_by_path.get(path) or "") + ".txt")
            texts[path] = open(tp, encoding="utf-8").read() if os.path.isfile(tp) else None
        return texts[path]

    report = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "tool": "kb_verify.py", "evidence": []}
    n_ok = n_fixed = n_bad = 0

    for qid, q in (answers.get("answers") or {}).items():
        for e in q.get("evidence") or []:
            ent = {"question": qid, "id": e.get("id"), "path": e.get("path")}
            report["evidence"].append(ent)
            p = e.get("path")
            if p not in sha_by_path:
                e["verified"] = False
                ent.update(verified=False, reason="path 不在 inventory")
                n_bad += 1
                continue
            e["sha256_16"] = sha_by_path[p]
            t = text_of(p)
            if t is None:
                e["verified"] = False
                ent.update(verified=False, reason="无抽取文本")
                n_bad += 1
                continue
            r = locate(t, e.get("exact_quote") or "")
            if r is None:
                e["verified"] = False
                ent.update(verified=False, reason="exact_quote 非原文子串")
                n_bad += 1
                continue
            sub, cs, ce = r
            changed = (sub != e.get("exact_quote") or e.get("char_start") != cs)
            e["exact_quote"] = sub
            e["char_start"], e["char_end"] = cs, ce
            # 回填页码/段落
            page = t[:cs].count("\f") + 1
            e["page"] = page
            anchors = index.get(p) or []
            hit = next((a for a in anchors
                        if a.get("char_start", 0) <= cs < a.get("char_end", 0)), None)
            if hit:
                e["para_index"] = hit["para_index"]
                e["anchor_id"] = hit["anchor_id"]
            e["verified"] = True
            ent.update(verified=True, fixed=bool(changed), page=page)
            n_fixed += 1 if changed else 0
            n_ok += 1 if not changed else 0

    report["counts"] = {"verified_as_is": n_ok, "verified_fixed": n_fixed,
                        "unverified": n_bad}
    out_ans = os.path.join(W, "answers_verified.json")
    with open(out_ans, "w", encoding="utf-8") as f:
        json.dump(answers, f, ensure_ascii=False, indent=1)
    with open(os.path.join(W, "verify_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    sys.stdout.write("# 证据核验: 原样通过 %d, 自动修齐 %d, 未通过 %d -> %s\n"
                     % (n_ok, n_fixed, n_bad, out_ans))
    if n_bad:
        sys.stdout.write("# 未通过的证据已标记 verified=false, 提交前必须删除或替换!\n")
        sys.exit(1)


if __name__ == "__main__":
    main()
