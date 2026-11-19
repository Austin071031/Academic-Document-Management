# 哈希账本方法学

## 为什么是账本

科研资料库整理的关键风险是**不可审计**：复制错了、漏了、改了都无法事后证明。本流水线把每次触碰文件的事实写成 append-only 账本与日志：

- `inventory.jsonl`：scan 时对每个文件的一次性事实记录（path,size,mtime,sha256,readable,error,kind,extracted_from,depth,scanned_at）。行内不可变。
- `plan.json`：从账本纯函数推导的组织方案（dry-run，不落盘），任何归位/去重/版本结论都能从账本重新推出。
- `operation_log.jsonl`：apply 的每个动作（before/after/sha256/action/time/status）。
- `verify_report.json`：交付后对 library 的重哈希比对。

账本 → 方案 → 操作 → 复核四者分离，使"结果"与"推出结果的过程"都可独立检查。

## 如何复跑核对

他人拿到 output/ 后无需信任本流水线，可独立核对：

```bash
# 1. 重算 library 哈希，与交付的 inventory/manifest 比对
python3 scripts/library_pipeline.py verify --input <原input> --work <work> --output <output>

# 2. 完全不信任脚本时，手工抽查：
sha256sum output/library/<任意文件>   # 对照 manifest.json 中该文件 sha256
# 3. 对账本抽查：重算 input 文件哈希对照 inventory.jsonl 同行
```

verify 的判定标准：planned 文件逐一 match；mismatch=哈希被改动；missing=计划复制却缺失；extra=交付中出现计划外文件。verdict=PASS 要求 match==expected 且无 mismatch/missing/error。

## 确定性

- 所有排序显式（path/mtime 字典序），重复组 canonical 取 mtime 最旧。
- 冲突命名 `__dupN` 在 plan 阶段一次性分配，apply 只执行不决策。
- 版本阈值 0.75、去重只看 sha256 与大小、零字节排除——全部硬编码于脚本，同输入必得同输出。

## 已知局限

版本相似度基于文件名归一化 stem，不读内容语义；完全改名版本可能漏判。元数据 join 依赖 stem 匹配。二者均要求在 result.uncertainty 中声明。
