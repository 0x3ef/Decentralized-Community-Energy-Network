# Backend development

Install the backend in editable mode with development dependencies:

```bash
cd apps/backend
python -m pip install -e '.[dev]'
pytest
pytest tests/test_energy_service.py -q
pytest tests/test_marketplace_service.py -k fill -q
ruff check .
mypy .
```

Use `make setup` at repository root for the full local stack. Use `make test-backend` for Docker-backed backend tests and `./scripts/test.sh --integration` for integration suites.
