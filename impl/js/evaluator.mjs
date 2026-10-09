#!/usr/bin/env node
// Independent source-step interpreter. No parser, checker, authority or host I/O.
// Nat arithmetic uses BigInt; the wire preserves decimal strings, not Numbers.
import { createInterface } from 'node:readline';
import { pathToFileURL } from 'node:url';
import { createHash } from 'node:crypto';

const arities = new Map(Object.entries({
  bound: 2, lam: 2, app: 3, mix: 3, fix: 3, specification: 3, prototype: 3,
  reflect: 2, metadata: 2, project: 2, nat: 2, boolean: 2, label: 2,
  binary: 4, unary: 3, extend: 3, record: 2, get: 3, ifZero: 4, inject: 3,
  case: 3, ifBool: 4, perform: 2, done: 2, toData: 2,
}));
const primitives = new Set(['add', 'multiply', 'equal', 'conjunction',
  'labelEqual', 'subtract', 'divide', 'less', 'lessEqual', 'modulo',
  'textConcat', 'textTake', 'textDrop', 'textSpan', 'textBreak']);
const unaries = new Set(['natText', 'textLength', 'sha256Text']);
const values = new Set(['lam', 'nat', 'boolean', 'label', 'record',
  'specification', 'prototype', 'inject']);
const scalarString = x => typeof x === 'string' && !/[\uD800-\uDFFF]/u.test(x);
const naturalIndex = x => Number.isSafeInteger(x) && x >= 0;
function requireThat(condition, message) {
  if (!condition) throw new TypeError(message);
}

export function validate(term) {
  const pending = [term];
  while (pending.length) {
    const t = pending.pop();
    requireThat(Array.isArray(t) && arities.has(t[0]) && t.length === arities.get(t[0]),
      'unknown constructor or wrong term arity');
    const [tag, a, b] = t;
    if (tag === 'bound') requireThat(naturalIndex(a), 'bound index must be a safe nonnegative integer');
    else if (tag === 'nat') requireThat(typeof a === 'string' && /^(0|[1-9][0-9]*)$/.test(a),
      'Nat must be a canonical unsigned decimal string');
    else if (tag === 'boolean') requireThat(typeof a === 'boolean', 'Boolean must be a JSON Boolean');
    else if (tag === 'label') requireThat(scalarString(a), 'label must be a Unicode scalar string');
    else if (tag === 'get' || tag === 'inject') {
      requireThat(scalarString(tag === 'get' ? b : a), 'key must be a Unicode scalar string');
      pending.push(tag === 'get' ? a : b);
    } else if (tag === 'record' || tag === 'extend' || tag === 'case') {
      const fields = t.at(-1);
      requireThat(Array.isArray(fields), 'fields and arms must be ordered arrays');
      for (const field of fields) {
        requireThat(Array.isArray(field) && field.length === 2 && scalarString(field[0]),
          'field or arm must be [Unicode string,term]');
        pending.push(field[1]);
      }
      if (tag !== 'record') pending.push(a);
    } else if (tag === 'binary') {
      requireThat(primitives.has(a), 'unknown primitive');
      pending.push(b, t[3]);
    } else if (tag === 'unary') {
      requireThat(unaries.has(a), 'unknown unary primitive');
      pending.push(b);
    } else pending.push(...t.slice(1));
  }
  return term;
}

// A substitution is a function from free indices to terms. Lifting it under
// each binder is the definition from the source, independent of evaluation.
function substitute(t, env) {
  const under = i => i === 0 ? ['bound', 0] : rename(env(i - 1), n => n + 1);
  const sub = child => substitute(child, env);
  switch (t[0]) {
    case 'bound': return env(t[1]);
    case 'nat': case 'boolean': case 'label': return t;
    case 'lam': return ['lam', substitute(t[1], under)];
    case 'ifZero': return ['ifZero', sub(t[1]), sub(t[2]), substitute(t[3], under)];
    case 'record': return ['record', t[1].map(([key, body]) => [key, sub(body)])];
    case 'extend': return ['extend', sub(t[1]), t[2].map(([key, body]) => [key, sub(body)])];
    case 'case': return ['case', sub(t[1]), t[2].map(([key, body]) => [key, substitute(body, under)])];
    case 'get': return ['get', sub(t[1]), t[2]];
    case 'inject': return ['inject', t[1], sub(t[2])];
    case 'binary': return ['binary', t[1], sub(t[2]), sub(t[3])];
    case 'unary': return ['unary', t[1], sub(t[2])];
    default: return [t[0], ...t.slice(1).map(sub)];
  }
}
function rename(t, mapping) {
  return substitute(t, i => {
    const n = mapping(i);
    requireThat(naturalIndex(n), 'host capacity: bound index exceeds safe integer range');
    return ['bound', n];
  });
}
const instantiate = (body, argument) => substitute(body, i => i === 0 ? argument : ['bound', i - 1]);
const nat = n => ['nat', n.toString()];
const bool = b => ['boolean', b];

const scalars = text => Array.from(text);
function prefixLength(text, alphabet, member) {
  const set = new Set(scalars(alphabet));
  let count = 0;
  for (const c of scalars(text)) { if (set.has(c) !== member) break; count++; }
  return count;
}
function primitive(op, left, right) {
  if (op === 'conjunction')
    return left[0] === 'boolean' && right[0] === 'boolean' ? () => bool(left[1] && right[1]) : null;
  if (op === 'labelEqual')
    return left[0] === 'label' && right[0] === 'label' ? () => bool(left[1] === right[1]) : null;
  if (op === 'textConcat' || op === 'textSpan' || op === 'textBreak') {
    if (left[0] !== 'label' || right[0] !== 'label') return null;
    if (op === 'textConcat') return () => ['label', left[1] + right[1]];
    return () => nat(BigInt(prefixLength(left[1], right[1], op === 'textSpan')));
  }
  if (op === 'textTake' || op === 'textDrop') {
    if (left[0] !== 'label' || right[0] !== 'nat') return null;
    return () => {
      const n = BigInt(right[1]), size = BigInt(Buffer.byteLength(left[1], 'utf8'));
      const chars = scalars(left[1]);
      if (op === 'textTake') return ['label', n === 0n ? '' : n >= size ? left[1] : chars.slice(0, Number(n)).join('')];
      return ['label', n === 0n ? left[1] : n >= size ? '' : chars.slice(Number(n)).join('')];
    };
  }
  if (left[0] !== 'nat' || right[0] !== 'nat') return null;
  return () => {
    const a = BigInt(left[1]), b = BigInt(right[1]);
    switch (op) {
      case 'add': return nat(a + b);
      case 'multiply': return nat(a * b);
      case 'equal': return bool(a === b);
      case 'subtract': return nat(a < b ? 0n : a - b);
      case 'divide': return nat(b === 0n ? 0n : a / b);
      case 'modulo': return nat(b === 0n ? a : a % b);
      case 'less': return bool(a < b);
      case 'lessEqual': return bool(a <= b);
    }
  };
}
function unaryOp(op, arg) {
  if (op === 'natText' && arg[0] === 'nat') return () => ['label', arg[1]];
  if (op === 'textLength' && arg[0] === 'label') return () => nat(BigInt(scalars(arg[1]).length));
  if (op === 'sha256Text' && arg[0] === 'label')
    return () => ['label', createHash('sha256').update(arg[1], 'utf8').digest('hex')];
  return null;
}

const stuck = { kind: 'stuck' };
const step = advance => ({ kind: 'step', advance });
function inside(t, index) {
  const action = inspect(t[index]);
  const replace = x => t.map((child, i) => i === index ? x : child);
  if (action.kind === 'step') return step(() => replace(action.advance()));
  if (action.kind === 'yield') return {
    kind: 'yield', plan: action.plan, resume: response => replace(action.resume(response)),
  };
  return stuck;
}

// Congruence rules recurse only into the source evaluation position. A step
// thunk delays contraction until fuel is available; yields consume no steps.
function inspect(t) {
  const [tag, a, b, c] = t;
  if (values.has(tag)) return { kind: 'value' };
  switch (tag) {
    case 'app':
      if (a[0] === 'lam') return step(() => instantiate(a[1], b));
      if (a[0] === 'specification') return step(() => ['app', a[2], b]);
      return inside(t, 1);
    case 'mix': return step(() => ['lam', ['lam',
      ['app', ['app', rename(b, n => n + 2), ['bound', 1]],
        ['app', ['app', rename(a, n => n + 2), ['bound', 1]], ['bound', 0]]]]]);
    case 'fix': return step(() => ['app', ['app', a, t], b]);
    case 'reflect': case 'metadata': case 'project':
      if (a[0] === (tag === 'metadata' ? 'specification' : 'prototype'))
        return step(() => a[tag === 'project' ? 2 : 1]);
      return inside(t, 1);
    case 'get': {
      if (a[0] !== 'record') return inside(t, 1);
      const field = a[1].find(([key]) => key === b);
      return field ? step(() => field[1]) : stuck;
    }
    case 'extend':
      if (a[0] !== 'record') return inside(t, 1);
      return step(() => ['record', [...b, ...a[1].filter(([key]) => !b.some(([k]) => k === key))]]);
    case 'binary': {
      if (!values.has(b[0])) return inside(t, 2);
      if (!values.has(c[0])) return inside(t, 3);
      const reduce = primitive(a, b, c);
      return reduce ? step(reduce) : stuck;
    }
    case 'unary': {
      if (!values.has(b[0])) return inside(t, 2);
      const reduce = unaryOp(a, b);
      return reduce ? step(reduce) : stuck;
    }
    case 'ifZero':
      if (a[0] !== 'nat') return inside(t, 1);
      return step(() => a[1] === '0' ? b : instantiate(c, nat(BigInt(a[1]) - 1n)));
    case 'case': {
      if (a[0] !== 'inject') return inside(t, 1);
      const arm = b.find(([key]) => key === a[1]);
      return arm ? step(() => instantiate(arm[1], a[2])) : stuck;
    }
    case 'ifBool':
      if (a[0] !== 'boolean') return inside(t, 1);
      return step(() => a[1] ? b : c);
    case 'perform': return { kind: 'yield', plan: a, resume: response => response };
    case 'done': case 'toData': return step(() => a);
    default: return stuck;
  }
}

export function run(job) {
  requireThat(job !== null && typeof job === 'object' && !Array.isArray(job) &&
    Object.keys(job).every(key => ['name', 'term', 'responses', 'fuel'].includes(key)),
  'job must contain only name,term,responses,fuel');
  requireThat(scalarString(job.name), 'job requires a Unicode string name');
  let term = validate(job.term);
  const responses = job.responses === undefined ? [] : job.responses;
  let fuel = job.fuel === undefined ? 10000 : job.fuel;
  requireThat(Array.isArray(responses), 'responses must be an array');
  requireThat(naturalIndex(fuel), 'fuel must be a safe nonnegative integer');
  responses.forEach(validate);
  const plans = [];
  let response = 0;
  for (;;) {
    const action = inspect(term);
    if (action.kind === 'step') {
      if (fuel === 0) return { name: job.name, status: 'exhausted', term, plans };
      term = action.advance();
      fuel--;
    } else if (action.kind === 'yield') {
      plans.push(action.plan);
      if (response === responses.length) return { name: job.name, status: 'yield', term, plans };
      term = action.resume(responses[response++]);
    } else return { name: job.name, status: action.kind, term, plans };
  }
}

async function main() {
  let lineNumber = 0;
  for await (const line of createInterface({ input: process.stdin, crlfDelay: Infinity })) {
    lineNumber++;
    try {
      process.stdout.write(JSON.stringify(run(JSON.parse(line))) + '\n');
    } catch (error) {
      process.stderr.write(`line ${lineNumber}: ${error.message}\n`);
      process.exitCode = 1;
      break;
    }
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) await main();
