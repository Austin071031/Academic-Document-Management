# v2.0.0-B-案例操作执行器 — 使用与方法说明

**父辈版本**：版本谱系图谱 v1.0.0（attempt 89366，68.6667 分）（本目录 scripts/ 完整继承其流水线：inventory / extract /
segment / lineage / retrieve / verify / report）。

**本迭代差异（只改能显著提分的内容）**：新增 `operations.py`：把题面所称 aliases / administrative version notes / metadata / recovery / index operations 做成确定性执行器，产物落 organized_library/（catalog、别名登记、版本注记、恢复日志、操作台账），只读输入。

**主攻评分点**：任务完成度 15 分（操作类任务）+ 结果可核验性 5 分。

## 运行

工作流见 `SKILL.md` 第 3 节；其余约定（运行契约、证据锚点六要素、诚实状态机、
finalize 校验）与父辈一致，不再重复。合成演示见 `examples/EXAMPLE.md`
（标注为示例）。

## 依赖

Python ≥3.9 标准库；pdftotext 建议安装；tesseract / soffice 按可用性自动降级
并如实记录。无网络依赖。

## 本地验证基线（合成案例，非平台数据）

见同目录 SUBMISSION.md（提交后补记平台结果）。
