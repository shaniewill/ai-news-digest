---
name: preview-digest
description: Dry-run 渲染日报但不写 vault、不入库。用来调 prompt 或预览输出。用户说"看一下今天会输出什么"、"/preview-digest"时调用。
---

执行步骤：

1. 跑 `uv run python -m src.main daily --dry-run`。
2. 该命令应在 stdout 完整 print 渲染后的 markdown，并把 LLM 调用计入 token 统计但不写文件、不更新 SQLite。
3. 把输出的前 80 行展示给用户（用 ```markdown 包裹）。
4. 末尾附：
   - 估算 token 用量
   - 估算 USD 成本（基于 config 里的模型档单价）
   - 警告项：fetcher 失败、缺源、items < 阈值等

不要：在 dry-run 模式下意外写 vault 或入库。如果脚本不支持 `--dry-run`，提示用户先实现。
