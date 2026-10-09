"""Explicit local operator attestations; neither language inference nor authority."""
import copy

FORMAT = 'delvetalk-manual-interpretation-v1'


def validate(decision):
    if not isinstance(decision, dict):
        raise ValueError('interpretation must be an object')
    status = decision.get('status')
    fields = {'status', 'interpreter', 'basis', 'request' if status == 'act' else 'message'}
    if status not in ('act', 'clarify', 'escalate') or set(decision) != fields:
        raise ValueError('interpretation requires act/request or clarify|escalate/message and interpreter/basis')
    for name, maximum in [('interpreter', 256), ('basis', 2048)]:
        value = decision[name]
        if not isinstance(value, str) or not value.strip() or len(value.encode('utf-8')) > maximum:
            raise ValueError('invalid interpretation ' + name)
    if status == 'act':
        if not isinstance(decision['request'], dict):
            raise ValueError('interpreted request must be an exact wire object')
    elif (not isinstance(decision['message'], str) or not decision['message'].strip()
          or len(decision['message'].encode('utf-8')) > 2048):
        raise ValueError('clarification/escalation requires a bounded message')
    return copy.deepcopy(decision)


def attestation(decision, source, record_sha256):
    return {'format': FORMAT, 'decision': validate(decision), 'source': copy.deepcopy(source),
            'sourceRecordSha256': record_sha256,
            'scope': 'Local operator attestation of intended meaning; interpreter label is not an authenticated account. '
                     'The original post does not itself encode or cryptographically authorize this derived request.'}
