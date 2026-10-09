"""Text authoring and exact captured migrations over existing source desks."""
import copy
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_offers
import desk
import room


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


forge = module('spween_workshop_forge', 'protocols/town-forge/generate.py')
source_desk_package = module('spween_source_desk_package', 'protocols/source-desk/package.py')
SYNTAX = 'spween-handler-workshop@1'


def authoring_source(revision=1):
    if revision not in (1, 2):
        raise ValueError('fixture revision must be 1 or 2')
    scene = (HERE / 'moth.scene').read_bytes().decode('utf-8')
    handler = (HERE / ('Handler.obend' if revision == 1 else 'Chorus.obend')).read_bytes().decode('utf-8')
    text = 'spween handler workshop 1\n\n```spween\n' + scene + '```\n\n```obend Handler\n' + handler + '```\n'
    if revision == 2:
        runtime = (HERE / 'LanternRuntime.obend').read_bytes().decode('utf-8')
        text += '\n```obend SceneRuntime\n' + runtime + '```\n'
    return text


def examples():
    return (HERE / 'moth.examples').read_bytes().decode('utf-8')


def source_desk():
    """The ordinary source Candidate; syntax is chosen by the writing source."""
    return source_desk_package.candidate()


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
    return {'objects': forge.factory('objects', placeholder, object_law),
            'desks': source_desk_package.factory(compiler, authors),
            'writers': source_desk_package.writing_factory()}


def submission_offer(writer, writer_root, observations, *, database=None):
    """Capture the actual admitted writing participant's source invitation."""
    view = room.inspect_object(writer_root, writer)
    roots = dict(observations)
    roots[writer] = writer_root
    return source_offers.capture(view, roots, database=database)['submit']


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
