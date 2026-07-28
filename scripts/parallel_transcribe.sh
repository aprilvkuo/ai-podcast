#!/bin/bash
# 并行转录 — 用 xargs -P 控制并行度
# 用法: bash parallel_transcribe.sh ep103 ep104 ep105 ...

PARALLEL=4
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "并行转录 — 并行度: $PARALLEL"
echo "期号: $@"
echo ""

printf '%s\n' "$@" | xargs -P "$PARALLEL" -I {} bash "$SCRIPT_DIR/transcribe_one.sh" {}

echo ""
echo "=== 状态 ==="
sqlite3 "$HOME/.claude/podcast/xyz_pipeline.db" "SELECT status, COUNT(*) c FROM episodes GROUP BY status ORDER BY c DESC;"
