import unittest
from unittest.mock import patch, mock_open

from tests.base import load_compiled_monitor
import src.config as src_config

compiled_monitor = load_compiled_monitor()

class BaseTestConfigLoading:
    @patch('os.path.isfile')
    @patch('builtins.open', new_callable=mock_open, read_data='nat_type = 1\nrendezvous_server = "test.server.com"\n[options]\ndirect-access-port = 12345')
    def test_read_rustdesk_config_valid(self, mock_file, mock_isfile):
        mock_isfile.return_value = True
        cfg = self.target.read_rustdesk_config()
        self.assertEqual(cfg['nat_type'], 1)
        self.assertEqual(cfg['rendezvous_server'], 'test.server.com')
        self.assertEqual(cfg['direct_port'], '12345')

    @patch('os.path.isfile')
    @patch('builtins.open', new_callable=mock_open, read_data="nat_type = 1\nrendezvous_server = 'test.server.com'\n[options]\ndirect-access-port = '12345'")
    def test_read_rustdesk_config_single_quotes(self, mock_file, mock_isfile):
        mock_isfile.return_value = True
        cfg = self.target.read_rustdesk_config()
        self.assertEqual(cfg['nat_type'], 1)
        self.assertEqual(cfg['rendezvous_server'], 'test.server.com')
        self.assertEqual(cfg['direct_port'], '12345')

    @patch('os.path.isfile')
    def test_read_rustdesk_config_missing(self, mock_isfile):
        mock_isfile.return_value = False
        cfg = self.target.read_rustdesk_config()
        self.assertEqual(cfg['direct_port'], '21118')

    @patch('os.path.isfile')
    @patch('builtins.open', side_effect=OSError("Permission denied"))
    def test_read_rustdesk_config_oserror(self, mock_file, mock_isfile):
        mock_isfile.return_value = True
        cfg = self.target.read_rustdesk_config()
        self.assertEqual(cfg['direct_port'], '21118')


class TestConfigLoadingSrc(BaseTestConfigLoading, unittest.TestCase):
    def setUp(self):
        self.target = src_config


class TestConfigLoadingCompiled(BaseTestConfigLoading, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor
