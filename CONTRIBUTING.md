# Contributing

## Setup

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
python server.py
```

## Running tests

```bash
python tests/test_smoke.py
```

Starts a server on port 18766, runs 10 smoke tests covering all endpoints
(health, CRUD groups, send as human/agent, @mention filtering, members,
frontend serving), then shuts down cleanly.

## Architecture

```
Browser / curl / Agent
        │
        ▼
┌──────────────────┐
│  CharsetFixASGI   │  ← intercepts raw body, fixes non-UTF-8 encoding
└──────┬───────────┘
       ▼
┌──────────────────┐
│    FastAPI app    │
│                   │
│  /api/health      │  health check
│  /api/agents      │  agent registry from agents.json
│  /api/groups      │  CRUD groups, each group = one JSON file
│  /api/send/*      │  append message to group file
│  /api/messages/*  │  read messages with cursor + @mention filter
│  /api/stream/*    │  SSE push, subscriber queues
│  /                │  serve frontend/index.html
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│   File system     │
│  messages/*.json  │  one file per group (JSON array, max 200 msgs)
│  _cursors.json    │  per-agent read positions
│  agents.json      │  agent name/role/avatar registry
└──────────────────┘
```

### Key decisions

- **No database** — file-based persistence with atomic writes (`tempfile` + `os.replace`). Simple, zero-setup, works everywhere. At 200 messages/group, even full JSON parse is trivially fast.

- **Agent identity enforcement** — `/api/send/{group}/{agent}` looks up the agent in `agents.json` and overrides `from_name`/`role`/`avatar`. An AI agent can't hallucinate a wrong identity.

- **@mention filtering** — `GET /api/messages/{group}?consumer=agent_id` returns only public messages and messages mentioning the consumer. Agents don't see irrelevant chatter, saving LLM context tokens.

- **Per-group + cursor locks** — each group has its own `asyncio.Lock` for message writes; a separate `asyncio.Lock` protects the cursors file. No global lock contention.

- **SSE with gap-filling** — the frontend uses `lastId` tracking. On SSE reconnect, it fetches `?since=lastId` to catch any messages sent during the disconnection.

- **Encoding fix** — `CharsetFixASGI` middleware intercepts raw request bodies before Starlette parses them. Tries UTF-8 first, then GBK/GB2312/GB18030. Solves the common problem of AI agents on Windows sending garbled Chinese text.

## Code style

- Python: PEP 8 (see `.editorconfig`)
- Frontend: 2-space indent, `textContent` for all user data (no `innerHTML` injection)
- Functions should fit on screen

## Before submitting

1. `python tests/test_smoke.py`
2. `python server.py` starts without errors
3. No user data in `messages/` (gitignored)
