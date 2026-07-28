#!/usr/bin/env python3
"""
智能下载脚本：优先小宇宙直链，否则回退到 YouTube。

用法：
  python3 download_episode.py --ep 145
  python3 download_episode.py --ep 145 --output-dir /path/to/dir
  python3 download_episode.py --batch 144,143,142,141,140,139,138
"""

import argparse
import json
import re
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional, Dict

PODCAST_BRIDGE_DB = Path.home() / ".hermes/skills/podcast/podcast-bridge/podcast_library/library.sqlite3"
DEFAULT_OUTPUT_DIR = Path.home() / ".claude/podcast/xyz_downloads"


def find_xiaoyuzhou_audio(ep_number: int) -> Optional[Dict]:
    """查找小宇宙音频直链"""
    if not PODCAST_BRIDGE_DB.exists():
        return None
    
    conn = sqlite3.connect(PODCAST_BRIDGE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT episode_no, title, audio_url, episode_url
        FROM episodes
        WHERE subscription_id = 1
        ORDER BY published_at DESC
    """)
    
    for row in cur.fetchall():
        title = row['title'] or ''
        m = re.search(r'^(\d+)\.', title)
        if m and int(m.group(1)) == ep_number:
            conn.close()
            return {
                'audio_url': row['audio_url'],
                'page_url': row['episode_url'],
                'title': title,
            }
    
    conn.close()
    return None


def get_youtube_url(ep_number: int) -> Optional[str]:
    """从播放列表获取 YouTube URL（需要 yt-dlp）"""
    playlist_url = "https://www.youtube.com/playlist?list=PLwAchVoh-4zNSI5UlKEkKCL5r_jJyrFeO"
    try:
        result = subprocess.run(
            ["yt-dlp", "--flat-playlist", "--print", "%(playlist_index)s | %(id)s | %(title)s",
             playlist_url],
            capture_output=True, text=True, timeout=60
        )
        for line in result.stdout.split('\n'):
            parts = line.split('|')
            if len(parts) >= 3:
                title = parts[2].strip()
                m = re.search(r'^(\d+)\.', title)
                if m and int(m.group(1)) == ep_number:
                    video_id = parts[1].strip()
                    return f"https://www.youtube.com/watch?v={video_id}"
    except Exception as e:
        print(f"  警告：获取 YouTube URL 失败: {e}", file=sys.stderr)
    return None


def download_from_xiaoyuzhou(audio_url: str, output_path: Path) -> bool:
    """从小宇宙下载音频"""
    try:
        result = subprocess.run(
            ["curl", "-L", "-o", str(output_path), audio_url],
            capture_output=True, text=True, timeout=300
        )
        return result.returncode == 0 and output_path.exists()
    except Exception as e:
        print(f"  小宇宙下载失败: {e}", file=sys.stderr)
        return False


def download_from_youtube(youtube_url: str, output_path: Path) -> bool:
    """从 YouTube 下载音频"""
    try:
        result = subprocess.run(
            ["yt-dlp", "-f", "bestaudio[ext=m4a]", "--no-playlist",
             "-o", str(output_path), youtube_url],
            capture_output=True, text=True, timeout=600
        )
        return result.returncode == 0 and output_path.exists()
    except Exception as e:
        print(f"  YouTube 下载失败: {e}", file=sys.stderr)
        return False


def download_episode(ep_number: int, output_dir: Path) -> dict:
    """
    智能下载单期音频。
    
    Returns:
        dict with 'success', 'source', 'path', 'title'
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. 检查是否已存在
    existing = list(output_dir.glob(f"ep{ep_number}_*.m4a"))
    if existing:
        return {
            'success': True,
            'source': 'cached',
            'path': str(existing[0]),
            'title': None,
        }
    
    # 2. 优先小宇宙
    xiaoyuzhou = find_xiaoyuzhou_audio(ep_number)
    if xiaoyuzhou and xiaoyuzhou['audio_url']:
        print(f"  #{ep_number}: 小宇宙直链 → 下载中...")
        output_path = output_dir / f"ep{ep_number}_xiaoyuzhou.m4a"
        if download_from_xiaoyuzhou(xiaoyuzhou['audio_url'], output_path):
            return {
                'success': True,
                'source': 'xiaoyuzhou',
                'path': str(output_path),
                'title': xiaoyuzhou['title'],
            }
        print(f"  小宇宙下载失败，回退到 YouTube...")
    
    # 3. 回退 YouTube
    youtube_url = get_youtube_url(ep_number)
    if youtube_url:
        print(f"  #{ep_number}: YouTube → 下载中...")
        output_path = output_dir / f"ep{ep_number}_youtube.m4a"
        if download_from_youtube(youtube_url, output_path):
            return {
                'success': True,
                'source': 'youtube',
                'path': str(output_path),
                'title': None,
            }
    
    return {
        'success': False,
        'source': 'failed',
        'path': None,
        'title': None,
    }


def main():
    parser = argparse.ArgumentParser(description="智能下载播客音频（优先小宇宙）")
    parser.add_argument("--ep", type=int, help="单期下载")
    parser.add_argument("--batch", type=str, help="批量下载（逗号分隔期号）")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args()
    
    if args.ep:
        ep_number = args.ep
        result = download_episode(ep_number, args.output_dir)
        if result['success']:
            print(f"✅ #{ep_number} 下载完成 ({result['source']})")
            print(f"   路径: {result['path']}")
        else:
            print(f"❌ #{ep_number} 下载失败")
    
    elif args.batch:
        eps = [int(e.strip()) for e in args.batch.split(",")]
        print(f"批量下载 {len(eps)} 期: {eps}")
        print()
        
        results = []
        for ep in eps:
            result = download_episode(ep, args.output_dir)
            results.append((ep, result))
            status = "✅" if result['success'] else "❌"
            source = result['source']
            print(f"  {status} #{ep:>3}: {source}")
        
        # 汇总
        success = sum(1 for _, r in results if r['success'])
        from_xiaoyuzhou = sum(1 for _, r in results if r['source'] == 'xiaoyuzhou')
        from_youtube = sum(1 for _, r in results if r['source'] == 'youtube')
        cached = sum(1 for _, r in results if r['source'] == 'cached')
        
        print()
        print(f"完成: {success}/{len(eps)}")
        print(f"  小宇宙: {from_xiaoyuzhou} | YouTube: {from_youtube} | 缓存: {cached}")
    
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
