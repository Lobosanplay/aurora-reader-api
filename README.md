# Aurora Reader API

Backend foundation for the Aurora Reader browser extension. The API handles bounded translation,
contextual questions and user-initiated audio transcription; browser extraction, playback and
recording remain extension responsibilities. **This phase has no live AI adapter.** Model-dependent
requests return `503 PROVIDER_UNAVAILABLE` until an adapter is implemented and configured; identical
source/target translation is fully operational.

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
an ignored local `.env`. `AI_PROVIDER=unconfigured` is the only supported value in this phase.
Do not place a provider key in the extension or assume setting OpenAI variables enables inference.
The provider interface is in `app/providers/base.py`; a verified async provider adapter is a
subsequent milestone.

Default limits: 20 chunks, 4,000 characters each, 20,000 total translation characters;
1,000 question characters; 12,000 context characters with up to 5 related chunks; 5,000,000
audio bytes and 60 seconds for PCM WAV; 100,000 JSON-body bytes; 2,000 answer characters;
4,000 transcript characters; 30-second provider deadline; four concurrent provider
operations; 600 output tokens reserved for a future adapter. All are configurable via uppercase
environment names. The multipart transport budget includes 65,536 bytes overhead. Only
`audio/wav` with a complete mono/stereo PCM RIFF/WAVE container (8/16/24/32-bit samples)
is accepted. Ogg and WebM are rejected until codec, duration and integrity checks are available.
Actual transcription is unavailable until an adapter is installed.

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
vendor charges. Future adapters must enforce `MAX_RESPONSE_TOKENS`, honor the provider deadline
and capability policy, and arrange upstream spending limits without inventing token accounting.
`SUPPORTED_LANGUAGES` is an optional JSON list of normalized language tags; when set, unsupported
request languages return `422 UNSUPPORTED_LANGUAGE`, including identity requests. An empty list
means syntax-only validation, **not** verified model support.

No audio, page text or transcript
is persisted by application code; multipart parsing may temporarily spool uploads to disk and
closes them after handling. Third-party retention must be reviewed before enabling an adapter.

The extension currently has no API DTOs/client. See the contract's frontend migration section;
this backend proposal has **not** been ratified across repositories.
