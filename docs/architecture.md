# Architecture

`app/main.py` constructs FastAPI, request-size guard, CORS and exception handling.
`app/schemas/` defines strict v1 public DTOs; `app/api/routes/` only binds transport input to
services. `app/services/` enforces semantic limits, provenance and chunk invariants.
`app/providers/base.py` defines the replaceable async protocol. `app/api/dependencies.py`
wraps any injected provider with a request deadline and shared per-process concurrency cap.
Without a provider, inference fails explicitly; identity translation remains available.
`app/providers/factory.py` constructs only the selected OpenAI or Gemini adapter when that
provider's backend-only key is set and closes its client at shutdown. Both implement
`app/providers/base.py` without changing routes or services. OpenAI uses Responses structured
parsing and in-memory WAV transcription; Gemini uses structured JSON text output and inline-WAV
transcription, without remote Files API uploads. Both separate trusted instructions from
JSON-encoded untrusted text, request `store=false`, enable no retrieval tools or SDK retries,
and bound text output tokens. Services recheck IDs/order and provenance. No automatic fallback
sends private data to a different vendor. Tests use offline fakes; no database, browsing or
server-side reading session is used. Model-level grounding and prompt-injection resistance are
not established by structural tests alone.

`app/main.py` gates local inference requests by loopback peer; production startup requires a
gateway assertion and a server-held gateway key. Authentication occurs before body buffering.
`app/core/rate_limit.py` caps requests per peer in a process-local window; the shared semaphore
caps provider operations, not request rates. A real public deployment needs network isolation,
gateway user/session authentication and distributed quotas. Provider adapters translate vendor
failures to the typed errors in `app/providers/errors.py`; the wrapper logs only request ID and
error category. The provider protocol remains asynchronous and vendor-neutral.

Question context labels the untrusted title and deduplicates excerpts before inference. The
service rejects `page` attribution without usable context, but factual grounding cannot be
proven by this structural check. Answer/transcript character ceilings apply independently of
the text adapter's token budget. The transcription adapters check transcript size after inference;
Gemini returns null for detected language rather than guessing from a plain-text response.
