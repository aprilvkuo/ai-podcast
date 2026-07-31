#!/usr/bin/env python3
"""Parse all .ep cards from index.html into structured records for refactoring."""
import re, json, sys

def find_ep_blocks(html):
    """Return list of (start_idx, end_idx_exclusive, block_text) for each .ep div."""
    blocks = []
    # find openings
    pattern = re.compile(r'<div class="ep" data-url="')
    for m in pattern.finditer(html):
        start = m.start()
        # From start, parse div tags to find balanced close
        i = start
        depth = 0
        # scan div open/close tags
        tag_re = re.compile(r'<(/?)div\b[^>]*>', re.I)
        for tm in tag_re.finditer(html, i):
            tag = tm.group(0)
            if tm.group(1) == '/':
                depth -= 1
                if depth == 0:
                    blocks.append((start, tm.end(), html[start:tm.end()]))
                    break
            else:
                depth += 1
    return blocks

def main(path):
    with open(path, 'r', encoding='utf-8') as f:
        html = f.read()
    blocks = find_ep_blocks(html)
    print(f"Found {len(blocks)} .ep blocks")
    # Extract fields from first block to validate
    recs = []
    for start, end, text in blocks:
        ep_num = re.search(r'class="ep-num">([^<]*)<', text)
        ep_date = re.search(r'class="ep-date">([^<]*)<', text)
        dur = re.search(r'class="dur">([^<]*)<', text)
        title = re.search(r'class="ep-title">(.*?)</h3>', text, re.S)
        source = re.search(r'class="source">(.*?)</span>', text, re.S)
        desc = re.search(r'class="desc">(.*?)</p>', text, re.S)
        url = re.search(r'data-url="([^"]*)"', text)
        # note-content: the div and everything until matching close, capture note-inner inner
        note_m = re.search(r'<div class="note-content" style="display:none">\s*<div class="note-inner">(.*)</div>\s*</div>\s*</div>', text, re.S)
        recs.append({
            'url': url.group(1) if url else '',
            'ep_num': ep_num.group(1) if ep_num else '',
            'ep_date': ep_date.group(1) if ep_date else '',
            'dur': dur.group(1) if dur else '',
            'title': title.group(1).strip() if title else '',
            'source': source.group(1).strip() if source else '',
            'desc': desc.group(1) if desc else '',
            'note_inner': note_m.group(1).strip() if note_m else '',
        })
    # quick validation: note_inner non-empty for all
    empty_notes = [r['ep_num'] for r in recs if not r['note_inner']]
    print(f"Records parsed: {len(recs)}")
    print(f"Empty note_inner: {empty_notes if empty_notes else 'NONE (all have notes)'}")
    print(f"Duplicate URLs: {len(recs) - len(set(r['url'] for r in recs))}")
    print(f"Sample ep_num order (first 3): {[r['ep_num'] for r in recs[:3]]}")
    print(f"Sample ep_num order (last 3): {[r['ep_num'] for r in recs[-3:]]}")
    # save json
    with open('/Users/egg/.claude/podcast/scripts/eps_data.json', 'w', encoding='utf-8') as f:
        json.dump(recs, f, ensure_ascii=False, indent=1)
    print("Saved to scripts/eps_data.json")

if __name__ == '__main__':
    main(sys.argv[1] if len(sys.argv) > 1 else '/Users/egg/.claude/podcast/index.html')
