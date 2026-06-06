# QuantMind Agent

QuantMind Agent 是一个面向 A 股的多 Agent 股票预测/辅助交易决策框架。

第一版参考 `TradingAgents` 的思想，但采用更轻量的固定串行流程：

```text
技术分析 Agent → 新闻分析 Agent → 风险控制 Agent → 交易决策 Agent
```

当前版本默认使用 Mock 数据和规则 Agent，便于先跑通整体框架；同时已最小化接入 AkShare/Tushare/Alpha Vantage 与 DeepSeek。后续可以逐步升级 LangGraph、回测系统和 Web/API。

> 安全提示：如果行情数据源显示为 `mock` 或 `*_fallback_mock`，说明当前分析使用的是占位行情。系统会在报告中显示醒目的数据可信度警告，并将最终交易决策按安全规则降级为 `WAIT`、仓位降为 `0%`，避免基于占位数据输出高置信买卖建议。

## 快速开始

### PowerShell + 项目级虚拟环境

```powershell
cd quantmind-agent
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe main.py --symbol 600519 --date 2026-06-05
```

> 如果暂时不安装依赖，也可以先直接运行；项目会在没有 `.env` 时使用默认 Mock 配置。
> `.venv/` 已加入 `.gitignore`，不要提交虚拟环境目录。

### 本地 Web 页面运行

当前项目已提供 FastAPI + 原生 HTML/CSS/JS 的轻量 Web 页面：

```powershell
cd quantmind-agent
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn web_app:app --host 0.0.0.0 --port 8000 --reload
```

浏览器打开：

```text
http://127.0.0.1:8000
```

Web 第一版支持：

- 首页输入股票名称、A 股代码或美股 ticker，例如 `贵州茅台`、`600519`、`Apple`、`AAPL`；
- 非 A 股/美股或暂未收录中文名称会提示不可查询；
- 分析页通过进度条展示 `技术分析 Agent → 新闻分析 Agent → 风险控制 Agent → 交易决策 Agent` 的串行进度；
- 分析完成后优先展示最终交易决策，再展示技术、新闻、风险三个 Agent 的详情卡片。

Zeabur 部署时可使用类似启动命令：

```bash
uvicorn web_app:app --host 0.0.0.0 --port ${PORT:-8000}
```

### Mock 数据运行

```powershell
cd quantmind-agent
$env:QUANTMIND_DATA_PROVIDER='mock'
.\.venv\Scripts\python.exe main.py --symbol 600519 --date 2026-06-05
```

报告顶部会显示：

```text
行情数据源: mock
请求 Provider: mock
```

### AkShare 数据运行

```powershell
cd quantmind-agent
$env:QUANTMIND_DATA_PROVIDER='akshare'
.\.venv\Scripts\python.exe main.py --symbol 600519 --date 2026-06-05
```

如果 AkShare 成功返回 A 股日线行情，报告顶部会显示：

```text
行情数据源: akshare
请求 Provider: akshare
```

如果当前网络、代理或 AkShare 上游接口不可用，例如无法访问 `push2his.eastmoney.com` 并出现 `ProxyError`，程序会打印失败原因并自动回退到 Mock 行情，报告顶部会显示：

```text
行情数据源: akshare_fallback_mock
请求 Provider: akshare
回退原因: AkShare 行情获取失败: ...
```

AkShare 真实行情依赖当前网络、代理/梯子出口与东方财富 K 线接口状态。当前项目会把 `AKSHARE_TIMEOUT` 传入 AkShare 请求；同时在 60 天窗口失败后，自动尝试 30 天、20 天更短窗口，仍失败才回退 Mock。可通过报告顶部判断是否真正使用了真实行情：

- `行情数据源: akshare`：AkShare 真实行情已成功进入 Agent 流程。
- `行情数据源: akshare_fallback_mock`：已请求 AkShare，但因网络、超时、空数据或字段异常等原因回退 Mock。

如果网络不稳定，建议：

- 更换代理/梯子节点后重试；
- 对 `eastmoney.com` / `push2his.eastmoney.com` 尝试 DIRECT 或固定稳定节点；
- 使用历史交易日验证，例如 `--date 2024-06-05`，避免未来日期没有真实行情；
- 不要仅凭 `curl` 一次失败判断 AkShare 必然失败，项目主流程和 AkShare 内部请求路径可能表现不同。

### AkShare 诊断脚本

如果只想诊断 AkShare 网络与字段转换，不跑完整 Agent 流程，可以使用：

```powershell
cd quantmind-agent
.\.venv\Scripts\python.exe examples/check_akshare.py --symbol 600519 --date 2024-06-05
```

诊断脚本会输出：

- `AKSHARE_ENABLED` 和 `AKSHARE_TIMEOUT`；
- 当前 `stock_zh_a_hist` 是否支持 `timeout` 参数；
- 60 / 30 / 20 天窗口逐次尝试结果；
- 成功时的返回条数、首日、末日、最新收盘价；
- 失败时的失败类型和截断后的失败原因。

报告顶部也会展示更明确的 AkShare 可观测信息。例如 AkShare 请求失败并回退 Mock 时：

```text
行情数据源: akshare_fallback_mock
请求 Provider: akshare
回退原因: AkShare 行情获取失败: ...
回退类型: proxy_error
AkShare 尝试: 60天 failed, 30天 failed, 20天 failed
```

> 当前项目已支持 Tushare 日线行情最小接入；使用前需要配置 `TUSHARE_TOKEN`。

### Tushare 数据运行

如果希望使用 Tushare 获取 A 股日线行情，需要先在 Tushare 官网获取 token，然后通过 `.env` 或 PowerShell 环境变量配置。

`.env` 写法：

```env
QUANTMIND_DATA_PROVIDER=tushare
TUSHARE_TOKEN=你的_tushare_token
```

PowerShell 临时配置写法：

```powershell
cd quantmind-agent
$env:QUANTMIND_DATA_PROVIDER='tushare'
$env:TUSHARE_TOKEN='你的_tushare_token'
.\.venv\Scripts\python.exe main.py --symbol 600519 --date 2024-06-05
```

Tushare 成功返回行情时，报告顶部会显示：

```text
行情数据源: tushare
请求 Provider: tushare
```

如果未配置 token、token 无权限或接口请求失败，程序会自动回退 Mock，报告顶部会显示：

```text
行情数据源: tushare_fallback_mock
请求 Provider: tushare
回退类型: missing_token / token_error / timeout / empty_data / schema_mismatch / tushare_error
```

> 请不要把真实 `TUSHARE_TOKEN` 提交到 Git；建议只写在本地 `.env` 或当前 PowerShell 会话中。

### Tushare 诊断脚本

如果只想检查 token 配置和 Tushare 日线接口，可以使用：

```powershell
cd quantmind-agent
$env:TUSHARE_TOKEN='你的_tushare_token'
.\.venv\Scripts\python.exe examples/check_tushare.py --symbol 600519 --date 2024-06-05
```

### 新闻数据：A 股 AkShare，美股 Alpha Vantage

当前新闻 Provider 支持：

- `auto`：A 股新闻走 AkShare，美股新闻走 Alpha Vantage；
- `akshare`：强制使用 AkShare A 股个股新闻；
- `alpha_vantage`：强制使用 Alpha Vantage 新闻；
- `mock`：使用占位新闻。

推荐 `.env` 写法：

```env
QUANTMIND_NEWS_PROVIDER=auto
AKSHARE_ENABLED=true
AKSHARE_TIMEOUT=15
ALPHA_VANTAGE_API_KEY=你的_alpha_vantage_api_key
ALPHA_VANTAGE_TIMEOUT=15
```

如果只想诊断 AkShare A 股个股新闻接口，可以使用：

```powershell
cd quantmind-agent
.\.venv\Scripts\python.exe examples/check_akshare_news.py --symbol 600519 --date 2026-06-05
```

诊断脚本会调用 AkShare 的 `stock_news_em`，并输出是否成功、返回新闻数、新闻标题、来源和链接。主流程会过滤与目标股票不相关的新闻；AkShare 新闻请求失败或过滤后没有相关新闻时会自动回退 Mock 新闻，并在报告中显示：

```text
新闻数据源: akshare_fallback_mock
请求新闻 Provider: akshare
新闻回退原因: AkShare 新闻获取失败: ... / AkShare 未返回与目标股票相关的可用新闻
新闻回退类型: proxy_error / timeout / empty_data / schema_mismatch / akshare_error
```

### Alpha Vantage 新闻数据

如果希望使用 Alpha Vantage 获取新闻与情绪数据，需要先获取 Alpha Vantage API Key，然后配置新闻 Provider。

`.env` 写法：

```env
QUANTMIND_NEWS_PROVIDER=alpha_vantage
ALPHA_VANTAGE_API_KEY=你的_alpha_vantage_api_key
ALPHA_VANTAGE_TIMEOUT=15
```

PowerShell 临时配置写法：

```powershell
cd quantmind-agent
$env:QUANTMIND_NEWS_PROVIDER='alpha_vantage'
$env:ALPHA_VANTAGE_API_KEY='你的_alpha_vantage_api_key'
.\.venv\Scripts\python.exe examples/check_alpha_vantage_news.py --symbol 600519 --date 2024-06-05
```

诊断脚本会输出：

- 当前新闻 Provider；
- API Key 脱敏状态；
- Alpha Vantage ticker 映射；
- 请求是否成功；
- 返回新闻数量和标题。

> Alpha Vantage 主要保留给美股新闻；A 股新闻建议使用 `QUANTMIND_NEWS_PROVIDER=auto` 或 `akshare`。Alpha Vantage 的新闻接口会返回宏观、行业和多股票新闻，当前项目会用 `ticker_sentiment` 过滤必须包含目标 ticker 的新闻；如果过滤后没有相关新闻，主流程会自动回退 Mock 新闻，保证 Agent 流程不中断。

主流程报告顶部会展示新闻数据源可观测信息。例如 Alpha Vantage 对 A 股代码请求成功但返回 0 条可用新闻时，会自动回退 Mock 新闻，并显示：

```text
新闻数据源: alpha_vantage_fallback_mock
请求新闻 Provider: alpha_vantage
新闻回退原因: Alpha Vantage 未返回可用新闻
新闻回退类型: empty_data
```

Alpha Vantage 成功返回真实新闻时会显示：

```text
新闻数据源: alpha_vantage
请求新闻 Provider: alpha_vantage
```

### DeepSeek 结构化分析与交易决策 Agent

当前 DeepSeek 最小接入可用于 4 个核心 Agent：

- `技术分析 Agent`：基于 Python 已计算完成的 MA5、MA10、最新价和成交量变化，输出结构化 `TechnicalReport`。
- `新闻分析 Agent`：基于新闻标题、摘要和新闻源 metadata 输出结构化 `NewsReport`。
- `风险控制 Agent`：基于技术、新闻和规则基线风险报告输出结构化 `RiskReport`，仓位和止损会被 Python Guardrails 裁剪。
- `交易决策 Agent`：综合技术、新闻、风险报告给出最终 `BUY / HOLD / WAIT / SELL` 决策。

交易动作统一含义：

- `BUY`：买入/加仓/试探性建仓，仓位必须大于 `0`，且不超过风险建议仓位和最大仓位。
- `HOLD`：已有仓位继续持有但不新增买入；当前系统没有持仓上下文时仓位输出 `0%`。
- `WAIT`：观望等待、不买不卖；信息不足、信号冲突或数据不可靠时使用，仓位固定 `0%`。
- `SELL`：卖出/减仓/规避风险；当前系统没有持仓数量时仓位输出 `0%`。

这样可以保留规则 Agent 的可测试性，并在 LLM 失败时自动回退到规则逻辑。

`.env` 写法：

```env
QUANTMIND_LLM_PROVIDER=deepseek
QUANTMIND_LLM_MODEL=deepseek-chat
QUANTMIND_LLM_BASE_URL=https://api.deepseek.com
QUANTMIND_LLM_TIMEOUT=30
DEEPSEEK_API_KEY=你的_deepseek_api_key
```

诊断 DeepSeek 连接：

```powershell
cd quantmind-agent
.\.venv\Scripts\python.exe examples/check_deepseek.py
```

诊断脚本会脱敏显示 API Key，并在成功时输出 `调用耗时: ... ms`，用于快速观察 DeepSeek API 的网络耗时；不会打印完整 token/API key。

当 `QUANTMIND_LLM_PROVIDER=deepseek` 且已配置 API Key 时，技术、新闻、风险和交易决策 Agent 会优先调用 DeepSeek；如果未配置 key、API 请求失败或 JSON 解析失败，对应 Agent 会自动回退到规则逻辑。所有 prompt 只包含股票代码、日期、结构化分析结果、新闻标题/摘要与数据源 metadata，不包含任何 API Key。

> 如果新闻数据源显示为 `alpha_vantage_fallback_mock`，说明 Alpha Vantage 新闻不可用后回退到了 Mock 新闻。此类新闻只能作为占位情绪信号，不能当作真实新闻证据；DeepSeek 新闻分析 prompt 会明确提示这一点，并要求在 summary 中说明其非真实新闻证据属性。

主流程报告会在 `[最终交易决策]` 区域显示：

```text
LLM Provider: deepseek
LLM Model: deepseek-chat
LLM 耗时: ... ms
LLM 回退类型: N/A
LLM 输入摘要: symbol=600519, date=2024-06-05, ...
LLM 输出摘要: action=..., confidence=..., position_size=..., summary=...
交易决策来源: deepseek
依据: ...
```

其中 `LLM 输入摘要` 只包含股票代码、日期、数据源、技术/新闻/风险评分和规则基线等摘要信息，不输出完整 prompt；`LLM 输出摘要` 只展示结构化响应的关键字段，不展示原始完整响应或任何 API Key。

如果未配置 key、API 请求失败或 JSON 解析失败，会自动回退规则决策，并显示：

```text
交易决策来源: rule_fallback
LLM 回退类型: missing_api_key / http_error / timeout / network_error / invalid_response / schema_mismatch / llm_error
LLM 回退原因: ...
```

> 项目只会脱敏显示 API Key，例如 `sk-...abcd`，不要把真实 `DEEPSEEK_API_KEY` 提交到 Git。

如果行情数据源为 `mock` 或 `*_fallback_mock`，最终交易决策会额外触发占位数据保护：

```text
⚠ 数据可信度警告: 当前行情为 mock 或 fallback mock，占位性质较强。
⚠ 最终交易决策已按安全规则降级为 WAIT，不能作为真实投资建议。
动作: WAIT
建议仓位: 0%
```

这类保护优先级高于规则决策和 DeepSeek 决策，目的是避免把占位行情误读为真实行情证据。

### 本地验证命令

建议只编译项目源码目录，避免扫描 `.venv`：

```powershell
cd quantmind-agent
.\.venv\Scripts\python.exe -m compileall main.py quantmind examples tests
.\.venv\Scripts\python.exe -m unittest discover -s tests
```

## 配置

所有 API Key 和运行配置都放在 `.env` 中，不要写入代码。

关键配置：

- `QUANTMIND_DATA_PROVIDER`: `mock` / `akshare` / `tushare`
- `QUANTMIND_NEWS_PROVIDER`: `auto` / `mock` / `akshare` / `alpha_vantage`
- `TUSHARE_TOKEN`: Tushare Token
- `AKSHARE_ENABLED`: 是否启用 AkShare，默认 `true`
- `AKSHARE_TIMEOUT`: AkShare 请求超时配置，默认 `15` 秒，会传入当前版本支持 `timeout` 参数的 `ak.stock_zh_a_hist`
- `QUANTMIND_LLM_PROVIDER`: 当前实际支持 `mock` / `deepseek`；其他 provider 名称为后续扩展预留
- `QUANTMIND_LLM_API_KEY`: 默认 LLM API Key
- `QUANTMIND_DEFAULT_POSITION_SIZE`: 默认仓位比例
- `QUANTMIND_STOP_LOSS_PCT`: 默认止损比例

## 项目结构

```text
quantmind-agent/
├── main.py
├── quantmind/
│   ├── config.py
│   ├── schemas.py
│   ├── agents/
│   ├── data/
│   ├── graph/
│   └── utils/
└── examples/
```

## 免责声明

本项目仅用于研究和学习，不构成任何投资建议。交易有风险，决策需谨慎。
