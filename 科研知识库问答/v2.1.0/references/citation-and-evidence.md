# 引用、证据与不确定性规范

## 1. 证据条目(evidence)字段

answers.json 中每条证据必须是如下结构,坐标与摘录缺一不可:

```json
{
  "id": "E1",
  "path": "papers/catalyst_paper_v2.pdf",
  "version_label": "v2",
  "canonical": true,
  "page": 3,
  "para_index": 7,
  "char_start": 412,
  "char_end": 555,
  "exact_quote": "在 300 °C 下转化率由 42% 提升至 67%,选择性维持在 91% 以上。",
  "sha256": "<该文件在 inventory.json 中的哈希前 16 位>"
}
```

要求:

- `exact_quote` 必须是 `text/<file_id>.txt` 对应段落中的**逐字连续子串**,长度 60–200 字;引用前打开文本核对首尾各一次。
- `page` 对 PDF 取自 pdftotext 分页(\f);对纯文本文件为 `null`,以 `para_index + char_start/char_end` 定位。
- `canonical` 表示该文件是其文档版本链中被采纳的版本;引用被取代的旧版本时写 `false` 并在答案中说明原因(版本对比题)。
- 一条论断可挂多条证据(多来源一致);同一证据被多条论断复用时,id 保持一致。

## 2. 答案结构

```json
{
  "answer": "……结论表述……[E1][E2]",
  "claims": [
    {"text": "论断一", "evidence": ["E1"]},
    {"text": "论断二", "evidence": ["E2"]}
  ],
  "evidence": [ {E1 结构}, {E2 结构} ],
  "uncertainty": "A",
  "uncertainty_note": "单一来源但为 canonical 终稿,全文一致。",
  "searched": {"queries": ["转化率 300"], "scope": "canonical 版本, 8 个文档", "hits_considered": 6}
}
```

- `answer` 中的每个关键论断都必须在 `claims` 中出现并挂证据;不含论断的过渡性语句可以不挂。
- `searched` 记录检索词与范围,支撑"换一个人重走一遍"。

## 3. 不确定性分级

| 级别 | 含义 | 必要条件 |
|---|---|---|
| A | 可靠 | 单一 canonical 来源,原文表述明确无歧义 |
| B | 较可靠 | 两个及以上独立来源(不同文档或不同版本)一致 |
| C | 有冲突 | 来源间数值/结论不一致;答案须并列呈现冲突并说明取信依据 |
| D | 存疑 | 关键证据来自 OCR、不可读文件的旁证、或相关文件不可读导致覆盖不全 |

附加规则:凡引用经 OCR 得到的文本,uncertainty 最高为 D,并在 `uncertainty_note` 说明。

## 4. 缺证(知识库里没有)的写法

```json
{
  "question": "<原问题>",
  "answer": "知识库中没有足够依据回答该问题。",
  "questions_without_evidence": [
    {"question": "<原问题>",
     "searched": {"queries": ["..."], "scope": "全部 canonical 版本 + 全量索引"},
     "what_is_missing": "资料库仅含 X、Y 两类文献,不含任何关于 <主题> 的论述;版本链中亦无相关补充材料。"}
  ],
  "uncertainty": "D"
}
```

## 5. 版本冲突的写法

```json
{
  "conflicts": [{
    "question": "<题号>",
    "positions": [
      {"path": "a_v1.pdf", "page": 2, "para_index": 3, "exact_quote": "效率为 12%。"},
      {"path": "a_v2.pdf", "page": 2, "para_index": 3, "exact_quote": "效率修正为 14%。"}
    ],
    "resolution": "按管理方版本说明/按更新版本 v2 取信;v1 数值并列保留备查。",
    "resolution_basis": "version_notes.md 第 2 条 / 无管理规则时默认新版本优先"
  }]
}
```
