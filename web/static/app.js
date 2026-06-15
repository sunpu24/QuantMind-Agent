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
    ${renderAgentHeader("📈", "Technical Agent", "技术分析", report.signal || "-")}
    ${renderMetricPills([
      ["趋势", report.signal || "-"],
      ["评分", report.score ?? "-"],
    ])}
    <p class="agent-summary">${escapeHtml(report.summary || "暂无技术分析摘要")}</p>
    ${renderInsightList([
      ["最新价", indicators.latest ?? "-"],
      ["MA5", indicators.ma5 ?? "-"],
      ["MA10", indicators.ma10 ?? "-"],
      ["成交量变化", formatPercent(indicators.volume_change)],
    ], "行情指标")}
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
    ? '<div class="insight-item">没有找到相关的新闻</div>'
    : headlines.map((title) => renderNewsHeadline(title, newsByTitle.get(String(title)))).join("") || '<div class="insight-item">没有找到相关的新闻</div>';
  $("#newsCard").innerHTML = `
    ${renderAgentHeader("📰", "News Agent", "新闻分析", report.sentiment || "-")}
    ${renderMetricPills([
      ["情绪", report.sentiment || "-"],
      ["评分", report.score ?? "-"],
    ])}
    <p class="agent-summary">${escapeHtml(report.summary || "暂无新闻分析摘要")}</p>
    <div class="insight-list"><h4>新闻线索</h4>${headlineItems}</div>
  `;
}

function renderNewsHeadline(title, metadata) {
  const safeTitle = escapeHtml(title);
  const url = metadata && metadata.url ? String(metadata.url) : "";
  if (!url) return `<div class="insight-item">${safeTitle}</div>`;
  return `<div class="insight-item"><a href="${escapeAttribute(url)}" target="_blank" rel="noopener noreferrer">${safeTitle}</a></div>`;
}

function renderFundamentalCard(report) {
  const metrics = report.metrics || {};
  $("#fundamentalCard").innerHTML = `
    ${renderAgentHeader("🏦", "Fundamental Agent", "基本面分析", report.signal || "-")}
    ${renderMetricPills([
      ["信号", report.signal || "-"],
      ["评分", report.score ?? "-"],
      ["来源", report.data_source || "-"],
    ])}
    <p class="agent-summary">${escapeHtml(report.summary || "暂无基本面分析摘要")}</p>
    ${renderInsightList(Object.entries(metrics || {}), "财务指标", "暂无财务指标")}
  `;
}

function renderSentimentCard(report) {
  const sources = report.sources || [];
  $("#sentimentCard").innerHTML = `
    ${renderAgentHeader("💬", "Sentiment Agent", "舆情分析", report.sentiment || "-")}
    ${renderMetricPills([
      ["情绪", report.sentiment || "-"],
      ["评分", report.score ?? "-"],
      ["热度", report.buzz_score ?? "-"],
      ["分歧", report.disagreement_score ?? "-"],
    ])}
    <p class="agent-summary">${escapeHtml(report.summary || "暂无舆情分析摘要")}</p>
    ${renderChipList(sources, "舆情来源", "暂无舆情来源")}
  `;
}

function renderResearchPerspectiveCard(selector, eyebrow, title, report) {
  const isBullish = selector.includes("bullish");
  $(selector).innerHTML = `
    ${renderAgentHeader(isBullish ? "🐂" : "🐻", eyebrow, title, report.stance || "-")}
    ${renderMetricPills([
      ["立场", report.stance || "-"],
      ["置信度", formatPercent(report.confidence)],
    ])}
    <p class="agent-summary thesis">${escapeHtml(report.thesis || "暂无研究观点")}</p>
    ${renderChipList(report.key_points || [], "关键要点", "暂无关键要点")}
    ${renderInsightList((report.concerns || []).map((value) => ["风险", value]), "关注风险", "暂无关注风险")}
  `;
}

function renderResearchManagerCard(report) {
  $("#researchManagerCard").innerHTML = `
    ${renderAgentHeader("🧭", "Research Manager Agent", "研究经理结论", report.conclusion || "-")}
    ${renderMetricPills([
      ["结论", report.conclusion || "-"],
      ["置信度", formatPercent(report.confidence)],
    ])}
    <p class="agent-summary thesis">${escapeHtml(report.final_summary || "暂无研究经理结论")}</p>
    <div class="summary-compare">
      <div><span>多头摘要</span><p>${escapeHtml(report.bullish_summary || "-")}</p></div>
      <div><span>空头摘要</span><p>${escapeHtml(report.bearish_summary || "-")}</p></div>
    </div>
    ${renderChipList(report.key_evidence || [], "关键证据", "暂无关键证据")}
  `;
}

function renderRiskCard(report) {
  $("#riskCard").innerHTML = `
    ${renderAgentHeader("🛡️", "Risk Agent", "风险控制", report.level || "-")}
    ${renderMetricPills([
      ["等级", report.level || "-"],
      ["评分", report.score ?? "-"],
      ["建议仓位", formatPercent(report.suggested_position)],
      ["止损建议", formatPercent(report.stop_loss_pct)],
      ["来源", report.risk_source || "-"],
    ])}
    <p class="agent-summary thesis">${escapeHtml(report.summary || "暂无风险控制摘要")}</p>
  `;
}

function renderAgentHeader(icon, eyebrow, title, tag) {
  return `
    <div class="agent-header">
      <div class="agent-icon">${escapeHtml(icon)}</div>
      <div>
        <p class="eyebrow">${escapeHtml(eyebrow)}</p>
        <h3>${escapeHtml(title)}</h3>
      </div>
      <span class="agent-tag">${escapeHtml(formatDisplayValue(tag))}</span>
    </div>
  `;
}

function renderMetricPills(items) {
  return `
    <div class="mini-metrics metric-pills">
      ${items.map(([label, value]) => `
        <span><em>${escapeHtml(label)}</em><strong>${escapeHtml(formatDisplayValue(value))}</strong></span>
      `).join("")}
    </div>
  `;
}

function renderInsightList(items, title, emptyText = "暂无内容") {
  const rows = (items || []).filter(Boolean);
  const content = rows.length === 0
    ? `<div class="insight-item">${escapeHtml(emptyText)}</div>`
    : rows.map(([label, value]) => `
        <div class="insight-item">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(formatDisplayValue(value))}</strong>
        </div>
      `).join("");
  return `<div class="insight-list"><h4>${escapeHtml(title)}</h4>${content}</div>`;
}

function renderChipList(values, title, emptyText = "暂无内容") {
  const chips = values && values.length > 0
    ? values.map((value) => `<span>${escapeHtml(formatDisplayValue(value))}</span>`).join("")
    : `<span>${escapeHtml(emptyText)}</span>`;
  return `<div class="chip-list"><h4>${escapeHtml(title)}</h4><div>${chips}</div></div>`;
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