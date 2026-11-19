# 版本1 · 证据锚点引擎 — 使用与方法说明

## 这个版本解决什么问题

把检索命中落到**段落级锚点**并保证可逐字复核，重点处理三类定位错误来源：
印刷页码与 PDF 物理页错位、双栏排版文本交错、跨页表格/图注被切断。

## 与基础 Agent 的差异（可验证的增益）

| 能力 | 基础 Agent | 本版本 |
|---|---|---|
| 页码 | 报物理页或目测页码 | 页脚数字等差拟合估计 offset，双线索印证，给 printed_page + confidence |
| 双栏 PDF | 按交错行阅读，段落破碎 | 分列位置一致性检测 + 左右栏重排（仅在证据充分时启用） |
| 引用 | 凭记忆复述 | quote 必须逐字存在于所 claim 的文档页内，机器校验（verify.py） |
| 跨页题注 | 漏命中 | 页尾未完结题注与次页续接并留痕（stitched_blocks） |

## 依赖与安装

- Python ≥3.9（仅标准库）；系统命令按可用性自动检测：`pdftotext`、`pdftoppm`、
  `tesseract`（后两者缺失时扫描件如实标注 `no_text_layer_ocr_unavailable`）。
- 无 pip 依赖、无网络依赖。安装＝把本目录复制到 `/skills/weekly-skill`。

## 目录约定

```
SKILL.md            本文件与调用说明
scripts/
  common.py         共享工具（日志/哈希/分词/锚点/子进程）
  inventory.py      盘点：清单/哈希/权限/重复（步骤0）
  extract.py        按物理页提取文本，扫描件判 no_text_layer（步骤1）
  pagefix.py        【旗舰】页码校正/双栏重排/题注续接（步骤1.5）
  segment.py        章节树/段落锚点（步骤2，自动采用 pagefix 修正）
  retrieve.py       段落级 BM25 检索（步骤3）
  verify.py         逐字回链校验（步骤4）
  report.py         镜像 output_contract 组装 result.json（步骤6）
```

## 元数据字段（证据锚点 schema）

`file_path, sha256, version, section_path, section_title, paragraph_id, page,
printed_page, quote`。`printed_page` 由 `pagefix.json.docs[].offset` 推导，
`offset_basis` 给出拟合证据与置信度；无可靠 offset 时为 `null`，只报物理页。

## 运行示例

见 `SKILL.md` 第 4、9 节；合成演示见 `examples/EXAMPLE.md`（标注为示例）。

## 限制与失败处理

- 扫描件无 OCR 环境时该文件只能作为"存在性"证据，不作 quote 证据；
- 版式复杂的会议模板（多栏+浮动图）重排可能不彻底，column_evidence 可供人工复核；
- 所有失败写入 failures 数组，status 按诚实规则降级。

## 维护

- 词表/启发式规则集中在各脚本顶部常量区；`common.SKILL_VERSION` 记版本；
- 运行日记 `/app/work/run_journal.jsonl` 为 append-only，可审计可复跑。
