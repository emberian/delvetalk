"""Physical loader for the explicit source-owned private notebook."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import source_object


def modules():
    paths = [('Abi', 'world/lib/prelude/Abi.obend'),
             ('List', 'world/lib/prelude/List.obend'), ('Preparation', 'world/lib/prelude/Preparation.obend'),
             ('Encounter', 'world/lib/prelude/Encounter.obend'),
             ('Document', 'world/lib/document/Document.obend'),
             ('Conversation', 'protocols/conversation/Conversation.obend'),
             ('Interpretation', 'protocols/interpretation/Interpretation.obend'),
             ('ModelEncounter', 'protocols/interpretation/Encounter.obend'),
             ('ConversationModel', 'protocols/interpretation/ConversationModel.obend'),
             ('Notebook', 'protocols/account-heap/Notebook.obend')]
    return source_object.read_modules([(name, ROOT / path) for name, path in paths])


def notebook():
    return source_object.load(modules(), syntax='objective-bend-spell@3')
