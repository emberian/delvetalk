#!/usr/bin/env python3
"""Readable authoring helpers for the checked-in protocol-json source."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
L = lambda value: ['literal', value]
S = lambda key: ['state', key]
I = lambda key: ['input', key]
B = lambda term, *args: ['bend', ['lam', term], list(args)]
V = ['bound', 0]
T = ['boolean', True]
F = ['boolean', False]
label = lambda value: ['label', value]
get = lambda term, key: ['get', term, key]
eq = lambda a, b: ['binary', 'labelEqual', a, b]
choose = lambda cond, yes, no: ['ifBool', cond, yes, no]
record = lambda values: ['record', [[key, value] for key, value in values.items()]]

def nonempty(key):
    return [B(choose(eq(V, label('')), F, T), I(key)), L(True)]

def enum(key, choices):
    term = F
    for value in reversed(choices):
        term = choose(eq(V, label(value)), T, term)
    return [B(term, I(key)), L(True)]

def command(role, guards, writes, result):
    return {'require': [[['principal'], L(role)]] + guards,
            'set': writes, 'result': result, 'outbox': []}

def build():
    initial = {'northOffered': False, 'southOffered': False, 'arranged': False,
               'northConsent': False, 'southConsent': False, 'opened': False,
               'north': {}, 'south': {}, 'caption': '', 'first': ''}
    fields = {'title': {'type': 'string', 'minLength': 1, 'maxLength': 120},
              'note': {'type': 'string', 'minLength': 1, 'maxLength': 320},
              'minutes': {'type': 'nat', 'minimum': 1, 'maximum': 30},
              'fragile': {'type': 'bool'},
              'light': {'type': 'enum', 'options': ['dim', 'bright']}}
    commands, forms = {}, {}
    for artist in ('north', 'south'):
        name = 'offer-' + artist
        commands[name] = command(artist,
            [[S(artist + 'Offered'), L(False)], [S('arranged'), L(False)],
             nonempty('title'), nonempty('note'), enum('light', ['dim', 'bright']),
             [B(['binary', 'lessEqual', ['nat', '1'], V], I('minutes')), L(True)],
             [B(['binary', 'lessEqual', V, ['nat', '30']], I('minutes')), L(True)],
             [B(choose(V, T, T), I('fragile')), L(True)]],
            {artist + 'Offered': L(True), artist: ['record', {key: I(key) for key in fields}]},
            ['record', {'artist': ['principal'], 'title': I('title')}])
        forms[name] = {'label': 'Offer the ' + artist + ' piece', 'fields': fields}
        name = 'consent-' + artist
        commands[name] = command(artist,
            [[S('arranged'), L(True)], [S(artist + 'Consent'), L(False)], [S('opened'), L(False)]],
            {artist + 'Consent': L(True)}, S('caption'))
        forms[name] = {'label': 'Approve this arrangement as ' + artist, 'fields': {}}
    commands['arrange'] = command('curator',
        [[S('northOffered'), L(True)], [S('southOffered'), L(True)], [S('arranged'), L(False)],
         nonempty('caption'), enum('first', ['north', 'south'])],
        {'arranged': L(True), 'caption': I('caption'), 'first': I('first')}, I('caption'))
    forms['arrange'] = {'label': 'Propose the exhibition arrangement', 'fields': {
        'caption': {'type': 'string', 'minLength': 1, 'maxLength': 400},
        'first': {'type': 'enum', 'options': ['north', 'south']}}}
    commands['open'] = command('curator',
        [[S('arranged'), L(True)], [S('northConsent'), L(True)],
         [S('southConsent'), L(True)], [S('opened'), L(False)]],
        {'opened': L(True)}, S('caption'))
    forms['open'] = {'label': 'Open the exhibition', 'fields': {}}
    # A state-only pure view: observed phase is useful; it does not confer authority.
    state = ['bound', 1]
    flag = lambda key: get(state, key)
    action = lambda name: record({'text': label(forms[name]['label']),
                                  'command': label(name), 'input': record({})})
    def outstanding(prefix, suffix, done):
        north, south = prefix + 'north', prefix + 'south'
        one_n = record({north: action(north)})
        one_s = record({south: action(south)})
        both = record({north: action(north), south: action(south)})
        return choose(flag('north' + suffix), choose(flag('south' + suffix), done, one_s),
                      choose(flag('south' + suffix), one_n, both))
    actions = outstanding('consent-', 'Consent', record({'open': action('open')}))
    offers = outstanding('offer-', 'Offered', record({'arrange': action('arrange')}))
    actions = choose(flag('opened'), record({}), choose(flag('arranged'), actions, offers))
    prose = choose(flag('opened'), flag('caption'),
        choose(flag('arranged'), flag('caption'), label('Two pieces, one room. Offer each piece, arrange them, then approve together.')))
    for artist in ('south', 'north'):
        prose = choose(eq(V, label(artist)), choose(flag(artist + 'Offered'),
                    get(flag(artist), 'note'), label('This artist has not offered a piece.')), prose)
    term = ['lam', ['lam', record({'title': label('The Room Between'), 'prose': prose, 'actions': actions})]]
    return {'profile': 'delvetalk-local-v1', 'name': 'shared-exhibition-v1',
            'description': 'A two-artist exhibition opens only after both approve the curator arrangement.',
            'initial': initial, 'commands': commands, 'affordances': forms,
            'viewPanels': [{'id': 'north', 'label': 'North artist’s note'},
                           {'id': 'south', 'label': 'South artist’s note'}],
            'viewProgram': {'profile': 'delvetalk-bend-view-v1', 'term': term}}


def scenarios():
    north = {'title': 'Fold', 'note': 'A paper test piece.', 'minutes': 4, 'fragile': True, 'light': 'dim'}
    south = {'title': 'Thread', 'note': 'A woven test piece.', 'minutes': 6, 'fragile': False, 'light': 'bright'}
    step = lambda who, cmd, data={}, kind='committed', root='current': {
        'principal': who, 'command': cmd, 'input': data, 'root': root, 'kind': kind}
    happy = [step('north', 'offer-north', north), step('south', 'offer-south', south),
             step('curator', 'arrange', {'caption': 'Fold meets Thread.', 'first': 'south'}),
             step('south', 'consent-south'), step('north', 'consent-north'), step('curator', 'open')]
    last = build()['initial'].copy()
    last.update(north=north, south=south, northOffered=True, southOffered=True,
                arranged=True, northConsent=True, southConsent=True, opened=True,
                caption='Fold meets Thread.', first='south')
    happy[-1] = {**happy[-1], 'state': last, 'result': 'Fold meets Thread.', 'outbox': []}
    invalid = [step('curator', 'open', kind='refused'),
               step('north', 'consent-north', kind='refused'),
               step('south', 'offer-north', {**north, 'principal': 'north'}, 'refused'),
               step('north', 'offer-north', {**north, 'title': ''}, 'refused'),
               step('north', 'offer-north', {**north, 'minutes': 0}, 'refused'),
               step('north', 'offer-north', {**north, 'minutes': 31}, 'refused'),
               step('north', 'offer-north', {**north, 'minutes': True}, 'refused'),
               step('north', 'offer-north', {**north, 'fragile': 'true'}, 'refused'),
               step('north', 'offer-north', {**north, 'light': 'sun'}, 'refused'),
               happy[0], step('north', 'offer-north', north, 'refused'),
               step('south', 'offer-south', south, 'refused', 'initial'), happy[1], happy[2],
               step('curator', 'open', kind='refused'), happy[3],
               step('curator', 'open', kind='refused'), happy[4],
               step('curator', 'arrange', {'caption': 'Changed after consent.', 'first': 'north'}, 'refused'),
               happy[5], step('curator', 'open', kind='refused')]
    return [{'name': name, 'law': ['north', 'south', 'curator'], 'steps': steps}
            for name, steps in [('both-consent-then-open', happy), ('role-types-stale-and-consent', invalid)]]

if __name__ == '__main__':
    for name, data in [('protocol.json', build()), ('migration.json', build()['initial']), ('scenarios.json', scenarios())]:
        (HERE / name).write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
