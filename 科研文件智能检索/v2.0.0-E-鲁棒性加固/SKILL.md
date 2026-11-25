---
name: research-doc-robust-recovery
description: 科研文件智能检索 v2.0.0-E——鲁棒性加固与降级保底。当文件库格式复杂（RTF/EML/归档包/旧版 Office/扫描件/损坏 PDF）或流水线可能中断时使用：加固版提取器全覆盖回退链，recover.py 保证任何中断都落盘一份诚实的 result.json。父辈：版本谱系图谱（平台 68.67 分）；本迭代主攻可靠体验（稳定性+异常处理）。不适用开放网络检索与权限建设。
---

# 科研文件智能检索 · 鲁棒性加固（v2.0.0-E）

**父辈版本**：版本谱系图谱 v1.0.0（attempt 89366，68.6667 分）。
**本迭代唯一主攻**：可靠体验 10 分（运行稳定性 4 + 异常处理 3）。加固版
`extract.py` 覆盖更多真实格式与故障回退；`recover.py` 兜底——无论哪一环中断，
/app/output 始终有一份诚实标注的 result.json。

## 1. 加固点清单

| 故障/格式 | 父辈 v1.0.0 | 本迭代 |
|---|---|---|
| RTF | 按纯文本读（控制字混入） | 控制字剥离、\'xx 十六进制字符解码 |
| EML | 按纯文本读（头体混杂） | email 标准库解析，取 text/plain + 头字段 |
| zip/tar 归档 | 只记录不处理 | 受控解包（≤20 文本成员、单成员≤2MiB），成员以 unit 记录 |
| OCR 语言包缺失 | OCR 直接失败 | eng+chi_sim 失败自动回退 eng |
| 损坏/加密 PDF | pdftotext 失败即记 | 回退链 mutool → qpdf(qdf 文本流粗提)，均失败如实记录 |
| 旧版 Office | antiword 单点 | antiword → catdoc 链 |
| 流水线中断 | 无交付 | recover.py 重跑缺失阶段一次 + 强制装配降级 result.json |

## 2. 运行契约（先读再动）

| 项 | 约定 |
|---|---|
| 案例输入 | `/input/case.json`（`case_id`、`output_contract`）与 `/input/task.md` |
| 工作目录 | `/app/work`；最终输出 `/app/output` |
| 预算 | 64 次模型请求 / 900 秒 |

## 3. 标准工作流

```bash
W=/app/work; O=/app/output; mkdir -p "$W" "$O"
python3 $SKILL/scripts/inventory.py --input-root /input --work-dir $W
python3 $SKILL/scripts/extract.py   --input-root /input --work-dir $W   # 加固版
python3 $SKILL/scripts/segment.py   --work-dir $W
python3 $SKILL/scripts/lineage.py   --work-dir $W
EXCL=$(python3 -c "import json;print(json.dumps(json.load(open('$W/lineage.json'))['exclude_sha256']))")
python3 $SKILL/scripts/retrieve.py --work-dir $W --query "<核心问题>" --topk 10 \
    --filter "{\"exclude_sha256\": $EXCL}"
python3 $SKILL/scripts/verify.py --work-dir $W
python3 $SKILL/scripts/report.py --skeleton --input-root /input --work-dir $W --output-dir $O
# 补 answer/status 后 finalize；随后必跑：
python3 $SKILL/scripts/recover.py --input-root /input --work-dir $W --output-dir $O
```

**预算将尽时立即执行**：skeleton → recover.py（它自动补 finalize），保证交付。

## 4. 降级规则（必须遵守）

1. recover.py 对缺失阶段**各重跑一次**（防死循环）；仍缺失的进
   degraded_report.json（阶段、重跑返回码、stderr 摘要）；
2. 降级 result.json：`status` 按缺失阶段数定 partial/failed，绝不为 success；
   `empty_reason` 说明缺了什么、尽力恢复了什么；
3. 恢复成功的文件（OCR/回退工具）在证据中标注来源（ocr / mutool_recovery /
   qdf_recovery），quote 校验仍按原文本执行；
4. 归档成员证据的路径写作 `归档名.zip::成员名`，并在 answer 说明出自归档；
5. 回退链每一步的成败都进 failures/journal，不静默。

## 5. 异常处置决策表（继承并扩展父辈）

| 情况 | 处置 |
|---|---|
| 全部 PDF 损坏 | 逐文件走 mutool/qpdf 回退；全败则 evidence 只剩元数据，answer 降级说明 |
| 归档内含二级归档 | 不解套（budget guard），记录 nested_archive_skipped |
| OCR 中英文都失败 | 记 ocr_failed，文件仅作存在性证据 |
| 输入根目录缺失 | inventory 记 path_missing；recover 装配 failed 级 result.json |
| 无 output_contract | 默认字段集 + uncertainty |

## 6. 最小调用示例（示意输出，非正式案例结果）

```bash
# 库含 memo.rtf / notice.eml / export_bundle.zip / scanned_note.pdf
python3 $SKILL/scripts/extract.py --input-root /input --work-dir /app/work
# → docs=11 with_text=9：rtf 控制字已剥离、eml 取正文、zip 解出 2 个文本成员
# 删除 hits.json 模拟中断后：
python3 $SKILL/scripts/recover.py --input-root /input --work-dir /app/work --output-dir /app/output
# → degraded=1 recovered=3；result.json status=partial, empty_reason 如实说明
```

## 7. 不适用情况

联网查新、综述写作、权限建设；加密文件的解密（只做识别与记录，不绕过）。
