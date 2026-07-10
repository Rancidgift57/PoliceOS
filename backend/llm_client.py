"""
Shared LLM client for OpenRouter (https://openrouter.ai).

Why OpenRouter over calling OpenAI directly:
- One API key, one bill, access to Claude / Llama / Gemini / Mistral / DeepSeek
  etc. - useful here because the evaluator (needs strict logic) and the
  generator (needs voice/creativity) often want *different* models, and
  OpenRouter lets you pick per-call without juggling multiple provider keys.
- OpenAI-compatible /chat/completions endpoint, so the official `openai`
  Python SDK works unmodified - just point base_url at OpenRouter.

Why not `client.beta.chat.completions.parse(...)`:
That convenience method is OpenAI-proprietary structured-output plumbing and
isn't guaranteed to work across arbitrary OpenRouter-routed models. Instead
we ask the model for `response_format={"type": "json_object"}` (widely
supported) plus an explicit "return ONLY JSON" instruction, then validate
the result against a Pydantic model ourselves - with one repair retry if the
model wraps the JSON in prose or markdown fences.

Swapping to Hugging Face Inference Providers instead of OpenRouter:
Hugging Face's router (https://router.huggingface.co/v1) is ALSO
OpenAI-compatible as of their newer Inference Providers API, so this same
client works by just changing BASE_URL and the API key env var - see the
HF_* constants below, commented out. The JSON-mode reliability varies more
by underlying model on HF, so keep the repair-retry path either way.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Type, TypeVar

from openai import AsyncOpenAI
from pydantic import BaseModel, ValidationError

logger = logging.getLogger("llm_client")

T = TypeVar("T", bound=BaseModel)

# --- OpenRouter (default) ---------------------------------------------------
BASE_URL = os.environ.get("LLM_BASE_URL", "https://openrouter.ai/api/v1")
API_KEY = os.environ.get("OPENROUTER_API_KEY", os.environ.get("LLM_API_KEY", ""))

# --- Hugging Face Inference Providers (alternative) -------------------------
# BASE_URL = os.environ.get("LLM_BASE_URL", "https://router.huggingface.co/v1")
# API_KEY = os.environ.get("HF_TOKEN", os.environ.get("LLM_API_KEY", ""))

client = AsyncOpenAI(
    base_url=BASE_URL,
    api_key=API_KEY,
    default_headers={
        # OpenRouter uses these purely for its public leaderboard attribution;
        # harmless no-ops on other providers.
        "HTTP-Referer": os.environ.get("APP_URL", "https://police-os.local"),
        "X-Title": "Police OS",
    },
)

# Sensible free/cheap defaults - override via env vars per deployment.
EVALUATOR_MODEL = os.environ.get("EVALUATOR_MODEL", "anthropic/claude-3.5-haiku")
GENERATOR_MODEL = os.environ.get("GENERATOR_MODEL", "meta-llama/llama-3.3-70b-instruct")
NARRATIVE_MODEL = os.environ.get("NARRATIVE_MODEL", "anthropic/claude-3.5-sonnet")

# Fallback chain: if the primary model errors out (rate limit, provider
# outage - common on OpenRouter when a specific upstream is overloaded),
# retry once against a different model before giving up.
FALLBACK_MODEL = os.environ.get("FALLBACK_MODEL", "google/gemini-2.0-flash-001")


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1] if text.count("```") >= 2 else text.strip("`")
        text = text.removeprefix("json").strip()
    return text


async def structured_completion(
    schema: Type[T],
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 600,
) -> T:
    """Calls an OpenRouter/HF chat model and validates the JSON reply
    against `schema`, with a fallback model on failure."""
    full_system = (
        f"{system_prompt}\n\n"
        f"Respond with ONLY a single valid JSON object matching this shape "
        f"(no prose, no markdown fences):\n{json.dumps(schema.model_json_schema())}"
    )

    for attempt_model in (model, FALLBACK_MODEL):
        try:
            response = await client.chat.completions.create(
                model=attempt_model,
                messages=[
                    {"role": "system", "content": full_system},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content
            return schema.model_validate_json(_strip_code_fence(raw))
        except (ValidationError, json.JSONDecodeError, ValueError) as exc:
            logger.warning("structured_completion parse failed on %s: %s", attempt_model, exc)
        except Exception as exc:  # provider/network error -> try fallback
            logger.warning("structured_completion request failed on %s: %s", attempt_model, exc)

    raise RuntimeError(f"structured_completion failed on both {model} and {FALLBACK_MODEL}")


async def text_completion(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 200,
) -> str:
    """Plain text completion (used for in-character dialogue) with the same
    fallback behavior as structured_completion."""
    for attempt_model in (model, FALLBACK_MODEL):
        try:
            response = await client.chat.completions.create(
                model=attempt_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("text_completion request failed on %s: %s", attempt_model, exc)

    raise RuntimeError(f"text_completion failed on both {model} and {FALLBACK_MODEL}")


async def stream_text_completion(
    system_prompt: str,
    user_prompt: str,
    model: str,
    temperature: float = 0.7,
    max_tokens: int = 200,
):
    """Async generator yielding text chunks as they arrive, for the
    Secure Messenger's SSE endpoint. Falls back to the fallback model if the
    primary stream errors before yielding anything; once a stream has
    started yielding content, a mid-stream error is surfaced to the caller
    rather than silently retried (retrying would duplicate partial text the
    client already rendered)."""
    for attempt_model in (model, FALLBACK_MODEL):
        yielded_anything = False
        try:
            stream = await client.chat.completions.create(
                model=attempt_model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    yielded_anything = True
                    yield delta
            return
        except Exception as exc:
            logger.warning("stream_text_completion failed on %s: %s", attempt_model, exc)
            if yielded_anything:
                raise

    raise RuntimeError(f"stream_text_completion failed on both {model} and {FALLBACK_MODEL}")
