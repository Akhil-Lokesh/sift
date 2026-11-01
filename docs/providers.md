# Provider facts

Read from official documentation on **2026-11-01**. Re-check before any paid run. Prices are USD.
`src/sift/pricing.py` mirrors the numbers below. If either changes, update both.

## Claude (answering models)

Sources:
- Pricing: https://platform.claude.com/docs/en/about-claude/pricing
- Prompt caching: https://platform.claude.com/docs/en/build-with-claude/prompt-caching

### Model identifiers and prices (per million tokens)

| Role | Model ID | Input | 5m cache write | 1h cache write | Cache read | Output |
|---|---|---|---|---|---|---|
| small | `claude-haiku-5-5` (prompt ≤ 100K) | $0.10 | $0.125 | $0.20 | $0.01 | $0.50 |
| small | `claude-haiku-5-5` (prompt > 100K) | $0.50 | $0.625 | $1.00 | $0.05 | $2.50 |
| medium | `claude-sonnet-5-5` | $2.00 | $2.50 | $4.00 | $0.10 | $10.00 |
| large | `claude-opus-5-5` | $4.00 | $5.00 | $8.00 | $0.20 | $20.00 |

Multipliers on base input:
- A cache write is 1.25x for the 5-minute lifetime and 2x for the 1-hour lifetime.
- A cache read is 0.05x on Opus 5.5 and Sonnet 5.5, and 0.1x on Haiku 5.5. The spec draft was unsure about Haiku. The pricing table resolves it: $0.01 on $0.10 is 0.1x.

Haiku 5.5 is priced per request on its total prompt length, including cache reads and writes. Once a prompt passes 100K tokens, every token in that request is billed at the higher price. Our conversations should stay far below this, but `pricing.py` handles it anyway.

The pricing page also lists `inference_geo="us"` at a 1.1x multiplier. We do not use it, and requests route globally.

Corrections to the spec draft:
- The draft said Haiku 5.5 and Sonnet 5.5 prices "differed across sources". The figures above come from the official table.
- Opus 5.5 at $4/$20 is confirmed.

### Prompt caching rules

- **Minimum cacheable prompt is 512 tokens** on Opus 5.5, Sonnet 5.5 and Haiku 5.5. A shorter prefix is silently not cached, with no error, and reports `cache_creation_input_tokens: 0`.
- **Lifetimes:** 5 minutes by default, or 1 hour with `"cache_control": {"type": "ephemeral", "ttl": "1h"}`. The lifetime runs from the *start* of the request that writes or reads the entry. A read refreshes the timer at no extra cost.
- **Caching is opt-in, not automatic.** This corrects spec §5, which says "the provider handles the cache automatically". A request must carry `cache_control`, either:
  - at the top level, so the API places the breakpoint on the last cacheable block and moves it forward as the conversation grows, or
  - on individual content blocks, with at most 4 breakpoints per request.
- **Lookback window is 20 blocks.** For each breakpoint, the API checks at most 20 earlier block positions for a matching cached entry. This matters for prompt building: when groups change, the matching prefix may sit more than 20 blocks back. Decide in step 6 whether to put explicit breakpoints at group boundaries.
- **A hit needs 100% identical prompt segments** up to and including the marked block. Render order is `tools`, then `system`, then `messages`.
- **Isolation:** caches are isolated per organization and per workspace.
- **Per-model scope:** the caching page does not say that caches are per model. The skill reference notes that "caches are model-scoped". Spec §2 assumes per-model caches. **Verify empirically in step 2**: send the same prompt to two models and check `cache_read_input_tokens`.
- **Usage fields in each response:**
  - `input_tokens` counts only the tokens after the last breakpoint.
  - `cache_read_input_tokens`.
  - `cache_creation_input_tokens`, with a TTL breakdown in `cache_creation.ephemeral_5m_input_tokens` and `cache_creation.ephemeral_1h_input_tokens`.
  - Total prompt = `input_tokens` + `cache_read_input_tokens` + `cache_creation_input_tokens`.

### API notes for the 5.5 models (from the Anthropic SDK skill reference)

- **Thinking cannot be disabled on Opus 5.5.** Sending `{type: "disabled"}` returns a 400, so control cost with `output_config.effort`.
  - Opus 5.5 and Haiku 5.5 default to `medium` effort. Sonnet 5.5 defaults to `high`.
  - **Pin effort explicitly for all three models**, or the comparison mixes in different effort defaults.
  - Thinking tokens are billed as output, so they belong in the cost.
- **Changing effort mid-conversation invalidates the message cache**, unless it is done through the per-message effort system message (beta). Keep effort fixed per model for a run.
- **Assistant prefill returns a 400** on all three models.
- **Responses with `stop_reason: "refusal"`** must be handled before reading `content`.

## Jev (decision model, TypeSafe AI)

Sources:
- Models: https://docs.typesafe.ai/models.md
- System One endpoint: https://docs.typesafe.ai/api/system-one.md
- Python SDK: https://docs.typesafe.ai/sdk/python.md
- Sync client: https://docs.typesafe.ai/sdk/python/api/clients/sync.md

### Models

| Model ID | Notes |
|---|---|
| `jev-1.14.0` | Newest release, available since 2026-10-14 |
| `jev-1.13.0` | Same price and limits as 1.14 |

- The aliases `jev-latest` and `jev-preview` both currently point to `jev-1.14.0`. They move when a new release ships, so **never use an alias in experiments**. Pin `jev-1.14.0`.
- Each response's `model` field reports which ID answered. Log it.

### Endpoint

- Request: `POST https://api.typesafe.ai/v1/systemone`, with header `Authorization: Bearer $TYPESAFE_API_KEY`.
- Model list: `GET /v1/models`.
- Python SDK: `typesafe-sdk`, with clients `TypeSafeClient` and `AsyncTypeSafeClient`. It reads `TYPESAFE_API_KEY`.

### Request

The request has three fields: `model`, `state` (a string, object, or array), and `questions` (`{name: question}`).

| Type | `criteria` | Answer fields |
|---|---|---|
| `noul` | Optional `{"true": desc, "false": desc}` | `noul` = P(yes), from 0 to 1. No confidence field. |
| `choice` | Required `{option: desc or null}`, 1 to 255 options | `choice`, `confidence`, `probabilities` (sum to about 1) |
| `score` | Required ordered list of **1 to 10** levels, indexed from 0 | `score` (probability-weighted, can be fractional), `legend`, `probabilities`, `confidence` |
| `box` | (image localisation) | Not used. It needs images plus a "danger zone" header. |

Each question carries its text in `instructions`.

Corrections to spec §4:
- The spec says there are "exactly three question types". There is a fourth, `box`, which works on images only. It is irrelevant here.
- The spec says Score takes "2 to 10 levels". The API allows 1 to 10.

### Response

- `model`: the ID that answered.
- `answers`: keyed by question name.
- `usage`: `input_tokens` (billable) and `output_tokens` (currently free).
- Errors: `400` returns a `detail` field, and `422` returns field errors.

### Limits and price

- **Context:** 64K tokens per request, covering the state plus all questions, and 32K per question, covering the state plus one question.
  - The optional header `TypeSafe-Danger-Zone-Long-Context: true` raises both limits to 262K. Same price, but the docs say it is slower and less accurate. **Do not use it.**
- **Price:** $0.042 per million input tokens. Output is free. Jev 1.13 and 1.14 cost the same.
- **Rate limits:** set per organization, in tokens per second and requests per second. They appear at `console.typesafe.ai/rate-limits`. Over the limit, the API returns 429, and the SDK retries.
- **Latency:** not documented on these pages. The 70–500 ms range in the spec is a vendor claim. Measure it in step 1.

## Still unverified

- Whether Claude caches are scoped per model. Test in step 2.
- Jev latency and calibration. Measure in step 1 and step 8.
- Alternative decision models: Microsoft-Decision-1, OpenAI Decisions API, SemIf, Kev, Laya, InnerJev. Not checked yet. Check availability and licence before the comparison experiment.
- Which accounts and keys the owner has. `scripts/check_access.py` reports this.
