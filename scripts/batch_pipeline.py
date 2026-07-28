#!/usr/bin/env python3
"""
蛋播批量管线 — 编排完整工作流：
  下载 → 转录 → LLM改稿 → TTS → Obsidian笔记 → 发布

特性：
- 断点续传（xyz_pipeline.db 追踪状态）
- 小宇宙优先下载
- 每批 N 期，可并行 TTS
- 音频不保存，转录+文稿持久化

用法：
  python3 batch_pipeline.py --batch 144,143,142,141,140,139,138
  python3 batch_pipeline.py --batch 144,143,142 --skip-tts
  python3 batch_pipeline.py --status
"""

import argparse
import json
import os
import re
import sqlite3
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# --- Paths ---
PODCAST_DIR = Path.home() / ".claude/podcast"
DB_PATH = PODCAST_DIR / "xyz_pipeline.db"
DOWNLOAD_DIR = PODCAST_DIR / "xyz_downloads"
TRANSCRIPT_DIR = PODCAST_DIR / "transcripts"
SCRIPT_DIR = PODCAST_DIR / "scripts"  # 对话稿保存
NOTE_DIR = Path.home() / "Library/Mobile Documents/iCloud~md~obsidian/Documents/life-system/vault/20 Knowledge/Notes/GenAI Guide"
EPISODES_DIR = PODCAST_DIR / "episodes"

PODCAST_BRIDGE = Path.home() / ".hermes/skills/podcast/podcast-bridge"
TRANSCRIBE_PY = PODCAST_BRIDGE / "transcribe.py"
DOWNLOAD_PY = PODCAST_DIR / "scripts/download_episode.py"
VENV_PYTHON = PODCAST_BRIDGE / "venv" / "bin" / "python3"

# --- DB ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS episodes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ep_number INTEGER UNIQUE,
            title TEXT,
            video_id TEXT,
            source TEXT,
            status TEXT DEFAULT 'pending',
            audio_path TEXT,
            transcript_path TEXT,
            script_path TEXT,
            note_path TEXT,
            podcast_file TEXT,
            duration_sec INTEGER,
            score REAL,
            error_msg TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    return conn


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def db_upsert_episode(conn, ep_number, **kwargs):
    """Insert or update episode record"""
    keys = list(kwargs.keys())
    values = list(kwargs.keys())
    
    cur = conn.cursor()
    cur.execute("SELECT id FROM episodes WHERE ep_number = ?", (ep_number,))
    row = cur.fetchone()
    
    if row:
        set_clause = ", ".join(f"{k} = ?" for k in keys)
        set_clause += ", updated_at = CURRENT_TIMESTAMP"
        cur.execute(f"UPDATE episodes SET {set_clause} WHERE ep_number = ?", 
                    list(kwargs.values()) + [ep_number])
    else:
        cols = ", ".join(keys)
        placeholders = ", ".join("?" for _ in keys)
        cur.execute(f"INSERT INTO episodes (ep_number, {cols}) VALUES (?, {placeholders})",
                    [ep_number] + list(kwargs.values()))
    conn.commit()


def get_episode_status(conn, ep_number):
    cur = conn.cursor()
    cur.execute("SELECT status FROM episodes WHERE ep_number = ?", (ep_number,))
    row = cur.fetchone()
    return row['status'] if row else None


# --- Pipeline Steps ---
def step_download(ep_number):
    """下载音频，返回 (success, audio_path, title)"""
    result = subprocess.run(
        [sys.executable, str(DOWNLOAD_PY), "--ep", str(ep_number), "--output-dir", str(DOWNLOAD_DIR)],
        capture_output=True, text=True, timeout=600
    )
    
    if result.returncode != 0:
        return False, None, result.stderr
    
    # Parse output
    for line in result.stdout.split('\n'):
        if line.startswith("✅"):
            # Extract path
            m = re.search(r'路径:\s*(.+)', line)
            if m:
                return True, m.group(1).strip(), None
    
    return False, None, result.stdout


def step_transcribe(ep_number, audio_path):
    """转录音频，返回 (success, transcript_path)"""
    output_name = f"ep{ep_number}_transcript.md"
    output_path = TRANSCRIPT_DIR / output_name
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    
    result = subprocess.run(
        [str(VENV_PYTHON), str(TRANSCRIBE_PY), audio_path, "--chapters",
         "--asr-provider", "whisperx",
         "--output", str(output_path)],
        capture_output=True, text=True, timeout=3600
    )
    
    if result.returncode == 0 and output_path.exists():
        return True, str(output_path)
    
    # Check if output was created with different name
    candidates = list(TRANSCRIPT_DIR.glob(f"ep{ep_number}*.md"))
    if candidates:
        return True, str(candidates[0])
    
    return False, result.stderr


def step_generate_script(ep_number, transcript_path):
    """
    LLM改稿：转录文本 → 双人对话稿
    这里调用 delegate_task 让子 agent 处理
    """
    SCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = SCRIPT_DIR / f"ep{ep_number}_script.md"
    
    # Read transcript
    with open(transcript_path, 'r', encoding='utf-8') as f:
        transcript = f.read()
    
    # Truncate if too long (keep first 50K chars for context)
    if len(transcript) > 50000:
        transcript = transcript[:50000] + "\n\n... (转录过长，已截取前5万字)"
    
    # Build prompt for sub-agent
    prompt = f"""你是蛋播的写稿 AI。请将以下访谈转录改写成双人播客对话稿。

## 质量标准
- 音频控制在 15 分钟以内（约 70-80 段对话）
- 由浅入深：生活类比 → 原理剖析 → 为什么 → 举一反三
- 口语化，不用 Markdown 符号
- 英文术语转中文（KV Cache→键值缓存、MTP→多词元预测）
- 每段 2-4 句，不要太长

## 角色
- H（主持人）：提问者，代表听众，追问"为什么"
- G（嘉宾）：解释者，用类比和原理回答

## 格式
每行以 H: 或 G: 开头：
H: 大家好，欢迎收听蛋播...
G: 对，我先从一个生活场景说起...

## 结构
1. 开场引入（H）
2. 背景铺垫（G，用生活类比）
3. 核心概念 1-3 个（H问→G答，每个概念：类比→原理→为什么→举一反三）
4. 对比/争议
5. 对听众的意义
6. 总结告别

## 转录原文
{transcript}

---

请输出完整的 H:/G: 对话稿，写入文件：{output_path}
"""
    
    # Write prompt to temp file for sub-agent
    prompt_path = SCRIPT_DIR / f"ep{ep_number}_prompt.txt"
    with open(prompt_path, 'w', encoding='utf-8') as f:
        f.write(prompt)
    
    # Return the prompt path — actual LLM work done by parent orchestrator
    return str(prompt_path)


def step_generate_note(ep_number, transcript_path, script_path):
    """
    生成 Obsidian 学习笔记
    """
    NOTE_DIR.mkdir(parents=True, exist_ok=True)
    output_path = NOTE_DIR / f"ep{ep_number}_学习解读_{datetime.now().strftime('%Y-%m-%d')}.md"
    
    # Read inputs
    with open(transcript_path, 'r', encoding='utf-8') as f:
        transcript = f.read()
    
    script_text = ""
    if Path(script_path).exists():
        with open(script_path, 'r', encoding='utf-8') as f:
            script_text = f.read()
    
    # Truncate
    if len(transcript) > 30000:
        transcript = transcript[:30000] + "\n\n... (截取前3万字)"
    
    prompt = f"""你是蛋播的学习笔记撰写 AI。请根据以下转录和对话稿，撰写深度学习解读笔记。

## 质量标准
- 深入浅出：生活类比 → 直觉理解 → 原理机制 → 深层为什么 → 前沿延伸
- 每个新概念必须有生活类比 + 原理解释 + 举一反三
- 刨根问底：至少追问 3 层为什么
- 内容尽可能详细，不要浮于表面
- 250-400 行

## 文档结构

# {{主题}} — 学习解读

> 来源：张小珺商业访谈录 #{{期号}}
> 嘉宾：{{姓名}}（{{身份}}）
> 原始发布：{{日期}}
> 转录：[[{{转录文件名}}]]

---

## 一句话：这期到底在讲什么

## 从你最熟悉的东西开始

## 核心概念（由浅入深）

### 概念1：{{名称}}
**类比**：{{生活类比}}
**原理**：{{底层机制}}
**为什么不用老方法**：{{之前的方案及其局限}}
**刨根问底**：{{更深层的为什么}}
**举一反三**：{{跨领域映射}}

## 关键洞察

## 和我的知识体系的连接

## 还没想明白的问题

## 含金量评分（满分 10 分）

从以下维度打分：
- 信息密度（是否有独到见解 vs 老生常谈）
- 深度（是否触及底层原理 vs 浮于表面）
- 实用性（对实际工作/投资是否有指导意义）
- 启发性（是否引发新的思考方向）
- 嘉宾权威性（是否是该领域一线实践者）

给出总分和理由。

## 一句话总结

---

## 转录原文
{transcript}

## 对话稿（如有）
{script_text}

---

请输出完整的学习解读笔记，写入文件：{output_path}
"""
    
    prompt_path = SCRIPT_DIR / f"ep{ep_number}_note_prompt.txt"
    with open(prompt_path, 'w', encoding='utf-8') as f:
        f.write(prompt)
    
    return str(prompt_path)


def step_tts(ep_number, script_path):
    """TTS 生成播客音频"""
    if not Path(script_path).exists():
        return False, "对话稿不存在"
    
    # Read script
    with open(script_path, 'r', encoding='utf-8') as f:
        script = f.read()
    
    # Parse H:/G: lines
    lines = []
    for line in script.split('\n'):
        line = line.strip()
        if line.startswith('H:') or line.startswith('G:'):
            lines.append(line)
    
    if not lines:
        return False, "对话稿格式错误"
    
    # Generate TTS segments
    segments_dir = EPISODES_DIR / f"ep{ep_number}_segments"
    segments_dir.mkdir(parents=True, exist_ok=True)
    
    EDGE_TTS = Path.home() / ".hermes/hermes-agent/venv/bin/edge-tts"
    VOICE_H = "zh-CN-YunyangNeural"
    VOICE_G = "zh-CN-XiaoxiaoNeural"
    
    for i, line in enumerate(lines):
        speaker = line[0]  # H or G
        text = line[2:].strip()
        if not text:
            continue
        
        voice = VOICE_H if speaker == 'H' else VOICE_G
        seg_path = segments_dir / f"{i:03d}_{speaker}.mp3"
        
        if not seg_path.exists():
            subprocess.run([
                str(EDGE_TTS), "--voice", voice, "--rate", "+5%",
                "--text", text, "--write-media", str(seg_path)
            ], capture_output=True, timeout=30)
    
    # Concatenate
    concat_list = segments_dir / "filelist.txt"
    with open(concat_list, 'w') as f:
        for i in range(len(lines)):
            seg = segments_dir / f"{i:03d}_H.mp3"
            if seg.exists():
                f.write(f"file '{seg.name}'\n")
            seg = segments_dir / f"{i:03d}_G.mp3"
            if seg.exists():
                f.write(f"file '{seg.name}'\n")
    
    output_file = EPISODES_DIR / f"ep{ep_number}-dual-{datetime.now().strftime('%Y%m%d')}.mp3"
    result = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_list), "-c", "copy", str(output_file)
    ], capture_output=True, timeout=120)
    
    if output_file.exists():
        return True, str(output_file)
    
    return False, result.stderr.decode()


# --- Main Pipeline ---
def run_pipeline(ep_numbers, skip_tts=False, skip_note=False):
    conn = get_db()
    
    print(f"{'='*60}")
    print(f"蛋播批量管线 — 处理 {len(ep_numbers)} 期")
    print(f"{'='*60}")
    print()
    
    for ep in ep_numbers:
        status = get_episode_status(conn, ep)
        print(f"── #{ep} (当前状态: {status}) ──")
        
        # Step 1: Download
        if status in (None, 'pending', 'download_failed'):
            print(f"  下载音频...")
            ok, audio_path, err = step_download(ep)
            if ok:
                db_upsert_episode(conn, ep, status='downloaded', audio_path=audio_path)
                print(f"  ✅ 下载完成: {audio_path}")
                status = 'downloaded'
            else:
                db_upsert_episode(conn, ep, status='download_failed', error_msg=str(err))
                print(f"  ❌ 下载失败: {err}")
                continue
        
        # Step 2: Transcribe
        if status in ('downloaded', 'transcribe_failed'):
            audio_path = None
            cur = conn.cursor()
            cur.execute("SELECT audio_path FROM episodes WHERE ep_number = ?", (ep,))
            row = cur.fetchone()
            if row:
                audio_path = row['audio_path']
            
            if audio_path and Path(audio_path).exists():
                print(f"  转录中...")
                ok, transcript_path = step_transcribe(ep, audio_path)
                if ok:
                    db_upsert_episode(conn, ep, status='transcribed', transcript_path=transcript_path)
                    print(f"  ✅ 转录完成: {transcript_path}")
                    status = 'transcribed'
                else:
                    db_upsert_episode(conn, ep, status='transcribe_failed', error_msg=str(transcript_path))
                    print(f"  ❌ 转录失败")
                    continue
            else:
                print(f"  ⚠️ 音频文件不存在，跳过")
                continue
        
        # Step 3: Generate Script (prompt for sub-agent)
        if status == 'transcribed':
            cur = conn.cursor()
            cur.execute("SELECT transcript_path FROM episodes WHERE ep_number = ?", (ep,))
            row = cur.fetchone()
            transcript_path = row['transcript_path'] if row else None
            
            if transcript_path:
                prompt_path = step_generate_script(ep, transcript_path)
                db_upsert_episode(conn, ep, status='script_pending', script_path=prompt_path)
                print(f"  📝 改稿 prompt 已生成: {prompt_path}")
                print(f"  ⚠️ 需要 LLM 处理改稿（由 orchestrator 执行）")
                status = 'script_pending'
        
        # Step 4: TTS
        if not skip_tts and status == 'script_done':
            cur = conn.cursor()
            cur.execute("SELECT script_path FROM episodes WHERE ep_number = ?", (ep,))
            row = cur.fetchone()
            script_path = row['script_path'] if row else None
            
            if script_path and Path(script_path).exists():
                print(f"  TTS 生成中...")
                ok, result = step_tts(ep, script_path)
                if ok:
                    db_upsert_episode(conn, ep, status='tts_done', podcast_file=result)
                    print(f"  ✅ TTS 完成: {result}")
                    status = 'tts_done'
                else:
                    print(f"  ❌ TTS 失败: {result}")
        
        print()
    
    # Summary
    print(f"{'='*60}")
    print("管线状态汇总:")
    cur = conn.cursor()
    cur.execute("SELECT status, COUNT(*) FROM episodes GROUP BY status")
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]}")
    print(f"{'='*60}")
    
    conn.close()


def show_status():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT ep_number, title, status, score FROM episodes ORDER BY ep_number DESC")
    rows = cur.fetchall()
    
    print(f"蛋播管线状态 ({len(rows)} 期)")
    print(f"{'='*60}")
    for row in rows:
        score_str = f"({row['score']}/10)" if row['score'] else ""
        print(f"  #{row['ep_number']:>3} | {row['status']:>15} | {score_str} | {row['title'][:40] if row['title'] else ''}")
    conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="蛋播批量管线")
    parser.add_argument("--batch", type=str, help="逗号分隔期号")
    parser.add_argument("--status", action="store_true", help="查看状态")
    parser.add_argument("--skip-tts", action="store_true", help="跳过 TTS")
    parser.add_argument("--skip-note", action="store_true", help="跳过笔记")
    args = parser.parse_args()
    
    if args.status:
        show_status()
    elif args.batch:
        eps = [int(e.strip()) for e in args.batch.split(",")]
        run_pipeline(eps, skip_tts=args.skip_tts, skip_note=args.skip_note)
    else:
        parser.print_help()
