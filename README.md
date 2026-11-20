# Aurora Reader API

Backend foundation for the Aurora Reader browser extension. The API handles bounded translation,
contextual questions and user-initiated audio transcription; browser extraction, playback and
recording remain extension responsibilities. The optional OpenAI adapter supplies real inference
when explicitly enabled with a backend-only credential. Otherwise model-dependent requests return
`503 PROVIDER_UNAVAILABLE`; identical source/target translation remains a local operation.

## Requirements and local setup

Python 3.12+ (the offline suite was run with Python 3.14). On Linux/macOS:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
uvicorn app.main:app --reload
```

On Windows, activate with `.venv\Scripts\activate` (PowerShell:
`.venv\Scripts\Activate.ps1`). Visit `http://localhost:8000/docs` for Swagger or
`http://localhost:8000/openapi.json` for the schema.

`GET /health` reports process availability, **not provider readiness**. The inference routes
are `POST /api/v1/translate`, `POST /api/v1/ask` and `POST /api/v1/transcribe`.
See [the proposed backend contract](docs/api-contract.md) for payloads and failure codes.

```bash
pytest -q
ruff check .
ruff format --check .
```

The [backend CI workflow](.github/workflows/ci.yml) runs these offline checks on pull requests
and pushes to `main` with Python 3.12 and 3.14. The tests use provider fakes; passing CI does
not demonstrate live inference or frontend integration.

ECC Tools reports about an absent ECC manifest in `AGENTS.md`, missing evaluator/reference
corpora, or harness drift are advisory for this repository: it is the Aurora Reader backend, not
the ECC Tools source repository. Do not add unrelated ECC fixtures or an undocumented manifest
just to silence those reports. If ECC check publication says it was denied or unavailable, a
GitHub App owner must enable **Checks: read and write** and the installation owner must approve
the permission update; this cannot be fixed by changing this repository's workflow permissions.

Configuration uses environment variables (see `.env.example`); Pydantic Settings also loads
an ignored local `.env`. `AI_PROVIDER=unconfigured` is the default. For **controlled loopback
development only**, set `AI_PROVIDER=openai` and provide `OPENAI_API_KEY` privately to the backend.
Installing `pip install -e ".[dev]"` includes the official `openai>=2.54,<3` SDK. A key alone
does not activate inference; opting in without a key leaves inference unavailable (503).
`OPENAI_TEXT_MODEL=gpt-6.1-terra` handles translation and answers;
`OPENAI_TRANSCRIPTION_MODEL=gpt-transcribe` handles WAV transcription. Replacements must support
Responses structured parsing or file transcription respectively. The async client is shared for
the app lifespan and closed at shutdown, with a 30-second SDK timeout and zero SDK retries.
Text calls use `store=false`, `reasoning.effort=none`, and the configured output-token budget.

Default limits: 20 chunks, 4,000 characters each, 20,000 total translation characters;
1,000 question characters; 12,000 context characters with up to 5 related chunks; 5,000,000
audio bytes and 60 seconds for PCM WAV; 100,000 JSON-body bytes; 2,000 answer characters;
4,000 transcript characters; 30-second provider deadline; four concurrent provider
operations; 600 text output tokens (configurable up to 16,384). All are configurable via uppercase
environment names. The multipart transport budget includes 65,536 bytes overhead. Only
`audio/wav` with a complete mono/stereo PCM RIFF/WAVE container (8/16/24/32-bit samples)
is accepted. Ogg and WebM are rejected until codec, duration and integrity checks are available.
Large translations may exceed the default output-token budget and fail `502` rather than drop
chunks; choose an appropriate bounded `MAX_RESPONSE_TOKENS` before sending long texts. For
transcription, the SDK receives an in-memory WAV. The optional hint is forwarded when present;
regional hints other than `zh-CN`, `zh-TW`, `zh-HK` fail `422 UNSUPPORTED_LANGUAGE` because the
provider only documents regional `zh` hints. Other syntactically valid tags do **not** guarantee
model support or accuracy; set `SUPPORTED_LANGUAGES` to an operator-tested list.

The default allowed browser origin is `http://localhost:5173`; configure `ALLOWED_ORIGINS`
as a JSON list including the actual `chrome-extension://<id>` origin when known. `DEPLOYMENT_MODE=local`
allows inference routes only from a loopback ASGI peer, including identity translation; it must
not be placed behind a publicly accessible reverse proxy. `DEPLOYMENT_MODE=production` fails
startup unless `TRUSTED_GATEWAY_ENABLED=true`, a server-side `API_ACCESS_KEY` of at least 32
characters, and explicit secure origins are configured. The backend checks `X-Aurora-API-Key`
in constant time; use a randomly generated high-entropy key held only by a trusted gateway.
**Never bundle it in the extension.**
The flag is an operator assertion, not proof that a gateway exists. A real public deployment
still requires gateway-enforced user/session authentication, distributed rate and cost quotas,
TLS and network isolation of this backend. CORS is not authentication.

`REQUESTS_PER_WINDOW=60` and `RATE_WINDOW_SECONDS=60` apply per ASGI peer per process;
429 responses include `Retry-After`. This is a development/single-process backstop, not a
distributed quota: a reverse proxy may make all users share the same peer address. The
four-operation semaphore limits concurrent provider work but neither request volume nor
vendor charges. Set upstream spending limits and monitor usage privately. Cost grows with translated
chunks, input/output tokens, repeated questions and audio duration; application logs contain no
usage content.
`SUPPORTED_LANGUAGES` is an optional JSON list of normalized language tags; when set, unsupported
request languages return `422 UNSUPPORTED_LANGUAGE`, including identity requests. An empty list
means syntax-only validation, **not** verified model support.

No audio, page text or transcript
is persisted by application code; multipart parsing may temporarily spool uploads to disk and
closes them after handling. `store=false` for text does not establish zero provider retention;
third-party data handling must be reviewed before sending real content.

Recheck official [model details](https://developers.openai.com/api/docs/models/gpt-6.1-terra),
[structured outputs](https://developers.openai.com/api/docs/guides/structured-outputs),
[file transcription](https://developers.openai.com/api/docs/guides/speech-to-text) and
[pricing](https://developers.openai.com/api/docs/pricing) before changing models. Offline tests
mock the SDK. For an **intentional live smoke test**, use a private loopback instance, an
explicitly supplied budget-limited test credential, verified model access, short synthetic
translation/question/WAV inputs and no repeated automatic calls. Remove the test credential
afterward. No live calls run from `pytest`; live inference and frontend compatibility are unverified.

The extension currently has no API DTOs/client. See the contract's frontend migration section;
this backend proposal has **not** been ratified across repositories.
