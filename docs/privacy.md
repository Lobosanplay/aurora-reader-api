# Privacy and deployment gate

The API does not intentionally persist user page text, questions, transcripts or recordings.
The multipart parser may spool large uploads to temporary storage; upload resources are closed
after the request. No content-bearing application logs are emitted. Provider adapters must avoid
logging prompts/audio and document the third party's processing and retention terms before
deployment. No provider is enabled in this phase.

Only explicitly configured origins are allowed by CORS, but CORS does not stop non-browser
clients. Before public deployment, add abuse prevention, authentication or equivalent access
controls, usage/cost quotas, HTTPS and operational monitoring. Review proxy upload limits and
extension origins, including published extension IDs. Treat all supplied page text as untrusted.
