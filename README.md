# KStore development source

- Durable activity capture and document revisions backed by PostgreSQL.
- Asynchronous Qdrant indexing with GPU workload coordination.
- Operator-authorized behavioural reminders independent of relevance search.
- Hosted review of captured activity against configured authority documents.
- Dashboard for observed runtime state.

## Development

- Python 3.11 or later.
- `python3 -m venv .venv`
- `.venv/bin/pip install -e .`
- `.venv/bin/python -m unittest discover -s tests`
- Configure private `.env` from `.env.example`; use isolated test stores.
- Client configuration schema: `client/client.env.example`.
- Mandatory reminders use `KSTORE_REMINDER_MANIFEST` and `KSTORE_AUTHORITY_ROOT`.
- Manifest JSON: schema integer 1 and an ordered rules array of objects with unique id and relative path fields. Paths must resolve inside the authority root.
- Configure native hook trust through the harness user interface. Settings files alone do not prove execution.

## Release boundary

- This public repository contains source, not private transcripts, deployment configuration or database contents.
- Production promotion uses a separately cleared private release repository and records the exact public source revision.
- Native startup capture, peer delivery and agent compliance require runtime evidence beyond unit tests.
- The current hub deployment does not represent a complete restored multi-node P2P mesh.
