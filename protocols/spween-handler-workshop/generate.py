"""Text authoring and exact captured migrations over existing source desks."""
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_offers
import desk
import source_object


def module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


room = module('spween_workshop_room', 'scene/room.py')
forge = module('spween_workshop_forge', 'protocols/town-forge/generate.py')
handlers = module('spween_workshop_handlers', 'scene/handlers.py')
adapter = module('spween_workshop_adapter', 'syntaxes/spween_workshop.py')
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
    material = adapter.parse_source(authoring_source())
    document = handlers.bridge({'op': 'parse', 'source': material['scene']})
    modules = handlers.modules_for(document, handler_modules=material['handlerModules'],
        scene_source=(HERE / 'UnwrittenScene.obend').read_bytes().decode('utf-8'))
    if initial_state is None:
        placeholder = source_object.load(modules, syntax='objective-bend-object',
            constructor='configure', arguments=[handlers.scene_data(document)])
    else:
        placeholder = source_object.load(modules, syntax='objective-bend-object',
            constructor='initial', arguments=[initial_state['model']])
    return {'objects': forge.object_factory(placeholder, authors, ['start', 'choose'], managers=authors),
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
        sys.stdout.buffer.write(desk.canonical(source_desk()) + b'\n')
