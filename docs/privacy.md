# Privacy and deployment gate

The API does not intentionally persist user page text, questions, transcripts or recordings.
The multipart parser may spool large uploads to temporary storage; upload resources are closed
after the request. The selected OpenAI or Gemini adapter sends necessary page/question text
or short validated WAV audio to its configured vendor. Gemini sends bounded audio inline, not
through the remote Files API. Application code does not log prompts, transcripts or audio.
OpenAI text and Gemini text/transcription calls request `store=false`; OpenAI audio uses a
short-lived in-memory buffer. Gemini Interactions otherwise stores requests by default:
`store=false` is deliberate, but does **not** establish zero vendor retention. Review each
vendor's retention, training/abuse monitoring, residency, account tier, SDK/network telemetry
and infrastructure logs before sending real user content. The default provider is disabled
and the selected provider requires its own backend-only key.

Only explicitly configured origins are allowed by CORS, but CORS does not stop non-browser
clients. Local mode rejects non-loopback ASGI peers; do not proxy local mode publicly.
Production mode refuses startup without an explicit gateway assertion, server-side key and
secure origins. The key is for gateway-to-backend communication, **not** a browser credential:
browser extensions cannot keep shared secrets. The in-memory per-peer limiter and per-process
provider semaphore are backstops, not distributed access or spend controls. Before public
deployment, deploy and verify a trusted gateway with user/session authentication, distributed
rate and cost quotas, HTTPS, backend network isolation and operational monitoring. Do not set
`TRUSTED_GATEWAY_ENABLED` without such a gateway. Avoid recording gateway keys in access logs.
Review proxy upload limits and extension origins, including published extension IDs. Treat all
supplied page text as untrusted. Source labels are structurally checked, not factual proof.
Application provider diagnostics log only an opaque request ID
and a fixed error category; infrastructure logging and third-party retention need separate review.
