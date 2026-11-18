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

Configuration uses environment variables (see `.env.example`); Pydantic Settings also loads
an ignored local `.env`. `AI_PROVIDER=unconfigured` is the only supported value in this phase.
Do not place a provider key in the extension or assume setting OpenAI variables enables inference.
The provider interface is in `app/providers/base.py`; a verified async provider adapter is a
subsequent milestone.

Default limits: 20 chunks, 4,000 characters each, 20,000 total translation characters;
1,000 question characters; 12,000 context characters with up to 5 related chunks; 5,000,000
audio bytes and 60 seconds for WAV; 100,000 JSON-body bytes; 30-second provider deadline; four concurrent provider
operations; 600 output tokens reserved for a future adapter. All are configurable via uppercase
environment names. The multipart transport budget includes 65,536 bytes overhead. Supported
audio containers are PCM WAV, Ogg and WebM with matching MIME and container signature; **Ogg/WebM
codecs and duration are not verified** and actual transcription is unavailable until an adapter is installed.

The default allowed browser origin is `http://localhost:5173`; configure `ALLOWED_ORIGINS`
as a JSON list including the actual `chrome-extension://<id>` origin when known. CORS is not
authentication. **Never publicly expose this unauthenticated paid-inference API** before adding
authentication, rate/cost limits and deployment/privacy review. No audio, page text or transcript
is persisted by application code; multipart parsing may temporarily spool uploads to disk and
closes them after handling. Third-party retention must be reviewed before enabling an adapter.

The extension currently has no API DTOs/client. See the contract's frontend migration section;
this backend proposal has **not** been ratified across repositories.
