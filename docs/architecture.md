# Architecture

`app/main.py` constructs FastAPI, request-size guard, CORS and exception handling.
`app/schemas/` defines strict v1 public DTOs; `app/api/routes/` only binds transport input to
services. `app/services/` enforces semantic limits, provenance and chunk invariants.
`app/providers/base.py` defines the replaceable async protocol. `app/api/dependencies.py`
wraps any injected provider with a request deadline and shared per-process concurrency cap.
Without a provider, inference fails explicitly; identity translation remains available.
`app/providers/openai_provider.py` uses one lifespan-managed `AsyncOpenAI` client when
`AI_PROVIDER=openai` and a backend-only key is set. Text uses Responses structured parsing,
separate trusted instructions and JSON-encoded untrusted data, `store=false`, no tools, no SDK
retries, and a bounded output-token budget. Services recheck IDs/order and provenance. Audio
uses an in-memory WAV buffer. Without credentials no SDK client is started. Tests use offline
fakes; no database, browsing or server-side reading session is used. Model-level grounding and
prompt-injection resistance are not established by structural tests alone.

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
the text adapter's token budget. The file-transcription API has no documented output-token
parameter; the backend checks transcript size after inference.
