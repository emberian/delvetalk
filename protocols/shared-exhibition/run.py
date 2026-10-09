#!/usr/bin/env python3
"""Author, compile, adopt and inhabit a source-bound private exhibition.

Uses prebuilt local hosts only; no network, model or publication. The destination
must be fresh. --content supplies private participant text, never source code.
"""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import bootstrap
import compiler_queue
import continuation
import portal

TARGET = 'exhibition:room-between'
CANDIDATE = 'proposal:exhibition'
PROFILE = 'transactions'


def law(invoke, reprogram=(), managers=('operator',)):
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': invoke,
            'reprogram': list(reprogram), 'law': list(managers)}


def fixture_content():
    return {'north': {'title': 'Fold', 'note': 'A paper test piece.',
                     'minutes': 4, 'fragile': True, 'light': 'dim'},
            'south': {'title': 'Thread', 'note': 'A woven test piece.',
                     'minutes': 6, 'fragile': False, 'light': 'bright'},
            'arrangement': {'caption': 'Fold meets Thread.', 'first': 'south'}}


def run(directory, content=None):
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    content = fixture_content() if content is None else content
    source = (HERE / 'protocol.json').read_bytes()
    program = bootstrap.loads(source)
    runtime = bootstrap.history.runtime(PROFILE)
    desk = bootstrap.desk_module.Desk(directory / 'world.json', directory / 'artifacts', profile=PROFILE)
    events = []

    def record(label, result, kind='committed'):
        events.append({'event': label, 'result': result})
        bootstrap.save_new(directory / 'events' / (str(len(events)) + '.json'), events[-1])
        actual = result.get('kind', result.get('status'))
        if actual != kind:
            raise AssertionError(f'{label}: wanted {kind}; got {result}')
        return result

    (directory / 'events').mkdir()
    # Every creation and replacement retains its original source envelope.
    placeholder = (ROOT / 'protocols/counter/protocol.json').read_bytes()
    for raw in (placeholder, (ROOT / 'protocols/source-desk/protocol.json').read_bytes(), source):
        bootstrap.preserve_lowering(directory, raw)
    target_law = law({'offer-north': ['north'], 'offer-south': ['south'],
                      'consent-north': ['north'], 'consent-south': ['south'],
                      'arrange': ['curator'], 'open': ['curator']}, reprogram=['curator'])
    target = record('create-target', desk.exchange({'op': 'create', 'object': TARGET,
        'principal': 'operator', 'intent': 'exhibition-create',
        'protocol': bootstrap.loads(placeholder), 'law': target_law}))['data']['root']
    candidate = record('create-source-desk', desk.create(CANDIDATE, 'operator', 'desk-create',
        law({'submit': ['builder'], 'compiled': ['compiler'], 'failed': ['compiler'],
             'adopt': ['curator']})))['data']['root']
    pending = record('submit-original-source', desk.submit(CANDIDATE, 'builder', 'source-submit', candidate,
        'protocol-json@1', source, (HERE / 'scenarios.json').read_bytes(), program['initial'], TARGET))['data']['root']
    queue = compiler_queue.CompilerQueue(directory / 'queue', desk.database, desk.artifact_store, profile=PROFILE)
    job = queue.enqueue(CANDIDATE, 'compiler', 'compile-source', pending)['job']
    queue_report = queue.run()
    if queue_report['errors']:
        raise AssertionError(queue_report)
    compiled = queue.inspect(job)
    ready = record('queued-compilation', compiled['receipt'])['data']['root']
    if ready['state']['status'] != 'ready':
        raise AssertionError(ready['state']['diagnostics'])
    bootstrap.preserve_build(directory, ready['state']['artifact'])
    assert desk.inspect(TARGET) == target, 'compilation must not adopt'
    record('compiler-cannot-adopt', desk.adopt(CANDIDATE, TARGET, 'compiler', 'bad-adopt', ready, target), 'refused')
    record('curator-adopts', desk.adopt(CANDIDATE, TARGET, 'curator', 'adopt', ready, target))
    bootstrap.save_new(directory / 'manifest.json', {
        'format': 'delvetalk-inhabited-bootstrap-v1', 'cafe': TARGET,
        'candidate': CANDIDATE, 'participants': ['north', 'south', 'curator'], 'runtime': runtime})
    apps = {principal: portal.Portal(directory, principal=principal, allow_local_actions=True)
            for principal in ('north', 'south', 'curator', 'visitor')}

    def prepared(principal, command, fields, card=None):
        app = apps[principal]
        card = card or app.object(TARGET)
        action = next(item for item in card['actions'] if item['command'] == command)
        token = action['token'] + ' ' + json.dumps(fields, ensure_ascii=False)
        interpreted = app.interpretation({'card': card['card'], 'text': token})
        record('token-' + command + '-' + principal, interpreted, 'proposed')
        draft = app.prepare({'card': card['card'], 'action': interpreted['action'], 'fields': interpreted['fields']})
        assert draft['wire']['expected']['version'] == card['version']
        return draft

    def play(principal, command, fields, *, card=None, kind='committed'):
        draft = prepared(principal, command, fields, card)
        reply = record('play-' + command + '-' + principal,
                       apps[principal].execute({'draft': draft['draft']}), kind)
        return draft, reply

    first_card = apps['north'].object(TARGET)
    assert first_card['mode'] == 'projection', first_card
    assert first_card['panel'] == 'main'
    assert {panel['id'] for panel in first_card['panels']} == {'main', 'north', 'south'}
    assert {a['command'] for a in first_card['actions']} == {'offer-north', 'offer-south'}
    before = desk.database.read_bytes()
    invalid_action = next(a for a in first_card['actions'] if a['command'] == 'offer-north')
    malformed = apps['north'].interpretation({'card': first_card['card'],
        'text': invalid_action['token'] + ' ' + json.dumps({**content['north'], 'minutes': True})})
    record('typed-token-rejects-boolean-nat', malformed, 'clarify')
    assert desk.database.read_bytes() == before
    play('visitor', 'offer-north', content['north'], card=first_card, kind='refused')
    first_draft, first_reply = play('north', 'offer-north', content['north'], card=first_card)
    before = desk.database.read_bytes()
    assert apps['north'].execute({'draft': first_draft['draft']}) == first_reply
    assert before == desk.database.read_bytes(), 'retry must not append or execute'
    play('south', 'offer-south', content['south'], card=first_card, kind='refused')
    play('south', 'offer-south', content['south'])
    play('curator', 'arrange', content['arrangement'])
    agreed = apps['north'].object(TARGET)
    assert agreed['prose'] == content['arrangement']['caption']
    assert {a['command'] for a in agreed['actions']} == {'consent-north', 'consent-south'}
    play('south', 'consent-south', {})
    # A direct invocation bypasses the view but cannot bypass semantic consent.
    record('curator-cannot-open-before-both', desk.exchange({'op': 'invoke', 'object': TARGET,
        'principal': 'curator', 'intent': 'premature-open', 'expected': desk.inspect(TARGET),
        'command': 'open', 'input': {}}), 'refused')
    play('north', 'consent-north', {}, card=agreed, kind='refused')
    play('north', 'consent-north', {})
    play('curator', 'open', {})
    final = apps['curator'].object(TARGET)
    assert final['actions'] == []
    for artist in ('north', 'south'):
        panel = apps[artist].object(TARGET, panel=artist)
        assert panel['panel'] == artist
        assert panel['panels'] == first_card['panels']
        assert panel['prose'] == content[artist]['note']
    detail = apps['curator'].detail(final['card'])
    assert detail['root']['state']['opened'] is True
    assert detail['root']['protocol'] == program
    if bootstrap.canonical(runtime) != bootstrap.canonical(bootstrap.history.runtime(PROFILE)):
        raise RuntimeError('Runtime changed during journey; retained private run is not stable-runtime evidence')
    exported = continuation.prepare_bootstrap(directory, directory / 'continuation')
    index = bootstrap.loads((directory / 'continuation/index.json').read_bytes())
    anchors = {'expected_genesis': index['history']['genesis'], 'expected_head': index['history']['head']}
    checked = continuation.verify(directory / 'continuation', **anchors)
    report = {'profile': PROFILE, 'object': TARGET, 'job': job, 'events': len(events),
              'version': final['version'], 'state': detail['state'],
              'continuation': exported, 'verification': checked}
    bootstrap.save_new(directory / 'journey.json', report)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--content', type=Path, help='Private JSON: north, south, arrangement')
    args = parser.parse_args()
    result = run(args.directory, json.loads(args.content.read_text()) if args.content else None)
    print(json.dumps({'profile': result['profile'], 'events': result['events'],
                      'version': result['version'], 'continuation': result['continuation']['entryPoint']}, indent=2))
