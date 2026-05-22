import json, time, os
from urllib.request import urlopen

BASE_URL = "http://localhost:8766"
GROUP = "xiuxianv4"
CONSUMER = "reviewer"
STATE_FILE = r"C:\Users\65455\Desktop\agent-chat\_reviewer_state.json"

def load_state():
    if os.path.exists(STATE_FILE):
        try:
            return json.loads(open(STATE_FILE, encoding="utf-8").read())
        except:
            pass
    return {"last_id": 0}

def save_state(s):
    open(STATE_FILE, "w", encoding="utf-8").write(json.dumps(s))

LOG_FILE = r"C:\Users\65455\Desktop\agent-chat\_reviewer_inbox.txt"

state = load_state()
last_id = state["last_id"]
print(f"Reviewer monitor: group=xiuxianv4 last_id={last_id} interval=5s")

while True:
    try:
        url = f"{BASE_URL}/api/messages/{GROUP}?consumer={CONSUMER}"
        data = json.loads(urlopen(url, timeout=10).read())
        msgs = data.get("messages", [])
        new = [m for m in msgs if m["id"] > last_id]
        if new:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                for m in new:
                    line = json.dumps(m, ensure_ascii=False)
                    f.write(line + "\n")
                    print(f"[{m['time']}] {m['from']}: {m['text'][:200]}")
            state["last_id"] = msgs[-1]["id"]
            save_state(state)
            last_id = state["last_id"]
    except Exception as e:
        print(f"err: {e}")
    time.sleep(5)
