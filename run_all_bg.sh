#!/bin/bash
# Run TTS + re-transcribe failed episodes in parallel
SCRIPT_DIR="/Users/egg/.claude/podcast/scripts"
PODCAST_DIR="/Users/egg/.claude/podcast"

echo "=== TTS: script_done(22期) → tts_done ==="
cd "$PODCAST_DIR"
python3 run_tts2.py 2>&1 | tee /tmp/tts_run.log

echo ""
echo "=== Done ==="
