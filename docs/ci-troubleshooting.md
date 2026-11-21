# Backend CI failure modes

The [Backend checks workflow](../.github/workflows/ci.yml) runs on pull requests and pushes to
`main` using Python 3.12 and 3.14. Reproduce a failing job with the **same Python version** and:

```bash
python -m pip install -e ".[dev]"
ruff check .
ruff format --check .
pyright --pythonpath "$(command -v python)" app tests
pytest -q
```

| Failure | First check | Resolution |
|---|---|---|
| Install or dependency resolution | Python version and `pip install` output | Reproduce with the failing matrix version; update declared constraints only after verifying compatibility. |
| Ruff lint or format | Reported file and line | Fix the reported issue; run both Ruff commands again. |
| Pyright type error | Reported symbol and installed dependency types | Correct the annotation or call rather than suppressing the error. |
| Pytest failure | Failing assertion and test inputs | Reproduce locally with provider fakes; no API key is needed for the default suite. |
| OpenAPI contract test failure | `tests/test_contract_schema.py` and `docs/api-contract.md` | Restore the v1 shape or coordinate an intentional versioned contract change with the extension. |
| Tests pass locally but fail on one matrix version | Python and package versions in that job | Reproduce with that interpreter; inspect differences before changing version constraints. |
| ECC check says “publication denied or unavailable” | GitHub App installation permissions | The app owner must enable Checks read/write and the installation owner must approve the update. This is not fixed with this workflow's `permissions` setting. |

The workflow uses offline tests and does not provide live-model, deployed gateway, or
cross-repository extension evidence. ECC reference-set and hosted-evaluator notices describe
the ECC corpus, not missing Aurora backend tests. Do not attach synthetic scanner reports or
unrelated ECC fixtures to make those notices green.
