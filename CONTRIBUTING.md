# Contributing

## Setup

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for tests/linting
python server.py
```

## Running tests

```bash
python tests/test_smoke.py
```

## Code style

- Python: follow PEP 8 (see `.editorconfig`)
- Frontend: 2-space indent, no trailing whitespace
- Keep functions small and focused

## Before submitting

1. Run `python tests/test_smoke.py`
2. Verify `python server.py` starts without errors
3. Make sure no user data is committed (`messages/` is gitignored)
