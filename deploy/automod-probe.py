#!/usr/bin/env python3
"""Ask the automod classifier about argv texts, or one text per stdin line, without changing a world."""
import argparse
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from transport import automod  # noqa: E402
from transport.config import Config  # noqa: E402


def read_policy(path):
    if path:
        return Path(path).expanduser().read_text()
    source = (ROOT / 'spec/Delvetalk/Host/Moderation.lean').read_text()
    expression = source.split('def policy : String :=', 1)[1].split('\ndef ', 1)[0]
    literal = r'"(?:\\.|[^"\\])*"'
    parts = re.findall(literal, expression)
    if not parts or re.sub(literal + r'|\+\+|\s+', '', expression):
        raise ValueError('Moderation.policy must be concatenated string literals')
    return ''.join(json.loads(part) for part in parts)


def verdict(st, policy, text):
    answer = automod.ask_glm(st, policy, automod.user_text([{'text': text}]))
    if answer.get('status') != 'replied':
        return {'status': answer.get('status', 'failed'), 'reason': answer.get('reason', 'blocked')}
    try:
        raw = answer['raw']
        items = json.loads(raw[raw.index('{'):raw.rindex('}') + 1])['verdicts']
        if len(items) != 1 or items[0].get('i') != 0 or type(items[0].get('flag')) is not bool:
            raise ValueError('expected one verdict')
        return items[0]
    except (ValueError, KeyError, TypeError, AttributeError):
        return {'status': 'failed', 'reason': 'unreadable verdict'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--policy', metavar='FILE', help='plain system text; default: Moderation.policy from Lean source')
    parser.add_argument('--key-file', default='~/.zai-key', metavar='FILE')
    parser.add_argument('texts', nargs='*', help='each argument is one text; default: one text per stdin line')
    args = parser.parse_args()
    try:
        policy = read_policy(args.policy)
    except (OSError, ValueError, IndexError):
        parser.error('cannot read policy; use --policy FILE for plain system text')
    st = SimpleNamespace(config=Config.load(zai_key_file=args.key_file))
    texts = args.texts if args.texts else (line.rstrip('\r\n') for line in sys.stdin)
    failed = False
    for text in texts:
        result = verdict(st, policy, text)
        print(json.dumps({'text': text, **result}, ensure_ascii=False), flush=True)
        failed |= 'flag' not in result
    return int(failed)


if __name__ == '__main__':
    sys.exit(main())
