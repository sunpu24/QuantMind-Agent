from __future__ import annotations

import unittest

from quantmind.schemas import AgentState
from quantmind.utils.report import _format_akshare_attempts, render_text_report


class ReportTest(unittest.TestCase):
    def test_format_akshare_attempts(self) -> None:
        result = _format_akshare_attempts(
            [
                {"lookback_days": 60, "status": "failed"},
                {"lookback_days": 30, "status": "success"},
            ]
        )

        self.assertEqual(result, "60天 failed, 30天 success")

    def test_render_text_report_shows_fallback_type_and_attempts(self) -> None:
        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            market_data={
                "source": "akshare_fallback_mock",
                "requested_provider": "akshare",
                "fallback_reason": "AkShare 行情获取失败: proxy unavailable",
                "fallback_type": "proxy_error",
                "akshare_attempts": [
                    {"lookback_days": 60, "status": "failed"},
                    {"lookback_days": 30, "status": "failed"},
                    {"lookback_days": 20, "status": "failed"},
                ],
            },
        )

        report = render_text_report(state)

        self.assertIn("行情数据源: akshare_fallback_mock", report)
        self.assertIn("请求 Provider: akshare", report)
        self.assertIn("回退类型: proxy_error", report)
        self.assertIn("AkShare 尝试: 60天 failed, 30天 failed, 20天 failed", report)
        self.assertIn("未找到可用行情数据", report)
        self.assertIn("最终交易决策为 WAIT", report)
        self.assertNotIn("占位", report)

    def test_render_text_report_shows_warning_for_plain_mock_market_data(self) -> None:
        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            market_data={"source": "mock", "requested_provider": "mock"},
        )

        report = render_text_report(state)

        self.assertIn("未找到可用行情数据", report)

    def test_render_text_report_shows_news_source_metadata(self) -> None:
        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            news_data=[
                {
                    "title": "600519: 公司核心业务保持稳定增长，机构关注度提升",
                    "date": "2024-06-05",
                    "news_source": "alpha_vantage_fallback_mock",
                    "requested_news_provider": "alpha_vantage",
                    "news_fallback_reason": "Alpha Vantage 未返回可用新闻",
                    "news_fallback_type": "empty_data",
                }
            ],
        )

        report = render_text_report(state)

        self.assertIn("新闻数据源: alpha_vantage_fallback_mock", report)
        self.assertIn("请求新闻 Provider: alpha_vantage", report)
        self.assertIn("新闻回退原因: Alpha Vantage 未返回可用新闻", report)
        self.assertIn("新闻回退类型: empty_data", report)

    def test_render_text_report_shows_llm_decision_metadata(self) -> None:
        from quantmind.schemas import TradeAction, TradeDecision

        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            final_decision=TradeDecision(
                action=TradeAction.HOLD,
                confidence=0.7,
                position_size=0.0,
                summary="DeepSeek 建议等待。",
                risk_notes="注意波动。",
                decision_source="deepseek",
                llm_provider="deepseek",
                llm_model="deepseek-chat",
                llm_reasoning="技术偏弱但风险中等，暂不追高。",
                llm_elapsed_ms=1560,
                llm_fallback_type=None,
                llm_prompt_summary="symbol=600519, tech=bearish/40, risk=medium/50",
                llm_response_summary="action=HOLD, confidence=0.7, position_size=0.0",
            ),
        )

        report = render_text_report(state)

        self.assertIn("LLM Provider: deepseek", report)
        self.assertIn("LLM Model: deepseek-chat", report)
        self.assertIn("LLM 耗时: 1560 ms", report)
        self.assertIn("LLM 回退类型: N/A", report)
        self.assertIn("LLM 输入摘要: symbol=600519, tech=bearish/40, risk=medium/50", report)
        self.assertIn("LLM 输出摘要: action=HOLD, confidence=0.7, position_size=0.0", report)
        self.assertIn("动作规则: BUY=买入/加仓", report)
        self.assertIn("交易决策来源: deepseek", report)
        self.assertIn("依据: 技术偏弱但风险中等，暂不追高。", report)

    def test_render_text_report_shows_llm_fallback_audit_metadata(self) -> None:
        from quantmind.schemas import TradeAction, TradeDecision

        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            final_decision=TradeDecision(
                action=TradeAction.BUY,
                confidence=0.74,
                position_size=0.3,
                summary="规则回退建议小仓位参与。",
                risk_notes="风险中等。",
                decision_source="rule_fallback",
                llm_provider="deepseek",
                llm_model="deepseek-chat",
                llm_fallback_reason="DeepSeek 请求超时",
                llm_fallback_type="timeout",
                llm_elapsed_ms=30001,
                llm_prompt_summary="symbol=600519, tech=bullish/78, risk=medium/50",
            ),
        )

        report = render_text_report(state)

        self.assertIn("交易决策来源: rule_fallback", report)
        self.assertIn("LLM 耗时: 30001 ms", report)
        self.assertIn("LLM 回退类型: timeout", report)
        self.assertIn("LLM 输入摘要: symbol=600519, tech=bullish/78, risk=medium/50", report)
        self.assertIn("LLM 输出摘要: N/A", report)
        self.assertIn("LLM 回退原因: DeepSeek 请求超时", report)

    def test_render_text_report_shows_risk_source(self) -> None:
        from quantmind.schemas import RiskLevel, RiskReport

        state = AgentState(
            symbol="600519",
            trade_date="2024-06-05",
            risk_report=RiskReport(
                level=RiskLevel.MEDIUM,
                score=50,
                suggested_position=0.5,
                stop_loss_pct=0.05,
                summary="DeepSeek 解释，规则裁剪仓位。",
                risk_source="deepseek_guardrailed",
            ),
        )

        report = render_text_report(state)

        self.assertIn("风险控制来源: deepseek_guardrailed", report)


if __name__ == "__main__":
    unittest.main()