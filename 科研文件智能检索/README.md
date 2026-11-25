# 科研文件智能检索 — Skill 系列（玻尔产品周赛第四期）

围绕"文件已在库中，如何被准确找到、定位到章节、按条件筛出并给出可回链证据"
这一课题开发的 5 个截然不同方向的 Skill。每个版本都是一个**完整可运行**的检索
流水线（盘点→提取→切分→检索→校验→报告，输出严格镜像案例 `output_contract`），
并各自拥有一种旗舰能力。所有脚本仅用 Python 标准库，按平台运行契约设计
（输入 `/input/case.json`+`task.md`，工作 `/app/work`，输出 `/app/output`）。

| 版本 | 方向 | 一句话差异 | 旗舰脚本 | 平台得分（attempt） |
|---|---|---|---|---|
| [版本1-证据锚点引擎](版本1-证据锚点引擎/) | 章节级定位 | 印刷页↔物理页偏移校正、双栏重排、跨页题注续接、逐字回链校验 | `pagefix.py` | 68.0（[89362](https://play.bohrium.com/attempt/89362)，final） |
| [版本2-版本谱系图谱](版本2-版本谱系图谱/) | 版本关系 | 哈希去重+相似度版本链，副本不作独立证据，检索版本感知 | `lineage.py` | **68.6667**（[89366](https://play.bohrium.com/attempt/89366)，final） |
| [版本3-谓词约束过滤](版本3-谓词约束过滤/) | 硬约束执行 | 任务条件编译为强类型谓词，逐谓词审计，不满足如实报告绝不放宽 | `constraints.py` | 67.6667（[89367](https://play.bohrium.com/attempt/89367)，final） |
| [版本4-语义对齐检索](版本4-语义对齐检索/) | 概念级检索 | 中英/同义/缩写对照词表+自动缩写抽取，查询双向展开的概念索引 | `concepts.py` + `aliases.txt` | pending（[89373](https://play.bohrium.com/attempt/89373)，平台评测器报错未出分） |
| [版本5-自校验审计工作流](版本5-自校验审计工作流/) | 可复核交付 | 交付前五道机器 gate、运行日记、输出哈希清单、复跑指引 | `audit.py` | pending（[89374](https://play.bohrium.com/attempt/89374)，平台评测器报错未出分） |

各版本目录内 `SUBMISSION.md` 记录对应 attempt 的提交时间、bundle 哈希、评测状态、
本地验证基线与迭代记录（更新于 2026-11-25 查分）。

## 共享设计

- **证据锚点 schema**：file_path / sha256 / version / section_path / page /
  printed_page / paragraph_id / quote——每条结论可逐字复核；
- **诚实状态机**：失败分类学（no_permission、no_text_layer_ocr_unavailable 等）
  统一入 failures，带失败的 run 不得标 success；
- **输出契约**：`report.py` 读取 case.json 的 output_contract 逐字段镜像，
  先骨架落盘、模型补答案、finalize 校验、（v5）audit 把门；
- **预算纪律**：64 次模型请求/900 秒内可完成——重活全脚本化，模型只做阅读与汇总。

## 运行（任意版本）

```bash
SKILL=<本目录>/版本X/scripts
python3 $SKILL/inventory.py --input-root /input --work-dir /app/work
python3 $SKILL/extract.py   --input-root /input --work-dir /app/work
python3 $SKILL/segment.py   --work-dir /app/work
python3 $SKILL/retrieve.py  --work-dir /app/work --query "<核心问题>"
python3 $SKILL/verify.py    --work-dir /app/work
python3 $SKILL/report.py --skeleton  --input-root /input --work-dir /app/work --output-dir /app/output
# 补 answer/status 后
python3 $SKILL/report.py --finalize --input-root /input --work-dir /app/work --output-dir /app/output
```

各版本额外的旗舰步骤见其 SKILL.md 第 4 节。每个版本目录含 SKILL.md、README.md、
scripts/、examples/（合成演示，标注为示例）与 GITHUB_URL.txt。
