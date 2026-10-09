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
    this.classList = { toggle() {} };
  }
  set textContent(value) { this.content = String(value); this.children = []; }
  get textContent() { return (this.content || '') + this.children.map(n => n.textContent).join(''); }
  set innerHTML(_) { throw new Error('World text must never enter HTML'); }
  append(...nodes) { this.children.push(...nodes); }
  replaceChildren(...nodes) { this.children = nodes; }
  setAttribute(name, value) { this.attributes[name] = value; }
  addEventListener(name, listener) { this.listeners[name] = listener; }
  setCustomValidity(message) { this.validityMessage = message; }
  reportValidity() { return !this.validityMessage; }
}
const ids = new Map();
const document = {
  createElement: tag => new Node(tag),
  getElementById: id => {
    if (!ids.has(id)) ids.set(id, new Node('div'));
    return ids.get(id);
  },
};
const requests = [];
const context = vm.createContext({
  document, URL, location: { href: 'https://example.invalid/' },
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
