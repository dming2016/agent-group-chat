"""Monitor script: polls the AgentGroupChat API for new messages.

Usage: python monitor.py
Config via env vars: AGENTCHAT_URL, AGENTCHAT_GROUP, AGENTCHAT_CONSUMER, AGENTCHAT_INTERVAL, AGENTCHAT_FILTER_ROLE
"""

import json, time, os
from pathlib import Path
from urllib.request import urlopen

BASE_URL = os.environ.get("AGENTCHAT_URL", "http://localhost:8766")
GROUP = os.environ.get("AGENTCHAT_GROUP", "code-review")
CONSUMER = os.environ.get("AGENTCHAT_CONSUMER", "codex-monitor")
INTERVAL = int(os.environ.get("AGENTCHAT_INTERVAL", "180"))
FILTER_ROLE = os.environ.get("AGENTCHAT_FILTER_ROLE", "")  # skip messages from this role
TIMEOUT = int(os.environ.get("AGENTCHAT_TIMEOUT", "30"))
STATE_FILE = Path(__file__).parent / "_monitor_state.json"

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"last_id": 0}

def save_state(s):
    STATE_FILE.write_text(json.dumps(s), "utf-8")

def main():
    state = load_state()
    print(f"monitor: group={GROUP} consumer={CONSUMER} last_id={state['last_id']} interval={INTERVAL}s")
    if FILTER_ROLE:
        print(f"         filtering out role={FILTER_ROLE}")
    print("Press Ctrl+C to stop\n")

    while True:
        try:
            url = f"{BASE_URL}/api/messages/{GROUP}?consumer={CONSUMER}"
            data = json.loads(urlopen(url, timeout=TIMEOUT).read())
            msgs = data.get("messages", [])

            new_msgs = [m for m in msgs if m["id"] > state["last_id"]]
            if FILTER_ROLE:
                new_msgs = [m for m in new_msgs if m["role"] != FILTER_ROLE]

            if new_msgs:
                for m in new_msgs:
                    print(f"\n[{m['time']}] {m['from']}:")
                    print(m["text"][:500])
                    print("-" * 40)
                state["last_id"] = msgs[-1]["id"] if msgs else state["last_id"]
                save_state(state)
        except Exception as e:
            print(f"poll error: {e}")

        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
