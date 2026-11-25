# v2.0.0：案例组件补全（research-library-ledger-pipeline-v2-0）

基座 = 版本1 确定性哈希账本流水线（盘点、哈希、去重、版本判定、归位、校验全部保留、行为不变）。v2 定向增量：补齐基座缺失的两个案例组件——**检索问答**（qa.py：倒排索引 + 行号片段证据）与**恢复/重建索引**（recover.py：按文件名/哈希/别名从账本、压缩包展开或源备份恢复，sha256 校验记账）。全链路末尾按 case.json 自动衔接，幂等，失败记账不崩溃。

可复跑、可审计、脚本驱动的端到端科研资料库整理流水线。所有确定性工作（盘点、哈希、去重、版本判定、归位、校验、恢复、检索）都在脚本内完成，Agent 只负责读 case.json、运行脚本、填写 result.json 的叙述字段。

## 安装

整个目录即 Skill 包（≤50 个 UTF-8 文本文件，纯标准库，无密钥无二进制）。评测方将其放到 `/skills/weekly-skill` 即可；也可以任何位置独立调用：

```bash
python3 scripts/library_pipeline.py --input /input --work /app/work --output /app/output
```

## 调用方式

```bash
# 全链路（scan→plan→apply→partial-result→report→verify→[自动衔接 recover/qa]→re-verify）
python3 scripts/library_pipeline.py [--input /input] [--work /app/work] [--output /app/output]

# 单步
python3 scripts/library_pipeline.py scan   --input /input --work /app/work
python3 scripts/library_pipeline.py plan   --input /input --work /app/work --output /app/output
python3 scripts/library_pipeline.py apply  --work /app/work --output /app/output
python3 scripts/library_pipeline.py report --input /input --work /app/work --output /app/output
python3 scripts/library_pipeline.py verify --work /app/work --output /app/output

# v2 案例组件（全链路末尾已按 case.json 自动衔接；以下为手动/补充用法）
python3 scripts/recover.py --input /input --work /app/work --output /app/output --from-case
python3 scripts/recover.py --input /input --work /app/work --output /app/output \
    --target "文件名或sha256前缀" [--restore-to "library/内落点"]
python3 scripts/recover.py --input /input --work /app/work --output /app/output --rebuild-index
python3 scripts/qa.py      --input /input --work /app/work --output /app/output [--query "关键词"]

# result.json 生命周期
python3 scripts/write_partial_result.py --input /input --work /app/work --output /app/output
python3 scripts/finalize_result.py      --input /input --work /app/work --output /app/output
python3 scripts/validate_result.py      --input /input --output /app/output   # 退出码 0=通过

# Skill 包提交契约自检（frontmatter/文件数/大小/UTF-8/符号链接/密钥扫描）
python3 scripts/preflight_check.py                                          # 退出码 0=PASS
```

## 输入 / 输出

**输入**：`--input`（默认 `/input`）：含 case.json、task.md 与乱序科研资料库。
**工作区**：`--work`（默认 `/app/work`）：inventory.jsonl 账本、plan.json、extracted/（安全展开的压缩包成员）、scan_summary.json、search_index.json（v2）。
**输出**：`--output`（默认 `/app/output`）：library/ 组织树、manifest.json/csv、duplicates.json、versions.json、operation_log.jsonl、verify_report.json、inventory.jsonl 与 plan.json 审计副本、README.md、result.json，以及 v2 新增的 search_results.json（检索问答证据）与 recovery_log.jsonl（恢复/重建索引账本）。

## 方法

1. **scan**：递归盘点（跳过顶层 case.json/task.md，登记为 metadata）；每文件 1 MiB 分块流式 sha256；逐行写入 inventory.jsonl 账本 `{path,size,mtime,sha256,readable,error,kind,extracted_from,depth}`；zip/tar 用 stdlib 安全展开（拒绝绝对路径与 `..` 穿越），成员登记为 archive_member。
2. **plan**：纯 dry-run。解析文件名模式（`项目号_作者_年份_类型.ext`）、伴随 CSV/TSV join、管理备注（文件名含 备注|说明|管理|notes|readme 的 md/txt/csv 中 key:value 行）；每个元数据字段带 `{field,value,source,evidence}`，抽不到为 null+原因。内容 sha256 相同 → 精确重复组（mtime 最旧者为 canonical）；零字节文件不参与去重。版本链按 difflib 归一化 stem 相似度（≥0.75，与文件名原始形态无关）聚类 + mtime 升序排序，给出 `superseded_by`。目标路径 `项目/年份/数据类型/`（压缩包成员多一级压缩包名目录），冲突确定性分配 `__dupN`。
3. **apply**：`shutil.copy2` 复制（不移动，保留源证据），绝不覆盖；每次操作写 operation_log.jsonl（before/after/sha256/action/time/status）。
4. **report**：manifest.json + manifest.csv（BOM，Excel 友好；每字段附 source/evidence 列）、duplicates.json、versions.json、README.md，并把账本/方案复制为审计副本。
5. **verify**：对 library 重哈希与 plan 比对，输出每文件 match/mismatch/missing/extra 与 totals、verdict（PASS/FAIL）。

## 限制

- 版本判定不解析语义内容；完全改名且 stem 相似度 <0.75 的历史版本会漏判（写入 versions.json 方法与 result.uncertainty）。
- 伴随表 join 为 stem 精确/子串匹配；结构自由的表格可能 join 不上（字段保持 null+原因）。
- 巨型单文件（>500MB）会完整哈希与复制，耗时随 IO 线性增长。
- 单次 scan 全量重生成账本（幂等优先）；日志类文件（inventory/operation_log）行内不可变。

## 自查方法

合成 fixture（中文名、改名副本、两版本 txt、管理备注 CSV、坏 zip、空目录、5 层深目录、含 output_contract 4 字段 + searches + recovery 任务的 case.json）后真实运行：

```bash
FIX=/tmp/fixture_v2 && rm -rf $FIX /tmp/w2 /tmp/o2 && mkdir -p "$FIX/空目录" "$FIX/深/层/级/a/b"
printf '实验数据\n1,2,3\n' > "$FIX/数据.csv"
printf '实验数据\n1,2,3\n' > "$FIX/数据备份-副本.csv"          # 内容相同的改名副本（恢复目标）
printf '报告 v1 内容：引言与背景介绍。\n' > "$FIX/项目A_张三_2023_报告.txt"
printf '报告 v2 内容：引言与背景介绍，并补充了方法章节。本文包含某关键词以便检索。\n' > "$FIX/项目A_张三_2023_报告_v2.txt"
printf '文件名,备注\n项目A_张三_2023_报告.txt,定稿前版本\n' > "$FIX/管理备注.csv"
head -c 64 /dev/urandom > "$FIX/坏.zip"                      # 非 zip 内容
echo '深层文件内容' > "$FIX/深/层/级/a/b/深层文件.md"           # 5 层深目录
cat > "$FIX/case.json" <<'EOF'
{
  "case_id": "fixture-v2-selfcheck",
  "output_contract": ["summary", "library_manifest", "search_answers", "recovery_results"],
  "searches": ["某关键词", "不存在的关键词xyz"],
  "recovery": [{"target": "数据备份-副本.csv", "restore_to": "recovered/数据备份-副本.csv"}]
}
EOF
echo '# task' > "$FIX/task.md"

python3 scripts/library_pipeline.py --input $FIX --work /tmp/w2 --output /tmp/o2   # 退出码应 0
python3 scripts/finalize_result.py  --input $FIX --work /tmp/w2 --output /tmp/o2
python3 scripts/validate_result.py  --input $FIX --output /tmp/o2                  # 退出码应 0
python3 scripts/preflight_check.py                                               # 退出码应 0
```

验收要点：退出码 0；verify_report.json `verdict=PASS` 且全部 match（恢复新增文件只计 extra 不破坏 PASS）；search_results.json 中 `某关键词` 命中带 文件:行号+片段 证据、`不存在的关键词xyz` 诚实 no_evidence；recovery_log.jsonl 有 recovered 记录且 sha256_expected==sha256_actual；result.json 含 case_id + 4 个契约字段；preflight PASS。

**自查结果摘要（2026-11-25 本仓库实跑）**：
- 全链路退出码 0；`[scan] entries=9 readable=9`；verify 初跑 `match=6 mismatch=0 missing=0 extra=0 (PASS)`，自动衔接后重跑 `match=6 extra=1 (PASS)`（extra 即恢复进 library/ 的别名文件）。
- 自动衔接 `[chain] extras: [('recover', 0), ('qa', 0)]`：recover 把别名 `数据备份-副本.csv` 从源备份恢复到 `library/recovered/数据备份-副本.csv`，日志记 `basis=exact basename match, source_kind=source_backup, sha256_expected==sha256_actual, status=recovered`；qa 索引 6 个文本文件 67 个 term（含文件名维度），`某关键词 → answered`（命中 `项目A/2023/文档/项目A_张三_2023_报告_v2.txt:1` 含原文片段），`不存在的关键词xyz → no_evidence`（附缺口原因）。
- result.json 生命周期：partial（4 个契约字段占位）→ finalize（status=success，verify=PASS）→ validate `OK: case_id=fixture-v2-selfcheck fields=4`。
- 幂等与边界实跑：全链路重跑退出码 0、恢复目标记 `already_present` 不覆盖；`--target <sha256前12位>` 按内容寻址恢复成功；不存在目标记 `not_found`（standalone 退出码 1，链路内不崩溃）；`--rebuild-index` 三步（report/qa --index-only/verify）全部记 `rebuilt`；v1 风格 case.json（无 searches/recovery）不触发衔接，输出与基座一致。
- preflight_check：`verdict=PASS files=22（含 preflight_report.json 自身）desc=545B problems=0`。
- 自查中修复 1 个 v2 新 bug：qa 只索引正文行、按文件名的查询必然 no_evidence → 补"文件名维度"（路径入索引，命中记 `match=filename, line=0`）。
