import unittest
from unittest.mock import patch

from tests.base import load_compiled_monitor
import src.parser as src_parser

compiled_monitor = load_compiled_monitor()


class BaseTestParseTcpInfo:
    def test_parse_tcp_info_all_metrics(self):
        line = " rtt:10.5/5.2 cwnd:10 retrans:1/2 bytes_sent:1000 bytes_received:2000"
        rtt, jitter, cwnd, retrans, bsent, brecv = self.target.parse_tcp_info(line)
        self.assertEqual(rtt, 10.5)
        self.assertEqual(jitter, 5.2)
        self.assertEqual(cwnd, 10)
        self.assertEqual(retrans, 2)
        self.assertEqual(bsent, 1000)
        self.assertEqual(brecv, 2000)

    def test_parse_tcp_info_partial_metrics(self):
        line = " rtt:10.5/5.2 cwnd:10"
        rtt, jitter, cwnd, retrans, bsent, brecv = self.target.parse_tcp_info(line)
        self.assertEqual(rtt, 10.5)
        self.assertEqual(jitter, 5.2)
        self.assertEqual(cwnd, 10)
        self.assertIsNone(retrans)
        self.assertIsNone(bsent)
        self.assertIsNone(brecv)

    def test_parse_tcp_info_no_metrics(self):
        line = " some random string without metrics"
        rtt, jitter, cwnd, retrans, bsent, brecv = self.target.parse_tcp_info(line)
        self.assertIsNone(rtt)
        self.assertIsNone(jitter)
        self.assertIsNone(cwnd)
        self.assertIsNone(retrans)
        self.assertIsNone(bsent)
        self.assertIsNone(brecv)

    def test_parse_tcp_info_integer_rtt(self):
        line = " rtt:10/5 cwnd:10"
        rtt, jitter, cwnd, retrans, bsent, brecv = self.target.parse_tcp_info(line)
        self.assertEqual(rtt, 10.0)
        self.assertEqual(jitter, 5.0)

    def test_parse_tcp_info_malformed_rtt(self):
        line = " rtt:10.5/ cwnd:10" # missing jitter
        rtt, jitter, cwnd, retrans, bsent, brecv = self.target.parse_tcp_info(line)
        self.assertIsNone(rtt)
        self.assertIsNone(jitter)
        self.assertEqual(cwnd, 10)


class TestParseTcpInfoSrc(BaseTestParseTcpInfo, unittest.TestCase):
    def setUp(self):
        self.target = src_parser


class TestParseTcpInfoCompiled(BaseTestParseTcpInfo, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor


class BaseTestParseConnections:
    @patch('subprocess.check_output')
    def test_parse_connections_basic(self, mock_ss):
        mock_ss.return_value = """Netid State Recv-Q Send-Q Local Address:Port Peer Address:Port Process
tcp ESTAB 0 0 192.168.1.10:12345 1.2.3.4:21117 users:(("rustdesk",pid=1234,fd=5))
 tcp-info: rtt:10.5/5.2 cwnd:10 bytes_sent:1000 bytes_received:2000
"""
        conns = self.target.parse_connections("rustdesk", "21118")
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
        conns = self.target.parse_connections("rustdesk", "21118")
        self.assertEqual(len(conns), 1)
        self.assertEqual(conns[0]['pid'], '')

class TestParseConnectionsSrc(BaseTestParseConnections, unittest.TestCase):
    def setUp(self):
        self.target = src_parser

class TestParseConnectionsCompiled(BaseTestParseConnections, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor


class BaseTestExtractPort:
    def test_extract_port_ipv4(self):
        self.assertEqual(self.target.extract_port("192.168.1.1:12345"), "12345")
        self.assertEqual(self.target.extract_port("0.0.0.0:21118"), "21118")
        self.assertEqual(self.target.extract_port("127.0.0.1:80"), "80")

    def test_extract_port_ipv6(self):
        self.assertEqual(self.target.extract_port("[fe80::1]:8080"), "8080")
        self.assertEqual(self.target.extract_port("[::1]:443"), "443")
        self.assertEqual(self.target.extract_port("[2001:db8:85a3::8a2e:370:7334]:22"), "22")
        self.assertEqual(self.target.extract_port("::1:8080"), "8080")

    def test_extract_port_wildcards(self):
        self.assertEqual(self.target.extract_port("*:*"), "*")
        self.assertEqual(self.target.extract_port("127.0.0.1:*"), "*")
        self.assertEqual(self.target.extract_port("[::1]:*"), "*")
        self.assertEqual(self.target.extract_port("*"), "")

    def test_extract_port_no_port(self):
        self.assertEqual(self.target.extract_port("no_port_here"), "")
        self.assertEqual(self.target.extract_port("192.168.1.1"), "")
        self.assertEqual(self.target.extract_port("localhost"), "")

    def test_extract_port_edge_cases(self):
        self.assertEqual(self.target.extract_port(""), "")
        self.assertEqual(self.target.extract_port(":"), "")
        self.assertEqual(self.target.extract_port("127.0.0.1:"), "")
        self.assertEqual(self.target.extract_port("malformed:string:with:many:colons:1234"), "1234")


class TestExtractPortSrc(BaseTestExtractPort, unittest.TestCase):
    def setUp(self):
        self.target = src_parser

class TestExtractPortCompiled(BaseTestExtractPort, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor
