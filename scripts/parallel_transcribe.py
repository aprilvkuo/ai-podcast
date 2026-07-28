#!/usr/bin/env python3
"""并行转录 — 同时跑 N 个 whisperx 进程"""
import os
import re
import subprocess
import sqlite3
import time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed

PODCAST_DIR = Path.home() / ".claude/podcast"
DB_PATH = PODCAST_DIR / "xyz_pipeline.db"
DOWNLOAD_DIR = PODCAST_DIR / "xyz_downloads"
TRANSCRIPT_DIR = PODCAST_DIR / "transcripts"
VENV_PYTHON = Path.home() / ".hermes/skills/podcast/podcast-bridge/venv/bin/python3"
TRANSCRIBE_PY = Path.home() / ".hermes/skills/podcast/podcast-bridge/transcribe.py"
PARALLEL = 4  # M4 10核，4个并行刚好

def get_pending_eps():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT ep_number FROM episodes WHERE status = 'downloaded' ORDER BY ep_number")
    eps = [row[0] for row in cur.fetchall()]
    conn.close()
    return eps

def find_audio(ep_num):
    for f in DOWNLOAD_DIR.glob(f"ep{ep_num}_xiaoyuzhou.m4a"):
        return f
    for f in DOWNLOAD_DIR.glob(f"ep{ep_num}*"):
        return f
    return None

def transcribe_one(ep_num):
    audio = find_audio(ep_num)
    if not audio:
        return ep_num, False, "音频文件不存在"
    
    output_path = TRANSCRIPT_DIR / f"ep{ep_num}_transcript.md"
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    
    cmd = [
        str(VENV_PYTHON), str(TRANSCRIBE_PY), str(audio),
        "--chapters", "--asr-provider", "whisperx",
        "--output", str(output_path)
    ]
    
    start = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    elapsed = time.time() - start
    
    if proc.returncode == 0 and output_path.exists():
        # Update DB
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE episodes SET status='transcribed', transcript_path=?, updated_at=CURRENT_TIMESTAMP WHERE ep_number=?",
                     (str(output_path), ep_num))
        conn.commit()
        conn.close()
        return ep_num, True, f"{elapsed:.0f}s"
    else:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("UPDATE episodes SET status='transcribe_failed', error_msg=?, updated_at=CURRENT_TIMESTAMP WHERE ep_number=?",
                     (proc.stderr[:500], ep_num))
        conn.commit()
        conn.close()
        return ep_num, False, proc.stderr[:200]

def main():
    eps = get_pending_eps()
    print(f"待转录: {len(eps)} 期, 并行度: {PARALLEL}")
    print(f"期号: {eps}\n")
    
    done = 0
    failed = 0
    start_all = time.time()
    
    with ProcessPoolExecutor(max_workers=PARALLEL) as pool:
        futures = {pool.submit(transcribe_one, ep): ep for ep in eps}
        
        for future in as_completed(futures):
            ep, ok, msg = future.result()
            if ok:
                done += 1
                print(f"  ✅ ep{ep}: {msg} ({done}/{len(eps)})")
            else:
                failed += 1
                print(f"  ❌ ep{ep}: {msg}")
    
    total = time.time() - start_all
    print(f"\n{'='*50}")
    print(f"完成: {done} 成功, {failed} 失败, 总耗时 {total/60:.1f} 分钟")

if __name__ == "__main__":
    main()
