---
name: run-daily
description: 跑一次 daily pipeline，把日报写入 vault。用户说"跑今天的"、"生成日报"、"/run-daily"时调用。
---

执行步骤：

1. 跑 `uv run python -m src.main daily` (PowerShell)，把 stdout/stderr 都捕获。
2. 解析最后 30 行，提取：
   - run_id、耗时、抓取条数、deep/brief 各几条
   - 写入路径（`<vault>/AI_news/Daily/YYYY-MM-DD.md`，vault 根从 `config.yaml` `vault.path` 取）
   - 是否有 fetcher 失败警告
3. 如果脚本退出码 ≠ 0，**不要**当成功；展示错误最后 50 行让用户判断。
4. 成功的话，输出三行摘要：
   - 抓取/去重/输出条数
   - vault 路径
   - 用户可以直接打开的 Obsidian URI（`obsidian://open?vault=...&file=AI_news/Daily/YYYY-MM-DD`）

不要：自动重跑、自动改 config、自动 commit 结果。
