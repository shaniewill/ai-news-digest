# AI news digest assistant

每日 AI 圈热点追踪与深度分析助手。规格文档见 [`idea.md`](idea.md)；Claude Code 工作约束见 [`CLAUDE.md`](CLAUDE.md)。

## 它做什么

每天从 Hacker News / Anthropic / OpenAI RSS / GitHub Trending 等源抓取候选条目，去重 + 排序后跑 7 个 LLM sub-roles：

| Role | 模型档 | 输出 |
|------|--------|------|
| curator | Haiku | 选 5 deep + ~35 brief + ~5 weak + 今日一句话 |
| deep-analyst | Sonnet | 每条 5 段式（FACT/CONTEXT/STAKEHOLDERS/IMPLICATIONS/UNCERTAINTY） |
| brief-summarizer | Haiku | 速览一行中文 |
| weak-signal-scout | Haiku | 讨论量低但值得盯的弱信号 |
| trend-connector | Haiku | 连到 Topics MOC 的 wikilink |
| prediction-drafter | Sonnet | 1–2 条可证伪预判（带时间点 + 证伪条件） |
| weekly-reviewer | Sonnet | 周报（独立命令） |

输出写到 Obsidian vault：

```
<your-obsidian-vault>/AI_news/
├── Daily/YYYY-MM-DD.md
├── Weekly/YYYY-Www.md
├── Predictions/pred-YYYY-MM-DD-NN-<slug>.md
└── Topics/<MOC>.md   (手维护)
```

> Vault 根路径由 `config.yaml` 的 `vault.path` 配置。模板见 `config.example.yaml`。

## 快速开始

```powershell
# 1. 装依赖
uv sync

# 2. 配置
Copy-Item config.example.yaml config.yaml
Set-Content -Path .env -Value "ANTHROPIC_API_KEY=sk-ant-你的key" -Encoding utf8

# 3. 测一个源（不调 LLM）
uv run python -m src.main test-source hackernews

# 4. dry-run（调 LLM 但不写 vault）
uv run python -m src.main daily --dry-run
# 输出到 data/dry-run-YYYY-MM-DD-<run_id>.md

# 5. 正式跑
uv run python -m src.main daily

# 6. 周报（每周日跑一次）
uv run python -m src.main weekly
```

## CLI commands

```
uv run python -m src.main daily [--dry-run]   # 日报
uv run python -m src.main weekly              # 周报
uv run python -m src.main test-source <name>  # 单测 fetcher
uv run python -m src.main list-sources        # 列出已注册的 source
```

## 项目结构

```
src/
├── main.py                  # Click CLI
├── config.py                # 加载 config.yaml + .env
├── models.py                # NewsItem / DeepAnalysis / Prediction / DigestPayload
├── fetchers/
│   ├── hackernews.py        # HN Algolia API
│   ├── rss.py               # 通用 RSS（Anthropic / OpenAI blogs）
│   └── github_trending.py   # GitHub trending 抓取
├── pipeline/
│   ├── dedup.py             # URL 归一化 + SQLite 去重
│   ├── rank.py              # 加权 score/comments/recency
│   ├── analyze.py           # 7 sub-role 编排
│   ├── render.py            # Jinja2 渲染
│   └── weekly.py            # 周报回溯
├── llm/anthropic_client.py  # Anthropic SDK 封装 + prompt caching + JSON 重试
└── obsidian/writer.py       # 写 vault + 拆 predictions

prompts/
├── curator.md
├── deep_analyst.md
├── brief_summarizer.md
├── weak_signal_scout.md
├── trend_connector.md
├── prediction_drafter.md
└── weekly_reviewer.md

templates/daily-digest.md.j2

.claude/
├── settings.json            # 权限 + Obsidian MCP server
├── agents/                  # fetcher-author / prompt-engineer / digest-critic
└── skills/                  # /run-daily /test-source /preview-digest /add-source /review-digest

fixtures/sample_items.json   # 10 条假数据，离线开发用
tests/test_pipeline.py       # 4 个 pytest（dedup / rank / render / normalize_url）
```

## Claude Code 集成

打开 Claude Code 进入本仓库后可直接用：

- `/run-daily` — 跑日报并报告
- `/preview-digest` — dry-run 看输出
- `/test-source hackernews` — 单测某个 fetcher
- `/add-source` — 引导式加新源
- `/review-digest [date]` — 红队评估今日 digest

需要专项工作时调用 subagent：`fetcher-author`（加/改源）、`prompt-engineer`（调 prompt）、`digest-critic`（评质量）。

## 已知 trade-off / 下一步

- **Twitter/X 依赖 RSSHub 公共实例**：`rsshub.app` 长期不稳定（常被 302 到 google 404）。fetcher 容错返回 0 条不影响其余流程，但若想稳定拿 X 内容，需自建 RSSHub 或换 instance：把 `config.yaml` 的 `twitter.instance_url` 指向你自己的部署。
- **JSON 输出依赖 LLM 自律**：用了一道重试 + 严格化提示，但更稳的方式是 Anthropic tool_use 模式（Phase 2 改）。
- **trend_connector / weekly_reviewer 需要历史 daily**：第一周内输出会偏弱，跑满 7 天后周报才有意义。
- **Phase 5 自动发帖当前禁止实现**——见 `CLAUDE.md` "Hard constraints"。

## 测试

```powershell
uv run pytest tests/ -v
```

不需要 API key，使用 `fixtures/sample_items.json`。

## 计费提示

- **Claude Code**（开发期）：走 Pro/Max 订阅 OAuth，**不要**让环境里的 `ANTHROPIC_API_KEY` 拦截
- **`uv run … daily`**（运行期）：走 `.env` 里的 Console API key
- 详见 `CLAUDE.md` "Environment（Windows）" 节
