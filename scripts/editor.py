"""Physical custody for source-prepared Editor interactions.

The captured source export chooses the turn or asks a question. This helper
retains its exact native result and recovers the same admission after lost replies.
"""
import copy
from pathlib import Path

import clerk
import desk
import source_offers


class Editor:
    def __init__(self, client, custody):
        self.client = client
        self.custody = Path(custody)

    def interact(self, invitation, contribution, principal, intent):
        inputs = {'invitation': copy.deepcopy(invitation), 'contribution': copy.deepcopy(contribution),
                  'principal': principal, 'intent': intent}
        identity = desk.digest({'principal': principal, 'intent': intent})
        path = self.custody / 'interactions' / (identity + '.json')
        if path.exists():
            retained = desk.loads(path.read_bytes())
            if desk.canonical(retained['inputs']) != desk.canonical(inputs):
                raise ValueError('interaction identity already binds different captured inputs')
        else:
            retained = {'inputs': inputs}
            clerk.save(path, retained)
        if 'preparation' not in retained:
            retained['preparation'] = source_offers.prepare(invitation, principal, intent, contribution,
                                                          database=self.client.database)
            clerk.save(path, retained)
        if retained['preparation']['kind'] == 'ready' and 'receipt' not in retained:
            retained['receipt'] = self.client.exchange(retained['preparation']['request'])
            clerk.save(path, retained)
        return copy.deepcopy(retained)
