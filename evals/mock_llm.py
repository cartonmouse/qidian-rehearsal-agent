"""Deterministic chat provider used by offline LLM contract evaluations.

This is intentionally small and local. It does not emulate model quality; it
returns fixture payloads so the evaluation can exercise provider integration,
structured validation, source anchoring and adaptive line-reading contracts
without storing or requiring a real API key.
"""

from __future__ import annotations

import json
import re
from typing import Any


class ContractMockLLM:
    """Return scene or adaptive-dialogue fixtures based on the system prompt."""

    def __init__(self, *, scenes: dict[str, dict[str, Any]], adaptive: dict[str, Any]):
        self.scenes = scenes
        self.adaptive = adaptive
        self.last_attempts = 0
        self.calls: list[list[dict[str, str]]] = []

    def invoke(self, messages: list[dict[str, str]]) -> str:
        self.calls.append(messages)
        self.last_attempts = 1
        system = messages[0].get("content", "") if messages else ""
        if "剧本结构化解析器" in system:
            prompt = messages[-1].get("content", "") if messages else ""
            match = re.search(r"当前场次编号：([0-9]+)", prompt)
            if not match or match.group(1) not in self.scenes:
                raise AssertionError("mock scene fixture is missing for the requested scene")
            payload = self.scenes[match.group(1)]
        elif "对词搭档" in system:
            if "turns" in self.adaptive:
                payload = self.adaptive
            else:
                prompt = messages[-1].get("content", "") if messages else ""
                source_prompt = prompt.split("请改写以下非练习者参考台词", 1)[-1]
                match = re.search(r'"character":\s*"([^"]+)"', source_prompt)
                if not match or match.group(1) not in self.adaptive:
                    raise AssertionError("mock adaptive fixture is missing for the requested partner")
                payload = self.adaptive[match.group(1)]
        else:
            raise AssertionError("unexpected system prompt in LLM contract evaluation")
        return json.dumps(payload, ensure_ascii=False)


__all__ = ["ContractMockLLM"]
