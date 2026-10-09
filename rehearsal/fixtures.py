#!/usr/bin/env python3
"""Rebuild rehearsal/fixtures/posts.json from the owner's read-only archive: every postView in
the captured getFeed/searchPosts/getPostThread pages and the saved status thread, one per uri,
in createdAt order. Writes SOURCES.txt (each input with its SHA-256) beside it.

  python3 rehearsal/fixtures.py ~/claude_state/delvetalk/watch/archive/captures/*.json thread2.json
"""
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent / 'fixtures'


def walk(thread, out):
    if isinstance(thread, dict):
        if isinstance(thread.get('post'), dict):
            out[thread['post']['uri']] = thread['post']
        walk(thread.get('parent'), out)
        for reply in thread.get('replies') or []:
            walk(reply, out)


def main(paths):
    posts, sources = {}, []
    for path in sorted(paths):
        raw = Path(path).read_bytes()
        sources.append(f'{hashlib.sha256(raw).hexdigest()}  {Path(path).name}')
        data = json.loads(raw)
        page = data.get('response', data)  # a capture wraps the page; a saved thread is the page
        for item in page.get('feed') or []:
            posts[item['post']['uri']] = item['post']
        for post in page.get('posts') or []:
            posts[post['uri']] = post
        walk(page.get('thread'), posts)
    ordered = sorted(posts.values(), key=lambda p: (p['record']['createdAt'], p['uri']))
    (HERE / 'posts.json').write_text(json.dumps(ordered, ensure_ascii=False))
    (HERE / 'SOURCES.txt').write_text(
        f'{len(ordered)} distinct posts, {ordered[0]["record"]["createdAt"]} to {ordered[-1]["record"]["createdAt"]}\n'
        'from these files (getFeed/searchPosts/getPostThread captures and the status thread):\n' + '\n'.join(sources) + '\n')
    print(len(ordered))


if __name__ == '__main__':
    main(sys.argv[1:])
