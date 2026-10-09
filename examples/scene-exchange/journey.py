#!/usr/bin/env python3
"""A source-to-history relay using existing proposal, portal and Lean routes."""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import portal
import propose
import source_object

bootstrap = portal.bootstrap
history = bootstrap.history
room = bootstrap.room
world = bootstrap.desk_module.world
HERE = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(history.canonical(value) + b'\n')
    return path


def run(directory, *, profile='compiled'):
    directory = Path(directory).resolve()
    require(profile == 'compiled', 'scene exchange requires source admission')
    require(not directory.exists(), 'choose a new custody directory')
    pinned = history.runtime(profile)  # Refuse missing binaries; never build here.
    directory.mkdir(parents=True, mode=0o700)
    db = directory / 'world.json'
    attachments, reports = {}, {}
    objects = {'relay': 'scene:rain-relay', 'card': 'card:rain-name'}
    workshop = bootstrap.scene_workshop.frame_source((HERE / 'rain-relay.scene').read_bytes().decode('utf-8'), [
        {'name': 'Handler', 'source': (ROOT / 'protocols/spween-handlers/Handler.obend').read_bytes().decode('utf-8')}]).encode()
    for key, filename, syntax, source, scenarios in [
            ('relay', 'rain-relay.workshop', 'spween-handler-workshop@1', workshop,
             (HERE / 'rain-relay.examples').read_bytes()),
            ('card', 'RainCard.obend', 'objective-bend-object', (HERE / 'RainCard.obend').read_bytes(),
             (HERE / 'rain-card.examples').read_bytes())]:
        report = propose.propose(syntax, source, scenarios, profile=profile)
        require(report['passed'], 'proposal scenarios failed: ' + key)
        reports[key] = report['id']
        report_path = save(directory / 'artifacts' / (key + '-proposal.json'), report)
        source_path = directory / 'sources' / filename
        source_path.parent.mkdir(exist_ok=True)
        source_path.write_bytes(source)
        artifact = report['candidate']['artifact']
        paths = [source_path, report_path]
        protocol = artifact['lowered']
        if key == 'relay':
            wrapped = room.source_artifact(protocol)
            identity = room.store_artifact(directory / 'artifacts/rooms', wrapped)
            paths.append(directory / 'artifacts/rooms' / (identity + '.json'))
            original = directory / 'sources/rain-relay.scene'
            original.write_bytes((HERE / 'rain-relay.scene').read_bytes())
            paths.append(original)
        request = {'op': 'create', 'object': objects[key], 'principal': 'operator',
                   'intent': 'create-' + key, 'protocol': protocol,
                   'law': {'profile': 'delvetalk-scoped-law', 'read': 'public',
                           'invoke': {name: ['jun', 'tavi'] for name in protocol['commands']},
                           'reprogram': ['jun', 'tavi'], 'law': ['operator']}}
        reply = world.exchange(db, request, profile=profile)
        require(reply['kind'] == 'committed', 'creation failed: ' + str(reply))
        attachments[history.digest(request)] = paths
    save(directory / 'manifest.json', {'format': 'delvetalk-scene-exchange-v1',
         'runtime': pinned, 'cafe': objects['relay'], 'objects': objects})
    sessions = {name: portal.Portal(directory, state=directory / ('custody-' + name),
                principal=name, allow_local_actions=True) for name in ('jun', 'tavi', 'visitor')}
    events = []

    def capture(person, key):
        return sessions[person].object(objects[key])

    def act(person, card, label, fields=None, *, kind='committed', error=None):
        session = sessions[person]
        action = next(item for item in card['actions'] if item['label'] == label)
        token = action['token'] + (' ' + history.canonical(fields).decode() if fields is not None else '')
        interpretation = session.interpretation({'card': card['card'], 'text': token})
        require(interpretation['status'] == 'proposed', 'token did not select an action')
        draft = session.prepare({'card': card['card'], 'action': interpretation['action'],
                                 'fields': interpretation['fields']})
        response = session.execute({'draft': draft['draft']})
        require(response['kind'] == kind, 'unexpected action outcome: ' + str(response))
        if error is not None:
            require(response['reply']['data'] == error, 'unexpected refusal reason')
        events.append({'principal': person, 'card': card, 'token': token,
                       'interpretation': interpretation, 'draft': draft, 'response': response})
        return response

    act('jun', capture('jun', 'relay'), 'Start')
    initial_jun = capture('jun', 'relay')
    initial_tavi = capture('tavi', 'relay')
    early_root = sessions['jun'].detail(initial_jun['card'])['root']
    early = world.exchange(db, {'op': 'invoke', 'object': objects['relay'], 'principal': 'jun',
        'intent': 'unoffered-release', 'expected': early_root, 'command': 'choose', 'input': {'choice': 2}},
        profile=profile)
    require(early['kind'] == 'refused' and 'choice unavailable' in str(early['data']),
            'receiving source guard accepted an unoffered early release')
    save(directory / 'guard-refusal.json', early)
    act('visitor', capture('visitor', 'relay'), 'Free the roof vane', kind='refused', error='unauthorized')
    freed = act('jun', initial_jun, 'Free the roof vane')
    retried = sessions['jun'].execute({'draft': freed['draft']})
    require(retried == freed, 'exact retry changed its receipt')
    act('tavi', initial_tavi, 'Open the listening shutter', kind='refused', error='stale read root')
    act('tavi', capture('tavi', 'relay'), 'Open the listening shutter')
    released = act('jun', capture('jun', 'relay'), 'Release the rain note')
    released_model = source_object.plain(source_object.state_data(released['reply']['data']['root']))
    variables = released_model['handler']['variables']
    announcements = []
    while variables['variant'] == 'cons':
        head = variables['payload']['head']
        if head['name'] == 'announcement':
            announcements.append(head['value'])
        variables = variables['payload']['tail']
    require(announcements == [{'variant': 'string', 'payload': {
        'value': 'The rain draws one silver line across the listening room.'}}],
        'the source handler did not retain the scene announcement')
    final_room = capture('tavi', 'relay')
    require('silver line trembles' in final_room['prose'], 'listening room was not reached')

    name_card = capture('tavi', 'card')
    bad_token = name_card['actions'][0]['token'] + ' {"name":"Threadsong","ink":"green"}'
    clarification = sessions['tavi'].interpretation({'card': name_card['card'], 'text': bad_token})
    require(clarification['status'] == 'clarify', 'unknown ink was accepted by the form')
    act('tavi', name_card, 'Name the rain', {'name': 'Threadsong', 'ink': 'silver'})
    act('jun', capture('jun', 'card'), 'Name the rain', {'name': 'New name', 'ink': 'blue'}, kind='refused')
    final_card = capture('jun', 'card')
    detail = sessions['jun'].detail(final_card['card'])
    rain_name = source_object.plain(source_object.state_data(detail['root']))
    require(rain_name == {'name': 'Threadsong', 'ink': 'silver', 'by': 'tavi'}, 'rain card changed')
    save(directory / 'events.json', events)
    save(directory / 'final-room.json', final_room)
    save(directory / 'final-card.json', final_card)
    save(directory / 'form-refusal.json', clarification)
    require(history.canonical(pinned) == history.canonical(history.runtime(profile)),
            'runtime changed during journey; rerun in a stable checkout')
    exported = history.export_history(db, directory / 'history', profile=profile, attachments=attachments)
    verified = history.verify_history(directory / 'history', expected_genesis=exported['genesis'],
                                      expected_head=exported['head'])
    report = {'format': 'delvetalk-scene-exchange-report-v1', 'runtime': pinned,
              'proposals': reports, 'history': exported, 'verified': verified,
              'admissions': len(events), 'retryRecovered': True, 'fieldClarification': clarification['status'],
              'rainName': rain_name, 'earlyGuardRefusal': early, 'room': final_room['title'],
              'scope': 'Scripted local principals; source-owned scene effects have no external delivery claim.'}
    save(directory / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path, help='new private custody directory')
    parser.add_argument('--profile', choices=('compiled',), default='compiled')
    args = parser.parse_args()
    try:
        report = run(args.directory, profile=args.profile)
    except (ValueError, OSError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(history.canonical(report).decode())
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
