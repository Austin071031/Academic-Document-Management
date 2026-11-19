---
name: research-doc-concept-alignment
description: 科研文件智能检索——跨文件语义对齐。当同一概念在库中以不同措辞出现（缩写 vs 全称、中文 vs 英文、同义词、上下位词），文件名检索必然漏命中时使用。旗舰能力：术语规范化层（人工跨语言词表 + 语料缩写自动抽取）驱动的概念级索引与检索。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 语义对齐检索（版本4）

## 1. 用途与触发

科研材料里同一个概念有多种写法：正文写 "sodium dodecyl sulfate (SDS)"，
笔记写 "SDS-PAGE"，方案写 "十二烷基硫酸钠电泳"；中文记录写"缓冲液"，英文报告写
"buffer"。**按文件名或字面匹配必然漏命中**。本版本旗舰能力 `concepts.py` 构建
**术语规范化层**：

1. 人工跨语言对照表 `aliases.txt`（中英/同义/上下位，可扩充）；
2. 从语料自动抽取"缩写↔全称"对（`缩写 (全称)`、`全称（缩写）` 模式）；
3. 合并为概念映射 `concepts.json`，检索时对**查询与索引双向展开**：
   查 "缓冲液" 等价于查 {buffer, buffering solution, 缓冲体系, 缓冲溶液, …}；
4. 输出跨文件概念索引 `concept_index.json`：每个概念出现在哪些文件/章节/页。

## 2. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`）与 `/input/task.md` |
| 工作目录 | `/app/work`；最终输出 `/app/output` |
| 预算 | 64 次模型请求 / 900 秒——索引与对齐全脚本化 |

第一步读 case.json/task.md；result.json 原样保留 output_contract 字段与 case_id。

## 3. 定位 Skill 资源

```bash
SKILL=/skills/weekly-skill
[ -f "$SKILL/SKILL.md" ] || SKILL=$(dirname "$(find /skills /app/submission -maxdepth 3 -name SKILL.md 2>/dev/null | head -1)")
```

## 4. 标准工作流

```bash
W=/app/work; O=/app/output; mkdir -p "$W" "$O"
python3 $SKILL/scripts/inventory.py --input-root /input --work-dir $W
python3 $SKILL/scripts/extract.py --input-root /input --work-dir $W
python3 $SKILL/scripts/segment.py --work-dir $W
# 步骤2.7 【旗舰】概念对齐：词表+自动缩写 → concepts.json + concept_index.json
python3 $SKILL/scripts/concepts.py --work-dir $W --aliases $SKILL/scripts/aliases.txt
# 步骤3 概念级检索（查询经概念映射双向展开；中英文互命中）
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<核心问题>" \
    --concepts $W/concepts.json --topk 10
python3 $SKILL/scripts/verify.py --work-dir $W
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# 补 answer 后 finalize
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
```

核查概念覆盖：先查 `concept_index.json` 看问题核心概念在哪些文件出现过——
若核心概念 0 命中，先检查是否缺别名（可从 hits 的 matched_terms 反推补充），
再考虑 genuinely 不存在，并如实报告。

## 5. 语义对齐规则（必须遵守）

1. 概念命中必须在 answer 中说明匹配路径（如：查"缓冲液"→经别名 buffer→
   命中英文报告），让复核者理解为何不同措辞的文件被命中；
2. `matched_terms` 只代表词面对齐，**结论强度仍以 verify 逐字校验为准**；
3. 缩写自动抽取可能有误（如把单位当缩写），写入 `acronyms_used` 供复核；
4. 上下位扩展不跨概念跳跃：查"电泳"不会自动命中"western blot"的具体实验条件段，
   除非任务问的就是具体技术——保持克制的扩展比过度扩展更可信；
5. 同一概念跨文件命中多份时，按版本谱系/时间标注，不重复计数。

## 6. 词表维护

`aliases.txt` 每行 `概念 = 别名1 | 别名2 | …`，`#` 开头为注释。默认词表覆盖通用
科研术语（缓冲液/离心/电泳/质谱/色谱/PCR/光谱…）。领域案例可在运行前按 task.md
补充专业词对——**补充词表是允许的，编造文件内容不允许**。

## 7. 异常处置决策表

| 情况 | 处置 |
|---|---|
| 查询概念不在词表也无自动缩写 | 字面 bigram 检索照常；answer 注明"按字面匹配" |
| 多义词命中噪声（如 "MS"=质谱/毫秒） | 依据上下文段落打分排序，低分命中在 answer 中降级说明 |
| 中英混合文档 | CJK bigram 与拉丁 token 分别索引，混合查询两边都查 |
| 无权限/损坏/扫描件 | 同核心流程，记 failures |
| 空结果 | 写 empty_reason（概念不存在 vs 别名缺失），status 不为 success |
| 无 output_contract | 默认字段集 + uncertainty 说明 |

## 8. result.json 组装规则

- `--skeleton` 预填 files / evidence（含 matched_terms）/ failures / metadata
  （concept_index 统计）。
- answer 撰写要求：列概念→文件映射；每条证据附匹配路径说明；跨语言命中必须点明。
- status / finalize / manifest / changes 同核心流程。

## 9. 最小调用示例（示意输出，非正式案例结果）

```bash
# 库: 中文笔记写"磷酸盐缓冲液（PBS）"，英文报告写 "phosphate buffered saline"
python3 $SKILL/scripts/concepts.py --work-dir /app/work
# → concepts.json 含 pbs ↔ 磷酸盐缓冲液 ↔ phosphate buffered saline 同概念
python3 $SKILL/scripts/retrieve.py --work-dir /app/work --query "PBS 配方" \
    --concepts /app/work/concepts.json
# → 中文笔记与英文报告同时命中，matched_terms 显示对齐路径，verify 逐字通过
```

## 10. 不适用情况

联网查新、综述写作、权限建设；概念之间的逻辑推理（A 是否蕴含 B）超出词面对齐范围。
