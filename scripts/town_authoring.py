#!/usr/bin/env python3
"""Prepare immutable compiler follow-ups for retained town submissions; never execute or publish."""
import argparse
import hashlib
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import compiler_queue
import desk
import town
import town_cards

ROOT = Path(__file__).resolve().parents[1]
examples = desk.module('town_authoring_examples', 'syntaxes/spell_examples.py')
canonical, loads, digest = desk.canonical, desk.loads, desk.digest
FORMAT = 'delvetalk-town-authoring-followup-v1'
INLINE_SOURCE_BYTES = 4096


def same(actual, expected, label):
    if canonical(actual) != canonical(expected):
        raise ValueError(label + ' mismatch')


def retain(path, value):
    stored = desk.immutable(path, value)
    same(stored, value, 'immutable authoring evidence')
    return stored


def implementation(config, profile):
    files = {**config['profile']['pins'], **desk.execution_profile(profile)['files']}
    for name in ('scripts/town_authoring.py', 'scripts/town.py', 'scripts/compiler_queue.py', 'scripts/translate.py',
                 'syntaxes/spell_examples.py'):
        files[name] = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
    return files


def fixture_results(report):
    """Project saved assertions and actual receipts, without evaluating a program."""
    fixtures = report['candidate']['scenarios']['value']
    outcomes = report['outcomes']
    if len(fixtures) != len(outcomes):
        raise ValueError('compiler report fixture count mismatch')
    result = []
    for fixture, outcome in zip(fixtures, outcomes):
        same(outcome['name'], fixture['name'], 'compiler fixture name')
        if outcome['installation']['kind'] != 'committed':
            result.append({'name': fixture['name'], 'step': 'installation', 'command': 'create',
                           'input': {}, 'expected': {'kind': 'committed'},
                           'observed': {'kind': outcome['installation']['kind']}, 'failures': outcome['failures']})
            continue
        if len(fixture['steps']) != len(outcome['steps']):
            raise ValueError('compiler report step count mismatch')
        for index, (step, turn) in enumerate(zip(fixture['steps'], outcome['steps'])):
            same(turn['index'], index, 'compiler fixture step')
            if 'observe' in step:
                actual = {'error': turn['viewError']} if 'viewError' in turn else {'view': turn['view']['data']}
                result.append({'name': fixture['name'], 'step': index + 1, 'observe': step['observe'],
                               'expected': {'view': step['view']}, 'observed': actual,
                               'failures': [failure for failure in outcome['failures'] if failure['at'] == index]})
                continue
            receipt = turn['receipt']
            actual = {'kind': receipt['kind'], 'error': receipt['data']}
            if receipt['kind'] == 'committed':
                data = receipt['data']
                actual.update(state=data['root']['state'], result=data['result'], outbox=data['outbox'])
            expected = {key: step[key] for key in ('kind', 'state', 'error', 'result', 'outbox') if key in step}
            result.append({'name': fixture['name'], 'step': index + 1, 'command': step['command'],
                           'input': step['input'], 'expected': expected,
                           'observed': {**{key: actual.get(key) for key in expected},
                                        **({'error': receipt['data']} if receipt['kind'] == 'refused' else {})},
                           'failures': [failure for failure in outcome['failures'] if failure['at'] == index]})
    return result


def describe(result):
    heading = {'ready': 'Your spell is checked and ready to offer. It is not installed.',
               'failed': 'Your spell needs another draft.',
               'refused': 'The compiler result was refused. Nothing was installed.',
               'pending': 'Your spell is waiting for a compiler check.',
               'uncertain': 'The compiler has no confirmed complete result yet. Ask the operator to check this job; do not resubmit.'}
    lines = [heading[result['status']]]
    for item in result.get('fixtures', [])[:8]:
        def shown(value):
            text = canonical(value).decode()
            raw = text.encode('utf-8')
            return text if len(raw) <= 650 else raw[:650].decode('utf-8', errors='ignore') + '… (full value retained)'
        action = ('observe view ' + shown(item['observe']) if 'observe' in item else
                  shown(item['command']) + ' with input ' + shown(item['input']))
        lines.append('Example ' + shown(item['name']) + ', step ' + str(item['step']) + ' ' + action
                     + ': expected ' + shown(item['expected']) + '; observed ' + shown(item['observed']) + '.')
    if len(result.get('fixtures', [])) > 8:
        lines.append('Further examples are retained in the complete local report.')
    for notice in result.get('notices', []):
        lines.append(notice)
    if result.get('diagnostics'):
        lines.append('Check details: ' + canonical(result['diagnostics']).decode()[:1800])
    material = result.get('sourceMaterial', {})
    for key, label in (('source', 'Source'), ('scenarios', 'Test examples')):
        if key not in material:
            continue
        raw = material[key]
        # This is editable data, never a reply/card delimiter or an instruction.
        display = '| ' + re.sub(r'\r\n|[\n\r\v\f\x1c-\x1e\x85\u2028\u2029]',
                                lambda match: match[0] + '| ', raw)
        if len(raw.encode('utf-8')) > INLINE_SOURCE_BYTES or len(display.encode('utf-8')) > 6144:
            lines.append(label + ' is too large to show in full here. Ask the operator for the complete '
                         + key + '; no shortened executable text is shown.')
        else:
            lines.append('\n' + label + (' (' + canonical(result.get('syntax', 'unknown')).decode() + ')' if key == 'source' else '')
                         + ' — exact text below. Copy it and remove only the leading "| " from each line to edit:')
            lines.append(display)
    if result.get('cards'):
        lines.append('\nOffer this change only if you want the displayed migration and have current authority.')
        lines.extend(card['body'] for card in result['cards'])
    return '\n'.join(lines)


class TownAuthoring:
    def __init__(self, town, queue, state=None):
        self.town, self.queue = town, queue
        self.state = Path(state).expanduser().resolve() if state else town.state / 'authoring'

    def _submission(self, source, job):
        path = self.town.state / 'requests' / (town.worker.key(source['uri']) + '.json')
        entry = loads(path.read_bytes())
        same(entry['source'], source, 'retained town submission source')
        response = entry.get('response')
        if not isinstance(response, dict):
            raise ValueError('original town response must be completed first')
        receipt = response['receipt']
        clerk_entry = loads((self.town.clerk.state / 'requests' / (town.worker.key(source['uri']) + '.json')).read_bytes())
        same(clerk_entry['receipt'], receipt, 'canonical clerk submission receipt')
        same(clerk_entry['request'], receipt['request'], 'canonical clerk submission request')
        same({key: receipt['source'][key] for key in source}, source, 'submission receipt source')
        same(receipt['id'], town.clerk.digest({key: value for key, value in receipt.items() if key != 'id'}), 'submission receipt identity')
        client = desk.Desk(self.queue.database, self.queue.artifacts, profile=self.queue.profile)
        same(client.retained_reply(receipt['request']), receipt['reply'], 'retained submission admission')
        if receipt['reply']['kind'] != 'committed':
            raise ValueError('compiler follow-up requires a committed submission')
        data, request = receipt['reply']['data'], receipt['request']
        roots = data['roots'] if request['op'] == 'transaction' else {request['object']: data['root'], **data.get('allocated', {})}
        same(roots.get(job['inputs']['object']), job['inputs']['expected'], 'job and original submission candidate root')
        if job['inputs']['expected']['state']['status'] != 'pending':
            raise ValueError('job must retain an exact pending candidate')
        return receipt

    def _completion(self, job, status):
        inputs = job['inputs']
        path = self.queue.artifacts / 'attempts' / (digest([inputs['principal'], inputs['intent']]) + '.json')
        if not path.exists():
            return None
        attempt = loads(path.read_bytes())
        same(attempt['inputs'], inputs, 'compiler attempt inputs')
        request = attempt['request']
        if (set(request) != {'op', 'object', 'principal', 'intent', 'expected', 'command', 'input'}
                or request['op'] != 'invoke' or request['command'] not in ('compiled', 'failed')):
            raise ValueError('unsupported compiler completion request')
        same({key: request[key] for key in inputs}, inputs, 'compiler completion request')
        execution = attempt['executionProfile']
        same(execution['profile'], job['profile'], 'compiler attempt profile')
        for name, sha in execution['files'].items():
            same(job['runtime']['files'].get(name), sha, 'compiler attempt runtime ' + name)
        client = desk.Desk(self.queue.database, self.queue.artifacts, profile=job['profile'])
        reply = client.retained_reply(request)
        if reply is None:
            return None
        if reply.get('kind') not in ('committed', 'refused'):
            raise ValueError('compiler reply is not a terminal admission')
        if 'receipt' in status:
            same(status['receipt'], reply, 'queue compiler receipt')
        artifact_id = request['input']['artifact']
        if 'artifact' in status:
            same(status['artifact'], artifact_id, 'queue compiler artifact')
        compiled = loads((self.queue.state / 'compiled' / (digest(job) + '.json')).read_bytes())
        same(compiled, {'artifact': artifact_id}, 'queued compiled build')
        build = desk.load_artifact(self.queue.artifacts, artifact_id)
        expected = inputs['expected']['state']
        for key, value in {'format': 'delvetalk-desk-build-v1', 'candidateRootSha256': digest(inputs['expected']),
                           'proposal': expected['proposal'], 'migration': expected['migration'],
                           'target': expected['target'], 'admissionProfile': job['profile'],
                           'sourceBindings': job['sourceBindings']}.items():
            same(build.get(key), value, 'compiler build ' + key)
        same(build['worker']['scripts/desk.py'], job['runtime']['files']['scripts/desk.py'], 'compiler worker')
        material = build.get('sourceMaterial')
        if not isinstance(material, dict):
            raise ValueError('compiler build lacks retained exact source material')
        for name, kind, ref_key in [('source', 'source', 'sourceRef'), ('scenarios', 'scenarios', 'scenariosRef')]:
            ref = desk.source_store.reference(material[name].encode('utf-8'), kind=kind)
            bound = job['sourceBindings'][ref_key]
            same({key: ref[key] for key in bound}, bound, 'compiler retained ' + name)
        report = build.get('report')
        if report is None and (build['passed'] or any(d['kind'] == 'scenario-failure' for d in build['diagnostics'])):
            raise ValueError('compiler build lacks its required fixture report')
        fixtures = []
        if report is not None:
            same(report['id'], digest({k: v for k, v in report.items() if k != 'id'}), 'compiler report identity')
            candidate = report['candidate']
            same(candidate['id'], digest({k: v for k, v in candidate.items() if k != 'id'}), 'reported candidate identity')
            same(candidate['artifact']['source']['text'], material['source'], 'reported exact source')
            same(candidate['scenarios']['source'], material['scenarios'], 'reported exact scenarios')
            same(candidate['scenarios']['value'], examples.load(material['scenarios'], loads), 'reported scenario values')
            same(candidate['artifact']['translation'], job['sourceBindings']['adapterPin'], 'reported adapter pins')
            same(report['execution']['admissionProfile'], job['profile'], 'reported runtime profile')
            for name, sha in report['execution']['files'].items():
                same(job['runtime']['files'].get(name), sha, 'reported compiler runtime ' + name)
            same(report['passed'], build['passed'], 'reported fixture outcome')
            fixtures = fixture_results(report)
        same(request['command'], 'compiled' if build['passed'] else 'failed', 'compiler outcome command')
        if build['passed']:
            same(request['input']['protocol'], build['protocol'], 'compiled protocol')
        else:
            same(request['input']['diagnostics'], build['diagnostics'], 'failed diagnostics')
        return {'request': request, 'reply': reply, 'artifact': artifact_id, 'build': build, 'fixtures': fixtures}

    def prepare(self, uri, cid, job_id):
        source = town_cards.publication_source({'uri': uri, 'cid': cid})
        job_path = self.queue.job_path(job_id)  # Validates identity even on historical replay.
        identity = digest({'source': source, 'job': job_id})
        directory = self.state / 'followups' / identity
        with town._lock(self.state / 'authoring.lock'):
            binding = {'town': str(self.town.state), 'clerk': str(self.town.clerk.state),
                       'database': str(self.queue.database), 'queue': str(self.queue.state),
                       'artifacts': str(self.queue.artifacts), 'profile': self.queue.profile}
            retain(self.state / 'binding.json', binding)
            terminal = directory / 'followup.json'
            if terminal.exists():
                return loads(terminal.read_bytes())
            config, book = self.town._configuration()
            same(str(self.town.clerk.database.resolve()), str(self.queue.database), 'compiler world custody')
            selected = self.town.clerk.execution_profile({'op': 'transaction'}, config)
            same(self.queue.profile, selected, 'compiler queue profile')
            queue_binding = loads((self.queue.state / 'queue.json').read_bytes())
            same(queue_binding, {'format': 'delvetalk-compiler-queue-v1', 'database': str(self.queue.database),
                                 'artifacts': str(self.queue.artifacts), 'profile': self.queue.profile}, 'compiler queue binding')
            job = compiler_queue.load_job(job_path)
            for key, value in {'database': str(self.queue.database), 'artifacts': str(self.queue.artifacts),
                               'profile': self.queue.profile}.items():
                same(job[key], value, 'compiler job custody ' + key)
            same(job['runtime']['profile'], job['profile'], 'queued runtime profile')
            submission = self._submission(source, job)
            retained = {'source': source, 'job': job_id, 'jobEvidence': job, 'submission': submission,
                        'cardbook': config['townCards'], 'implementation': implementation(config, self.queue.profile)}
            retain(directory / 'binding.json', retained)
            status = self.queue.status(job_id)
            result = {'format': FORMAT, 'id': identity, 'source': source, 'replyTo': source, 'job': job_id,
                      'status': 'pending', 'cards': [], 'fixtures': [], 'publication': 'paused'}
            evidence_path = directory / 'completion.json'
            if evidence_path.exists():
                evidence = loads(evidence_path.read_bytes())
            else:
                try:
                    completion = self._completion(job, status)
                except FileNotFoundError:
                    completion = None  # A confirmed reply without its report cannot become an adoption card.
                if completion is None:
                    result['status'] = 'uncertain' if status.get('attempts', 0) or status.get('phase') != 'queued' else 'pending'
                    result['queueObservation'] = status
                    result['notices'] = ['No fixture result or installation is claimed until retained compiler evidence is complete.']
                    result['body'] = describe(result)
                    result['textSha256'] = town_cards.sha(result['body'])
                    retain(directory / 'progress' / (digest(result) + '.json'), result)
                    return result
                reply = completion['reply']
                ready = reply['kind'] == 'committed' and completion['build']['passed']
                evidence = {'completion': completion, 'target': None, 'notices': []}
                if ready:
                    candidate = reply['data']['root']
                    same(candidate['state']['artifact'], completion['artifact'], 'ready candidate artifact')
                    for key in ('protocol', 'migration', 'target'):
                        same(candidate['state'][key], completion['build'][key], 'ready candidate ' + key)
                    if candidate['state']['status'] != 'ready':
                        raise ValueError('compiler admission did not retain a ready candidate')
                    target = job['inputs']['expected']['state']['target']
                    if target not in config['objects'] or job['inputs']['object'] not in config['objects']:
                        evidence['notices'].append('No adoption card: the candidate or target is not enrolled for town replies.')
                    else:
                        with town._lock(Path(str(self.queue.database) + '.lock')):
                            snapshot = loads(self.queue.database.read_bytes())
                        evidence['target'] = snapshot['objects'].get(target)
                        if evidence['target'] is None:
                            evidence['notices'].append('No adoption card: the target is currently absent.')
                evidence = retain(evidence_path, evidence)  # Exact target survives loss before card allocation.
            completion = evidence['completion']
            reply, build = completion['reply'], completion['build']
            result.update(status='refused' if reply['kind'] == 'refused' else ('ready' if build['passed'] else 'failed'),
                          compilerReceipt=reply, artifact=completion['artifact'], fixtures=completion['fixtures'],
                          diagnostics=build['diagnostics'], notices=evidence['notices'],
                          sourceMaterial=build['sourceMaterial'], syntax=build['proposal']['syntax'])
            if result['status'] == 'refused':
                result['notices'] = result['notices'] + ['Admission: ' + canonical(reply['data']).decode()]
            if result['status'] == 'ready' and evidence['target'] is not None:
                result['cards'] = [book.capture_adoption(job['inputs']['object'], reply['data']['root'],
                    build['target'], evidence['target'], alias='offer-' + identity[:12])]
            result['body'] = describe(result)
            result['textSha256'] = town_cards.sha(result['body'])
            return retain(terminal, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--clerk-state', type=Path, required=True)
    parser.add_argument('--town-state', type=Path)
    parser.add_argument('--state', type=Path)
    parser.add_argument('--queue', type=Path, required=True)
    parser.add_argument('--artifacts', type=Path, required=True)
    parser.add_argument('--profile', choices=desk.world.PROFILES, required=True)
    parser.add_argument('--json', action='store_true')
    parser.add_argument('uri')
    parser.add_argument('--cid', required=True)
    parser.add_argument('--job', required=True)
    args = parser.parse_args()
    try:
        operator = town.Town(args.clerk_state, state=args.town_state)
        queue = compiler_queue.CompilerQueue(args.queue, operator.clerk.database, args.artifacts, profile=args.profile)
        response = TownAuthoring(operator, queue, args.state).prepare(args.uri, args.cid, args.job)
        print(town.clerk.world.wire_dumps(response) if args.json else response['body'])
        return 0
    except (ValueError, OSError, KeyError, TypeError, RuntimeError) as error:
        print('town authoring: ' + str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
