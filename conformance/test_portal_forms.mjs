// Exercise the actual portal script with a small DOM boundary. This checks form
// semantics and text-only insertion; browser layout is deliberately not modeled.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

class Node {
  constructor(tag) {
    this.tag = tag;
    this.children = [];
    this.dataset = {};
    this.attributes = {};
    this.listeners = {};
    this.value = '';
    this.checked = false;
    this.classList = { toggle() {}, add() {} };
  }
  set textContent(value) { this.content = String(value); this.children = []; }
  get textContent() { return (this.content || '') + this.children.map(n => n.textContent).join(''); }
  set innerHTML(_) { throw new Error('World text must never enter HTML'); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  focus() {}
  scrollIntoView() {}
  get childElementCount() { return this.children.length; }
  setCustomValidity(message) { this.validityMessage = message; }
  reportValidity() { return !this.validityMessage; }
}
const ids = new Map();
const document = {
  createElement: tag => new Node(tag),
  querySelector: selector => document.getElementById(selector),
  getElementById: id => {
    if (!ids.has(id)) ids.set(id, new Node('div'));
    return ids.get(id);
  },
};
const requests = [];
const navigation = [];
const events = {};
const location = { href: 'https://example.invalid/' };
const history = Object.fromEntries(['pushState', 'replaceState'].map(method => [method, (_, __, url) => {
  location.href = String(url); navigation.push({ method, url: String(url) });
}]));
const context = vm.createContext({
  document, URL, history, location,
  window: { addEventListener(name, fn) { events[name] = fn; } },
  matchMedia: () => ({ matches: true }),
  fetch: (url, options) => {
    requests.push({ url, options });
    return new Promise(() => {}); // Startup waits; no network or world authority.
  },
});
vm.runInContext(readFileSync(new URL('../portal/static/app.js', import.meta.url), 'utf8'), context);
const input = field => context.fieldInput(field, 0, 0);
const read = controls => JSON.parse(JSON.stringify(context.readFields(controls)));

const malicious = '<img src=x onerror="alert(1)"> & "moon"';
const word = input({ name: 'word', label: 'Which remembered place?', type: 'string',
  required: true, minLength: 1, example: malicious });
assert.equal(word.label.children[0].textContent, 'Which remembered place? · required');
assert.equal(word.input.placeholder, malicious);
assert.equal(word.label.children.at(-1).textContent, `Example: ${malicious}`);
assert.equal(word.input.attributes['aria-describedby'], word.label.children.at(-1).id);
assert.equal(word.input.value, '');
assert.throws(() => read([word]), /text length/);
word.input.value = 'the orchard';
assert.deepEqual(read([word]), { word: 'the orchard' });

const count = input({ name: 'count', type: 'nat', required: true, example: 0 });
assert.equal(count.input.placeholder, '0');
assert.equal(count.label.children.at(-1).textContent, 'Example: 0');
assert.equal(count.input.value, '');
assert.throws(() => read([count]), /number/);
count.input.value = '2';
assert.deepEqual(read([count]), { count: 2 });

for (const example of [false, true]) {
  const toggle = input({ name: 'invite', type: 'bool', example });
  assert.equal(toggle.label.children.at(-1).textContent, `Example: ${example}`);
  assert.equal(toggle.input.checked, false);
  assert.deepEqual(read([toggle]), { invite: false });
}
const choice = input({ name: 'color', type: 'enum', required: true,
  options: ['amber', malicious], example: malicious });
assert.equal(choice.input.children[2].textContent, malicious);
assert.equal(choice.label.children.at(-1).textContent, `Example: ${malicious}`);
assert.equal(choice.input.value, '');
assert.throws(() => read([choice]), /Choose a value/);
choice.input.value = '0';
assert.deepEqual(read([choice]), { color: 'amber' });
const optional = input({ name: 'note', type: 'string', example: 'welcome' });
assert.deepEqual(read([optional]), {});
const empty = input({ name: 'note', type: 'string', example: '' });
assert.equal(empty.label.children.at(-1).textContent, 'Example: ""');
assert.equal(input({ name: 'plain', type: 'string' }).label.children.length, 2);
const sourceText = input({ name: 'source', label: 'Source', type: 'string', required: true,
  minLength: 1, maxLength: 4096 });
assert.equal(sourceText.input.tag, 'textarea');
sourceText.input.value = 'edition ObjectiveBend 1\n\ndef main()->String:\n  "a literal <tag>"\n';
assert.deepEqual(read([sourceText]), { source: sourceText.input.value });

// Public card fields exclude projection-bound input. Rendering must neither
// invent controls for that input nor submit example text on the user's behalf.
context.renderActions({ card: 'garden', actions: [{ id: 'a1', label: 'Enter the garden',
  input: { destination: 'garden' }, fields: [word.field] }] });
const form = document.getElementById('actions').children[0];
const renderedInput = form.children.find(n => n.className === 'action-fields').children[0].children[1];
assert.equal(renderedInput.name, 'word');
assert.equal(renderedInput.value, '');
form.listeners.submit({ preventDefault() {} });
await new Promise(resolve => setImmediate(resolve));
assert.equal(requests.filter(r => r.url === '/api/prepare').length, 0);
renderedInput.value = 'my own words';
form.listeners.submit({ preventDefault() {} });
await new Promise(resolve => setImmediate(resolve));
const prepared = requests.find(r => r.url === '/api/prepare');
assert.deepEqual(JSON.parse(prepared.options.body), {
  card: 'garden', action: 'a1', fields: { word: 'my own words' },
});
console.log('Portal authored examples: text-only guidance, empty fields, explicit submission passed.');

// Panel navigation is generic, encoded in the URL, and preserves uncertain work.
vm.runInContext("state.world = { mode: 'public-preview', objects: [{ id: 'door', title: 'Door' }] }", context);
const panels = [{ id: 'main', label: 'Overview' }, { id: 'ink & light', label: malicious }];
const cards = [];
context.fetch = async (url, options) => {
  requests.push({ url, options });
  const panel = new URL(url, location.href).searchParams.get('panel') || 'main';
  const card = { card: 'card-' + cards.length, object: 'door', title: 'Door', prose: panel,
    panel, panels, actions: [], version: 0 };
  cards.push(card);
  return { ok: true, json: async () => card };
};
await context.openObject('door', true, 'ink & light', 'push');
assert.equal(new URL(location.href).searchParams.get('panel'), 'ink & light');
assert.equal(navigation.at(-1).method, 'pushState');
assert.equal(document.getElementById('object-panels').children[1].textContent, malicious);
assert.equal(document.getElementById('object-panels').children[1].attributes['aria-current'], 'true');
assert.equal(document.getElementById('interpret-form').hidden, true);
document.getElementById('refresh-object').listeners.click();
await new Promise(resolve => setImmediate(resolve));
assert.equal(new URL(requests.at(-1).url, location.href).searchParams.get('panel'), 'ink & light');
assert.equal(navigation.at(-1).method, 'replaceState');
location.href = 'https://example.invalid/?object=door&panel=main';
await events.popstate();
assert.equal(document.getElementById('object-prose').textContent, 'main');
assert.equal(new URL(location.href).searchParams.has('panel'), false);
const draft = { draft: 'retaineddraft', summary: 'Knock', object: 'door', panel: 'ink & light',
  token: 'private-token', fields: { note: malicious }, canExecute: false, wireJson: '{}' };
context.showDraft(draft);
assert.equal(document.getElementById('send-draft').hidden, true);
assert.equal(document.getElementById('draft-command-row').hidden, true);
assert.equal(document.getElementById('preview-copy').hidden, false);
assert.equal(document.getElementById('draft-fields').children[1].textContent, malicious);
context.showDraft({ ...draft, reads: [{ object: 'workshop', version: 2 }, { object: malicious, version: 0 }],
  absence: ['candidates/new'] });
assert.equal(document.getElementById('draft-target').textContent,
  `Captured together: workshop · version 2; ${malicious} · version 0. All steps commit together.`);
assert.equal(document.getElementById('draft-absence').textContent,
  'Creates: candidates/new. These object names must still be absent.');
vm.runInContext("state.world.mode = 'local-interactive'; state.uncertain = true;", context);
location.href = 'https://example.invalid/?object=door&panel=ink%20%26%20light';
await events.popstate();
assert.equal(new URL(location.href).searchParams.get('draft'), 'retaineddraft');
assert.equal(document.getElementById('draft-panel').hidden, false);
assert.equal(document.getElementById('draft-command').textContent, 'private-token');
assert.equal(vm.runInContext('state.uncertain', context), true);
assert.equal(vm.runInContext('state.draft.draft', context), 'retaineddraft');
const requestCount = requests.length;
vm.runInContext('state.sending = true', context);
await context.openObject('door', false, 'main', 'push');
assert.equal(requests.length, requestCount);
console.log('Portal panels: selection, refresh, history, safe labels, public copy and uncertain draft preservation passed.');

location.href = 'https://example.invalid/?object=other';
await events.popstate();
assert.equal(new URL(location.href).searchParams.get('object'), 'door');
vm.runInContext("state.sending = false; authoring.uncertain = true; authoring.draft = { draft: 'retained-work' };", context);
location.href = 'https://example.invalid/?object=door&work=other-work';
await events.popstate();
assert.equal(new URL(location.href).searchParams.get('work'), 'retained-work');
assert.equal(vm.runInContext('authoring.draft.draft', context), 'retained-work');
assert.equal(requests.some(r => r.url.includes('/api/authoring/draft?draft=other-work')), false);

// Resolve two real route requests in reverse order: late old work must not
// replace a newer restored draft, its uncertainty, or its URL.
vm.runInContext("state.sending = false; state.uncertain = false; state.draft = null; state.world = { mode: 'local-interactive', objects: [{id: 'door'}], authoring: {} }; authoring.pending = false; authoring.uncertain = false; authoring.draft = null;", context);
const workReplies = new Map();
context.fetch = async (url, options) => {
  requests.push({ url, options });
  if (url.startsWith('/api/authoring/draft?')) {
    const id = new URL(url, location.href).searchParams.get('draft');
    return new Promise(resolve => workReplies.set(id, () => resolve({ ok: true,
      json: async () => ({ draft: id, operation: 'compile', canExecute: true }) })));
  }
  const value = url.startsWith('/api/object')
    ? { card: 'door-card', object: 'door', panel: 'main', panels, actions: [] }
    : { phase: 'prepared' };
  return { ok: true, json: async () => value };
};
location.href = 'https://example.invalid/?object=door&work=old';
const oldRoute = events.popstate();
await new Promise(resolve => setImmediate(resolve));
assert.equal(workReplies.has('old'), true);
location.href = 'https://example.invalid/?object=door&work=new';
const newRoute = events.popstate();
await new Promise(resolve => setImmediate(resolve));
workReplies.get('new')();
await newRoute;
assert.equal(vm.runInContext('authoring.draft.draft', context), 'new');
assert.equal(vm.runInContext('authoring.uncertain', context), true);
workReplies.get('old')();
await oldRoute;
assert.equal(vm.runInContext('authoring.draft.draft', context), 'new');
assert.equal(vm.runInContext('authoring.uncertain', context), true);
assert.equal(new URL(location.href).searchParams.get('work'), 'new');
assert.equal(requests.some(r => r.url === '/api/authoring/status?draft=old'), false);

// A response also loses authority to replace the UI if work starts while it
// is loading, even when no second route was requested.
for (const guard of ['pending', 'uncertain', 'preparing']) {
  vm.runInContext("authoring.pending = false; authoring.uncertain = false; authoring.preparing = false; authoring.draft = { draft: 'kept' };", context);
  location.href = `https://example.invalid/?object=door&work=delayed-${guard}`;
  const route = events.popstate();
  await new Promise(resolve => setImmediate(resolve));
  vm.runInContext(`authoring.${guard} = true`, context);
  workReplies.get(`delayed-${guard}`)();
  await route;
  assert.equal(vm.runInContext('authoring.draft.draft', context), 'kept');
  assert.equal(document.getElementById('authoring-alias').textContent, 'work new');
}
console.log('Portal delayed authoring responses: newest route and pending/uncertain work remain intact.');

// Authored catalogues contain reads, not invocations. The child endpoint selects
// from the retained parent card and returns its own fresh object/card/panel.
vm.runInContext("state.sending = false; state.uncertain = false; state.draft = null; authoring.pending = false; authoring.uncertain = false; authoring.preparing = false; state.world = { mode: 'public-preview', objects: [{id: 'index'}, {id: 'lantern'}] };", context);
const catalogue = { card: 'parent-capture', object: 'index', panel: 'main', title: 'An exhibition',
  actions: [], children: [{ key: 'lamp & one', label: malicious, object: 'lantern', panel: 'glow' },
    { key: 'missing', label: 'An absent exhibit', object: 'absent', panel: 'main' }] };
const childCard = { card: 'child-current-capture', object: 'lantern', panel: 'glow', title: 'The lantern now',
  actions: [], children: [], panels: [{id: 'main', label: 'Overview'}, {id: 'glow', label: 'Glow'}] };
context.fetch = async (url, options) => {
  requests.push({url, options});
  let value = catalogue;
  if (url.startsWith('/api/child')) {
    assert.equal(new URL(url, location.href).searchParams.get('card'), 'parent-capture');
    value = new URL(url, location.href).searchParams.get('key') === 'missing'
      ? {status: 'unavailable', message: 'Unknown object'}
      : {status: 'opened', card: childCard};
  }
  return {ok: true, json: async () => value};
};
await context.openObject('index');
const children = document.getElementById('view-children').children.at(-1).children;
assert.equal(children[0].textContent, malicious);
assert.equal(children[0].tag, 'button');
assert.equal(document.getElementById('actions').textContent, 'No actions are offered in this reading.');
await children[1].listeners.click();
assert.equal(vm.runInContext('state.card.card', context), 'parent-capture');
assert.match(document.getElementById('notice').textContent, /Unavailable: An absent exhibit/);
assert.equal(document.getElementById('view-children').hidden, false);
const childRequestStart = requests.length;
await children[0].listeners.click();
assert.equal(vm.runInContext('state.card.card', context), 'child-current-capture');
assert.equal(new URL(location.href).searchParams.get('object'), 'lantern');
assert.equal(new URL(location.href).searchParams.get('panel'), 'glow');
assert.equal(navigation.at(-1).method, 'pushState');
assert.equal(document.getElementById('view-children').hidden, true);
assert.equal(requests.slice(childRequestStart).length, 1);
assert.equal(requests.at(-1).options.method, undefined);
assert.equal(catalogue.card, 'parent-capture');
assert.equal(catalogue.object, 'index');
console.log('Portal authored children: safe read-only labels, fresh child capture, unavailable-row recovery passed.');
