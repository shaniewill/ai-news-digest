from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from anthropic import Anthropic

log = logging.getLogger("llm")


@dataclass
class LLMResult:
    text: str
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    model: str


class AnthropicLLM:
    def __init__(self, cfg: dict[str, Any]) -> None:
        api_key = cfg.get("_env", {}).get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError("ANTHROPIC_API_KEY missing (.env or environment)")
        self.client = Anthropic(api_key=api_key)
        llm_cfg = cfg.get("llm", {})
        self.model_fast = llm_cfg.get("model_fast", "claude-haiku-4-5")
        self.model_deep = llm_cfg.get("model_deep", "claude-sonnet-4-6")
        self.enable_cache = bool(llm_cfg.get("enable_prompt_caching", True))

    def call(
        self,
        system_prompt: str,
        user_message: str,
        *,
        deep: bool = False,
        max_tokens: int = 2048,
        cache_system: bool = True,
    ) -> LLMResult:
        model = self.model_deep if deep else self.model_fast
        if cache_system and self.enable_cache:
            system_block = [
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ]
        else:
            system_block = system_prompt

        resp = self.client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system_block,
            messages=[{"role": "user", "content": user_message}],
        )
        text_parts = [b.text for b in resp.content if getattr(b, "type", "") == "text"]
        text = "\n".join(text_parts).strip()

        usage = resp.usage
        return LLMResult(
            text=text,
            input_tokens=getattr(usage, "input_tokens", 0),
            output_tokens=getattr(usage, "output_tokens", 0),
            cached_input_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            model=model,
        )

    def call_json(self, system_prompt: str, user_message: str, **kw: Any) -> dict[str, Any]:
        result = self.call(system_prompt, user_message, **kw)
        try:
            data = _parse_json_response(result.text)
        except json.JSONDecodeError as e:
            log.warning("first JSON parse failed (%s); retrying with stricter instruction", e)
            stricter = (
                user_message
                + "\n\n严格要求：上次返回的不是合法 JSON。这次只输出合法 JSON，不要 markdown 代码块包裹，不要任何解释文字。字符串内的换行写成 \\n。"
            )
            result = self.call(system_prompt, stricter, **kw)
            data = _parse_json_response(result.text)
        data["_usage"] = {
            "input": result.input_tokens,
            "output": result.output_tokens,
            "cached": result.cached_input_tokens,
            "model": result.model,
        }
        return data


def _parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.removeprefix("json").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start : end + 1])
        raise


def load_prompt(name: str, prompts_dir: str | Path = "prompts") -> str:
    p = Path(prompts_dir) / f"{name}.md"
    return p.read_text(encoding="utf-8")
