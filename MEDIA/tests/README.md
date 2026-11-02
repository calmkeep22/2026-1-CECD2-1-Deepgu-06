# Media server tests

Place media server tests in this directory using the `test_*.py` naming
convention. Run commands from `MEDIA` so imports resolve to the media server
`app` package.

```bash
python -m venv venv
./venv/Scripts/python -m pip install -r requirements-test.txt
./venv/Scripts/python -m pytest
```

On macOS or Linux, replace `venv/Scripts/python` with `venv/bin/python`.

HTTP calls to MediaMTX and backend callbacks should be mocked in component
tests. Use the root `compose.test.yml` stack only for integration tests.
