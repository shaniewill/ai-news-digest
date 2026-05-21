---
name: add-source
description: 引导式增源——问类型，生成 fetcher，更新 config。用户说"加一个新源"、"/add-source"时调用。
---

执行步骤：

1. 用 AskUserQuestion 问：
   - 源类型：`rss` / `reddit_subreddit` / `hackernews_search` / `custom_http`
   - 源 URL / 名称
   - 启用过滤（min_score、关键词包含/排除等）
2. 检查 `src/fetchers/` 是否已有同名 NAME 常量——有就让用户改名。
3. 委托 `fetcher-author` subagent 生成 fetcher 代码（用 Agent 工具）。
4. 把新源加入 `config.example.yaml` 的 `sources:` 节点（不动 `config.yaml` —— 那是用户自己的私本）。
5. 跑 `/test-source <new_name>` 验证一次。
6. 输出：fetcher 文件路径、config 改动 diff、test 结果摘要。

不要：直接改用户的 `config.yaml`（可能含 API key）；只改 `config.example.yaml`。
