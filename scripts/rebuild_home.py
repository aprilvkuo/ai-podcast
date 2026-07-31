#!/usr/bin/env python3
"""Rebuild index.html as xiaoyuzhou-style light horizontal list."""
import json

EPS = json.load(open('/Users/egg/.claude/podcast/scripts/eps_data.json'))
assert len(EPS) == 72, f"Expected 72, got {len(EPS)}"

def gradient(i):
    """Soft pastel gradient for thumbnail, cycling through hues."""
    hues = [18, 210, 160, 280, 40, 320, 90, 200]  # orange, blue, green, purple, amber, pink, lime, cyan
    h = hues[i % len(hues)]
    # slightly vary lightness per index for variety within same group
    l1 = 86 + (i % 4) * 3   # 86-95
    l2 = 66 + (i % 5) * 4   # 66-82
    c1 = f"hsl({h}, 72%, {l1}%)"
    c2 = f"hsl({(h+40)%360}, 78%, {l2}%)"
    angle = (i * 29) % 360
    return f"linear-gradient({angle}deg, {c1}, {c2})"

def thumb_text(ep_num, i):
    # strip "EP" prefix, show number
    return ep_num.replace('EP', '#')

def desc_html(r):
    d = r['desc'].strip()
    if not d:
        return ""
    return f'''      <p class="desc">{d}</p>\n'''

def card(r, i):
    return f'''    <div class="ep" data-url="{r['url']}" data-index="{i}">
      <div class="thumb" style="background:{gradient(i)}">{thumb_text(r['ep_num'], i)}</div>
      <div class="info">
        <h3 class="ep-title">{r['title']}</h3>
        <span class="source">{r['source']}</span>
{desc_html(r)}\
        <div class="meta"><span class="ep-date">{r['ep_date']}</span><span class="meta-dot">·</span><span class="dur">{r['dur']}</span></div>
      </div>
      <div class="actions">
        <button class="play-btn" onclick="playEp(this, '{r['url']}')">▶</button>
      </div>
      <button class="expand-btn" onclick="toggleNote(this)">📖 笔记</button>
      <div class="note-content" style="display:none">
        <div class="note-inner">
{r['note_inner']}
        </div>
      </div>
    </div>
'''
    
CSS = """* { margin:0; padding:0; box-sizing:border-box; }
body { font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB",Roboto,sans-serif; background:#fafafa; color:#222; min-height:100vh; -webkit-font-smoothing:antialiased; }
.container { max-width:760px; margin:0 auto; padding:24px 16px 130px; }
header { text-align:center; padding:40px 0 28px; }
header img { width:96px; height:96px; border-radius:22px; margin-bottom:14px; box-shadow:0 6px 20px rgba(0,0,0,.08); }
header h1 { font-size:26px; color:#111; margin-bottom:6px; letter-spacing:.5px; }
header p { color:#666; font-size:14px; line-height:1.6; }
.subscribe-box { display:flex; flex-direction:column; align-items:center; gap:8px; margin-top:18px; }
.subscribe { display:inline-flex; align-items:center; gap:8px; padding:10px 24px; background:#f97316; color:#fff; border:none; border-radius:24px; text-decoration:none; font-size:14px; font-weight:600; cursor:pointer; transition:transform .15s,box-shadow .15s; box-shadow:0 4px 14px rgba(249,115,22,.25); }
.subscribe:hover { background:#ea580c; transform:translateY(-1px); }
.sub-hint { color:#999; font-size:12px; }
.search-box { width:100%; max-width:380px; margin-top:18px; padding:11px 16px; border:1px solid #e5e5e5; border-radius:24px; font-size:14px; color:#333; background:#fff; box-shadow:0 1px 3px rgba(0,0,0,.04); transition:border-color .15s,box-shadow .15s; }
.search-box:focus { outline:none; border-color:#f97316; box-shadow:0 0 0 3px rgba(249,115,22,.15); }
.search-box::placeholder { color:#aaa; }
.no-results { text-align:center; color:#999; font-size:14px; padding:40px 0; display:none; }
.ep { display:grid; grid-template-columns:64px 1fr auto; grid-template-areas:"thumb info play" "thumb info expand" "note note note"; align-items:center; gap:12px 14px; background:#fff; border-radius:14px; padding:14px 16px; margin-bottom:10px; border:1px solid #f0f0f0; box-shadow:0 1px 2px rgba(0,0,0,.03); transition:box-shadow .15s,transform .15s,border-color .15s; cursor:pointer; }
.ep:hover { box-shadow:0 4px 14px rgba(0,0,0,.06); border-color:#e8e8e8; transform:translateY(-1px); }
.ep .thumb { grid-area:thumb; width:64px; height:64px; border-radius:12px; display:flex; align-items:center; justify-content:center; color:#111; font-size:20px; font-weight:800; letter-spacing:.5px; box-shadow:inset 0 0 0 1px rgba(0,0,0,.04); }
.ep .info { grid-area:info; min-width:0; }
.ep .play-btn { grid-area:play; justify-self:end; align-self:center; }
.ep-title { font-size:16px; color:#111; font-weight:600; line-height:1.4; margin-bottom:4px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.source { display:block; color:#9a3412; font-size:12px; margin-bottom:4px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.desc { color:#666; font-size:13px; line-height:1.5; margin-bottom:4px; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
.meta { color:#999; font-size:12px; display:flex; align-items:center; gap:6px; }
.meta-dot { color:#d0d0d0; }
.actions { display:contents; }
.play-btn { grid-area:play; width:46px; height:46px; border-radius:50%; border:none; background:#f97316; color:#fff; font-size:16px; cursor:pointer; display:flex; align-items:center; justify-content:center; transition:background .15s,transform .15s; box-shadow:0 3px 10px rgba(249,115,22,.25); }
.play-btn:hover { background:#ea580c; transform:scale(1.05); }
.play-btn.playing { background:#ea580c; }
.expand-btn { grid-area:expand; justify-self:end; background:none; border:1px solid #e0e0e0; color:#555; padding:4px 12px; border-radius:16px; cursor:pointer; font-size:12px; transition:all .15s; white-space:nowrap; }
.expand-btn:hover { border-color:#4a9eff; color:#4a9eff; background:#f5f9ff; }
.expand-btn.active { background:#4a9eff; border-color:#4a9eff; color:#fff; }
.note-content { grid-area:note; width:100%; margin-top:8px; padding:14px 4px 2px; border-top:1px solid #f0f0f0; }
.note-inner { font-size:14px; line-height:1.8; color:#333; }
.note-inner h2 { color:#111; font-size:18px; margin:20px 0 10px; }
.note-inner h3 { color:#1a1a1a; font-size:16px; margin:16px 0 8px; }
.note-inner h4 { color:#222; font-size:14px; margin:12px 0 6px; }
.note-inner p { margin:8px 0; }
.note-inner ul { margin:8px 0; padding-left:20px; }
.note-inner li { margin:4px 0; }
.note-inner blockquote { border-left:3px solid #f97316; padding-left:12px; color:#555; margin:10px 0; background:#fff7ed; padding:10px 12px; border-radius:0 8px 8px 0; }
.note-inner pre { background:#f6f6f6; padding:12px; border-radius:8px; overflow-x:auto; margin:10px 0; }
.note-inner code { font-family:monospace; font-size:13px; color:#c62828; }
.note-inner b { color:#111; }
.player { position:fixed; bottom:0; left:0; right:0; background:#fff; border-top:1px solid #eee; padding:12px 16px; display:none; align-items:center; gap:12px; z-index:100; box-shadow:0 -4px 20px rgba(0,0,0,.06); }
.player.show { display:flex; }
.player .p-title { flex:1; font-size:13px; color:#333; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.player audio { flex:2; height:40px; }
@media (max-width:520px) {
  .container { padding:16px 10px 130px; }
  .ep { grid-template-columns:52px 1fr auto; gap:10px 10px; padding:12px; }
  .ep .thumb { width:52px; height:52px; font-size:16px; }
  .ep-title { font-size:15px; }
  .play-btn { width:40px; height:40px; font-size:15px; }
  header img { width:80px; height:80px; }
}"""

HEAD = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>蛋播</title>
<style>
""" + CSS + """
</style>
</head>
<body>
<div class="container">
  <header>
    <div class="subscribe-box">
      <img src="cover.jpg" alt="蛋播">
    </div>
    <h1>蛋播</h1>
    <p>Egg 的 AI 技术播客，用类比和原理剖析理解前沿技术</p>
    <input type="search" class="search-box" id="searchInput" placeholder="搜索节目..." oninput="searchEpisodes()" autocomplete="off">
    <div class="subscribe-box">
      <button class="subscribe" onclick="copyRSS()">📋 复制 RSS 链接</button>
      <p class="sub-hint">复制后到 小宇宙 / Apple Podcasts / Spotify 中「添加 RSS 订阅」</p>
    </div>
  </header>
"""

TAIL = """  <div class="no-results" id="noResults">🔍 无匹配结果</div>
</div>
<div class="player" id="player">
  <span class="p-title" id="p-title"></span>
  <audio id="audio" controls></audio>
</div>
<script>
function playEp(btn, url) {
  if (!url) { return; }
  const player = document.getElementById('player');
  const audio = document.getElementById('audio');
  const pTitle = document.getElementById('p-title');
  const title = btn.closest('.ep').querySelector('.ep-title').textContent;
  document.querySelectorAll('.play-btn').forEach(b => { b.classList.remove('playing'); b.textContent = '▶'; });
  btn.classList.add('playing'); btn.textContent = '⏸';
  pTitle.textContent = title;
  audio.src = url;
  player.classList.add('show');
  audio.play();
}
function copyRSS() {
  const url = 'https://aprilvkuo.github.io/ai-podcast//feed.rss';
  navigator.clipboard.writeText(url).then(() => {
    const btn = document.querySelector('.subscribe');
    btn.textContent = '✅ 已复制！去播客App粘贴';
    setTimeout(() => { btn.textContent = '📋 复制 RSS 链接'; }, 3000);
  }).catch(() => {
    prompt('手动复制 RSS 链接：', url);
  });
}
function toggleNote(btn) {
  const note = btn.nextElementSibling;
  const isOpen = note.style.display !== 'none';
  note.style.display = isOpen ? 'none' : 'block';
  btn.textContent = isOpen ? '📖 笔记' : '📕 收起';
  btn.classList.toggle('active');
}
function searchEpisodes() {
  const q = (document.getElementById('searchInput').value || '').trim().toLowerCase();
  const cards = document.querySelectorAll('.ep');
  let shown = 0;
  cards.forEach(card => {
    const text = (card.querySelector('.ep-title').textContent + ' ' + (card.querySelector('.desc')?.textContent || '')).toLowerCase();
    const match = q === '' || text.indexOf(q) !== -1;
    card.style.display = match ? '' : 'none';
    if (match) shown++;
  });
  const empty = document.getElementById('noResults');
  if (empty) empty.style.display = (q !== '' && shown === 0) ? 'block' : 'none';
}
</script>
</body>
</html>
"""

cards = [card(r, i) for i, r in enumerate(EPS)]
out = HEAD + "\n" + "\n".join(cards) + "\n" + TAIL
with open('/Users/egg/.claude/podcast/index.html', 'w', encoding='utf-8') as f:
    f.write(out)

# Verification stats
import re
print("New file written. Stats:")
print("ep count:", out.count('class="ep"'))
print("note-content count:", out.count('class="note-content"'))
print("playEp onclicks:", out.count('playEp(this'))
print("toggleNote onclicks:", out.count('toggleNote(this'))
print("data-url count:", out.count('data-url="'))
print("unique data-urls:", len(set(re.findall(r'data-url="([^"]*)"', out))))
# verify note content total matches extracted
total_note_chars_in_out = sum(len(r['note_inner']) for r in EPS)
print("Total note chars expected:", total_note_chars_in_out)
