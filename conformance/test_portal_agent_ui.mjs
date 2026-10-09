// Run the actual browser script against a DOM/HTTP boundary; no token or source
// is sent to a network, and no world admission is simulated in the browser.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

class Node {
  constructor(tag) { Object.assign(this, { tag, children: [], dataset: {}, attributes: {}, listeners: {}, value: '', checked: false, hidden: false, classList: { toggle() {}, add() {} } }); }
  set textContent(value) { this.content = String(value); this.children = []; }
  get textContent() { return (this.content || '') + this.children.map(node => node.textContent).join(''); }
  set innerHTML(_) { throw new Error('Untrusted data entered HTML'); }
  append(...nodes) { for (const node of nodes) { if (node.parentNode) node.parentNode.removeChild(node); node.parentNode = this; this.children.push(node); } }
  removeChild(node) { this.children = this.children.filter(child => child !== node); node.parentNode = null; }
  replaceChildren(...nodes) { for (const child of this.children) child.parentNode = null; this.children = []; this.append(...nodes); }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  focus() {} scrollIntoView() {}
  get childElementCount() { return this.children.length; }
  get options() { return this.children; }
  setCustomValidity(message) { this.validityMessage = message; }
  reportValidity() { return !this.validityMessage; }
}
const ids = new Map();
const document = {
  createElement: tag => new Node(tag),
  querySelector: selector => document.getElementById(selector),
  getElementById: id => { if (!ids.has(id)) ids.set(id, new Node('div')); return ids.get(id); },
};
document.documentElement = document.querySelector(':root');
const themeStorage = new Map([['delvetalk.theme', 'dark']]);
const requests = [], copied = [], navigation = [];
const location = { href: 'https://delvetalk.invalid/' };
let responder = () => new Promise(() => {}), uuid = 0;
const context = vm.createContext({
  document, location, URL, TextEncoder, TextDecoder,
  localStorage: { getItem: key => themeStorage.get(key), setItem: (key, value) => themeStorage.set(key, value), removeItem: key => themeStorage.delete(key) },
  history: { replaceState(_, __, url) { navigation.push(String(url)); }, pushState(_, __, url) { navigation.push(String(url)); } },
  window: { addEventListener() {} }, matchMedia: () => ({ matches: true }),
  navigator: { clipboard: { async writeText(value) { copied.push(value); } } },
  setTimeout() {}, crypto: { randomUUID: () => `intent-${++uuid}` },
  fetch: async (url, options) => { requests.push({ url, options }); return responder(url, options); },
});
vm.runInContext(readFileSync(new URL('../portal/static/theme.js', import.meta.url), 'utf8'), context);
vm.runInContext(readFileSync(new URL('../portal/static/app.js', import.meta.url), 'utf8'), context);
const node = id => document.getElementById(id);
const evaluate = source => vm.runInContext(source, context);
const response = data => ({ ok: true, status: 200, text: async () => JSON.stringify(data), json: async () => data });
// Saved display preference is applied by the CSP-compatible prepaint script;
// the live control only persists this preference, never identity or source.
assert.equal(document.documentElement.dataset.theme, 'dark');
assert.equal(node('theme-preference').value, 'dark');
node('theme-preference').value = 'system';
node('theme-preference').listeners.change();
assert.equal(themeStorage.has('delvetalk.theme'), false);
assert.equal(document.documentElement.dataset.theme, 'system');
node('theme-preference').value = 'light';
node('theme-preference').listeners.change();
assert.equal(themeStorage.get('delvetalk.theme'), 'light');
const availableStorage = context.localStorage;
context.localStorage = { setItem() { throw new Error('Storage disabled'); } };
node('theme-preference').value = 'dark';
node('theme-preference').listeners.change();
assert.equal(document.documentElement.dataset.theme, 'dark', 'Unavailable storage does not disable the in-page choice');
context.localStorage = availableStorage;
const isolatedRoot = { dataset: {} };
vm.runInNewContext(readFileSync(new URL('../portal/static/theme.js', import.meta.url), 'utf8'), {
  document: { documentElement: isolatedRoot }, localStorage: { getItem: () => 'invalid-theme' },
});
assert.equal(isolatedRoot.dataset.theme, undefined, 'Unknown saved preferences use the system palette');
const identity = { accountId: 'account-one', did: 'did:plc:alice', defaultRealm: 'private', realms: ['private', 'shared'], capabilities: { turn: true, repl: true } };
const exactRoot = '{"state":{"count":9007199254740993123456789},"version":0}';
let outcome = 'unknown';
responder = async url => {
  if (url === '/AGENTS.md/me') return response(identity);
  if (url.includes('/world?')) return response((url.includes('&object=') || url.includes('&detail='))
    ? { root: {}, rootJson: exactRoot } : { objects: [{ object: 'notebook', root: {} }] });
  if (url.startsWith('/AGENTS.md/receipt')) return response(outcome === 'unknown'
    ? { status: 'unknown', reply: null, replyJson: null }
    : { status: 'retained', reply: { kind: 'committed' }, replyJson: '{"kind":"committed"}' });
  if (url === '/AGENTS.md/turn') throw new Error('Connection lost');
  return new Promise(() => {});
};
await context.connectAgent('secret-token');
assert.equal(node('agent-connected').hidden, false);
assert.equal(node('agent-realm').value, 'private');
assert.match(node('agent-capabilities').textContent, /turn, repl/);
assert.equal(node('agent-token').value, '');
assert.equal(node('objects').hidden, true, 'The connected realm owns the main shelf');
assert.equal(node('world-title').textContent, 'Private studio');
assert.equal(node('agent-realm-controls').parentNode, node('agent-sidebar-controls'));
node('browse-public').listeners.click();
assert.equal(node('agent-session').hidden, true, 'Anonymous preview is a separate focus');
assert.equal(node('objects').hidden, false);
assert.equal(evaluate('agentSession.token'), 'secret-token', 'Focus changes do not discard credentials');
node('resume-studio').listeners.click();
assert.equal(node('agent-session').hidden, false);
assert.equal(node('world-title').textContent, 'Private studio');

for (const request of requests.filter(request => request.url.startsWith('/AGENTS.md'))) {
  assert.equal(request.options.headers.Authorization, 'Bearer secret-token');
  assert.equal(request.options.credentials, 'omit');
  assert.equal(request.options.redirect, 'error');
  assert.ok(!request.url.includes('secret-token'));
}
await node('agent-objects').children[0].listeners.click();
assert.equal(node('agent-root-json').textContent, exactRoot);
const requestJson = `{"op":"invoke","object":"notebook","expected":${exactRoot},"command":"read","input":{}}`;
context.newAgentProposal('turn', requestJson);
assert.ok(node('agent-proposal-json').textContent.includes('9007199254740993123456789'));
assert.ok(!node('agent-proposal-json').textContent.includes('secret-token'));
await context.sendAgentProposal();
assert.equal(evaluate('agentSession.uncertain'), true);
assert.throws(() => context.newAgentProposal('turn', '{}'), /pending receipt/);
const sent = requests.find(request => request.url === '/AGENTS.md/turn');
assert.equal(JSON.parse(sent.options.body).requestJson, requestJson);
assert.equal(JSON.parse(sent.options.body).intent, 'browser:intent-1');
await context.sendAgentProposal(true);
assert.equal(evaluate('agentSession.uncertain'), true);
outcome = 'committed';
await context.sendAgentProposal(true);
assert.equal(evaluate('agentSession.uncertain'), false);
assert.equal(node('agent-send').disabled, true);
const recovery = node('agent-proposal-json').textContent;
context.disconnectAgent();
assert.equal(evaluate('agentSession.token'), '');
assert.equal(node('agent-connected').hidden, true);
await assert.rejects(() => context.agentApi('https://evil.invalid/AGENTS.md'), /Unknown agent API route/);
await context.connectAgent('second-token');
context.restoreAgentProposal(recovery);
assert.equal(evaluate('agentSession.proposal.intent'), 'browser:intent-1');
assert.equal(evaluate('agentSession.proposal.requestJson'), requestJson);
assert.throws(() => context.restoreAgentProposal(recovery), /pending receipt/);
await context.sendAgentProposal(true);
assert.throws(() => context.restoreAgentProposal(JSON.stringify({ ...JSON.parse(recovery), did: 'did:plc:mallory' })), /identity named/);
node('agent-realm').value = 'shared';
await context.readAgentWorld();
assert.equal(node('agent-repl-form').hidden, true);
assert.throws(() => context.newAgentProposal('repl', 'source'), /private studio/);

// Enrollment keeps the opaque credential separate from the exact public text.
context.disconnectAgent();
const challenge = 'delvetalk challenge <literal> & nonce';
responder = async (url, options) => {
  if (url === '/AGENTS.md') {
    assert.equal(options.headers.Authorization, undefined);
    assert.deepEqual(JSON.parse(options.body), { handle: 'alice.delve.town' });
    return response({ status: 'pending', token: 'pending-private-token', challenge: { text: challenge, did: identity.did, expiresAt: 'later', origin: 'https://delvetalk.invalid' } });
  }
  if (url === '/AGENTS.md/verify') {
    assert.equal(options.headers.Authorization, 'Bearer pending-private-token');
    assert.deepEqual(JSON.parse(options.body), { uri: 'at://did:plc:alice/town.delve.feed.post/proof' });
    return response({ status: 'verified', did: identity.did, accountId: identity.accountId });
  }
  if (url === '/AGENTS.md/me') return response(identity);
  return response({ objects: [] });
};
node('agent-handle').value = 'alice.delve.town';
await context.enrollAgent();
assert.equal(node('agent-challenge-text').textContent, challenge);
assert.equal(node('agent-issued-token').value, 'pending-private-token');
await node('copy-agent-challenge').listeners.click();
assert.equal(copied.at(-1), challenge);
assert.ok(!copied.at(-1).includes('pending-private-token'));
node('agent-proof').value = 'https://example.invalid/a-post';
await assert.rejects(context.verifyAgent, /at:\/\//);
node('agent-proof').value = 'at://did:plc:alice/town.delve.feed.post/proof';
await context.verifyAgent();
assert.equal(node('agent-connected').hidden, false);
assert.equal(node('agent-challenge').hidden, true);
assert.equal(evaluate('agentSession.token'), 'pending-private-token');
assert.ok(navigation.every(url => !url.includes('token')));

// Real authored fields and a source question lead to an account-bound draft;
// preparation does not execute, and execute references the retained draft.
let preparationCalls = 0, executionCalls = 0;
const garden = { card: 'garden-card', object: 'garden', title: '<Garden>', prose: 'A remembered place.', actions: [{
  id: 'plant', label: 'Plant a memory', available: true, preparation: true,
  fields: [{ name: 'word', label: 'What do you remember?', type: 'string', minLength: 1, maxLength: 100 }],
}] };
responder = async (url, options) => {
  if (url.includes('view=encounter')) return response(garden);
  if (url.includes('/world?')) return response((url.includes('&object=') || url.includes('&detail=')) ? { rootJson: exactRoot } : { objects: [{ object: 'garden' }] });
  if (url === '/AGENTS.md/turn') {
    const body = JSON.parse(options.body);
    assert.equal(options.headers.Authorization, 'Bearer pending-private-token');
    if (body.operation === 'prepare') {
      preparationCalls++;
      assert.equal(body.realm, 'shared');
      assert.equal(body.card, 'garden-card');
      assert.equal(body.action, 'plant');
      assert.equal(body.principal, undefined);
      if (!body.fields.word) return response({ format: 'delvetalk-portal-preparation-v1', preparation: 'saved-question', card: garden.card, action: 'plant', fields: {},
        outcome: { kind: 'question', message: '<Tell me a memory>', needs: ['word'] } });
      assert.equal(body.fields.word, 'the orchard');
      return response({ draft: 'retained-garden-turn', intent: 'native-intent', summary: 'Plant the orchard', wireJson: exactRoot });
    }
    assert.deepEqual(body, { realm: 'shared', operation: 'execute', draft: 'retained-garden-turn' });
    executionCalls++;
    return response({ reply: { kind: 'committed' }, replyJson: '{"kind":"committed"}' });
  }
  throw new Error('Unexpected route ' + url);
};
node('agent-realm').value = 'shared';
await context.readAgentWorld();
assert.equal(node('agent-encounter-title').textContent, '<Garden>');
assert.equal(node('agent-encounter-actions').children[0].children[0].textContent, 'Plant a memory');
await context.prepareAgentAction({ ...garden, realm: 'shared' }, 'plant', {});
assert.equal(node('agent-question').textContent, '<Tell me a memory>');
assert.equal(node('agent-conversation').hidden, false);
assert.equal(executionCalls, 0);
await node('copy-agent-conversation').listeners.click();
const conversationUrl = new URL(copied.at(-1));
assert.equal(conversationUrl.searchParams.get('conversation'), 'saved-question');
assert.equal(conversationUrl.searchParams.get('agentRealm'), 'shared');
assert.ok(!conversationUrl.href.includes('pending-private-token'));
const answerForm = node('agent-answer').children[0];
answerForm.children[0].children[1].value = 'the orchard';
answerForm.listeners.submit({ preventDefault() {} });
await new Promise(resolve => setImmediate(resolve));
assert.equal(preparationCalls, 2);
assert.equal(executionCalls, 0);
assert.equal(node('agent-conversation').hidden, true);
assert.match(node('agent-proposal-summary').textContent, /Plant the orchard.*shared world.*prepared/);
assert.equal(evaluate('agentSession.proposal.intent'), 'native-intent');
await context.sendAgentProposal();
assert.equal(executionCalls, 1);
assert.match(node('agent-result').textContent, /committed/);
// Restore a source question through the authenticated saved-card routes.
location.href = conversationUrl.href;
responder = async url => {
  if (url.includes('&preparation=')) return response({ format: 'delvetalk-portal-preparation-v1', preparation: 'saved-question', card: garden.card, action: 'plant', fields: {}, outcome: { kind: 'question', message: 'Still your question', needs: ['word'] } });
  if (url.includes('&card=') || url.includes('view=encounter')) return response(garden);
  if ((url.includes('&object=') || url.includes('&detail='))) return response({ rootJson: exactRoot });
  return response({ objects: [{ object: 'garden' }] });
};
await context.restoreAgentConversation();
assert.equal(node('agent-question').textContent, 'Still your question');
assert.equal(node('agent-realm').value, 'shared');

// The living document only attaches behavior to qualified bindings supplied by
// the captured card. Prose, labels and Capture metadata cannot synthesize it.
const docTarget = new Node('div'), remainingForms = new Node('div');
const realForm = new Node('form');
realForm.dataset.actionId = 'write';
const sourceField = context.fieldInput({ name: 'source', label: 'Note', type: 'string', required: true, minLength: 0, maxLength: 100 }, 'doc', 0);
const natField = context.fieldInput({ name: 'n', type: 'nat', required: true, minimum: 0, maximum: 20 }, 'doc', 1);
realForm.documentControls = [sourceField, natField];
realForm.append(sourceField.label, natField.label);
remainingForms.append(realForm);
const targets = [];
const malicious = '<script>steal(token)</script>';
const living = { actions: [{ id: 'write', label: 'Keep a note' }], document: { kind: 'sequence', items: [
  { kind: 'text', value: malicious },
  { kind: 'quote', attribution: 'A visitor', body: { kind: 'text', value: 'A remembered garden.' } },
  { kind: 'reference', key: 'unbound', label: 'Unbound place', object: 'evil', panel: 'main' },
  { kind: 'reference', key: 'bound', childKey: 'bound', label: 'The garden', object: 'garden', panel: 'main' },
  { kind: 'offer', label: 'Cannot dispatch this label', capture: { token: 'write' } },
  { kind: 'fields', actionId: 'write', capture: {}, values: [
    { name: 'source', value: { kind: 'text', value: 'the orchard' } },
    { name: 'n', value: { kind: 'natural', value: '9007199254740993123456789' } },
  ], needs: ['n'] },
  { kind: 'offer', actionId: 'write', label: 'Continue here', capture: {} },
  { kind: 'source', language: 'Bend', code: malicious, revision: 'source-rev' },
  { kind: 'result', status: 'uncertain', body: { kind: 'text', value: 'Awaiting its retained receipt.' } },
  { kind: 'continuation', label: 'Earlier contributions', key: 'history', after: '100000000000000000000', limit: '8' },
] } };
assert.equal(context.renderLivingDocument(living, docTarget, remainingForms, { reference: async ref => targets.push(ref.object) }), true);
const flatten = node => [node, ...node.children.flatMap(flatten)];
const rendered = flatten(docTarget);
assert.equal(rendered.filter(node => node === realForm).length, 1);
assert.equal(remainingForms.children.length, 0);
assert.equal(sourceField.input.value, 'the orchard');
assert.equal(natField.input.value, '', 'Unrepresentable natural may be shown but never rounded into a form');
assert.ok(docTarget.textContent.includes(malicious));
assert.ok(docTarget.textContent.includes('9007199254740993123456789'));
assert.ok(rendered.find(node => node.className === 'document-quote'));
assert.ok(rendered.find(node => node.className === 'document-result').dataset.status === 'uncertain');
assert.equal(rendered.find(node => node.textContent === 'Unbound place').tag, 'span');
assert.equal(rendered.find(node => node.textContent === 'Cannot dispatch this label').tag, 'p');
const ref = rendered.find(node => node.tag === 'button' && node.textContent === 'The garden');
await ref.listeners.click();
assert.deepEqual(targets, ['garden']);
assert.equal(rendered.find(node => node.className === 'document-continuation').tag, 'details');
assert.equal(requests.filter(request => request.url.includes('steal')).length, 0);

// Natural words stay an explicit activity and partial bindings remain a
// proposal. Source rendering alone never calls an interpreter or executes.
let modelCalls = 0;
responder = async (url, options) => {
  const body = JSON.parse(options.body);
  assert.equal(url, '/AGENTS.md/turn');
  if (body.operation === 'interpret') {
    modelCalls++;
    assert.equal(body.text, 'lend <a moth>');
    return response({ status: 'partial', action: 'plant', fields: { word: 'the orchard' }, unresolved: ['recipient'], message: 'Who should receive it?' });
  }
  assert.equal(body.operation, 'prepare');
  assert.equal(body.fields.word, 'the orchard');
  return response({ draft: 'from-partial', intent: 'partial-intent', summary: 'A source-checked proposal', fields: body.fields, wireJson: '{}' });
};
node('agent-intention').value = 'lend <a moth>';
node('agent-contribute').listeners.submit({ preventDefault() {} });
await new Promise(resolve => setImmediate(resolve));
assert.equal(modelCalls, 1);
assert.ok(node('agent-interpretation').textContent.includes('lend <a moth>'));
assert.ok(node('agent-interpretation').textContent.includes('Who should receive it?'));
const partialContinue = node('agent-interpretation').children.find(child => child.tag === 'button');
assert.equal(partialContinue.textContent, 'Continue with these details');
await partialContinue.listeners.click();
assert.equal(evaluate('agentSession.proposal.intent'), 'partial-intent');
assert.equal(executionCalls, 1, 'Interpreting or continuing never auto-executes');
// A source-owned completion already contains the exact prepared draft. The
// browser must not re-interpret it as an action or construct another intent.
let joinedRequests = 0;
responder = async (url, options) => {
  joinedRequests++;
  const body = JSON.parse(options.body);
  assert.equal(body.operation, 'interpret');
  return response({ status: 'ready', via: 'source', interpretation: 'kept-reading',
    draft: { draft: 'source-joined-draft', intent: 'source-joined-intent', summary: 'A kept thought', wireJson: exactRoot } });
};
node('agent-intention').value = 'Keep this thought';
node('agent-contribute').listeners.submit({ preventDefault() {} });
await new Promise(resolve => setImmediate(resolve));
assert.equal(joinedRequests, 1, 'Showing a joined draft does not prepare or execute again');
assert.equal(evaluate('agentSession.proposal.draft'), 'source-joined-draft');
assert.equal(evaluate('agentSession.proposal.intent'), 'source-joined-intent');
assert.equal(evaluate('agentSession.proposal.wireJson'), exactRoot);
assert.equal(node('agent-send').disabled, false);
context.showAgentMembership({ status: 'pending' });
assert.match(node('agent-membership-message').textContent, /identity is verified.*pending/);
assert.equal(node('agent-membership-retry').hidden, false);
context.showAgentMembership({ status: 'unconfigured' });
assert.match(node('agent-membership-message').textContent, /no automatic shared welcome/);
assert.equal(node('agent-membership-retry').hidden, true);
console.log('Authenticated UI: token/header isolation, enrollment proof, exact roots, explicit turns, realm separation and same-intent receipt recovery passed.');
console.log('Living document: source structure, bound contextual forms/references, exact partial values, inert metadata/continuations and text-only rendering passed.');

// Catalogue navigation fetches only the requested page and keeps selected work.
evaluate("agentSession.token = 'pager-token'; agentSession.me = {did:'did:plc:alice',capabilities:{}}; agentSession.card = {object:'held',realm:'shared'};");
node('agent-realm').value = 'shared';
const pageNext = '/AGENTS.md/world?realm=shared&cursor=retained-page';
let catalogueReads = 0, catalogueDrift = false;
node('agent-root').hidden = false;
responder = async url => {
  catalogueReads++;
  if (url === pageNext && catalogueDrift) return {ok:false,status:400,text:async()=>JSON.stringify({message:'stale catalogue cursor'})};
  return response(url === pageNext
    ? {objects:[{object:'two',name:'Second'}],links:{next:null}}
    : {objects:[{object:'one',name:'First'}],links:{next:pageNext}});
};
await context.readAgentWorld();
assert.equal(catalogueReads, 1);
assert.equal(evaluate('agentSession.card.object'), 'held');
assert.equal(node('agent-objects').children.at(-1).textContent, 'Next page');
await node('agent-objects').children.at(-1).listeners.click();
assert.equal(catalogueReads, 2);
assert.equal(node('agent-root').hidden, false, 'Paging keeps exact inspection available');
assert.equal(node('agent-objects').children[0].textContent, 'Second');
assert.equal(evaluate('agentSession.card.object'), 'held');
await context.readAgentWorld();
catalogueDrift = true;
await node('agent-objects').children.at(-1).listeners.click();
assert.match(node('agent-message').textContent, /stale catalogue cursor.*Refresh/);
assert.equal(node('agent-objects').children[0].textContent, 'First');
console.log('Catalogue: explicit bounded next-page fetch, selected-work preservation and stale-page refresh guidance passed.');

// Explicit Read again recaptures the held object, even if it is absent from the
// first shelf page. Its old uncertain proposal remains the exact same intent.
const retainedProposal = evaluate('JSON.stringify(agentSession.proposal)');
evaluate('agentSession.uncertain = true');
const refreshRequests = [];
responder = async url => {
  refreshRequests.push(url);
  if (url.includes('&detail=')) return response({ exact: { root: exactRoot } });
  if (url.includes('&object=held')) return response({ card: 'held-current', object: 'held', title: 'Current held object', prose: 'A fresh source reading.', actions: [] });
  return response({ objects: [{ object: 'other', name: 'Other object' }], links: {} });
};
await node('agent-refresh').listeners.click();
assert.equal(refreshRequests.length, 3, 'Refresh reads shelf, selected encounter, and captured detail');
assert.ok(refreshRequests.some(url => url.includes('&object=held&view=encounter')));
assert.equal(evaluate('agentSession.card.card'), 'held-current');
assert.equal(node('agent-encounter-title').textContent, 'Current held object');
assert.equal(node('agent-root').hidden, false);
assert.equal(evaluate('JSON.stringify(agentSession.proposal)'), retainedProposal);
assert.equal(evaluate('agentSession.uncertain'), true);
console.log('Explicit refresh recaptures selected source while preserving uncertain same-intent work.');
