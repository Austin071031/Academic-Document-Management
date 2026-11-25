# 复跑核对命令清单（reproduce）

他人在任何一台只有 Python 3 标准库的机器上，按以下顺序逐条执行即可独立核对本 Skill 的
全部交付物。假定 Skill 目录为 `$SKILL`（平台评测时为 `/skills/weekly-skill`），
案例输入在 `/input`（含 case.json、task.md 与乱序资料库）。

## 1. 全链路（一次跑完，含 v2 自动衔接 recover/qa）

```bash
python3 $SKILL/scripts/write_partial_result.py --input /input --work /app/work --output /app/output
python3 $SKILL/scripts/library_pipeline.py    --input /input --work /app/work --output /app/output
# 期望：退出码 0；末尾打印 [verify] ... (PASS)；
# 若 case.json 含 recovery 类任务/searches/questions，会额外打印 [chain] extras: [...]
```

## 2. 案例组件单独复跑（幂等，可反复执行）

```bash
# 恢复 case.json 中全部 recovery 任务（写 /app/output/recovery_log.jsonl）
python3 $SKILL/scripts/recover.py --input /input --work /app/work --output /app/output --from-case
# 恢复单个目标（文件名 / sha256 前缀 / 别名），可指定 library/ 内落点
python3 $SKILL/scripts/recover.py --input /input --work /app/work --output /app/output \
    --target "关键词或sha256前缀" --restore-to "项目/年份/类型/文件名"
# 重建 manifest + 检索索引 + verify
python3 $SKILL/scripts/recover.py --input /input --work /app/work --output /app/output --rebuild-index
# 检索问答（写 /app/output/search_results.json，索引在 /app/work/search_index.json）
python3 $SKILL/scripts/qa.py --input /input --work /app/work --output /app/output
python3 $SKILL/scripts/qa.py --work /app/work --output /app/output --query "任意关键词"
```

## 3. 校验与定稿

```bash
python3 $SKILL/scripts/library_pipeline.py verify --input /input --work /app/work --output /app/output
python3 $SKILL/scripts/finalize_result.py      --input /input --work /app/work --output /app/output
python3 $SKILL/scripts/validate_result.py      --input /input --output /app/output   # 退出码必须 0
```

## 4. 交付物独立抽查（不依赖本 Skill 任何代码）

```bash
# 4a. library/ 中某文件的哈希应等于 manifest.json / recovery_log.jsonl 中的 sha256
sha256sum "/app/output/library/<项目>/<年份>/<类型>/<文件名>"
# 4b. 每条恢复记录应能对应：来源(source)、依据(basis)、落点(restored_to)、校验(sha256_expected==sha256_actual)
python3 -c "import json;[print(json.loads(l)['status'],json.loads(l).get('target'),json.loads(l).get('restored_to')) for l in open('/app/output/recovery_log.jsonl',encoding='utf-8')]"
# 4c. 检索命中可用 grep 复核（行号应对得上 search_results.json 的 line 字段）
grep -rn "关键词" /app/output/library/
```

## 5. Skill 包自身提交契约自检

```bash
python3 $SKILL/scripts/preflight_check.py            # 检查 $SKILL 自身，退出码 0=PASS
# 产物：$SKILL/preflight_report.json（frontmatter/description 字节数、文件数、大小、UTF-8、符号链接、密钥扫描）
```

## 6. 本地合成 fixture 自查

见 README.md「自查方法」：一条命令块建 fixture（中文名、改名副本、双版本、管理备注 CSV、
坏 zip、空目录、5 层深目录、含 searches+recovery 的 case.json），跑全链路即可复现
README 中的实测摘要。
