#!/bin/bash
# 并行转录 — 单集 wrapper（监控文件增长，稳定后杀进程）
# 用法: bash transcribe_one.sh <ep_number>

EP="$1"
VENV_PYTHON="$HOME/.hermes/skills/podcast/podcast-bridge/venv/bin/python3"
TRANSCRIBE_PY="$HOME/.hermes/skills/podcast/podcast-bridge/transcribe.py"
DOWNLOAD_DIR="$HOME/.claude/podcast/xyz_downloads"
TRANSCRIPT_DIR="$HOME/.claude/podcast/transcripts"
DB="$HOME/.claude/podcast/xyz_pipeline.db"

# 找音频文件
AUDIO=""
for f in "$DOWNLOAD_DIR/ep${EP}_xiaoyuzhou.m4a" "$DOWNLOAD_DIR/ep${EP}.m4a" "$DOWNLOAD_DIR/ep${EP}"*; do
    if [ -f "$f" ]; then
        AUDIO="$f"
        break
    fi
done

if [ -z "$AUDIO" ]; then
    echo "❌ ep$EP: 音频文件不存在"
    sqlite3 "$DB" "UPDATE episodes SET status='transcribe_failed', error_msg='音频文件不存在', updated_at=CURRENT_TIMESTAMP WHERE ep_number='$EP';"
    exit 1
fi

OUTPUT="$TRANSCRIPT_DIR/ep${EP}_transcript.md"
mkdir -p "$TRANSCRIPT_DIR"

echo "▶️  ep$EP 开始转录..."

# 设置环境变量防止模型重复下载
export FUNASR_DISABLE_UPDATE=1

# 后台运行转录
"$VENV_PYTHON" "$TRANSCRIBE_PY" "$AUDIO" --skip-preflight --asr-provider whisperx --output "$OUTPUT" >/tmp/ep${EP}_transcribe.log 2>&1 &
PID=$!

# 等待文件出现并稳定
LAST_SIZE=0
STABLE_COUNT=0
MAX_WAIT=3600
ELAPSED=0

while [ $ELAPSED -lt $MAX_WAIT ]; do
    sleep 5
    ELAPSED=$((ELAPSED + 5))
    
    if [ -f "$OUTPUT" ]; then
        CURRENT_SIZE=$(stat -f%z "$OUTPUT" 2>/dev/null || echo 0)
        if [ "$CURRENT_SIZE" -eq "$LAST_SIZE" ] && [ "$CURRENT_SIZE" -gt 10000 ]; then
            STABLE_COUNT=$((STABLE_COUNT + 1))
            if [ "$STABLE_COUNT" -ge 6 ]; then  # 30秒不变
                kill -9 "$PID" 2>/dev/null
                wait "$PID" 2>/dev/null
                sqlite3 "$DB" "UPDATE episodes SET status='transcribed', transcript_path='$OUTPUT', updated_at=CURRENT_TIMESTAMP WHERE ep_number='$EP';"
                echo "✅ ep$EP 完成 ($(($ELAPSED))s, $(($CURRENT_SIZE/1024))KB)"
                exit 0
            fi
        else
            STABLE_COUNT=0
        fi
        LAST_SIZE="$CURRENT_SIZE"
    fi
    
    # 检查进程是否还在
    if ! kill -0 "$PID" 2>/dev/null; then
        wait "$PID"
        RC=$?
        if [ -f "$OUTPUT" ] && [ "$RC" -eq 0 ]; then
            sqlite3 "$DB" "UPDATE episodes SET status='transcribed', transcript_path='$OUTPUT', updated_at=CURRENT_TIMESTAMP WHERE ep_number='$EP';"
            echo "✅ ep$EP 完成 (进程退出)"
            exit 0
        else
            sqlite3 "$DB" "UPDATE episodes SET status='transcribe_failed', error_msg='进程异常退出 rc=$RC', updated_at=CURRENT_TIMESTAMP WHERE ep_number='$EP';"
            echo "❌ ep$EP 进程异常退出 rc=$RC"
            exit 1
        fi
    fi
done

# 超时
kill -9 "$PID" 2>/dev/null
sqlite3 "$DB" "UPDATE episodes SET status='transcribe_failed', error_msg='超时', updated_at=CURRENT_TIMESTAMP WHERE ep_number='$EP';"
echo "❌ ep$EP 超时"
exit 1
