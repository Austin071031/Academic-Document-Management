#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""kb_pack.py -- 证据打包: 一次生成每题的紧凑证据包, 最小化模型阅读轮次。

设计(效率增益方向):
  - 每题输出一个 ≤ max_chars 的纯文本块: 去重后的 top 命中段落 + 坐标头
  - 所有题合并为一个文件, Agent 一次 read 即可完成全部命中段落过目
  - 同时输出 token/请求预算报告, 支撑"效率增益可验证性"

用法:
  python3 kb_pack.py --work /app/work [--max-chars-per-q 6000]
输出: <work>/evidence_pack.txt  <work>/pack_report.json
"""
import argparse
import json
import os
import sys
import time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", default="/app/work")
    ap.add_argument("--max-chars-per-q", type=int, default=6000)
    args = ap.parse_args()
    W = args.work

    hits_path = os.path.join(W, "hits.json")
    if not os.path.isfile(hits_path):
        raise SystemExit("hits.json 不存在, 先运行 kb_search.py --questions")
    with open(hits_path, encoding="utf-8") as f:
        hits = json.load(f).get("questions") or {}

    blocks, report = [], {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                          "tool": "kb_pack.py", "questions": {}}
    total_chars = 0
    for qid, q in hits.items():
        seen, picked, chars = set(), [], 0
        for h in q.get("hits") or []:
            key = (h["path"], h.get("page"), h.get("para_index"))
            if key in seen:
                continue
            seen.add(key)
            t = h["text"].strip()
            if chars + len(t) > args.max_chars_per_q:
                break
            picked.append(h)
            chars += len(t)
        head = "==== 问题 %s: %s\n" % (qid, q.get("query"))
        body = "\n\n".join(
            "[H%d] %s p%s ¶%s anchor=%s score=%.2f\n%s"
            % (i + 1, h["path"], h.get("page"), h.get("para_index"),
               h["anchor_id"], h["score"], h["text"].strip())
            for i, h in enumerate(picked))
        blocks.append(head + body)
        report["questions"][qid] = {"hits_packed": len(picked), "chars": chars}
        total_chars += chars

    pack = "\n\n".join(blocks) + "\n"
    with open(os.path.join(W, "evidence_pack.txt"), "w", encoding="utf-8") as f:
        f.write(pack)
    report["total_chars"] = total_chars
    report["estimated_read_calls"] = 1
    with open(os.path.join(W, "pack_report.json"), "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=1)
    sys.stdout.write("# 证据包完成: %d questions, %d chars -> evidence_pack.txt (一次读取)\n"
                     % (len(hits), total_chars))


if __name__ == "__main__":
    main()
