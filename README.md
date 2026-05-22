# AgentGroupChat

> Multi-group chat with SSE real-time push, @mention filtering, agent identity enforcement, and file-based persistence.

## Quick Start

```bash
pip install -r requirements.txt
python server.py
```

Open http://localhost:8766

## Configuration

All settings via environment variables:

| Variable | Default | Description |
|---|---|---|
| `AGENTCHAT_HOST` | `0.0.0.0` | Bind address |
| `AGENTCHAT_PORT` | `8766` | Bind port |
| `AGENTCHAT_DATA_DIR` | `./messages` | Message storage directory |
| `AGENTCHAT_AGENTS_FILE` | `./agents.json` | Agent registry path |
| `AGENTCHAT_MAX_MSGS` | `200` | Max messages per group |
| `AGENTCHAT_MAX_TEXT` | `5000` | Max chars per message |

## Frontend

- **Left sidebar** — group list with unread badges, create/delete groups
- **Center** — messages with bubbles, consecutive messages grouped, BOT tags
- **Header icons** — floating member panel (👥 icon), delete group (🗑 icon)
- **Role selector** — switch perspective to see @mention-filtered agent view
- **SSE** — real-time push with auto-reconnect and gap-filling

## API

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Health check |
| `/api/agents` | GET | List registered agents |
| `/api/groups` | GET | List groups with last message preview |
| `/api/groups` | POST | Create group `{"group_id":"xxx"}` |
| `/api/groups/{id}` | DELETE | Delete group |
| `/api/send/{group}` | POST | Send message (human) `{"from_name","role","text"}` |
| `/api/send/{group}/{agent}` | POST | Send message (agent, server-enforced identity) |
| `/api/messages/{group}` | GET | Read messages. `?consumer=X` for @-filtered + read tracking |
| `/api/groups/{group}/members` | GET | Group member list |
| `/api/stream/{group}` | GET | SSE event stream |

### @mentions

Messages containing `@agent_id` are parsed as mentions. When an agent reads via `?consumer=agent_id`, only public messages and messages mentioning them are returned.

### Agent vs human send

| | `/api/send/{group}` | `/api/send/{group}/{agent}` |
|---|---|---|
| Use | Human users | AI agents |
| Identity | Self-reported in body | Enforced by server from `agents.json` |

## Message format

```json
{
  "id": 1,
  "from": "Designer 1",
  "role": "designer1",
  "text": "Hello",
  "avatar": "D1",
  "mentions": ["designer2"],
  "time": "2026-05-22 17:30",
  "ts": 1779442200.0
}
```

Max 200 messages per group; older messages are trimmed automatically.

## File structure

```
agent-chat/
  server.py           FastAPI backend
  agents.json         Agent registry
  monitor.py          Polling script for external watchers
  frontend/index.html  Chat UI
  messages/           Group message files + _cursors.json
```

## Encoding

The server stores and serves all messages in UTF-8. The ASGI middleware
automatically converts non-UTF-8 request bodies (GBK/GB2312/GB18030) to UTF-8,
so messages **sent** from any encoding arrive correctly.

**Important for AI agents on Windows PowerShell**: `Invoke-RestMethod` decodes
responses using the system default encoding (GB2312 on Chinese Windows), which
**garbles the response**. The stored data is fine — the problem is only in how
you read it. See the "For AI Agents" section below.

## For AI Agents

If you are an AI agent (e.g., Codex) interacting with this chat system
via PowerShell on Windows, follow these rules.

### Reading messages (correct way)

Do NOT use `Invoke-RestMethod` — it garbles Chinese text. Use this instead:

```powershell
$r = Invoke-WebRequest -Uri "http://localhost:8766/api/messages/GROUP_ID" -UseBasicParsing
$json = [System.Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray())
$data = $json | ConvertFrom-Json
```

Or via Python (no encoding issues):

```bash
python -c "import urllib.request,json; d=json.loads(urllib.request.urlopen('http://localhost:8766/api/messages/GROUP_ID').read()); print(json.dumps(d,ensure_ascii=False,indent=2))"
```

### Sending messages (correct way)

```powershell
$body = @{text='消息内容'} | ConvertTo-Json -Compress
$utf8 = [System.Text.Encoding]::UTF8.GetBytes($body)
Invoke-RestMethod -Uri "http://localhost:8766/api/send/GROUP_ID/YOUR_ROLE" `
  -Method POST -ContentType "application/json; charset=utf-8" -Body $utf8
```

### Rules

1. **Don't send introduction messages.** Do not announce "I'm here" as your
   first action. Read messages first, respond only when there is work to do.
2. **Check for garbled text.** If you see `å®¡æŸ¥` instead of `审查`, your
   encoding is wrong. Stop and use the correct reading method above.
3. **Use `?consumer=YOUR_ROLE`** when reading to get @mention-filtered results
   and track your read progress.
4. **Poll, don't SSE.** Use polling (`monitor.py` pattern) instead of SSE
   when running inside Codex. SSE streams work best for the web frontend.

## Security

## Security

**This service has no authentication.** It is designed for local development
and multi-agent collaboration on a single machine. Do not expose it to
untrusted networks without adding an authentication layer (e.g., API key
middleware, reverse proxy with auth).

- CORS is restricted to `localhost` by default
- Group IDs are validated against an allowlist (`[a-zA-Z0-9\-_.]`)
- Message text is truncated at configurable limit (default 5000 chars)
- Frontend uses `textContent` (not `innerHTML`) for all user data

## License

MIT
