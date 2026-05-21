---
name: test-source
description: 单测一个 fetcher，不写数据库不调 LLM。用户说"测一下 hackernews 源"、"/test-source <name>"时调用。
---

参数：`<source_name>`（必填，对应 `src/fetchers/<name>.py` 的 NAME 常量）。

执行步骤：

1. 跑 `uv run python -m src.main test-source <name>`。
2. 该命令应返回 JSON 数组（前 10 条 NewsItem）。
3. 检查：
   - 条目数 > 0
   - 每条都有 `title, url, source, published_at`
   - URL 是合法 http(s)
   - title 是英文（如果不是，警告——可能 fetcher 解析错位）
4. 用表格输出前 5 条标题+score+评论数+发布时间。
5. 如果脚本失败，先看 traceback；常见问题：网络、ToS 屏蔽、源结构变更。

不要：把测试结果写入 SQLite 或 vault。
