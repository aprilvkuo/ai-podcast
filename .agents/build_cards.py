#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批量构建蛋播 index.html 卡片 & feed.rss item。

用法:
  python3 build_cards.py --sample ep96   # 只生成 ep96 卡片的 HTML 到 stdout 用于验证
  python3 build_cards.py --apply          # 实际写回 index.html / feed.rss
"""
import json, os, re, subprocess, sys, datetime, glob
from md2html import md_to_html, process_inline

ROOT = '/Users/egg/.claude/podcast'
META = '/tmp/publish_metadata.json'
NOTEDIR = '/Users/egg/Library/Mobile Documents/iCloud~md~obsidian/Documents/life-system/vault/20 Knowledge/Notes/GenAI Guide'
INDEX = os.path.join(ROOT, 'index.html')
FEED = os.path.join(ROOT, 'feed.rss')
SITE = 'https://aprilvkuo.github.io/ai-podcast'

def get_duration(audio):
    """audio 是 metadata 里的 audio 文件名。返回格式化时长。"""
    p = os.path.join(ROOT, 'episodes', audio)
    if not os.path.exists(p):
        # 本地无音频时的合理估算（渲染音频约 10 分钟）
        return '~10min'
    try:
        out = subprocess.run(['afinfo', p], capture_output=True, text=True).stdout
        m = re.search(r'estimated duration:\s*([\d.]+)', out)
        sec = float(m.group(1)) if m else None
        if sec is None:
            return '~10min'
        sec = int(round(sec))
        mm, ss = divmod(sec, 60)
        hh, mm2 = divmod(mm, 60)
        if hh > 0:
            return '%d:%02d:%02d' % (hh, mm2, ss)
        return '%d:%02d' % (mm, ss)
    except Exception:
        return '~10min'

def read_note(d):
    if not d.get('note_exists'):
        return None, None
    p = d['note_path']
    if not os.path.exists(p):
        return None, None
    return open(p, encoding='utf-8').read(), p

def extract_source(md):
    """从笔记提取来源行文本。支持多种格式：
       '> 来源：xx' | '来源：xx' | '## 来源' 后跟内容行 | '- **来源**：xx' | '## 来源\\n- bullet'
    """
    lines = md.split('\n')
    for idx, line in enumerate(lines):
        s = line.strip()
        # 1) '## 来源' 标题：取其后第一个非空且非标题、非'转录'开头的行
        if re.match(r'#{1,6}\s*来源', s):
            for j in range(idx + 1, min(idx + 6, len(lines))):
                v = lines[j].strip()
                if not v or re.match(r'#{1,6}\s+', v):
                    continue
                v = re.sub(r'^\s*[-*+]?\s*', '', v)
                v = re.sub(r'^(\*+)?来源[:：]?\s*\**\s*', '', v)
                if re.search(r'转录|链接|原文', v) and not re.search(r'嘉宾|节目|张小珺|访谈', v):
                    continue
                if v:
                    return v
            return None
        # 2) 行内含 '来源[:：]' (块引用或纯文本)，支持 **来源**： 加粗样式
        if re.search(r'(>+\s*)?(.{0,10})来源[*\s]*[:：]', s):
            v = s
            v = re.sub(r'^>\s*', '', v)
            v = re.sub(r'^[-\*+]?\s*\**\s*', '', v)  # 去掉行首 bullet + 加粗星号
            v = re.sub(r'^.*?来源[*\s]*[:：]\s*', '', v)
            if v:
                return v
    return None

def extract_source_clean(source):
    """把来源裁剪到节目名：去掉 '嘉宾/转录/期数' 及分隔符之后的内容。"""
    if not source:
        return source
    s = source
    # 去掉 markdown 加粗残留
    s = s.replace('**', '').strip()
    # 在 嘉宾/转录/期数/原文/链接 前截断
    cut = re.search(r'(?:嘉宾|转录|期数|原文|原链接|🔗)', s)
    if cut:
        s = s[:cut.start()]
    # 在分隔符 ｜ | · ， 前截断（仅当等号另一侧还有文本时保留前面的节目名）
    s = re.split(r'[｜|·，]', s)[0].strip()
    if not s:
        return source
    return s.strip()

def extract_date(d, md):
    """从 note 文件名提取日期 yyyy-mm-dd。"""
    m = re.search(r'(\d{4}-\d{2}-\d{2})', d.get('note_file') or '')
    if m:
        return m.group(1)
    m2 = re.search(r'(\d{4}-\d{2}-\d{2})', d.get('audio') or '')
    if m2:
        return m2.group(1)
    return '2026-07-31'

def extract_desc(md):
    """从笔记 '一句话' 节取第一段作为卡片描述。"""
    # 找到 '一句话' 标题后的第一段
    lines = md.split('\n')
    capture = False
    for ln in lines:
        s = ln.strip()
        if re.match(r'#{1,6}\s*.*一句话', s):
            capture = True
            continue
        if capture:
            if not s:
                continue
            if s.startswith('#') or re.match(r'^\s*>\s+', s):
                continue
            if re.match(r'^\s*[-*+]', s):
                # 取 bullet 行文本作为描述（去掉 bullet 标记），如 "## 一句话\n- 一句话内容"
                one = re.sub(r'^\s*[-*+]\s+', '', s)
                return one
            return s
    # 兜底：裸 '一句话[:：]...' 行（无标题前缀，如 "一句话：xx"）
    for ln in lines:
        m = re.match(r'^\s*一句话[:：]\s*(.+)', ln.strip())
        if m:
            return m.group(1)
    return ''

def make_title(d):
    return d['title']

def ep_label(d):
    e = d['ep']
    return 'EP' + str(e).upper()

def build_card_html(d, note_html, source, desc, ep_date, dur, audio_url_local=None):
    title = make_title(d)
    url = d['audio_url']
    label = ep_label(d)
    src_span = '📎 ' + source if source else '🚧 待补充来源'
    desc_p = '<p class="desc">%s</p>' % desc if desc else '<p class="desc"></p>'
    note_inner = note_html if note_html else '<p>暂无详细解读</p>'
    card = f'''    <div class="ep" data-url="{url}">
      <div class="ep-head">
        <span class="ep-num">{label}</span>
        <span class="ep-date">{ep_date}</span>
        <span class="dur">{dur}</span>
      </div>
      <h3 class="ep-title">{title}</h3>
      <span class="source">{src_span}</span>
      {desc_p}
      <button class="play-btn" onclick="playEp(this, '{url}')">▶ 播放</button>
      <button class="expand-btn" onclick="toggleNote(this)">📖 查看笔记</button>
      <div class="note-content" style="display:none">
        <div class="note-inner">
{note_inner}
        </div>
      </div>
    </div>'''
    return card

def build_rss_item(d, note_html_html_for_content, source, desc, ep_date, dur, length):
    title = make_title(d)
    link = SITE + '/'
    guid = d['audio']
    dt = datetime.datetime.fromisoformat(ep_date + 'T09:00:00+08:00')
    pubDate = dt.strftime('%a, %d %b %Y 09:00:00 +0800')
    enc_url = SITE + '/episodes/' + d['audio']
    subtitle = source or title
    xml_guid = guid
    if length is None:
        length = '0'
    body = note_html_html_for_content
    item = f'''    <item>
      <title>{title}</title>
      <link>{link}</link>
      <guid isPermaLink="false">{xml_guid}</guid>
      <pubDate>{pubDate}</pubDate>
      <enclosure url="{enc_url}" length="{length}" type="audio/mpeg"/>
      <itunes:subtitle>{subtitle}</itunes:subtitle>
      <description>{desc}</description>
      <content:encoded><![CDATA[{body}]]></content:encoded>
    </item>'''
    return item

def build_content_header(source, ep_date):
    header = [f'<b>📌 原始来源</b>：{source}', f'<b>📅 解读日期</b>：{ep_date}', '<hr/>']
    return '\n'.join(header)

def prep(d):
    md, path = read_note(d)
    source = extract_source(md) if md else None
    source = extract_source_clean(source) if source else None
    # ep 编号兜底：若来源为主系列(张小珺)且不含期数，追加 ep{num}（如 ep117）
    if source and d.get('ep') and str(d['ep']).isdigit():
        epnum = str(d['ep'])
        if '张小珺' in source and not re.search(re.escape(epnum) + r'\b', source):
            source = (source.rstrip(' ·|，') + ' ep' + epnum).strip()
    ep_date = extract_date(d, md)
    desc = extract_desc(md) if md else ''
    dur = get_duration(d['audio'])
    note_html = md_to_html(md) if md else None
    # content:encoded 的完整 HTML：header + note body（note body 自带 <h2> 标题）
    if md:
        body = build_content_header(source or '待补充', ep_date) + '\n' + note_html
    else:
        h2title = process_inline(make_title(d))
        body = build_content_header(source or '待补充', ep_date) + '\n' + '<h2>%s</h2>' % h2title + '\n<p>暂无详细解读</p>'
    # 去掉 body 末尾多余的 <br/>
    body = re.sub(r'(<br/>\s*)+$', '', body) + '\n'
    return dict(d, source=source, ep_date=ep_date, desc=desc, dur=dur,
                note_html=note_html, body=body)

def apply_index(episodes):
    """把一批卡片增量插入 index.html：插到最后一个 .ep 卡片后面（即 container 结束 </div> 前）。"""
    idx = open(INDEX, encoding='utf-8').read()
    cards = []
    for d in episodes:
        info = prep(d)
        cards.append(build_card_html(d, info['note_html'], info['source'], info['desc'],
                                      info['ep_date'], info['dur']))
    block = '\n'.join(cards)
    # 插入点：最后的 </div> 在 </div>\n<div class="player" 之前
    marker = '</div>\n<div class="player" id="player">'
    if marker not in idx:
        raise SystemExit('ERROR: player marker not found in index.html')
    idx = idx.replace(marker, block + '\n' + marker)
    open(INDEX, 'w', encoding='utf-8').write(idx)
    print('index.html: inserted %d cards' % len(cards))

def apply_feed(episodes, order_desc=True):
    """把一批 RSS item 插入 feed.rss：插到 </channel> 前。"""
    fe = open(FEED, encoding='utf-8').read()
    items = []
    for d in episodes:
        info = prep(d)
        p = os.path.join(ROOT, 'episodes', d['audio'])
        length = None
        if os.path.exists(p):
            try:
                length = os.path.getsize(p)
            except Exception:
                length = None
        items.append(build_rss_item(d, info['body'], info['source'], info['desc'],
                                     info['ep_date'], info['dur'], length))
    block = '\n' + '\n'.join(items)
    marker = '    </channel>\n</rss>'
    if marker not in fe:
        raise SystemExit('ERROR: channel marker not found in feed.rss')
    fe = fe.replace(marker, block + '\n' + marker)
    open(FEED, 'w', encoding='utf-8').write(fe)
    print('feed.rss: inserted %d items' % len(items))

def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else '--sample'
    data = json.load(open(META))
    tts = [d for d in data if d['status'] == 'tts_done']

    if mode == '--sample':
        ep = sys.argv[2] if len(sys.argv) > 2 else '96'
        d = next((x for x in tts if x['ep'] == ep), None)
        if not d:
            print('unknown ep', ep); return
        info = prep(d)
        print('# CARD')
        print(build_card_html(d, info['note_html'], info['source'], info['desc'], info['ep_date'], info['dur']))
        print('# RSS ITEM (content:encoded preview first 1500 chars)')
        print(build_rss_item(d, info['body'], info['source'], info['desc'], info['ep_date'], info['dur'], None)[:1500])
        return
    if mode == '--sample-insert':
        # 只把 ep96 插入 index.html（用于浏览器验证）
        ep = sys.argv[2] if len(sys.argv) > 2 else '96'
        d = next((x for x in tts if x['ep'] == ep), None)
        apply_index([d])
        return
    if mode == '--apply':
        apply_index(tts)
        apply_feed(tts)
        return
    print('unknown mode', mode)

if __name__ == '__main__':
    main()
