#!/usr/bin/env python3
"""
检查 podcast-bridge 库是否有对应的小宇宙音频直链。
如果有，返回音频 URL（优先使用）；如果没有，返回 None，由调用方走 yt-dlp 下载 YouTube。

原理：
1. podcast-bridge 的 library.sqlite3 已经同步了张小珺在 RSS/小宇宙的 50 期
2. 每期的 title 含期号（如 "145. 口述SpaceX..."），audio_url 是直链
3. 通过期号匹配，可以避免重复下载 YouTube 视频

用法：
  python3 check_xiaoyuzhou.py --ep 145
  # 输出: https://dts-api.xiaoyuzhoufm.com/track/...  (或 NOT_FOUND)
"""

import argparse
import re
import sqlite3
import sys
from pathlib import Path

# podcast-bridge library path
PODCAST_BRIDGE_DB = Path.home() / ".hermes/skills/podcast/podcast-bridge/podcast_library/library.sqlite3"


from typing import Optional

def find_xiaoyuzhou_audio(ep_number: int) -> Optional[dict]:
    """
    根据张小珺期号，查找小宇宙音频信息。
    
    Returns:
        dict with 'audio_url', 'page_url', 'title' or None
    """
    if not PODCAST_BRIDGE_DB.exists():
        return None
    
    conn = sqlite3.connect(PODCAST_BRIDGE_DB)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 张小珺的 subscription_id = 1
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


def list_available_episodes() -> list[int]:
    """列出 podcast-bridge 中所有可用的张小珺期号"""
    if not PODCAST_BRIDGE_DB.exists():
        return []
    
    conn = sqlite3.connect(PODCAST_BRIDGE_DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT title FROM episodes WHERE subscription_id = 1
    """)
    
    episodes = []
    for row in cur.fetchall():
        m = re.search(r'^(\d+)\.', row[0] or '')
        if m:
            episodes.append(int(m.group(1)))
    
    conn.close()
    return sorted(episodes, reverse=True)


def main():
    parser = argparse.ArgumentParser(description="Check Xiaoyuzhou audio availability")
    parser.add_argument("--ep", type=int, help="Episode number to check")
    parser.add_argument("--list", action="store_true", help="List all available episodes")
    parser.add_argument("--check-batch", type=str, help="Check multiple episodes (comma-separated, e.g. 144,143,142)")
    args = parser.parse_args()
    
    if args.list:
        eps = list_available_episodes()
        print(f"小宇宙可用张小珺期数: {len(eps)}")
        print(f"期数: {eps}")
        return
    
    if args.ep:
        result = find_xiaoyuzhou_audio(args.ep)
        if result:
            print(f"FOUND")
            print(f"audio_url: {result['audio_url']}")
            print(f"page_url:  {result['page_url']}")
            print(f"title:     {result['title']}")
        else:
            print("NOT_FOUND")
        return
    
    if args.check_batch:
        eps = [int(e.strip()) for e in args.check_batch.split(",")]
        for ep in eps:
            result = find_xiaoyuzhou_audio(ep)
            status = "✅ 小宇宙" if result else "❌ 需YouTube"
            print(f"  #{ep:>3}: {status}")
        return
    
    parser.print_help()


if __name__ == "__main__":
    main()
