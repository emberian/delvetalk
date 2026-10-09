"""Declarative TWO-player table package construction; no gameplay/admission here.

The returned JSON is interpreted only by the compiled Lean profile. This module
fills a userspace protocol template with a table identity and two DID grants.
"""
import json
from pathlib import Path

GAME = Path(__file__).resolve().parents[1] / 'automatafl'
DOMAIN = 'delvetalk.automatafl.commit.v1'
OPENING = json.loads((GAME / 'original-opening.json').read_text())


def literal(value):
    return ['literal', value]


def state(name):
    return ['state', name]


def supplied(name):
    return ['input', name]


def primitive(name, left, right):
    return ['bend', ['lam', ['lam', ['binary', name, ['bound', 1], ['bound', 0]]]], [left, right]]


def member(record, name):
    return ['bend', ['lam', ['get', ['bound', 0], name]], [record]]


def natural(expr):
    return primitive('add', expr, literal(0))


def source_bundle(entry='play'):
    return {'modules': [{'name': name, 'source': (GAME / (name + '.obend')).read_text()}
                        for name in ['Automatafl', 'Validated']], 'entry': entry}


def initial_state(table_id):
    # The original stock two-player opening; there is no offered board parameter.
    return {'table': table_id, 'round': 0, 'width': OPENING['width'], 'height': OPENING['height'],
            'game': {'board': int(OPENING['board']),
                     'automaton': OPENING['automaton'], 'marks': 0, 'status': 0, 'winner': 0},
            'commit0': '', 'commit1': '', 'revealed0': False, 'revealed1': False,
            'source0': 0, 'target0': 0, 'source1': 0, 'target1': 0}


def protocol(table_id):
    commands = {}
    live = [[state('table'), ['object']], [member(state('game'), 'winner'), literal(0)]]
    same_round = [[state('round'), supplied('round')]]
    for seat in (0, 1):
        suffix = str(seat)
        commands['commit' + suffix] = {
            'require': live + same_round + [
                [state('commit' + suffix), literal('')],
                [['sha256-valid', supplied('digest')], literal(True)]],
            'set': {'commit' + suffix: supplied('digest')},
            'result': literal('committed'), 'outbox': []}
        preimage = ['array', [literal(DOMAIN), ['object'], state('round'), literal(seat),
                               natural(supplied('source')), natural(supplied('target')),
                               supplied('nonce')]]
        commands['reveal' + suffix] = {
            'require': live + same_round + [
                [primitive('labelEqual', state('commit0'), literal('')), literal(False)],
                [primitive('labelEqual', state('commit1'), literal('')), literal(False)],
                [state('revealed' + suffix), literal(False)],
                [['sha256-valid', supplied('nonce')], literal(True)],
                [['sha256', preimage], state('commit' + suffix)]],
            'set': {'revealed' + suffix: literal(True),
                    'source' + suffix: natural(supplied('source')),
                    'target' + suffix: natural(supplied('target'))},
            'result': literal('revealed'), 'outbox': []}
    arguments = [state('width'), state('height'), member(state('game'), 'board'),
                 member(state('game'), 'automaton'), member(state('game'), 'marks'),
                 state('source0'), state('target0'), state('source1'), state('target1')]
    commands['resolve'] = {
        'require': live + same_round + [[state('revealed0'), literal(True)],
                                      [state('revealed1'), literal(True)]],
        'set': {'game': ['package', source_bundle(), arguments],
                'round': primitive('add', state('round'), literal(1)),
                'commit0': literal(''), 'commit1': literal(''),
                'revealed0': literal(False), 'revealed1': literal(False),
                'source0': literal(0), 'target0': literal(0),
                'source1': literal(0), 'target1': literal(0)},
        'result': literal('resolved'), 'outbox': []}
    return {'profile': 'delvetalk-local-v1', 'name': 'automatafl-two-player-table-v1',
            'initial': initial_state(table_id), 'commands': commands}


def law(seat0_did, seat1_did):
    # Configuration of explicit grants, not a client-side authorization decision.
    return {'profile': 'delvetalk-scoped-law-v1', 'invoke': {
        'commit0': [seat0_did], 'reveal0': [seat0_did],
        'commit1': [seat1_did], 'reveal1': [seat1_did],
        'resolve': [seat0_did, seat1_did]}, 'reprogram': [], 'law': []}


def create_request(table_id, seat0_did, seat1_did, principal, intent):
    return {'op': 'create', 'object': table_id, 'principal': principal, 'intent': intent,
            'protocol': protocol(table_id), 'law': law(seat0_did, seat1_did)}


if __name__ == '__main__':
    import argparse
    import json
    parser = argparse.ArgumentParser(description='Emit an immutable two-player table create request.')
    parser.add_argument('--table', required=True)
    parser.add_argument('--seat0', required=True)
    parser.add_argument('--seat1', required=True)
    parser.add_argument('--principal', required=True)
    parser.add_argument('--intent', required=True)
    args = parser.parse_args()
    print(json.dumps(create_request(args.table,args.seat0,args.seat1,args.principal,args.intent),
                     ensure_ascii=False,separators=(',',':')))
