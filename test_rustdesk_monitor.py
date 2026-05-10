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

class TestAnsiFunctions(unittest.TestCase):
    def test_ansi_len(self):
        self.assertEqual(monitor.ansi_len("hello"), 5)
        self.assertEqual(monitor.ansi_len("\033[1mhello\033[0m"), 5)
        self.assertEqual(monitor.ansi_len("\033[38;5;84m●\033[0m"), 1)
        self.assertEqual(monitor.ansi_len(""), 0)
        self.assertEqual(monitor.ansi_len("\033[48;5;236m\033[38;5;75m RustDesk \033[0m"), 10)

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

if __name__ == "__main__":
    unittest.main()
