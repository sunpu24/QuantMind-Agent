const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const OPTIONAL_ANALYSIS_AGENTS = ["technical", "news", "fundamental", "sentiment"];
const ALWAYS_ON_STEPS = ["resolved", "prepared", "bullish_research", "bearish_research", "research_manager", "risk", "decision"];

function initHome() {
  const form = $("#searchForm");
  if (!form) return;

  const input = $("#stockInput");
  const errorText = $("#errorText");
  const setError = (message) => {
    errorText.textContent = message || "";
  };

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const query = input.value.trim();
    if (!query) {
      setError("请输入股票名称或代码");
      return;
    }

    setError("正在校验股票...");
    try {
      const response = await fetch(`/api/validate?q=${encodeURIComponent(query)}`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        setError(payload.message || "当前仅支持 A 股和美股，输入内容不可查询");
        return;
      }
      const selectedAgents = getSelectedAnalysisAgents();
      const targetParams = new URLSearchParams({ query });
      targetParams.set("agents", selectedAgents.join(","));
      window.location.href = `/analysis?${targetParams.toString()}`;
    } catch (error) {
      setError("网络异常，请稍后重试");
    }
  });

  $$(".examples button").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.query || "";
      input.focus();
    });
  });
}

function getSelectedAnalysisAgents() {
  return $$("input[name='agent']:checked")
    .map((input) => input.value)
    .filter(Boolean);
}

function initAnalysis() {
  const progressBar = $("#progressBar");
  if (!progressBar) return;

  const params = new URLSearchParams(window.location.search);
  const query = params.get("query") || "";
  const selectedAgents = getAnalysisAgentsFromParams(params);
  const title = $("#analysisTitle");
  const statusText = $("#statusText");

  if (!query) {
    title.textContent = "缺少股票输入";
    statusText.textContent = "请返回首页重新输入股票名称或代码。";
    return;
  }

  title.textContent = `正在分析：${query}`;
  updateVisibleSteps(selectedAgents);
  const streamParams = new URLSearchParams({ q: query, agents: selectedAgents.join(",") });
  const source = new EventSource(`/api/analyze/stream?${streamParams.toString()}`);

  source.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    updateProgress(payload);
    if (payload.symbol) {
      title.textContent = `正在分析：${payload.symbol.display_name}（${payload.symbol.symbol}）`;
    }
    if (payload.type === "result") {
      renderResult(payload.data, selectedAgents);
      source.close();
    }
    if (payload.type === "error") {
      statusText.textContent = payload.message;
      source.close();
    }
  };

  source.onerror = () => {
    statusText.textContent = "分析连接中断，请返回首页后重试。";
    source.close();
  };
}

function getAnalysisAgentsFromParams(params) {
  if (!params.has("agents")) return OPTIONAL_ANALYSIS_AGENTS;
  return (params.get("agents") || "")
    .split(",")
    .map((agent) => agent.trim())
    .filter((agent) => OPTIONAL_ANALYSIS_AGENTS.includes(agent));
}

function updateVisibleSteps(selectedAgents) {
  const visibleSteps = new Set([...ALWAYS_ON_STEPS, ...selectedAgents]);
  $$("#steps li").forEach((item) => {
    item.classList.toggle("hidden", !visibleSteps.has(item.dataset.step));
  });
}

function updateProgress(payload) {
  const progressBar = $("#progressBar");
  const statusText = $("#statusText");
  const percent = Math.max(0, Math.min(100, Number(payload.percent || 0)));
  progressBar.style.width = `${percent}%`;
  statusText.textContent = payload.message || "分析中...";

  const order = $$("#steps li:not(.hidden)").map((item) => item.dataset.step);
  const fallbackOrder = [
    "resolved",
    "prepared",
    "technical",
    "news",
    "fundamental",
    "sentiment",
    "bullish_research",
    "bearish_research",
    "research_manager",
    "risk",
    "decision",
  ];
  const currentIndex = order.indexOf(payload.step);
  const fallbackCurrentIndex = fallbackOrder.indexOf(payload.step);
  $$("#steps li:not(.hidden)").forEach((item) => {
    const step = item.dataset.step;
    const index = order.indexOf(step);
    const fallbackIndex = fallbackOrder.indexOf(step);
    const isDone = currentIndex !== -1
      ? currentIndex >= index
      : fallbackCurrentIndex >= fallbackIndex && fallbackCurrentIndex !== -1;
    item.classList.toggle("done", isDone);
    item.classList.toggle("active", step === payload.step);
  });
}

function renderResult(data, selectedAgents = OPTIONAL_ANALYSIS_AGENTS) {
  const progressTrack = $(".progress-track");
  const steps = $("#steps");
  if (progressTrack) progressTrack.classList.add("hidden");
  if (steps) steps.classList.add("hidden");

  const panel = $("#resultPanel");
  panel.classList.remove("hidden");

  const decision = data.final_decision || {};
  const action = decision.action || "WAIT";
  $("#decisionBadge").textContent = action;
  $("#decisionBadge").className = `badge badge-${action.toLowerCase()}`;
  $("#decisionSummary").textContent = decision.summary || "暂无最终结论";
  $("#confidence").textContent = formatPercent(decision.confidence);
  $("#positionSize").textContent = formatPercent(decision.position_size);
  $("#decisionSource").textContent = decision.decision_source || "-";
  $("#tradeDate").textContent = data.trade_date || "-";
  $("#riskNotes").textContent = decision.risk_notes || "";
  $("#disclaimer").textContent = data.disclaimer || "";

  toggleCard("#technicalCard", selectedAgents.includes("technical"));
  toggleCard("#newsCard", selectedAgents.includes("news"));
  toggleCard("#fundamentalCard", selectedAgents.includes("fundamental"));
  toggleCard("#sentimentCard", selectedAgents.includes("sentiment"));

  if (selectedAgents.includes("technical")) renderTechnicalCard(data.technical_report || {});
  if (selectedAgents.includes("news")) renderNewsCard(data.news_report || {}, data.news_data || []);
  if (selectedAgents.includes("fundamental")) renderFundamentalCard(data.fundamental_report || {});
  if (selectedAgents.includes("sentiment")) renderSentimentCard(data.sentiment_report || {});
  renderResearchPerspectiveCard("#bullishResearchCard", "Bullish Research Agent", "多头研究员观点", data.bullish_research_report || {});
  renderResearchPerspectiveCard("#bearishResearchCard", "Bearish Research Agent", "空头研究员观点", data.bearish_research_report || {});
  renderResearchManagerCard(data.research_debate_report || {});
  renderRiskCard(data.risk_report || {});
}

function toggleCard(selector, visible) {
  const card = $(selector);
  if (card) card.classList.toggle("hidden", !visible);
}

function renderTechnicalCard(report) {
  const indicators = report.indicators || {};
  $("#technicalCard").innerHTML = `
    <p class="eyebrow">Technical Agent</p>
    <h3>技术分析</h3>
    <div class="mini-metrics">
      <span>趋势：<strong>${escapeHtml(report.signal || "-")}</strong></span>
      <span>评分：<strong>${escapeHtml(report.score ?? "-")}</strong></span>
    </div>
    <p>${escapeHtml(report.summary || "暂无技术分析摘要")}</p>
    <ul class="plain-list">
      <li>最新价：${escapeHtml(indicators.latest ?? "-")}</li>
      <li>MA5：${escapeHtml(indicators.ma5 ?? "-")}</li>
      <li>MA10：${escapeHtml(indicators.ma10 ?? "-")}</li>
      <li>成交量变化：${formatPercent(indicators.volume_change)}</li>
    </ul>
  `;
}

function renderNewsCard(report, newsData = []) {
  const headlines = report.headlines || [];
  const newsByTitle = new Map(
    newsData
      .filter((item) => item && item.title)
      .map((item) => [String(item.title), item])
  );
  const noNews = headlines.length === 0 && report.summary === "没有找到相关的新闻";
  const headlineItems = noNews
    ? '<li>没有找到相关的新闻</li>'
    : headlines.map((title) => renderNewsHeadline(title, newsByTitle.get(String(title)))).join("") || "<li>没有找到相关的新闻</li>";
  $("#newsCard").innerHTML = `
    <p class="eyebrow">News Agent</p>
    <h3>新闻分析</h3>
    <div class="mini-metrics">
      <span>情绪：<strong>${escapeHtml(report.sentiment || "-")}</strong></span>
      <span>评分：<strong>${escapeHtml(report.score ?? "-")}</strong></span>
    </div>
    <p>${escapeHtml(report.summary || "暂无新闻分析摘要")}</p>
    <ul class="plain-list">${headlineItems}</ul>
  `;
}

function renderNewsHeadline(title, metadata) {
  const safeTitle = escapeHtml(title);
  const url = metadata && metadata.url ? String(metadata.url) : "";
  if (!url) return `<li>${safeTitle}</li>`;
  return `<li><a href="${escapeAttribute(url)}" target="_blank" rel="noopener noreferrer">${safeTitle}</a></li>`;
}

function renderFundamentalCard(report) {
  const metrics = report.metrics || {};
  $("#fundamentalCard").innerHTML = `
    <p class="eyebrow">Fundamental Agent</p>
    <h3>基本面分析</h3>
    <div class="mini-metrics">
      <span>信号：<strong>${escapeHtml(report.signal || "-")}</strong></span>
      <span>评分：<strong>${escapeHtml(report.score ?? "-")}</strong></span>
      <span>来源：<strong>${escapeHtml(report.data_source || "-")}</strong></span>
    </div>
    <p>${escapeHtml(report.summary || "暂无基本面分析摘要")}</p>
    <ul class="plain-list">${renderKeyValueItems(metrics, "暂无财务指标")}</ul>
  `;
}

function renderSentimentCard(report) {
  const sources = report.sources || [];
  const sourceItems = sources.map((source) => `<li>${escapeHtml(source)}</li>`).join("") || "<li>暂无舆情来源</li>";
  $("#sentimentCard").innerHTML = `
    <p class="eyebrow">Sentiment Agent</p>
    <h3>舆情分析</h3>
    <div class="mini-metrics">
      <span>情绪：<strong>${escapeHtml(report.sentiment || "-")}</strong></span>
      <span>评分：<strong>${escapeHtml(report.score ?? "-")}</strong></span>
      <span>热度：<strong>${escapeHtml(report.buzz_score ?? "-")}</strong></span>
      <span>分歧：<strong>${escapeHtml(report.disagreement_score ?? "-")}</strong></span>
    </div>
    <p>${escapeHtml(report.summary || "暂无舆情分析摘要")}</p>
    <ul class="plain-list">${sourceItems}</ul>
  `;
}

function renderResearchPerspectiveCard(selector, eyebrow, title, report) {
  $(selector).innerHTML = `
    <p class="eyebrow">${escapeHtml(eyebrow)}</p>
    <h3>${escapeHtml(title)}</h3>
    <div class="mini-metrics">
      <span>立场：<strong>${escapeHtml(report.stance || "-")}</strong></span>
      <span>置信度：<strong>${formatPercent(report.confidence)}</strong></span>
    </div>
    <p>${escapeHtml(report.thesis || "暂无研究观点")}</p>
    <h4>关键要点</h4>
    <ul class="plain-list">${renderListItems(report.key_points || [], "暂无关键要点")}</ul>
    <h4>关注风险</h4>
    <ul class="plain-list">${renderListItems(report.concerns || [], "暂无关注风险")}</ul>
  `;
}

function renderResearchManagerCard(report) {
  $("#researchManagerCard").innerHTML = `
    <p class="eyebrow">Research Manager Agent</p>
    <h3>研究经理结论</h3>
    <div class="mini-metrics">
      <span>结论：<strong>${escapeHtml(report.conclusion || "-")}</strong></span>
      <span>置信度：<strong>${formatPercent(report.confidence)}</strong></span>
    </div>
    <p>${escapeHtml(report.final_summary || "暂无研究经理结论")}</p>
    <ul class="plain-list">
      <li>多头摘要：${escapeHtml(report.bullish_summary || "-")}</li>
      <li>空头摘要：${escapeHtml(report.bearish_summary || "-")}</li>
    </ul>
    <h4>关键证据</h4>
    <ul class="plain-list">${renderListItems(report.key_evidence || [], "暂无关键证据")}</ul>
  `;
}

function renderRiskCard(report) {
  $("#riskCard").innerHTML = `
    <p class="eyebrow">Risk Agent</p>
    <h3>风险控制</h3>
    <div class="mini-metrics">
      <span>等级：<strong>${escapeHtml(report.level || "-")}</strong></span>
      <span>评分：<strong>${escapeHtml(report.score ?? "-")}</strong></span>
    </div>
    <p>${escapeHtml(report.summary || "暂无风险控制摘要")}</p>
    <ul class="plain-list">
      <li>建议仓位：${formatPercent(report.suggested_position)}</li>
      <li>止损建议：${formatPercent(report.stop_loss_pct)}</li>
      <li>来源：${escapeHtml(report.risk_source || "-")}</li>
    </ul>
  `;
}

function renderKeyValueItems(values, emptyText) {
  const entries = Object.entries(values || {});
  if (entries.length === 0) return `<li>${escapeHtml(emptyText)}</li>`;
  return entries.map(([key, value]) => `<li>${escapeHtml(key)}：${escapeHtml(formatDisplayValue(value))}</li>`).join("");
}

function renderListItems(values, emptyText) {
  if (!values || values.length === 0) return `<li>${escapeHtml(emptyText)}</li>`;
  return values.map((value) => `<li>${escapeHtml(formatDisplayValue(value))}</li>`).join("");
}

function formatDisplayValue(value) {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "object") return JSON.stringify(value);
  return value;
}

function formatPercent(value) {
  if (value === undefined || value === null || value === "") return "-";
  const number = Number(value);
  if (Number.isNaN(number)) return String(value);
  return `${Math.round(number * 100)}%`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replaceAll("`", "&#096;");
}

initHome();
initAnalysis();