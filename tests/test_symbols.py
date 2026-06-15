from __future__ import annotations

import unittest
from unittest.mock import patch

import pandas as pd

from quantmind.utils import symbols
from quantmind.utils.symbols import resolve_symbol


class SymbolResolveTest(unittest.TestCase):
    def test_resolves_a_share_alias(self) -> None:
        resolved = resolve_symbol("贵州茅台")
        self.assertEqual(resolved.symbol, "600519")
        self.assertEqual(resolved.market, "A_SHARE")

    def test_resolves_yili_and_gree_aliases(self) -> None:
        yili = resolve_symbol("伊利股份")
        self.assertEqual(yili.symbol, "600887")
        self.assertEqual(yili.display_name, "伊利股份")
        self.assertEqual(yili.market, "A_SHARE")

        gree = resolve_symbol("格力电器")
        self.assertEqual(gree.symbol, "000651")
        self.assertEqual(gree.display_name, "格力电器")
        self.assertEqual(gree.market, "A_SHARE")

    def test_resolves_a_share_name_from_akshare_list(self) -> None:
        symbols._load_a_share_aliases_from_akshare.cache_clear()
        df = pd.DataFrame({"code": ["601398"], "name": ["工商银行"]})
        fake_ak = type("FakeAkShare", (), {"stock_info_a_code_name": staticmethod(lambda: df)})

        with patch.dict("sys.modules", {"akshare": fake_ak}):
            resolved = resolve_symbol("工商银行")

        self.assertEqual(resolved.symbol, "601398")
        self.assertEqual(resolved.display_name, "工商银行")
        self.assertEqual(resolved.market, "A_SHARE")
        self.assertEqual(resolved.input_type, "a_share_name")
        symbols._load_a_share_aliases_from_akshare.cache_clear()

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
        with patch("quantmind.utils.symbols._resolve_a_share_name_from_akshare", return_value=None), self.assertRaises(ValueError):
            resolve_symbol("暂未收录公司")


if __name__ == "__main__":
    unittest.main()