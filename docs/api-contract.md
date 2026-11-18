# Aurora Reader API — proposed backend v1 contract

Status: implemented **backend proposal**, not synchronized with the extension. Base URL in local
development: `http://localhost:8000`; production must use HTTPS. OpenAPI: `/openapi.json`,
interactive docs: `/docs`. Only the three routes below are inference endpoints.

## `POST /api/v1/translate`

JSON request:

```json
{"source_language":"en","target_language":"es","chunks":[{"id":"chunk-001","text":"Neural networks learn patterns."}]}
```

JSON response (provider-dependent translation shown illustratively, not currently available):

```json
{"source_language":"en","target_language":"es","chunks":[{"id":"chunk-001","text":"Las redes neuronales aprenden patrones."}]}
```

One or more chunks, maximum 20; ID is 1–100 ASCII letters/digits/underscore/hyphen, unique
per request; nonblank text maximum 4,000 characters/chunk and 20,000 combined. Translation
preserves count, IDs and order; malformed provider results fail rather than being repaired.
Same-language requests return unchanged text/IDs without a provider. Different languages currently
return `503` (no adapter). Input text is document data, never executable instructions.

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
The backend removes duplicate fragments and prioritizes the current chunk. A contextless question
still requires a provider to produce an insufficiency response. Possible source values in the
proposed v1 vocabulary: `page`, `general`, `insufficient`, `external`, `mixed`; **this backend rejects
`external` and `mixed`** without approved retrieval. `context_sufficient` is true only for `page`.
`general` must identify general model knowledge, not claim that knowledge comes from the page;
`insufficient` indicates no supported answer. The requested language is passed to the provider.
Page context is always untrusted data; the backend does not fetch URLs. No live answer adapter exists
in this phase; requests return `503`.

## `POST /api/v1/transcribe`

Multipart form parts: required `file`; optional `language` hint (e.g. `es`).
Successful response (illustrative; a configured provider is required):

```json
{"text":"¿Qué significa una capa en una red neuronal?","language":"es"}
```

`language` in the response is nullable when unknown. Accepted MIME/container combinations:
`audio/wav` with valid PCM RIFF/WAVE framing, `audio/ogg` with OggS header, `audio/webm` with EBML header
and WebM marker in first 128 bytes. Filenames are ignored for detection. Maximum audio content
is 5,000,000 bytes; PCM WAV duration is limited to 60 seconds; request transport max is
5,065,536 bytes. Empty files fail `400`;
unrecognized or mismatched containers fail `415`. Duration, codec, decodability and inaudibility
cannot be reliably established for Ogg/WebM from these header checks; a future adapter must check its supported
codecs and reject invalid/inaudible input. Uploaded files are closed after processing. No
transcription happens without a provider (returns `503`).

## Shared validation, errors and operations

Language tags match `^[a-z]{2,3}(?:-[A-Z]{2})?$` (syntactic validation only, **not** a list of
verified provider-supported languages). Unknown JSON properties are rejected. JSON request bodies
have a 100,000-byte transport cap; compressed request bodies are not accepted. All `POST` responses
are typed in OpenAPI. `/health` returns `{"status":"ok"}` even if inference is unavailable.

Failures have the shape:

```json
{"error":{"code":"INVALID_INPUT","message":"The request could not be processed.","request_id":"opaque-id"}}
```

`X-Request-ID` echoes the generated request ID. Current codes:

| HTTP | Code | Meaning |
|---|---|---|
| 400 | `INVALID_AUDIO` | Empty audio |
| 422 | `INVALID_INPUT` | Invalid JSON/schema, missing part or invalid language hint |
| 413 | `PAYLOAD_TOO_LARGE` | Request or configured semantic limit exceeded |
| 415 | `UNSUPPORTED_MEDIA_TYPE` | Unsupported audio signature/MIME or content encoding |
| 502 | `BAD_UPSTREAM_RESPONSE` | Provider output failed validation |
| 503 | `PROVIDER_UNAVAILABLE` | No provider or provider operation failed |
| 504 | `PROVIDER_TIMEOUT` | Provider operation exceeded deadline |
| 500 | `INTERNAL_ERROR` | Unexpected server error |

`429` is reserved for a future quota/rate limiter; this phase does not emit it. No authentication
is implemented. Concurrency is capped at four provider operations/process; the 30-second timeout
includes waiting for capacity. No automatic provider retries. Client disconnect cancellation is
best-effort; it cannot guarantee avoiding provider charges.

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
