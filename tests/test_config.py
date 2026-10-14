"""Refuted by any live open-town key failing to load, or a removed setting still being accepted."""
import tempfile
import unittest
from pathlib import Path

from transport.config import Config


class ConfigLoad(unittest.TestCase):
    def test_live_open_keys_load_and_removed_keys_are_refused_by_name(self):
        live = {
            'arrival': 'open', 'hand_find': False, 'watch_topic': 'watch-open',
            'summon_handle': 'obend.fg-goose.online', 'card_room': 8000,
            'arrive_per_address': 30, 'arrive_per_hour': 300,
            'turn_quota': 300, 'object_quota': 96,
        }
        toml = '''arrival = "open"
hand_find = false
watch_topic = "watch-open"
summon_handle = "obend.fg-goose.online"
card_room = 8000
arrive_per_address = 30
arrive_per_hour = 300
turn_quota = 300
object_quota = 96
'''
        removed = {
            'model_poll': '1.0', 'watch_stream': '"delvetalk-ops"',
            'probe_names': '"deploycheck"', 'automod': 'true',
            'automod_model': '"glm-5.3-flash"',
            'automod_base_url': '"https://api.z.ai/api/anthropic"',
            'automod_window': '5.0', 'automod_batch': '24',
            'automod_daily_calls': '2000', 'automod_quiet_hours': '24',
        }
        with tempfile.TemporaryDirectory() as state:
            path = Path(state) / 'delvetalk.toml'
            path.write_text(toml)
            config = Config.load(state, environ={})
            self.assertEqual({key: getattr(config, key) for key in live}, live)
            for key, value in removed.items():
                with self.subTest(removed=key):
                    path.write_text(toml + f'{key} = {value}\n')
                    with self.assertRaisesRegex(SystemExit, f"delvetalk.toml: no setting '{key}'"):
                        Config.load(state, environ={})
