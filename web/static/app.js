const $ = (selector) => document.querySelector(selector);
const $$ = (selector) => Array.from(document.querySelectorAll(selector));
const OPTIONAL_ANALYSIS_AGENTS = ["technical", "news", "fundamental", "sentiment"];
const ALWAYS_ON_STEPS = ["resolved", "prepared", "market_regime", "bullish_research", "bearish_research", "research_manager", "risk", "decision"];
const RECENT_SEARCHES_KEY = "quantmind.recentSearches";
const WATCHLIST_KEY = "quantmind.watchlist";
let latestAnalysisResult = null;
let latestAnalysisQuery = "";
let latestAnalysisSymbol = null;

function initHome() {
  const form = $("#searchForm");
  if (!form) return;

  const input = $("#stockInput");
  const errorText = $("#errorText");
  initAgentQuickActions();
  const setError = (message) => {
    errorText.textContent = message || "";
  };
  initCompareEntry(setError);
  renderRecentSearches(input);
  initWatchlist(input, setError);

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
      saveRecentSearch(query, payload.data);
      startAnalysis(query);
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

function initAgentQuickActions() {
  const setChecked = (checked) => {
    $$("input[name='agent']").forEach((input) => {
      input.checked = checked;
    });
  };
  $("#selectAllAgents")?.addEventListener("click", () => setChecked(true));
  $("#clearAgents")?.addEventListener("click", () => setChecked(false));
}

function initCompareEntry(setStatus = () => {}) {
  const button = $("#startCompareButton");
  if (!button) return;

  button.addEventListener("click", () => {
    const queries = ["#compareInputA", "#compareInputB", "#compareInputC"]
      .map((selector) => $(selector)?.value.trim())
      .filter(Boolean);
    const uniqueQueries = [...new Set(queries)];
    if (uniqueQueries.length < 2) {
      setStatus("请至少输入 2 只不同股票用于对比");
      return;
    }

    const selectedAgents = getSelectedAnalysisAgents();
    const params = new URLSearchParams({ symbols: uniqueQueries.join(",") });
    params.set("agents", selectedAgents.join(","));
    window.location.href = `/static/compare.html?${params.toString()}`;
  });
}

function renderRecentSearches(input) {
  const container = $("#recentSearches");
  const list = $("#recentSearchList");
  if (!container || !list) return;

  const searches = getRecentSearches();
  container.classList.toggle("hidden", searches.length === 0);
  list.innerHTML = searches.map((item) => `
    <button type="button" data-query="${escapeAttribute(item.query)}">
      <strong>${escapeHtml(item.display_name || item.query)}</strong>
      <span>${escapeHtml(item.symbol || item.query)}</span>
    </button>
  `).join("");

  $$("#recentSearchList button").forEach((button) => {
    button.addEventListener("click", () => {
      input.value = button.dataset.query || "";
      input.focus();
    });
  });
  $("#clearRecentSearches")?.addEventListener("click", () => {
    localStorage.removeItem(RECENT_SEARCHES_KEY);
    renderRecentSearches(input);
  });
}

function initWatchlist(input, setStatus = () => {}) {
  const addButton = $("#addWatchlistButton");
  const list = $("#watchlistItems");
  if (!addButton || !list) return;

  renderWatchlist(input);
  addButton.addEventListener("click", async () => {
    const query = input.value.trim();
    if (!query) {
      setStatus("请输入股票名称或代码后再加入自选");
      return;
    }

    setStatus("正在校验并加入自选...");
    try {
      const response = await fetch(`/api/validate?q=${encodeURIComponent(query)}`);
      const payload = await response.json();
      if (!response.ok || !payload.ok) {
        setStatus(payload.message || "当前输入无法加入自选");
        return;
      }
      saveWatchlistItem(query, payload.data);
      renderWatchlist(input);
      setStatus("已加入自选股");
    } catch (error) {
      setStatus("网络异常，暂时无法加入自选");
    }
  });
}

function renderWatchlist(input) {
  const list = $("#watchlistItems");
  const empty = $("#watchlistEmpty");
  if (!list || !empty) return;

  const items = getWatchlist();
  empty.classList.toggle("hidden", items.length > 0);
  list.innerHTML = items.map((item) => `
    <article class="watchlist-item">
      <button type="button" class="watchlist-main" data-action="fill" data-query="${escapeAttribute(item.query)}">
        <strong>${escapeHtml(item.display_name || item.query)}</strong>
        <span>${escapeHtml(item.symbol || item.query)}</span>
      </button>
      <div class="watchlist-actions">
        <button type="button" class="ghost-button" data-action="analyze" data-query="${escapeAttribute(item.query)}">分析</button>
        <button type="button" class="ghost-button danger-button" data-action="remove" data-symbol="${escapeAttribute(item.symbol || item.query)}">移除</button>
      </div>
    </article>
  `).join("");

  $$("#watchlistItems button").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.action;
      const query = button.dataset.query || "";
      if (action === "fill") {
        input.value = query;
        input.focus();
      }
      if (action === "analyze") {
        startAnalysis(query);
      }
      if (action === "remove") {
        removeWatchlistItem(button.dataset.symbol || query);
        renderWatchlist(input);
      }
    });
  });
}

function getWatchlist() {
  try {
    const value = JSON.parse(localStorage.getItem(WATCHLIST_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch (error) {
    return [];
  }
}

function saveWatchlistItem(query, symbol = {}) {
  const normalizedQuery = String(query || symbol.display_name || symbol.symbol || "").trim();
  if (!normalizedQuery) return;
  const normalizedSymbol = String(symbol.symbol || normalizedQuery).trim();
  const nextItem = {
    query: normalizedQuery,
    symbol: normalizedSymbol,
    display_name: symbol.display_name || normalizedQuery,
    market: symbol.market || "",
    saved_at: new Date().toISOString(),
  };
  const deduped = getWatchlist().filter((item) => item.symbol !== normalizedSymbol && item.query !== normalizedQuery);
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify([nextItem, ...deduped].slice(0, 20)));
}

function removeWatchlistItem(symbolOrQuery) {
  const value = String(symbolOrQuery || "");
  const nextItems = getWatchlist().filter((item) => item.symbol !== value && item.query !== value);
  localStorage.setItem(WATCHLIST_KEY, JSON.stringify(nextItems));
}

function startAnalysis(query) {
  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) return;
  const selectedAgents = getSelectedAnalysisAgents();
  const targetParams = new URLSearchParams({ query: normalizedQuery });
  targetParams.set("agents", selectedAgents.join(","));
  window.location.href = `/analysis?${targetParams.toString()}`;
}

function getRecentSearches() {
  try {
    const value = JSON.parse(localStorage.getItem(RECENT_SEARCHES_KEY) || "[]");
    return Array.isArray(value) ? value : [];
  } catch (error) {
    return [];
  }
}

function saveRecentSearch(query, symbol = {}) {
  const normalizedQuery = String(query || "").trim();
  if (!normalizedQuery) return;
  const nextItem = {
    query: normalizedQuery,
    symbol: symbol.symbol || normalizedQuery,
    display_name: symbol.display_name || normalizedQuery,
    saved_at: new Date().toISOString(),
  };
  const deduped = getRecentSearches().filter((item) => item.query !== normalizedQuery && item.symbol !== nextItem.symbol);
  localStorage.setItem(RECENT_SEARCHES_KEY, JSON.stringify([nextItem, ...deduped].slice(0, 6)));
}

function getSelectedAnalysisAgents() {
  return $$("input[name='agent']:checked")
    .map((input) => input.value)
    .filter(Boolean);
}

function initCompare() {
  const progressBar = $("#compareProgressBar");
  if (!progressBar) return;

  const params = new URLSearchParams(window.location.search);
  const queries = (params.get("symbols") || "")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean)
    .slice(0, 3);
  const selectedAgents = getAnalysisAgentsFromParams(params);
  const title = $("#compareTitle");
  const status = $("#compareStatus");

  if (queries.length < 2) {
    title.textContent = "缺少对比股票";
    status.textContent = "请返回首页，至少输入 2 只股票后重新开始对比。";
    return;
  }

  title.textContent = `正在对比：${queries.join(" vs ")}`;
  const entries = queries.map((query, index) => ({ id: index, query, symbol: null, data: null, status: "pending", message: "等待分析", percent: 0 }));
  renderCompareProgress(entries);
  runCompareQueue(entries, selectedAgents);
}

async function runCompareQueue(entries, selectedAgents) {
  for (let index = 0; index < entries.length; index += 1) {
    const entry = entries[index];
    entry.status = "running";
    entry.message = "启动分析中...";
    renderCompareProgress(entries);
    updateCompareOverallProgress(entries, index, 0);
    try {
      await runCompareAnalysis(entry, selectedAgents, (payload) => {
        entry.percent = Math.max(0, Math.min(100, Number(payload.percent || entry.percent || 0)));
        entry.message = payload.message || "分析中...";
        if (payload.symbol) entry.symbol = payload.symbol;
        updateCompareOverallProgress(entries, index, entry.percent);
        renderCompareProgress(entries);
      });
    } catch (error) {
      entry.status = "error";
      entry.message = error.message || "分析失败";
      entry.percent = 100;
      renderCompareProgress(entries);
    }
  }

  updateCompareOverallProgress(entries, entries.length, 100);
  renderCompareResult(entries, selectedAgents);
}

function runCompareAnalysis(entry, selectedAgents, onProgress) {
  return new Promise((resolve, reject) => {
    const streamParams = new URLSearchParams({ q: entry.query, agents: selectedAgents.join(",") });
    const source = new EventSource(`/api/analyze/stream?${streamParams.toString()}`);
    source.onmessage = (event) => {
      let payload;
      try { payload = JSON.parse(event.data); } catch (error) { return; }
      onProgress(payload);
      if (payload.type === "result") {
        entry.status = "done";
        entry.percent = 100;
        entry.message = "分析完成";
        entry.symbol = payload.symbol || entry.symbol;
        entry.data = payload.data;
        source.close();
        resolve(entry);
      }
      if (payload.type === "error") {
        source.close();
        reject(new Error(payload.message || "分析失败"));
      }
    };
    source.onerror = () => {
      source.close();
      reject(new Error("分析连接中断"));
    };
  });
}

function updateCompareOverallProgress(entries, currentIndex, currentPercent) {
  const progressBar = $("#compareProgressBar");
  const status = $("#compareStatus");
  const completedUnits = Math.min(currentIndex, entries.length);
  const currentUnit = currentIndex < entries.length ? currentPercent / 100 : 0;
  const percent = Math.round(((completedUnits + currentUnit) / entries.length) * 100);
  if (progressBar) progressBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
  if (status) {
    const active = entries.find((entry) => entry.status === "running");
    status.textContent = active
      ? `正在分析第 ${currentIndex + 1}/${entries.length} 只：${getCompareEntryName(active)} · ${active.message}`
      : percent >= 100 ? "对比分析完成。" : "准备启动对比分析...";
  }
}

function renderCompareProgress(entries) {
  const container = $("#compareProgressCards");
  if (!container) return;
  container.innerHTML = entries.map((entry) => `
    <article class="compare-progress-card compare-${escapeAttribute(entry.status)}">
      <div class="compare-progress-heading">
        <strong>${escapeHtml(getCompareEntryName(entry))}</strong>
        <span>${escapeHtml(getCompareStatusLabel(entry.status))}</span>
      </div>
      <div class="compare-mini-track"><div style="width: ${Math.max(0, Math.min(100, entry.percent || 0))}%"></div></div>
      <small>${escapeHtml(entry.message || "等待分析")}</small>
    </article>
  `).join("");
}

function renderCompareResult(entries, selectedAgents) {
  const panel = $("#compareResultPanel");
  if (!panel) return;
  panel.classList.remove("hidden");
  const completed = entries.filter((entry) => entry.status === "done" && entry.data);
  const badge = $("#compareCompletedBadge");
  if (badge) {
    badge.textContent = `${completed.length}/${entries.length} 完成`;
    badge.className = `badge ${completed.length === entries.length ? "badge-buy" : "badge-wait"}`;
  }
  renderCompareSummary(completed, entries);
  renderCompareTable(completed, selectedAgents);
}

function renderCompareSummary(completed, allEntries) {
  const container = $("#compareSummaryCards");
  if (!container) return;
  if (completed.length === 0) {
    container.innerHTML = '<div class="compare-summary-card"><strong>暂无可对比结果</strong><p>所有股票分析都未能完成，请返回后重试。</p></div>';
    return;
  }
  const bestConfidence = maxBy(completed, (entry) => normalizePercentValue(entry.data?.final_decision?.confidence));
  const bestPosition = maxBy(completed, (entry) => normalizePercentValue(entry.data?.final_decision?.position_size));
  const lowestRisk = minBy(completed, (entry) => normalizePercentValue(entry.data?.risk_report?.score));
  const mostBullish = maxBy(completed, (entry) => countBullishSignals(entry.data));
  const failedCount = allEntries.length - completed.length;
  container.innerHTML = [
    ["最高置信度", getCompareEntryName(bestConfidence), `${normalizePercentValue(bestConfidence?.data?.final_decision?.confidence)}%`],
    ["建议仓位最高", getCompareEntryName(bestPosition), formatPercent(bestPosition?.data?.final_decision?.position_size)],
    ["风险评分最低", getCompareEntryName(lowestRisk), `${normalizePercentValue(lowestRisk?.data?.risk_report?.score)}%`],
    ["多头信号最多", getCompareEntryName(mostBullish), `${countBullishSignals(mostBullish?.data)} 个`],
  ].map(([label, name, value]) => `
    <div class="compare-summary-card"><span>${escapeHtml(label)}</span><strong>${escapeHtml(name || "-")}</strong><p>${escapeHtml(value || "-")}</p></div>
  `).join("") + (failedCount > 0 ? `
    <div class="compare-summary-card compare-warning"><span>未完成</span><strong>${failedCount} 只</strong><p>可先查看已完成股票的横向对比。</p></div>
  ` : "");
}

function renderCompareTable(entries, selectedAgents) {
  const container = $("#compareTable");
  if (!container) return;
  if (entries.length === 0) {
    container.innerHTML = '<p class="muted">暂无可展示的对比数据。</p>';
    return;
  }
  const rows = [
    ["最终动作", (entry) => entry.data?.final_decision?.action || "WAIT"],
    ["置信度", (entry) => formatPercent(entry.data?.final_decision?.confidence)],
    ["建议仓位", (entry) => formatPercent(entry.data?.final_decision?.position_size)],
    ["风险等级", (entry) => entry.data?.risk_report?.level || "-"],
    ["风险评分", (entry) => formatDisplayValue(entry.data?.risk_report?.score)],
    ["技术信号", (entry) => selectedAgents.includes("technical") ? entry.data?.technical_report?.signal || "-" : "未启用"],
    ["新闻情绪", (entry) => selectedAgents.includes("news") ? entry.data?.news_report?.sentiment || "-" : "未启用"],
    ["基本面信号", (entry) => selectedAgents.includes("fundamental") ? entry.data?.fundamental_report?.signal || "-" : "未启用"],
    ["舆情情绪", (entry) => selectedAgents.includes("sentiment") ? entry.data?.sentiment_report?.sentiment || "-" : "未启用"],
    ["研究经理", (entry) => entry.data?.research_debate_report?.conclusion || "-"],
    ["摘要", (entry) => entry.data?.final_decision?.summary || "暂无摘要"],
  ];
  container.innerHTML = `
    <table class="compare-table"><thead><tr><th>指标</th>${entries.map((entry) => `<th>${escapeHtml(getCompareEntryName(entry))}</th>`).join("")}</tr></thead>
      <tbody>${rows.map(([label, getter]) => `<tr><th>${escapeHtml(label)}</th>${entries.map((entry) => `<td>${escapeHtml(formatDisplayValue(getter(entry)))}</td>`).join("")}</tr>`).join("")}</tbody></table>
  `;
}

function getCompareEntryName(entry) {
  if (!entry) return "-";
  const symbol = entry.symbol || {};
  if (symbol.display_name && symbol.symbol) return `${symbol.display_name}（${symbol.symbol}）`;
  return symbol.display_name || symbol.symbol || entry.query || "-";
}

function getCompareStatusLabel(status) {
  return { pending: "等待", running: "分析中", done: "完成", error: "失败" }[status] || "等待";
}

function countBullishSignals(data = {}) {
  return [data?.technical_report?.signal, data?.news_report?.sentiment, data?.fundamental_report?.signal, data?.sentiment_report?.sentiment, data?.research_debate_report?.conclusion]
    .filter((value) => String(value || "").toLowerCase() === "bullish").length;
}

function maxBy(items, getter) {
  return items.reduce((best, item) => (best === null || getter(item) > getter(best) ? item : best), null);
}

function minBy(items, getter) {
  return items.reduce((best, item) => (best === null || getter(item) < getter(best) ? item : best), null);
}

function initAnalysis() {
  const progressBar = $("#progressBar");
  if (!progressBar) return;

  const params = new URLSearchParams(window.location.search);
  const query = params.get("query") || "";
  const selectedAgents = getAnalysisAgentsFromParams(params);
  const title = $("#analysisTitle");
  const statusText = $("#statusText");
  latestAnalysisQuery = query;
  initReportActions();
  initAnalysisWatchlistAction();
  initAgentCardControls();

  if (!query) {
    title.textContent = "缺少股票输入";
    statusText.textContent = "请返回首页重新输入股票名称或代码。";
    return;
  }

  title.textContent = `正在分析：${query}`;
  appendLog("准备启动分析工作流", "pending");
  updateVisibleSteps(selectedAgents);
  const streamParams = new URLSearchParams({ q: query, agents: selectedAgents.join(",") });
  const source = new EventSource(`/api/analyze/stream?${streamParams.toString()}`);

  source.onmessage = (event) => {
    let payload;
    try {
      payload = JSON.parse(event.data);
    } catch (error) {
      appendLog("收到无法解析的工作流事件，已忽略", "error");
      return;
    }
    updateProgress(payload);
    appendLog(payload.message || "收到工作流事件", payload.type === "error" ? "error" : payload.type === "result" ? "done" : "progress");
    if (payload.symbol) {
      title.textContent = `正在分析：${payload.symbol.display_name}（${payload.symbol.symbol}）`;
      latestAnalysisQuery = `${payload.symbol.display_name}（${payload.symbol.symbol}）`;
      latestAnalysisSymbol = payload.symbol;
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
    appendLog("分析连接中断，请返回首页后重试。", "error");
    source.close();
  };
}

function initAnalysisWatchlistAction() {
  $("#saveWatchlistButton")?.addEventListener("click", () => {
    const symbol = latestAnalysisSymbol || {};
    const fallbackQuery = latestAnalysisQuery || new URLSearchParams(window.location.search).get("query") || "";
    saveWatchlistItem(symbol.display_name || symbol.symbol || fallbackQuery, symbol);
    setReportStatus("已加入自选股");
  });
}

function appendLog(message, type = "progress") {
  const list = $("#eventLog");
  const count = $("#logCount");
  if (!list) return;
  const item = document.createElement("div");
  item.className = `log-item log-${type}`;
  item.innerHTML = `<time>${escapeHtml(new Date().toLocaleTimeString("zh-CN", { hour12: false }))}</time><span>${escapeHtml(message)}</span>`;
  list.appendChild(item);
  list.scrollTop = list.scrollHeight;
  if (count) count.textContent = `${list.children.length} 条事件`;
}

function initReportActions() {
  $("#copyReportButton")?.addEventListener("click", async () => {
    if (!latestAnalysisResult) return setReportStatus("报告尚未生成");
    const markdown = buildMarkdownReport(latestAnalysisResult);
    try {
      await copyTextToClipboard(markdown);
      setReportStatus("已复制到剪贴板");
    } catch (error) {
      setReportStatus("复制失败，请手动选择内容");
    }
  });

  $("#downloadReportButton")?.addEventListener("click", () => {
    if (!latestAnalysisResult) return setReportStatus("报告尚未生成");
    const markdown = buildMarkdownReport(latestAnalysisResult);
    const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `QuantMind-${getDateStamp()}-${sanitizeFilename(latestAnalysisQuery || latestAnalysisResult.symbol || "report")}.md`;
    link.click();
    URL.revokeObjectURL(link.href);
    setReportStatus("Markdown 已导出");
  });
}

async function copyTextToClipboard(text) {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(text);
    return;
  }

  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.left = "-9999px";
  textarea.style.top = "0";
  document.body.appendChild(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  document.body.removeChild(textarea);
  if (!copied) throw new Error("Fallback copy failed");
}

function setReportStatus(message) {
  const status = $("#reportActionStatus");
  if (!status) return;
  status.textContent = message;
  window.setTimeout(() => {
    status.textContent = "";
  }, 2400);
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
     "market_regime",
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
  latestAnalysisResult = data;
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
  renderDecisionScorePanel(data, selectedAgents);
  renderDecisionContributionPanel(decision);
  renderMarketRegimeCard(data.market_regime_report || {});

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
  syncAgentCardCollapseButtons();
}

function renderDecisionScorePanel(data, selectedAgents = OPTIONAL_ANALYSIS_AGENTS) {
  const panel = $("#decisionScorePanel");
  if (!panel) return;

  const model = buildDecisionScoreModel(data, selectedAgents);
  panel.className = `decision-score-panel decision-score-${model.action.toLowerCase()}`;
  panel.innerHTML = `
    <div class="score-gauge-card">
      <div class="score-gauge" style="--score-value: ${model.confidencePercent}; --score-color: ${model.color}">
        <div class="score-gauge-inner">
          <span>${escapeHtml(model.confidenceLabel)}</span>
          <strong>${model.confidencePercent}%</strong>
        </div>
      </div>
      <div>
        <p class="eyebrow">Decision Score</p>
        <h3>${escapeHtml(model.title)}</h3>
        <p class="score-caption">${escapeHtml(model.caption)}</p>
      </div>
    </div>
    <div class="score-bars" aria-label="决策评分明细">
      ${model.bars.map(renderDecisionScoreBar).join("")}
    </div>
  `;
}

function renderDecisionContributionPanel(decision = {}) {
  const panel = $("#decisionContributionPanel");
  if (!panel) return;
  const breakdown = decision.contribution_breakdown || {};
  const entries = Object.entries(breakdown);
  const maxAbs = Math.max(0.01, ...entries.map(([, value]) => Math.abs(Number(value) || 0)));
  panel.innerHTML = `
    <div class="contribution-heading">
      <div>
        <p class="eyebrow">Dynamic Weighting</p>
        <h3>动态加权评分：${escapeHtml(formatSignedNumber(decision.weighted_score))}</h3>
      </div>
      <span>${escapeHtml(decision.regime_adjustment || "暂无市场状态调整说明")}</span>
    </div>
    <div class="contribution-list">
      ${entries.map(([key, value]) => renderContributionRow(key, value, maxAbs)).join("") || '<p class="muted">暂无贡献度明细</p>'}
    </div>
  `;
}

function renderContributionRow(key, value, maxAbs) {
  const number = Number(value) || 0;
  const width = Math.round(Math.min(100, Math.abs(number) / maxAbs * 100));
  const tone = number < 0 ? "negative" : "positive";
  return `
    <div class="contribution-row contribution-${tone}">
      <div class="contribution-label"><span>${escapeHtml(formatContributionLabel(key))}</span><strong>${escapeHtml(formatSignedNumber(number))}</strong></div>
      <div class="contribution-track"><div style="width: ${width}%"></div></div>
    </div>
  `;
}

function buildDecisionScoreModel(data, selectedAgents = OPTIONAL_ANALYSIS_AGENTS) {
  const decision = data.final_decision || {};
  const action = String(decision.action || "WAIT").toUpperCase();
  const confidencePercent = normalizePercentValue(decision.confidence);
  const positionPercent = normalizePercentValue(decision.position_size);
  const signalScores = collectSignalScores(data, selectedAgents);
  const riskPercent = normalizePercentValue(data.risk_report?.score);
  const color = getDecisionActionColor(action);

  return {
    action,
    color,
    confidencePercent,
    confidenceLabel: action,
    title: getDecisionScoreTitle(action, confidencePercent),
    caption: buildDecisionScoreCaption(action, signalScores, riskPercent),
    bars: [
      ["置信度", confidencePercent, "最终决策可靠性", "confidence"],
      ["建议仓位", positionPercent, positionPercent > 0 ? "按风险约束后的可用仓位" : "当前建议不新增仓位", "position"],
      ["多头信号", signalScores.bullish, `${signalScores.enabledCount} 个信号源参与`, "bullish"],
      ["空头信号", signalScores.bearish, `${signalScores.enabledCount} 个信号源参与`, "bearish"],
      ["风险约束", riskPercent, getRiskScoreLabel(data.risk_report), "risk"],
    ],
  };
}

function collectSignalScores(data, selectedAgents = OPTIONAL_ANALYSIS_AGENTS) {
  const signals = [];
  const addSignal = (enabled, stance, score, weight = 1) => {
    if (!enabled || !stance) return;
    signals.push({ stance: String(stance).toLowerCase(), score: normalizePercentValue(score), weight });
  };

  addSignal(selectedAgents.includes("technical"), data.technical_report?.signal, data.technical_report?.score);
  addSignal(selectedAgents.includes("news"), data.news_report?.sentiment, data.news_report?.score);
  addSignal(selectedAgents.includes("fundamental"), data.fundamental_report?.signal, data.fundamental_report?.score);
  addSignal(selectedAgents.includes("sentiment"), data.sentiment_report?.sentiment, data.sentiment_report?.score);
  addSignal(true, data.research_debate_report?.conclusion, data.research_debate_report?.confidence, 1.5);

  const totals = signals.reduce((acc, item) => {
    if (item.stance === "bullish") acc.bullish += item.score * item.weight;
    if (item.stance === "bearish") acc.bearish += item.score * item.weight;
    acc.weight += item.weight;
    return acc;
  }, { bullish: 0, bearish: 0, weight: 0 });

  return {
    bullish: totals.weight ? Math.round(totals.bullish / totals.weight) : 0,
    bearish: totals.weight ? Math.round(totals.bearish / totals.weight) : 0,
    enabledCount: signals.length,
  };
}

function renderDecisionScoreBar([label, value, helper, tone]) {
  const percent = Math.max(0, Math.min(100, Number(value || 0)));
  return `
    <div class="score-bar-row score-bar-${escapeAttribute(tone)}">
      <div class="score-bar-heading">
        <span>${escapeHtml(label)}</span>
        <strong>${percent}%</strong>
      </div>
      <div class="score-bar-track" aria-hidden="true">
        <div class="score-bar-fill" style="width: ${percent}%"></div>
      </div>
      <small>${escapeHtml(helper)}</small>
    </div>
  `;
}

function normalizePercentValue(value) {
  if (value === undefined || value === null || value === "") return 0;
  const number = Number(value);
  if (Number.isNaN(number)) return 0;
  const percent = Math.abs(number) <= 1 ? number * 100 : number;
  return Math.round(Math.max(0, Math.min(100, percent)));
}

function getDecisionActionColor(action) {
  if (action === "BUY") return "#38d6b4";
  if (action === "SELL") return "#ff6b7a";
  if (action === "HOLD") return "#facc15";
  return "#55a7ff";
}

function getDecisionScoreTitle(action, confidencePercent) {
  const actionText = {
    BUY: "偏向买入 / 建仓",
    SELL: "偏向卖出 / 降风险",
    HOLD: "偏向持有 / 不加仓",
    WAIT: "偏向观望 / 等待确认",
  }[action] || "偏向观望 / 等待确认";
  const strength = confidencePercent >= 75 ? "高置信" : confidencePercent >= 60 ? "中等置信" : "低置信";
  return `${strength} · ${actionText}`;
}

function buildDecisionScoreCaption(action, signalScores, riskPercent) {
  const lead = action === "BUY" ? "正向信号占优" : action === "SELL" ? "负向或风险信号占优" : "多空信号仍需确认";
  return `${lead}，多头 ${signalScores.bullish}% / 空头 ${signalScores.bearish}% / 风险 ${riskPercent}%。`;
}

function getRiskScoreLabel(report = {}) {
  const level = report?.level ? String(report.level).toLowerCase() : "";
  if (level === "high") return "高风险，强约束仓位";
  if (level === "medium") return "中等风险，需控制仓位";
  if (level === "low") return "低风险，约束较弱";
  return "暂无风险等级";
}

function initAgentCardControls() {
  document.addEventListener("click", (event) => {
    const button = event.target.closest(".agent-collapse-button");
    if (!button) return;
    const card = button.closest(".agent-card");
    if (!card) return;
    setAgentCardCollapsed(card, !card.classList.contains("collapsed"));
  });

  $("#expandAllAgentCards")?.addEventListener("click", () => setAllAgentCardsCollapsed(false));
  $("#collapseAllAgentCards")?.addEventListener("click", () => setAllAgentCardsCollapsed(true));
}

function setAllAgentCardsCollapsed(collapsed) {
  $$(".agent-card:not(.hidden)").forEach((card) => setAgentCardCollapsed(card, collapsed));
}

function setAgentCardCollapsed(card, collapsed) {
  card.classList.toggle("collapsed", collapsed);
  const button = card.querySelector(".agent-collapse-button");
  if (!button) return;
  button.setAttribute("aria-expanded", String(!collapsed));
  button.textContent = collapsed ? "展开" : "收起";
}

function syncAgentCardCollapseButtons() {
  $$(".agent-card").forEach((card) => {
    setAgentCardCollapsed(card, card.classList.contains("collapsed"));
  });
}

function buildMarkdownReport(data) {
  const decision = data.final_decision || {};
  const risk = data.risk_report || {};
  const debate = data.research_debate_report || {};
  const lines = [
    `# QuantMind 分析报告：${latestAnalysisQuery || data.symbol || "-"}`,
    "",
    `- 分析日期：${data.trade_date || "-"}`,
    `- 最终动作：${decision.action || "WAIT"}`,
    `- 置信度：${formatPercent(decision.confidence)}`,
    `- 建议仓位：${formatPercent(decision.position_size)}`,
    `- 决策来源：${decision.decision_source || "-"}`,
    "",
    "## 最终结论",
    decision.summary || "暂无最终结论",
    "",
    "## 风险提示",
    decision.risk_notes || risk.summary || "暂无风险提示",
    "",
    "## 市场信号",
    formatReportSection("技术分析", data.technical_report),
    formatReportSection("新闻分析", data.news_report),
    formatReportSection("基本面分析", data.fundamental_report),
    formatReportSection("舆情分析", data.sentiment_report),
    "",
    "## 研究员辩论",
    `- 多头观点：${data.bullish_research_report?.thesis || "-"}`,
    `- 空头观点：${data.bearish_research_report?.thesis || "-"}`,
    `- 研究经理：${debate.final_summary || debate.conclusion || "-"}`,
    "",
    "## 风险控制",
    `- 风险等级：${risk.level || "-"}`,
    `- 风险评分：${risk.score ?? "-"}`,
    `- 建议仓位：${formatPercent(risk.suggested_position)}`,
    `- 止损建议：${formatPercent(risk.stop_loss_pct)}`,
    "",
    data.disclaimer || "本报告仅用于研究和学习，不构成任何投资建议。",
  ];
  return lines.join("\n");
}

function formatReportSection(title, report = {}) {
  if (!report) return `- ${title}：未启用或暂无数据`;
  const signal = report.signal || report.sentiment || report.stance || report.level || "-";
  const score = report.score ?? report.confidence ?? "-";
  return `- ${title}：${signal} / 评分：${formatDisplayValue(score)} / ${report.summary || report.thesis || "暂无摘要"}`;
}

function sanitizeFilename(value) {
  return String(value).replace(/[\\/:*?"<>|]/g, "-").slice(0, 80);
}

function getDateStamp() {
  const date = new Date();
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}${month}${day}`;
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

function renderMarketRegimeCard(report) {
  const card = $("#marketRegimeCard");
  if (!card) return;
  card.innerHTML = `
    ${renderAgentHeader("🌡️", "Market Regime Agent", "市场状态", report.regime || "-")}
    ${renderMetricPills([
      ["市场状态", report.regime || "-"],
      ["波动率", formatPercent(report.volatility)],
      ["趋势强度", formatPercent(report.trend_strength)],
      ["最大回撤", formatPercent(report.max_drawdown)],
    ])}
    <p class="agent-summary thesis">${escapeHtml(report.summary || "暂无市场状态解释")}</p>
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
      <div class="agent-header-actions">
        <span class="agent-tag">${escapeHtml(formatDisplayValue(tag))}</span>
        <button type="button" class="agent-collapse-button" aria-expanded="true">收起</button>
      </div>
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

function formatSignedNumber(value) {
  const number = Number(value);
  if (Number.isNaN(number)) return "-";
  return `${number >= 0 ? "+" : ""}${number.toFixed(4)}`;
}

function formatContributionLabel(key) {
  return {
    technical: "技术分析",
    news: "新闻情绪",
    fundamental: "基本面",
    sentiment: "舆情",
    research: "研究经理",
    risk_penalty: "风险惩罚",
  }[key] || key;
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
initCompare();