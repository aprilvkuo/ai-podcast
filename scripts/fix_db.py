#!/usr/bin/env python3
import sqlite3
from pathlib import Path

DB = "xyz_pipeline.db"
TRANS_DIR = Path("transcripts")

conn = sqlite3.connect(DB)
cur = conn.cursor()

# 扫描所有转录文件，更新 DB
for f in sorted(TRANS_DIR.glob("ep*_transcript.md")):
    stem = f.stem  # e.g. ep103_transcript
    ep_str = stem.split("_")[0][2:]  # e.g. 103
    if ep_str.isdigit():
        ep = int(ep_str)
        size = f.stat().st_size
        cur.execute("SELECT status FROM episodes WHERE ep_number=?", (ep,))
        row = cur.fetchone()
        if row and row[0] != "transcribed":
            cur.execute("UPDATE episodes SET status='transcribed', transcript_path=?, updated_at=CURRENT_TIMESTAMP WHERE ep_number=?",
                        (str(f), ep))
            print(f"  ep{ep}: {row[0]} → transcribed ({size/1024:.0f}KB)")

conn.commit()

# 显示状态
cur.execute('SELECT status, COUNT(*) c FROM episodes GROUP BY status ORDER BY c DESC')
print("\n当前状态:")
for row in cur.fetchall():
    print(f"  {row[0]}: {row[1]}期")

cur.execute('SELECT ep_number FROM episodes WHERE status="downloaded" ORDER BY ep_number')
print("\n待转录:", [r[0] for r in cur.fetchall()])

conn.close()
