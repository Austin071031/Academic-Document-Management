# v2.0.0-E-鲁棒性加固 — 使用与方法说明

**父辈版本**：版本谱系图谱 v1.0.0（attempt 89366，68.6667 分）（本目录 scripts/ 完整继承其流水线：inventory / extract /
segment / lineage / retrieve / verify / report）。

**本迭代差异（只改能显著提分的内容）**：加固 `extract.py`（RTF 剥离、EML 解析、zip/tar 受控解包、OCR 语言回退、损坏 PDF mutool/qpdf 回退、legacy Office 工具链）+ 新增 `recover.py`：缺失阶段重跑一次 + 强制装配诚实降级的 result.json。

**主攻评分点**：可靠体验 10 分（运行稳定性 4 + 异常处理 3）。

## 运行

工作流见 `SKILL.md` 第 3 节；其余约定（运行契约、证据锚点六要素、诚实状态机、
finalize 校验）与父辈一致，不再重复。合成演示见 `examples/EXAMPLE.md`
（标注为示例）。

## 依赖

Python ≥3.9 标准库；pdftotext 建议安装；tesseract / soffice 按可用性自动降级
并如实记录。无网络依赖。

## 本地验证基线（合成案例，非平台数据）

见同目录 SUBMISSION.md（提交后补记平台结果）。
