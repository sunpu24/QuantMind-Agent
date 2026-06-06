const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));

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
      window.location.href = `/analysis?query=${encodeURIComponent(query)}`;
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

function initAnalysis() {
  const progressBar = $("#progressBar");
  if (!progressBar) return;

  const params = new URLSearchParams(window.location.search);
  const query = params.get("query") || "";
  const title = $("#analysisTitle");
  const statusText = $("#statusText");

  if (!query) {
    title.textContent = "缺少股票输入";
    statusText.textContent = "请返回首页重新输入股票名称或代码。";
    return;
  }

  title.textContent = `正在分析：${query}`;
  const source = new EventSource(`/api/analyze/stream?q=${encodeURIComponent(query)}`);

  source.onmessage = (event) => {
    const payload = JSON.parse(event.data);
    updateProgress(payload);
    if (payload.symbol) {
      title.textContent = `正在分析：${payload.symbol.display_name}（${payload.symbol.symbol}）`;
    }
    if (payload.type === "result") {
      renderResult(payload.data);
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

function updateProgress(payload) {
  const progressBar = $("#progressBar");
  const statusText = $("#statusText");
  const percent = Math.max(0, Math.min(100, Number(payload.percent || 0)));
  progressBar.style.width = `${percent}%`;
  statusText.textContent = payload.message || "分析中...";

  const order = ["resolved", "prepared", "technical", "news", "risk", "decision"];
  const currentIndex = order.indexOf(payload.step);
  $$("#steps li").forEach((item) => {
    const step = item.dataset.step;
    const index = order.indexOf(step);
    item.classList.toggle("done", currentIndex >= index && currentIndex !== -1);
    item.classList.toggle("active", step === payload.step);
  });
}

function renderResult(data) {
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

  renderTechnicalCard(data.technical_report || {});
  renderNewsCard(data.news_report || {}, data.news_data || []);
  renderRiskCard(data.risk_report || {});
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