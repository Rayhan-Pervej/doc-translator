# Notes

## Bedrock Prompt Caching TTL

| Type | TTL | Use Case |
|---|---|---|
| `ephemeral` | 5 min | Batch runs: timer resets on every hit, stays alive during continuous calls |
| `ephemeral_1h` | 1 hour | Long-running jobs with slow/paused chunks between calls |

> Cache is currently NOT active. Bedrock requires minimum 1024 tokens in the system prompt to enable caching. Our system prompt is ~80 tokens.
> To enable: expand the system prompt to 1024+ tokens (e.g. add a glossary, domain rules, or examples) and add `cache_control: {"type": "ephemeral"}` to the system block. Cache read is billed at 0.1x, write at 1.25x, saves ~90% on input tokens after the first call.

## Network Drop Mid-API Call

- Bedrock does NOT charge for dropped calls, billing only happens on successful response
- Risk is lost time, not cost: the chunk must be retried from scratch
- Current code does NOT catch `APIConnectionError`, a network blip will crash the run
- Fix: catch `APIConnectionError` in `_invoke()` and retry with same backoff (5s, 10s, 20s)
- After 3 failed retries: chunk falls back to originals (untranslated, zero cost)

## DONE: Dynamic Chunk Sizing (replace fixed BATCH_CHUNK_SIZE = 40)

Implemented via local `_estimate_output_tokens()` in `common.py`, no API call needed.
Chunks split when estimated output tokens exceed `OUTPUT_TOKEN_BUDGET = 6000` OR string count hits `MAX_STRINGS_PER_CHUNK = 80`.

- Short strings: more per chunk (up to 80)
- Long strings: fewer per chunk (output budget kicks in first)
- No API calls, instant, runs before every batch

## TODO: Detect & Retry Untranslated Japanese

In `batch_translate()` in `common.py`, covers all file types (xlsx, docx, txt).
PDF has its own loop in `pdf.py`, handle separately.

Flow:
1. After translation, scan each output value for remaining Japanese characters
2. Collect strings that still have Japanese, re-send as a second translate call
3. Still Japanese after retry: console warn only (never visible in the document)

## TODO: Glossary / Terminology Consistency

Option A (already implemented): file name + folder path passed as context to every API call.
Claude infers domain terminology from it (e.g. financial file uses financial terms).

Option B (future): add a `glossary.json` with approved term mappings (e.g. Revenue for sales terms).
Inject into system prompt so Claude always uses client-approved terms across all chunks.

> Option A is good enough for now. Add Option B only if a client needs strict terminology control.
