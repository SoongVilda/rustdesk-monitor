import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import src.main as src_main
from tests.base import load_compiled_monitor

compiled_monitor = load_compiled_monitor()


class BaseTestDashboardLoop:
    def test_run_dashboard_handles_interrupt_during_connection_collection(self):
        args = SimpleNamespace(watch=0.5, process_name="rustdesk")
        log_fh = Mock()

        with patch.object(
            self.target, "collect_connections", side_effect=KeyboardInterrupt
        ):
            with patch("builtins.print") as mock_print:
                self.target.run_dashboard(args, Mock(), "Unknown", "21118", 0.5, log_fh)

        log_fh.close.assert_called_once()
        self.assertTrue(
            any("Exiting" in str(call) for call in mock_print.call_args_list)
        )


class TestDashboardLoopSrc(BaseTestDashboardLoop, unittest.TestCase):
    def setUp(self):
        self.target = src_main


class TestDashboardLoopCompiled(BaseTestDashboardLoop, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor
