# 04 · 基线诊断

## 基线确认

§0-9 填"自动" → 取台账最高分。台账中无已出分版本，唯一版本 v1.0.0 的三次提交均
evaluation_error（score=0 且 score_is_final=false）→ **基线 = v1.0.0 / attempt 88966（最后一条）/ 0 分（弃权，非终评）**。

## 分支判定（§4）

基线 0 < 目标分 75 × 0.7 = 52.5 → **问题在契约层（弃权型失分），禁止方向迭代，只出 1 个修复版 v2.0.0**，
仅修弃权型问题。本分支下 §0-5（4 个版本）缩减为 1 版，理由：在评测能跑通之前，任何方向增量都无法被评分兑现（R3）。

## 机制资产清单（= 白名单，逐项"这个脚本做什么"）

见 `_iteration/01_skeleton_diff.md` 表 3 —— 22 个文件全部列入，v2.0.0 必须超集保留：
pipeline.py（工作流 A 主链）、search.py（检索）、inspect_case/inventory/extract_refs/plan/apply/report/validate_output + run_pipeline.sh（工作流 B 六脚本 + 一键链）、schemas/rules/references×5/docs/examples/CHANGELOG/GITHUB_URL。

## 余量缺口表

| 缺口 | 归属维度 | 根因 | 对应活路 | 可拿回 | 承担版本 |
|-|-|-|-|-|-|
| 评测弃权（3/3 evaluation_error） | 全部 100 分 | A 弃权型：frontmatter description 1046B 疑似越 1024B 上限；瞬时分量由重提吸收 | v2.0.0 压缩 description ≤900B + 提交预检脚本固化上限 | 恢复被评资格（0 → 机制真实水平，目标 75+5） | v2.0.0 |
| submission.md 缺失 | 生态贡献（文档完整性） | B 建制缺失 | v2.0.0 按模板补齐并回填 attempt | 小（文档分项内） | v2.0.0 |
| direction.json 缺失 | 建制（FORGE 流程要求，非评分项） | B 建制缺失 | v2.0.0 补齐且参数被预检脚本真实读取 | 0（流程资产） | v2.0.0 |
| 根 README 索引缺失 | 仓库维护 | B 建制缺失 | v2.0.0 建立索引并注明基线关系 | 0（仓库资产） | v2.0.0 |

## 本地代理评测记录（基线 v1.0.0，自造夹具）

自造材料库（3 份 PDF 含 5 类批注 + 重复件 + 版本件 + 散落笔记 + docx 剪藏 + 空文件 + 断链 + 加密 + 损坏件）：
工作流 A 锚点校验 10/10 exact、跨版本归并簇 3、CJK 检索命中、preview 叠加图框位正确、
确定性复跑一致；工作流 B 版本归档/重复归档/审计/回滚/selfcheck 全过。
输出 result.json 含 case_id + output_contract 五字段全自动交付。
该记录为 v2.0.0 回归闸门的比对基准。
