# 版本1：确定性哈希账本流水线（research-library-ledger-pipeline-v1）

可复跑、可审计、脚本驱动的端到端科研资料库整理流水线。所有确定性工作（盘点、哈希、去重、版本判定、归位、校验）都在脚本内完成，Agent 只负责读 case.json、运行脚本、填写 result.json 的叙述字段。

## 安装

整个目录即 Skill 包（≤50 个 UTF-8 文本文件，纯标准库，无密钥无二进制）。评测方将其放到 `/skills/weekly-skill` 即可；也可以任何位置独立调用：

```bash
python3 scripts/library_pipeline.py --input /input --work /app/work --output /app/output
```

## 调用方式

```bash
# 全链路（scan→plan→apply→partial-result→report→verify）
python3 scripts/library_pipeline.py [--input /input] [--work /app/work] [--output /app/output]

# 单步
python3 scripts/library_pipeline.py scan   --input /input --work /app/work
python3 scripts/library_pipeline.py plan   --input /input --work /app/work --output /app/output
python3 scripts/library_pipeline.py apply  --work /app/work --output /app/output
python3 scripts/library_pipeline.py report --input /input --work /app/work --output /app/output
python3 scripts/library_pipeline.py verify --work /app/work --output /app/output

# result.json 生命周期
python3 scripts/write_partial_result.py --input /input --work /app/work --output /app/output
python3 scripts/finalize_result.py      --input /input --work /app/work --output /app/output
python3 scripts/validate_result.py      --input /input --output /app/output   # 退出码 0=通过
```

## 输入 / 输出

**输入**：`--input`（默认 `/input`）：含 case.json、task.md 与乱序科研资料库。
**工作区**：`--work`（默认 `/app/work`）：inventory.jsonl 账本、plan.json、extracted/（安全展开的压缩包成员）、scan_summary.json。
**输出**：`--output`（默认 `/app/output`）：library/ 组织树、manifest.json/csv、duplicates.json、versions.json、operation_log.jsonl、verify_report.json、inventory.jsonl 与 plan.json 审计副本、README.md、result.json。

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

合成 fixture（中文名、改名副本、两版本 txt、管理备注 CSV、坏 zip、空目录、深目录、好 zip）后真实运行：

```bash
FIX=/tmp/fixture_v1 && rm -rf $FIX /tmp/w1 /tmp/o1 && mkdir -p "$FIX/空目录" "$FIX/深/层/级/a/b/c"
printf '实验数据\n1,2,3\n' > "$FIX/数据.csv"
printf '实验数据\n1,2,3\n' > "$FIX/数据备份-副本.csv"          # 内容相同的改名副本
printf '报告 v1 内容：引言与背景介绍。\n' > "$FIX/项目A_张三_2023_报告.txt"
printf '报告 v2 内容：引言与背景介绍，并补充了方法章节。\n' > "$FIX/项目A_张三_2023_报告_v2.txt"
printf '文件名,备注\n项目A_张三_2023_报告.txt,定稿前版本\n' > "$FIX/管理备注.csv"
head -c 64 /dev/urandom > "$FIX/坏.zip"                      # 非 zip 内容
echo '深层文件内容' > "$FIX/深/层/级/a/b/c/深层文件.md"
mkdir -p /tmp/z && echo '包内数据' > /tmp/z/包内表.csv && (cd /tmp/z && zip -q "$FIX/附件包.zip" 包内表.csv)
mkdir -p /tmp/t && echo 'tar内数据' > /tmp/t/内表.txt && (cd /tmp/t && tar -cf "$FIX/资料.tar" 内表.txt)

python3 scripts/library_pipeline.py --input $FIX --work /tmp/w1 --output /tmp/o1
```

验收要点（实际运行结果见下方"自查结果摘要"）：退出码 0；verify_report.json `verdict=PASS` 且全部 match；duplicates.json 检出 `数据备份-副本.csv` 为 `数据.csv` 的别名；versions.json 给出 `项目A_张三_2023_报告.txt` 被 v2 `superseded_by`；坏 zip 登记 archive_error 但仍入库；空目录记录于 scan_summary.json；深层文件正常入库。

**自查结果摘要（2026-11-19 本仓库实跑）**：全链路退出码 0，账本 13 条目（含 zip/tar 各 1 个合法成员）；verify `match=10, mismatch=0, missing=0, extra=0, verdict=PASS`；duplicates 检出 1 组（canonical=数据.csv，alias=数据备份-副本.csv，同一 sha256）；versions 1 条链（报告 v1 → v2，superseded_by 指向 v2；跨压缩包相似名不误连）；坏 zip 以 archive_error 登记并正常复制；空目录 1 个记入 scan_summary；`附件包.zip` / `资料.tar` 成员安全展开并入库（修复了 zip 成员名 cp437 误判为 UTF-8 的 mojibake 问题）；单步执行与 scan 重跑均幂等；result.json 经 write_partial → agent 补述 → finalize（status=success）→ validate（退出码 0）全生命周期通过。自查中发现并修复 3 个 bug：manifest.csv 缺 type/notes 的 evidence 列、重复组误收单例、版本候选跨压缩包误连。
