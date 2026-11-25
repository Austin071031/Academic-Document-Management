# 异常识别与处置矩阵

| # | 情况 | 识别方式 | 处置 |
|---|---|---|---|
| 1 | 文件不可读(权限不足) | inventory.json `readable: false` 或 stat_error | 登记 `permission` 异常(uid/gid/mode 已记录);若题目涉及该文件,相关答案 uncertainty=D 并在 what_is_missing 说明"该文件因权限不可读,无法确认是否含相关证据";不尝试绕过权限 |
| 2 | 符号链接 | `is_symlink: true` | 不追随、不索引;记录 link_target;若链接目标在库内,目标文件会被正常盘点,两者靠哈希去重关联 |
| 3 | 扫描件无文本层 | extract_report `needs_ocr` | 走 OCR 回退(阶段 2);引用时标注 OCR 风险,uncertainty ≤ D |
| 4 | PDF 加密/损坏 | extract_report `error` | 记录错误原因;列入异常清单;题目涉及则降级说明 |
| 5 | 目录为空 | inventory 目录条目 `empty directory`;或 roots 下零文件 | 若整个资料库为空:status=failed,说明"输入资料库为空,无可检索内容";单个子目录为空:登记即可 |
| 6 | 重复副本 | versions.json `duplicate_groups`(sha256 相同) | 一组只保留一个 canonical 入索引;其余在清单中保留路径与哈希,不删原文件 |
| 7 | 历史版本 | versions.json 多版本文档 | 默认只索引 canonical;版本对比题用 `--all-versions` 重建索引并同时保留两份 |
| 8 | 管理方版本规定 | 库内 version_notes/changelog/README/说明 类文件 | 读出其规定,写 version_rules.json 重跑 kb_versions.py;规则优先于启发式 |
| 9 | 版本冲突/证据矛盾 | 同一问题不同版本/文档给出不同结论 | conflicts 并列双方坐标与原文;取信顺序:管理方规则 > 更新版本 > canonical;不做无依据折中 |
| 10 | 题目超范围 | 检索+同义词重查仍无命中 | 走缺证流程,answer="知识库中没有足够依据",说明检索范围与缺失内容 |
| 11 | case.json 缺 output_contract | 阶段 0 发现 | 按题目文字要求推断交付字段,result.json 中仍保留 case_id/status/sources/uncertainty 等支撑字段,并在 change_log 说明合同缺失 |
| 12 | 抽取文本乱码 | preview/段落肉眼检查 | 换编码重读(GBK/GB18030/Latin-1 依次尝试);仍乱码则标记 error 并登记 |

## 恢复方式

- 任何阶段失败都不删除中间产物;从 `/app/work` 已生成文件继续。
- 单文件处理异常不影响其他文件(脚本逐文件 try/except)。
- 预算耗尽时:保留 result.json 当前版本(status=partial)、report.md、已复制的 inventory/versions/extract/ops_log,保证交付物可复核。
