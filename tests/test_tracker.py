import unittest
from unittest.mock import patch

from tests.base import load_compiled_monitor
import src.tracker as src_tracker

compiled_monitor = load_compiled_monitor()


class BaseTestHealthAndAlerts:
    def test_tracker_rates_with_missing_counters(self):
        for first_sent, next_sent, first_received, next_received, tx, rx in (
            (100, 200, None, None, 100, None),
            (None, None, 100, 200, None, 100),
            (100, 200, None, 200, 100, None),
            (100, None, 100, 200, None, 100),
            (100, 200, 100, 300, 100, 200),
        ):
            with self.subTest(counters=(first_sent, next_sent, first_received, next_received)):
                tracker = self.target.ConnectionTracker()
                first = {'local': '127.0.0.1:12345', 'peer': '127.0.0.1:21117',
                         'bytes_sent': first_sent, 'bytes_received': first_received}
                second = dict(first, bytes_sent=next_sent, bytes_received=next_received)
                with patch('time.time', side_effect=[100, 101]):
                    tracker.update([first])
                    result = tracker.update([second])[0]
                self.assertEqual(result['tx_rate'], tx)
                self.assertEqual(result['rx_rate'], rx)
                self.assertEqual(result['bytes_received'], next_received)

    def test_compute_health(self):
        self.assertEqual(self.target.compute_health({'dir': 'LSTN'}), '—')
        self.assertEqual(self.target.compute_health({'dir': 'IN', 'rtt': None}), '?')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'A')

        self.assertEqual(self.target.compute_health({
            'dir': 'IN', 'rtt': 45, 'jitter': 10, 'retrans': 1, 'rx': '10', 'tx': '0'
        }), 'B')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 95, 'jitter': 5, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'C')

        self.assertEqual(self.target.compute_health({
            'dir': 'IN', 'rtt': 150, 'jitter': 15, 'retrans': 5, 'rx': '0', 'tx': '0'
        }), 'D')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 250, 'jitter': 20, 'retrans': 10, 'rx': '0', 'tx': '0'
        }), 'F')

    def test_compute_health_edge_cases(self):
        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 20, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'B')
        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 5, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'B')
        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': '1', 'tx': '0'
        }), 'B')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 50, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'C')
        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 45, 'jitter': 2, 'retrans': 3, 'rx': '0', 'tx': '0'
        }), 'C')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 100, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'D')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 200, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'F')

    def test_compute_health_exception_handling(self):
        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': 'invalid', 'tx': '0'
        }), 'A')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': None, 'tx': '0'
        }), 'A')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': None, 'tx': 'invalid'
        }), 'A')

        self.assertEqual(self.target.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0
        }), 'A')

    def test_detect_alerts(self):
        self.assertEqual(self.target.detect_alerts([]), [])

        conns = [
            {'type': 'Relay', 'dir': 'IN', 'rtt': 15},
            {'type': 'Relay', 'dir': 'OUT', 'rtt': 250},
            {'type': 'Direct', 'dir': 'IN', 'rtt': 45, 'retrans': 6},
            {'type': 'Direct', 'dir': 'OUT', 'rtt': 15, 'rx': '100', 'tx': '50'}
        ]

        alerts = self.target.detect_alerts(conns)
        self.assertEqual(len(alerts), 4)
        self.assertTrue(any('2 relay connection(s)' in a for a in alerts))
        self.assertTrue(any('1 connection(s) with RTT >200ms' in a for a in alerts))
        self.assertTrue(any('1 connection(s) with retransmissions' in a for a in alerts))
        self.assertTrue(any('1 connection(s) with queued data' in a for a in alerts))

    def test_detect_alerts_edge_cases(self):
        conns = [
            {'type': 'Relay', 'dir': 'LSTN'},
            {'type': 'Direct', 'dir': 'OUT', 'rtt': 200},
            {'type': 'Direct', 'dir': 'OUT', 'retrans': 5},
            {'type': 'Direct', 'dir': 'OUT', 'rx': '0', 'tx': '0'},
        ]
        alerts = self.target.detect_alerts(conns)
        self.assertEqual(len(alerts), 0)

    def test_detect_alerts_malformed_data(self):
        conns = [
            {'type': 'Direct', 'dir': 'IN', 'rx': 'invalid', 'tx': 'invalid'},
            {'type': 'Direct', 'dir': 'IN', 'rx': None, 'tx': None},
        ]
        alerts = self.target.detect_alerts(conns)
        self.assertEqual(len(alerts), 0)

    def test_listener_backlog_is_not_queued_data(self):
        listener = {'proto': 'tcp', 'state': 'LISTEN', 'type': 'Direct Access (Listening)',
                    'dir': 'LSTN', 'rx': '0', 'tx': '128'}
        self.assertEqual(self.target.detect_alerts([listener]), [])

        established = dict(listener, state='ESTAB', dir='IN', tx='10')
        udp = dict(listener, proto='udp', state='UNCONN', rx='100', tx='0')
        alerts = self.target.detect_alerts([listener, established, udp])
        self.assertEqual(len(alerts), 1)
        self.assertIn('2 connection(s) with queued data', alerts[0])


class TestHealthAndAlertsSrc(BaseTestHealthAndAlerts, unittest.TestCase):
    def setUp(self):
        self.target = src_tracker


class TestHealthAndAlertsCompiled(BaseTestHealthAndAlerts, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor
