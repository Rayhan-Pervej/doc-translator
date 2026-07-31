"""
Bedrock Claude client: API calls, retry logic, token tracking.
"""

import json
import os
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent.parent / ".env", override=True)
except ImportError:
    pass

MODEL_ID   = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_client = None  # lazy-initialized on first API call
_usage  = {"input_tokens": 0, "output_tokens": 0}  # accumulates across all calls in a run


def get_actual_usage() -> dict:
    inp  = _usage["input_tokens"]
    out  = _usage["output_tokens"]
    cost = inp / 1_000_000 * 3.00 + out / 1_000_000 * 15.00
    return {"input_tokens": inp, "output_tokens": out, "cost_usd": cost}


def _get_client():
    global _client
    if _client is None:
        kwargs = {"region_name": AWS_REGION}
        key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
        # if keys are not in .env, boto3 falls back to ~/.aws/credentials automatically
        if key_id and secret:
            kwargs["aws_access_key_id"] = key_id
            kwargs["aws_secret_access_key"] = secret
        _client = boto3.client("bedrock-runtime", **kwargs)
    return _client


def _invoke(prompt: str, max_tokens: int = 8096) -> str:
    body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    for attempt in range(3):
        try:
            response = _get_client().invoke_model(modelId=MODEL_ID, body=json.dumps(body))
            result   = json.loads(response["body"].read())
            usage    = result.get("usage", {})
            # track real token usage so we can compare against the estimate at the end
            _usage["input_tokens"]  += usage.get("input_tokens", 0)
            _usage["output_tokens"] += usage.get("output_tokens", 0)
            return result["content"][0]["text"].strip()
        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                # exponential backoff: 5s, 10s, 20s
                wait = 2 ** attempt * 5
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Translation failed after 3 attempts due to rate limiting")


def translate(text: str, context: str = "") -> str:
    if not text or not text.strip():
        return text
    context_block = f"\nContext: {context}" if context else ""
    prompt = f"""You are a professional Japanese-to-English translator.{context_block}

Translate the following Japanese text to natural, professional English.

Rules:
- Preserve all formatting: line breaks, bullet points, numbering, table structure
- Do not translate proper nouns, product names, company names unless a standard English equivalent is well-known
- Maintain the same formal or informal register as the original
- If text is already in English, return it unchanged
- Return ONLY the translated text, no explanations or notes

Japanese text:
{text}"""
    return _invoke(prompt, max_tokens=8096)


def translate_name(name: str, context: str = "") -> str:
    if not name or not name.strip():
        return name
    context_block = f"\nContext: {context}" if context else ""
    prompt = f"""You are translating a Japanese file or folder name to English for use in a file system.{context_block}

Translate this Japanese name to English: {name}

Rules:
- Return a clean, concise English name
- Use the same capitalization style as the original (if it looks like a title, use Title Case; if lowercase, use lowercase)
- Keep it short and meaningful
- Do not use special characters except hyphens and underscores
- Do not add explanations, return ONLY the translated name

Japanese name: {name}"""
    return _invoke(prompt, max_tokens=200).strip('"\'')
