# Backend tests

Place backend tests in this directory using the `test_*.py` naming convention.
Run commands from `BE` so imports resolve to the backend `app` package.

```bash
python -m venv venv
./venv/Scripts/python -m pip install -r requirements-test.txt
./venv/Scripts/python -m pytest
```

On macOS or Linux, replace `venv/Scripts/python` with `venv/bin/python`.

The local test stack exposes MySQL on `127.0.0.1:3307` and the media server
on `127.0.0.1:19000`. Copy `.env.test.example` to `.env` only in an isolated
test environment, or export the same values before running tests.
