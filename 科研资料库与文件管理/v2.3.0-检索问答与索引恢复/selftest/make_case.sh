#!/usr/bin/env bash
# 合成自查案例：中文名/改名副本/两版本 txt/CSV 管理备注/坏 zip/空目录/
# 深目录/含中文可检索内容。用法: bash selftest/make_case.sh <目标目录>
set -euo pipefail
DEST="${1:?用法: make_case.sh <dest_dir>}"
IN="$DEST/input"
rm -rf "$DEST"
mkdir -p "$IN/中微子实验/深/层/目/录" "$IN/中微子实验/空目录占位" "$IN/行政材料"

cat > "$DEST/input/case.json" <<'EOF'
{
  "case_id": "selftest_case_001",
  "output_contract": {
    "required_files": ["result.json", "archive/{case_id}_archive.tar.gz",
                       "archive/SHA256SUMS", "archive/MANIFEST.json",
                       "archive/HANDOFF_README.md", "library/"]
  },
  "searches": ["中微子", "实验目的"],
  "questions": ["保存期限是多久"]
}
EOF

cat > "$DEST/input/task.md" <<'EOF'
# 合成自查任务（示例）
请整理本资料库并交付归档。
保存期限：10年
密级：内部
EOF

cat > "$IN/中微子实验/实验记录_v1.txt" <<'EOF'
中微子振荡实验 第一轮记录
实验目的：测量中微子质量顺序。
剂量数据：3.2e12 POT。
EOF
sleep 0.05
cat > "$IN/中微子实验/实验记录_v2.txt" <<'EOF'
中微子振荡实验 第二轮记录
实验目的：测量中微子质量顺序。
剂量数据：8.1e12 POT。
新增：探测器噪声降低 12%。
EOF
cp "$IN/中微子实验/实验记录_v1.txt" "$IN/中微子实验/实验记录_v1.bak.txt"

cat > "$IN/行政材料/管理备注 2026.csv" <<'EOF'
文件,负责人,备注
实验记录_v2.txt,王工,以此版为准
EOF

cat > "$IN/中微子实验/深/层/目/录/深层笔记.md" <<'EOF'
# 深层笔记
中微子探测器的液闪配方见附表。
EOF

# 好 zip（python 生成保证可复现）
python3 - "$IN" <<'EOF'
import os, sys, zipfile
inp = sys.argv[1]
with zipfile.ZipFile(os.path.join(inp, "行政材料", "附表.zip"), "w") as z:
    z.writestr("inner.csv", "编号,数值\n1,42\n")
# 坏 zip：截断头
with open(os.path.join(inp, "中微子实验", "坏压缩包.zip"), "wb") as f:
    f.write(b"PK\x03\x04not a real zip")
EOF

echo "合成案例就绪: $DEST"
