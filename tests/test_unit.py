"""单元测试：安全计算器与文件工具的安全边界。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from safe_calc import CalculationError, safe_calculate
from tools import (
    _is_sensitive,
    _resolve_in_project,
    edit_file,
    read_file,
    write_file,
)


class TestSafeCalculator(unittest.TestCase):
    def test_basic_arithmetic(self):
        self.assertEqual(safe_calculate("123*456"), "56088")
        self.assertEqual(safe_calculate("(1+2)*3"), "9")
        self.assertEqual(safe_calculate("2**10"), "1024")
        self.assertEqual(safe_calculate("10/4"), "2.5")

    def test_negative_and_float(self):
        self.assertEqual(safe_calculate("-5 + 2"), "-3")
        self.assertAlmostEqual(float(safe_calculate("1.5*2")), 3.0)

    def test_division_by_zero_rejected(self):
        with self.assertRaises(CalculationError):
            safe_calculate("1/0")

    def test_sandbox_escape_rejected(self):
        for expression in (
            "().__class__",
            "().__class__.__bases__[0]",
            "open('/etc/passwd')",
            "__import__('os')",
            "lambda: 1",
        ):
            with self.assertRaises(CalculationError):
                safe_calculate(expression)

    def test_huge_power_rejected(self):
        with self.assertRaises(CalculationError):
            safe_calculate("9**9**9**9")

    def test_too_long_expression_rejected(self):
        with self.assertRaises(CalculationError):
            safe_calculate("1+" * 150)


class TestFileToolSafety(unittest.TestCase):
    def test_path_traversal_blocked(self):
        self.assertIsNone(_resolve_in_project("../outside.txt"))
        self.assertIsNone(_resolve_in_project("../../Windows/win.ini"))

    def test_sibling_directory_prefix_blocked(self):
        # 旧代码用 startswith 判断，兄弟目录可以绕过；现在必须被拒绝
        self.assertIsNone(_resolve_in_project("../simple_rag_evil/x.py"))

    def test_sensitive_files_blocked(self):
        for path in (
            ".env",
            ".env.production",
            "ai_agent.db",
            ".git/config",
            "server.key",
        ):
            resolved = _resolve_in_project(path)
            if resolved is not None:
                self.assertTrue(_is_sensitive(resolved), path)

    def test_read_missing_file_graceful(self):
        result = read_file("does_not_exist_xyz.py")
        self.assertIn("文件不存在", result)

    def test_edit_file_unique_match_required(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target = os.path.join(project_root, "_tmp_edit_test.txt")
        try:
            with open(target, "w", encoding="utf-8") as f:
                f.write("hello hello\n")
            result = edit_file(
                "_tmp_edit_test.txt", "hello", "world"
            )
            self.assertIn("出现了 2 次", result)
        finally:
            if os.path.exists(target):
                os.remove(target)

    def test_write_and_read_roundtrip(self):
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        target = os.path.join(project_root, "_tmp_write_test.txt")
        try:
            result = write_file("_tmp_write_test.txt", "content-abc")
            self.assertIn("成功", result)
            self.assertEqual(
                read_file("_tmp_write_test.txt"), "content-abc"
            )
        finally:
            if os.path.exists(target):
                os.remove(target)


if __name__ == "__main__":
    unittest.main()
