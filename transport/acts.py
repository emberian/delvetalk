"""Call and pin framing shared by record requests and XRPC procedures.

Admission and plan atomicity belong to the host. This judges only the wire
shape and builds the host's one plan spell.
"""
PLAN_CALLS, SPELL_BYTES, INTENT_BYTES, PIN_COUNT, NAME_BYTES = 8, 4096, 256, 16, 128


def text(value, maximum):
    """A Unicode string within its UTF-8 byte budget."""
    try:
        return isinstance(value, str) and bool(value.strip()) and len(value.encode('utf-8')) <= maximum
    except UnicodeEncodeError:
        return False


def judge_call(mode, calls, pins):
    """-> (why, call): one spell/object call, or one `delvetalk plan` of 1..8 spells.

    The untagged call has exactly one form: spell, or object + verb + optional
    fields. Pins are the host's commit-if-unchanged input, passed without edits.
    """
    if not isinstance(pins, list) or len(pins) > PIN_COUNT or any(
            not isinstance(p, dict) or not text(p.get('object'), NAME_BYTES) or type(p.get('version')) is not int or
            p['version'] < 0 or set(p) - {'object', 'version', 'cid'} or ('cid' in p and not text(p['cid'], 256)) for p in pins):
        return 'if is a list of {object, version}', None
    plan = mode == 'plan'
    if not isinstance(calls, list) or not calls or len(calls) > (PLAN_CALLS if plan else 1) or not all(isinstance(c, dict) for c in calls):
        return f'a plan has 1 to {PLAN_CALLS} calls' if plan else 'an act has exactly one call', None
    if plan and not all(set(c) == {'spell'} and isinstance(c['spell'], str) for c in calls):
        return 'a plan is spells only', None
    for c in calls:
        if set(c) == {'spell'}:
            if not text(c['spell'], SPELL_BYTES):
                return f'a spell is nonempty Unicode text of at most {SPELL_BYTES} UTF-8 bytes', None
        elif ('spell' in c or not {'object', 'verb'} <= set(c) or set(c) - {'object', 'verb', 'fields'} or
              not text(c.get('object'), NAME_BYTES) or not text(c.get('verb'), NAME_BYTES)):
            return 'a call is a spell, or an object with a verb (and fields), not both', None
        elif 'fields' in c and not isinstance(c['fields'], dict):
            return 'fields must be a JSON object', None
    return None, {'spell': 'delvetalk plan\n' + '\n'.join(c['spell'].strip('\n') for c in calls)} if plan else calls[0]
