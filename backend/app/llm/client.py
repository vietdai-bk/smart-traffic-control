"""Groq client tối giản (OpenAI-compatible Chat Completions) — dùng httpx, không phụ thuộc SDK."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings


class LLMError(Exception):
    """Lỗi gọi LLM (chưa cấu hình, timeout, HTTP lỗi, phản hồi sai định dạng)."""


@dataclass
class LLMReply:
    content: str
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    latency_ms: float = 0.0
    usage: dict = field(default_factory=dict)

    def json(self) -> dict:
        text = self.content.strip()
        if text.startswith("```"):
            text = text.strip("`")
            text = text[text.find("{"):]
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end < 0:
            raise LLMError("Phản hồi LLM không chứa JSON")
        try:
            data = json.loads(text[start:end + 1])
        except json.JSONDecodeError as exc:
            raise LLMError(f"JSON không hợp lệ: {exc}") from exc
        if not isinstance(data, dict):
            raise LLMError("JSON phải là object")
        return data


def is_configured() -> bool:
    return bool(settings.groq_api_key)


async def chat(
    messages: list[dict[str, Any]],
    *,
    model: str | None = None,
    tools: list[dict] | None = None,
    json_mode: bool = False,
    temperature: float = 0.2,
    max_tokens: int = 900,
    timeout_s: float | None = None,
) -> LLMReply:
    if not is_configured():
        raise LLMError("Chưa cấu hình GROQ_API_KEY — LLM đang tắt")
    body: dict[str, Any] = {
        "model": model or settings.llm_model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    t0 = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=timeout_s or settings.llm_timeout_s) as client:
            res = await client.post(
                f"{settings.groq_base_url}/chat/completions",
                headers={"Authorization": f"Bearer {settings.groq_api_key}"},
                json=body,
            )
    except httpx.TimeoutException as exc:
        raise LLMError(f"LLM quá thời gian chờ ({timeout_s or settings.llm_timeout_s:.0f}s)") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"Không kết nối được Groq: {exc}") from exc
    latency = (time.perf_counter() - t0) * 1000.0
    if res.status_code != 200:
        try:
            msg = res.json().get("error", {}).get("message", res.text)
        except ValueError:
            msg = res.text
        raise LLMError(f"Groq HTTP {res.status_code}: {msg[:300]}")
    data = res.json()
    try:
        msg = data["choices"][0]["message"]
    except (KeyError, IndexError) as exc:
        raise LLMError("Phản hồi Groq thiếu choices") from exc
    return LLMReply(
        content=msg.get("content") or "",
        tool_calls=msg.get("tool_calls") or [],
        model=data.get("model", body["model"]),
        latency_ms=latency,
        usage=data.get("usage", {}),
    )
