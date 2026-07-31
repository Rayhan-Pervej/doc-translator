"""
Shared helpers: Japanese detection, XML escaping, batch translation.
Used by all handlers and the estimator.
"""

from pydantic import BaseModel

from .client import translate, translate_structured

# Output token budget per chunk.
# Each entry: index (1-2 tokens) + EN translation + ~15 tokens JSON overhead.
# Stay well under 8096 max_tokens to avoid Claude cutting off mid-response.
OUTPUT_TOKEN_BUDGET    = 6000
MAX_STRINGS_PER_CHUNK  = 80


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
    """Estimate output tokens for one {index, translation} entry.
    Index is tiny (~2 tokens). Translation is EN output only, no JP string returned.
    EN translation estimated at ~0.7x JP char count at ~0.4 tokens/char.
    Add ~15 tokens for JSON object punctuation.
    """
    jp   = sum(1 for c in s if 0x3000 <= ord(c) <= 0x9FFF or 0xF900 <= ord(c) <= 0xFAFF)
    rest = len(s) - jp
    val_tokens = int((jp * 0.7 + rest) * 0.4)
    return val_tokens + 15


def _build_chunks(unique: list[str]) -> list[list[str]]:
    """Split unique strings into chunks sized by estimated output token budget."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_out = 0

    for s in unique:
        out_tok = _estimate_output_tokens(s)
        if current and (current_out + out_tok > OUTPUT_TOKEN_BUDGET or len(current) >= MAX_STRINGS_PER_CHUNK):
            chunks.append(current)
            current     = [s]
            current_out = out_tok
        else:
            current.append(s)
            current_out += out_tok

    if current:
        chunks.append(current)

    return chunks


def _restore(v: str, orig: str) -> str:
    """Match line break style of original in the translated value."""
    if "\r\n" in orig:
        v = v.replace("\n", "\r\n")
    return v


# Index-based structured output: Claude returns {index, translation} pairs.
# No original string returned, no key matching, no character normalization issues.
# We map back to chunk[index-1] by position, works regardless of what Claude does to text.
class _Entry(BaseModel):
    index:       int
    translation: str

class _Translations(BaseModel):
    translations: list[_Entry]


def _translate_chunk(chunk: list[str], context: str) -> dict[str, str]:
    numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(chunk))
    prompt = (
        f"Translate each numbered Japanese text below to English.\n"
        f"Return a JSON object with a 'translations' array. Each element must have:\n"
        f"  'index': the number from the input (1, 2, 3 ...)\n"
        f"  'translation': the English translation\n"
        f"Rules:\n"
        f"- Translate ONLY Japanese text. Leave English, numbers, symbols unchanged.\n"
        f"- Do NOT add notes or explanations.\n"
        f"- Every index must appear in the output.\n\n"
        f"Example - if input is:\n"
        f"1. 売上高\n"
        f"2. 合計\n"
        f'Output: {{"translations": [{{"index": 1, "translation": "Revenue"}}, '
        f'{{"index": 2, "translation": "Total"}}]}}\n\n'
        f"Context: {context}\n\n"
        f"{numbered}"
    )

    print(f"    [debug] sending {len(chunk)} strings, first 3: {chunk[:3]}")

    best: dict[int, str] = {}  # index to translation

    for attempt in range(3):
        parsed = translate_structured(prompt, _Translations)
        if parsed is not None:
            got = {e.index: e.translation for e in parsed.translations if 1 <= e.index <= len(chunk)}
            if len(got) > len(best):
                best = got
            missing_indices = [i+1 for i in range(len(chunk)) if i+1 not in got]
            if not missing_indices:
                final = {chunk[i-1]: _restore(got[i], chunk[i-1]) for i in got}
                sample = dict(list(final.items())[:3])
                print(f"    [debug] got {len(final)} translations, sample: {sample}")
                return final
            print(f"    [warn] {len(missing_indices)} index(es) missing on attempt {attempt+1}/3, retrying...")
        else:
            print(f"    [warn] Structured output parse failed on attempt {attempt+1}/3, retrying...")

    if best:
        result = {chunk[i-1]: _restore(best[i], chunk[i-1]) for i in best}
        missing_count = len(chunk) - len(result)
        if missing_count:
            print(f"    [warn] Partial result: {len(result)}/{len(chunk)}, {missing_count} go to individual retry")
        return result

    print(f"    [warn] All 3 attempts failed for chunk of {len(chunk)} strings")
    return {}


def _translate_single(text: str, context: str) -> str:
    """Translate one string individually. Fallback for strings dropped by chunk translate."""
    prompt = (
        f"Translate the following Japanese text to natural, professional English.\n"
        f"Rules:\n"
        f"- Translate ONLY Japanese text. Leave English, numbers, symbols unchanged.\n"
        f"- Return ONLY the translated text, no notes or explanations.\n\n"
        f"Context: {context}\n\n"
        f"Japanese text: {text}"
    )
    return _restore(translate(prompt, context="").strip(), text)


def batch_translate(texts: list[str], context: str) -> dict[str, str]:
    """Translate a list of unique Japanese strings. Returns {original: translated}."""
    unique = list(dict.fromkeys(t for t in texts if t.strip() and has_japanese(t)))
    if not unique:
        return {}

    chunks = _build_chunks(unique)
    result: dict[str, str] = {}

    for chunk_num, chunk in enumerate(chunks, 1):
        chunk_result = _translate_chunk(chunk, context)
        result.update(chunk_result)
        missing = [t for t in chunk if t not in chunk_result]
        if missing:
            print(f"    [retry] {len(missing)} string(s) missing from chunk {chunk_num}, retrying individually:")
            for s in missing:
                preview = s[:60].replace("\n", "\\n")
                print(f"      - {preview!r}")
                result[s] = _translate_single(s, context)

    return result
