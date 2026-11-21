# Aurora Reader API — proposed backend v1 contract

Status: implemented **backend proposal**, not synchronized with the extension. Base URL in local
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

One or more chunks, maximum 20; ID is 1–100 ASCII letters/digits/underscore/hyphen, unique
per request; nonblank text maximum 4,000 characters/chunk and 20,000 combined. Translation
preserves count, IDs and order; malformed provider results fail rather than being repaired.
Same-language requests return unchanged text/IDs without a provider after access, rate and
language checks. Different languages use the optional configured OpenAI adapter or return `503`
when disabled/missing a key. Incomplete structured output or mismatched IDs fail `502`; the
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
Page context is always untrusted data; the backend does not fetch URLs. With OpenAI enabled,
structured results are validated, but a source label is not proof of factual grounding.
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
`502`. The `gpt-transcribe` file API accepts WAV; when no single detected language is available,
the result language is null. Regional hints except `zh-CN`, `zh-TW`, `zh-HK` fail
`422 UNSUPPORTED_LANGUAGE` with this adapter. Other syntactically accepted tags are not
guaranteed supported. Uploaded files are closed; the SDK receives a short-lived in-memory
buffer. Without an enabled provider/key, transcription returns `503`.

## Shared validation, errors and operations

Language tags normalize ASCII case (`EN` → `en`, `es-mx` → `es-MX`) and then match
`^[a-z]{2,3}(?:-[A-Z]{2})?$`. Set `SUPPORTED_LANGUAGES` as a JSON list to reject unsupported
request tags with `422 UNSUPPORTED_LANGUAGE`; an empty list validates syntax only and is **not**
a claim about provider capabilities. Selected adapters must still verify real language support.
Unknown JSON properties are rejected. JSON request bodies
have a 100,000-byte transport cap; compressed request bodies are not accepted. All `POST` responses
are typed in OpenAPI. `/health` returns `{"status":"ok"}` even if inference is unavailable.

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
| 422 | `UNSUPPORTED_LANGUAGE` | Configured language capability list excludes the request tag |
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
The shared async SDK client uses the configured 30-second timeout and closes at shutdown.
The file-transcription endpoint does not expose a documented output-token cap; the backend checks
transcript characters after the call. Text requests set `store=false`, which is not a provider
zero-retention guarantee.

Default models: `gpt-6.1-terra` for text (documented Responses structured outputs; $1/1M input
and $5/1M output tokens in reviewed pricing) and `gpt-transcribe` for file audio (documented
WAV support; $0.0045/minute in reviewed pricing). Pricing, account availability and quotas can
change. Provider documentation does not guarantee comprehensive text language quality; configure
`SUPPORTED_LANGUAGES` to an operator-tested list. Offline SDK mocks are not a live test.

## Frontend integration/migration (not yet implemented)

The extension's `docs/api-contract.md` currently says shapes and errors are not agreed and there
is no `src/types/api.ts` or `src/services/api-client.ts`. Before integration, ratify this proposal
and limits in that contract. Add types for `TranslationChunk/Request/Response`,
`QuestionContext/Request/Response`, `AnswerSource`, `TranscriptionResponse` and the error envelope
to `src/types/api.ts`. Implement JSON and multipart requests, runtime validation, request
cancellation and error-code handling in `src/services/api-client.ts`. Convert the extension's
`TextChunk` (`originalText`, `index`) to `{id,text}` and map returned chunks back by stable ID,
never by implicit position alone. The extension must provide consent before text/audio upload,
manage its own playback/microphone state, configure the public `VITE_API_BASE_URL` and origin
permission, and never receive provider secrets. Cross-repository end-to-end compatibility is not
verified.
The extension must also choose supported PCM WAV recording (not Ogg/WebM), normalize tags, handle
`401`/`403`/`429` and `UNSUPPORTED_LANGUAGE`, and never send a gateway key from browser code.
