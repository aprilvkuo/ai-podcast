#!/usr/bin/env python3
"""Generate TTS for remaining script_done episodes."""
import os
import re
import subprocess
import sqlite3
from pathlib import Path
from datetime import datetime

DB = Path("/Users/egg/.claude/podcast/xyz_pipeline.db")
SCRIPTS_DIR = Path("/Users/egg/.claude/podcast/scripts")
EPISODES_DIR = Path("/Users/egg/.claude/podcast/episodes")
EDGE_TTS = Path("/Users/egg/.hermes/hermes-agent/venv/bin/edge-tts")
VOICE_H = "zh-CN-YunyangNeural"
VOICE_G = "zh-CN-XiaoxiaoNeural"
DATE_STR = datetime.now().strftime("%Y%m%d")

def parse_script(path):
    segments = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('H:') or line.startswith('G:'):
                speaker = line[0]
                text = line[2:].strip()
                if text:
                    segments.append((speaker, text))
    return segments

def generate_tts(ep_number):
    script_path = SCRIPTS_DIR / f"ep{ep_number}_script.md"
    if not script_path.exists():
        return None, "script not found"
    
    segments = parse_script(script_path)
    if not segments:
        return None, "no segments"
    
    seg_dir = EPISODES_DIR / f"ep{ep_number}_segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    
    for i, (speaker, text) in enumerate(segments):
        voice = VOICE_H if speaker == 'H' else VOICE_G
        seg_path = seg_dir / f"{i:03d}_{speaker}.mp3"
        if not seg_path.exists():
            r = subprocess.run(
                [str(EDGE_TTS), "--voice", voice, "--rate", "+5%",
                 "--text", text, "--write-media", str(seg_path)],
                capture_output=True, timeout=30
            )
        if i % 20 == 0:
            print(f"  [{i+1}/{len(segments)}]...")
    
    concat_list = seg_dir / "filelist.txt"
    with open(concat_list, 'w') as f:
        for i in range(len(segments)):
            for sp in ['H', 'G']:
                seg = seg_dir / f"{i:03d}_{sp}.mp3"
                if seg.exists():
                    f.write(f"file '{seg.name}'\n")
    
    output = EPISODES_DIR / f"ep{ep_number}-dual-{DATE_STR}.mp3"
    r = subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0",
         "-i", str(concat_list), "-c", "copy", str(output)],
        capture_output=True, timeout=120
    )
    
    if output.exists():
        return str(output), None
    return None, r.stderr.decode()[:200]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get remaining script_done
cur.execute("SELECT ep_number FROM episodes WHERE status='script_done' ORDER BY ep_number")
rows = cur.fetchall()

done = 0
for row in rows:
    ep = row['ep_number']
    print(f"\n--- ep{ep} ---")
    try:
        path, err = generate_tts(ep)
        if path:
            cur.execute("UPDATE episodes SET status='tts_done', podcast_file=? WHERE ep_number=?", (path, ep))
            conn.commit()
            done += 1
            print(f"  ✅ {os.path.basename(path)}")
        else:
            print(f"  ❌ {err}")
    except Exception as e:
        print(f"  ❌ {e}")

print(f"\n=== TTS done: {done}/{len(rows)} ===")
conn.close()
