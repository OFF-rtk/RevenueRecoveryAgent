"""
core/llm/client.py
──────────────────
Deterministic, observable Groq LLM client wrapper.

Contract (enforced here, not by callers):
  - temperature is always 0 — callers cannot override this.
  - The system prompt always comes from a versioned file in /prompts/.
  - A SHA-256 hash of the prompt file is logged with every call.
  - Retries (up to 3×, exponential back-off) on transient Groq errors.
  - Non-retryable errors re-raise immediately with a structured ERROR log.
  - No writes to audit_events here — that is the responsibility of the
    layer above (diagnosis, intervention, etc.). This keeps the wrapper
    independently testable without a database.

Usage:
    from core.llm.client import call_llm
    from core.config import settings

    result = await call_llm(
        prompt_version="diagnosis_v1",
        model=settings.groq_tier1_model,
        user_messages=[{"role": "user", "content": case_context}],
    )
    print(result.content)      # the model's reply
    print(result.latency_ms)   # wall-clock ms
    print(result.prompt_hash)  # for audit trail logging one layer up
"""
import asyncio
import hashlib
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
from groq import APIConnectionError, APITimeoutError, AsyncGroq, BadRequestError, RateLimitError

log = structlog.get_logger()

# /prompts/ lives at the repo root — two levels above this file
PROMPTS_DIR = Path(__file__).parent.parent.parent / "prompts"

# Errors that are safe to retry (transient infrastructure issues)
_RETRYABLE = (RateLimitError, APITimeoutError, APIConnectionError)
_MAX_RETRIES = 10
_RETRY_BASE_DELAY_S = 1.0  # doubles each attempt: 1s, 2s, 4s


@dataclass(frozen=True)
class LLMResponse:
    """Structured return value from a single LLM call."""

    content: str
    model: str
    prompt_version: str
    prompt_hash: str      # first 12 hex chars of SHA-256 of the prompt file
    input_tokens: int
    output_tokens: int
    latency_ms: float


def _load_prompt(prompt_version: str) -> tuple[str, str]:
    """
    Read the versioned prompt file and return (content, hash_prefix).
    Raises FileNotFoundError loudly if the file is missing — a missing prompt
    is a code error, not a runtime condition to swallow.
    """
    path = PROMPTS_DIR / f"{prompt_version}.txt"
    if not path.exists():
        raise FileNotFoundError(
            f"Prompt file not found: {path}  "
            f"(PROMPTS_DIR={PROMPTS_DIR}, cwd={Path.cwd()})"
        )
    content = path.read_text(encoding="utf-8").strip()
    digest = hashlib.sha256(content.encode()).hexdigest()[:12]
    return content, digest


async def call_llm(
    prompt_version: str,
    model: str,
    user_messages: list[dict[str, Any]],
    api_key: str | None = None,
    base_url: str | None = None,
    **kwargs: Any,
) -> LLMResponse:
    """
    Make one deterministic Groq chat-completion call.

    Args:
        prompt_version: Filename stem under /prompts/ (e.g. "diagnosis_v1").
                        The file provides the system prompt.
        model:          Groq model ID (e.g. settings.groq_tier1_model).
        user_messages:  List of {"role": ..., "content": ...} dicts appended
                        after the system prompt. Typically one user message.
        api_key:        Optional API key override. If not provided, uses the default from settings.
        **kwargs:       Passed through to the Groq client (e.g. max_tokens).
                        temperature is silently stripped — always 0.

    Returns:
        LLMResponse dataclass.

    Raises:
        FileNotFoundError: prompt file missing.
        groq.APIError subclass: after retries are exhausted or on fatal error.
    """
    from core.config import settings  # lazy import avoids circular startup issues

    # ── Enforce determinism (default) ───────────────────────────────────────
    temperature = kwargs.pop("temperature", 0)  # default to 0 for agent, allow override for testing

    # ── Load and hash the versioned prompt ──────────────────────────────────
    system_prompt, prompt_hash = _load_prompt(prompt_version)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        *user_messages,
    ]

    active_api_key = api_key if api_key is not None else settings.groq_api_key
    active_base_url = base_url if base_url is not None else settings.groq_base_url
    client = AsyncGroq(api_key=active_api_key, base_url=active_base_url)

    log.info(
        "llm_call_start",
        prompt_version=prompt_version,
        prompt_hash=prompt_hash,
        model=model,
        message_count=len(messages),
        temperature=temperature,
    )

    last_error: Exception | None = None

    # Ensure the model always has enough room to emit a complete JSON object.
    # Callers may still override via kwargs if needed.
    kwargs.setdefault("max_tokens", 4096)

    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            t0 = time.monotonic()
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                **kwargs,
            )
            latency_ms = (time.monotonic() - t0) * 1000

            content = response.choices[0].message.content or ""
            usage = response.usage

            result = LLMResponse(
                content=content,
                model=model,
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
                input_tokens=usage.prompt_tokens if usage else 0,
                output_tokens=usage.completion_tokens if usage else 0,
                latency_ms=round(latency_ms, 2),
            )

            log.info(
                "llm_call_success",
                prompt_version=prompt_version,
                prompt_hash=prompt_hash,
                model=model,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                latency_ms=result.latency_ms,
                finish_reason=response.choices[0].finish_reason,
                raw_response_preview=content[:500],
            )

            return result

        except _RETRYABLE as exc:
            last_error = exc
            delay = _RETRY_BASE_DELAY_S * (2 ** (attempt - 1))
            
            if isinstance(exc, RateLimitError):
                import re
                m = re.search(r"try again in (?:(\d+)m)?([\d\.]+)s", str(exc))
                if m:
                    mins = int(m.group(1)) if m.group(1) else 0
                    secs = float(m.group(2))
                    delay = (mins * 60) + secs + 5.0  # 5s buffer
                else:
                    delay = max(delay, 20.0)

            log.warning(
                "llm_call_retryable_error",
                prompt_version=prompt_version,
                model=model,
                attempt=attempt,
                max_retries=_MAX_RETRIES,
                error_type=type(exc).__name__,
                error=str(exc),
                retry_delay_s=delay if attempt < _MAX_RETRIES else 0,
            )
            if attempt < _MAX_RETRIES:
                await asyncio.sleep(delay)

        except BadRequestError as exc:
            # json_validate_failed means the model ran out of tokens mid-JSON.
            # Treat as a parse failure so DiagnosisFailedError can be raised
            # by the caller instead of crashing the whole batch.
            if "json_validate_failed" in str(exc) or "Failed to generate JSON" in str(exc):
                log.warning(
                    "llm_call_json_truncated",
                    prompt_version=prompt_version,
                    model=model,
                    attempt=attempt,
                    error=str(exc),
                )
                raise ValueError(f"LLM JSON truncated (max tokens reached): {exc}") from exc
            log.error(
                "llm_call_fatal_error",
                prompt_version=prompt_version,
                model=model,
                attempt=attempt,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise

        except Exception as exc:
            # Non-retryable — log and re-raise immediately
            log.error(
                "llm_call_fatal_error",
                prompt_version=prompt_version,
                model=model,
                attempt=attempt,
                error_type=type(exc).__name__,
                error=str(exc),
            )
            raise

    # All retries exhausted
    log.error(
        "llm_call_exhausted_retries",
        prompt_version=prompt_version,
        model=model,
        attempts=_MAX_RETRIES,
        error_type=type(last_error).__name__ if last_error else "unknown",
        error=str(last_error),
    )
    assert last_error is not None  # always true after the loop
    raise last_error
