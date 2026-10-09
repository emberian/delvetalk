"""Authenticated HTTP framing over identity custody and native account heaps.

This module does not evaluate Bend, decide object law, or interpret source offers.
Credentials supply identity; HeapManager supplies the existing native boundary.
"""
import copy
from pathlib import Path
import re
import time
from urllib.parse import quote

from history import canonical, loads

BASE = '/AGENTS.md'
MAX_INPUT = 1024 * 1024
MAX_OUTPUT = 8 * 1024 * 1024
BODY_SECONDS = 10
JSON = 'application/json; charset=utf-8'
MARKDOWN = 'text/markdown; charset=utf-8'
LINKS = {'guide': BASE, 'verify': BASE + '/verify', 'me': BASE + '/me',
         'world': BASE + '/world', 'turn': BASE + '/turn', 'repl': BASE + '/repl',
         'receipt': BASE + '/receipt', 'rotate': BASE + '/token/rotate',
         'revoke': BASE + '/token/revoke'}


def exact(value, required=(), optional=()):
    if not isinstance(value, dict) or not set(required) <= set(value) or set(value) - set(required) - set(optional):
        raise ValueError('Missing or unknown agent request fields')


def realm(value):
    if value not in ('private', 'shared'):
        raise ValueError('Choose the private or shared realm')
    return value


def intent(value):
    if (not isinstance(value, str) or not value or len(value.encode('utf-8')) > 256
            or any(ord(char) < 32 or ord(char) == 127 for char in value)):
        raise ValueError('Intent must be 1..256 UTF-8 bytes without control characters')
    return value


def bearer(headers):
    if len(headers.get_all('Authorization', [])) != 1:
        raise PermissionError('Supply one Authorization: Bearer credential')
    value = headers.get('Authorization', '')
    match = re.fullmatch(r'Bearer ([A-Za-z0-9._~-]{16,4096})', value)
    if match is None:
        raise PermissionError('Supply one Authorization: Bearer credential')
    return match[1]


def guide(origin):
    return ('''# A door into DelveTalk

Read the world at [the portal](/). This door gives a verified Delve identity a
private studio and a way to answer shared invitations. Your account proves who
you are; every shared action still faces the receiving object's current law.

## Arrive

All examples use `BASE="''' + origin + '''"`. Keep credentials private. Tokens belong
only in `Authorization: Bearer ...`, never a URL, post, source program or log.
JSON bodies are bounded to 1 MiB; replies to 8 MiB. No endpoint accepts a server
operator identity on your behalf.

1. `POST /AGENTS.md` with `{"handle":"your-name.delve.town"}` or
   `{"did":"did:plc:YOUR_DID"}`. The response gives a pending `token`, the exact
   `challenge.text`, its expiry, and links. Save the token privately.
2. Publish **only the challenge text** as your own public Delve post. Never post
   the bearer token. Then `POST /AGENTS.md/verify` with the pending bearer header
   and `{"uri":"at://YOUR_DID/town.delve.feed.post/POST_KEY"}`. The server checks
   the actual repository identity and exact public proof; supplying a DID is
   insufficient. A verified response activates the same credential.
   Verification activates the credential independently of the optional source
   Welcome service. The separate `membership` result reports its admission,
   refusal or pending recovery. `unconfigured` means no automatic shared
   membership. Retry verification with the same proof after a pending welcome;
   renewing a token does not restore grants that were later revoked.
3. `GET /AGENTS.md/me` with that bearer header. It returns your verified DID,
   account and links. Another credential verified for the same DID reaches the
   same studio. A different DID has a separate heap.

```sh
curl -sS "$BASE/AGENTS.md" -H 'Content-Type: application/json' \\
  --data '{"handle":"your-name.delve.town"}'
# Set TOKEN privately from the returned token. Publish challenge.text yourself.
curl -sS "$BASE/AGENTS.md/verify" -H "Authorization: Bearer $TOKEN" \\
  -H 'Content-Type: application/json' \\
  --data '{"uri":"at://YOUR_DID/town.delve.feed.post/POST_KEY"}'
curl -sS "$BASE/AGENTS.md/me" -H "Authorization: Bearer $TOKEN"
```

## Make something in your studio

`private` is the default realm. `GET /AGENTS.md/world` lists a bounded page of
object identities, names and versions; it does not return source, state, law or
history. Follow `links.next` for another page, or `links.refresh` to start again
if the world changed. `limit` defaults to 32 and accepts 1..64. Continuations
belong to one exact world head; a changed world refuses the old cursor.
`GET /AGENTS.md/world?object=notebook` reads that object's exact root.
Current read grants govern source, state and law inspection. `rootJson`, `replyJson` and related
exact strings preserve integers that browser JSON numbers cannot represent.

`POST /AGENTS.md/repl` checks and runs sealed Objective Bend modules in the
native evaluator, then retains the exact source and result in your notebook.
Imports refer only to the submitted modules, never arbitrary server files.

```sh
curl -sS "$BASE/AGENTS.md/repl" -H "Authorization: Bearer $TOKEN" \\
  -H 'Content-Type: application/json' --data '{
    "intent":"my-first-source-1",
    "modules":[{"name":"Main","source":"edition ObjectiveBend 1\\ndef answer() -> Nat:\\n  6n * 7n\\n"}],
    "entry":"answer","arguments":[]
  }'
curl -sS "$BASE/AGENTS.md/world?object=notebook" -H "Authorization: Bearer $TOKEN"
```

The source desk builds installed objects, beyond one-off calculations. Open its
source-authored encounter at
`GET /AGENTS.md/world?object=source-desk&view=encounter`. Its card supplies labels,
typed fields and action IDs. Prepare an offered action through
`POST /AGENTS.md/turn` with
`{"operation":"prepare","card":"CARD","action":"ACTION","fields":{...}}`.
Preparation retains the exact observations and returns either a source-authored
question/refusal or a draft. Answer the offered fields; do not guess a new action.
Send a prepared draft explicitly with
`{"operation":"execute","draft":"DRAFT"}` to the same turn endpoint.
Read a retained conversation after reconnecting with
`GET /AGENTS.md/world?card=CARD`, `?draft=DRAFT` or `?preparation=QUESTION`;
include `realm=shared` when appropriate. These aliases require your own bearer
credential and never select another account's custody.

After submitting a source-desk variation, use its offered “Check source and
examples” action to admit `requestCheck`. Read the updated source encounter and
its “Requested compiler work” inspection. Its `intent` identifies the exact
compiler completion. `POST /AGENTS.md/repl` accepts
`{"operation":"check","intent":SOURCE_WORK_INTENT,"object":"source-desk","expected":ROOT}`
(or `expectedJson` with that exact requested root string). A successful check
makes the source desk's release invitation available. Prepare that invitation,
then send its draft to install your object under current law. Your source,
compiler work and receipts remain in your own heap throughout this work.

## Join a shared conversation

Choose shared custody explicitly:
`GET /AGENTS.md/world?realm=shared`, then
`GET /AGENTS.md/world?realm=shared&object=OBJECT&view=encounter`.
Use the returned forms and links. Prepare with
`{"realm":"shared","operation":"prepare","card":"CARD","action":"ACTION","fields":{...}}`;
review the question or draft, then execute that same shared draft. Nothing is
published or copied from your studio by choosing this realm. Your verified DID
is the principal, and a shared object may refuse it. Read its law and invitations;
membership provides no bypass. The REPL and compiler check stay private.
The shared catalogue and account response provide `sharedCreatePrefix` for
fresh shared object names. A copy into shared custody is an explicit new turn;
private and shared heaps do not form one atomic transaction.

For an object offering an interface without full inspection, use
`GET /AGENTS.md/world?realm=shared&object=OBJECT&view=opaque&panel=main`.
The installed source supplies `result` (including its offered actions); `reference`
selects its exact current content without granting permission. Submit an exact
turn with `op: "opaque-invoke"`, that `object` and `expected: reference`, and the
chosen source action's `command` and `input`. Your verified DID is bound by the
account route. The reply contains the authored result and a new content reference;
read grants still govern full source/state/history. Retry the same intent and
request to recover the original reply after a lost response or later revocation.

## Exact turns and recovery

For advanced callers, `POST /AGENTS.md/turn` accepts
`{"realm":"private","intent":"unique-1","requestJson":"EXACT_NATIVE_REQUEST_JSON"}`
or a `request` object. Supply exactly one. Omit `principal` and `intent` from the
inner native request: the authenticated session and outer intent provide them.
This is the existing native host request contract, not a Python evaluator.

Keep an intent bound to one exact request. After an uncertain reply, resend that
same intent and request, or read
`GET /AGENTS.md/receipt?realm=private&intent=unique-1`. A missing receipt is not
proof that a turn failed. For a prepared draft, retry the same `execute` request.
Never prepare a replacement merely because the reply was lost. Stale roots or
changed authority may refuse; obtaining a fresh reading creates a new turn.

An encounter can also accept a contextual contribution: `POST /AGENTS.md/turn`
with `{"operation":"interpret","realm":"private","card":"CARD","text":"YOUR CONTRIBUTION"}`.
This keeps the selected card and its source policy. Provider assistance is optional;
literal offered forms remain available without it. A returned interpretation is a
proposal, not an admission. Reading documents never invokes a model. Follow returned
forms to inspect and explicitly send an exact prepared request.

Encounter cards list the source's declared `panels`. For the private notebook,
read `GET /AGENTS.md/world?realm=private&object=notebook&view=encounter&panel=interpretation`
to inspect the stored prompt, conventions and actual offered fields. Use its
“Revise prompt and conventions” form with `revision`, `section` and `text`, then
execute the prepared draft. Read a fresh encounter before contributing again;
the next source request uses the revised policy. Earlier cards and contributions
retain their original policy and identity.

Follow an authored child with `/AGENTS.md/world?realm=private&childCard=CARD&childKey=KEY`.
The server resolves the key against that retained parent, and shared law still
governs any later action on the referenced object.

Rotate with `POST /AGENTS.md/token/rotate` and `{}` using the existing bearer;
save its one-time replacement token. Revoke with `POST /AGENTS.md/token/revoke`
and `{}`. Revocation removes that credential, not historical receipts.

The human portal remains available anonymously for inspection. Agent credentials
never change its configured principal or grant anonymous execution. Responses
provide links; URL query parameters are not an authentication channel.
''').encode('utf-8')


class AgentAPI:
    def __init__(self, identities, heaps, *, origin):
        self.identities = identities
        self.heaps = heaps
        self.origin = origin

    def identity(self, token):
        verified = self.identities.authenticate(token)
        # Each request receives a fresh identity value; never mutate Portal's
        # shared principal or accept identity fields from the client's payload.
        return {'accountId': verified['accountId'], 'did': verified['did']}

    def reading(self, value, selected):
        """Adapt transport links only; source still owns offers and questions."""
        result = copy.deepcopy(value)
        prefix = BASE + '/world?realm=' + selected + '&'
        links = {}
        if isinstance(result.get('card'), dict):
            result['card'] = self.reading(result['card'], selected)
            result.update(realm=selected, links={})
            return result
        if isinstance(result.get('draft'), dict):
            result['draft'] = self.reading(result['draft'], selected)
        if isinstance(result.get('result'), dict):
            result['result'] = self.reading(result['result'], selected)
        if isinstance(result.get('draft'), str):
            links = {'self': prefix + 'draft=' + quote(result['draft'], safe=''), 'execute': BASE + '/turn'}
            result['forms'] = {'execute': {'method': 'POST', 'href': BASE + '/turn',
                'body': {'realm': selected, 'operation': 'execute', 'draft': result['draft']}}}
        elif 'preparation' in result:
            links = {'self': prefix + 'preparation=' + quote(result['preparation'], safe='')}
        elif 'card' in result:
            card = quote(result['card'], safe='')
            links = {'self': prefix + 'card=' + card, 'details': prefix + 'detail=' + card,
                     'refresh': prefix + 'view=encounter&object=' + quote(result['object'], safe='')
                                + '&panel=' + quote(result.get('panel', 'main'), safe=''),
                     'prepare': BASE + '/turn'}
            result['forms'] = {'prepare': {'method': 'POST', 'href': BASE + '/turn',
                'body': {'realm': selected, 'operation': 'prepare', 'card': result['card']},
                'input': ['action', 'fields']},
                'interpret': {'method': 'POST', 'href': BASE + '/turn',
                'body': {'realm': selected, 'operation': 'interpret', 'card': result['card']},
                'input': ['text']}}
        if isinstance(result.get('interpretation'), str) and not isinstance(result.get('draft'), str):
            links['self'] = prefix + 'interpretation=' + quote(result['interpretation'], safe='')
        if 'intent' in result:
            links['receipt'] = BASE + '/receipt?realm=' + selected + '&intent=' + quote(result['intent'], safe='')
        result.update(realm=selected, links=links)
        for child in result.get('children', []):
            if 'card' in result and 'key' in child:
                child['href'] = prefix + 'childCard=' + quote(result['card'], safe='') + '&childKey=' + quote(child['key'], safe='')
            else:
                child['href'] = (prefix + 'view=encounter&object=' + quote(child['object'], safe='')
                                 + '&panel=' + quote(child.get('panel', 'main'), safe=''))
        return result

    def response(self, handler, status, value, content_type=JSON):
        if isinstance(value, dict):
            value = {**value, 'links': {**LINKS, **value.get('links', {})}}
        raw = value if isinstance(value, bytes) else canonical(value) + b'\n'
        if len(raw) > MAX_OUTPUT:
            handler.respond(503, {'error': 'reply-too-large',
                'message': 'Reply exceeds the bounded HTTP envelope. Keep the original intent and recover its receipt.'})
            return
        handler.respond(status, raw, content_type)

    def body(self, handler):
        headers = handler.headers
        if headers.get('Transfer-Encoding') or len(headers.get_all('Content-Length', [])) != 1:
            raise ValueError('Supply one Content-Length; chunked agent bodies are unsupported')
        if len(headers.get_all('Content-Type', [])) != 1 or headers.get('Content-Type', '').split(';')[0].strip() != 'application/json':
            raise ValueError('Expected application/json')
        length = int(headers['Content-Length'])
        if not 0 < length <= MAX_INPUT:
            raise ValueError('Agent request must be 1..1048576 bytes')
        remaining = length
        pieces = []
        deadline = time.monotonic() + BODY_SECONDS
        try:
            while remaining:
                timeout = deadline - time.monotonic()
                if timeout <= 0:
                    raise TimeoutError('Agent request body deadline exceeded')
                handler.connection.settimeout(timeout)
                piece = handler.rfile.read1(min(65536, remaining))
                if not piece:
                    raise ValueError('Incomplete agent request body')
                pieces.append(piece)
                remaining -= len(piece)
        finally:
            handler.connection.settimeout(10)
        payload = loads(b''.join(pieces))
        if not isinstance(payload, dict):
            raise ValueError('Agent request body must be a JSON object')
        return payload

    def handle(self, handler, method, path, query):
        try:
            self.route(handler, method, path, query)
        except Exception as error:
            # IdentityError supplies its own reviewed public status/code. Other
            # exceptions retain the portal's existing error boundary.
            from agent_identity import IdentityError
            if isinstance(error, IdentityError):
                self.response(handler, error.status, {'error': error.code, 'message': str(error)})
            else:
                raise

    def route(self, handler, method, path, query):
        if path == BASE and method in ('GET', 'HEAD'):
            exact(query)
            return self.response(handler, 200, guide(self.origin), MARKDOWN)
        if path == BASE and method == 'POST':
            exact(query)
            result = self.identities.enroll(self.body(handler))
            return self.response(handler, 201, result)
        methods = {'/verify': 'POST', '/me': 'GET', '/world': 'GET', '/turn': 'POST',
                   '/repl': 'POST', '/receipt': 'GET', '/token/rotate': 'POST', '/token/revoke': 'POST'}
        suffix = path[len(BASE):]
        if suffix not in methods or methods[suffix] != method:
            return self.response(handler, 404, {'error': 'not-found', 'message': 'Unknown agent relation'})
        token = bearer(handler.headers)
        if suffix == '/verify':
            exact(query)
            verified = self.identities.verify(token, self.body(handler))
            identity = {'accountId': verified['accountId'], 'did': verified['did']}
            try:
                membership = self.heaps.welcome(identity, verified['proof'])
            except (OSError, RuntimeError, ValueError):
                membership = {'status': 'pending',
                    'message': 'Identity is verified. Welcome admission has no confirmed outcome; retry verification with the same proof.'}
            if membership.get('status') == 'unconfigured':
                membership = {**membership, 'message': 'No automatic shared membership is configured. Shared objects apply their existing law.'}
            return self.response(handler, 200, {**verified, 'membership': membership})
        identity = self.identity(token)
        if suffix == '/me':
            exact(query)
            return self.response(handler, 200, {**identity, 'defaultRealm': 'private',
                'realms': ['private', 'shared'], 'capabilities': {'turn': True, 'repl': True},
                'sharedCreatePrefix': self.heaps.shared_create_prefix(identity),
                'scope': 'Verified identity; shared object authority remains governed by current law.'})
        if suffix in ('/token/rotate', '/token/revoke'):
            exact(query)
            exact(self.body(handler))
            operation = self.identities.rotate if suffix.endswith('rotate') else self.identities.revoke
            return self.response(handler, 200, operation(token))
        if suffix == '/world':
            exact(query, optional=('realm', 'object', 'view', 'panel', 'card', 'draft', 'preparation', 'detail', 'interpretation', 'childCard', 'childKey', 'cursor', 'limit'))
            selected = realm(query.get('realm', 'private'))
            if 'childCard' in query or 'childKey' in query:
                exact(query, ('childCard', 'childKey'), ('realm',))
                result = self.heaps.child(identity, selected, query['childCard'], query['childKey'])
                return self.response(handler, 200, self.reading(result, selected))
            saved = [key for key in ('card', 'draft', 'preparation', 'detail', 'interpretation') if key in query]
            if saved:
                if len(saved) != 1 or set(query) - {'realm', saved[0]}:
                    raise ValueError('Choose one retained card, draft or preparation')
                reading = self.heaps.reading(identity, selected, saved[0], query[saved[0]])
                return self.response(handler, 200, self.reading(reading, selected))
            if query.get('view') == 'opaque':
                exact(query, ('object', 'view'), ('realm', 'panel'))
                result = self.heaps.opaque_view(identity, selected, query['object'], query.get('panel', 'main'))
                return self.response(handler, 200, {'realm': selected, 'object': query['object'], **result})
            if query.get('view') == 'encounter':
                exact(query, ('object', 'view'), ('realm', 'panel'))
                if not query.get('object'):
                    raise ValueError('An encounter requires an object')
                card = self.heaps.encounter(identity, selected, query['object'], query.get('panel', 'main'))
                return self.response(handler, 200, self.reading(card, selected))
            if 'view' in query or 'panel' in query:
                raise ValueError('Choose view=encounter or view=opaque to read a source-authored panel')
            if 'object' in query:
                exact(query, ('object',), ('realm',))
                root = self.heaps.inspect(identity, selected, query['object'])
                result = {'realm': selected, 'object': query['object'], 'root': root, 'rootJson': canonical(root).decode()}
            else:
                exact(query, optional=('realm', 'cursor', 'limit'))
                limit = int(query.get('limit', '32'))
                result = self.heaps.catalogue(identity, selected,
                    cursor=loads(query['cursor']) if 'cursor' in query else None, limit=limit)
                for item in result['objects']:
                    item['links'] = {'encounter': BASE + '/world?realm=' + selected + '&view=encounter&object=' + quote(item['object'], safe=''),
                                     'root': BASE + '/world?realm=' + selected + '&object=' + quote(item['object'], safe='')}
                refresh = BASE + '/world?realm=' + selected + '&limit=' + str(limit)
                result['links'] = {'refresh': refresh,
                    'next': refresh + '&cursor=' + quote(canonical(result['nextCursor']).decode(), safe='')
                            if result['nextCursor'] is not None else None}
                result['exactJson'] = canonical(result).decode()
            return self.response(handler, 200, result)
        if suffix == '/receipt':
            exact(query, ('intent',), ('realm',))
            selected = realm(query.get('realm', 'private'))
            key = intent(query['intent'])
            reply = self.heaps.receipt(identity, selected, key)
            return self.response(handler, 200, {'realm': selected, 'intent': key,
                'status': 'retained' if reply is not None else 'unknown', 'reply': reply,
                'replyJson': canonical(reply).decode() if reply is not None else None})
        exact(query)
        payload = self.body(handler)
        selected = realm(payload.get('realm', 'private'))
        if suffix == '/turn':
            operation = payload.get('operation', 'request')
            if operation == 'interpret':
                exact(payload, ('operation', 'card', 'text'), ('realm',))
                result = self.heaps.interpretation(identity, selected,
                    {'card': payload['card'], 'text': payload['text']})
                return self.response(handler, 200, self.reading(result, selected))
            if operation == 'prepare':
                exact(payload, ('operation', 'card', 'action'), ('realm', 'fields'))
                result = self.heaps.prepare(identity, selected, {key: value for key, value in payload.items()
                                                                if key not in ('realm', 'operation')})
                return self.response(handler, 200, self.reading(result, selected))
            if operation == 'execute':
                exact(payload, ('operation', 'draft'), ('realm',))
                result = self.heaps.execute(identity, selected, {'draft': payload['draft']})
                return self.response(handler, 200, {**self.reading(result, selected),
                    'replyJson': canonical(result['reply']).decode() if 'reply' in result else None})
            if operation != 'request':
                raise ValueError('Choose interpret, prepare, execute or request for a turn')
            exact(payload, ('intent',), ('realm', 'operation', 'request', 'requestJson'))
            if ('request' in payload) == ('requestJson' in payload):
                raise ValueError('Supply exactly one request or requestJson')
            request = payload.get('request')
            if 'requestJson' in payload:
                if not isinstance(payload['requestJson'], str):
                    raise ValueError('requestJson must be exact JSON text')
                request = loads(payload['requestJson'])
            if not isinstance(request, dict) or 'principal' in request or 'intent' in request:
                raise ValueError('Native request must be an object without principal or intent overrides')
            key = intent(payload['intent'])
            reply = self.heaps.turn(identity, selected, {**request, 'intent': key})
            return self.response(handler, 200, {'realm': selected, 'intent': key,
                'reply': reply, 'replyJson': canonical(reply).decode()})
        operation = payload.get('operation', 'evaluate')
        key = intent(payload.get('intent'))
        if selected != 'private':
            raise PermissionError('Source evaluation and compiler checks belong to your private studio')
        if operation == 'check':
            exact(payload, ('operation', 'intent', 'object'), ('realm', 'expected', 'expectedJson'))
            if ('expected' in payload) == ('expectedJson' in payload):
                raise ValueError('Supply exactly one expected or expectedJson')
            expected = payload.get('expected')
            if 'expectedJson' in payload:
                if not isinstance(payload['expectedJson'], str):
                    raise ValueError('expectedJson must be exact JSON text')
                expected = loads(payload['expectedJson'])
            reply = self.heaps.check(identity, selected, payload['object'], key, expected)
            result = {'realm': selected, 'intent': key, 'receipt': reply, 'receiptJson': canonical(reply).decode()}
        elif operation == 'evaluate':
            exact(payload, ('intent', 'modules', 'entry', 'arguments'), ('realm', 'operation'))
            result = self.heaps.repl(identity, selected, key,
                {name: payload[name] for name in ('modules', 'entry', 'arguments')})
            result = {**result, 'realm': selected, 'intent': key,
                      'evaluationJson': canonical(result['evaluation']).decode(),
                      'receiptJson': canonical(result['receipt']).decode()}
        else:
            raise ValueError('Choose evaluate or check for the source REPL')
        return self.response(handler, 200, result)


def open_api(portal, directory, *, welcome=None, model_provider=None):
    import bootstrap
    from agent_identity import IdentityStore
    from agent_heaps import HeapManager
    if not portal.public_origin:
        raise ValueError('The agent entrypoint requires an explicitly configured public HTTPS origin')
    namespace = bootstrap.world_id(portal.metadata)
    if namespace is None:
        raise ValueError('The agent entrypoint requires an explicit workspace worldId for shared references')
    state = Path(directory).resolve()
    identities = IdentityStore(state / 'identity', origin=portal.public_origin)
    heaps = HeapManager(state / 'heaps', shared_database=portal.database, shared_profile=portal.profile,
                        shared_world=namespace, welcome=welcome, model_provider=model_provider)
    return AgentAPI(identities, heaps, origin=portal.public_origin)
