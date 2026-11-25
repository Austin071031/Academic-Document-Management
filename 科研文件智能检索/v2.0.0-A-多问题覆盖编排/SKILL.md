---
name: research-doc-multi-question-coverage
description: 科研文件智能检索 v2.0.0-A——多问题覆盖编排。当案例含多个检索问题（case.json 的 questions/searches/queries 或 task.md 的编号问句）且要求逐问回答、逐问给出可核验证据时使用。父辈：版本谱系图谱（平台 68.67 分）；本迭代主攻任务完成度与结果完整性。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 多问题覆盖编排（v2.0.0-A）

**父辈版本**：版本谱系图谱 v1.0.0（attempt 89366，68.6667 分）。
**本迭代唯一主攻**：评审反馈"更完整"→ 案例是多问题结构，单查询流程覆盖面不足。
`orchestrate.py` 自动解析全部问题、逐问检索+机器校验、生成覆盖矩阵与完整性自评。

## 1. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`、questions/constraints）与 `/input/task.md` |
| 工作目录 | `/app/work`；最终输出 `/app/output`（result.json 含 output_contract 全部字段 + case_id） |
| 预算 | 64 次模型请求 / 900 秒——问题发现、逐问检索、校验全部脚本化；模型只写 answer |

第一步读 case.json/task.md；result.json 原样保留 output_contract 字段名与 case_id。

## 2. 定位 Skill 资源

```bash
SKILL=/skills/weekly-skill
[ -f "$SKILL/SKILL.md" ] || SKILL=$(dirname "$(find /skills /app/submission -maxdepth 3 -name SKILL.md 2>/dev/null | head -1)")
```

## 3. 标准工作流

```bash
W=/app/work; O=/app/output; mkdir -p "$W" "$O"
python3 $SKILL/scripts/inventory.py --input-root /input --work-dir $W
python3 $SKILL/scripts/extract.py   --input-root /input --work-dir $W
python3 $SKILL/scripts/segment.py   --work-dir $W
python3 $SKILL/scripts/lineage.py   --work-dir $W     # 父辈能力：版本谱系
EXCL=$(python3 -c "import json;print(json.dumps(json.load(open('$W/lineage.json'))['exclude_sha256']))")
# 步骤3.1 【旗舰】多问题编排：解析全部问题→逐问检索→统一校验→覆盖矩阵
python3 $SKILL/scripts/orchestrate.py --input-root /input --work-dir $W --topk 5 \
    --filter <(echo "{\"exclude_sha256\": $EXCL}")
# 覆盖自评<1.0 时：对 unanswered 的问题补充检索（换措辞/别名），再重跑 orchestrate
python3 $SKILL/scripts/verify.py --work-dir $W
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# ——按 coverage.json 逐问撰写 answer（每问独立小节），补 status 后——
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
```

## 4. 覆盖纪律（本迭代核心，必须遵守）

1. `coverage.json.questions[]` 是逐问台账：`status` ∈ answered / candidates_only /
   unanswered；`completeness_self_score` 是已校验回答占比。
2. answer 必须**逐问成节**（每问一节：结论 + 证据引用）；candidates_only 的问题
   必须说明"候选未通过逐字校验"的原因；unanswered 必须给 empty_reason。
3. 自评分 <1.0 时先补救（同义词/缩写/换语序重跑该问），补救后仍无的如实保留；
   **禁止**为了自评分好看而删除问题。
4. 每问的 `constraints`（case.json 里问题自带 filters）作为该问硬过滤执行，
   并在 answer 该节开头说明"条件 X、Y 下命中 N 处"。
5. 证据沿用父辈规范：file_path/sha256/version/section_path/page/printed_page/quote，
   全部经 verify.py 逐字校验；副本不作独立证据（version_role 标注）。

## 5. 异常处置决策表

| 情况 | 处置 |
|---|---|
| case/task 解析不出问题 | orchestrate 输出 note；由模型从 task.md 提炼问题手动跑 retrieve，并在 coverage 说明 |
| 某问过滤后零文档 | 该问 status=unanswered，诊断是年份/类型/编号哪一维排除 |
| 问题间互相重叠 | 证据可复用（qid 标注），但每问仍独立成节回答 |
| 无权限/扫描件/损坏 | 记 failures，status≠success |
| 无 output_contract | 默认字段集 + uncertainty 说明 |

## 6. result.json 组装规则

- skeleton 预填 files/evidence/versions/failures/filters；answer 逐问撰写后 finalize。
- status：全部问题 answered 且无失败 → success；部分 answered 或有失败 → partial；
  全部 unanswered → failed。
- finalize 校验契约完备 + manifest 哈希 + changes 变更记录。

## 7. 最小调用示例（示意输出，非正式案例结果）

```bash
# case.json: questions=[{question:"缓冲液配方写在哪版哪节？",filters:{doc_type:["pdf"]}},
#                       {question:"PBS stock 保存条件？",filters:{doc_type:["docx"]}}]
python3 $SKILL/scripts/orchestrate.py --input-root /input --work-dir /app/work
# → questions=2 answered=2 score=1.0
# → coverage.json: q01 answered(verified=5) / q02 answered(verified=1)
```

## 8. 不适用情况

联网查新、综述写作、权限建设；问题语义改写超出字面/别名对齐的，由模型在
answer 中说明映射关系并标注不确定性。
