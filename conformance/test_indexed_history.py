"""Trusted checkpoint history paging, live refusal append and exact restart.

Checkpoint rows are generated custody fixtures, not claimed source executions.
The fresh refusal after loading runs through the actual compiled receiver.
"""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class IndexedHistory(unittest.TestCase):
    def test_large_prefix_pages_refusals_append_and_checkpoint_restart(self):
        with tempfile.TemporaryDirectory() as temporary:
            home = Path(temporary)
            root = {'version': 0, 'state': {}, 'protocol': {}, 'law': {
                'profile': 'delvetalk-scoped-law', 'read': 'public',
                'invoke': {}, 'reprogram': ['alice'], 'law': ['alice']}}
            private = {**root, 'law': {**root['law'], 'read': ['alice']}}
            count = 8192
            entries = []
            for ordinal in range(count):
                intent = 'past-' + str(ordinal)
                request = {'op': 'invoke', 'object': 'public', 'command': 'touch',
                           'principal': 'bob', 'intent': intent, 'input': {}}
                if ordinal < 512 or ordinal % 2: request['reads'] = {'private': private}
                entries.append({'request': request, 'receipt': {'kind': 'refused',
                    'intent': intent, 'object': 'public', 'data': 'unauthorized'}})
            checkpoint = home / 'input.json'
            raw = json.dumps({'objects': {'public': root, 'private': private},
                              'receipts': entries}, separators=(',', ':')) + '\n'
            checkpoint.write_text(raw)
            seal = {'sequence': count, 'head': 'retained-custody-anchor',
                    'sha256': hashlib.sha256(raw.encode()).hexdigest()}
            process = None
            def start():
                return subprocess.Popen([str(ROOT / '.lake/build/bin/delvetalk-compiled'), '--resident'],
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1, cwd=ROOT)
            def call(frame):
                process.stdin.write(json.dumps(frame, separators=(',', ':')) + '\n')
                process.stdin.flush()
                reply = json.loads(process.stdout.readline())
                self.assertNotIn('error', reply, reply)
                return reply
            def page(offset, principal='bob', before=count):
                return call({'op': 'query', 'request': {'op': 'object-history',
                    'object': 'public', 'principal': principal, 'before': before,
                    'offset': offset, 'limit': 32}})['reply']
            def stop():
                process.stdin.close()
                process.wait(timeout=10)
                process.stdout.close()
                process.stderr.close()
            try:
                process = start()
                self.assertEqual(call({'op': 'load', 'path': str(checkpoint), 'seal': seal})['sequence'], count)
                # A far-offset page visits only its bounded window, including
                # whole-row omissions for the unreadable native-bound peer.
                skipped = page(0)
                self.assertEqual(skipped['history'], [])
                self.assertEqual(skipped['scanned'], 256)
                self.assertEqual(skipped['nextOffset'], 256)
                first = page(count - 512)
                self.assertEqual([row['request']['intent'] for row in first['history']],
                    ['past-' + str(i) for i in range(count - 512, count - 448, 2)])
                self.assertLessEqual(first['scanned'], 256)
                self.assertLess(first['scanned'], 100)
                self.assertEqual(first['nextOffset'], count - 448)
                trusted = page(count - 512, 'alice')
                self.assertEqual(len(trusted['history']), 32)
                self.assertEqual(trusted['scanned'], 33)
                fresh = {'op': 'invoke', 'object': 'public', 'principal': 'bob',
                         'intent': 'fresh-refusal', 'command': 'touch', 'input': {}}
                prepared = call({'op': 'prepare', 'request': fresh})
                self.assertEqual(prepared['entry']['reply']['kind'], 'refused')
                retained = prepared['entry']['reply']
                call({'op': 'finalize', 'head': prepared['entry']['head']})
                self.assertEqual(call({'op': 'lookup', 'request': fresh})['reply'], retained)
                appended = page(count, before=count + 1)
                self.assertEqual([row['request']['intent'] for row in appended['history']], ['fresh-refusal'])
                self.assertEqual(appended['scanned'], 1)
                output = home / 'output.json'
                exported = call({'op': 'export', 'path': str(output)})['seal']
                stop()
                process = start()
                call({'op': 'load', 'path': str(output), 'seal': exported})
                self.assertEqual(page(count - 512), first)
                self.assertEqual(page(count, before=count + 1), appended)
                self.assertEqual(call({'op': 'lookup', 'request': fresh})['reply'], retained)
            finally:
                if process is not None and process.poll() is None: stop()


if __name__ == '__main__': unittest.main()
