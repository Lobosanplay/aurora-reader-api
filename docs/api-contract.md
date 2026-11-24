# Aurora Reader API — implemented backend v1 contract

Status: implemented server contract aligned in documentation with
`../aurora-reader-extension/docs/api-contract.md`; **browser integration is not implemented**.
The FastAPI routes, Pydantic schemas and runtime guards are authoritative. Generated
`/openapi.json` confirms `POST /api/v1/translate`, `POST /api/v1/ask`,
`POST /api/v1/transcribe` and `GET /health`; it does not capture every runtime size limit,
audio byte check or access guard. Base URL in local
development: `http://localhost:8000`; production must use HTTPS. OpenAPI: `/openapi.json`,
interactive docs: `/docs`. Only the three routes below are inference endpoints.

## `POST /api/v1/translate`

JSON request (local requests must originate from loopback; production calls require
gateway-only `X-Aurora-API-Key`, never a key embedded in the extension):

```json
{"source_language":"en","target_language":"es","chunks":[{"id":"chunk-001","text":"Neural networks learn patterns."}]}
```

JSON response (illustrative output; live inference not yet verified):

```json
{"source_language":"en","target_language":"es","chunks":[{"id":"chunk-001","text":"Las redes neuronales aprenden patrones."}]}
```

One or more chunks, maximum 20; ID is 1–100 ASCII letters/digits/underscore/hyphen
(`^[A-Za-z0-9_-]+$`), unique
per request; nonblank text maximum 4,000 characters/chunk and 20,000 combined. Translation
preserves count, IDs and order; malformed provider results fail rather than being repaired.
Provider translations that exceed the configured per-chunk or combined character limits fail
`502 BAD_UPSTREAM_RESPONSE`, rather than returning unbounded expanded text.
Same-language requests return unchanged text/IDs without a provider after access, rate and
language checks. Different languages use the selected OpenAI or Gemini adapter or return `503`
when disabled/missing its key. Incomplete structured output or mismatched IDs fail `502`; the
default 600-token text output budget may be too small for long translations. Input text is
document data, never executable instructions.

## `POST /api/v1/ask`

JSON request:

```json
{"question":"¿Qué significa una capa en una red neuronal?","language":"es","context":{"title":"Introduction to Deep Learning","current_chunk":"Neural networks consist of interconnected layers.","related_chunks":["Each layer applies transformations to its inputs."]}}
```

JSON response (illustrative; a configured provider is required):

```json
{"answer":"Una capa transforma información antes de enviarla a la siguiente etapa.","source":"page","context_sufficient":true}
```

Question is nonblank, maximum 1,000 characters. `context` is required; `title` defaults to
empty (max 500 characters), `current_chunk` defaults to empty, `related_chunks` defaults to an
empty list (max five entries). Total raw context size including title is at most 12,000 characters.
The backend sends the labeled page title, then current excerpt and deduplicated related excerpts;
title and excerpt are untrusted data. A contextless question
still requires a provider to produce an insufficiency response. Possible source values in the
proposed v1 vocabulary: `page`, `general`, `insufficient`, `external`, `mixed`; **this backend rejects
`external` and `mixed`** without approved retrieval. `context_sufficient` is true only for `page`.
`general` must identify general model knowledge, not claim that knowledge comes from the page;
`insufficient` indicates no supported answer. The requested language is passed to the provider.
`page` without a nonblank current or related excerpt (including title-only context) is rejected
as `502`. This structural rule does not
verify factual grounding or prove resistance to prompt injection; evaluate real adapters separately.
Answers are limited to 2,000 characters by default and oversized provider results fail `502`,
not silently truncate.
Page context is always untrusted data; the backend does not fetch URLs. With either provider
enabled, structured results are validated, but a source label is not proof of factual grounding.
Requests without an enabled provider/key return `503`.

## `POST /api/v1/transcribe`

Multipart form parts: required `file`; optional `language` hint (e.g. `es`).
Successful response (illustrative; a configured provider is required):

```json
{"text":"¿Qué significa una capa en una red neuronal?","language":"es"}
```

`language` in the response is nullable when unknown. Only `audio/wav` with a complete RIFF/WAVE
structure, mono or stereo PCM (8/16/24/32-bit samples), nonzero rate, consistent chunk lengths,
sample alignment and actual frames is accepted. Filenames are ignored for detection. Ogg and
WebM currently fail `415` pending reliable codec, duration and integrity validation; this is
a deliberate change from the earlier proposed acceptance. Maximum audio content
is 5,000,000 bytes; PCM WAV duration is limited to 60 seconds; request transport max is
5,065,536 bytes. Empty or malformed WAV files fail `400`; unsupported media/codec fails `415`.
Provider transcripts over 4,000 characters, blank text and invalid detected language tags fail
`502`. The OpenAI `gpt-transcribe` file API accepts WAV; when no single detected language is
available, the result language is null. OpenAI regional hints except `zh-CN`, `zh-TW`, `zh-HK`
fail `422 UNSUPPORTED_LANGUAGE`. Gemini accepts the same validated WAV publicly and transmits
bounded audio inline (not through the Files API), using `gemini-3.5-transcribe` in verbatim mode.
Its optional hint is mapped only for `en`, `en-US`, `en-GB`, `es`, `es-US`, `fr`, `fr-FR`, `de`,
`de-DE`, `pt`, `pt-BR`, `pt-PT`; other hints fail `422 UNSUPPORTED_LANGUAGE`. Gemini currently
returns `language: null` rather than guessing a detected locale from plain-text output.
Other syntactically accepted tags are not guaranteed supported. Uploaded files are closed;
without an enabled selected provider/key, transcription returns `503`.

## Shared validation, errors and operations

Language tags normalize ASCII case (`EN` → `en`, `es-mx` → `es-MX`) and then match
`^[a-z]{2,3}(?:-[A-Z]{2})?$`. Set `SUPPORTED_LANGUAGES` as a JSON list to reject unsupported
request tags with `422 UNSUPPORTED_LANGUAGE`; an empty list validates syntax only and is **not**
a claim about provider capabilities. Selected adapters must still verify real language support.
Unknown JSON properties are rejected. JSON request bodies
have a 100,000-byte transport cap; compressed request bodies are not accepted. All `POST` responses
are typed in OpenAPI. `/health` returns `{"status":"ok"}` even if inference is unavailable.
Missing multipart parts, invalid JSON and unknown JSON fields yield `422 INVALID_INPUT`.
Unknown routes yield `404 NOT_FOUND`; unsupported methods yield `405 INVALID_INPUT`.

Failures have the shape:

```json
{"error":{"code":"INVALID_INPUT","message":"The request could not be processed.","request_id":"opaque-id"}}
```

`X-Request-ID` echoes the generated request ID. Current codes:

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `INVALID_AUDIO` | Empty or malformed WAV audio |
| 401 | `UNAUTHORIZED` | Missing or invalid production gateway key |
| 403 | `FORBIDDEN` | Non-loopback peer in local mode |
| 422 | `INVALID_INPUT` | Invalid JSON/schema, missing part or malformed language hint |
| 422 | `UNSUPPORTED_LANGUAGE` | Configured language capability list excludes the request tag, or transcription adapter cannot represent the hint |
| 413 | `PAYLOAD_TOO_LARGE` | Request or configured semantic limit exceeded |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Unsupported audio MIME/codec or content encoding |
| 429 | `RATE_LIMITED` | Process-local peer request limit; includes `Retry-After` |
| 429 | `PROVIDER_RATE_LIMITED` | Upstream provider throttling (when enabled) |
| 502 | `BAD_UPSTREAM_RESPONSE` | Provider output failed validation |
| 502 | `PROVIDER_FAILURE` | Unexpected adapter failure |
| 503 | `PROVIDER_UNAVAILABLE` | No provider/key, invalid provider credentials/configuration, or unavailable upstream |
| 503 | `PROVIDER_QUOTA_EXCEEDED` | Upstream provider quota exhausted (when enabled) |
| 504 | `PROVIDER_TIMEOUT` | Provider operation exceeded deadline |
| 500 | `INTERNAL_ERROR` | Unexpected server error |
| 404 | `NOT_FOUND` | Unknown route |
| 405 | `INVALID_INPUT` | Unsupported method |

`DEPLOYMENT_MODE=local` (default) permits inference routes only for loopback ASGI peers.
`DEPLOYMENT_MODE=production` fails startup without `TRUSTED_GATEWAY_ENABLED=true`, a server-side
key at least 32 characters long and explicit secure origins. The backend checks the gateway key
with constant-time comparison before reading request bodies. **The gateway assertion does not
verify a gateway exists.** Never place this key in a distributed extension; public deployment
requires separate user/session authentication at a trusted gateway, backend network isolation,
TLS and distributed rate/cost quotas. Process-local per-peer rate limiting defaults to 60 requests
per 60 seconds and does not use client-supplied forwarding headers. Concurrency is capped at
four provider operations/process; the 30-second timeout includes waiting for capacity. A
text adapter honors the configured 600-token output budget (configurable up to 16,384);
character ceilings are enforced separately. No automatic SDK retries. Client disconnect
cancellation is best-effort; it cannot guarantee avoiding provider charges. Diagnostic logs contain
only request ID and fixed failure category, not prompts, transcripts, audio or credentials.
The selected async SDK client uses the configured 30-second timeout and closes at shutdown.
The transcription adapters check transcript characters after the call. OpenAI text and Gemini
text/transcription requests set `store=false`, which is not a provider zero-retention guarantee.
Gemini transcription uses stateless Interactions requests because storage is otherwise enabled
there by default; no cross-provider fallback is attempted.

The selected provider is configured only by the backend with `AI_PROVIDER=unconfigured|openai|gemini`.
OpenAI defaults to `OPENAI_TEXT_MODEL=gpt-6.1-terra` and
`OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe`; Gemini defaults to
`GEMINI_TEXT_MODEL=gemini-3.8-flash` and
`GEMINI_TRANSCRIPTION_MODEL=gemini-3.5-transcribe`. The selected vendor's API key is private to
the server. Model access, billing, quotas and language quality must be verified with the actual
account; configure `SUPPORTED_LANGUAGES` to an operator-tested list. Offline SDK mocks are not
a live test. Switching providers does not change public v1 DTOs, but changing accepted language
hints or formats requires a contract review.

## Frontend integration/migration (not yet implemented)

The extension extracts ordered `TextChunk` records (`id`, `index`, `originalText`, optional unused
`translatedText`) after toolbar activation and speaks source text locally. There is no API
client, microphone, target-language selector, upload consent flow or translation cache. Only
`activeTab` and `scripting` are permitted. See the extension contract for TypeScript DTO examples
and the full future-consumer plan.

Map `originalText` to request `text` in `index` order, validate ID syntax before sending, and
only apply response `text` to matching `translatedText` after checking count, ID order, response
languages and active document/operation. An undeclared page language requires an explicit source
tag strategy; translated speech must use the target tag. Batch within server limits without
dropping text. No server-side reading cursor or translation cache exists. For questions, send
only consented title/current excerpt and up to five related excerpts; render `page`, `general`
and `insufficient` honestly. Source labels are not factual proof. For transcription, capture
or convert to bounded PCM WAV; browser WebM/Ogg cannot be sent through or renamed WAV.
The API returns text, never playback commands. Stop/navigation must abort and ignore stale
responses; provider cancellation is best-effort.

The user deliberately initiates the action, sees what page excerpt or microphone audio leaves
the browser, and grants explicit consent **before upload**. The extension sends only necessary
data, not hidden/form content or unrelated pages. The backend validates input and invokes the
configured provider; application code does not intentionally persist page text, transcripts or
audio, though multipart parsing may spool and vendor retention requires review. Both sides treat
webpage text as untrusted and avoid sensitive logs. Public browser-to-gateway authentication is
an unresolved deployment decision; CORS is not authorization. Local mode requires a loopback
ASGI peer. Configure the public `VITE_API_BASE_URL`, narrow extension host permission and actual
extension origin in `ALLOWED_ORIGINS` as appropriate. Never expose the server-held
`X-Aurora-API-Key` or provider credentials to the extension. Cross-repository end-to-end
compatibility and live inference remain unverified.
