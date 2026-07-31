"""
Bedrock Claude client: API calls, retry logic, token tracking.
"""

import os
import time
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel
from anthropic import AnthropicBedrock, RateLimitError, APIStatusError

T = TypeVar("T", bound=BaseModel)

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

MODEL_ID   = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_client = None  # lazy-initialized on first API call
_usage  = {"input_tokens": 0, "output_tokens": 0}

SYSTEM_TRANSLATE = [
    {
        "type": "text",
        "text": (
            "You are a professional Japanese-to-English translator.\n"
            "Rules:\n"
            "- Preserve all formatting: line breaks, bullet points, numbering, table structure\n"
            "- Do not translate proper nouns, product names, company names unless a standard English equivalent is well-known\n"
            "- Maintain the same formal or informal register as the original\n"
            "- If text is already in English, return it unchanged\n"
            "- Return ONLY the translated text, no explanations or notes"
        ),
    }
]

SYSTEM_TRANSLATE_NAME = [
    {
        "type": "text",
        "text": (
            "You are translating Japanese file and folder names to English for use in a file system.\n"
            "Rules:\n"
            "- Return a clean, concise English name\n"
            "- Use the same capitalization style as the original (title case for titles, lowercase for lowercase)\n"
            "- Keep it short and meaningful\n"
            "- Do not use special characters except hyphens and underscores\n"
            "- Do not add explanations, return ONLY the translated name"
        ),
    }
]


def get_actual_usage() -> dict:
    inp  = _usage["input_tokens"]
    out  = _usage["output_tokens"]
    cost = inp / 1_000_000 * 3.00 + out / 1_000_000 * 15.00
    return {"input_tokens": inp, "output_tokens": out, "cost_usd": cost}


def _get_client() -> AnthropicBedrock:
    global _client
    if _client is None:
        kwargs = {"aws_region": AWS_REGION}
        key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
        # if keys are not in .env, SDK falls back to ~/.aws/credentials automatically
        if key_id and secret:
            kwargs["aws_access_key"] = key_id
            kwargs["aws_secret_key"] = secret
        _client = AnthropicBedrock(**kwargs)
    return _client


def _invoke(system: list, prompt: str, max_tokens: int = 8096) -> str:
    for attempt in range(3):
        try:
            message = _get_client().messages.create(
                model=MODEL_ID,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
            usage = message.usage
            _usage["input_tokens"]  += usage.input_tokens
            _usage["output_tokens"] += usage.output_tokens
            return message.content[0].text.strip()
        except RateLimitError:
            wait = 2 ** attempt * 5  # backoff: 5s, 10s, 20s
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
        except APIStatusError as e:
            if e.status_code < 500:
                raise
            wait = 2 ** attempt * 5
            print(f"  Server error {e.status_code}, waiting {wait}s...")
            time.sleep(wait)
    raise RuntimeError("Translation failed after 3 attempts")


def translate(text: str, context: str = "") -> str:
    if not text or not text.strip():
        return text
    context_line = f"\nContext: {context}" if context else ""
    prompt = f"{context_line}\n\nJapanese text:\n{text}".lstrip()
    return _invoke(SYSTEM_TRANSLATE, prompt, max_tokens=8096)


def translate_name(name: str, context: str = "") -> str:
    if not name or not name.strip():
        return name
    context_line = f"\nContext: {context}" if context else ""
    prompt = f"{context_line}\n\nJapanese name: {name}".lstrip()
    return _invoke(SYSTEM_TRANSLATE_NAME, prompt, max_tokens=200).strip('"\'')


def translate_structured(prompt: str, model: type[T]) -> T | None:
    """Call Claude with structured output enforced by Pydantic schema.
    Returns None on failure so the caller can retry.
    """
    for attempt in range(3):
        try:
            message = _get_client().messages.parse(
                model=MODEL_ID,
                max_tokens=8096,
                system=SYSTEM_TRANSLATE,
                messages=[{"role": "user", "content": prompt}],
                output_format=model,
            )
            usage = message.usage
            _usage["input_tokens"]  += usage.input_tokens
            _usage["output_tokens"] += usage.output_tokens
            return message.parsed_output
        except RateLimitError:
            wait = 2 ** attempt * 5
            print(f"  Rate limited, waiting {wait}s...")
            time.sleep(wait)
        except APIStatusError as e:
            if e.status_code < 500:
                raise
            wait = 2 ** attempt * 5
            print(f"  Server error {e.status_code}, waiting {wait}s...")
            time.sleep(wait)
        except Exception:
            return None
    return None
