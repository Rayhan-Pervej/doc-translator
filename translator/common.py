"""
Shared helpers: Japanese detection, XML escaping, batch translation.
Used by all handlers and the estimator.
"""

from .client import translate

BATCH_CHUNK_SIZE = 40


def has_japanese(text: str) -> bool:
    return any(0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF for c in text)


def jp_char_count(text: str) -> int:
    return sum(1 for c in text if 0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF)


def xml_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def xml_unescape(s: str) -> str:
    return (s.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'"))


def _translate_chunk(chunk: list[str], context: str) -> dict[str, str]:
    numbered = "\n".join(f"[{i+1}] {t}" for i, t in enumerate(chunk))
    prompt = (
        f"Translate the Japanese portions of each numbered text segment to English.\n"
        f"Return ONLY the translations, one per line, keeping the same [N] numbering.\n"
        f"Rules:\n"
        f"- Translate ONLY Japanese text. Leave English, numbers, symbols, and formulas unchanged.\n"
        f"- Do NOT add notes or extra text.\n\n"
        f"Context: {context}\n\n"
        f"{numbered}"
    )
    raw = translate(prompt, context="")
    result: dict[str, str] = {}
    for ln in raw.splitlines():
        ln = ln.strip()
        if ln.startswith("[") and "]" in ln:
            try:
                idx = int(ln[1:ln.index("]")])
                val = ln[ln.index("]") + 1:].strip()
                result[chunk[idx - 1]] = val
            except (ValueError, IndexError):
                pass
    return result


def batch_translate(texts: list[str], context: str) -> dict[str, str]:
    """Translate a list of unique Japanese strings. Returns {original: translated}."""
    unique = list(dict.fromkeys(t for t in texts if t.strip() and has_japanese(t)))
    if not unique:
        return {}
    result: dict[str, str] = {}
    for i in range(0, len(unique), BATCH_CHUNK_SIZE):
        chunk = unique[i:i + BATCH_CHUNK_SIZE]
        chunk_result = _translate_chunk(chunk, context)
        result.update(chunk_result)
        missing = [t for t in chunk if t not in chunk_result]
        if missing:
            chunk_num = i // BATCH_CHUNK_SIZE + 1
            print(f"    [warn] {len(missing)} string(s) not returned by API in chunk {chunk_num}, keeping originals")
    return result
