#!/usr/bin/env node
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { run, validate } from '../impl/js/evaluator.mjs';

const fixtures = JSON.parse(readFileSync(new URL('./cases.json', import.meta.url), 'utf8'));
for (const { expected, ...job } of fixtures)
  assert.deepEqual(run(job), { name: job.name, ...expected }, job.name);

let checks = 0;
const n = x => ['nat', String(x)];
const b = x => ['boolean', x];
const label = x => ['label', x];
function expect(term, result, { status = 'value', plans = [], ...options } = {}) {
  checks++;
  assert.deepEqual(run({ name: 'js-check', term, ...options }),
    { name: 'js-check', status, term: result, plans });
}
const huge = 10n ** 5000n + 123456789n;
expect(['binary', 'add', n(huge), n(1)], n(huge + 1n));
expect(['binary', 'multiply', n(huge), n(huge)], n(huge * huge));
expect(['binary', 'subtract', n(1), n(huge)], n(0));
expect(['binary', 'divide', n(huge), n(0)], n(0));
expect(['binary', 'modulo', n(huge), n(0)], n(huge));
expect(['binary', 'less', n(9007199254740992n), n(9007199254740993n)], b(true));
expect(['binary', 'labelEqual', label('🪼'), label('🪼')], b(true));
expect(['binary', 'labelEqual', label('é'), label('e\u0301')], b(false));
expect(['get', ['record', [['__proto__', n(9)], ['💭\u0000', n(7)]]], '💭\u0000'], n(7));
for (const term of [
  ['binary', 'equal', b(true), n(1)],
  ['binary', 'conjunction', label('true'), label('false')],
  ['ifBool', n(1), n(7), n(8)],
]) expect(term, term, { status: 'stuck', fuel: 0 });

// Wrong left scalar still demands the right computation: conjunction is strict.
const rawPlan = ['app', n(3), n(4)];
const pending = ['binary', 'conjunction', b(false), ['perform', rawPlan]];
expect(pending, pending, { status: 'yield', plans: [rawPlan], fuel: 0 });
expect(pending, b(false), { responses: [b(true)], plans: [rawPlan], fuel: 1 });
expect(['perform', rawPlan], n(9), { responses: [n(9)], plans: [rawPlan], fuel: 0 });
const returnTerm = ['done', n(7)];
expect(returnTerm, returnTerm, { status: 'exhausted', fuel: 0 });
expect(returnTerm, n(7), { fuel: 1 });

// Capture avoidance under each binder, including an open response.
expect(['app', ['lam', ['lam', ['bound', 1]]], ['bound', 0]], ['lam', ['bound', 1]]);
expect(['app', ['lam', ['ifZero', n(2), n(0), ['lam', ['bound', 2]]]], ['bound', 0]],
  ['lam', ['bound', 1]]);
expect(['app', ['lam', ['case', ['inject', 'x', n(7)], [['x', ['lam', ['bound', 2]]]]]], ['bound', 0]],
  ['lam', ['bound', 1]]);
expect(['get', ['perform', label('fields')], 'x'], n(4), {
  plans: [label('fields')], responses: [['record', [['x', n(4)]]]], fuel: 1,
});

const malformed = [
  ['nat', 1], ['nat', true], ['nat', '01'], ['nat', '-1'], ['nat', '1\n'],
  ['boolean', 1], ['boolean', 'true'], ['bound', true], ['bound', -1],
  ['bound', 1.5], ['bound', 9007199254740992], ['label', '\ud800'],
  ['label', '\udc00'], ['label', '\ud800x'], ['get', n(1), '\udfff'],
  ['record', { x: n(1) }], ['record', [['x', n(1), n(2)]]],
  ['binary', 'toString', n(1), n(2)], ['nat', '1', 'extra'], ['noSuchTerm'],
];
for (const term of malformed) assert.throws(() => validate(term), TypeError);
for (const extra of [{ fuel: true }, { fuel: -1 }, { fuel: 9007199254740992 },
  { responses: false }, { unexpected: 0 }, { name: '\ud800' }])
  assert.throws(() => run({ name: 'invalid', term: n(1), ...extra }), TypeError);

const evaluator = fileURLToPath(new URL('../impl/js/evaluator.mjs', import.meta.url));
const jobs = fixtures.map(({ expected, ...job }) => job);
const valid = spawnSync(process.execPath, [evaluator], {
  input: jobs.map(job => JSON.stringify(job)).join('\n') + '\n', encoding: 'utf8',
});
assert.equal(valid.status, 0, valid.stderr);
assert.equal(valid.stderr, '');
const outputs = valid.stdout.trim().split('\n').map(JSON.parse);
assert.deepEqual(outputs, fixtures.map(({ name, expected }) => ({ name, ...expected })));
for (const input of ['not json\n', JSON.stringify({ name: 'bad', term: ['boolean', 1] }) + '\n']) {
  const invalid = spawnSync(process.execPath, [evaluator], { input, encoding: 'utf8' });
  assert.equal(invalid.status, 1);
  assert.equal(invalid.stdout, '');
  assert.match(invalid.stderr, /^line 1:/);
}
console.log(`JS: ${fixtures.length} shared cases, ${checks} semantic edge cases, ${malformed.length + 6} malformed inputs, JSONL checks passed`);
