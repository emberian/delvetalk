// Checked CLI used by publication preflight and unittest. JSON samples arrive on stdin.
// Exit 0: valid; 1: validation failed; 2: the pinned validator is unavailable.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

let validator = '@atproto/lexicon 0.7.16';
let api;
try {
  const require = createRequire(import.meta.url);
  const entry = process.env.ATPROTO_LEXICON_PACKAGE
    ? path.join(process.env.ATPROTO_LEXICON_PACKAGE, 'dist/index.js')
    : (() => {
        try { return require.resolve('@atproto/lexicon'); }
        catch { return createRequire(path.join(process.cwd(), 'package.json')).resolve('@atproto/lexicon'); }
      })();
  const pkg = JSON.parse(fs.readFileSync(path.resolve(path.dirname(entry), '../package.json')));
  validator = `${pkg.name} ${pkg.version}`;
  if (pkg.version !== '0.7.16') throw new Error(`needs 0.7.16, found ${pkg.version}`);
  api = await import(pathToFileURL(entry).href);
} catch (error) {
  console.log(JSON.stringify({ validator, unavailable: error.message, errors: [] }));
  process.exit(2);
}

const lex = new api.Lexicons();
// https://github.com/bluesky-social/atproto/blob/main/lexicons/com/atproto/lexicon/schema.json
// The standard publication record schema intentionally validates only the version;
// lexiconDoc.parse below checks the document language itself.
lex.add({ lexicon: 1, id: 'com.atproto.lexicon.schema', defs: { main: {
  type: 'record', key: 'nsid', record: {
    type: 'object', required: ['lexicon'], properties: { lexicon: { type: 'integer' } },
  },
} } });
lex.add({ lexicon: 1, id: 'com.atproto.repo.strongRef', defs: { main: {
  type: 'object', required: ['uri', 'cid'], properties: {
    uri: { type: 'string', format: 'at-uri' }, cid: { type: 'string', format: 'cid' },
  },
} } });
const errors = [], files = [];
function attempt(label, fn) {
  try { fn(); } catch (error) { errors.push(`${label}: ${error.message}`); }
}
function walk(directory) {
  for (const name of fs.readdirSync(directory).sort()) {
    const filename = path.join(directory, name);
    if (fs.statSync(filename).isDirectory()) walk(filename);
    else if (name.endsWith('.json')) {
      files.push(filename);
      attempt(filename, () => {
        const doc = JSON.parse(fs.readFileSync(filename, 'utf8'));
        api.lexiconDoc.parse(doc); // add() alone does not check document syntax.
        lex.add(doc); // Keep the original, including extensions the schema parser strips.
      });
    }
  }
}
attempt('directory', () => walk(process.argv[2] ?? 'lexicons'));
// Check references after loading the entire collection, including forward references.
function refs(node, label) {
  if (!node || typeof node !== 'object') return;
  if (node.type === 'ref') attempt(label, () => lex.getDefOrThrow(node.ref));
  if (node.type === 'union') for (const ref of node.refs) attempt(label, () => lex.getDefOrThrow(ref));
  for (const [key, value] of Object.entries(node)) refs(value, `${label}.${key}`);
}
for (const doc of lex) refs(doc.defs, doc.id);
attempt('samples', () => {
  const input = fs.readFileSync(0, 'utf8');
  const samples = input.trim() ? JSON.parse(input) : [];
  for (const [index, sample] of samples.entries()) attempt(sample.label ?? `sample ${index}`, () => {
    const value = api.jsonToLex(sample.value); // Wire $link/$bytes -> actual IPLD values.
    switch (sample.kind) {
      case 'record': lex.assertValidRecord(sample.nsid, value); break;
      case 'params': lex.assertValidXrpcParams(sample.nsid, value); break;
      case 'input': lex.assertValidXrpcInput(sample.nsid, value); break;
      case 'output': lex.assertValidXrpcOutput(sample.nsid, value); break;
      case 'object': {
        const result = lex.validate(sample.nsid, value);
        if (!result.success) throw result.error;
        break;
      }
      default: throw new Error(`unknown sample kind: ${sample.kind}`);
    }
  });
});
console.log(JSON.stringify({ validator, files, errors }));
process.exit(errors.length ? 1 : 0);
