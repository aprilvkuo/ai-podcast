#!/usr/bin/env python3
"""
Generate TTS audio for podcast episodes using edge-tts and ffmpeg.
Processes ep145, ep75, ep81, ep91, ep95.
"""

import os
import re
import subprocess
import sqlite3
import tempfile
import shutil
from pathlib import Path

# Configuration
DB_PATH = "/Users/egg/.claude/podcast/xyz_pipeline.db"
SCRIPTS_DIR = "/Users/egg/.claude/podcast/scripts"
OUTPUT_DIR = "/Users/egg/.claude/podcast/episodes"
EDGE_TTS_PATH = "/Users/egg/.hermes/hermes-agent/venv/bin/edge-tts"
FFMPEG_PATH = "/opt/homebrew/bin/ffmpeg"

VOICE_H = "zh-CN-YunyangNeural"
VOICE_G = "zh-CN-XiaoxiaoNeural"
RATE = "+5%"

EPISODES = [145, 75, 81, 91, 95]


def parse_script(script_path):
    """Parse script file and extract (seq, speaker, text) tuples."""
    segments = []
    seq = 0
    with open(script_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            # Match pattern: H: text or G: text
            match = re.match(r"^([HG]):\s*(.+)$", line)
            if match:
                seq += 1
                speaker = match.group(1)
                text = match.group(2).strip()
                if text:
                    segments.append((seq, speaker, text))
    return segments


def generate_tts_segment(text, voice, output_path):
    """Generate a single TTS segment using edge-tts."""
    cmd = [
        EDGE_TTS_PATH,
        "--voice", voice,
        "--rate", RATE,
        "--text", text,
        "--write-media", str(output_path)
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"edge-tts failed: {result.stderr}")
    return output_path


def concatenate_segments(segment_paths, output_path):
    """Concatenate multiple mp3 files into one using ffmpeg."""
    # Create a concat demuxer input file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for seg_path in segment_paths:
            f.write(f"file '{seg_path}'\n")
        concat_file = f.name

    try:
        cmd = [
            FFMPEG_PATH,
            "-y",  # overwrite output
            "-f", "concat",
            "-safe", "0",
            "-i", concat_file,
            "-acodec", "libmp3lame",
            "-q:a", "2",
            str(output_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg concat failed: {result.stderr}")
    finally:
        os.unlink(concat_file)

    return output_path


def update_db(ep_number, podcast_file):
    """Update the database with podcast_file path and status='tts_done'."""
    # DB uses ep_number without 'ep' prefix (e.g., "145" not "ep145")
    clean_number = str(ep_number).replace("ep", "")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE episodes SET podcast_file = ?, status = 'tts_done', updated_at = datetime('now') WHERE ep_number = ?",
        (podcast_file, clean_number)
    )
    conn.commit()
    conn.close()


def process_episode(ep_number):
    """Process a single episode: parse script, generate TTS, concatenate, update DB."""
    script_path = os.path.join(SCRIPTS_DIR, f"{ep_number}_script.md")
    if not os.path.exists(script_path):
        print(f"  [SKIP] Script not found: {script_path}")
        return False

    print(f"\n{'='*60}")
    print(f"Processing {ep_number}")
    print(f"{'='*60}")

    # Parse script
    segments = parse_script(script_path)
    print(f"  Found {len(segments)} segments")
    if not segments:
        print(f"  [SKIP] No segments found in script")
        return False

    # Create temp directory for segments
    temp_dir = tempfile.mkdtemp(prefix=f"podcast_{ep_number}_")
    segment_paths = []

    try:
        # Generate TTS for each segment
        for i, (seq, speaker, text) in enumerate(segments):
            voice = VOICE_H if speaker == "H" else VOICE_G
            seg_filename = f"{seq:03d}_{speaker}.mp3"
            seg_path = os.path.join(temp_dir, seg_filename)

            print(f"  [{i+1}/{len(segments)}] Generating {seg_filename} ({len(text)} chars)...")
            try:
                generate_tts_segment(text, voice, seg_path)
                segment_paths.append(seg_path)
            except Exception as e:
                print(f"    [ERROR] Failed to generate segment {seg_filename}: {e}")
                # Continue with remaining segments

        if not segment_paths:
            print(f"  [ERROR] No segments were generated successfully")
            return False

        # Concatenate all segments
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        final_output = os.path.join(OUTPUT_DIR, f"{ep_number}.mp3")
        print(f"  Concatenating {len(segment_paths)} segments into {final_output}...")
        concatenate_segments(segment_paths, final_output)

        # Verify output
        if os.path.exists(final_output):
            size_mb = os.path.getsize(final_output) / (1024 * 1024)
            print(f"  Output: {final_output} ({size_mb:.1f} MB)")
        else:
            print(f"  [ERROR] Final output not created")
            return False

        # Update database
        update_db(ep_number, final_output)
        print(f"  Database updated: podcast_file={final_output}, status=tts_done")

        return True

    finally:
        # Clean up temp directory
        shutil.rmtree(temp_dir, ignore_errors=True)


def main():
    print("Podcast TTS Generator")
    print(f"Episodes: {', '.join(EPISODES)}")
    print(f"Output directory: {OUTPUT_DIR}")
    print(f"Database: {DB_PATH}")

    results = {}
    for ep in EPISODES:
        try:
            success = process_episode(ep)
            results[ep] = "SUCCESS" if success else "FAILED"
        except Exception as e:
            print(f"  [FATAL] {ep}: {e}")
            results[ep] = f"ERROR: {e}"

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    for ep, status in results.items():
        print(f"  {ep}: {status}")


if __name__ == "__main__":
    main()
