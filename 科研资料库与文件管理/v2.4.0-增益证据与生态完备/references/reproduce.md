# 复跑核对命令清单（reproduce）

在 Skill 根目录执行（`$SK` = Skill 根目录绝对路径）。预期结果如每步注释。

## 0. 语法检查（零依赖）

```bash
python3 -m py_compile scripts/*.py && echo SYNTAX_OK
```

## 1. 端到端跑两次（幂等验证）

```bash
python3 scripts/organize.py --input /tmp/skill-fixture/input \
    --work /tmp/skill-fixture/work1 --output /tmp/skill-fixture/out1
echo "exit=$?"          # 预期 exit=0
python3 scripts/organize.py --input /tmp/skill-fixture/input \
    --work /tmp/skill-fixture/work2 --output /tmp/skill-fixture/out2
echo "exit=$?"          # 预期 exit=0
```

注意：apply 会把空目录移入 quarantine（改变输入），第二次运行前请从
原始夹具重新复制 input；或者接受第二次 empty_dirs=0（条目级哈希仍一致，
见 gain_metrics.json.idempotency）。

## 2. 幂等哈希对照

```bash
python3 - <<'EOF'
import json
m1 = json.load(open('/tmp/skill-fixture/out1/gain_metrics.json'))
m2 = json.load(open('/tmp/skill-fixture/out2/gain_metrics.json'))
i1, i2 = m1['idempotency'], m2['idempotency']
assert i1['idempotent'] and i2['idempotent'], 'in-process rerun mismatch'
assert i1['first_run_entries_sha256'] == i2['first_run_entries_sha256'], 'run-to-run mismatch'
print('IDEMPOTENT_OK', i1['first_run_entries_sha256'])
EOF
```

## 3. 结果完整性核对

```bash
python3 - <<'EOF'
import json
r = json.load(open('/tmp/skill-fixture/out1/result.json'))
a = json.load(open('/tmp/skill-fixture/work1/audit.json'))
g = json.load(open('/tmp/skill-fixture/out1/gain_metrics.json'))
assert r['case_id'] and r['status'] in ('complete', 'complete_with_warnings')
assert r['sources'] and isinstance(r['uncertainty'], list) and r['change_records']
assert a['all_match'] is True
assert g['model_calls'] == 0
print('RESULT_OK status=%s verified=%s all_match=%s' % (
    r['status'], a['verified'], a['all_match']))
EOF
```

## 4. 检索与恢复核对（夹具含 searches/recovery 时）

```bash
python3 - <<'EOF'
import json
s = json.load(open('/tmp/skill-fixture/out1/search_results.json'))
print('queries=%d answered=%d' % (s['queries_total'], s['queries_answered']))
for r in s['results']:
    print(' ', r['query'], '->', r['status'],
          [(h['path'], h['line']) for h in r['hits'][:2]])
for line in open('/tmp/skill-fixture/out1/recovery_log.jsonl'):
    rec = json.loads(line)
    print('recover:', rec['request'], '->', rec['status'], rec['verified'])
EOF
```

## 5. 提交契约自检

```bash
python3 scripts/preflight_check.py          # 退出码 0 = 可提交
echo "preflight_exit=$?"
```

## 6. 约定翻译抽查（可选）

```bash
mkdir -p /tmp/conv/input && cd /tmp/conv/input
echo '{"case_id":"conv","layout":"{topic}/{year}/{kind}/{name}"}' > case.json
echo hello > 报告.txt
python3 "$SK/scripts/organize.py" --input /tmp/conv/input \
    --work /tmp/conv/work --output /tmp/conv/out
find /tmp/conv/out/library -type f   # 预期落在 <topic>/2026|undated/<kind>/报告.txt
```
