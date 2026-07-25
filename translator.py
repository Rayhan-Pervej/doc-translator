"""
Bedrock Claude translation helper.
Loads config from .env and sends text to Claude via AWS Bedrock.
"""

import json
import os
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError

# Load .env if python-dotenv is available, otherwise rely on env vars already set
try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env", override=True)
except ImportError:
    pass

MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "us.anthropic.claude-sonnet-4-6")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")

_client = None


def _get_client():
    global _client
    if _client is None:
        kwargs = {"region_name": AWS_REGION}
        # Only pass explicit keys if set — allows IAM role / AWS CLI profile too
        key_id = os.environ.get("AWS_ACCESS_KEY_ID")
        secret = os.environ.get("AWS_SECRET_ACCESS_KEY")
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
            response = _get_client().invoke_model(
                modelId=MODEL_ID,
                body=json.dumps(body),
            )
            result = json.loads(response["body"].read())
            return result["content"][0]["text"].strip()
        except ClientError as e:
            if e.response["Error"]["Code"] == "ThrottlingException":
                wait = 2 ** attempt * 5
                print(f"  Rate limited, waiting {wait}s...")
                time.sleep(wait)
            else:
                raise
    raise RuntimeError("Translation failed after 3 attempts due to rate limiting")


def translate(text: str, context: str = "") -> str:
    """Translate Japanese text to English."""
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
    """Translate a Japanese folder or file name to a clean English slug."""
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
- Do not add explanations — return ONLY the translated name

Japanese name: {name}"""

    translated = _invoke(prompt, max_tokens=200)
    return translated.strip('"\'')
