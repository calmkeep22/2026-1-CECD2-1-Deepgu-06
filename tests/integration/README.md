# Backend-media integration tests

Place cross-service scenarios in this directory. Start the isolated local stack
from the repository root before running integration tests.

```bash
docker compose -f compose.test.yml up --build -d
docker compose -f compose.test.yml ps
```

The stack exposes backend `18000`, media API `19000`, MySQL `3307`, MediaMTX
RTMP `11935`, HLS `18888`, and MediaMTX API `19997` on localhost. It does not
require AWS credentials. Stop it with:

```bash
docker compose -f compose.test.yml down -v
```
