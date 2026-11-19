# 版本2 · 版本谱系图谱 — 使用与方法说明

## 这个版本解决什么问题

文件库中改名副本、修订版、扫描件并存时，检索最常见的错误是**把副本当独立证据**
（一份内容数成多份）、引用旧版当新版、漏掉改名文件。本版本建立**版本谱系图**，
让检索与计数都"版本感知"。

## 谱系关系判定

| 关系 | 判据 | 含义 |
|---|---|---|
| duplicate_exact | sha256 相同 | 逐字节重复 |
| renamed_copy | 哈希相同 + 文件名规范化不同 | 改名副本 |
| revision_chain | shingle Jaccard ≥ 0.60 + 版本标签/日期可排序 | 修订链 |
| related_content | Jaccard ≥ 0.30 | 弱关联（共享内容段） |
| singleton | 无匹配 | 独立文档 |

canonical 推举顺序：版本阶段（final > submission > revision > draft）>
版本号 > 日期。每个簇只算一份证据；`exclude_sha256` 直接供检索硬过滤。

## 依赖与安装

- Python ≥3.9（仅标准库）；无网络依赖。安装＝复制到 `/skills/weekly-skill`。
- 前置流水线：inventory → extract → segment（本目录 scripts/ 已含）。

## 目录约定

```
scripts/lineage.py   【旗舰】谱系构建（步骤2.5）
scripts/{inventory,extract,segment,retrieve,verify,report}.py  核心流水线
```

## 元数据字段

`version_tags`（文件名解析）、`version_role`（canonical / exact_copy /
renamed_copy / older_revision / intermediate_revision / only_version）、
`cluster_id`、`is_canonical`、`date`（文件名日期优先，mtime 兜底并标注）。

## 运行示例

见 `SKILL.md` 第 4、9 节；合成演示见 `examples/EXAMPLE.md`（标注为示例）。

## 限制与失败处理

- 内容相似度基于词级 shingle，图片型 PDF（扫描件）彼此无法比对内容——按哈希与
  文件名规范化判定；
- 版本标签缺失时保守标 `only_version`，不猜测版本关系；
- 同名不同内容绝不合并（哈希不同即各自保留）。

## 维护

判定阈值 `--sim-rev 0.60 --sim-rel 0.30` 可调；阈值调整需在运行日记中留痕。
