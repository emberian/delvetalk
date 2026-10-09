"""Load the explicit source-composed contract candidate; no workflow recipe."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def candidate():
    modules = source_object.read_modules([
        ('Abi', ROOT / 'world/lib/prelude/Abi.obend'),
        ('List', ROOT / 'world/lib/prelude/List.obend'), ('Preparation', ROOT / 'world/lib/prelude/Preparation.obend'),
        ('Encounter', ROOT / 'world/lib/prelude/Encounter.obend'),
        ('Candidate', ROOT / 'protocols/editor/Candidate.obend'),
        ('ContractWorkshop', ROOT / 'protocols/contract-workshop/Workshop.obend'),
        ('ContractCandidate', ROOT / 'protocols/contract-workshop/ContractCandidate.obend')])
    return source_object.load(modules, syntax='objective-bend-spell@3')
