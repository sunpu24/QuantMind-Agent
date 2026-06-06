from __future__ import annotations

import argparse
import unittest

from main import validate_trade_date


class MainCliTest(unittest.TestCase):
    def test_validate_trade_date_accepts_iso_date(self) -> None:
        self.assertEqual(validate_trade_date("2024-06-05"), "2024-06-05")

    def test_validate_trade_date_rejects_invalid_format(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            validate_trade_date("20240605")


if __name__ == "__main__":
    unittest.main()