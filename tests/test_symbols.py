from __future__ import annotations

import unittest

from quantmind.utils.symbols import resolve_symbol


class SymbolResolveTest(unittest.TestCase):
    def test_resolves_a_share_alias(self) -> None:
        resolved = resolve_symbol("贵州茅台")
        self.assertEqual(resolved.symbol, "600519")
        self.assertEqual(resolved.market, "A_SHARE")

    def test_resolves_a_share_code(self) -> None:
        resolved = resolve_symbol("600519.SH")
        self.assertEqual(resolved.symbol, "600519")
        self.assertEqual(resolved.display_name, "贵州茅台")
        self.assertEqual(resolved.input_type, "a_share_code")

    def test_resolves_us_ticker(self) -> None:
        resolved = resolve_symbol("aapl")
        self.assertEqual(resolved.symbol, "AAPL")
        self.assertEqual(resolved.market, "US")

    def test_rejects_unknown_chinese_name(self) -> None:
        with self.assertRaises(ValueError):
            resolve_symbol("暂未收录公司")


if __name__ == "__main__":
    unittest.main()