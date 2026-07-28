#!/usr/bin/env python3
"""Generate TTS audio for podcast episodes."""

import os
import re
import subprocess
import sqlite3
import tempfile
import shutil
from pathlib import Path

# Configuration
WORKSPACE = Path("/Users/egg/.claude/podcast")
SCRIPTS_DIR = WORKSPACE / "scripts"
DB_PATH = WORKSPACE / "xyz_pipeline.db"
OUTPUT_DIR = WORKSPACE / "audio"

EDGE_TTS = "/Users/egg/.hermes/hermes-agent/venv/bin/edge-tts"

VOICE_MAP = {
    "H": "zh-CN-YunyangNeural",
    "G": "zh-CN-XiaoxiaoNeural",
}

RATE = "+5%"

EPISODES = ["127", "128"]

def parse_script(script_path: Path) -> list[tuple[int, str, str]]:
    """Parse script file and return list of (line_num, speaker, text)."""
    segments = []
    pattern = re.compile(r'^([HG]):\s*(.+)$')
    
    with open(script_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')
            m = pattern.match(line)
            if m:
                speaker = m.group(1)
                text = m.group(2).strip()
                if text:  # skip empty text
                    segments.append((len(segments) + 1, speaker, text))
    
    return segments


def generate_segment(text: str, voice: str, output_path: Path) -> bool:
    """Generate a single TTS segment using edge-tts."""
    cmd = [
        EDGE_TTS,
        "--voice", voice,
        "--rate", RATE,
        "--text", text,
        "--write-media", str(output_path),
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"    ERROR: edge-tts failed: {result.stderr}")
        return False
    return True


def concatenate_segments(segment_files: list[Path], output_path: Path, tmp_dir: Path) -> bool:
    """Concatenate MP3 segments using ffmpeg concat demuxer."""
    # Create concat list file
    concat_file = tmp_dir / "concat.txt"
    with open(concat_file, 'w', encoding='utf-8') as f:
        for seg in segment_files:
            # Escape single quotes in path
            escaped = str(seg).replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")
    
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-acodec", "libmp3lame",
        "-q:a", "4",
        str(output_path),
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        print(f"    ERROR: ffmpeg failed: {result.stderr}")
        return False
    return True


def process_episode(ep_str: str, db_id: int):
    """Process a single episode."""
    script_path = SCRIPTS_DIR / f"ep{ep_str}_script.md"
    output_path = OUTPUT_DIR / f"ep{ep_str}.mp3"
    
    if not script_path.exists():
        print(f"  SKIP: Script not found: {script_path}")
        return
    
    print(f"\n{'='*60}")
    print(f"Processing ep{ep_str} (db_id={db_id})")
    print(f"Script: {script_path}")
    print(f"Output: {output_path}")
    
    # Parse script
    segments = parse_script(script_path)
    print(f"  Found {len(segments)} segments")
    
    if not segments:
        print(f"  SKIP: No segments found")
        return
    
    # Create temp directory for segments
    tmp_dir = Path(tempfile.mkdtemp(prefix=f"ep{ep_str}_"))
    try:
        segment_files = []
        
        # Generate TTS for each segment
        for idx, (line_num, speaker, text) in enumerate(segments):
            seg_filename = f"{idx:04d}_{speaker}.mp3"
            seg_path = tmp_dir / seg_filename
            
            voice = VOICE_MAP.get(speaker, "zh-CN-YunyangNeural")
            
            print(f"  [{idx+1}/{len(segments)}] {speaker} (line {line_num}): {text[:50]}...")
            
            if not generate_segment(text, voice, seg_path):
                print(f"  FAILED to generate segment {idx}")
                continue
            
            segment_files.append(seg_path)
        
        if not segment_files:
            print(f"  SKIP: No segments generated")
            return
        
        # Concatenate
        print(f"  Concatenating {len(segment_files)} segments...")
        if not concatenate_segments(segment_files, output_path, tmp_dir):
            print(f"  FAILED to concatenate")
            return
        
        # Update database
        print(f"  Updating database...")
        conn = sqlite3.connect(str(DB_PATH))
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE episodes SET podcast_file = ?, status = ?, updated_at = datetime('now') WHERE id = ?",
            (str(output_path), "tts_done", db_id)
        )
        conn.commit()
        conn.close()
        
        print(f"  DONE: {output_path}")
        
    finally:
        # Clean up temp directory
        shutil.rmtree(tmp_dir, ignore_errors=True)


def main():
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # Get episode IDs from database
    conn = sqlite3.connect(str(DB_PATH))
    cursor = conn.cursor()
    
    # Map ep numbers to db ids
    ep_to_id = {}
    placeholders = ", ".join(["?"] * len(EPISODES))
    cursor.execute(f"SELECT id, ep_number FROM episodes WHERE ep_number IN ({placeholders})",
                   tuple(EPISODES))
    for row in cursor.fetchall():
        ep_to_id[row[1]] = row[0]
    
    conn.close()
    
    # Process each episode
    for ep_id in EPISODES:
        db_id = ep_to_id.get(ep_id)
        if db_id is None:
            print(f"\nSKIP: {ep_id} not found in database")
            continue
        
        try:
            process_episode(ep_id, db_id)
        except Exception as e:
            print(f"\nERROR processing {ep_id}: {e}")
            import traceback
            traceback.print_exc()
    
    print(f"\n{'='*60}")
    print("All episodes processed!")


if __name__ == "__main__":
    main()
