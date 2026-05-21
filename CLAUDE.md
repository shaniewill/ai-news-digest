# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# AI news digest assistant — project context

每日 AI 圈热点追踪与深度分析助手。规格主文档：`idea.md`（v0.2）。本文件是 Claude Code 工作时的硬约束摘要；与 `idea.md` 冲突时，以 `idea.md` 为准。

## Hard constraints

- **Vault path**：`D:/Obsidian/Obsidian Vault` — daily digest 写到 `AI_news/Daily/YYYY-MM-DD.md`，predictions 写到 `AI_news/Predictions/`，不要写到 vault 其他位置。
- **Language**：对话回复用中文；标题/术语/文件名/代码标识符用英文（idea.md 第 20–24 行）。LLM 生成的 digest 同规则：英文标题 + 中文分析 + 英文术语保留。
- **Scope**：Phase 1 MVP 只做 HN + 1 个 blog RSS + GitHub trending，不引入 Twitter/X、arXiv、newsletter。Phase 5 自动发帖**当前禁止实现**。
- **Output**：仅 Obsidian 静默落盘。不做邮件/Telegram/Slack 通知。
- **Sources of truth**：LLM 不许编造新闻——任何写进 digest 的事实必须可追溯到 fetcher 拉到的原文 URL。

## Tech stack

- Python 3.11+，`uv` 管理依赖
- LLM：Anthropic API（`claude-haiku-4-5` for fast 档，`claude-sonnet-4-6` for deep 档）— 启用 prompt caching
- 数据：SQLite at `data/news.db`（gitignore）
- 模板：Jinja2 渲染 `templates/daily-digest.md.j2`
- HTTP：`httpx` + `feedparser`

## Runtime sub-roles（idea.md 5.1 角色显式化）

每条 sub-role 是独立 prompt 文件，位于 `prompts/`：

| Role | Prompt file | Model |
|---|---|---|
| curator | `prompts/curator.md` | fast |
| deep-analyst | `prompts/deep_analyst.md` | deep |
| brief-summarizer | `prompts/brief_summarizer.md` | fast |
| weak-signal-scout | `prompts/weak_signal_scout.md` | fast |
| trend-connector | `prompts/trend_connector.md` | fast |
| prediction-drafter | `prompts/prediction_drafter.md` | deep |
| weekly-reviewer | `prompts/weekly_reviewer.md` | deep |

## File layout

详见 `idea.md` 7.2。关键入口：`src/main.py`（CLI：`daily | weekly | test-source <name> | list-sources`）。

## Architecture（数据流）

`daily` 跑一次的完整管线（`src/pipeline/` 下逐步组合）：

1. **Fetch** — `src/fetchers/__init__.py` 的 `REGISTRY` 字典枚举所有 source（hackernews / rss / github_trending / huggingface / twitter）。每个 fetcher 返回 `list[NewsItem]`，遵循统一签名 `fetch(cfg: dict) -> list[NewsItem]`。**加新源就是加一个模块 + 在 REGISTRY 注册**，不改主流程。
2. **Dedup** — `pipeline/dedup.py` 用归一化 URL（小写 host、去 `www.`、剥 `utm_*` / `fbclid` 等追踪参数、去尾斜杠）做 key，命中过去写入的 SQLite `items` 表就丢弃；新条目此时入库。
3. **Rank** — `pipeline/rank.py` 加权 `score * 0.4 + comments * 0.3 + recency_decay * 0.3`（指数衰减半衰期 48h，可配置）。RSS / HF 这种 `score=0` 的源排名天然偏后——靠 curator prompt 的 source-diversity 硬约束兜回来，不要在 rank 层加 boost（那会扭曲热度信号）。
4. **LLM sub-roles** — `pipeline/analyze.py` 的 `run_daily(...)` 串起 7 个 role：curator 选 ids → deep-analyst 逐条 5 段式（并行展开 5 次）→ brief-summarizer 出 overview + 3-4 主题聚类 → weak-signal-scout / trend-connector / prediction-drafter。
5. **Render & Write** — `pipeline/render.py` 用 Jinja2 套 `templates/daily-digest.md.j2`，`obsidian/writer.py` 落盘到 vault：daily 写一个文件，每条 prediction 拆成 `Predictions/pred-YYYY-MM-DD-NN-<slug>.md`。

`DigestPayload`（`src/models.py`）是模板的唯一输入契约：改字段时模板、analyze、test 三处要一起改。`BriefCluster.items` 是 `list[tuple[NewsItem, str]]`（条目 + 一行中文），Jinja 里 unpack 成 `it, one_line`。

### LLM 调用约定

- `src/llm/anthropic_client.py` 的 `AnthropicLLM` 封装两档模型（fast/deep）+ prompt caching。`call_json(...)` 解析失败会**自动重试一次**，拼一段"严格要求只输出 JSON"的提示——所以 prompt 模板里可以信任 LLM 大概率返回合法 JSON，但调用方仍要对缺字段做 `.get(..., default)`，不要直接下标。
- 想换 JSON 可靠性方案到 Anthropic tool_use 模式时，统一改 `anthropic_client.py`，role prompts 不动。

### 信息源 source diversity

curator prompt 里写了"5 条 deep 同一 source 最多 2 条"的硬约束。**这是 prompt 层防御，不是代码层校验**——改 curator prompt 时不要丢这条；后续若要改成代码强制（rerank or reject），改 `pipeline/analyze.py:run_daily` 的 `deep_items` 截取处。

## Testing

```powershell
uv run pytest tests/ -v                                                # 全跑
uv run pytest tests/test_pipeline.py::test_ranking_orders_by_weighted_score -v   # 单测一个用例
```

测试用 `fixtures/sample_items.json`（10 条假数据），**不调 LLM、不需要 API key**。`render_daily` 的测试既验证 frontmatter 也验证 brief cluster 模板分支，是模板改动的回归网。

`test-source` 单测一个 fetcher（真实网络，不调 LLM）：

```powershell
uv run python -m src.main test-source hackernews
uv run python -m src.main test-source huggingface
```

## Dry-run

`daily --dry-run` 把 LLM 跑完，但**不写 vault**——输出到 `data/dry-run-YYYY-MM-DD-<run_id>.md`（用文件而非 stdout 是为了绕开 Windows 控制台 GBK 编码炸 emoji 的问题）。看完用 `code data/dry-run-*.md` 或在 Obsidian 临时打开。

## Environment（Windows）

- Shell 是 PowerShell：用 `$env:VAR` 不是 `$VAR`，用 `;` 链接命令不是 `&&`（参考工具说明）。Bash via Bash tool 也可用。
- API Key 放 `.env`，**不进 git**。
- 不要执行 `git config` 或 `git push` 相关命令，除非用户明确要求。

### Claude Code 用 Pro 订阅 vs 日报脚本用 API Key（两套计费，勿混）

| 用途 | 认证方式 | 怎么配 |
|------|----------|--------|
| **Claude Code**（终端写代码） | Claude **Pro/Max 订阅** OAuth | `.\scripts\start-claude-pro.ps1` 或先 `Remove-Item Env:ANTHROPIC_API_KEY` 再 `claude` |
| **`uv run … daily`**（生成日报） | Console **API Key** | 项目根目录 `.env` 里的 `ANTHROPIC_API_KEY`（Console 单独建 key，按量计费） |

**重要**：环境里若存在 `ANTHROPIC_API_KEY`，Claude Code 会**优先走 API 计费**，不用 Pro 额度；你关掉 Console 里的 key 后会 **401**。  
切换步骤：`claude auth logout` → `.\scripts\start-claude-pro.ps1` → 浏览器用 **claude.ai Pro 账号**登录（**不要**选 Console / API billing）。  
登录后在 Claude Code 里输入 `/status`，应显示 subscription，而非 custom API key。若仍走 API：在 `/config` 里关掉 **Use custom API key**。

**不要**用 `claude auth login --console`（那是 Console API 计费，不是 Pro 订阅）。

## Common commands

```powershell
uv sync                                      # 安装依赖
uv run python -m src.main daily              # 跑一次日报
uv run python -m src.main daily --dry-run    # 不写 vault，只 print
uv run python -m src.main test-source hackernews
uv run python -m src.main weekly             # 周报
```

## Claude Code 集成（Layer B）

`.claude/` 下三类专项配置：

- `agents/` — 三个 subagent：`fetcher-author`（加/改源）、`prompt-engineer`（调 prompt）、`digest-critic`（红队评估今日 digest 质量）
- `skills/` — 五个用户向 skill：`/run-daily`、`/test-source`、`/preview-digest`、`/add-source`、`/review-digest`
- `settings.json` — 权限白名单 + Obsidian MCP server（`obsidian-mcp` npm，指向 `D:/Obsidian/Obsidian Vault`）

加新 source 走 `fetcher-author` 子 agent 或 `/add-source` skill 时，记得在 `src/fetchers/__init__.py` 的 `REGISTRY` 注册，并在 `config.example.yaml` + `config.yaml` 同步加配置块。

## What NOT to do

- 不要为了"鲁棒"加 fallback 把幻觉新闻写进 digest——宁可少 1 条也不要假事实。
- 不要在 Phase 1 引入 ranking ML、embedding 聚类、Web UI——这些是 Phase 4。
- 不要 amend 已有 commit，不要 `--no-verify`。
- 不要在 vault 里放 `.venv`、`data/`、`.env` 等代码工件。
- 不要在 `pipeline/rank.py` 里给 RSS/HF 加 score boost 去平衡——用 curator prompt 的 source-diversity 约束。
