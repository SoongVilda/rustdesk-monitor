# Unit tests for rustdesk-monitor.py
import unittest
from unittest.mock import patch, mock_open
import importlib.util
import sys
import os
import re

# Import the script as a module
module_name = "rustdesk_monitor"
file_path = "rustdesk-monitor.py"
spec = importlib.util.spec_from_file_location(module_name, file_path)
monitor = importlib.util.module_from_spec(spec)
sys.modules[module_name] = monitor
spec.loader.exec_module(monitor)

class TestParseTcpInfo(unittest.TestCase):
    def test_parse_tcp_info_all_metrics(self):
        line = " rtt:10.5/5.2 cwnd:10 retrans:1/2 bytes_sent:1000 bytes_received:2000"
        rtt, jitter, cwnd, retrans, bsent, brecv = monitor.parse_tcp_info(line)
        self.assertEqual(rtt, 10.5)
        self.assertEqual(jitter, 5.2)
        self.assertEqual(cwnd, 10)
        self.assertEqual(retrans, 2)
        self.assertEqual(bsent, 1000)
        self.assertEqual(brecv, 2000)

    def test_parse_tcp_info_partial_metrics(self):
        line = " rtt:10.5/5.2 cwnd:10"
        rtt, jitter, cwnd, retrans, bsent, brecv = monitor.parse_tcp_info(line)
        self.assertEqual(rtt, 10.5)
        self.assertEqual(jitter, 5.2)
        self.assertEqual(cwnd, 10)
        self.assertIsNone(retrans)
        self.assertIsNone(bsent)
        self.assertIsNone(brecv)

    def test_parse_tcp_info_no_metrics(self):
        line = " some random string without metrics"
        rtt, jitter, cwnd, retrans, bsent, brecv = monitor.parse_tcp_info(line)
        self.assertIsNone(rtt)
        self.assertIsNone(jitter)
        self.assertIsNone(cwnd)
        self.assertIsNone(retrans)
        self.assertIsNone(bsent)
        self.assertIsNone(brecv)

    def test_parse_tcp_info_integer_rtt(self):
        line = " rtt:10/5 cwnd:10"
        rtt, jitter, cwnd, retrans, bsent, brecv = monitor.parse_tcp_info(line)
        self.assertEqual(rtt, 10.0)
        self.assertEqual(jitter, 5.0)

    def test_parse_tcp_info_malformed_rtt(self):
        line = " rtt:10.5/ cwnd:10" # missing jitter
        rtt, jitter, cwnd, retrans, bsent, brecv = monitor.parse_tcp_info(line)
        self.assertIsNone(rtt)
        self.assertIsNone(jitter)
        self.assertEqual(cwnd, 10)


class TestRenderSparkline(unittest.TestCase):
    def test_render_sparkline_empty(self):
        self.assertEqual(monitor.render_sparkline([]), "")

    def test_render_sparkline_single(self):
        self.assertEqual(monitor.render_sparkline([10]), "▁")

    def test_render_sparkline_flat(self):
        self.assertEqual(monitor.render_sparkline([10, 10, 10]), "▁▁▁")

    def test_render_sparkline_truncation(self):
        # 12 elements, default width is 10, so it should only take last 10
        self.assertEqual(len(monitor.render_sparkline([1]*12)), 10)

    def test_render_sparkline_custom_width(self):
        self.assertEqual(len(monitor.render_sparkline([1]*12, width=5)), 5)

    def test_render_sparkline_ascending(self):
        # 8 characters in SPARK_CHARS: "▁▂▃▄▅▆▇█"
        vals = [0, 1, 2, 3, 4, 5, 6, 7]
        self.assertEqual(monitor.render_sparkline(vals), "▁▂▃▄▅▆▇█")

    def test_render_sparkline_descending(self):
        vals = [7, 6, 5, 4, 3, 2, 1, 0]
        self.assertEqual(monitor.render_sparkline(vals), "█▇▆▅▄▃▂▁")

    def test_render_sparkline_mixed(self):
        vals = [0, 7, 0, 7]
        self.assertEqual(monitor.render_sparkline(vals), "▁█▁█")

    def test_render_sparkline_floats(self):
        vals = [0.0, 3.5, 7.0]
        self.assertEqual(monitor.render_sparkline(vals), "▁▄█")

class TestAnsiFunctions(unittest.TestCase):
    def test_ansi_len(self):
        # Basic cases
        self.assertEqual(monitor.ansi_len("hello"), 5)
        self.assertEqual(monitor.ansi_len("\033[1mhello\033[0m"), 5)
        self.assertEqual(monitor.ansi_len("\033[38;5;84m●\033[0m"), 1)
        self.assertEqual(monitor.ansi_len(""), 0)
        self.assertEqual(monitor.ansi_len("\033[48;5;236m\033[38;5;75m RustDesk \033[0m"), 10)

        # Edge cases and complex codes
        self.assertEqual(monitor.ansi_len("\033[1m\033[31m\033[42mmulti-ansi\033[0m"), 10)
        self.assertEqual(monitor.ansi_len("\033[m"), 0) # empty ansi code
        self.assertEqual(monitor.ansi_len("\033[31m"), 0) # only ansi code
        self.assertEqual(monitor.ansi_len("\033[38;2;255;0;0mRGB text\033[0m"), 8) # true color ansi
        self.assertEqual(monitor.ansi_len("text \033[31;1;4mwith\033[0m codes"), 15) # interlaced

        # Invalid/partial ansi codes (regex should ignore them if they don't end in 'm')
        self.assertEqual(monitor.ansi_len("\033[31partial"), 11)
        self.assertEqual(monitor.ansi_len("hello\033["), 7)

    def test_ansi_center(self):
        # Plain strings
        self.assertEqual(monitor.ansi_center("abc", 7), "  abc  ")
        self.assertEqual(monitor.ansi_center("abcd", 7), " abcd  ") # pad=3, left=1, right=2
        self.assertEqual(monitor.ansi_center("abcde", 5), "abcde")
        self.assertEqual(monitor.ansi_center("abcdef", 5), "abcdef") # width < len

        # ANSI strings
        ansi_str = "\033[1mhello\033[0m"
        centered = monitor.ansi_center(ansi_str, 9)
        self.assertEqual(monitor.ansi_len(centered), 9)
        self.assertEqual(centered, "  " + ansi_str + "  ")

        ansi_str_2 = "\033[38;5;84m●\033[0m" # len 1
        centered_2 = monitor.ansi_center(ansi_str_2, 3)
        self.assertEqual(monitor.ansi_len(centered_2), 3)
        self.assertEqual(centered_2, " " + ansi_str_2 + " ")

        # Empty string
        self.assertEqual(monitor.ansi_center("", 4), "    ")
        self.assertEqual(monitor.ansi_center("", 0), "")

    def test_ansi_ljust(self):
        # Plain strings
        self.assertEqual(monitor.ansi_ljust("abc", 5), "abc  ")
        self.assertEqual(monitor.ansi_ljust("abcde", 5), "abcde")
        self.assertEqual(monitor.ansi_ljust("abcdef", 5), "abcdef") # width < len

        # ANSI strings
        ansi_str = "\033[1mhello\033[0m"
        ljusted = monitor.ansi_ljust(ansi_str, 8)
        self.assertEqual(monitor.ansi_len(ljusted), 8)
        self.assertEqual(ljusted, ansi_str + "   ")

        ansi_str_2 = "\033[38;5;84m●\033[0m" # len 1
        ljusted_2 = monitor.ansi_ljust(ansi_str_2, 3)
        self.assertEqual(monitor.ansi_len(ljusted_2), 3)
        self.assertEqual(ljusted_2, ansi_str_2 + "  ")

        # Empty string
        self.assertEqual(monitor.ansi_ljust("", 4), "    ")
        self.assertEqual(monitor.ansi_ljust("", 0), "")

class TestParseConnections(unittest.TestCase):
    @patch('subprocess.check_output')
    def test_parse_connections_basic(self, mock_ss):
        mock_ss.return_value = """Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
tcp ESTAB 0 0 192.168.1.10:12345 1.2.3.4:21117 users:(("rustdesk",pid=1234,fd=5))
 tcp-info: rtt:10.5/5.2 cwnd:10 bytes_sent:1000 bytes_received:2000
"""
        conns = monitor.parse_connections("rustdesk", "21118")
        self.assertEqual(len(conns), 1)
        c = conns[0]
        self.assertEqual(c['pid'], '1234')
        self.assertEqual(c['pname'], 'rustdesk')
        self.assertEqual(c['type'], 'Relay (Indirect Routing)')

    @patch('subprocess.check_output')
    def test_parse_connections_malformed_proc_blob(self, mock_ss):
        mock_ss.return_value = """Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
tcp ESTAB 0 0 192.168.1.10:12345 1.2.3.4:21117 rustdesk pid=
"""
        conns = monitor.parse_connections("rustdesk", "21118")
        self.assertEqual(len(conns), 1)
        self.assertEqual(conns[0]['pid'], '')

class TestConfigLoading(unittest.TestCase):
    @patch('os.path.isfile')
    @patch('builtins.open', new_callable=mock_open, read_data='nat_type = 1\nrendezvous_server = "test.server.com"\n[options]\ndirect-access-port = 12345')
    def test_read_rustdesk_config_valid(self, mock_file, mock_isfile):
        mock_isfile.return_value = True
        cfg = monitor.read_rustdesk_config()
        self.assertEqual(cfg['nat_type'], 1)
        self.assertEqual(cfg['rendezvous_server'], 'test.server.com')
        self.assertEqual(cfg['direct_port'], '12345')

    @patch('os.path.isfile')
    def test_read_rustdesk_config_missing(self, mock_isfile):
        mock_isfile.return_value = False
        cfg = monitor.read_rustdesk_config()
        self.assertEqual(cfg['direct_port'], '21118')

    @patch('os.path.isfile')
    @patch('builtins.open', side_effect=OSError("Permission denied"))
    def test_read_rustdesk_config_oserror(self, mock_file, mock_isfile):
        mock_isfile.return_value = True
        cfg = monitor.read_rustdesk_config()
        self.assertEqual(cfg['direct_port'], '21118')

class TestHealthAndAlerts(unittest.TestCase):
    def test_compute_health(self):
        # Listen direction
        self.assertEqual(monitor.compute_health({'dir': 'LSTN'}), '—')

        # Missing RTT
        self.assertEqual(monitor.compute_health({'dir': 'IN', 'rtt': None}), '?')

        # Grade A: rtt < 20, jitter < 5, retrans == 0, queue == 0
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'A')

        # Grade B: rtt < 50, retrans <= 2
        self.assertEqual(monitor.compute_health({
            'dir': 'IN', 'rtt': 45, 'jitter': 10, 'retrans': 1, 'rx': '10', 'tx': '0'
        }), 'B')

        # Grade C: rtt < 100
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 95, 'jitter': 5, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'C')

        # Grade D: rtt < 200
        self.assertEqual(monitor.compute_health({
            'dir': 'IN', 'rtt': 150, 'jitter': 15, 'retrans': 5, 'rx': '0', 'tx': '0'
        }), 'D')

        # Grade F: rtt >= 200
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 250, 'jitter': 20, 'retrans': 10, 'rx': '0', 'tx': '0'
        }), 'F')

    def test_compute_health_edge_cases(self):
        # Grade A boundary checks (needs rtt < 20, jitter < 5, retrans == 0, queue == 0)
        # Fail rtt bound (rtt=20)
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 20, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'B')
        # Fail jitter bound (jitter=5)
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 5, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'B')
        # Fail queue bound (q > 0)
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': '1', 'tx': '0'
        }), 'B')

        # Grade B boundary checks (needs rtt < 50, retrans <= 2)
        # Fail rtt bound (rtt=50)
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 50, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'C')
        # Fail retrans bound (retrans=3)
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 45, 'jitter': 2, 'retrans': 3, 'rx': '0', 'tx': '0'
        }), 'C')

        # Grade C boundary checks (needs rtt < 100)
        # Fail rtt bound (rtt=100)
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 100, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'D')

        # Grade D boundary checks (needs rtt < 200)
        # Fail rtt bound (rtt=200)
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 200, 'jitter': 2, 'retrans': 0, 'rx': '0', 'tx': '0'
        }), 'F')

    def test_compute_health_exception_handling(self):
        # Trigger ValueError due to invalid string for int() conversion
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': 'invalid', 'tx': '0'
        }), 'A')

        # Trigger TypeError due to passing None for int() conversion
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': None, 'tx': '0'
        }), 'A')

        # Both invalid
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0, 'rx': None, 'tx': 'invalid'
        }), 'A')

        # Missing rx and tx (defaults to 0,0 in the get)
        self.assertEqual(monitor.compute_health({
            'dir': 'OUT', 'rtt': 15, 'jitter': 2, 'retrans': 0
        }), 'A')

    def test_detect_alerts(self):
        # Empty case
        self.assertEqual(monitor.detect_alerts([]), [])

        # Mixed alerts
        conns = [
            {'type': 'Relay', 'dir': 'IN', 'rtt': 15},
            {'type': 'Relay', 'dir': 'OUT', 'rtt': 250},
            {'type': 'Direct', 'dir': 'IN', 'rtt': 45, 'retrans': 6},
            {'type': 'Direct', 'dir': 'OUT', 'rtt': 15, 'rx': '100', 'tx': '50'}
        ]

        alerts = monitor.detect_alerts(conns)
        self.assertEqual(len(alerts), 4)
        self.assertTrue(any('2 relay connection(s)' in a for a in alerts))
        self.assertTrue(any('1 connection(s) with RTT >200ms' in a for a in alerts))
        self.assertTrue(any('1 connection(s) with retransmissions' in a for a in alerts))
        self.assertTrue(any('1 connection(s) with queued data' in a for a in alerts))

    def test_detect_alerts_edge_cases(self):
        conns = [
            # Relay but LSTN (should not trigger relay alert)
            {'type': 'Relay', 'dir': 'LSTN'},
            # RTT exactly 200 (should not trigger RTT alert)
            {'type': 'Direct', 'dir': 'OUT', 'rtt': 200},
            # Retrans exactly 5 (should not trigger retrans alert)
            {'type': 'Direct', 'dir': 'OUT', 'retrans': 5},
            # Rx/Tx exactly 0 (should not trigger queued data alert)
            {'type': 'Direct', 'dir': 'OUT', 'rx': '0', 'tx': '0'},
        ]
        alerts = monitor.detect_alerts(conns)
        self.assertEqual(len(alerts), 0)

    def test_detect_alerts_malformed_data(self):
        conns = [
            # Invalid rx/tx that cause ValueError
            {'type': 'Direct', 'dir': 'IN', 'rx': 'invalid', 'tx': 'invalid'},
            # Invalid rx/tx that cause TypeError
            {'type': 'Direct', 'dir': 'IN', 'rx': None, 'tx': None},
        ]
        alerts = monitor.detect_alerts(conns)
        # Should not crash and not trigger queued data alerts
        self.assertEqual(len(alerts), 0)

class TestUtilityFunctions(unittest.TestCase):
    def test_extract_port(self):
        self.assertEqual(monitor.extract_port("192.168.1.1:12345"), "12345")
        self.assertEqual(monitor.extract_port("[fe80::1]:8080"), "8080")
        self.assertEqual(monitor.extract_port("*:*"), "*")
        self.assertEqual(monitor.extract_port("127.0.0.1:*"), "*")
        self.assertEqual(monitor.extract_port("no_port_here"), "")
        self.assertEqual(monitor.extract_port("0.0.0.0:21118"), "21118")

    def test_fmt_duration(self):
        self.assertEqual(monitor.fmt_duration(0), "0s")
        self.assertEqual(monitor.fmt_duration(45), "45s")
        self.assertEqual(monitor.fmt_duration(60), "1m0s")
        self.assertEqual(monitor.fmt_duration(65), "1m5s")
        self.assertEqual(monitor.fmt_duration(3600), "1h0m")
        self.assertEqual(monitor.fmt_duration(3665), "1h1m")
        self.assertEqual(monitor.fmt_duration(7325), "2h2m")

    def test_fmt_rate(self):
        # None case
        self.assertEqual(monitor.fmt_rate(None), "—")

        # Bytes cases
        self.assertEqual(monitor.fmt_rate(0), "0B")
        self.assertEqual(monitor.fmt_rate(1), "1B")
        self.assertEqual(monitor.fmt_rate(500), "500B")
        self.assertEqual(monitor.fmt_rate(1023), "1023B")

        # Kilobytes cases
        self.assertEqual(monitor.fmt_rate(1024), "1.0K")
        self.assertEqual(monitor.fmt_rate(1536), "1.5K")
        self.assertEqual(monitor.fmt_rate(1048575), "1024.0K")

        # Megabytes cases
        self.assertEqual(monitor.fmt_rate(1048576), "1.0M")
        self.assertEqual(monitor.fmt_rate(1572864), "1.5M")
        self.assertEqual(monitor.fmt_rate(1024 * 1024 * 1024), "1024.0M") # 1GB

        # Float inputs
        self.assertEqual(monitor.fmt_rate(500.5), "500B") # 500.5 rounds to 500 in python string format with .0f due to banker's rounding
        self.assertEqual(monitor.fmt_rate(1024.0), "1.0K")

        # Negative cases (edge case, shouldn't really happen but code allows it)
        self.assertEqual(monitor.fmt_rate(-100), "-100B")

if __name__ == "__main__":
    unittest.main()
