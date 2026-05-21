---
name: review-digest
description: 红队评估一份已生成的 daily digest。用户说"评一下今天的输出"、"/review-digest [date]"时调用。
---

参数：`[date]`（可选，默认今天，格式 `YYYY-MM-DD`）。

执行步骤：

1. 解析 date；构造 vault 路径 `<vault>/AI_news/Daily/<date>.md`（vault 根从 `config.yaml` `vault.path` 取）。
2. 如果文件不存在，提示用户先跑 `/run-daily` 或换日期。
3. 用 Agent 工具调 `digest-critic` subagent，把文件路径传过去，让它读 + 评。
4. 把 critic 返回的打分表 + 3 条改进建议原样展示给用户。
5. 询问用户是否要把改进建议交给 `prompt-engineer` subagent 落实（不要直接动 prompt）。

不要：自己评 digest——必须委托 `digest-critic`，保持职责分离。
