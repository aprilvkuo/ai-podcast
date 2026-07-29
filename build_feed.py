#!/usr/bin/env python3
"""Rebuild feed.rss and index.html, then git push."""
import sqlite3, json, os, subprocess
from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape

BASE = Path("/Users/egg/.claude/podcast")
DB = BASE / "xyz_pipeline.db"
FEED = BASE / "feed.rss"
INDEX = BASE / "index.html"
SITE = "https://aprilvkuo.github.io/ai-podcast"
COVER = f"{SITE}/cover.jpg"

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Get published episodes
cur.execute("SELECT * FROM episodes WHERE status='published' ORDER BY ep_number DESC")
rows = cur.fetchall()

# Build RSS
items = []
for row in rows:
    ep = row['ep_number']
    title = row['title']
    audio = row['podcast_file']
    
    if not audio or not os.path.exists(audio):
        continue
    
    audio_url = f"{SITE}/episodes/{os.path.basename(audio)}"
    pub_date = row['processed_at'] or row['created_at'] or datetime.now().isoformat()
    
    # Get note content for description
    desc = f"第{ep}期：{title}"
    
    item = f"""  <item>
    <title><![CDATA[第{ep}期：{title}]]></title>
    <link>{SITE}/?ep={ep}</link>
    <guid isPermaLink="false">{SITE}/ep{ep}</guid>
    <pubDate>{pub_date}</pubDate>
    <description><![CDATA[{desc}]]></description>
    <enclosure url="{audio_url}" length="0" type="audio/mpeg"/>
  </item>"""
    items.append(item)

rss = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:itunes="http://www.itunes.com/dtds/podcast-1.0.dtd">
  <channel>
    <title>蛋播</title>
    <link>{SITE}</link>
    <description>AI与科技播客，用声音解读前沿技术</description>
    <language>zh-cn</language>
    <itunes:author>蛋播</itunes:author>
    <itunes:image href="{COVER}"/>
    {''.join(items)}
  </channel>
</rss>"""

FEED.write_text(rss, encoding='utf-8')
print(f"✅ feed.rss: {len(rows)} episodes")

# Build index.html
html_items = []
for row in rows:
    ep = row['ep_number']
    title = row['title']
    audio = row['podcast_file']
    if not audio:
        continue
    audio_url = f"episodes/{os.path.basename(audio)}"
    html_items.append(f"""  <div class="episode">
    <h3>第{ep}期：{escape(title)}</h3>
    <audio controls src="{audio_url}"></audio>
  </div>""")

html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>蛋播</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; background: #f5f5f7; }}
    h1 {{ color: #1d1d1f; }}
    .episode {{ background: white; border-radius: 12px; padding: 16px; margin: 12px 0; }}
    audio {{ width: 100%; }}
  </style>
</head>
<body>
  <h1>🥚 蛋播</h1>
  <p>AI与科技播客</p>
  {''.join(html_items)}
</body>
</html>"""

INDEX.write_text(html, encoding='utf-8')
print("✅ index.html")

# Check if site has a git repo
repo_path = BASE / ".git"
if repo_path.exists():
    r = subprocess.run(["git", "add", "-A"], cwd=str(BASE), capture_output=True, text=True, timeout=10)
    r = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=str(BASE), capture_output=True, timeout=10)
    if r.returncode != 0:
        r = subprocess.run(["git", "commit", "-m", f"ep{rows[0]['ep_number'] if rows else 149} published"], 
                         cwd=str(BASE), capture_output=True, text=True, timeout=10)
        print(r.stdout.strip()[-200:])
        r = subprocess.run(["git", "push"], cwd=str(BASE), capture_output=True, text=True, timeout=30)
        print(r.stdout.strip()[-200:] if r.stdout else r.stderr.strip()[-200:])
    else:
        print("No changes to push")
else:
    print("No git repo found")

conn.close()
