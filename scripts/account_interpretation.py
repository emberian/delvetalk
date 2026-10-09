"""Account-scoped model activity custody and opaque native source transport.

The manager's bounded worker supplies identity, realm, and physical custody.
Source constructs prompts and checks proposals; this helper never maps domain
fields, chooses an application operation, or admits its own model output.
"""
import base64
import hashlib
import desk

encoded = desk.canonical


def run(manager, identity, realm, payload):
    identity, key, directory, resident = manager._context(identity, realm)
    portal = manager._portal(identity, realm)
    if manager.model_provider is not None:
        from interpret import AnthropicProposer
        scope = encoded([identity['accountId'], identity['did'], realm,
                         'urn:delvetalk:heap:' + key if resident else manager.shared_world]).decode()
        portal.proposer = AnthropicProposer(None, directory=directory / 'models' / realm,
            identity_scope=scope, provider=manager.model_provider)
    import interpret
    import source_object
    import source_packages
    import source_offers
    from scene import projection
    if not isinstance(payload, dict) or set(payload) != {'card', 'text'}:
        raise ValueError('interpretation requires exactly card and text')
    interpret.string(payload['text'], interpret.MAX_TEXT)
    saved = portal._read('cards', payload['card'])
    token = base64.b32encode(hashlib.sha256(encoded(payload)).digest()).decode().lower()[:12]
    path = portal.state / 'interpretations' / (token + '.json')
    if path.exists():
        memo = portal._read('interpretations', token)
        if encoded(memo['input']) != encoded(payload):
            raise ValueError('interpretation custody key collision')
        if 'result' in memo:
            return {**memo['result'], 'interpretation': token}
    else:
        # Reserve custody before any provider work. Each repeated original
        # contribution against this exact card has one retained identity.
        memo = {'input': payload}
        manager._save_encounter(path, memo)
    portal._pins(saved)
    descriptor = projection.interpretation(saved['view'])
    if descriptor is None or portal.proposer is None or interpret.token_input(payload['text']):
        result = portal.interpretation(payload)
        result.pop('interpretation', None)
    else:
        root = saved['view']['root']
        package = root['protocol']['viewProgram']['package']
        source_packages.validate_selector(package)
        modules = source_packages.validate_tables(root['protocol'])[package['name']]['modules']
        codec = descriptor.get('contributionCodec', 'value')
        if 'sourceRequest' not in memo:
            empty = source_object.variant('nil', source_object.record({}))
            native = interpret.native(descriptor['request'], [root['state']['model'],
                source_object.data(payload['text']), empty,
                source_object.data({'object': saved['view']['object'], 'principal': identity['did']})], modules=modules)
            fields = {field['name']: field['value'] for field in native['fields']}
            memo['sourceRequest'] = {'job': source_object.plain(fields['job']),
                'envelope': fields['envelope'] if codec == 'data' else source_object.values('decode', [fields['envelope']])[0]}
            manager._save_encounter(path, memo)
        request = memo['sourceRequest']
        portal._pins(saved)
        try:
            reply = portal.proposer.request_source(request['job'], source_modules=modules,
                envelope=request['envelope'])
        except Exception as error:
            memo['providerReceipt'] = portal.proposer.last_receipt
            status = getattr(error, 'status', (memo['providerReceipt'] or {}).get('status', 'unavailable'))
            result = {'status': status, 'via': 'source', 'original': payload['text'],
                'providerReceipt': memo['providerReceipt'],
                'message': str(error) if isinstance(error, interpret.ProviderReplyError) else 'No confirmed interpretation is available. Recover this saved contribution before retrying.'}
            if status in ('pending', 'uncertain', 'rejected', 'provider-error'):
                memo['result'] = result
            manager._save_encounter(path, memo)
            return {**result, 'interpretation': token}
        memo['providerReceipt'] = portal.proposer.last_receipt
        memo['providerReply'] = reply
        manager._save_encounter(path, memo)
        invitation = {'format': source_offers.FORMAT, 'object': saved['view']['object'],
            'root': root, 'entry': descriptor['prepare'], 'observations': [], 'contributionCodec': codec,
            'title': saved['card']['title'], 'label': 'Retain this interpreted contribution', 'fields': []}
        contribution = (source_object.record({'request': request['envelope'], 'reply': source_object.value(reply)})
                        if codec == 'data' else {'request': request['envelope'], 'reply': reply})
        outcome = source_offers.prepare_value(invitation, identity['did'], 'interpretation:' + token,
            contribution,
            database=None if resident else manager.shared_database, receiver=resident)
        portal._pins(saved)
        result = {'status': outcome['kind'], 'message': outcome.get('message', outcome.get('summary', '')),
                  'via': 'source', 'original': payload['text'], 'providerReceipt': memo['providerReceipt']}
        if outcome['kind'] == 'ready':
            draft = {'interpretation': token, 'card': payload['card'],
                'object': saved['view']['object'], 'version': root['version'],
                'command': descriptor['prepare'], 'summary': outcome.get('summary', 'Retain interpreted contribution'),
                'request': outcome['request'], 'runtime': saved['runtime'], 'localPrincipal': identity['did'],
                'wire': portal.request_wire(outcome['request']), 'reply': None}
            alias = portal._store('drafts', draft)
            result['draft'] = portal.draft(alias)
        else:
            result['outcome'] = outcome
    memo['result'] = result
    manager._save_encounter(path, memo)
    return {**result, 'interpretation': token}
