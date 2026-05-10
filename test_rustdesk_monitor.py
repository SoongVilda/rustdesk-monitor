# Unit tests for rustdesk-monitor.py
import unittest
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

if __name__ == "__main__":
    unittest.main()
