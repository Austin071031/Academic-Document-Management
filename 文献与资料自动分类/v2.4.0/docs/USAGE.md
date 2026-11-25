# 使用说明（USAGE）

## 一分钟上手

```bash
bash scripts/run_pipeline.sh /input /app/work /app/output   # 完整整理
python3 scripts/selftest.py                                  # 金标准自测（无需真实数据）
python3 scripts/kb_search.py --output-dir /app/output --query "钙钛矿 光催化"
```

## 输入约定

- `/input/case.json`：case_id、output_contract、可选 questions/searches/recover 字段；
- `/input/task.md`：整理规则（命名模板、目录维度、恢复请求）；
- 管理性材料：别名表（aliases*）、版本说明（*version*notes*）、元数据表（metadata.csv/json）。

## 自定义规则

写 `/app/work/plan_config.json` 覆盖默认（见 references/naming_rules.md 第 3 节）。

## 复用规则包

- `rules/taxonomy.json`：类型判定规则表 + 版本分组/去重方法（机器可读）；
- `rules/tag_vocab.json`：受控标签词表（同义合并）；
- `rules/naming_templates.json`：命名模板与降级链；
- `fixtures/expected.json` + `scripts/selftest.py`：金标准自测集。
