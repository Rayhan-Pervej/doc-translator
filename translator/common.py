"""
Shared helpers: Japanese detection, XML escaping, batch translation.
Used by all handlers and the estimator.
"""

import json
import re

from .client import translate

OUTPUT_TOKEN_BUDGET   = 6000
MAX_STRINGS_PER_CHUNK = 80

SYSTEM_PROMPT = (
    "You are a professional Japanese-to-English translator.\n"
    "Rules:\n"
    "- Translate ONLY Japanese text. Leave English, numbers, symbols, and formulas unchanged.\n"
    "- Use natural, professional English.\n"
    "- Do NOT add notes, explanations, or extra text.\n"
    "- If a string is already English, return it as-is.\n\n"
    "Example input:\n"
    "[1] 採用資料\n"
    "[2] 報告書\n"
    "[3] Unit Price\n\n"
    "Example output:\n"
    '["Recruitment Materials", "Report", "Unit Price"]'
)


def has_japanese(text: str) -> bool:
    return any(0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF for c in text)


def jp_char_count(text: str) -> int:
    return sum(1 for c in text if 0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF)


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def xml_unescape(s: str) -> str:
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'"))


def _estimate_output_tokens(s: str) -> int:
    """Estimate output tokens for one string's English translation — used by _build_chunks()
    to keep each chunk under OUTPUT_TOKEN_BUDGET before sending to the API. Never makes an
    API call. JP chars expand to ~0.7 English words, each word ~0.4 tokens, +15 overhead."""
    jp   = sum(1 for c in s if 0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF)
    rest = len(s) - jp
    return int((jp * 0.7 + rest) * 0.4) + 15


def _build_chunks(unique: list[str]) -> list[list[str]]:
    chunks: list[list[str]] = []
    current: list[str] = []
    budget = 0
    for s in unique:
        est = _estimate_output_tokens(s)
        if current and (budget + est > OUTPUT_TOKEN_BUDGET or len(current) >= MAX_STRINGS_PER_CHUNK):
            chunks.append(current)
            current = []
            budget = 0
        current.append(s)
        budget += est
    if current:
        chunks.append(current)
    return chunks


def _parse_array(raw: str) -> list[str] | None:
    """Extract a JSON array from Claude's response, stripping markdown fences if present."""
    # strip ```json ... ``` or ``` ... ``` fences
    raw = re.sub(r"```(?:json)?\s*", "", raw).strip()
    # find the first [ ... ] in the response
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group())
        if isinstance(data, list) and all(isinstance(x, str) for x in data):
            return data
        return None
    except json.JSONDecodeError:
        return None


def _translate_chunk(chunk: list[str], context: str) -> dict[str, str]:
    n = len(chunk)
    numbered = "\n".join(f"[{i+1}] {s}" for i, s in enumerate(chunk))
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        f"You are translating: {context}\n\n"
        f"Translate the following {n} Japanese texts to English.\n"
        f"Return ONLY a JSON array with EXACTLY {n} strings in the same order.\n"
        f"No extra text, no explanation, no markdown — just the array.\n\n"
        f"{numbered}"
    )

    print(f"    [debug] sending {n} strings, first 3: {chunk[:3]}")

    best: list[str] | None = None
    for attempt in range(3):
        raw = translate(prompt, context="")
        data = _parse_array(raw)

        if data is not None and len(data) == n:
            result = {chunk[i]: data[i] for i in range(n)}
            sample = dict(list(result.items())[:3])
            print(f"    [debug] got {n} translations, sample: {sample}")
            return result

        if data is not None and len(data) > 0:
            if best is None or len(data) > len(best):
                best = data
            print(f"    [warn] expected {n} items, got {len(data)} on attempt {attempt+1}/3, retrying...")
        else:
            print(f"    [warn] invalid/empty response on attempt {attempt+1}/3, retrying...")

    # partial best result — map what we have, leave the rest for individual fallback
    result: dict[str, str] = {}
    if best:
        for i in range(min(len(best), n)):
            if best[i].strip():
                result[chunk[i]] = best[i]
        print(f"    [warn] using partial result: {len(result)}/{n} strings")

    return result


def _translate_single(text: str, context: str) -> str:
    """Fallback: translate one string individually."""
    result = translate(text, context=context)
    return result if result and result.strip() else text


def batch_translate(texts: list[str], context: str) -> dict[str, str]:
    """Translate a list of Japanese strings. Returns {original: translated}."""
    unique = list(dict.fromkeys(t for t in texts if t.strip() and has_japanese(t)))
    if not unique:
        return {}

    chunks = _build_chunks(unique)
    print(f"  [batch] {len(unique)} unique strings → {len(chunks)} chunk(s)")

    result: dict[str, str] = {}
    for chunk_num, chunk in enumerate(chunks, 1):
        chunk_result = _translate_chunk(chunk, context)
        result.update(chunk_result)

        missing = [t for t in chunk if t not in chunk_result]
        if missing:
            print(f"    [retry] {len(missing)} string(s) missing from chunk {chunk_num}, retrying individually:")
            for s in missing:
                print(f"      → {s[:60]}")
                result[s] = _translate_single(s, context)

    return result
