#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""蛋播播客 markdown->HTML 转换器 (与现有 index.html/feed.rss note-inner 风格一致)
规则：
  #/##/###  -> h2/h3/h4
  > 连续行    -> 各自一个 <blockquote>
  - 列表     -> <ul><li>
  数字. 行    -> 各自一个 <p>（与现有习惯一致，不转 ol）
  普通段落(连续到空行) -> 每行一个 <p>
  ---        -> <br/>
  空行块      -> <br/>
  **bold**   -> <b>
  "           -> &quot;
  [[wikilink]] -> 纯文本（去掉括号）
  每块后跟 <br/>
"""
import re
import html

def process_inline(text):
    # wikilink 转纯文本
    text = re.sub(r'\[\[([^\]]+)\]\]', lambda m: m.group(1), text)
    # 保护 ** markdown 加粗
    text = text.replace('**', '\x00BOLD\x00')
    # 转义 & < > 为 HTML 实体（quote=False 不转双引号）
    text = html.escape(text, quote=False)
    text = text.replace('\x00BOLD\x00', '**')
    # 加粗
    parts = text.split('**')
    out = []
    for i, p in enumerate(parts):
        if i % 2 == 1:
            out.append('<b>' + p + '</b>')
        else:
            out.append(p)
    text = ''.join(out)
    # 转义 ASCII 双引号 -> &quot;
    text = text.replace('"', '&quot;')
    return text

def md_to_html(md):
    lines = md.split('\n')
    blocks = []  # html 块列表
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i].rstrip()
        s = line.strip()
        if not s:
            i += 1
            continue
        # 水平线 -> 一个 <br/> 逻辑块
        if re.fullmatch(r'-{3,}', s) or re.fullmatch(r'\*{3,}', s):
            blocks.append('<br/>')
            i += 1
            continue
        # 标题
        m = re.match(r'(#{1,6})\s+(.*)', s)
        if m:
            level = len(m.group(1))
            htag = {1: 'h2', 2: 'h3', 3: 'h4', 4: 'h5', 5: 'h6', 6: 'h6'}[min(level, 6)]
            blocks.append('<%s>%s</%s>' % (htag, process_inline(m.group(2)), htag))
            i += 1
            continue
        # 块引用：连续 > 行组成一个逻辑块，内部无 <br/>，仅块后加一个 <br/>
        if s.startswith('>'):
            bq_items = []
            while i < n and lines[i].strip().startswith('>'):
                bq = lines[i].strip()[1:].strip()
                bq_items.append('<blockquote>%s</blockquote>' % process_inline(bq))
                i += 1
            blocks.append('\n'.join(bq_items))
            continue
        # 无序列表（连续 - / * / +）
        if re.match(r'^\s*[-*+]\s+', s):
            items = []
            while i < n:
                ls = lines[i].strip()
                mm = re.match(r'^\s*[-*+]\s+(.*)$', ls)
                if mm:
                    items.append('  <li>%s</li>' % process_inline(mm.group(1)))
                    i += 1
                else:
                    break
            blocks.append('<ul>\n' + '\n'.join(items) + '\n</ul>')
            continue
        # 数字列表项 -> 各成一个 <p>
        if re.match(r'^\s*\d+\.\s+', s):
            while i < n:
                ls = lines[i].strip()
                mm = re.match(r'^\s*\d+\.\s+(.*)$', ls)
                if mm:
                    blocks.append('<p>%s</p>' % process_inline(mm.group(1)))
                    i += 1
                else:
                    break
            continue
        # 普通段落
        para_lines = []
        while i < n:
            pl = lines[i].rstrip()
            if not pl.strip():
                break
            ps = pl.strip()
            if re.match(r'^\s*[-*+]\s+', ps) or re.match(r'^\s*\d+\.\s+', ps) or ps.startswith('>') or re.match(r'#{1,6}\s+', ps) or re.fullmatch(r'-{3,}', ps):
                break
            para_lines.append(process_inline(pl.strip()))
            i += 1
        blocks.extend('<p>%s</p>' % pl for pl in para_lines)
        continue

    # 组装：每个逻辑块后跟一个 <br/>，块与块之间。块本身是 <br/>（来自 ---）则不再额外加 <br/>。
    out = []
    for b in blocks:
        out.append(b)
        if b.strip() != '<br/>':
            out.append('<br/>')
    text = '\n'.join(out)
    text = re.sub(r'(<br/>\s*)+$', '', text)
    return text

if __name__ == '__main__':
    ep96 = '/Users/egg/Library/Mobile Documents/iCloud~md~obsidian/Documents/life-system/vault/20 Knowledge/Notes/GenAI Guide/自动驾驶10年演进_郎咸朋_学习解读_2026-07-31.md'
    md = open(ep96, encoding='utf-8').read()
    print(md_to_html(md))
