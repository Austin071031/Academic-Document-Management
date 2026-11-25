---
name: research-doc-gain-metrics
description: 科研文件智能检索 v2.0.0-C——增益量化与对照协议。当交付需要向评审证明"相对基础 Agent 的质量/效率增益"（使用增益 25 分、创新证据 5 分）时使用：自动汇总可复算量化指标、生成公平对照协议 GAINS.md、产出评分细则自评清单。父辈：版本谱系图谱（平台 68.67 分）。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 增益量化对照（v2.0.0-C）

**父辈版本**：版本谱系图谱 v1.0.0（attempt 89366，68.6667 分）。
**本迭代唯一主攻**：评分细则要求"通过公平对照证明质量或效率改善""用真实文件集
与对照证明创新点"——父辈无任何量化指标与对照协议输出。`metrics.py` 产出
可复算指标 + GAINS.md 对照协议 + self_audit.json 细则自评。

## 1. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`）与 `/input/task.md` |
| 工作目录 | `/app/work`；最终输出 `/app/output`（result.json + metrics.json + GAINS.md + self_audit.json） |
| 预算 | 64 次模型请求 / 900 秒 |

第一步读 case.json/task.md；result.json 原样保留 output_contract 字段与 case_id。

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
python3 $SKILL/scripts/lineage.py   --work-dir $W
EXCL=$(python3 -c "import json;print(json.dumps(json.load(open('$W/lineage.json'))['exclude_sha256']))")
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<核心问题>" --topk 10 \
    --filter "{\"exclude_sha256\": $EXCL}"
python3 $SKILL/scripts/verify.py --work-dir $W
# 步骤3.3 【旗舰】量化指标 + 对照协议 + 细则自评
python3 $SKILL/scripts/metrics.py --input-root /input --work-dir $W --output-dir $O
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# 补 answer；把 self_audit 中 not_covered 的维度补齐或如实说明
python3 $SKILL/scripts/report.py --finalize --input-root /input --work-dir $W --output-dir $O
```

## 4. 量化纪律（必须遵守）

1. metrics.json 中每个数值必须能由 /app/work 与 /app/output 的产物复算
   （字段注明来源文件）；**禁止**填入估计值或相对值（如"提升 3 倍"）；
2. GAINS.md 对照协议中**基础 Agent 一侧留空**，由平台/白板填写——绝不编造
   对照数据；本侧数值如实填写；
3. self_audit.json 按评分细则十个维度逐一核对产物存在性；not_covered 的维度
   要么补产物，要么在 answer 中明确说明缺失；
4. 效率指标用"脚本步骤数 + 分阶段耗时"表达（替代人工翻页/比对/去重的量），
   不虚构人工对照耗时。

## 5. 证据与版本规则（继承父辈）

证据锚点六要素 + verify 逐字校验；副本不作独立证据；版本角色标注；
failures 诚实分类（no_permission / no_text_layer / extract_failed…）。

## 6. result.json 组装规则

- skeleton 预填；answer 引用 verified 证据；status 依诚实规则；
- finalize 把 metrics.json / GAINS.md / self_audit.json 一并纳入 manifest 哈希清单。

## 7. 最小调用示例（示意输出，非正式案例结果）

```bash
python3 $SKILL/scripts/metrics.py --input-root /input --work-dir /app/work --output-dir /app/output
# → metrics: verify_rate=1.0 anchors=1.0 steps=27
# → GAINS.md 对照表本侧列已填实测值，基础侧留 __ 待平台填写
# → self_audit.json: covered 9/10（缺失维度附补齐建议）
```

## 8. 不适用情况

联网查新、综述写作、权限建设；本模块只量化本侧表现，不替代平台对基础 Agent
的实际测量。
