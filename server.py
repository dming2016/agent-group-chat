import json, asyncio, time, re, os
from contextlib import asynccontextmanager
from pathlib import Path
from datetime import datetime
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel

# ═══════════════════════════════════════════════
#  Config (env-overridable, with safe parsing)
# ═══════════════════════════════════════════════

def _env_int(key: str, default: int) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default

HOST = os.environ.get("AGENTCHAT_HOST", "0.0.0.0")
PORT = _env_int("AGENTCHAT_PORT", 8766)
MAX_MSGS = _env_int("AGENTCHAT_MAX_MSGS", 200)
MAX_TEXT = _env_int("AGENTCHAT_MAX_TEXT", 5000)
MSG_DIR = Path(os.environ.get("AGENTCHAT_DATA_DIR", Path(__file__).parent / "messages"))
AGENTS_FILE = Path(os.environ.get("AGENTCHAT_AGENTS_FILE", Path(__file__).parent / "agents.json"))

# ═══════════════════════════════════════════════
#  ASGI encoding fix
# ═══════════════════════════════════════════════

class CharsetFixASGI:
    """Intercept raw POST/PUT/PATCH body, try UTF-8 then GBK/GB2312/GB18030."""
    FALLBACK_ENCODINGS = ["gbk", "gb2312", "gb18030"]

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in ("POST", "PUT", "PATCH"):
            return await self.app(scope, receive, send)
        body_chunks = []
        more_body = True
        while more_body:
            message = await receive()
            if message["type"] == "http.request":
                body_chunks.append(message.get("body", b""))
                more_body = message.get("more_body", False)
        raw_body = b"".join(body_chunks)
        if raw_body and len(raw_body) <= 1_048_576:
            try:
                raw_body.decode("utf-8")
            except UnicodeDecodeError:
                for enc in self.FALLBACK_ENCODINGS:
                    try:
                        raw_body = raw_body.decode(enc).encode("utf-8")
                        break
                    except (UnicodeDecodeError, UnicodeEncodeError):
                        continue
        sent = False
        async def fixed_receive():
            nonlocal sent
            if not sent:
                sent = True
                return {"type": "http.request", "body": raw_body, "more_body": False}
            return {"type": "http.request", "body": b""}
        return await self.app(scope, fixed_receive, send)

# ═══════════════════════════════════════════════
#  State
# ═══════════════════════════════════════════════

MSG_DIR.mkdir(parents=True, exist_ok=True)
CURSOR_FILE = MSG_DIR / "_cursors.json"

def _load_json(path: Path, default=None):
    try:
        return json.loads(path.read_text("utf-8")) if path.exists() else (default if default is not None else {})
    except (json.JSONDecodeError, OSError):
        return default if default is not None else {}

_agents = _load_json(AGENTS_FILE, {})
_read_cursors = _load_json(CURSOR_FILE, {})
_subscribers: dict[str, list[asyncio.Queue]] = {}
_locks: dict[str, asyncio.Lock] = {}
_cursor_lock = asyncio.Lock()

SAFE_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")

def _safe_gid(gid: str) -> str:
    if not gid or len(gid) > 64 or not all(c in SAFE_CHARS for c in gid):
        raise HTTPException(400, "invalid group_id")
    return gid

def _f(gid: str) -> Path:
    return MSG_DIR / f"{_safe_gid(gid)}.json"

def _load(gid: str) -> list[dict]:
    f = _f(gid)
    if not f.exists():
        return []
    try:
        return json.loads(f.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        return []

def _save(gid: str, msgs: list[dict]) -> None:
    tmp = _f(gid).with_suffix(".tmp")
    tmp.write_text(json.dumps(msgs, ensure_ascii=False, indent=2), "utf-8")
    os.replace(tmp, _f(gid))

def _get_lock(gid: str) -> asyncio.Lock:
    """Acquire per-group lock. Safe in asyncio (no await between check and set)."""
    if gid not in _locks:
        _locks[gid] = asyncio.Lock()
    return _locks[gid]

async def _save_cursors_safe() -> None:
    async with _cursor_lock:
        CURSOR_FILE.write_text(json.dumps(_read_cursors, ensure_ascii=False), "utf-8")

_mention_re = re.compile(r"@(\w[\w-]*)")

def _parse_mentions(text: str) -> list[str]:
    return list(set(_mention_re.findall(text)))

async def _broadcast(gid: str, msg: dict) -> None:
    dead = []
    for q in _subscribers.get(gid, []):
        try:
            q.put_nowait(msg)
        except asyncio.QueueFull:
            dead.append(q)
    for q in dead:
        _subscribers.get(gid, []).remove(q)

def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")

# ═══════════════════════════════════════════════
#  Models
# ═══════════════════════════════════════════════

class SendMsg(BaseModel):
    from_name: str = ""
    role: str = ""
    text: str
    avatar: str = ""

class CreateGroup(BaseModel):
    group_id: str
    name: str = ""

# ═══════════════════════════════════════════════
#  SSE heartbeat cleanup
# ═══════════════════════════════════════════════

async def _heartbeat_cleanup():
    """Periodically probe and purge dead subscriber queues."""
    while True:
        await asyncio.sleep(60)
        for gid, queues in list(_subscribers.items()):
            alive = []
            for q in queues:
                try:
                    q.put_nowait(None)
                    try:
                        q.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                    alive.append(q)
                except asyncio.QueueFull:
                    alive.append(q)
            _subscribers[gid] = alive

# ═══════════════════════════════════════════════
#  Lifespan (replaces deprecated on_event)
# ═══════════════════════════════════════════════

@asynccontextmanager
async def _lifespan(app: FastAPI):
    """Startup: launch heartbeat. Shutdown: save cursors."""
    asyncio.create_task(_heartbeat_cleanup())
    yield
    try:
        CURSOR_FILE.write_text(json.dumps(_read_cursors, ensure_ascii=False), "utf-8")
    except Exception:
        pass

# ═══════════════════════════════════════════════
#  App setup
# ═══════════════════════════════════════════════

_raw_app = FastAPI(title="AgentGroupChat", lifespan=_lifespan)
_raw_app.add_middleware(
    CORSMiddleware,
    allow_origins=[f"http://localhost:{PORT}", f"http://127.0.0.1:{PORT}"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# ═══════════════════════════════════════════════
#  Routes: Health
# ═══════════════════════════════════════════════

@_raw_app.get("/api/health")
async def health() -> dict:
    json_files = [f for f in MSG_DIR.glob("*.json") if not f.name.startswith("_")]
    return {"status": "ok", "groups": len(json_files), "agents": len(_agents)}

# ═══════════════════════════════════════════════
#  Routes: Agents
# ═══════════════════════════════════════════════

@_raw_app.get("/api/agents")
async def get_agents() -> dict:
    return {"agents": _agents}

# ═══════════════════════════════════════════════
#  Routes: Groups
# ═══════════════════════════════════════════════

def _group_meta(f: Path) -> dict:
    try:
        ms = json.loads(f.read_text("utf-8"))
    except (json.JSONDecodeError, OSError):
        ms = []
    last = ms[-1] if ms else None
    return {
        "group_id": f.stem,
        "message_count": len(ms),
        "last_message": last["text"][:50] if last else "",
        "last_time": last["time"] if last else "",
    }

@_raw_app.get("/api/groups")
async def groups() -> dict:
    gs = [_group_meta(f) for f in sorted(MSG_DIR.glob("*.json")) if not f.name.startswith("_")]
    return {"groups": gs}

@_raw_app.post("/api/groups")
async def create_group(body: CreateGroup) -> dict:
    if _f(body.group_id).exists():
        raise HTTPException(409, "group exists")
    _save(body.group_id, [])
    return {"group_id": body.group_id, "name": body.name or body.group_id}

@_raw_app.delete("/api/groups/{group_id}")
async def delete_group(group_id: str) -> dict:
    f = _f(group_id)
    if not f.exists():
        raise HTTPException(404, "group not found")
    lock = _get_lock(group_id)
    async with lock:
        f.unlink()
    prefix = group_id + ":"
    async with _cursor_lock:
        for k in [k for k in _read_cursors if k.startswith(prefix)]:
            del _read_cursors[k]
        CURSOR_FILE.write_text(json.dumps(_read_cursors, ensure_ascii=False), "utf-8")
    return {"deleted": group_id}

# ═══════════════════════════════════════════════
#  Routes: Send
# ═══════════════════════════════════════════════

@_raw_app.post("/api/send/{group_id}/{agent_id}")
async def send_as_agent(group_id: str, agent_id: str, body: SendMsg) -> dict:
    agent = _agents.get(agent_id)
    if not agent:
        raise HTTPException(400, f"unknown agent: {agent_id}")
    text = body.text
    truncated = len(text) > MAX_TEXT
    if truncated:
        text = text[:MAX_TEXT]
    mentions = _parse_mentions(text)
    lock = _get_lock(group_id)
    async with lock:
        ms = _load(group_id)
        msg = {
            "id": len(ms) + 1,
            "from": agent["name"], "role": agent["role"],
            "text": text, "avatar": agent["avatar"],
            "mentions": mentions,
            "time": _now(), "ts": time.time(),
        }
        ms.append(msg)
        if len(ms) > MAX_MSGS:
            ms = ms[-MAX_MSGS:]
        _save(group_id, ms)
    await _save_cursors_safe()
    await _broadcast(group_id, msg)
    resp = dict(msg)
    if truncated:
        resp["truncated"] = True
    return resp

@_raw_app.post("/api/send/{group_id}")
async def send_msg(group_id: str, body: SendMsg) -> dict:
    text = body.text
    truncated = len(text) > MAX_TEXT
    if truncated:
        text = text[:MAX_TEXT]
    mentions = _parse_mentions(text)
    lock = _get_lock(group_id)
    async with lock:
        ms = _load(group_id)
        msg = {
            "id": len(ms) + 1,
            "from": body.from_name, "role": body.role,
            "text": text,
            "avatar": body.avatar or (body.from_name[0] if body.from_name else "?"),
            "mentions": mentions,
            "time": _now(), "ts": time.time(),
        }
        ms.append(msg)
        if len(ms) > MAX_MSGS:
            ms = ms[-MAX_MSGS:]
        _save(group_id, ms)
    await _save_cursors_safe()
    await _broadcast(group_id, msg)
    resp = dict(msg)
    if truncated:
        resp["truncated"] = True
    return resp

# ═══════════════════════════════════════════════
#  Routes: Messages
# ═══════════════════════════════════════════════

@_raw_app.get("/api/messages/{group_id}")
async def get_msgs(group_id: str, since: int = 0, role: str = "", consumer: str = "") -> dict:
    ms = _load(group_id)
    cid = consumer or role
    if cid and cid in _agents:
        ms = [m for m in ms if not m.get("mentions") or cid in m["mentions"]]
    if cid:
        cursor_key = f"{group_id}:{cid}"
        async with _cursor_lock:
            since = max(since, _read_cursors.get(cursor_key, 0))
    if since > 0:
        ms = [m for m in ms if m["id"] > since]
    if cid and ms:
        async with _cursor_lock:
            _read_cursors[f"{group_id}:{cid}"] = ms[-1]["id"]
    return {"messages": ms}

# ═══════════════════════════════════════════════
#  Routes: Members
# ═══════════════════════════════════════════════

@_raw_app.get("/api/groups/{group_id}/members")
async def group_members(group_id: str) -> dict:
    ms = _load(group_id)
    seen: dict[str, dict] = {}
    # Agents who have sent messages
    for m in ms:
        role = m.get("role", "")
        if role in _agents and role not in seen:
            seen[role] = {"name": _agents[role]["name"], "role": role,
                          "avatar": _agents[role]["avatar"], "last_seen": m["time"],
                          "active": True}
    # Agents who have polled (read cursor exists for this group)
    prefix = group_id + ":"
    for key in _read_cursors:
        if key.startswith(prefix):
            role = key[len(prefix):]
            if role in _agents and role not in seen:
                seen[role] = {"name": _agents[role]["name"], "role": role,
                              "avatar": _agents[role]["avatar"], "last_seen": None,
                              "active": False}
    # Sort: active members first, then by last_seen
    result = sorted(seen.values(), key=lambda x: (0 if x.get("active") else 1, x.get("last_seen") or ""), reverse=False)
    return {"members": result}

# ═══════════════════════════════════════════════
#  Routes: SSE
# ═══════════════════════════════════════════════

@_raw_app.get("/api/stream/{group_id}")
async def stream(group_id: str, request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    _subscribers.setdefault(group_id, []).append(q)
    async def gen():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=30)
                    if msg is None:
                        continue
                    yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
                except asyncio.TimeoutError:
                    yield ":\n\n"
        finally:
            subs = _subscribers.get(group_id)
            if subs and q in subs:
                subs.remove(q)
    return StreamingResponse(gen(), media_type="text/event-stream")

@_raw_app.get("/")
async def index():
    return FileResponse(Path(__file__).parent / "frontend" / "index.html")

app = CharsetFixASGI(_raw_app)

if __name__ == "__main__":
    import uvicorn
    print(f"AgentGroupChat starting on {HOST}:{PORT}")
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
