import unittest

from tests.base import load_compiled_monitor
import src.ui as src_ui

compiled_monitor = load_compiled_monitor()

class BaseTestRenderSparkline:
    def test_render_sparkline_empty(self):
        self.assertEqual(self.target.render_sparkline([]), "")

    def test_render_sparkline_single(self):
        self.assertEqual(self.target.render_sparkline([10]), "▁")

    def test_render_sparkline_flat(self):
        self.assertEqual(self.target.render_sparkline([10, 10, 10]), "▁▁▁")

    def test_render_sparkline_truncation(self):
        self.assertEqual(len(self.target.render_sparkline([1]*12)), 10)

    def test_render_sparkline_custom_width(self):
        self.assertEqual(len(self.target.render_sparkline([1]*12, width=5)), 5)

    def test_render_sparkline_ascending(self):
        vals = [0, 1, 2, 3, 4, 5, 6, 7]
        self.assertEqual(self.target.render_sparkline(vals), "▁▂▃▄▅▆▇█")

    def test_render_sparkline_descending(self):
        vals = [7, 6, 5, 4, 3, 2, 1, 0]
        self.assertEqual(self.target.render_sparkline(vals), "█▇▆▅▄▃▂▁")

    def test_render_sparkline_mixed(self):
        vals = [0, 7, 0, 7]
        self.assertEqual(self.target.render_sparkline(vals), "▁█▁█")

    def test_render_sparkline_floats(self):
        vals = [0.0, 3.5, 7.0]
        self.assertEqual(self.target.render_sparkline(vals), "▁▄█")

class TestRenderSparklineSrc(BaseTestRenderSparkline, unittest.TestCase):
    def setUp(self):
        self.target = src_ui

class TestRenderSparklineCompiled(BaseTestRenderSparkline, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor


class BaseTestAnsiFunctions:
    def test_ansi_len(self):
        self.assertEqual(self.target.ansi_len("hello"), 5)
        self.assertEqual(self.target.ansi_len("\033[1mhello\033[0m"), 5)
        self.assertEqual(self.target.ansi_len("\033[38;5;84m●\033[0m"), 1)
        self.assertEqual(self.target.ansi_len(""), 0)
        self.assertEqual(self.target.ansi_len("\033[48;5;236m\033[38;5;75m RustDesk \033[0m"), 10)
        self.assertEqual(self.target.ansi_len("\033[1m\033[31m\033[42mmulti-ansi\033[0m"), 10)
        self.assertEqual(self.target.ansi_len("\033[m"), 0)
        self.assertEqual(self.target.ansi_len("\033[31m"), 0)
        self.assertEqual(self.target.ansi_len("\033[38;2;255;0;0mRGB text\033[0m"), 8)
        self.assertEqual(self.target.ansi_len("text \033[31;1;4mwith\033[0m codes"), 15)
        self.assertEqual(self.target.ansi_len("\033[31partial"), 11)
        self.assertEqual(self.target.ansi_len("hello\033["), 7)

    def test_ansi_center(self):
        self.assertEqual(self.target.ansi_center("abc", 7), "  abc  ")
        self.assertEqual(self.target.ansi_center("abcd", 7), " abcd  ")
        self.assertEqual(self.target.ansi_center("abcde", 5), "abcde")
        self.assertEqual(self.target.ansi_center("abcdef", 5), "abcdef")

        ansi_str = "\033[1mhello\033[0m"
        centered = self.target.ansi_center(ansi_str, 9)
        self.assertEqual(self.target.ansi_len(centered), 9)
        self.assertEqual(centered, "  " + ansi_str + "  ")

        ansi_str_2 = "\033[38;5;84m●\033[0m"
        centered_2 = self.target.ansi_center(ansi_str_2, 3)
        self.assertEqual(self.target.ansi_len(centered_2), 3)
        self.assertEqual(centered_2, " " + ansi_str_2 + " ")

        self.assertEqual(self.target.ansi_center("", 4), "    ")
        self.assertEqual(self.target.ansi_center("", 0), "")

    def test_ansi_ljust(self):
        self.assertEqual(self.target.ansi_ljust("abc", 5), "abc  ")
        self.assertEqual(self.target.ansi_ljust("abcde", 5), "abcde")
        self.assertEqual(self.target.ansi_ljust("abcdef", 5), "abcdef")

        ansi_str = "\033[1mhello\033[0m"
        ljusted = self.target.ansi_ljust(ansi_str, 8)
        self.assertEqual(self.target.ansi_len(ljusted), 8)
        self.assertEqual(ljusted, ansi_str + "   ")

        ansi_str_2 = "\033[38;5;84m●\033[0m"
        ljusted_2 = self.target.ansi_ljust(ansi_str_2, 3)
        self.assertEqual(self.target.ansi_len(ljusted_2), 3)
        self.assertEqual(ljusted_2, ansi_str_2 + "  ")

        self.assertEqual(self.target.ansi_ljust("", 4), "    ")
        self.assertEqual(self.target.ansi_ljust("", 0), "")

class TestAnsiFunctionsSrc(BaseTestAnsiFunctions, unittest.TestCase):
    def setUp(self):
        self.target = src_ui

class TestAnsiFunctionsCompiled(BaseTestAnsiFunctions, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor


class BaseTestFmtUtils:
    def test_fmt_duration(self):
        self.assertEqual(self.target.fmt_duration(0), "0s")
        self.assertEqual(self.target.fmt_duration(45), "45s")
        self.assertEqual(self.target.fmt_duration(60), "1m0s")
        self.assertEqual(self.target.fmt_duration(65), "1m5s")
        self.assertEqual(self.target.fmt_duration(3600), "1h0m")
        self.assertEqual(self.target.fmt_duration(3665), "1h1m")
        self.assertEqual(self.target.fmt_duration(7325), "2h2m")

    def test_fmt_rate(self):
        self.assertEqual(self.target.fmt_rate(None), "—")
        self.assertEqual(self.target.fmt_rate(0), "0B")
        self.assertEqual(self.target.fmt_rate(1), "1B")
        self.assertEqual(self.target.fmt_rate(500), "500B")
        self.assertEqual(self.target.fmt_rate(1023), "1023B")
        self.assertEqual(self.target.fmt_rate(1024), "1.0K")
        self.assertEqual(self.target.fmt_rate(1536), "1.5K")
        self.assertEqual(self.target.fmt_rate(1048575), "1024.0K")
        self.assertEqual(self.target.fmt_rate(1048576), "1.0M")
        self.assertEqual(self.target.fmt_rate(1572864), "1.5M")
        self.assertEqual(self.target.fmt_rate(1024 * 1024 * 1024), "1024.0M")
        self.assertEqual(self.target.fmt_rate(500.5), "500B")
        self.assertEqual(self.target.fmt_rate(1024.0), "1.0K")
        self.assertEqual(self.target.fmt_rate(-100), "-100B")

class TestFmtUtilsSrc(BaseTestFmtUtils, unittest.TestCase):
    def setUp(self):
        self.target = src_ui

class TestFmtUtilsCompiled(BaseTestFmtUtils, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor


class BaseTestTruncFunction:
    def test_trunc_empty_or_small_width(self):
        self.assertEqual(self.target.trunc("hello", 0), "")
        self.assertEqual(self.target.trunc("hello", 1), "")

    def test_trunc_fits_within_width(self):
        self.assertEqual(self.target.trunc("hello", 6), "hello")
        self.assertEqual(self.target.trunc("hello", 10), "hello")

    def test_trunc_short_max_width_no_ellipsis(self):
        self.assertEqual(self.target.trunc("1234567890", 5), "1234")
        self.assertEqual(self.target.trunc("1234567890", 10), "123456789")

    def test_trunc_long_width_with_ellipsis(self):
        self.assertEqual(self.target.trunc("abcdefghijklmnopqrst", 11), "abc...qrst")
        self.assertEqual(self.target.trunc("abcdefghijklmnopqrst", 12), "abcd...qrst")
        self.assertEqual(self.target.trunc("12345678901", 11), "123...8901")

class TestTruncFunctionSrc(BaseTestTruncFunction, unittest.TestCase):
    def setUp(self):
        self.target = src_ui

class TestTruncFunctionCompiled(BaseTestTruncFunction, unittest.TestCase):
    def setUp(self):
        self.target = compiled_monitor
