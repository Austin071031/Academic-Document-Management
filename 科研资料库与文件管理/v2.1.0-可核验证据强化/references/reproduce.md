# 复跑核对命令清单（第三方可独立执行）

以下命令假设 Skill 安装在 `/skills/weekly-skill`，运行在
`/input`（case.json + 混乱资料库）、产物在 `/app/output`、中间产物在
`/app/work`。仅依赖 Python 3 标准库；PNG 预览需 matplotlib（可选，缺失时
自动降级为 SVG only 并在 result.json 的 uncertainty 中登记，不报错）。

## 1. 全链路（一条命令）

```bash
python3 /skills/weekly-skill/scripts/cas_run.py \
    --input /input --work /app/work --output /app/output
echo "exit=$?"   # 预期 0
```

## 2. 完整性核对（哈希级，退出码 0=全部一致 / 1=有篡改或丢失）

```bash
python3 /skills/weekly-skill/scripts/verify_cas.py \
    --input /input --work /app/work --output /app/output
cat /app/output/library/verify_report.json
```

人工抽查：重新哈希任意 tree 文件并与对象库比对——

```bash
F=$(find /app/output/library/tree -type f | head -1)
sha256sum "$F"
ls /app/output/library/objects/*/ | grep "$(sha256sum "$F" | cut -c1-64)"
```

## 3. 检索复核（重建倒排索引并重答 case.json 的 searches/questions）

```bash
python3 /skills/weekly-skill/scripts/search.py \
    --input /input --work /app/work --output /app/output
cat /app/output/library/search_results.json   # 每条命中带 文件+行号+片段
cat /app/output/search_results.json           # 顶层同步副本（recover_qa 写入）
```

## 4. 证据图复渲染（SVG 纯标准库必出；PNG 视 matplotlib 可用性）

```bash
python3 /skills/weekly-skill/scripts/render_evidence.py \
    --input /input --work /app/work --output /app/output
ls -l /app/output/library/evidence/   # lineage.svg（必须）+ tree_overview.svg + lineage.png（尽力）
```

用任意浏览器/查看器打开 SVG 即可目视核对：节点=唯一内容 sha256，
红色箭头=supersedes（新→旧，含 similarity 与行增删），紫色区=精确重复组。

## 5. 恢复与索引重建复核

```bash
python3 /skills/weekly-skill/scripts/recover.py \
    --input /input --work /app/work --output /app/output
cat /app/output/library/recovery_log.jsonl    # 每条恢复含 hash_verified=true
python3 /skills/weekly-skill/scripts/verify_cas.py \
    --input /input --work /app/work --output /app/output   # 恢复后再核对仍应 ok
```

## 6. 提交契约自检（针对 Skill 包自身）

```bash
python3 /skills/weekly-skill/scripts/preflight_check.py \
    --report /app/output/preflight_report.json
echo "exit=$?"   # 0=全部硬约束通过（≤50 文件、单文件≤500KB、总≤2MB、全 UTF-8、无符号链接、frontmatter 合法）
```

## 7. 结果一致性抽查

```bash
python3 - <<'EOF'
import json
r = json.load(open("/app/output/result.json", encoding="utf-8"))
case = json.load(open("/input/case.json", encoding="utf-8"))
fields = case.get("output_contract", [])
fields = [f if isinstance(f, str) else f.get("field") or f.get("name")
          for f in fields] if isinstance(fields, list) else list(fields)
missing = [f for f in fields if f not in r and f not in ("case_id", "status")]
print("case_id:", r.get("case_id"), "| status:", r.get("status"))
print("契约缺失字段:", missing or "无")
print("uncertainty 条数:", len(r.get("uncertainty", [])))
EOF
```
