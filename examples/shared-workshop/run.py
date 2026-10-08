#!/usr/bin/env python3
"""Run a local two-agent workshop through the existing Lean host profiles.

No network or agent model calls. Iris and Moss are scripted local principals;
this runner transports requests and checks their observations, not admission.
"""
import argparse
import concurrent.futures
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASK = 'workshop:benches'
OFFER = 'offer:moss'
SLOTS = ['answer:iris', 'answer:moss']
LAW = ['iris', 'moss']


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


world = load_module('workshop_world', ROOT / 'scripts/world.py')
proposal = load_module('workshop_proposal', ROOT / 'scripts/propose.py')


def read(name):
    return world.wire_loads((HERE / name).read_text())


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run_workshop(directory):
    """Use a fresh directory; return a complete request/receipt transcript."""
    for binary in ['delvetalk-world', 'delvetalk-transactions', 'delvetalk-typed']:
        require((ROOT / '.lake/build/bin' / binary).is_file(), f'Build {binary} first')
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    database = directory / 'world.json'
    require(not database.exists(), 'workshop requires a fresh world.json')
    for filename in ['report.json', 'proposal-report.json']:
        require(not (directory / filename).exists(), f'{filename} already exists')
    events = []

    def send(label, request):
        receipt = world.exchange(database, request, profile='transactions')
        events.append({'label': label, 'request': request, 'receipt': receipt})
        return receipt

    def inspect(name):
        return world.exchange(database, {'op': 'inspect', 'object': name,
                                         'principal': 'workshop-reader'}, profile='transactions')

    def committed(label, request):
        receipt = send(label, request)
        require(receipt['kind'] == 'committed', f'{label}: {receipt}')
        return receipt

    # The exact term checked here is used by both the task and offer programs.
    typed_job = read('boards.typed.json')
    task = read('task-v1.json')
    offer = read('offer.json')
    for definition in [task, offer]:
        price = definition['commands']['assign' if definition is task else 'quote']
        core = price['require'][3][1][1] if definition is task else price['set']['total'][1]
        require(core == typed_job['term'], 'typed packet must name the installed Bend term')
    proc = subprocess.run([str(ROOT / '.lake/build/bin/delvetalk-typed')],
                          input=world.wire_dumps(typed_job) + '\n', text=True,
                          capture_output=True, check=True, timeout=30)
    typed_receipt = world.wire_loads(proc.stdout)
    require(typed_receipt['status'] == 'accepted', 'boards function must type-check')

    for name, protocol in [(TASK, task), (OFFER, offer),
                           *[(name, read('answer-slot.json')) for name in SLOTS]]:
        committed('create ' + name, {'op': 'create', 'object': name, 'principal': 'iris',
                                    'intent': 'create:' + name, 'protocol': protocol, 'law': LAW})
    committed('Moss offers the materials estimate', {
        'op': 'invoke', 'object': OFFER, 'principal': 'moss', 'intent': 'quote',
        'expected': inspect(OFFER), 'command': 'quote', 'input': {}})
    assignment = committed('Iris accepts the offer and assigns the task atomically', {
        'op': 'transaction', 'principal': 'iris', 'intent': 'accept-and-assign',
        'reads': {TASK: inspect(TASK), OFFER: inspect(OFFER)}, 'calls': [
            {'object': OFFER, 'command': 'accept', 'input': {}},
            {'object': TASK, 'command': 'assign', 'inputFrom': 0}]})
    require(assignment['data']['results'][1]['total'] == 42, 'Bend estimate should be 42')
    before = {name: inspect(name) for name in [TASK, *SLOTS]}

    def completion(principal, intent):
        return {'op': 'transaction', 'principal': principal, 'intent': intent,
                'reads': copy.deepcopy(before), 'calls': [
                    {'object': TASK, 'command': 'complete', 'input': {'answer': 42}},
                    *[{'object': slot, 'command': 'publish', 'inputFrom': 0} for slot in SLOTS]]}

    # A routing mistake at the LAST slot must discard task completion and the
    # first slot's already-staged answer/outbox. There is no Python rollback.
    mistaken = completion('moss', 'misrouted-draft')
    mistaken['calls'][2] = {'object': SLOTS[1], 'command': 'publish',
                            'input': {'task': 'another-workshop', 'answer': 42, 'by': 'moss'}}
    refused = send('Moss catches a misrouted answer with atomic rollback', mistaken)
    require(refused['kind'] == 'refused' and refused['data'] == 'precondition failed',
            f'expected late precondition refusal: {refused}')
    after_rollback = {name: inspect(name) for name in before}
    require(after_rollback == before, 'late failure must not change any root')

    # Both authorized collaborators may complete an assigned task. They race
    # using the same roots; the custody wrapper serializes actual host requests.
    contenders = [completion(actor, 'complete:' + actor) for actor in LAW]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(world.exchange, database, req, profile='transactions')
                   for req in contenders]
        outcomes = [future.result() for future in futures]
    for req, receipt in zip(contenders, outcomes):
        events.append({'label': req['principal'] + ' competes to complete',
                       'request': req, 'receipt': receipt})
    require(sorted(r['kind'] for r in outcomes) == ['committed', 'refused'],
            'exactly one competing completion must commit')
    winner_index = next(i for i, r in enumerate(outcomes) if r['kind'] == 'committed')
    winner_request, winner = contenders[winner_index], outcomes[winner_index]
    loser_request, loser = contenders[1-winner_index], outcomes[1-winner_index]
    require(loser['data'] == 'stale read root', 'competitor must face exact stale roots')
    require(send('Exact successful completion retry', winner_request) == winner,
            'successful retry must recover original receipt')
    require(send('Exact losing completion retry', loser_request) == loser,
            'refused retry must recover original receipt')
    completed = {name: inspect(name) for name in before}
    require(completed[TASK]['state']['answer'] == 42, 'task answer missing')
    for slot in SLOTS:
        require(completed[slot]['state']['answer'] == winner['data']['results'][0],
                'both slots must contain the same committed completion record')
    duplicate = send('Fresh reference to the same answer slot cannot publish twice', {
        'op': 'invoke', 'principal': 'moss', 'intent': 'quoted-slot-reference',
        'object': SLOTS[0], 'expected': inspect(SLOTS[0]), 'command': 'publish',
        'input': {'task': TASK, 'answer': 42, 'by': 'moss'}})
    require(duplicate['kind'] == 'refused' and duplicate['data'] == 'precondition failed',
            'slot must be semantically one-shot, independently of intent identity')

    # Moss proposes the next protocol in a reviewed Markdown syntax. Isolated
    # scenario evidence is a proposal; it grants no installation authority.
    proposed = proposal.propose('protocol-markdown@1', (HERE / 'task-v2.md').read_bytes(),
                                (HERE / 'task-v2-scenarios.json').read_bytes())
    require(proposed['passed'], 'v2 isolated scenarios must pass')
    candidate = proposed['candidate']
    protocol_v2 = candidate['artifact']['lowered']
    pre_upgrade = inspect(TASK)
    migrated = {**pre_upgrade['state'], 'retrospective': None}
    upgrade = {'op': 'reprogram', 'object': TASK, 'principal': 'iris',
               'intent': 'install-v2:' + candidate['id'], 'expected': pre_upgrade,
               'protocol': protocol_v2, 'state': migrated}
    outsider = {**upgrade, 'principal': 'eve', 'intent': 'untrusted-install'}
    unauthorized = send('Proposal evidence gives Eve no authority', outsider)
    require(unauthorized['kind'] == 'refused' and unauthorized['data'] == 'unauthorized',
            'proposal must not bypass current law')
    installed = committed('Iris installs Moss proposal with explicit state migration', upgrade)
    new_root = installed['data']['root']
    require(new_root['law'] == pre_upgrade['law'], 'reprogram must preserve law')
    require(new_root['version'] == pre_upgrade['version'] + 1, 'reprogram is one revision')
    require(new_root['state'] == migrated, 'migration must preserve completed work')
    require(new_root['protocol'] == protocol_v2, 'install must use exact proposed protocol')
    conflicting = copy.deepcopy(upgrade)
    conflicting.update(principal='moss', intent='concurrent-protocol-edit')
    conflicting['protocol']['edition'] = 'competing edit'
    stale_edit = send('Moss concurrent protocol edit uses stale root', conflicting)
    require(stale_edit['kind'] == 'refused' and stale_edit['data'] == 'stale read root',
            'concurrent edit must be refused')
    reflected = committed('Moss uses the newly installed action', {
        'op': 'invoke', 'object': TASK, 'principal': 'moss', 'intent': 'retrospective',
        'expected': inspect(TASK), 'command': 'reflect',
        'input': {'note': 'Pre-cut the boards before assembly.'}})
    locked = committed('Iris deliberately seals the completed task', {
        'op': 'law', 'object': TASK, 'principal': 'iris', 'intent': 'seal-task',
        'expected': inspect(TASK), 'law': []})
    rescue = {**upgrade, 'expected': locked['data']['root'], 'intent': 'attempt-owner-rescue'}
    rescue_receipt = send('Former authority cannot reprogram through lockout', rescue)
    require(rescue_receipt['kind'] == 'refused' and rescue_receipt['data'] == 'unauthorized',
            'deliberate law lockout must have no reprogram bypass')
    require(send('Historical installation retry survives lockout', upgrade) == installed,
            'old admitted receipt must remain retrievable after lockout')
    require(send('Historical completion retry survives lockout', winner_request) == winner,
            'transaction history must remain retrievable after lockout')
    final = {name: inspect(name) for name in [TASK, OFFER, *SLOTS]}
    require(final[TASK] == locked['data']['root'], 'historical retry must not undo later state')
    report = {'format': 'delvetalk-shared-workshop-v1', 'winner': winner_request['principal'],
              'typed': {'job': typed_job, 'receipt': typed_receipt},
              'proposal': {'candidate': candidate['id'], 'report': proposed['id'], 'passed': proposed['passed']},
              'before_completion': before, 'after_rollback': after_rollback,
              'completed': completed, 'pre_upgrade': pre_upgrade, 'installed': new_root,
              'retrospective': reflected['data']['result'], 'final': final, 'events': events}
    (directory / 'proposal-report.json').write_bytes(proposal.translation.canonical(proposed) + b'\n')
    (directory / 'report.json').write_text(world.wire_dumps(report) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='new directory to retain world, receipts and proposal evidence')
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=False)
        report = run_workshop(args.output)
    else:
        with tempfile.TemporaryDirectory(prefix='delvetalk-workshop-') as temporary:
            report = run_workshop(temporary)
    summary = {'workshop': TASK, 'answer': report['final'][TASK]['state']['answer'],
               'completion_winner': report['winner'], 'answer_slots': 2,
               'typed': report['typed']['receipt']['status'], 'proposal_passed': report['proposal']['passed'],
               'protocol_edition': report['final'][TASK]['protocol']['edition'],
               'retrospective': report['final'][TASK]['state']['retrospective'],
               'final_law': report['final'][TASK]['law'], 'events': len(report['events'])}
    print(world.wire_dumps(summary))
    return 0


if __name__ == '__main__':
    sys.exit(main())
