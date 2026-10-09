"""Physical packaging of ordinary source Candidate desks and their factory."""
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def candidate():
    spec = importlib.util.spec_from_file_location('ordinary_candidate_package', ROOT / 'protocols/editor/generate.py')
    package = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(package)
    return package.candidate(editor_mode=False)


def factory(compiler, reporters):
    modules = source_object.read_modules([
        ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Allocation', ROOT / 'world/lib/prelude/Allocation.obend'),
        ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('Factory', ROOT / 'protocols/editor/Factory.obend'),
        ('WorkshopFactory', HERE / 'Factory.obend')])
    config = {'compiler': compiler, 'reporters': list(reporters), 'candidate': candidate()}
    return source_object.load(modules, syntax='objective-bend-spell@3',
        constructor='initial', arguments=[source_object.value(config)])


def writing(candidate, target, syntax):
    modules = source_object.read_modules([
        ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Writing', HERE / 'Writing.obend')])
    return source_object.load(modules, syntax='objective-bend-spell@3',
        constructor='initial', arguments=[source_object.data({
            'candidate': candidate, 'target': target, 'syntax': syntax})])
