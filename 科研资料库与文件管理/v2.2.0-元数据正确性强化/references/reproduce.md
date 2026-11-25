# 复跑核对命令清单（v2.2.0）

全部命令仅需 Python3 标准库，无网络。以 `<SKILL>` 表示本技能根目录
（含 SKILL.md 的目录），运行时评测壳内为 `/skills/weekly-skill`。

## 1. 提交契约自检（交付前必跑）

```bash
python3 <SKILL>/scripts/preflight_check.py
# 期望：退出码 0（PASS），报告 <SKILL>/preflight_report.json，七道 gate 全 OK
# gate：frontmatter 合法且 description ≤900B / ≤50 文件 / 单文件 ≤500KB /
#       总 ≤2MB / 全 UTF-8 / 无符号链接 / 无 token 密钥模式
```

## 2. 端到端管线（合成夹具见 README §7 自查方法）

```bash
python3 <SKILL>/scripts/provenance_pipeline.py \
    --input /tmp/prov22_case/input --work /tmp/prov22_case/work \
    --output /tmp/prov22_case/output
echo $?   # 期望 0
```

## 3. 关键产物核对点

```bash
# (a) 溯源台账逐字段带来源
python3 -c "import json,sys
rows=[json.loads(l) for l in open('/tmp/prov22_case/output/provenance.jsonl',encoding='utf-8')]
assert all({'file','field','value','source','evidence','confidence','rule'} <= set(r) for r in rows)
print('provenance ok:', len(rows), 'records')"

# (b) 检索问答带引用证据（case.json 含 searches/questions 时）
python3 -c "import json
d=json.load(open('/tmp/prov22_case/output/search_results.json',encoding='utf-8'))
for r in d['results']:
    if r['status']=='answered':
        h=r['hits'][0]; assert h['file'] and h['line']>=1 and h['snippet']
        assert 'metadata_provenance' in h
print('qa ok:', d['n_answered'], 'answered /', d['n_no_evidence'], 'no_evidence')"

# (c) 恢复日志（case.json 含 recovery 时）
python3 -c "import json
d=json.load(open('/tmp/prov22_case/output/recovery_log.json',encoding='utf-8'))
print('recovery ok:', d['n_requests'], 'requests,', d['n_restored_this_run'], 'restored')"

# (d) 字段正确性闸门进 result.json
python3 -c "import json
d=json.load(open('/tmp/prov22_case/output/result.json',encoding='utf-8'))
s=d['summary']; assert 'required_field_fill_rate' in s
assert 'unresolved_conflicts' in s and 'low_confidence_fields' in s
print('gate ok:', s['required_field_fill_rate']['overall'], s['unresolved_conflicts'], s['low_confidence_fields'])"

# (e) 幂等核对：同参数重跑，退出码仍 0；恢复项第二跑转 already_present
#     （不重复复制、不覆盖），search_results 结果稳定（除时间戳）
python3 <SKILL>/scripts/provenance_pipeline.py \
    --input /tmp/prov22_case/input --work /tmp/prov22_case/work \
    --output /tmp/prov22_case/output && echo rerun-rc-0
python3 -c "import json
rl=json.load(open('/tmp/prov22_case/output/recovery_log.json',encoding='utf-8'))
print({r['request']['id']: r['action'] for r in rl['records']})"

# (f) 手工单步重跑（Agent 补录后）
python3 <SKILL>/scripts/adjudicate.py     --input ... --work ... --output ... --config <SKILL>/config/field_dictionary.json
python3 <SKILL>/scripts/build_manifest.py --input ... --work ... --output ... --config <SKILL>/config/field_dictionary.json
python3 <SKILL>/scripts/qa_cite.py        --input ... --work ... --output ... --config <SKILL>/config/field_dictionary.json
python3 <SKILL>/scripts/recover.py        --input ... --work ... --output ... --config <SKILL>/config/field_dictionary.json --rebuild-index
python3 <SKILL>/scripts/finalize.py       --input ... --work ... --output ... --config <SKILL>/config/field_dictionary.json --final
```

## 4. 故障定位入口

- `work/pipeline_steps.json`：各阶段退出码与 stderr 尾部；
- `work/change_log.jsonl`：六要素变更记录（time/action/object/evidence/result/note）；
- `result.json.uncertainty`：不可读/坏包/空目录/no_evidence 查询/恢复失败全清单。
