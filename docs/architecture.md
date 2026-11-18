# Architecture

`app/main.py` constructs FastAPI, request-size guard, CORS and exception handling.
`app/schemas/` defines strict v1 public DTOs; `app/api/routes/` only binds transport input to
services. `app/services/` enforces semantic limits, provenance and chunk invariants.
`app/providers/base.py` defines the replaceable async protocol. `app/api/dependencies.py`
wraps any injected provider with a request deadline and shared per-process concurrency cap.
Without a provider, inference fails explicitly; identity translation remains available.
Provider implementation and model selection await verified capabilities. The fake provider lives
only under `tests/`. No database, browsing, or server-side reading session is used.
`app/prompts/` contains policy text for a future adapter; it is not yet sent to any model,
so model-level prompt-injection resistance has not been validated.
