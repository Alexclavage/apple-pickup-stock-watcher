import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import app as watcher


class WatcherSmokeTests(unittest.TestCase):
    def test_http_endpoints_without_network(self):
        c = watcher.app.test_client()
        self.assertEqual(c.get('/').status_code, 200)
        self.assertEqual(c.get('/api/status').status_code, 200)
        self.assertEqual(c.get('/health').status_code, 200)

    def test_partial_apple_response_does_not_repeat_available_alert(self):
        item = {'key': 'test:R102', 'status': 'available'}
        with tempfile.TemporaryDirectory() as temp, patch.object(watcher, 'STATE_FILE', Path(temp) / 'state.json'), patch.object(watcher, 'send_stock_changes') as send:
            with patch.object(watcher, 'fetch_all', side_effect=[([item], []), ([], ['Apple 541']), ([item], [])]):
                watcher.poll_once()
                self.assertEqual(send.call_count, 1)
                self.assertEqual(len(send.call_args.args[0]), 1)
                watcher.poll_once()
                watcher.poll_once()
                self.assertEqual(send.call_count, 3)
                self.assertEqual(send.call_args.args[0], [])
                self.assertIn('test:R102', watcher.load_state()['available_keys'])

if __name__ == '__main__':
    unittest.main()
