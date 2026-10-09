"""Text authoring and exact captured migrations over existing source desks."""
import copy
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import composite_offers
import desk


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


forge = module('spween_workshop_forge', 'protocols/town-forge/generate.py')
SYNTAX = 'spween-handler-workshop@1'


def authoring_source(revision=1):
    if revision not in (1, 2):
        raise ValueError('fixture revision must be 1 or 2')
    scene = (HERE / 'moth.scene').read_bytes().decode('utf-8')
    handler = (HERE / ('Handler.obend' if revision == 1 else 'Chorus.obend')).read_bytes().decode('utf-8')
    return 'spween handler workshop 1\n\n```spween\n' + scene + '```\n\n```obend Handler\n' + handler + '```\n'


def examples():
    return (HERE / 'moth.examples').read_bytes().decode('utf-8')


def source_desk():
    """Submit only through a captured migration card; compilation remains ordinary."""
    protocol = forge.source_desk()
    protocol['name'] = 'spween-handler-workshop-desk-v1'
    protocol['description'] = 'Write a Spween scene and Bend handlers; preserve a captured target state explicitly.'
    protocol['initial']['proposal']['syntax'] = SYNTAX
    submit = protocol['commands']['submit']
    submit['set']['proposal'][1]['syntax'] = forge.L(SYNTAX)
    submit['set']['migration'] = forge.I('migration')
    # An ordinary empty view cannot capture another object's state. The explicit
    # submission offer below captures both roots and binds the full migration.
    protocol['affordances'] = {}
    protocol['viewProgram'] = forge.view(forge.label('The scene and handler desk'),
        forge.label('Choose the object to revise, then obtain a writing card that preserves its captured state.'),
        forge.record({}))
    return protocol


def build(authors, compiler, *, initial_state=None):
    authors = forge.principals(authors)
    forge.principals([compiler])
    if initial_state is None:
        artifact = desk.translate.translate(SYNTAX, authoring_source().encode('utf-8'))
        initial_state = artifact['lowered']['initial']
    placeholder = forge.door()
    placeholder.update(name='unwritten-spween-handler-workshop-v1', initial=copy.deepcopy(initial_state))
    placeholder['commands'] = {command: {'require': [[forge.L(False), forge.L(True)]],
        'set': {}, 'result': forge.L('The workshop awaits its scene.'), 'outbox': []}
        for command in ('start', 'choose')}
    placeholder['affordances'] = {}
    placeholder.pop('viewProgram', None)
    placeholder['description'] = 'Write a scene and handlers at a desk, check examples, then adopt.'
    object_law = forge.L(forge.scoped({key: authors for key in ('start', 'choose')}, authors, authors))
    desk_law = forge.L(forge.scoped({'submit': authors, 'adopt': authors,
                                   'compiled': [compiler], 'failed': [compiler]}))
    return {'objects': forge.factory('objects', placeholder, object_law),
            'desks': forge.factory('desks', source_desk(), desk_law)}


def submission_offer(candidate, candidate_root, target, target_root):
    """Bind one complete migration to an exact target observation, with no refresh.

    Only the authored text is supplied later. Lean checks both roots when that
    text arrives; adoption separately checks the reviewed target/candidate roots.
    """
    fields = [{'name': name, 'label': label, 'type': 'string', 'required': True,
               'minLength': 1, 'maxLength': 4096} for name, label in
              [('source', 'Scene and ordered Bend handler blocks'), ('scenarios', 'Examples to check')]]
    return composite_offers.validate({'format': composite_offers.FORMAT,
        'title': 'Write a scene with ordinary Bend handlers',
        'label': 'Preserve the entire captured state of ' + target + ' at version ' + str(target_root['version']) + '.',
        'command': 'submit', 'reads': {candidate: candidate_root, target: target_root},
        'calls': [{'object': candidate, 'command': 'submit', 'input': {
            'target': target, 'source': None, 'scenarios': None,
            'migration': copy.deepcopy(target_root['state'])}}],
        'fields': fields, 'bindings': [{'field': name, 'call': 0, 'input': name} for name in ('source', 'scenarios')]})


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', action='store_true', help='print the exact text residents submit')
    parser.add_argument('--revision', type=int, choices=(1, 2), default=1)
    args = parser.parse_args()
    if args.source:
        sys.stdout.write(authoring_source(args.revision))
    else:
        (HERE / 'source-desk.json').write_bytes(desk.canonical(source_desk()) + b'\n')
