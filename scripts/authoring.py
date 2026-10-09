"""Exact physical UTF-8 source custody; world offerings own authoring behavior."""
import source_store

MAX_SOURCE = source_store.LIMITS['source']
MAX_UPLOAD = 7 * 1048576

def exact(value, required, optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError('Missing or unknown source custody fields')


class SourceCustody:
    def __init__(self, portal):
        self.artifacts = portal.directory / 'artifacts'

    def source(self, payload):
        exact(payload, ('text',), ('kind',))
        if not isinstance(payload['text'], str):
            raise ValueError('Source text must be UTF-8 text')
        kind = payload.get('kind', 'source')
        ref = source_store.store_bytes(self.artifacts, payload['text'].encode('utf-8'), kind=kind)
        return {'source': ref['sha256'], 'bytes': ref['bytes'], 'ref': ref}

    def read_source(self, source, kind='source'):
        ref = source_store.ref_for(self.artifacts, source, kind=kind)
        raw = source_store.read_bytes(self.artifacts, ref, kind=kind)
        return {'source': source, 'bytes': len(raw), 'ref': ref, 'text': raw.decode('utf-8')}

    def catalog(self):
        return {'maxSourceBytes': MAX_SOURCE, 'links': {'source': '/api/authoring/source'}}
