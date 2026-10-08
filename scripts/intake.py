#!/usr/bin/env python3
"""Observe one public Delve post, explicitly translate it, optionally test a proposal.

No login, external writes, live installation, incoming-code execution, or syntax guessing.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


translation = module('intake_translation', 'scripts/translate.py')
delve = module('intake_delve', 'scripts/delve.py')


def write(path, raw):
    with path.open('xb') as stream:
        stream.write(raw)


def json_write(path, value):
    write(path, translation.canonical(value) + b'\n')


def intake(uri, syntax, output, scenario_source=None, *, client=None, now=None, propose=None):
    """Keep observation/source even on translation refusal; output must not exist."""
    delve.post_uri(uri)
    output = Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('output already exists; choose a new observation directory')
    client = client or delve.Delve('~/claude_state/delvetalk')
    response = client.public('town.delve.feed.getPosts', {'uris': uri})
    posts = response.get('posts')
    if not isinstance(posts, list) or len(posts) != 1 or posts[0].get('uri') != uri:
        raise ValueError('requested post not returned exactly once')
    post = posts[0]
    text = post.get('record', {}).get('text')
    author = post.get('author')
    if not isinstance(text, str) or not isinstance(post.get('cid'), str) or not post['cid']:
        raise ValueError('post needs full text and CID')
    if not isinstance(author, dict) or not isinstance(author.get('did'), str) or not author['did']:
        raise ValueError('post needs an observed author DID')
    raw = text.encode('utf-8')
    if len(raw) > 512 * 1024:
        raise ValueError('post text exceeds 512 KiB intake limit')
    observed_at = now or datetime.now(timezone.utc).isoformat()
    observation = {
        'format': 'delvetalk-delve-observation-v1', 'observed_at': observed_at,
        'transport': {'endpoint': delve.APPVIEW + '/xrpc/town.delve.feed.getPosts',
                      'params': {'uris': uri}, 'authenticated': False},
        'uri': uri, 'cid': post['cid'], 'author': author, 'text': text,
        'source_sha256': translation.digest(raw), 'appview_response': response,
        'identity_scope': 'AppView observation; no independent repository-signature verification',
    }
    observation['id'] = translation.digest(translation.canonical(observation))
    output.mkdir(mode=0o700)
    write(output / 'source.txt', raw)
    json_write(output / 'observation.json', observation)
    report = {
        'format': 'delvetalk-intake-report-v1', 'observation_id': observation['id'],
        'uri': uri, 'cid': post['cid'], 'source_sha256': observation['source_sha256'],
        'operator_syntax': syntax, 'authority': 'none; public observation and isolated local fixtures only',
        'intake_sha256': translation.digest(Path(__file__).read_bytes()),
    }
    stage = 'translation'
    try:
        artifact = translation.translate(syntax, raw)
        json_write(output / 'artifact.json', artifact)
        report.update(status='translated', target=artifact['target'],
                      translation_pin=artifact['translation']['pin'], lowered_sha256=artifact['lowered_sha256'])
        if scenario_source is not None:
            # Operator supplies a local fixture. Never fetch executable material or adapters from a post.
            stage = 'proposal-check'
            write(output / 'scenarios.json', scenario_source)
            propose = propose or module('intake_proposal', 'scripts/propose.py').propose
            proposal = propose(syntax, raw, scenario_source)
            if proposal['candidate']['artifact'] != artifact:
                raise ValueError('translation changed during intake; rerun from a stable checkout')
            json_write(output / 'proposal-report.json', proposal)
            report.update(status='scenarios-passed' if proposal['passed'] else 'scenarios-failed',
                          proposal_report_id=proposal['id'], candidate_id=proposal['candidate']['id'])
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, RecursionError) as error:
        report.update(status='refused', stage=stage, error=str(error))
    report['id'] = translation.digest(translation.canonical(report))
    json_write(output / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('uri', help='exact at:// post URI')
    parser.add_argument('--syntax', required=True, help='operator-selected reviewed syntax ID/version')
    parser.add_argument('--output', type=Path, required=True, help='new private observation directory')
    parser.add_argument('--scenarios', type=Path, help='optional local scenario fixture; isolated Lean worlds only')
    args = parser.parse_args()
    try:
        scenarios = args.scenarios.read_bytes() if args.scenarios else None
        report = intake(args.uri, args.syntax, args.output, scenarios)
        sys.stdout.buffer.write(translation.canonical(report) + b'\n')
        return 0 if report['status'] in ('translated', 'scenarios-passed') else 1
    except (delve.Failure, ValueError, KeyError, TypeError, OSError, RuntimeError, RecursionError) as error:
        print(f'intake: {error}', file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
