# 复跑核对命令（v2.3.0）

以下命令用于对一次 pipeline 运行结果做独立复跑核对。假设：
`IN=/input`、`OUT=/app/output`、`CASE_ID` 为 case.json 中的 case_id。

## 1. 全流程重跑（幂等）

```bash
python3 scripts/archive_pipeline.py --input "$IN" --work /app/work --output "$OUT"
# 退出码 0 = status complete；recovery/QA 失败只记账不影响退出码
```

## 2. 归档校验（verify_archive.py）

```bash
python3 scripts/verify_archive.py --input "$IN" --output "$OUT"
# 读 $OUT/verify_report.json：status=ok 且 counts.match == MANIFEST.json file_count
```

## 3. 中文检索（query_index.py）

```bash
python3 scripts/query_index.py \
    --db "$OUT/library/index/library_index.db" --q "中文关键词"
# 输出 JSON：hits[].path + evidence[].line(1 起行号) + text
```

## 4. 检索问答（answer_questions.py）

```bash
python3 scripts/answer_questions.py --input "$IN" --output "$OUT"
# 读 $OUT/search_results.json：每条 {question, answer, hits, evidence_complete, no_evidence_reason}
# 读 $OUT/query_log.jsonl：每行 {query, elapsed_ms, hit_files, hit_snippets}
```

## 5. 恢复 / 索引操作（recovery_ops.py）

```bash
# 按 case.json 的 recovery 任务执行（字符串/对象形态均可）
python3 scripts/recovery_ops.py --input "$IN" --output "$OUT"

# 仅重建索引（FTS5 bigram；无 FTS5 退化 LIKE 并在 meta 登记 degraded）
python3 scripts/recovery_ops.py --output "$OUT" --rebuild-index

# 恢复指定目标：文件名 / 别名 / sha256 前缀（≥8 位 hex）
python3 scripts/recovery_ops.py --input "$IN" --output "$OUT" \
    --restore "实验记录_v1.txt" --restore "a1b2c3d4"

# 核对：$OUT/recovery_log.jsonl 每条含
#   op(restore/rebuild_index)/target/source_basis/source_path/result/
#   sha256_expected/sha256_actual/verified
# 恢复文件落在 library/_restored/（冲突自动 __dupN，不覆盖）；
# 恢复成功会联动重建索引，随后 query_index.py 即可检索到恢复内容
```

## 6. 提交契约自检（preflight_check.py）

```bash
python3 scripts/preflight_check.py
# 读 preflight_report.json：pass=true 且 violations 为空
# （frontmatter description ≤900B、≤50 文件、单文件 ≤500KB、
#   总 ≤2MB、全 UTF-8、无符号链接）
```
